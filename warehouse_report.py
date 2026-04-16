# -*- coding: utf-8 -*-
"""
warehouse_report.py — Depo Sipariş Raporu Üreticisi
====================================================

model_v3.py çalıştırıldıktan sonra çalıştırılır.
outputs/{SKU}/reorder_recommendation.json dosyalarını okuyarak:
  1. warehouse_order_report.csv  — insan-okunur, Excel'e atılabilir sipariş tablosu
  2. warehouse_summary.json      — API / dashboard için makine-okunur özet
  3. forecast_summary.csv        — her SKU için 3M ve 6M tahmin rakamları

Kullanım:
    python warehouse_report.py
"""

import os
import json
import math
import glob
import pandas as pd
import numpy as np
from datetime import datetime


# ---------------------------------------------------------------------------
# Yapılandırma
# ---------------------------------------------------------------------------
OUTPUTS_DIR   = "outputs"
SUMMARY_DIR   = os.path.join(OUTPUTS_DIR, "_SUMMARY")
REPORT_CSV    = os.path.join(SUMMARY_DIR, "warehouse_order_report.csv")
SUMMARY_JSON  = os.path.join(SUMMARY_DIR, "warehouse_summary.json")
FORECAST_CSV  = os.path.join(SUMMARY_DIR, "forecast_summary.csv")


# ---------------------------------------------------------------------------
# Yardımcı: Aciliyet etiketi
# ---------------------------------------------------------------------------
def urgency_label(p3m: float, e_t) -> str:
    """
    Stoksuz kalma istatistiklerine göre aciliyet rengi/etiketi.
      🔴 ACİL   — 3 ay içinde %70+ stok biter, veya E[T] ≤ 2 ay
      🟡 NORMAL — 3 ay içinde %35-70 stok biter
      🟢 GÜVENDE — düşük risk
    """
    et_val = float(e_t) if (e_t is not None and not (isinstance(e_t, float) and math.isnan(e_t))) else 99.0
    p3     = float(p3m) if p3m is not None else 0.0

    if p3 >= 0.70 or et_val <= 2.0:
        return "🔴 ACİL"
    elif p3 >= 0.35:
        return "🟡 NORMAL"
    else:
        return "🟢 GÜVENDE"


def order_action_label(order_qty: float) -> str:
    return "SİPARİŞ VER ✅" if order_qty > 0 else "Bekleme ⏸"


# ---------------------------------------------------------------------------
# Yardımcı: Tahmin CSV'sinden 3M ve 6M toplamları çek
# ---------------------------------------------------------------------------
def _read_forecast_totals(sku_outdir: str, best_exog: str, best_y: str, phase: str):
    """
    Seçilen komboya ait Full ve Short3 CSV'lerinden yhat toplamlarını döndürür.
    """
    suffix = "_REFIT" if phase == "REFIT" else ""

    # 6 aylık tahmin (Full)
    full_path = os.path.join(
        sku_outdir,
        f"preds_Full_{best_exog}_{best_y}{suffix}.csv".replace(" ", "_")
    )
    # 3 aylık tahmin (Short3)
    short_path = os.path.join(
        sku_outdir,
        f"preds_Short3_{best_exog}_{best_y}{suffix}.csv".replace(" ", "_")
    )

    def _sum_yhat(path):
        if not os.path.exists(path):
            return None, None, None
        try:
            df = pd.read_csv(path, parse_dates=["ds"])
            total = float(df["yhat"].sum())
            lo80  = float(df["pi80_lo"].sum()) if "pi80_lo" in df.columns else None
            hi80  = float(df["pi80_hi"].sum()) if "pi80_hi" in df.columns else None
            return total, lo80, hi80
        except Exception:
            return None, None, None

    yhat_6m, lo80_6m, hi80_6m = _sum_yhat(full_path)
    yhat_3m, lo80_3m, hi80_3m = _sum_yhat(short_path)

    return {
        "yhat_3m":   yhat_3m,
        "pi80_lo_3m": lo80_3m,
        "pi80_hi_3m": hi80_3m,
        "yhat_6m":   yhat_6m,
        "pi80_lo_6m": lo80_6m,
        "pi80_hi_6m": hi80_6m,
    }


