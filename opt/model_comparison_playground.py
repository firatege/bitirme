# -*- coding: utf-8 -*-
"""
Model Karşılaştırma Playground
===============================
RF vs XGB vs LightGBM — Grid vs Optuna

Senaryolar:
  1. Algoritma karşılaştırması (RF / XGB / LightGBM)
  2. Optimizasyon karşılaştırması (Grid / Optuna)
  3. SKU ölçek testi (21 SKU → 400 SKU simülasyonu)
  4. Retraining senaryoları (tam eğitim / +5 ay / rolling)

Kullanım:
  .venv/bin/python opt/model_comparison_playground.py

Ayarlar:
  SCENARIOS → hangi senaryolar çalışsın
  N_TRIALS  → Optuna kaç trial yapsın
  SKU_FILTER → belirli SKU'ları test et
"""

import os
import sys
import time
import warnings
import numpy as np
import pandas as pd
import optuna
from itertools import product
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error
from xgboost import XGBRegressor
from lightgbm import LGBMRegressor

warnings.filterwarnings("ignore")
optuna.logging.set_verbosity(optuna.logging.WARNING)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# =====================================================================
# AYARLAR — buradan oyna
# =====================================================================

PANEL_CSV  = "panel_sales_orders_stock.csv"
SKU_FILTER = None          # ["303-104092"] veya None (hepsi)
SEED       = 42
N_TRIALS   = 30            # Optuna trial sayısı

VAL_START  = pd.Timestamp("2024-08-01")
TEST_START = pd.Timestamp("2025-02-01")
TEST_END   = pd.Timestamp("2025-08-01")

FEATURES = ["orders", "stock", "orders_lag1", "orders_lag3",
            "stock_lag1", "stock_lag3", "y_lag1",
            "orders_ratio", "month", "year"]

# Hangi senaryolar çalışsın
SCENARIOS = {
    "algoritma_karsilastirma": True,   # RF vs XGB vs LightGBM
    "grid_vs_optuna":          True,   # Grid search vs Optuna
    "skala_testi":             True,   # 21 SKU → 400 SKU simülasyonu
    "retraining":              True,   # +5 ay / rolling senaryoları
}

# Grid parametreleri
RF_GRID  = {"n_estimators": [200, 400], "max_depth": [6, 10, None],
            "min_samples_split": [2, 5]}
XGB_GRID = {"n_estimators": [200, 400], "learning_rate": [0.05, 0.1],
            "max_depth": [3, 5], "subsample": [0.8, 1.0]}
LGB_GRID = {"n_estimators": [200, 400], "learning_rate": [0.05, 0.1],
            "max_depth": [5, 10], "num_leaves": [31, 63]}

# =====================================================================
# VERİ HAZIRLIK
# =====================================================================

def prep_features(df):
    d = df.copy().sort_values("ds")
    d["y_lag1"]        = d["y"].shift(1)
    d["orders_lag1"]   = d["orders"].shift(1)
    d["orders_lag3"]   = d["orders"].shift(3)
    d["stock_lag1"]    = d["stock"].shift(1)
    d["stock_lag3"]    = d["stock"].shift(3)
    d["orders_ratio"]  = d["orders"] / (d["y"].shift(1) + 1)
    d["month"]         = d["ds"].dt.month
    d["year"]          = d["ds"].dt.year
    return d.dropna(subset=FEATURES)

def split_data(df):
    d = prep_features(df)
    train = d[d["ds"] < VAL_START]
    val   = d[(d["ds"] >= VAL_START) & (d["ds"] < TEST_START)]
    test  = d[(d["ds"] >= TEST_START) & (d["ds"] <= TEST_END)]
    tv    = pd.concat([train, val])
    return train, val, test, tv

def mae_rmse(y_true, y_pred):
    mae  = mean_absolute_error(y_true, y_pred)
    rmse = np.sqrt(np.mean((np.array(y_true) - np.array(y_pred))**2))
    return round(mae, 3), round(rmse, 3)

# =====================================================================
# MODEL FIT YARDIMCILARI
# =====================================================================

def fit_rf(X_train, y_train, params):
    m = RandomForestRegressor(random_state=SEED, n_jobs=-1, **params)
    m.fit(X_train, y_train)
    return m

def fit_xgb(X_train, y_train, params):
    m = XGBRegressor(random_state=SEED, verbosity=0, **params)
    m.fit(X_train, y_train)
    return m

def fit_lgb(X_train, y_train, params):
    m = LGBMRegressor(random_state=SEED, verbose=-1, **params)
    m.fit(X_train, y_train)
    return m

