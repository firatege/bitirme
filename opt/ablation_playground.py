# -*- coding: utf-8 -*-
"""
Ablasyon Playground (Hızlı)
============================
Her bileşenin katkısını ölçer. Hız için:
  - Sabit ETS (add/add, damp=False) — grid yok
  - RF n_estimators=100
  - XGB n_estimators=100

Senaryolar:
  0. Baseline   : ETS EXOG + RF+XGB inv-ağırlık ensemble + REFIT
  1. No EXOG    : Carry-forward EXOG + RF+XGB + REFIT
  2. No REFIT   : ETS EXOG + RF+XGB ensemble, REFIT yok
  3. RF Only    : ETS EXOG + sadece RF + REFIT
  4. XGB Only   : ETS EXOG + sadece XGB + REFIT

Kullanım:
  .venv/bin/python opt/ablation_playground.py
"""

import warnings
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error
from statsmodels.tsa.holtwinters import ExponentialSmoothing

warnings.filterwarnings("ignore")

try:
    from xgboost import XGBRegressor
    HAVE_XGB = True
except Exception:
    HAVE_XGB = False

# =====================================================================
# AYARLAR
# =====================================================================

PANEL_CSV  = "panel_sales_orders_stock.csv"
SEED       = 42

VAL_START  = pd.Timestamp("2024-08-01")
TEST_START = pd.Timestamp("2025-02-01")
TEST_END   = pd.Timestamp("2025-08-01")

FEATURES_Y = ["orders", "stock", "orders_lag1", "orders_lag3",
              "stock_lag1", "stock_lag3", "y_lag1", "orders_ratio", "month", "year"]

# Hız için küçük parametreler
RF_PARAMS  = {"n_estimators": 100, "max_depth": 8, "random_state": SEED, "n_jobs": -1}
XGB_PARAMS = {"n_estimators": 100, "learning_rate": 0.08, "max_depth": 3,
              "subsample": 0.9, "colsample_bytree": 0.9, "random_state": SEED, "verbosity": 0}

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
    return d


def build_exog_ets(df_sku, col, start_ds, end_ds, cutoff):
    """Sabit ETS(add,add,damp=False) — grid yok, hızlı."""
    hist = df_sku[df_sku["ds"] < cutoff][["ds", col]].dropna()
    if len(hist) < 15:
        return None
    series = hist.set_index("ds")[col]
    series.index.freq = "MS"
    try:
        m = ExponentialSmoothing(series, trend="add", seasonal="add",
                                  seasonal_periods=12, damped_trend=False).fit(optimized=True)
        fut   = pd.date_range(start_ds, end_ds, freq="MS")
        fcast = m.forecast(len(fut))
        return pd.DataFrame({"ds": fut, col: np.maximum(0, fcast.values)})
    except Exception:
        return None


def build_exog_carry(df_sku, col, start_ds, end_ds, cutoff):
    """No-EXOG: son bilinen değeri ileriye taşı."""
    last_val = float(df_sku[df_sku["ds"] < cutoff][col].dropna().iloc[-1])
    fut = pd.date_range(start_ds, end_ds, freq="MS")
    return pd.DataFrame({"ds": fut, col: last_val})


def get_exog(df_sku, kind, start_ds, end_ds, cutoff):
    parts = []
    for col in ["orders", "stock"]:
        if kind == "ets":
            p = build_exog_ets(df_sku, col, start_ds, end_ds, cutoff)
        else:
            p = None
        if p is None:
            p = build_exog_carry(df_sku, col, start_ds, end_ds, cutoff)
        parts.append(p)
    return parts[0].merge(parts[1], on="ds", how="outer")


def recursive_forecast(model_rf, model_xgb, hist_df, exog_future, start_ds, end_ds, weights=(1.0, 0.0)):
    fut  = pd.date_range(start_ds, end_ds, freq="MS")
    fp   = pd.DataFrame({"ds": fut}).merge(exog_future, on="ds", how="left")
    full = pd.concat([hist_df, fp], ignore_index=True).sort_values("ds")
    preds = []
    for ds in fut:
        tmp = prep(full.copy())
        row = tmp[tmp["ds"] == ds]
        if len(row) == 0:
            preds.append(np.nan); continue
        X = row[FEATURES_Y].fillna(0).values
        yhat = weights[0] * max(0.0, float(model_rf.predict(X)[0]))
        if model_xgb is not None and weights[1] > 0:
            yhat += weights[1] * max(0.0, float(model_xgb.predict(X)[0]))
        yhat = max(0.0, yhat)
        preds.append(yhat)
        full.loc[full["ds"] == ds, "y"] = yhat
    return np.array(preds)


def inv_weights(y_true, p_rf, p_xgb, eps=1e-6):
    w_rf  = 1.0 / (mean_absolute_error(y_true, p_rf)  + eps)
    w_xgb = 1.0 / (mean_absolute_error(y_true, p_xgb) + eps)
    s = w_rf + w_xgb
    return w_rf / s, w_xgb / s