# ---------------------------------------------------------------------------
# Ana Rapor Üretici
# ---------------------------------------------------------------------------
def build_report() -> tuple[pd.DataFrame, list]:
    """
    outputs/{SKU}/reorder_recommendation.json dosyalarını okur,
    birleşik rapor DataFrame'i ve JSON özet listesi döndürür.
    """
    json_paths = sorted(glob.glob(
        os.path.join(OUTPUTS_DIR, "*", "reorder_recommendation.json")
    ))

    if not json_paths:
        print(f"UYARI: {OUTPUTS_DIR} altında reorder_recommendation.json bulunamadı.")
        print("Önce `python model_v3.py` çalıştırın.")
        return pd.DataFrame(), []

    rows      = []
    json_list = []
    forecast_rows = []

    for jpath in json_paths:
        try:
            with open(jpath, encoding="utf-8") as f:
                rec = json.load(f)
        except Exception as e:
            print(f"  HATA: {jpath} okunamadı — {e}")
            continue

        sku          = rec.get("sku", "?")
        profile      = rec.get("profile", "standard")
        combo        = rec.get("selected_combo", {})
        best_exog    = combo.get("exog", "")
        best_y       = combo.get("y_variant", "")
        phase        = combo.get("phase", "PRE")

        start_stock  = rec.get("starting_stock", 0.0)
        policy       = rec.get("policy", {})
        stockout     = rec.get("stockout", {})
        coverage     = rec.get("coverage", {})
        recommendation = rec.get("recommendation", {})

        p3m          = stockout.get("p3m", 0.0)
        p6m          = stockout.get("p6m", 0.0)
        e_t          = stockout.get("E_T_mo")
        cum_demand   = coverage.get("cum_demand_q", 0.0)
        order_raw    = recommendation.get("order_qty_raw", 0.0)
        order_qty    = recommendation.get("order_qty_rounded", 0.0)

        urgency      = urgency_label(p3m, e_t)
        action       = order_action_label(order_qty)

        # Profil istatistikleri (varsa)
        pstats       = rec.get("profile_stats", {})
        mean_sales   = pstats.get("mean_sales_active", None)
        trend_slope  = pstats.get("trend_slope", None)

        # Tahmin toplamları
        sku_outdir   = os.path.join(OUTPUTS_DIR, sku)
        fc_totals    = _read_forecast_totals(sku_outdir, best_exog, best_y, phase)

        # E[T] string formatı
        et_str = f"{float(e_t):.1f} ay" if (e_t is not None and not (
            isinstance(e_t, float) and math.isnan(e_t)
        )) else "—"

        row = {
            "sku":               sku,
            "profil":            profile,
            "aksiyon":           action,
            "siparis_adedi":     int(order_qty),
            "siparis_ham":       round(order_raw, 1),
            "aciliyet":          urgency,
            "stoksuz_3m_%":      f"{p3m*100:.0f}%",
            "stoksuz_6m_%":      f"{p6m*100:.0f}%",
            "beklenen_stoksuzluk": et_str,
            "mevcut_stok":       int(start_stock),
            "kumulatif_talep_6m": round(cum_demand, 0),
            "tahmin_3m_toplam":  round(fc_totals["yhat_3m"], 0) if fc_totals["yhat_3m"] is not None else "—",
            "tahmin_6m_toplam":  round(fc_totals["yhat_6m"], 0) if fc_totals["yhat_6m"] is not None else "—",
            "MOQ":               policy.get("MOQ", 0),
            "LOT_SIZE":          policy.get("LOT_SIZE", 1),
            "T_CHECK_ay":        policy.get("T_CHECK", 3),
            "H_COVER_ay":        policy.get("H_COVER", 6),
            "secilen_model":     f"{best_exog} / {best_y} ({phase})",
            "ortalama_aktif_satis": round(mean_sales, 0) if mean_sales is not None else "—",
            "trend_birimai":     round(trend_slope, 1) if trend_slope is not None else "—",
        }
        rows.append(row)

        # Tahmin özet satırı
        forecast_rows.append({
            "sku":          sku,
            "profil":       profile,
            "yhat_3m":      fc_totals["yhat_3m"],
            "pi80_lo_3m":   fc_totals["pi80_lo_3m"],
            "pi80_hi_3m":   fc_totals["pi80_hi_3m"],
            "yhat_6m":      fc_totals["yhat_6m"],
            "pi80_lo_6m":   fc_totals["pi80_lo_6m"],
            "pi80_hi_6m":   fc_totals["pi80_hi_6m"],
            "model":        f"{best_exog} / {best_y} ({phase})",
        })

        # JSON özet
        json_list.append({
            "sku":              sku,
            "profile":          profile,
            "action":           "ORDER" if order_qty > 0 else "HOLD",
            "order_qty":        int(order_qty),
            "urgency":          urgency,
            "p_stockout_3m":    round(p3m, 3),
            "p_stockout_6m":    round(p6m, 3),
            "E_T_stockout_mo":  e_t,
            "current_stock":    int(start_stock),
            "forecast_3m":      fc_totals["yhat_3m"],
            "forecast_6m":      fc_totals["yhat_6m"],
            "cum_demand_6m":    round(cum_demand, 0),
            "model":            f"{best_exog} / {best_y} ({phase})",
        })

    report_df     = pd.DataFrame(rows)
    forecast_df   = pd.DataFrame(forecast_rows)

    # Aciliyet sıralama: ACİL > NORMAL > GÜVENDE, sonra SKU adı
    urgency_order = {"🔴 ACİL": 0, "🟡 NORMAL": 1, "🟢 GÜVENDE": 2}
    if not report_df.empty:
        report_df["_sort"] = report_df["aciliyet"].map(urgency_order).fillna(9)
        report_df = report_df.sort_values(["_sort", "sku"]).drop(columns=["_sort"]).reset_index(drop=True)

    return report_df, json_list, forecast_df