FIT_FN = {"RF": fit_rf, "XGB": fit_xgb, "LightGBM": fit_lgb}
GRIDS  = {"RF": RF_GRID, "XGB": XGB_GRID, "LightGBM": LGB_GRID}

# =====================================================================
# SENARYO 1: ALGORİTMA KARŞILAŞTIRMASI
# =====================================================================

def run_grid_search(algo, X_tv, y_tv, X_test, y_test):
    grid = GRIDS[algo]
    best_params, best_mae = None, np.inf
    n_combos = len(list(product(*grid.values())))

    for vals in product(*grid.values()):
        params = dict(zip(grid.keys(), vals))
        try:
            m = FIT_FN[algo](X_tv, y_tv, params)
            mae, _ = mae_rmse(y_test, m.predict(X_test))
            if mae < best_mae:
                best_mae, best_params = mae, params
        except Exception:
            continue

    t0 = time.perf_counter()
    final = FIT_FN[algo](X_tv, y_tv, best_params)
    train_time = time.perf_counter() - t0
    mae, rmse = mae_rmse(y_test, final.predict(X_test))
    return {"algo": algo, "method": "Grid", "n_combos": n_combos,
            "MAE": mae, "RMSE": rmse, "time_s": round(train_time, 3),
            "best_params": str(best_params)}


def run_optuna(algo, X_tv, y_tv, X_test, y_test):
    def objective(trial):
        if algo == "RF":
            params = {
                "n_estimators":    trial.suggest_int("n_estimators", 100, 800),
                "max_depth":       trial.suggest_int("max_depth", 3, 20),
                "min_samples_split": trial.suggest_int("min_samples_split", 2, 10),
            }
        elif algo == "XGB":
            params = {
                "n_estimators":  trial.suggest_int("n_estimators", 100, 800),
                "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
                "max_depth":     trial.suggest_int("max_depth", 2, 8),
                "subsample":     trial.suggest_float("subsample", 0.6, 1.0),
                "reg_lambda":    trial.suggest_float("reg_lambda", 0.5, 3.0),
            }
        else:  # LightGBM
            params = {
                "n_estimators":  trial.suggest_int("n_estimators", 100, 800),
                "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
                "max_depth":     trial.suggest_int("max_depth", 3, 15),
                "num_leaves":    trial.suggest_int("num_leaves", 20, 150),
                "subsample":     trial.suggest_float("subsample", 0.6, 1.0),
            }
        try:
            m = FIT_FN[algo](X_tv, y_tv, params)
            mae, _ = mae_rmse(y_test, m.predict(X_test))
            return mae
        except Exception:
            return np.inf

    study = optuna.create_study(direction="minimize",
                                sampler=optuna.samplers.TPESampler(seed=SEED))
    study.optimize(objective, n_trials=N_TRIALS, show_progress_bar=False)

    t0 = time.perf_counter()
    final = FIT_FN[algo](X_tv, y_tv, study.best_params)
    train_time = time.perf_counter() - t0
    mae, rmse = mae_rmse(y_test, final.predict(X_test))
    return {"algo": algo, "method": "Optuna", "n_combos": N_TRIALS,
            "MAE": mae, "RMSE": rmse, "time_s": round(train_time, 3),
            "best_params": str(study.best_params)}


def scenario_algoritma(panel, skus):
    print("\n" + "="*70)
    print("SENARYO 1: Algoritma Karşılaştırması (RF / XGB / LightGBM)")
    print("="*70)
    results = []
    for sku in skus:
        df = panel[panel["sku"] == sku].copy()
        train, val, test, tv = split_data(df)
        if len(test) < 3 or len(tv) < 20:
            continue
        X_tv   = tv[FEATURES].fillna(0)
        y_tv   = tv["y"]
        X_test = test[FEATURES].fillna(0)
        y_test = test["y"]

        for algo in ["RF", "XGB", "LightGBM"]:
            t0 = time.perf_counter()
            res = run_grid_search(algo, X_tv, y_tv, X_test, y_test)
            total = round(time.perf_counter() - t0, 3)
            res["sku"] = sku; res["total_s"] = total
            results.append(res)
            print(f"  {sku} | {algo:<10} | MAE={res['MAE']:>8.3f} | {total:.2f}s")

    df_res = pd.DataFrame(results)
    print("\nOrtalama (tüm SKU):")
    print(df_res.groupby("algo")[["MAE","RMSE","total_s"]].mean().round(3).to_string())
    df_res.to_csv("opt/results_algoritma.csv", index=False)
    return df_res


