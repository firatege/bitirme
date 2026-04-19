# -*- coding: utf-8 -*-
"""
PI Kalibrasyon Playground
==========================
3 farklı yöntemle PI kalibrasyon sorunu çözülmeye çalışılıyor:

  Yöntem 1: Daha uzun VAL penceresi (12 ay, 18 ay)
  Yöntem 2: Rezidüleri VAL MAE'ye göre ölçekle
  Yöntem 3: Conformal Prediction (coverage garanti)

Kullanım:
  .venv/bin/python opt/pi_calibration_playground.py
"""

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
SEED       = 42
B          = 150

TEST_START = pd.Timestamp("2025-02-01")
TEST_END   = pd.Timestamp("2025-08-01")

FEATURES = ["orders", "stock", "orders_lag1", "orders_lag3",
            "stock_lag1", "stock_lag3", "y_lag1",
            "orders_ratio", "month", "year"]

# VAL pencere uzunlukları (Yöntem 1)
VAL_WINDOWS = {
    "mevcut (6 ay)":  pd.Timestamp("2024-08-01"),
    "uzun (12 ay)":   pd.Timestamp("2024-02-01"),
    "uzun (18 ay)":   pd.Timestamp("2023-08-01"),
}

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

def coverage(y_true, lo, hi):
    y = np.array(y_true)
    return float(np.mean((y >= lo) & (y <= hi)))

def pi_width(lo, hi):
    return float(np.mean(hi - lo))

def bootstrap_pi(yhat, residuals, B=150, scale=1.0):
    res = np.array(residuals, dtype=float)
    res = res[np.isfinite(res)] * scale
    n   = len(res)
    if n == 0:
        z = np.zeros(len(yhat))
        return z, z, z, z
    med   = np.median(res)
    res_c = res - med
    mad   = np.median(np.abs(res_c))
    b_lap = max(float(mad / np.sqrt(2)), 1e-6)
    noise = rng.laplace(0.0, b_lap, size=(len(yhat), B))
    sims  = np.maximum(0.0, yhat.reshape(-1,1) + noise)
    lo80  = np.quantile(sims, 0.10, axis=1)
    hi80  = np.quantile(sims, 0.90, axis=1)
    lo95  = np.quantile(sims, 0.025, axis=1)
    hi95  = np.quantile(sims, 0.975, axis=1)
    return lo80, hi80, lo95, hi95

# =====================================================================
# YÖNTEM 1: Farklı VAL Pencere Uzunlukları
# =====================================================================

def method1_val_window(df_sku):
    results = []
    d = prep(df_sku)
    test = d[(d["ds"] >= TEST_START) & (d["ds"] <= TEST_END)]
    if len(test) < 3:
        return []

    for name, val_start in VAL_WINDOWS.items():
        tv   = d[d["ds"] < TEST_START]
        val  = d[(d["ds"] >= val_start) & (d["ds"] < TEST_START)]
        train = d[d["ds"] < val_start]

        if len(train) < 12 or len(val) < 3:
            continue

        m = RandomForestRegressor(n_estimators=300, max_depth=8,
                                  random_state=SEED, n_jobs=-1)
        m.fit(tv[FEATURES].fillna(0), tv["y"])

        yhat_test = m.predict(test[FEATURES].fillna(0))
        yhat_val  = m.predict(val[FEATURES].fillna(0))
        residuals = val["y"].values - yhat_val

        lo80, hi80, lo95, hi95 = bootstrap_pi(yhat_test, residuals, B)
        y_true = test["y"].values

        results.append({
            "yöntem":      "1-VAL penceresi",
            "config":      name,
            "n_residuals": len(residuals),
            "coverage_80": round(coverage(y_true, lo80, hi80), 3),
            "coverage_95": round(coverage(y_true, lo95, hi95), 3),
            "width_80":    round(pi_width(lo80, hi80), 1),
        })
    return results

# =====================================================================
# YÖNTEM 2: Rezidü Ölçekleme
# =====================================================================

