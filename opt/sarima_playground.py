# -*- coding: utf-8 -*-
"""
SARIMA Playground — farklı grid konfigürasyonlarını karşılaştır.

Kullanım:
  python sarima_playground.py

Değiştirebileceklerin:
  - CONFIGS: farklı grid kombinasyonları
  - TARGET_COL: "orders" veya "stock"
  - SKU_FILTER: belirli SKU'ları test et (None = hepsi)
  - VAL_H: kaç aylık validation
"""

import time
import warnings
import itertools
import numpy as np
import pandas as pd
from statsmodels.tsa.statespace.sarimax import SARIMAX
from sklearn.metrics import mean_absolute_error

warnings.filterwarnings("ignore")

# =====================================================================
# AYARLAR — buradan oyna
# =====================================================================

PANEL_CSV  = "panel_sales_orders_stock.csv"
TARGET_COL = "orders"       # "orders" veya "stock"
VAL_H      = 6              # kaç aylık validation penceresi
VAL_START  = pd.Timestamp("2024-08-01")
SKU_FILTER = None           # örn: ["303-104092", "303-107672"] veya None (hepsi)

# Test edilecek grid konfigürasyonları
CONFIGS = {
    "mevcut (0-3 x 0-3)": {
        "p_rng": (0, 3), "q_rng": (0, 3), "P_rng": (0, 1), "Q_rng": (0, 1)
    },
    "küçük (0-2 x 0-2)": {
        "p_rng": (0, 2), "q_rng": (0, 2), "P_rng": (0, 1), "Q_rng": (0, 1)
    },
    "minimal (0-1 x 0-1)": {
        "p_rng": (0, 1), "q_rng": (0, 1), "P_rng": (0, 1), "Q_rng": (0, 1)
    },
    "sabit ARIMA(1,1,1)": {
        "p_rng": (1, 1), "q_rng": (1, 1), "P_rng": (0, 1), "Q_rng": (0, 1)
    },
    "sabit (1,1,1)(1,1,1)": {
        "p_rng": (1, 1), "q_rng": (1, 1), "P_rng": (1, 1), "Q_rng": (1, 1)
    },
}

# =====================================================================
# SARIMA fonksiyonları
# =====================================================================

def sarima_fit_best(y, p_rng, q_rng, P_rng, Q_rng):
    best, best_aic = None, np.inf
    combos = list(itertools.product(
        range(p_rng[0], p_rng[1]+1),
        range(q_rng[0], q_rng[1]+1),
        range(P_rng[0], P_rng[1]+1),
        range(Q_rng[0], Q_rng[1]+1),
    ))
    for p, q, P, Q in combos:
        try:
            r = SARIMAX(y, order=(p,1,q), seasonal_order=(P,1,Q,12),
                        enforce_stationarity=False,
                        enforce_invertibility=False).fit(disp=False)
            if r.aic < best_aic:
                best_aic = r.aic
                best = ((p,1,q), (P,1,Q,12))
        except Exception:
            pass
    return best, len(combos)


def evaluate_config(series, config_name, cfg, val_h):
    y_all = series.sort_values("ds").set_index("ds")[TARGET_COL]
    y_all.index.freq = "MS"

    cutoff = VAL_START
    y_train = y_all[y_all.index < cutoff]
    y_val   = y_all[y_all.index >= cutoff].iloc[:val_h]

    if len(y_train) < 18 or len(y_val) < 3:
        return None

    t0 = time.perf_counter()
    best_order, n_combos = sarima_fit_best(y_train, **cfg)
    if best_order is None:
        return None

    try:
        model = SARIMAX(y_train, order=best_order[0], seasonal_order=best_order[1],
                        enforce_stationarity=False,
                        enforce_invertibility=False).fit(disp=False)
        yhat = model.get_forecast(steps=len(y_val)).predicted_mean.values
    except Exception:
        return None

    elapsed = time.perf_counter() - t0
    mae = mean_absolute_error(y_val.values, yhat)

    return {
        "config":    config_name,
        "n_combos":  n_combos,
        "best_order": str(best_order),
        "MAE":       round(mae, 3),
        "time_s":    round(elapsed, 3),
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
        print(f"\n--- SKU: {sku} ({len(df_sku)} ay) ---")

        sku_rows = []
        for cfg_name, cfg in CONFIGS.items():
            res = evaluate_config(df_sku, cfg_name, cfg, VAL_H)
            if res is None:
                print(f"  {cfg_name:<30} → veri yetersiz / fit başarısız")
                continue
            sku_rows.append(res)
            print(f"  {cfg_name:<30} | combos={res['n_combos']:>3} "
                  f"| MAE={res['MAE']:>8.3f} | {res['time_s']:.2f}s "
                  f"| {res['best_order']}")

        if sku_rows:
            best = min(sku_rows, key=lambda x: x["MAE"])
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

    # Mevcut config'e göre hız kazanımı
    ref = "mevcut (0-3 x 0-3)"
    if ref in summary.index:
        ref_sure = summary.loc[ref, "ort_sure"]
        summary["hız_kazanımı"] = (ref_sure / summary["ort_sure"]).round(2).astype(str) + "×"
        print("\nMevcut konfigürasyona göre hız kazanımı:")
        print(summary[["ort_MAE", "ort_sure", "hız_kazanımı"]].to_string())

    out = "sarima_playground_results.csv"
    df.to_csv(out, index=False)
    print(f"\nDetaylı sonuçlar: {out}")


if __name__ == "__main__":
    main()