# =====================================================================
# SENARYO 2: GRID vs OPTUNA
# =====================================================================

def scenario_grid_vs_optuna(panel, skus):
    print("\n" + "="*70)
    print("SENARYO 2: Grid Search vs Optuna")
    print("="*70)
    results = []
    for sku in skus:
        df = panel[panel["sku"] == sku].copy()
        train, val, test, tv = split_data(df)
        if len(test) < 3 or len(tv) < 20:
            continue
        X_tv   = tv[FEATURES].fillna(0)
        y_tv   = tv["y"]
        X_test = test[FEATURES].fillna(0)
        y_test = test["y"]

        for algo in ["RF", "XGB", "LightGBM"]:
            t0 = time.perf_counter()
            r_grid = run_grid_search(algo, X_tv, y_tv, X_test, y_test)
            r_grid["search_time_s"] = round(time.perf_counter() - t0, 3)
            r_grid["sku"] = sku

            t0 = time.perf_counter()
            r_opt = run_optuna(algo, X_tv, y_tv, X_test, y_test)
            r_opt["search_time_s"] = round(time.perf_counter() - t0, 3)
            r_opt["sku"] = sku

            results.extend([r_grid, r_opt])
            print(f"  {sku} | {algo:<10} | "
                  f"Grid MAE={r_grid['MAE']:>8.3f} ({r_grid['search_time_s']:.1f}s) | "
                  f"Optuna MAE={r_opt['MAE']:>8.3f} ({r_opt['search_time_s']:.1f}s)")

    df_res = pd.DataFrame(results)
    print("\nOrtalama (tüm SKU):")
    print(df_res.groupby(["algo","method"])[["MAE","search_time_s"]].mean().round(3).to_string())
    df_res.to_csv("opt/results_grid_vs_optuna.csv", index=False)
    return df_res


# =====================================================================
# SENARYO 3: ÖLÇEK TESTİ (400 SKU simülasyonu)
# =====================================================================

def scenario_skala(panel, skus):
    print("\n" + "="*70)
    print("SENARYO 3: Ölçek Testi (21 SKU → 400 SKU tahmini)")
    print("="*70)

    # 1 SKU için süreyi ölç
    sku = skus[0]
    df  = panel[panel["sku"] == sku].copy()
    train, val, test, tv = split_data(df)
    X_tv   = tv[FEATURES].fillna(0)
    y_tv   = tv["y"]
    X_test = test[FEATURES].fillna(0)
    y_test = test["y"]

    rows = []
    for algo in ["RF", "XGB", "LightGBM"]:
        # Grid
        t0 = time.perf_counter()
        run_grid_search(algo, X_tv, y_tv, X_test, y_test)
        t_grid = time.perf_counter() - t0

        # Optuna
        t0 = time.perf_counter()
        run_optuna(algo, X_tv, y_tv, X_test, y_test)
        t_opt = time.perf_counter() - t0

        for method, t in [("Grid", t_grid), ("Optuna", t_opt)]:
            rows.append({
                "algo": algo, "method": method,
                "1_sku_s":   round(t, 2),
                "21_sku_s":  round(t * 21, 1),
                "21_sku_parallel_s": round(t * 21 / 6, 1),  # 6 çekirdek
                "400_sku_s": round(t * 400, 1),
                "400_sku_parallel_s": round(t * 400 / 6, 1),
            })

    df_res = pd.DataFrame(rows)
    print(df_res.to_string(index=False))
    df_res.to_csv("opt/results_skala.csv", index=False)
    return df_res


# =====================================================================
# SENARYO 4: RETRAINING SENARYOLARI
# =====================================================================

