# -*- coding: utf-8 -*-
"""
Bootstrap B Parametresi Playground
====================================
Farklı B değerlerinde PI kalitesi ve hızı karşılaştır.

Kullanım:
  .venv/bin/python opt/bootstrap_playground.py
"""

import time
import warnings
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error

warnings.filterwarnings("ignore")

# =====================================================================
# AYARLAR
# =====================================================================

PANEL_CSV  = "panel_sales_orders_stock.csv"
SKU_FILTER = None
SEED       = 42
N_RUNS     = 10       # her B değeri için kaç kez tekrar et (kararlılık testi)

VAL_START  = pd.Timestamp("2024-08-01")
TEST_START = pd.Timestamp("2025-02-01")
TEST_END   = pd.Timestamp("2025-08-01")

FEATURES = ["orders", "stock", "orders_lag1", "orders_lag3",
            "stock_lag1", "stock_lag3", "y_lag1",
            "orders_ratio", "month", "year"]

# Test edilecek B değerleri
B_VALUES = [10, 25, 50, 100, 150, 300, 500]

rng = np.random.default_rng(SEED)

# =====================================================================
# YARDIMCILAR
# =====================================================================

def prep(df):
    d = df.copy().sort_values("ds")
    d["y_lag1"]       = d["y"].shift(1)
    d["orders_lag1"]  = d["orders"].shift(1)
    d["orders_lag3"]  = d["orders"].shift(3)
    d["stock_lag1"]   = d["stock"].shift(1)
    d["stock_lag3"]   = d["stock"].shift(3)
    d["orders_ratio"] = d["orders"] / (d["y"].shift(1) + 1)
    d["month"]        = d["ds"].dt.month
    d["year"]         = d["ds"].dt.year
    return d.dropna(subset=FEATURES)


def bootstrap_pi(yhat, residuals, B, seed=None):
    rng_b = np.random.default_rng(seed)
    res = np.array(residuals, dtype=float)
    res = res[np.isfinite(res)]
    n   = len(res)
    if n == 0:
        return np.zeros(len(yhat)), np.zeros(len(yhat)), np.zeros(len(yhat)), np.zeros(len(yhat))

    med   = np.median(res)
    res_c = res - med
    mad   = np.median(np.abs(res_c))
    b_lap = max(float(mad / np.sqrt(2)), 1e-6)

    noise = rng_b.laplace(0.0, b_lap, size=(len(yhat), B))
    sims  = np.maximum(0.0, yhat.reshape(-1,1) + noise)

    lo80 = np.quantile(sims, 0.10, axis=1)
    hi80 = np.quantile(sims, 0.90, axis=1)
    lo95 = np.quantile(sims, 0.025, axis=1)
    hi95 = np.quantile(sims, 0.975, axis=1)
    return lo80, hi80, lo95, hi95


def coverage(y_true, lo, hi):
    y = np.array(y_true)
    return float(np.mean((y >= lo) & (y <= hi)))


def pi_width(lo, hi):
    return float(np.mean(hi - lo))

# =====================================================================
# ANA TEST
# =====================================================================

def main():
    panel = pd.read_csv(PANEL_CSV, parse_dates=["ds"])
    panel["sku"] = panel["sku"].astype(str)
    skus = panel["sku"].unique().tolist()
    if SKU_FILTER:
        skus = [s for s in skus if s in SKU_FILTER]

    print(f"SKU sayısı: {len(skus)} | B değerleri: {B_VALUES} | Tekrar: {N_RUNS}")
    print("=" * 75)

    all_results = []

    for sku in skus:
        df  = prep(panel[panel["sku"] == sku].copy())
        tv  = df[df["ds"] < TEST_START]
        val = df[(df["ds"] >= VAL_START) & (df["ds"] < TEST_START)]
        test = df[(df["ds"] >= TEST_START) & (df["ds"] <= TEST_END)]

        if len(tv) < 15 or len(test) < 3:
            continue

        # Model eğit
        m = RandomForestRegressor(n_estimators=300, max_depth=8,
                                  random_state=SEED, n_jobs=-1)
        m.fit(tv[FEATURES].fillna(0), tv["y"])

        yhat_test = m.predict(test[FEATURES].fillna(0))
        yhat_val  = m.predict(val[FEATURES].fillna(0))
        residuals = (val["y"].values - yhat_val)
        y_true    = test["y"].values

        print(f"\n--- SKU: {sku} ({len(residuals)} VAL rezidüsü) ---")

        sku_rows = []
        for B in B_VALUES:
            times = []
            coverages_80, coverages_95 = [], []
            widths_80, widths_95 = [], []

            for run in range(N_RUNS):
                t0 = time.perf_counter()
                lo80, hi80, lo95, hi95 = bootstrap_pi(yhat_test, residuals, B, seed=run)
                times.append(time.perf_counter() - t0)

                coverages_80.append(coverage(y_true, lo80, hi80))
                coverages_95.append(coverage(y_true, lo95, hi95))
                widths_80.append(pi_width(lo80, hi80))
                widths_95.append(pi_width(lo95, hi95))

            row = {
                "sku":          sku,
                "B":            B,
                "coverage_80":  round(np.mean(coverages_80), 3),
                "coverage_95":  round(np.mean(coverages_95), 3),
                "width_80":     round(np.mean(widths_80), 1),
                "width_95":     round(np.mean(widths_95), 1),
                "width_80_std": round(np.std(widths_80), 2),   # kararlılık
                "time_ms":      round(np.mean(times) * 1000, 2),
            }
            sku_rows.append(row)
            print(f"  B={B:>4} | cov80={row['coverage_80']:.3f} cov95={row['coverage_95']:.3f} "
                  f"| width80={row['width_80']:>7.1f} (±{row['width_80_std']}) "
                  f"| {row['time_ms']:.2f}ms")

        all_results.extend(sku_rows)

    df_res = pd.DataFrame(all_results)

    print("\n" + "=" * 75)
    print("GENEL ÖZET (tüm SKU ortalaması)")
    print("=" * 75)
    summary = (
        df_res.groupby("B")
              .agg(
                  coverage_80=("coverage_80", "mean"),
                  coverage_95=("coverage_95", "mean"),
                  width_80=("width_80", "mean"),
                  width_80_std=("width_80_std", "mean"),
                  time_ms=("time_ms", "mean"),
              )
              .round(3)
    )

    # B=150 referans
    ref_time = summary.loc[150, "time_ms"] if 150 in summary.index else 1
    summary["hız_kazanımı"] = (ref_time / summary["time_ms"]).round(2).astype(str) + "×"

    print(summary.to_string())

    out = "opt/results_bootstrap.csv"
    df_res.to_csv(out, index=False)
    print(f"\nDetaylı sonuçlar: {out}")


if __name__ == "__main__":
    main()