def method2_residual_scaling(df_sku):
    results = []
    d    = prep(df_sku)
    val_start = pd.Timestamp("2024-08-01")
    tv   = d[d["ds"] < TEST_START]
    val  = d[(d["ds"] >= val_start) & (d["ds"] < TEST_START)]
    test = d[(d["ds"] >= TEST_START) & (d["ds"] <= TEST_END)]

    if len(tv) < 15 or len(test) < 3 or len(val) < 3:
        return []

    m = RandomForestRegressor(n_estimators=300, max_depth=8,
                              random_state=SEED, n_jobs=-1)
    m.fit(tv[FEATURES].fillna(0), tv["y"])

    yhat_test = m.predict(test[FEATURES].fillna(0))
    yhat_val  = m.predict(val[FEATURES].fillna(0))
    residuals = val["y"].values - yhat_val
    y_true    = test["y"].values

    # Farklı ölçek faktörleri
    for scale in [1.0, 1.5, 2.0, 2.5, 3.0]:
        lo80, hi80, lo95, hi95 = bootstrap_pi(yhat_test, residuals, B, scale=scale)
        results.append({
            "yöntem":      "2-Rezidü ölçek",
            "config":      f"scale={scale}",
            "n_residuals": len(residuals),
            "coverage_80": round(coverage(y_true, lo80, hi80), 3),
            "coverage_95": round(coverage(y_true, lo95, hi95), 3),
            "width_80":    round(pi_width(lo80, hi80), 1),
        })
    return results

# =====================================================================
# YÖNTEM 3: Conformal Prediction
# =====================================================================

def method3_conformal(df_sku):
    """
    Split Conformal Prediction:
    1. Train üzerinde model eğit
    2. Calibration setinde nonconformity scores hesapla: |y - yhat|
    3. Test için: yhat ± quantile(scores, coverage_level)
    Coverage teorik olarak garanti altında.
    """
    results = []
    d = prep(df_sku)

    val_start  = pd.Timestamp("2024-08-01")
    calib_start = pd.Timestamp("2023-08-01")  # 18 aylık calibration

    train = d[d["ds"] < calib_start]
    calib = d[(d["ds"] >= calib_start) & (d["ds"] < TEST_START)]
    test  = d[(d["ds"] >= TEST_START) & (d["ds"] <= TEST_END)]

    if len(train) < 12 or len(calib) < 6 or len(test) < 3:
        return []

    m = RandomForestRegressor(n_estimators=300, max_depth=8,
                              random_state=SEED, n_jobs=-1)
    m.fit(train[FEATURES].fillna(0), train["y"])

    yhat_calib = m.predict(calib[FEATURES].fillna(0))
    scores     = np.abs(calib["y"].values - yhat_calib)  # nonconformity scores

    yhat_test = m.predict(test[FEATURES].fillna(0))
    y_true    = test["y"].values

    for target_cov, label in [(0.80, "CP-80%"), (0.95, "CP-95%")]:
        q = np.quantile(scores, target_cov)
        lo = np.maximum(0.0, yhat_test - q)
        hi = yhat_test + q
        results.append({
            "yöntem":      "3-Conformal",
            "config":      label,
            "n_residuals": len(scores),
            "coverage_80": round(coverage(y_true, lo, hi), 3),
            "coverage_95": round(coverage(y_true, lo, hi), 3),
            "width_80":    round(pi_width(lo, hi), 1),
        })
    return results

# =====================================================================
# ANA
# =====================================================================

def main():
    panel = pd.read_csv(PANEL_CSV, parse_dates=["ds"])
    panel["sku"] = panel["sku"].astype(str)
    skus = panel["sku"].unique().tolist()

    print(f"SKU sayısı: {len(skus)}")
    print("=" * 70)

    all_results = []

    for sku in skus:
        df_sku = panel[panel["sku"] == sku].copy()
        print(f"\n--- SKU: {sku} ---")

        r1 = method1_val_window(df_sku)
        r2 = method2_residual_scaling(df_sku)
        r3 = method3_conformal(df_sku)

        for r in r1 + r2 + r3:
            r["sku"] = sku
            all_results.append(r)
            print(f"  [{r['yöntem']}] {r['config']:<20} | "
                  f"n={r['n_residuals']:>3} | "
                  f"cov80={r['coverage_80']:.3f} cov95={r['coverage_95']:.3f} | "
                  f"width={r['width_80']:>8.1f}")

    df = pd.DataFrame(all_results)

    print("\n" + "=" * 70)
    print("GENEL ÖZET (tüm SKU ortalaması)")
    print("=" * 70)
    summary = (
        df.groupby(["yöntem", "config"])
          .agg(
              coverage_80=("coverage_80", "mean"),
              coverage_95=("coverage_95", "mean"),
              width_80=("width_80", "mean"),
          )
          .round(3)
    )
    print(summary.to_string())

    print("\n--- Hedef: coverage_80 ≈ 0.80, coverage_95 ≈ 0.95 ---")
    print("--- Mevcut durum: coverage_80 ≈ 0.197, coverage_95 ≈ 0.293 ---")

    out = "opt/results_pi_calibration.csv"
    df.to_csv(out, index=False)
    print(f"\nDetaylı sonuçlar: {out}")


if __name__ == "__main__":
    main()
