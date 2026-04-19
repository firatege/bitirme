# -*- coding: utf-8 -*-
"""
Pipeline Exporter
=================
Mevcut outputs/ klasöründen tek bir temiz pipeline_results.json üretir.
Model_v3.py'ye dokunmaz — sadece çıktıları okur ve birleştirir.

Dashboard / backend API için hazır JSON yapısı:
  - Her SKU: forecast serisi, geçmiş, metrikler, sipariş önerisi
  - Cross-SKU özet: stokout riski sıralaması, toplam öneri

Kullanım:
  python pipeline_exporter.py
  python pipeline_exporter.py --outputs outputs/ --out pipeline_results.json
"""

import os
import json
import argparse
import math
from datetime import datetime, timezone

import numpy as np
import pandas as pd


# =====================================================================
# YARDIMCILAR
# =====================================================================

def _safe_float(v):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    return round(float(v), 4)

def _urgency(p3m, e_t):
    """Stokout riskine göre aciliyet seviyesi."""
    if p3m is None:
        return "UNKNOWN"
    if p3m >= 0.8:
        return "CRITICAL"
    if p3m >= 0.4:
        return "HIGH"
    if p3m >= 0.1:
        return "MEDIUM"
    return "LOW"

def _urgency_color(urgency):
    return {"CRITICAL": "red", "HIGH": "orange", "MEDIUM": "yellow", "LOW": "green"}.get(urgency, "gray")

