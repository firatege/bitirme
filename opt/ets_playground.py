# -*- coding: utf-8 -*-
"""
ETS Playground — farklı konfigürasyonları karşılaştır.

Kullanım:
  .venv/bin/python ets_playground.py

Değiştirebileceklerin:
  - CONFIGS: farklı ETS kombinasyonları
  - TARGET_COL: "orders" veya "stock"
  - SKU_FILTER: belirli SKU'ları test et (None = hepsi)
  - VAL_H: kaç aylık validation
"""

import time
import warnings
import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from sklearn.metrics import mean_absolute_error

warnings.filterwarnings("ignore")

# =====================================================================
# AYARLAR — buradan oyna
# =====================================================================

PANEL_CSV  = "panel_sales_orders_stock.csv"
TARGET_COL = "orders"
VAL_H      = 6
VAL_START  = pd.Timestamp("2024-08-01")
SKU_FILTER = None

# Test edilecek ETS konfigürasyonları
CONFIGS = {
    "mevcut (tüm grid)": {
        "trends": ["add", "mul", None],
        "seasons": ["add", "mul", None],
        "damps": [True, False],
    },
    "damp=False sabit": {
        "trends": ["add", "mul", None],
        "seasons": ["add", "mul", None],
        "damps": [False],
    },
    "add/None only": {
        "trends": ["add", None],
        "seasons": ["add", None],
        "damps": [True, False],
    },
    "sabit add-add": {
        "trends": ["add"],
        "seasons": ["add"],
        "damps": [False],
    },
    "sabit add-add-damp": {
        "trends": ["add"],
        "seasons": ["add"],
        "damps": [True],
    },
    "trend yok sadece sezon": {
        "trends": [None],
        "seasons": ["add", "mul"],
        "damps": [False],
    },
}

# =====================================================================
# ETS fonksiyonları
# =====================================================================

def fit_ets_config(y, trends, seasons, damps):
    best, best_aic = None, np.inf
    n_combos = 0
    for trend in trends:
        for seas in seasons:
            for damp in damps:
                n_combos += 1
                try:
                    if seas is None:
                        m = ExponentialSmoothing(
                            y, trend=trend, seasonal=None, damped_trend=damp
                        ).fit(optimized=True)
                    else:
                        m = ExponentialSmoothing(
                            y, trend=trend, seasonal=seas,
                            seasonal_periods=12, damped_trend=damp
                        ).fit(optimized=True)
                    aic = getattr(m, "aic", np.inf)
                    if aic < best_aic:
                        best_aic = aic
                        best = m
                except Exception:
                    continue
    return best, n_combos


def evaluate_config(series, config_name, cfg, val_h):
    y_all = series.sort_values("ds").set_index("ds")[TARGET_COL]
    y_all.index.freq = "MS"

    y_train = y_all[y_all.index < VAL_START]
    y_val   = y_all[y_all.index >= VAL_START].iloc[:val_h]

    if len(y_train) < 18 or len(y_val) < 3:
        return None

    t0 = time.perf_counter()
    model, n_combos = fit_ets_config(y_train, **cfg)
    if model is None:
        return None

    try:
        yhat = model.forecast(len(y_val))
    except Exception:
        return None

    elapsed = time.perf_counter() - t0
    mae = mean_absolute_error(y_val.values, yhat.values)

    return {
        "config":   config_name,
        "n_combos": n_combos,
        "MAE":      round(mae, 3),
        "time_s":   round(elapsed, 3),
    }


# =====================================================================
# ANA
# =====================================================================

def main():
    panel = pd.read_csv(PANEL_CSV, parse_dates=["ds"])
    panel["sku"] = panel["sku"].astype(str)

    skus = panel["sku"].unique().tolist()
    if SKU_FILTER:
        skus = [s for s in skus if s in SKU_FILTER]

    print(f"\nTest edilen SKU sayısı : {len(skus)}")
    print(f"Hedef kolon            : {TARGET_COL}")
    print(f"Validation horizon     : {VAL_H} ay")
    print(f"Config sayısı          : {len(CONFIGS)}")
    print("=" * 70)

    all_results = []

    for sku in skus:
        df_sku = panel[panel["sku"] == sku].copy()
        print(f"\n--- SKU: {sku} ---")

        sku_rows = []
        for cfg_name, cfg in CONFIGS.items():
            res = evaluate_config(df_sku, cfg_name, cfg, VAL_H)
            if res is None:
                print(f"  {cfg_name:<30} → başarısız")
                continue
            sku_rows.append(res)
            print(f"  {cfg_name:<30} | combos={res['n_combos']:>2} "
                  f"| MAE={res['MAE']:>8.3f} | {res['time_s']:.3f}s")

        if sku_rows:
            best    = min(sku_rows, key=lambda x: x["MAE"])
            fastest = min(sku_rows, key=lambda x: x["time_s"])
            print(f"  → En iyi MAE  : {best['config']} (MAE={best['MAE']})")
            print(f"  → En hızlı    : {fastest['config']} ({fastest['time_s']}s)")

        for r in sku_rows:
            r["sku"] = sku
        all_results.extend(sku_rows)

    if not all_results:
        print("\nSonuç yok.")
        return

    df = pd.DataFrame(all_results)

    print("\n" + "=" * 70)
    print("GENEL ÖZET (tüm SKU ortalaması)")
    print("=" * 70)
    summary = (
        df.groupby("config")
          .agg(
              ort_MAE=("MAE", "mean"),
              ort_sure=("time_s", "mean"),
              toplam_sure=("time_s", "sum"),
              n_combos=("n_combos", "first"),
          )
          .sort_values("ort_MAE")
    )
    print(summary.to_string())

    ref = "mevcut (tüm grid)"
    if ref in summary.index:
        ref_sure = summary.loc[ref, "ort_sure"]
        summary["hız_kazanımı"] = (ref_sure / summary["ort_sure"]).round(2).astype(str) + "×"
        print("\nMevcut konfigürasyona göre hız kazanımı:")
        print(summary[["ort_MAE", "ort_sure", "hız_kazanımı"]].to_string())

    out = "ets_playground_results.csv"
    df.to_csv(out, index=False)
    print(f"\nDetaylı sonuçlar: {out}")


if __name__ == "__main__":
    main()