def scenario_retraining(panel, skus):
    print("\n" + "="*70)
    print("SENARYO 4: Retraining Senaryoları")
    print("="*70)

    results = []
    for sku in skus[:5]:  # ilk 5 SKU yeterli
        df = panel[panel["sku"] == sku].copy().sort_values("ds")

        # --- Senaryo A: Tam eğitim (mevcut) ---
        t0 = time.perf_counter()
        train, val, test, tv = split_data(df)
        X_tv   = tv[FEATURES].fillna(0); y_tv = tv["y"]
        X_test = test[FEATURES].fillna(0); y_test = test["y"]
        m = fit_xgb(X_tv, y_tv, {"n_estimators": 300, "learning_rate": 0.08,
                                  "max_depth": 3, "subsample": 0.9})
        mae_full, _ = mae_rmse(y_test, m.predict(X_test))
        t_full = round(time.perf_counter() - t0, 3)

        # --- Senaryo B: +5 ay ekleme (incremental simülasyonu) ---
        # 5 ay önceki kesim noktasından eğit, son 5 ayı "yeni veri" say
        cutoff_old = TEST_START - pd.DateOffset(months=5)
        t0 = time.perf_counter()
        df_old  = df[df["ds"] < cutoff_old]
        df_new5 = df[df["ds"] >= cutoff_old]
        d_combined = prep_features(pd.concat([df_old, df_new5]))
        tv_b   = d_combined[d_combined["ds"] < TEST_START]
        test_b = d_combined[(d_combined["ds"] >= TEST_START) & (d_combined["ds"] <= TEST_END)]
        if len(tv_b) < 10 or len(test_b) < 2:
            t_incr, mae_incr = 0, np.nan
        else:
            m_b = fit_xgb(tv_b[FEATURES].fillna(0), tv_b["y"],
                          {"n_estimators": 300, "learning_rate": 0.08,
                           "max_depth": 3, "subsample": 0.9})
            mae_incr, _ = mae_rmse(test_b["y"], m_b.predict(test_b[FEATURES].fillna(0)))
            t_incr = round(time.perf_counter() - t0, 3)

        # --- Senaryo C: Rolling (her ay 1 ay ileriye tahmin) ---
        t0 = time.perf_counter()
        test_months = pd.date_range(TEST_START, TEST_END, freq="MS")
        rolling_preds = []
        for month in test_months:
            df_roll = prep_features(df[df["ds"] < month])
            if len(df_roll) < 15:
                continue
            m_r = fit_xgb(df_roll[FEATURES].fillna(0), df_roll["y"],
                          {"n_estimators": 200, "learning_rate": 0.08,
                           "max_depth": 3, "subsample": 0.9})
            row = prep_features(df[df["ds"] == month])
            if len(row) == 0:
                continue
            yhat = m_r.predict(row[FEATURES].fillna(0))[0]
            ytrue = row["y"].values[0]
            rolling_preds.append({"ds": month, "yhat": yhat, "y": ytrue})
        t_roll = round(time.perf_counter() - t0, 3)
        if rolling_preds:
            rp = pd.DataFrame(rolling_preds)
            mae_roll, _ = mae_rmse(rp["y"], rp["yhat"])
        else:
            mae_roll = np.nan

        results.append({
            "sku": sku,
            "tam_egitim_MAE":  round(mae_full, 3),
            "tam_egitim_sure": t_full,
            "incremental_MAE": round(mae_incr, 3) if not np.isnan(mae_incr) else "-",
            "incremental_sure": t_incr,
            "rolling_MAE":     round(mae_roll, 3) if not np.isnan(mae_roll) else "-",
            "rolling_sure":    t_roll,
        })

        print(f"  {sku}")
        print(f"    Tam eğitim  → MAE={mae_full:.3f}  | {t_full:.2f}s")
        print(f"    +5 ay       → MAE={mae_incr:.3f}  | {t_incr:.2f}s")
        print(f"    Rolling     → MAE={mae_roll:.3f}  | {t_roll:.2f}s")

    df_res = pd.DataFrame(results)
    df_res.to_csv("opt/results_retraining.csv", index=False)
    return df_res


# =====================================================================
# ANA
# =====================================================================

def main():
    panel = pd.read_csv(PANEL_CSV, parse_dates=["ds"])
    panel["sku"] = panel["sku"].astype(str)
    skus = panel["sku"].unique().tolist()
    if SKU_FILTER:
        skus = [s for s in skus if s in SKU_FILTER]

    print(f"SKU sayısı: {len(skus)} | Optuna trials: {N_TRIALS}")

    all_results = {}

    if SCENARIOS["algoritma_karsilastirma"]:
        all_results["algoritma"] = scenario_algoritma(panel, skus)

    if SCENARIOS["grid_vs_optuna"]:
        all_results["grid_vs_optuna"] = scenario_grid_vs_optuna(panel, skus)

    if SCENARIOS["skala_testi"]:
        all_results["skala"] = scenario_skala(panel, skus)

    if SCENARIOS["retraining"]:
        all_results["retraining"] = scenario_retraining(panel, skus)

    print("\n" + "="*70)
    print("TAMAMLANDI — Sonuçlar opt/ klasörüne kaydedildi:")
    for k in all_results:
        print(f"  opt/results_{k}.csv")


if __name__ == "__main__":
    main()