def load_recommendation(outdir):
    path = os.path.join(outdir, "reorder_recommendation.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)

def load_best_metrics(outdir, rec):
    """Seçilen combo'nun metriklerini test_summary'den çek."""
    if rec is None:
        return {}
    phase = rec.get("selected_combo", {}).get("phase", "PRE")
    fname = "test_summary_ALL_REFIT.csv" if phase == "REFIT" else "test_summary_ALL.csv"
    path  = os.path.join(outdir, fname)
    if not os.path.exists(path):
        path = os.path.join(outdir, "test_summary_ALL.csv")
    if not os.path.exists(path):
        return {}

    df = pd.read_csv(path)
    exog  = rec["selected_combo"]["exog"]
    y_var = rec["selected_combo"]["y_variant"]
    row   = df[(df["Exog"] == exog) & (df["Y-Variant"] == y_var) & (df["Horizon"] == "Full")]
    if len(row) == 0:
        row = df[df["Horizon"] == "Full"].sort_values("MAE").head(1)
    if len(row) == 0:
        return {}
    r = row.iloc[0]
    return {
        "mae":   _safe_float(r.get("MAE")),
        "rmse":  _safe_float(r.get("RMSE")),
        "mape":  _safe_float(r.get("MAPE")),
        "w_rf":  _safe_float(r.get("w_RF")),
        "w_xgb": _safe_float(r.get("w_XGB")),
    }

def load_forecast(outdir, rec):
    """Seçilen combo'nun tahmin serisini oku."""
    if rec is None:
        return []
    exog    = rec["selected_combo"]["exog"]
    y_var   = rec["selected_combo"]["y_variant"]
    suffix  = "_REFIT" if rec["selected_combo"].get("phase") == "REFIT" else ""
    fname   = f"preds_full_selected_{exog}_{y_var}{suffix}.csv".replace(" ", "_")
    path    = os.path.join(outdir, fname)

    # Fallback: preds_Full_*
    if not os.path.exists(path):
        fname = f"preds_Full_{exog}_{y_var}{suffix}.csv".replace(" ", "_")
        path  = os.path.join(outdir, fname)
    if not os.path.exists(path):
        return []

    df = pd.read_csv(path, parse_dates=["ds"])
    rows = []
    for _, r in df.iterrows():
        rows.append({
            "ds":      r["ds"].strftime("%Y-%m-%d"),
            "yhat":    _safe_float(r.get("yhat")),
            "y":       _safe_float(r.get("y")),        # gerçek değer (test döneminde var)
            "pi80_lo": _safe_float(r.get("pi80_lo")),
            "pi80_hi": _safe_float(r.get("pi80_hi")),
            "pi95_lo": _safe_float(r.get("pi95_lo")),
            "pi95_hi": _safe_float(r.get("pi95_hi")),
        })
    return rows

def load_val_exog(outdir):
    """EXOG seçim metriklerini oku."""
    path = os.path.join(outdir, "val_exog_selection_basic.csv")
    if not os.path.exists(path):
        return []
    df = pd.read_csv(path)
    rows = []
    for _, r in df.iterrows():
        rows.append({
            "exog":        str(r.get("Exog", "")),
            "val_mae_ens": _safe_float(r.get("VAL_MAE_YENS")),
            "val_mae_rf":  _safe_float(r.get("VAL_MAE_RF")),
            "val_mae_xgb": _safe_float(r.get("VAL_MAE_XGB")),
        })
    return sorted(rows, key=lambda x: (x["val_mae_ens"] or 9e9))


# =====================================================================
# ANA EXPORT
# =====================================================================

def export(outputs_dir="outputs", panel_csv="panel_sales_orders_stock.csv",
           out_path="pipeline_results.json"):

    # Panel geçmişi
    history_map = {}
    if os.path.exists(panel_csv):
        panel = pd.read_csv(panel_csv, parse_dates=["ds"])
        for sku, grp in panel.groupby("sku"):
            history_map[str(sku)] = [
                {"ds": r["ds"].strftime("%Y-%m-%d"),
                 "y": _safe_float(r.get("y")),
                 "orders": _safe_float(r.get("orders")),
                 "stock":  _safe_float(r.get("stock"))}
                for _, r in grp.sort_values("ds").iterrows()
            ]

    skus_out = []
    sku_dirs = sorted([
        d for d in os.listdir(outputs_dir)
        if os.path.isdir(os.path.join(outputs_dir, d))
        and not d.startswith("_")
        and not d.startswith(".")
        and os.path.exists(os.path.join(outputs_dir, d, "reorder_recommendation.json"))
    ])

    for sku in sku_dirs:
        outdir = os.path.join(outputs_dir, sku)
        rec     = load_recommendation(outdir)
        metrics = load_best_metrics(outdir, rec)
        forecast = load_forecast(outdir, rec)
        val_exog = load_val_exog(outdir)

        # Stokout ve öneri
        stockout = rec.get("stockout", {}) if rec else {}
        recom    = rec.get("recommendation", {}) if rec else {}
        policy   = rec.get("policy", {}) if rec else {}
        p3m      = stockout.get("p3m")
        e_t      = stockout.get("E_T_mo")
        ord_qty  = recom.get("order_qty_rounded", 0) or 0
        urgency  = _urgency(p3m, e_t)

        skus_out.append({
            "sku": sku,
            "urgency": urgency,
            "urgency_color": _urgency_color(urgency),
            "selected_model": rec.get("selected_combo") if rec else None,
            "metrics": metrics,
            "stockout": {
                "p3m":  _safe_float(p3m),
                "p6m":  _safe_float(stockout.get("p6m")),
                "expected_months": _safe_float(e_t),
            },
            "recommendation": {
                "order_qty": int(ord_qty),
                "order_qty_raw": _safe_float(recom.get("order_qty_raw")),
                "needs_reorder": ord_qty > 0,
            },
            "policy": {
                "t_check":   int(policy.get("T_CHECK", 3)),
                "h_cover":   int(policy.get("H_COVER", 6)),
                "q_target":  _safe_float(policy.get("Q")),
                "moq":       _safe_float(policy.get("MOQ")),
                "lot_size":  _safe_float(policy.get("LOT_SIZE")),
            },
            "starting_stock": _safe_float(rec.get("starting_stock")) if rec else None,
            "forecast":  forecast,
            "history":   history_map.get(sku, []),
            "val_exog_ranking": val_exog,
        })

    # Urgency sıralaması: CRITICAL > HIGH > MEDIUM > LOW
    _order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "UNKNOWN": 4}
    skus_out.sort(key=lambda x: (_order.get(x["urgency"], 4), -(x["recommendation"]["order_qty"] or 0)))

    # Cross-SKU özet
    n_critical = sum(1 for s in skus_out if s["urgency"] == "CRITICAL")
    n_reorder  = sum(1 for s in skus_out if s["recommendation"]["needs_reorder"])
    total_qty  = sum(s["recommendation"]["order_qty"] for s in skus_out)
    maes       = [s["metrics"]["mae"] for s in skus_out if s["metrics"].get("mae") is not None]
    avg_mae    = round(float(np.mean(maes)), 2) if maes else None

    result = {
        "exported_at":  datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "outputs_dir":  outputs_dir,
        "sku_count":    len(skus_out),
        "summary": {
            "critical_stockout": n_critical,
            "needs_reorder":     n_reorder,
            "total_order_qty":   total_qty,
            "avg_mae":           avg_mae,
        },
        "skus": skus_out,
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    return result


# =====================================================================
# CLI ÇIKTI
# =====================================================================

def print_summary(result, out_path="pipeline_results.json"):
    s = result["summary"]
    print(f"\n{'='*60}")
    print(f"  Pipeline Exporter — {result['exported_at']}")
    print(f"{'='*60}")
    print(f"  SKU sayısı     : {result['sku_count']}")
    print(f"  Kritik stokout : {s['critical_stockout']}")
    print(f"  Sipariş gereken: {s['needs_reorder']}")
    print(f"  Toplam qty     : {s['total_order_qty']}")
    print(f"  Ort. MAE       : {s['avg_mae']}")
    print(f"{'='*60}")

    print(f"\n{'SKU':<20} {'Aciliyet':<10} {'MAE':>7} {'P3m':>6} {'Qty':>6}  Model")
    print("-" * 65)
    for sku_data in result["skus"]:
        mae     = sku_data["metrics"].get("mae")
        p3m     = sku_data["stockout"].get("p3m")
        qty     = sku_data["recommendation"]["order_qty"]
        model   = sku_data["selected_model"] or {}
        exog    = model.get("exog", "—")
        y_var   = model.get("y_variant", "—")
        phase   = model.get("phase", "")
        urgency = sku_data["urgency"]

        tag = f"{exog}+{y_var}" + ("+REFIT" if phase == "REFIT" else "")
        print(f"  {sku_data['sku']:<18} {urgency:<10} "
              f"{(f'{mae:.1f}' if mae else '—'):>7} "
              f"{(f'{p3m:.0%}' if p3m is not None else '—'):>6} "
              f"{qty:>6}  {tag}")

    print(f"\nJSON çıktısı: {out_path}")


def main():
    parser = argparse.ArgumentParser(description="Pipeline output exporter")
    parser.add_argument("--outputs", default="outputs",     help="outputs klasörü")
    parser.add_argument("--panel",   default="panel_sales_orders_stock.csv")
    parser.add_argument("--out",     default="pipeline_results.json")
    args = parser.parse_args()

    print(f"Okunuyor: {args.outputs}/")
    result = export(args.outputs, args.panel, args.out)
    print_summary(result, args.out)


if __name__ == "__main__":
    main()