# ---------------------------------------------------------------------------
# Konsol Özet Yazdırıcı
# ---------------------------------------------------------------------------
def print_console_summary(report_df: pd.DataFrame):
    """Terminal çıktısı — özet tablo."""
    if report_df.empty:
        print("Rapor boş.")
        return

    print("\n" + "=" * 100)
    print("DEPO SİPARİŞ RAPORU")
    print(f"Oluşturma tarihi: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 100)

    # Aciliyete göre grupla
    for label in ["🔴 ACİL", "🟡 NORMAL", "🟢 GÜVENDE"]:
        grp = report_df[report_df["aciliyet"] == label]
        if grp.empty:
            continue
        print(f"\n{label}")
        print("-" * 100)
        for _, r in grp.iterrows():
            order_str = (
                f"→ {int(r['siparis_adedi']):>8,} adet sipariş ver"
                if r["siparis_adedi"] > 0
                else "→        bekleme"
            )
            print(
                f"  {r['sku']:25s}  {r['profil']:14s}  "
                f"{order_str}   "
                f"3M-stoksuz: {r['stoksuz_3m_%']:>5s}   "
                f"6M-stoksuz: {r['stoksuz_6m_%']:>5s}   "
                f"Mevcut stok: {int(r['mevcut_stok']):>8,}   "
                f"3M tahmin: {str(r['tahmin_3m_toplam']):>8s}"
            )

    # Özet istatistik
    total_order_skus = (report_df["siparis_adedi"] > 0).sum()
    acil_count       = (report_df["aciliyet"] == "🔴 ACİL").sum()
    print("\n" + "=" * 100)
    print(f"Toplam {len(report_df)} SKU analiz edildi.")
    print(f"Sipariş önerilen SKU sayısı: {total_order_skus}")
    print(f"Acil durum (🔴): {acil_count} SKU")
    print("=" * 100)


# ---------------------------------------------------------------------------
# Ana Giriş Noktası
# ---------------------------------------------------------------------------
def main():
    os.makedirs(SUMMARY_DIR, exist_ok=True)

    print("[RAPOR] reorder_recommendation.json dosyaları okunuyor...")
    result = build_report()

    if len(result) == 3:
        report_df, json_list, forecast_df = result
    else:
        print("Hata: build_report() beklenmedik değer döndürdü.")
        return

    if report_df.empty:
        return

    # 1. Sipariş raporu CSV
    report_df.to_csv(REPORT_CSV, index=False, encoding="utf-8-sig")
    print(f"[RAPOR] → {REPORT_CSV}")

    # 2. JSON özet
    summary_payload = {
        "generated_at": datetime.now().isoformat(),
        "total_skus":   len(json_list),
        "order_count":  sum(1 for r in json_list if r["action"] == "ORDER"),
        "urgent_count": sum(1 for r in json_list if "ACİL" in r["urgency"]),
        "skus":         json_list,
    }
    with open(SUMMARY_JSON, "w", encoding="utf-8") as f:
        json.dump(summary_payload, f, ensure_ascii=False, indent=2)
    print(f"[RAPOR] → {SUMMARY_JSON}")

    # 3. Tahmin özeti CSV
    if not forecast_df.empty:
        forecast_df.to_csv(FORECAST_CSV, index=False, encoding="utf-8-sig")
        print(f"[RAPOR] → {FORECAST_CSV}")

    # 4. Konsol özet
    print_console_summary(report_df)


if __name__ == "__main__":
    main()