def train_models(df_fit):
    rf = RandomForestRegressor(**RF_PARAMS)
    rf.fit(df_fit[FEATURES_Y].fillna(0), df_fit["y"])
    xgb = None
    if HAVE_XGB:
        xgb = XGBRegressor(**XGB_PARAMS)
        xgb.fit(df_fit[FEATURES_Y].fillna(0).values, df_fit["y"].values)
    return rf, xgb

# =====================================================================
# ANA SENARYO ÇALIŞTIRICISI
# =====================================================================

SCENARIOS = {
    "0_baseline": {"exog": "ets",   "ensemble": "inv",   "refit": True},
    "1_no_exog":  {"exog": "carry", "ensemble": "inv",   "refit": True},
    "2_no_refit": {"exog": "ets",   "ensemble": "inv",   "refit": False},
    "3_rf_only":  {"exog": "ets",   "ensemble": "rf",    "refit": True},
    "4_xgb_only": {"exog": "ets",   "ensemble": "xgb",   "refit": True},
}


def run_sku(df_sku, cfg):
    d = prep(df_sku.copy())
    train = d[d["ds"] <  VAL_START]
    val   = d[(d["ds"] >= VAL_START) & (d["ds"] < TEST_START)]
    test  = d[(d["ds"] >= TEST_START) & (d["ds"] <= TEST_END)]
    tv    = d[d["ds"] < TEST_START]

    if len(train) < 20 or len(val) < 3 or len(test) < 3:
        return None

    # EXOG tabloları
    exog_test = get_exog(df_sku, cfg["exog"], TEST_START, TEST_END, TEST_START)
    exog_val  = get_exog(df_sku, cfg["exog"], VAL_START,
                         VAL_START + pd.DateOffset(months=5), VAL_START)

    # Train modelleri
    rf_pre, xgb_pre = train_models(train)

    # VAL tahmini → ağırlık hesabı
    hist_val = prep(df_sku[df_sku["ds"] < VAL_START].copy())
    val_rf   = recursive_forecast(rf_pre, None,    hist_val.copy(), exog_val,
                                   VAL_START, VAL_START + pd.DateOffset(months=5),
                                   weights=(1.0, 0.0))
    val_xgb  = recursive_forecast(rf_pre, xgb_pre, hist_val.copy(), exog_val,
                                   VAL_START, VAL_START + pd.DateOffset(months=5),
                                   weights=(0.0, 1.0)) if HAVE_XGB and xgb_pre else val_rf.copy()
    y_val = val["y"].values[:min(len(val_rf), len(val))]

    if cfg["ensemble"] == "inv" and HAVE_XGB and xgb_pre:
        w_rf, w_xgb = inv_weights(y_val, val_rf[:len(y_val)], val_xgb[:len(y_val)])
    elif cfg["ensemble"] == "rf":
        w_rf, w_xgb = 1.0, 0.0
    elif cfg["ensemble"] == "xgb":
        w_rf, w_xgb = 0.0, 1.0
    else:
        w_rf, w_xgb = 0.5, 0.5

    # REFIT
    if cfg["refit"]:
        rf_f, xgb_f = train_models(tv)
    else:
        rf_f, xgb_f = rf_pre, xgb_pre

    # TEST tahmini
    use_xgb = xgb_f if (w_xgb > 0 and xgb_f is not None) else None
    hist_test = prep(df_sku[df_sku["ds"] < TEST_START].copy())
    test_preds = recursive_forecast(rf_f, use_xgb, hist_test.copy(), exog_test,
                                     TEST_START, TEST_END, weights=(w_rf, w_xgb))
    y_test = test["y"].values[:len(test_preds)]
    return float(mean_absolute_error(y_test, test_preds[:len(y_test)]))


def main():
    panel = pd.read_csv(PANEL_CSV, parse_dates=["ds"])
    panel["sku"] = panel["sku"].astype(str)
    skus = panel["sku"].unique().tolist()

    print(f"SKU: {len(skus)} | XGB: {HAVE_XGB}")
    print("=" * 70)

    rows = []
    for sku in skus:
        df_sku = panel[panel["sku"] == sku].copy()
        line = f"SKU {sku}:"
        for name, cfg in SCENARIOS.items():
            if not HAVE_XGB and "xgb" in name:
                continue
            mae = run_sku(df_sku.copy(), cfg)
            tag = f"{mae:.0f}" if mae is not None else "—"
            line += f"  [{name.split('_',1)[1][:8]}={tag}]"
            if mae is not None:
                rows.append({"sku": sku, "senaryo": name, "mae": mae})
        print(line)

    df = pd.DataFrame(rows)
    print("\n" + "=" * 70)
    print("ÖZET (tüm SKU ortalaması)")
    print("=" * 70)

    summary = df.groupby("senaryo")["mae"].mean().round(1).to_frame("ort_mae")
    if "0_baseline" in summary.index:
        base = summary.loc["0_baseline", "ort_mae"]
        summary["fark"] = (summary["ort_mae"] - base).round(1)
        summary["fark_%"] = ((summary["ort_mae"] - base) / base * 100).round(1)
    print(summary.to_string())
    print("\n(+) fark = baseline'dan kötü | (-) fark = baseline'dan iyi")

    df.to_csv("opt/results_ablation.csv", index=False)
    print("\nSonuçlar: opt/results_ablation.csv")


if __name__ == "__main__":
    main()
