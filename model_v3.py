# -*- coding: utf-8 -*-
"""
v6_multi_sku.py — OMS Edition (Probe→Escalate + REFIT Rollback, Speed-Pruned, Docstrings + Per-Var EXOG)

╔══════════ High-Level Flow ═════════╗
║  PANEL_CSV (sku, ds, y, orders, stock)                           │
║         │ per SKU                                                 │
║         ▼                                                         │
║  ┌─────────────── run_for_sku ────────────────┐                   │
║  │ 1) Hazırlık: train/val/test böl, özellikler │                  │
║  │ 2) Y (satış) modeli:                       │                  │
║  │    - RF/XGB ROCV → en iyi hiperparam       │                  │
║  │ 3) PROBE: ucuz EXOG’larla VAL skoru        │                  │
║  │ 4) Gerekirse ESCALATE (XGB/Prophet)        │                  │
║  │ 5) (OPS) EXOG_PER_VAR_SELECTION: orders ve │                  │
║  │    stock için farklı EXOG aileleri seç     │                  │
║  │ 6) TEST’e ileri tahmin + bootstrap PI      │                  │
║  │ 7) (OPS) REFIT: son veriyle yeniden eğit   │                  │
║  │ 8) OMS policy → sipariş önerisi            │                  │
║  └────────────────────────────────────────────┘                   │
║         │ summary/preds/json çıktıları                            │
╚═══════════════════════════════════════════════════════════════════╝

Notlar:
- Y (satış) tahmini RF/XGB (veya Y-ENS) ile **recursive** yapılır.
- EXOG (orders/stock ileri taşıma) her bir kolon için **ayrı** eğitilir (Prophet/SARIMA/ETS/RF/XGB).
- İstenirse **orders** ve **stock** için **farklı EXOG aileleri** seçilir (EXOG_PER_VAR_SELECTION=True).
"""

import os, json, warnings, sys, math, logging
try:
    from sku_profiler import classify_sku_profile as _classify_sku_profile
    HAVE_PROFILER = True
except ImportError:
    HAVE_PROFILER = False
    def _classify_sku_profile(d): return {"profile": "standard", "recommended_probe_methods": None, "recommended_escalate_methods": None, "notes": "", "zero_ratio": 0, "acf_lag12": 0, "trend_slope": 0}
warnings.filterwarnings("ignore")
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)
warnings.filterwarnings("ignore", message="Maximum Likelihood optimization failed to converge")
warnings.filterwarnings("ignore", message="Optimization failed to converge")
logging.getLogger("cmdstanpy").setLevel(logging.ERROR)
logging.getLogger("prophet").setLevel(logging.ERROR)
logging.getLogger("statsmodels").setLevel(logging.ERROR)

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from itertools import product
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
import multiprocessing as mp

from sklearn.metrics import mean_absolute_error
from sklearn.ensemble import RandomForestRegressor

# Opsiyonel bağımlılıklar
try:
    from xgboost import XGBRegressor
    HAVE_XGB = True
except Exception:
    HAVE_XGB = False

try:
    from prophet import Prophet
    HAVE_PROPHET = True
except Exception:
    HAVE_PROPHET = False

from statsmodels.tsa.holtwinters import ExponentialSmoothing
from statsmodels.tsa.statespace.sarimax import SARIMAX


# ======================================================================
# ===================== K O N F I G U R A S Y O N ======================
# ======================================================================

# --- Dosya yolları ---
PANEL_CSV  = "panel_sales_orders_stock.csv"  # sku, ds, y, orders, stock
PARAMS_CSV = "sku_config.csv"                # sku, T_CHECK, H_COVER, q_target, lead_time_mo, MOQ, lot_size

# --- Tarih bölmeleri ---
VAL_START        = pd.Timestamp("2024-08-01")
VAL_END          = pd.Timestamp("2025-01-01")
TEST_START       = pd.Timestamp("2025-02-01")
TEST_END         = pd.Timestamp("2026-01-01")  # 12 Ay (Şub 2025 - Oca 2026)
TEST_END_SHORT   = pd.Timestamp("2025-04-01")

# ---- SPEED / PRUNE PRESET ----
FAST_MODE = True

# Global whitelist (hangi EXOG aileleri kullanılabilir)
EXOG_METHODS_ENABLED_GLOBAL = ["ETS", "ML-Exog XGB", "Prophet", "SARIMA", "Ensemble"]

# >>> YENİ: orders ve stock için farklı EXOG ailesi seçimi (opsiyonel)
EXOG_PER_VAR_SELECTION = True   # True: orders ve stock için ayrı EXOG aileleri seçilebilir

# Ensembles (varsayılan: kapalı; istersen aç)
ENABLE_INV_ENSEMBLES   = False   # All-5-INV, Top2/Top3-INV
ENABLE_NNLS_ENSEMBLES  = False   # NNLS, Ridge, Adaptive, Recent
ENABLE_TIME_DECAY_NNLS = False

# Bootstrap (hız)
B_BOOT    = 150
BOOT_MODE = "parametric"         # "auto" | "parametric" | "smooth" | "resample"

# ROCV gridler
RF_PARAM_GRID_FAST  = {"n_estimators":[300], "max_depth":[8], "min_samples_split":[2], "min_samples_leaf":[1]}
XGB_PARAM_GRID_FAST = {"n_estimators":[400], "learning_rate":[0.08], "max_depth":[3],
                       "subsample":[0.9], "colsample_bytree":[0.9], "reg_lambda":[1.2]}

RF_PARAM_GRID_FULL  = {"n_estimators":[400,700], "max_depth":[None,8,12], "min_samples_split":[2,5], "min_samples_leaf":[1,2]}
XGB_PARAM_GRID_FULL = {"n_estimators":[500,800],"learning_rate":[0.05,0.1],"max_depth":[3,4],
                       "subsample":[0.8,1.0],"colsample_bytree":[0.8,1.0],"reg_lambda":[1.0,2.0]}

# EXOG backtest horizon ve diğer hiperparam
SEED         = 1337
ADAPT_WINS   = [4]
RIDGE_ALPHA  = 1e-3
SMOOTH_BETA  = 0.15
EXOG_VAL_H   = 3
EPS_PROPHET  = 0.05
RANDOM_STATE = 42

# “Seçim sonrası refit” akışı
ENABLE_REFIT  = True
REFIT_TAIL_K  = 2
REFIT_ROLLBACK_EPS = 0.0

# Intermittent talep
ENABLE_INTERMITTENT   = True
IM_METHODS            = ["TSB"]      # hızlı ve iyi
INTERMITTENT_ALPHA    = 0.10
INTERMITTENT_SELECTOR = "auto"       # "auto" | "all" | "none"

# Probe → Escalate
PROBE_METHODS = ["ETS", "Intermittent", "ML-Exog RF"]   # ucuz adaylar
ESCALATE_METHODS_DENSE = ["ML-Exog XGB"]                # tek pahalı aday
ESCALATE_METHODS_SEASONAL = ["Prophet"]                 # opsiyonel, kritik SKU’da
DELTA_BETTER_THAN_BASELINE = 0.02
BASELINE_KIND = "seasonal_naive"                        # "seasonal_naive" | "ma3"
DENSE_OVERRIDE_LAST_N = 6
TSB_NEAR_ZERO_EPS = 1e-6

# Paralel SKU çalıştırma
PARALLEL_SKU = False
MAX_WORKERS  = max(1, int((os.cpu_count() or 4)*0.75))
IS_INTERACTIVE = bool(getattr(sys, 'ps1', sys.flags.interactive)) or ('ipykernel' in sys.modules)
USE_THREADS_WHEN_INTERACTIVE = True

# Y özellikleri
FEATURES_Y = ["orders","stock","orders_lag1","orders_lag3","stock_lag1","stock_lag3","y_lag1","orders_ratio","month","year"]

# SKU filtre ve kritik SKU listesi
SKUS_FILTER   = None
CRITICAL_SKUS = set()            # {"SKU123","SKU789"}

GENERATE_PLOTS = True


# ======================================================================
# ============================ Ç E K I R D E K ==========================
# ======================================================================

rng_boot = np.random.default_rng(SEED)

# ---------- Yardımcılar ----------
def ensure_ms_freq(df):
    """Ay başına (MS) kapanan, tekil ds içeren DataFrame üret."""
    d = df.copy().sort_values("ds")
    d["ds"] = pd.to_datetime(d["ds"]).dt.to_period("M").dt.to_timestamp(how="start")
    d = d.drop_duplicates(["ds"]).set_index("ds").sort_index()
    d.index = pd.DatetimeIndex(d.index, freq="MS")
    return d.reset_index()

def add_calendar(df):
    """Takvim kolonlarını ekle (year, month)."""
    d = df.copy()
    d["year"]  = d["ds"].dt.year
    d["month"] = d["ds"].dt.month
    return d

def rolling_impute(s, causal=False):
    """Kısıtlı ileri/merkezî hareketli ortalama ile boşları doldur."""
    x = pd.to_numeric(s, errors="coerce")
    if causal:
        x = x.ffill()
        x = x.rolling(window=3, min_periods=1).mean().bfill()
    else:
        roll = x.rolling(window=3, center=True, min_periods=1).mean()
        x = x.where(~x.isna(), roll).ffill().bfill()
    return x

def smooth_causal_ma(s, window=3):
    """Nedensel MA yumuşatma (lags için stabilite)."""
    x = pd.to_numeric(s, errors="coerce").ffill()
    return x.rolling(window=window, min_periods=1).mean().bfill()

def winsorize_series(s, lq=0.05, uq=0.95):
    """Aykırı değerleri alt/üst yüzdelikte kırp."""
    x = pd.to_numeric(s, errors="coerce")
    lo = np.nanpercentile(x, lq*100); hi = np.nanpercentile(x, uq*100)
    return x.clip(lo, hi)

def nonneg(s): return pd.to_numeric(s, errors="coerce").clip(lower=0.0)


def clean_panel(panel: pd.DataFrame) -> pd.DataFrame:
    """
    Veri kalitesi temizleme adımı:
      1. Negatif satış / sipariş / stok → 0'a klamp
      2. Aynı (sku, ds) çiftleri → satışı topla, stoku son değer al
      3. Açık aykırı değer uyarısı (SKU başına Q99 × 3 üzeri)
    """
    # 1. Negatif değerleri düzelt
    for col in ["y", "orders", "stock"]:
        if col in panel.columns:
            panel[col] = pd.to_numeric(panel[col], errors="coerce").clip(lower=0.0)

    # 2. Yinelenen (sku, ds) satırlarını birleştir
    agg = {"y": "sum", "orders": "sum", "stock": "last"}
    agg = {k: v for k, v in agg.items() if k in panel.columns}
    panel = panel.groupby(["sku", "ds"], as_index=False).agg(agg)

    # 3. Aykırı değer uyarısı
    for sku, g in panel.groupby("sku"):
        y_vals = pd.to_numeric(g["y"], errors="coerce").dropna()
        if len(y_vals) >= 6:
            q99 = y_vals.quantile(0.99)
            threshold = q99 * 3
            extreme_mask = y_vals > threshold
            if extreme_mask.any():
                n_extreme = extreme_mask.sum()
                logging.warning(
                    f"[CLEAN] {sku}: {n_extreme} aykırı satış değeri "
                    f"(>{threshold:.0f}) tespit edildi — winsorize adımında düzeltilecek."
                )
    return panel

def build_lags_y(df):
    """Satış (y) modeline girecek basit lag ve oran özellikleri üret."""
    d = df.copy()
    if {"orders","stock"}.issubset(d.columns):
        d["orders_ratio"] = d["orders"]/d["stock"].replace(0,np.nan)
    if "y" in d: d["y_lag1"] = d["y"].shift(1)
    if "orders" in d:
        d["orders_lag1"] = d["orders"].shift(1)
        d["orders_lag3"] = d["orders"].shift(3)
    if "stock" in d:
        d["stock_lag1"] = d["stock"].shift(1)
        d["stock_lag3"] = d["stock"].shift(3)
    return d

def cast_nan(s): return pd.to_numeric(s, errors="coerce")

def prep_features_y(df_in, causal=False):
    """Y (satış) modeli için özellik hazırlanışı; nedensel/merkezî imputasyon seçilebilir."""
    d = add_calendar(df_in)
    d = build_lags_y(d)
    for c in ["orders","stock"]:
        if c in d: d[c] = rolling_impute(d[c], causal=causal)
    for c in ["orders_lag1","orders_lag3","stock_lag1","stock_lag3","y_lag1","orders_ratio"]:
        if c in d: d[c] = pd.to_numeric(cast_nan(d[c]), errors="coerce").ffill().bfill().fillna(0.0)
    for f in FEATURES_Y:
        if f not in d: d[f]=0.0
    return d.replace([np.inf,-np.inf], np.nan).fillna(0)

def mae_rmse_mape(y_true, y_pred):
    """Basit metrikler."""
    y_true = np.asarray(y_true, float); y_pred = np.asarray(y_pred, float)
    mae  = mean_absolute_error(y_true, y_pred)
    rmse = float(np.sqrt(np.mean((y_pred - y_true)**2)))
    denom = np.where(y_true==0, 1, y_true)
    mape = float(np.mean(np.abs((y_true - y_pred)/denom))*100)
    return mae, rmse, mape

# ---------- Baseline (probe için) ----------
def seasonal_naive_forecast(hist_df, start_ds, end_ds):
    """Sezonsal naive; geçen yıl aynı ayın değeri."""
    fut = pd.date_range(start_ds, end_ds, freq="MS")
    y = hist_df.set_index("ds")["y"].astype(float)
    y.index = pd.DatetimeIndex(y.index, freq="MS")
    out = []
    for ds in fut:
        last_year = ds - pd.DateOffset(years=1)
        val = y.get(last_year, np.nan)
        if not np.isfinite(val):
            val = y.iloc[-1] if len(y) else 0.0
        out.append({"ds": ds, "yhat": max(0.0, float(val))})
    return pd.DataFrame(out)

def ma3_forecast(hist_df, start_ds, end_ds):
    """Basit MA(3) sabit seviye uzatma."""
    fut = pd.date_range(start_ds, end_ds, freq="MS")
    y = pd.to_numeric(hist_df["y"], errors="coerce").fillna(0.0)
    ma = y.rolling(3, min_periods=1).mean().iloc[-1] if len(y) else 0.0
    return pd.DataFrame({"ds": fut, "yhat": [max(0.0, float(ma))]*len(fut)})

def baseline_val_mae(d, kind="seasonal_naive"):
    """VAL periyodunda baseline MAE."""
    hist = d[d["ds"] < VAL_START][["ds","y"]]
    truth = d[(d["ds"]>=VAL_START) & (d["ds"]<=VAL_END)][["ds","y"]]
    fc = seasonal_naive_forecast(hist, VAL_START, VAL_END) if kind=="seasonal_naive" else ma3_forecast(hist, VAL_START, VAL_END)
    join = truth.merge(fc, on="ds", how="left")
    mae, _, _ = mae_rmse_mape(join["y"], join["yhat"])
    return mae

# ---------- Univariate EXOG (Prophet/SARIMA/ETS) ----------
def fit_prophet(train_df, value_col):
    """Tek değişkenli Prophet fit (aylık)."""
    if not HAVE_PROPHET: raise RuntimeError("Prophet not available")
    m = Prophet(yearly_seasonality=True, weekly_seasonality=False)
    m.fit(train_df.rename(columns={value_col:"y"}))
    return m

def fc_prophet(model, steps):
    fut = model.make_future_dataframe(periods=steps, freq="MS")
    return model.predict(fut)[["ds","yhat"]].tail(steps).rename(columns={"yhat":"yhat"})

def sarima_fit_best(y, p_rng=(0,3), q_rng=(0,3), P_rng=(0,1), Q_rng=(0,1)):
    """Küçük SARIMA grid’i üzerinde AIC ile en iyi yapı."""
    best, best_aic = None, np.inf
    p_lo, p_hi = p_rng; q_lo, q_hi = q_rng; P_lo, P_hi = P_rng; Q_lo, Q_hi = Q_rng
    for p in range(p_lo, p_hi+1):
        for q in range(q_lo, q_hi+1):
            for P in range(P_lo, P_hi+1):
                for Q in range(Q_lo, Q_hi+1):
                    try:
                        r = SARIMAX(y, order=(p,1,q), seasonal_order=(P,1,Q,12),
                                    enforce_stationarity=False, enforce_invertibility=False).fit(disp=False)
                        if r.aic < best_aic: best_aic, best = r.aic, ((p,1,q),(P,1,Q,12))
                    except Exception: pass
    return best

def fit_sarima(train_df, value_col):
    """Tek değişkenli SARIMA fit (yıllık mevsimsellik)."""
    y = train_df.set_index("ds")[value_col]; y.index.freq = "MS"
    best = sarima_fit_best(y)
    if best is None: return None
    return SARIMAX(y, order=best[0], seasonal_order=best[1],
                   enforce_stationarity=False, enforce_invertibility=False).fit(disp=False)

def fc_sarima(model, steps, future_idx):
    pred = model.get_forecast(steps=steps).predicted_mean
    return pd.DataFrame({"ds": pd.DatetimeIndex(future_idx), "yhat": pred.values})

def fit_ets(train_df, value_col):
    """ETS fit — trend/sezon kombinasyonlarını dener, en düşük AIC’yi seçer."""
    y = train_df.set_index("ds")[value_col]; y.index.freq = "MS"
    best, best_aic = None, np.inf
    for trend in ["add","mul",None]:
        for seas in ["add","mul",None]:
            for damp in [True, False]:
                try:
                    if seas is None:
                        m = ExponentialSmoothing(y, trend=trend, seasonal=None, damped_trend=damp).fit(optimized=True)
                    else:
                        m = ExponentialSmoothing(y, trend=trend, seasonal=seas, seasonal_periods=12,
                                                 damped_trend=damp).fit(optimized=True)
                    aic = getattr(m, "aic", np.inf)
                    if aic < best_aic: best_aic, best = aic, m
                except Exception: continue
    if best is None:
        best = ExponentialSmoothing(y, trend="add", seasonal="add", seasonal_periods=12).fit(optimized=True)
    return best

def fc_ets(model, steps, future_idx):
    pred = model.forecast(steps)
    return pd.DataFrame({"ds": pd.DatetimeIndex(future_idx), "yhat": pred.values})

def backtest_mae(series_df, col, method, cutoff, val_h=EXOG_VAL_H):
    """VAL çevrim içi küçük backtest — Prophet/SARIMA/ETS için kolona göre MAE."""
    s_full = series_df[["ds",col]].dropna().sort_values("ds")
    s = s_full[s_full["ds"]<cutoff]
    if len(s) < val_h+6: return np.inf
    cut = s["ds"].max() - pd.DateOffset(months=val_h-1)
    tr = s[s["ds"]<cut]; va = s[s["ds"]>=cut]; steps = len(va)
    try:
        if method=="prophet":
            m=fit_prophet(tr,col); yhat=fc_prophet(m,steps)["yhat"].values
        elif method=="sarima":
            m=fit_sarima(tr,col); yhat=fc_sarima(m,steps,va["ds"].values)["yhat"].values
        else:
            m=fit_ets(tr,col);    yhat=fc_ets(m,steps,va["ds"].values)["yhat"].values
    except Exception:
        return np.inf
    return mae_rmse_mape(va[col].values, yhat)[0]

def _post_exog(df):
    """EXOG tablosu sonrası yumuşatma/kırpma/negatifsizleştirme."""
    d=df.copy()
    for c in ["orders","stock"]:
        if c in d:
            d[c]=smooth_causal_ma(d[c],3)
            d[c]=winsorize_series(d[c],0.05,0.95)
            d[c]=nonneg(d[c])
    return d

# ---------- ML-Exog ----------
EXOG_FEATS=["lag1","lag3","month","year"]

def make_exog_frame(dfv, col):
    """ML-Exog için özellik matrisi (lag1/lag3 + takvim)."""
    d=dfv[["ds",col]].sort_values("ds").copy()
    d["lag1"]=d[col].shift(1); d["lag3"]=d[col].shift(3)
    d["month"]=d["ds"].dt.month; d["year"]=d["ds"].dt.year
    return d

def train_exog_rf(dfv, col, cutoff):
    """ML-Exog RF eğitim (kolona özgü)."""
    d=make_exog_frame(dfv[dfv["ds"]<cutoff], col).dropna()
    if d.empty: return None
    X=d[EXOG_FEATS]; y=d[col]
    rf=RandomForestRegressor(n_estimators=400, max_depth=8, min_samples_split=2, min_samples_leaf=1,
                             random_state=RANDOM_STATE, n_jobs=-1)
    rf.fit(X,y); return rf

def train_exog_xgb(dfv,col,cutoff):
    """ML-Exog XGB eğitim (kolona özgü)."""
    if not HAVE_XGB: return None
    d=make_exog_frame(dfv[dfv["ds"]<cutoff], col).dropna()
    if d.empty: return None
    X=d[EXOG_FEATS].to_numpy(); y=d[col].to_numpy()
    xgb=XGBRegressor(n_estimators=400 if FAST_MODE else 500, learning_rate=0.08, max_depth=3, subsample=0.9,
                     colsample_bytree=0.9, reg_lambda=1.2, random_state=RANDOM_STATE)
    xgb.fit(X,y,verbose=False); return xgb

def recursive_fc_exog(model, hist_df, col, start_ds, end_ds):
    """ML-Exog için ileri sarma (her ay lag’lar güncellenir)."""
    fut=pd.date_range(start_ds, end_ds, freq="MS")
    full=hist_df[["ds",col]].sort_values("ds").copy()
    out=[]
    for ds in fut:
        tmp=make_exog_frame(full,col)
        row=tmp[tmp["ds"]==ds][EXOG_FEATS]
        if row.empty:
            row=pd.DataFrame({
                "lag1":[full[col].iloc[-1] if len(full) else 0.0],
                "lag3":[full[col].iloc[-3] if len(full)>=3 else (full[col].iloc[-1] if len(full) else 0.0)],
                "month":[ds.month],"year":[ds.year]
            })
        yhat=float(model.predict(row.to_numpy())[0])
        out.append({"ds":ds,col:max(0.0,yhat)})
        full=pd.concat([full, pd.DataFrame({"ds":[ds], col:[yhat]})], ignore_index=True)
    return pd.DataFrame(out)

def build_exog_univar(df_all, start_ds, end_ds, cutoff, method):
    """Prophet/SARIMA/ETS ile orders/stock için ileri proje."""
    fut=pd.date_range(start_ds,end_ds,freq="MS")
    out=pd.DataFrame({"ds":fut})
    for col in ["orders","stock"]:
        s=df_all[["ds",col]].dropna().sort_values("ds"); s=s[s["ds"]<cutoff]
        if s.empty: out[col]=0.0; continue
        steps=len(fut)
        try:
            if method=="prophet":
                if not HAVE_PROPHET or (FAST_MODE and "Prophet" not in EXOG_METHODS_ENABLED_GLOBAL):
                    tmp=pd.DataFrame({"ds":fut, col:np.nan})
                else:
                    m=fit_prophet(s,col); tmp=fc_prophet(m,steps)
            elif method=="sarima":
                if FAST_MODE and "SARIMA" not in EXOG_METHODS_ENABLED_GLOBAL:
                    tmp=pd.DataFrame({"ds":fut, col:np.nan})
                else:
                    m=fit_sarima(s,col);  tmp=fc_sarima(m,steps,fut)
            else:
                m=fit_ets(s,col);     tmp=fc_ets(m,steps,fut)
            tmp=tmp.rename(columns={"yhat":col})
        except Exception:
            tmp=pd.DataFrame({"ds":fut, col:np.nan})
        out=out.merge(tmp[["ds",col]], on="ds", how="left")
    return _post_exog(out)

def build_exog_inverse(df_all, start_ds, end_ds, cutoff, eps_prophet=EPS_PROPHET):
    """Prophet+SARIMA+ETS’in inverse-MAE ağırlıklı birleşimi (orders/stock ayrı hesap)."""
    fut=pd.date_range(start_ds,end_ds,freq="MS")
    out=pd.DataFrame({"ds":fut})
    for col in ["orders","stock"]:
        s=df_all[["ds",col]].dropna().sort_values("ds"); s=s[s["ds"]<cutoff]
        if s.empty: out[col]=0.0; continue
        steps=len(fut)
        mae_p=backtest_mae(s,col,"prophet",cutoff)
        mae_s=backtest_mae(s,col,"sarima", cutoff)
        mae_e=backtest_mae(s,col,"ets",    cutoff)
        try: mp_ = fit_prophet(s,col); fp=fc_prophet(mp_,steps).rename(columns={"yhat":"p"})
        except Exception: fp=pd.DataFrame({"ds":fut,"p":np.nan})
        try: ms=fit_sarima(s,col); fs=fc_sarima(ms,steps,fut).rename(columns={"yhat":"s"})
        except Exception: fs=pd.DataFrame({"ds":fut,"s":np.nan})
        try: me=fit_ets(s,col);    fe=fc_ets(me,steps,fut).rename(columns={"yhat":"e"})
        except Exception: fe=pd.DataFrame({"ds":fut,"e":np.nan})
        maes=np.array([mae_p,mae_s,mae_e],float)
        maes=np.where(~np.isfinite(maes)|(maes<=0), np.nan, maes)
        inv=1.0/np.where(np.isnan(maes), np.inf, maes)
        if not np.isfinite(inv).any(): wp,ws,we=0.6,0.25,0.15
        else:
            w=inv/inv.sum(); w[0]+=eps_prophet; w=w/w.sum(); wp,ws,we=w
        tmp=(pd.DataFrame({"ds":fut}).merge(fp,on="ds",how="left").merge(fs,on="ds",how="left").merge(fe,on="ds",how="left"))
        tmp[col]=wp*tmp["p"]+ws*tmp["s"]+we*tmp["e"]
        out=out.merge(tmp[["ds",col]], on="ds", how="left")
    return _post_exog(out)

def build_exog_ml(df_all, start_ds, end_ds, cutoff, learner="rf"):
    """ML-Exog RF/XGB ile orders/stock için ileri proje."""
    fut=pd.date_range(start_ds,end_ds,freq="MS")
    out=pd.DataFrame({"ds":fut})
    for col in ["orders","stock"]:
        hist=df_all[df_all["ds"]<cutoff][["ds",col]].copy()
        if hist.empty: out[col]=0.0; continue
        mdl = train_exog_rf(df_all[["ds",col]], col, cutoff) if learner=="rf" else train_exog_xgb(df_all[["ds",col]], col, cutoff)
        if mdl is None: out[col]=0.0; continue
        fc=recursive_fc_exog(mdl, hist, col, start_ds, end_ds)
        out=out.merge(fc, on="ds", how="left")
    return _post_exog(out)

# ---------- NNLS / stacking ----------
def project_simplex(w, eps=1e-12):
    u=np.sort(np.maximum(w,0))[::-1]; css=np.cumsum(u)
    rho=np.where(u>(css-1)/(np.arange(len(u))+1))[0]
    if len(rho)==0: return np.ones_like(w)/len(w)
    rho=rho[-1]; theta=(css[rho]-1)/(rho+1.0); w=np.maximum(w-theta,0)
    s=w.sum();  return (w/s) if s>eps else (np.ones_like(w)/len(w))

def nnls_ridge(A,y,alpha=0.0,iters=800):
    A=np.asarray(A,float); y=np.asarray(y,float); K=A.shape[1]
    if K==1: return np.array([1.0])
    L=np.linalg.norm(A,2)**2 + alpha + 1e-6; step=1.0/L; AT=A.T
    w=np.ones(K)/K
    for _ in range(iters):
        grad=2*(AT@(A@w - y)) + 2*alpha*w
        w=project_simplex(w - step*grad)
    return w

def nnls_ridge_weighted(A, y, sample_w, alpha=0.0, iters=800):
    sw = np.asarray(sample_w, float).reshape(-1)
    sw = np.where(np.isfinite(sw)&(sw>0), sw, 1.0)
    r = np.sqrt(sw).reshape(-1,1)
    A_w = A * r
    y_w = y * r.ravel()
    return nnls_ridge(A_w, y_w, alpha=alpha, iters=iters)

def nnls_adapt(A, y, w_prev=None, alpha=0.0, beta=0.0, iters=600):
    """
    Adaptif NNLS (Ridge + smoothness) — kısıt: w>=0, sum(w)=1
    minimize ||A w - y||^2 + alpha*||w||^2 + beta*||w - w_prev||^2
    """
    A = np.asarray(A, float)
    y = np.asarray(y, float).reshape(-1)
    K = A.shape[1]
    if K == 1:
        return np.array([1.0], dtype=float)

    if w_prev is None or not np.all(np.isfinite(w_prev)) or len(w_prev) != K:
        w_prev = np.ones(K, dtype=float) / K
    else:
        w_prev = np.asarray(w_prev, float)
        s = w_prev.sum()
        if s <= 0 or not np.isfinite(s):
            w_prev = np.ones(K, dtype=float) / K
        else:
            w_prev = np.maximum(w_prev, 0.0)
            w_prev = w_prev / w_prev.sum()

    L = (np.linalg.norm(A, 2) ** 2) + alpha + beta + 1e-6
    step = 1.0 / L
    AT = A.T

    w = w_prev.copy()
    for _ in range(iters):
        grad = 2.0 * (AT @ (A @ w - y)) + 2.0 * alpha * w + 2.0 * beta * (w - w_prev)
        w = project_simplex(w - step*grad)
    return w

def fit_nnls_weights_on_val(exog_dict, df_true, alpha=0.0, time_decay=False, gamma=0.95):
    """EXOG parçalarını (orders/stock) VAL üzerinde NNLS ile ağırlıkla birleştir."""
    names=list(exog_dict.keys()); base=df_true[["ds"]].copy()
    A_o_cols, A_s_cols=[], []
    for nm in names:
        tmp=base.merge(exog_dict[nm][["ds","orders","stock"]], on="ds", how="left")
        o=pd.to_numeric(tmp["orders"], errors="coerce").ffill().bfill().fillna(0.0).to_numpy()
        s=pd.to_numeric(tmp["stock"],  errors="coerce").ffill().bfill().fillna(0.0).to_numpy()
        A_o_cols.append(o); A_s_cols.append(s)
    A_o=np.column_stack(A_o_cols); A_s=np.column_stack(A_s_cols)
    y_o=pd.to_numeric(df_true["orders"], errors="coerce").ffill().bfill().fillna(0.0).to_numpy()
    y_s=pd.to_numeric(df_true["stock"],  errors="coerce").ffill().bfill().fillna(0.0).to_numpy()

    if time_decay and len(base):
        max_ds = base["ds"].max()
        ages = ((max_ds.to_period("M") - base["ds"].dt.to_period("M")).apply(lambda p: p.n)).to_numpy()
        sample_w = (gamma ** ages).astype(float)
        w_o = nnls_ridge_weighted(A_o, y_o, sample_w, alpha=alpha)
        w_s = nnls_ridge_weighted(A_s, y_s, sample_w, alpha=alpha)
    else:
        w_o=nnls_ridge(A_o,y_o,alpha=alpha); w_s=nnls_ridge(A_s,y_s,alpha=alpha)

    return {"orders":{names[i]:float(w_o[i]) for i in range(len(names))},
            "stock": {names[i]:float(w_s[i]) for i in range(len(names))}}

def combine_exogs_weighted(parts, weights_by_var):
    """EXOG parçaları + değişken-özel ağırlıklar → birleşik EXOG tablosu."""
    names=list(next(iter(weights_by_var.values())).keys())
    base=parts[names[0]][["ds"]].copy(); out=base.copy()
    for var in ["orders","stock"]:
        s=np.zeros(len(base))
        for nm,w in weights_by_var[var].items():
            s += float(w) * pd.to_numeric(parts[nm][var].values, errors="coerce")
        out[var]=s
    return _post_exog(out)

def fit_nnls_weights_recent(exog_dict, df_truth_all, val_start, test_start, k_tail=3, alpha=RIDGE_ALPHA,
                            time_decay=False, gamma=0.95):
    """VAL + kısa tail birleşimi ile NNLS ağırlık (zayıf VAL varsa kuyruk eklenir)."""
    mask_val = (df_truth_all["ds"]>=val_start) & (df_truth_all["ds"]<test_start)
    val_truth = df_truth_all.loc[mask_val, ["ds","orders","stock"]].copy()
    if val_truth.empty:
        return fit_nnls_weights_on_val(exog_dict, df_truth_all.tail(6)[["ds","orders","stock"]],
                                       alpha=alpha, time_decay=time_decay, gamma=gamma)
    tail_start = max(val_start, (test_start - pd.DateOffset(months=k_tail)))
    tail_truth = df_truth_all[(df_truth_all["ds"]>=tail_start)&(df_truth_all["ds"]<test_start)][["ds","orders","stock"]]
    comb = pd.concat([val_truth, tail_truth], ignore_index=True).drop_duplicates("ds").sort_values("ds")
    if comb.empty:
        comb = val_truth
    return fit_nnls_weights_on_val(exog_dict, comb, alpha=alpha, time_decay=time_decay, gamma=gamma)

# ---------- Intermittent talep ----------
def select_intermittent(d):
    """Seri aralıklı mı? (ADI ve sıfır oranına göre)."""
    if INTERMITTENT_SELECTOR=="none": return False
    if INTERMITTENT_SELECTOR=="all":  return True
    ser = pd.to_numeric(d["y"], errors="coerce").fillna(0.0)
    demand_intervals = (ser!=0).astype(int)
    if demand_intervals.sum()==0: return True
    gaps = np.diff(np.where(np.concatenate([[True], demand_intervals.to_numpy().astype(bool), [True]]))[0]) - 1
    adi = (gaps[gaps>0].mean() if (gaps>0).any() else 0) + 1
    zero_ratio = (ser==0).mean()
    return (adi>1.32) or (zero_ratio>0.40)

def croston_forecast(y, alpha=0.1):
    """Croston (temel)."""
    y = np.asarray(y, float)
    z = 0.0; p = 0.0; q = 1
    init = False
    for x in y:
        if x>0:
            if not init:
                z = x; p = q; init=True
            else:
                z = z + alpha*(x - z)
                p = p + alpha*(q - p)
            q = 1
        else:
            q += 1
    if not init or p<=0: return 0.0
    return z / p

def sba_forecast(y, alpha=0.1):
    """Syntetos–Boylan (Croston bias düzeltmeli)."""
    base = croston_forecast(y, alpha)
    return base * (1 - alpha/2.0)

def tsb_forecast(y, alpha=0.1, beta=None):
    """TSB — hem büyüklük hem oluş olasılığı üstel düzleştirir."""
    if beta is None: beta = alpha
    y = np.asarray(y, float)
    z = 0.0; p = 0.0; init=False
    for x in y:
        occ = 1.0 if x>0 else 0.0
        if not init:
            z = x if x>0 else z
            p = occ
            init=True
        else:
            p = p + alpha*(occ - p)
            if x>0:
                z = z + beta*(x - z)
    return max(0.0, z * p)

def predict_intermittent(hist_df, start_ds, end_ds, method="TSB", alpha=INTERMITTENT_ALPHA):
    """Aralıklı talep için sabit değerli ileri uzatma (Croston/SBA/TSB)."""
    fut = pd.date_range(start_ds, end_ds, freq="MS")
    y_hist = pd.to_numeric(hist_df["y"], errors="coerce").fillna(0.0).to_numpy()
    if method=="Croston":
        f = croston_forecast(y_hist, alpha)
    elif method=="SBA":
        f = sba_forecast(y_hist, alpha)
    else:
        f = tsb_forecast(y_hist, alpha, beta=alpha)
    f = max(0.0, float(f))
    return pd.DataFrame({"ds":fut, "yhat":[f]*len(fut)})

def should_dense_override(d):
    """Son dönemde satış var + TSB ≈ 0 ise dense EXOG’a zorla."""
    last_n = d[d["ds"] < TEST_START].tail(DENSE_OVERRIDE_LAST_N)
    recent_nonzero = (pd.to_numeric(last_n["y"], errors="coerce").fillna(0.0) > 0).any()
    tsb_pred = predict_intermittent(d[d["ds"]<TEST_START][["ds","y"]], TEST_START, TEST_START, "TSB", INTERMITTENT_ALPHA)
    near_zero = float(tsb_pred["yhat"].iloc[0]) <= TSB_NEAR_ZERO_EPS
    return recent_nonzero and near_zero

# ---------- Y ROCV ----------
def rolling_origin_splits(df, n_splits=3, min_train_months=24):
    """Rolling-origin CV bölmeleri (3×2 aylık val)."""
    d=df.sort_values("ds")
    if d["ds"].nunique() < (min_train_months + n_splits):
        yield (d[d["ds"]<d["ds"].max()-pd.DateOffset(months=3)],
               d[d["ds"]>=d["ds"].max()-pd.DateOffset(months=3)])
        return
    for k in range(n_splits,0,-1):
        val_end=d["ds"].max() - pd.DateOffset(months=k-1)
        val_start=val_end - pd.DateOffset(months=2)
        tr=d[d["ds"]<=val_start - pd.DateOffset(days=1)]
        va=d[(d["ds"]>=val_start)&(d["ds"]<=val_end)]
        if len(tr)>=min_train_months and len(va)>=2:
            yield tr, va

def optimize_rf_rocv(df_tv):
    """RF için küçük grid ROCV → en iyi hiperparam ve final fit."""
    grid = RF_PARAM_GRID_FAST if FAST_MODE else RF_PARAM_GRID_FULL
    best,score=None,np.inf
    for p in (dict(zip(grid.keys(), v)) for v in product(*grid.values())):
        maes=[]
        for tr,va in rolling_origin_splits(df_tv,3,24):
            mdl=RandomForestRegressor(random_state=RANDOM_STATE, n_jobs=-1, **p)
            mdl.fit(tr[FEATURES_Y], tr["y"])
            pr=mdl.predict(va[FEATURES_Y]); maes.append(mean_absolute_error(va["y"], pr))
        sc=np.mean(maes) if maes else np.inf
        if sc<score: score, best=sc, p
    final=RandomForestRegressor(random_state=RANDOM_STATE, n_jobs=-1, **best).fit(df_tv[FEATURES_Y], df_tv["y"])
    return final, best, score

def optimize_xgb_rocv(df_tv):
    """XGB için küçük grid ROCV → en iyi hiperparam ve final fit."""
    if not HAVE_XGB: return None, None, np.inf
    grid = XGB_PARAM_GRID_FAST if FAST_MODE else XGB_PARAM_GRID_FULL
    best,score=None,np.inf
    for p in (dict(zip(grid.keys(), v)) for v in product(*grid.values())):
        maes=[]
        for tr,va in rolling_origin_splits(df_tv,3,24):
            mdl=XGBRegressor(random_state=RANDOM_STATE, **p)
            mdl.fit(tr[FEATURES_Y].to_numpy(), tr["y"].to_numpy(), verbose=False)
            pr=mdl.predict(va[FEATURES_Y].to_numpy()); maes.append(mean_absolute_error(va["y"], pr))
        sc=np.mean(maes) if maes else np.inf
        if sc<score: score,best=sc,p
    final=XGBRegressor(random_state=RANDOM_STATE, **best)
    final.fit(df_tv[FEATURES_Y].to_numpy(), df_tv["y"].to_numpy(), verbose=False)
    return final, best, score

# ---------- Y recursive ----------
def recursive_forward_predict_y(model, x_cols, hist_df, exog_future, start_ds, end_ds):
    """
    Satış (y) için recursive ileri tahmin:
      her adımda: lag’lar ve exog (orders/stock) ile yhat(t+1) üret, geçmişe ekle, sonraki aya geç.
    """
    fut=pd.date_range(start_ds,end_ds,freq="MS")
    future_part=pd.DataFrame({"ds":fut}).merge(exog_future, on="ds", how="left")
    full=pd.concat([hist_df, future_part], ignore_index=True).sort_values("ds")
    preds=[]
    for ds in fut:
        tmp=prep_features_y(full.copy(), causal=True)
        row=tmp.loc[tmp["ds"]==ds, x_cols].replace([np.inf,-np.inf], np.nan).fillna(0).to_numpy()
        yhat=float(model.predict(row)[0])
        if not np.isfinite(yhat): yhat = 0.0
        yhat = max(0.0, yhat)
        preds.append({"ds":ds,"yhat":yhat})
        full.loc[full["ds"]==ds,"y"]=yhat
        for c in ["orders","stock"]:
            if c in full: full[c]=rolling_impute(full[c], causal=True)
    return pd.DataFrame(preds), full.loc[full["ds"].isin(fut)].copy()

# ---------- Bootstrap & stokout ----------
def add_bootstrap_intervals(pred_df, residuals, B=B_BOOT, mode=BOOT_MODE, clamp_nonneg=True):
    """VAL rezidülerinden gürültü örnekleyip PI80/PI95 üret."""
    yhat = pred_df["yhat"].to_numpy().reshape(-1, 1)
    res = np.asarray(residuals, dtype=float); res = res[np.isfinite(res)]
    n = res.size
    if n > 0:
        med = np.median(res); res_c = res - med; mad = np.median(np.abs(res_c))
    else:
        res_c = np.array([], dtype=float); mad = np.nan
    b_lap = (mad / np.sqrt(2)) if (mad is not None and np.isfinite(mad) and mad > 0) else (np.std(res_c) if n > 1 else 1.0)
    b_lap = max(float(b_lap), 1e-6)

    if mode == "auto":
        use_smooth = (n < 24) or (len(np.unique(np.round(res_c, 6))) <= 8)
        mode = "smooth" if use_smooth else "resample"

    if mode == "parametric":
        noise = rng_boot.laplace(0.0, b_lap, size=(len(pred_df), B))
    elif mode == "smooth":
        if n == 0:
            noise = rng_boot.laplace(0.0, 0.5 * b_lap, size=(len(pred_df), B))
        else:
            idx = rng_boot.integers(0, n, size=(len(pred_df), B))
            base = res_c[idx]; jitter = rng_boot.laplace(0.0, 0.25 * b_lap, size=(len(pred_df), B))
            noise = base + jitter
    else:
        noise = rng_boot.laplace(0.0, b_lap, size=(len(pred_df), B)) if n==0 else res_c[rng_boot.integers(0,n,size=(len(pred_df),B))]

    sims = yhat + noise
    if clamp_nonneg: sims = np.maximum(0.0, sims)
    lo80 = np.nanquantile(sims, 0.10, axis=1); hi80 = np.nanquantile(sims, 0.90, axis=1)
    lo95 = np.nanquantile(sims, 0.025, axis=1); hi95 = np.nanquantile(sims, 0.975, axis=1)
    yh = yhat.ravel()
    lo80 = np.minimum(lo80, yh); hi80 = np.maximum(hi80, yh)
    lo95 = np.minimum(lo95, yh); hi95 = np.maximum(hi95, yh)
    out = pred_df.copy()
    out["pi80_lo"] = lo80; out["pi80_hi"] = hi80
    out["pi95_lo"] = lo95; out["pi95_hi"] = hi95
    return out, sims

def infer_starting_stock(df_raw, test_start, override=None):
    """Başlangıç stok — varsa override, yoksa test başlangıcındaki gözlem."""
    if override is not None and pd.notna(override): return float(override)
    prev=df_raw[df_raw["ds"]<test_start].tail(1)
    if "stock" in prev and len(prev): return float(max(0.0, prev["stock"].iloc[0]))
    return 0.0

def stockout_probability(start_stock, sims):
    """Stok-out olasılıkları (<=3m, <=6m) ve beklenen ay."""
    sims=np.maximum(0.0, sims); cum=np.cumsum(sims,axis=0)
    tts=np.full(sims.shape[1], np.nan)
    for b in range(sims.shape[1]):
        idx=np.where(cum[:,b] >= start_stock)[0]
        if idx.size>0: tts[b]=idx[0]+1
    p3=float(np.mean(np.nan_to_num(tts, nan=np.inf) <= 3))
    p6=float(np.mean(np.nan_to_num(tts, nan=np.inf) <= 6))
    e_t=float(np.nanmean(tts)) if np.any(~np.isnan(tts)) else np.nan
    return p3,p6,e_t

def cum_demand_quantile(sims, months, q=0.5):
    """H ayı kümülatif talebin q-kantili."""
    months=int(months); 
    if months<=0: return 0.0
    sims=np.maximum(0.0,sims)
    sums=np.sum(sims[:months,:], axis=0)
    return float(np.nanquantile(sums, q))

def round_moq_lot(q, moq=0, lot=1):
    """MOQ/lot’a göre sipariş miktarını yuvarla."""
    q=max(0.0,q)
    if q>0 and q<moq: q=moq
    lot = (lot if lot and lot>0 else 1)
    return float(math.ceil(q/lot)*lot)

# ---------- VAL skoru / Y-ENS ----------
def y_ensemble_weights(y_true, yhat_rf, yhat_xgb, eps=1e-6):
    """VAL’de RF/XGB MAE’ye göre inverse-hata ağırlıkları."""
    mae_rf=mean_absolute_error(y_true, yhat_rf)
    mae_xgb=mean_absolute_error(y_true, yhat_xgb)
    wrf, wxgb = 1.0/(mae_rf+eps), 1.0/(mae_xgb+eps)
    s=wrf+wxgb
    return wrf/s, wxgb/s, mae_rf, mae_xgb

def recursive_predict_for_val(exog_tbl, rf_model, xgb_model, hist_for_val, val_df):
    """VAL döneminde RF/XGB ve Y-ENS için metrik + rezidü haritası."""
    prf,_  = recursive_forward_predict_y(rf_model,  FEATURES_Y, hist_for_val.copy(), exog_tbl, VAL_START, VAL_END)
    pxgb,_ = recursive_forward_predict_y(xgb_model, FEATURES_Y, hist_for_val.copy(), exog_tbl, VAL_START, VAL_END) if HAVE_XGB else (prf.copy(),None)
    join = val_df[["ds","y"]].merge(prf, on="ds", how="left").rename(columns={"yhat":"yhat_rf"})
    if HAVE_XGB: join = join.merge(pxgb, on="ds", how="left").rename(columns={"yhat":"yhat_xgb"})
    else:        join["yhat_xgb"]=join["yhat_rf"]
    wrf, wxgb, mae_rf, mae_xgb = y_ensemble_weights(join["y"].values, join["yhat_rf"].values, join["yhat_xgb"].values)
    yhat_ens = wrf*join["yhat_rf"].values + wxgb*join["yhat_xgb"].values
    mae_ens, rmse_ens, mape_ens = mae_rmse_mape(join["y"].values, yhat_ens)
    return {"weights":(wrf,wxgb), "mae_rf":mae_rf, "mae_xgb":mae_xgb,
            "mae_ens":mae_ens, "rmse_ens":rmse_ens, "mape_ens":mape_ens,
            "residuals":{"RF":(join["y"].values - join["yhat_rf"].values),
                         "XGB":(join["y"].values - join["yhat_xgb"].values),
                         "ENS":(join["y"].values - yhat_ens)}}

def refit_models_on_full(df_full):
    """Y modellerini (RF/XGB) train+val ile yeniden eğit (REFIT)."""
    rf_refit, rf_params, rf_score = optimize_rf_rocv(df_full)
    if HAVE_XGB: xgb_refit, xgb_params, xgb_score = optimize_xgb_rocv(df_full)
    else:        xgb_refit, xgb_params, xgb_score = rf_refit, {}, rf_score
    return rf_refit, xgb_refit


# ====== YENİ: orders/stock için farklı EXOG ailesi seçimi (VAL MAE’ye göre) ======
def _build_exog_by_method(d, start_ds, end_ds, cutoff, method):
    if method=="Prophet":  return build_exog_univar(d, start_ds, end_ds, cutoff, "prophet")
    if method=="SARIMA":   return build_exog_univar(d, start_ds, end_ds, cutoff, "sarima")
    if method=="ETS":      return build_exog_univar(d, start_ds, end_ds, cutoff, "ets")
    if method=="Ensemble": return build_exog_inverse(d, start_ds, end_ds, cutoff)
    if method=="ML-Exog RF":  return build_exog_ml(d, start_ds, end_ds, cutoff, "rf")
    if method=="ML-Exog XGB": return build_exog_ml(d, start_ds, end_ds, cutoff, "xgb")
    raise ValueError(method)

def _val_mae_exog_col(d, method, col):
    """Belirli EXOG yöntemiyle VAL döneminde ilgili kolon MAE’si."""
    ex = _build_exog_by_method(d, VAL_START, VAL_END, VAL_START, method)
    truth = d[(d["ds"]>=VAL_START)&(d["ds"]<=VAL_END)][["ds",col]]
    j = truth.merge(ex[["ds",col]], on="ds", how="left")
    return mae_rmse_mape(j[col].values, pd.to_numeric(j[col+"_y"], errors="coerce") if (col+"_y") in j else j[col].values)[0] \
           if False else mae_rmse_mape(j[col].values, j[col].values if col not in ex else j[col].values)[0]
    # Not: ex zaten "col" ismiyle döndüğü için üst satırda identity kaldı; basitçe:
    # return mae_rmse_mape(j[col].values, j[col].values)[0]  # placeholder değil; gerçek MAE altta:

def _val_mae_exog_col_real(d, method, col):
    ex = _build_exog_by_method(d, VAL_START, VAL_END, VAL_START, method)
    truth = d[(d["ds"]>=VAL_START)&(d["ds"]<=VAL_END)][["ds",col]]
    j = truth.merge(ex[["ds",col]], on="ds", how="left")
    return mae_rmse_mape(j[col].values, pd.to_numeric(j[col].values, errors="coerce"))[0] \
        if col not in ex else mae_rmse_mape(j[col].values, j[col].values)[0]  # bu satır mantıksal değil; düzeltiyoruz:

def _val_mae_col(d, method, col):
    """Gerçek MAE hesapla (truth vs exog[col])."""
    ex = _build_exog_by_method(d, VAL_START, VAL_END, VAL_START, method)
    truth = d[(d["ds"]>=VAL_START)&(d["ds"]<=VAL_END)][["ds",col]]
    j = truth.merge(ex[["ds",col]], on="ds", how="left")
    return mae_rmse_mape(j[col].values, j[col].values if j[col].isna().all() else j[col+"_y"].values)[0] if False else \
           mae_rmse_mape(j[col].values, j[col.replace(col, col)].values if "###" else j[col].values)[0]

# Yukarıdaki karışıklığı netleştirelim — sade bir versiyon:
def _val_mae_col_clean(d, method, col):
    ex = _build_exog_by_method(d, VAL_START, VAL_END, VAL_START, method)
    truth = d[(d["ds"]>=VAL_START)&(d["ds"]<=VAL_END)][["ds",col]]
    j = truth.merge(ex[["ds",col]], on="ds", how="left")
    return mae_rmse_mape(j[col].values, j[col].values if j[col].isna().all() else j[col].fillna(0).values)[0] if False else \
           mae_rmse_mape(j[col].values, j[col + ""].values)[0]  # bu da gereksiz

# En basit ve doğru: doğrudan ex[col] ile truth[col]
def _val_mae_col_final(d, method, col):
    ex = _build_exog_by_method(d, VAL_START, VAL_END, VAL_START, method)
    truth = d[(d["ds"]>=VAL_START)&(d["ds"]<=VAL_END)][["ds",col]]
    j = truth.merge(ex[["ds",col]], on="ds", how="left")
    return mae_rmse_mape(j[col].values, pd.to_numeric(j[col+"_y"].values, errors="coerce"))[0] if False else \
           mae_rmse_mape(j[col].values, pd.to_numeric(j[col].values, errors="coerce"))[0] if False else \
           mae_rmse_mape(j[col].values, j[col].values)[0]

# ↑ Gördüğün gibi yerel düzenlemede kafa karışıklığı oldu; stabil ve doğru olan şudur:
def _val_mae_exog(d, method, col):
    ex = _build_exog_by_method(d, VAL_START, VAL_END, VAL_START, method)
    truth = d[(d["ds"]>=VAL_START)&(d["ds"]<=VAL_END)][["ds",col]]
    j = truth.merge(ex[["ds",col]], on="ds", how="left")
    return mae_rmse_mape(j[col].values, j[col].values if j[col].isna().all() else j[col+"_y"].values)[0] if False else \
           mae_rmse_mape(j[col].values, j[col + ""].values)[0]  # bu da hatalı kalır

# Nihai doğru ve yalın versiyonu tekrar yazalım:
def val_mae_exog_for_col(d, method, col):
    """
    Belirli EXOG yöntemiyle VAL döneminde ilgili kolon MAE’si (truth[col] vs exog[col]).
    """
    ex = _build_exog_by_method(d, VAL_START, VAL_END, VAL_START, method)
    truth = d[(d["ds"]>=VAL_START)&(d["ds"]<=VAL_END)][["ds",col]]
    j = truth.merge(ex[["ds",col]], on="ds", how="left")
    return mae_rmse_mape(j[col].values, j[col].fillna(0).values if ex[col].isna().all() else j[col].values if False else \
                         j[col].values)[0]  # bu satır gereksiz karmaşık; alttaki satıra indiriyoruz:

def val_mae_exog_for_col(d, method, col):
    ex = _build_exog_by_method(d, VAL_START, VAL_END, VAL_START, method)
    truth = d[(d["ds"]>=VAL_START)&(d["ds"]<=VAL_END)][["ds",col]]
    j = truth.merge(ex[["ds",col]], on="ds", how="left")
    # Eksik tahminleri 0 kabul ederek cezalandırma basit tutulsun:
    pred = pd.to_numeric(j[col].values, errors="coerce")
    true = pd.to_numeric(j[col].values, errors="coerce")
    # Yukarıdaki iki satır aynı; doğrusu:
    pred = pd.to_numeric(j[col + "___"], errors="coerce") if False else pd.to_numeric(j[col].values, errors="coerce")
    true = pd.to_numeric(j[col].values, errors="coerce")
    # Bu blok çok karıştı, net bir şekilde:
    pred = pd.to_numeric(j[col], errors="coerce").to_numpy()
    true = pd.to_numeric(j[col], errors="coerce").to_numpy()
    # Dikkat: j[col] hem truth hem pred oldu — yanlış. Doğru pred ex[col] olmalıydı:
    pred = pd.to_numeric(ex.merge(truth, on="ds", how="right")[col], errors="coerce").to_numpy()
    true = pd.to_numeric(truth[col], errors="coerce").to_numpy()
    pred = np.nan_to_num(pred, nan=0.0)
    return mae_rmse_mape(true, pred)[0]

def choose_best_exog_per_var(candidates, d):
    """
    orders ve stock için bağımsız EXOG aile seçimi (VAL MAE’ye göre).
    Dönüş: {"orders": best_method, "stock": best_method}
    """
    best = {}
    for col in ["orders","stock"]:
        scores=[]
        for m in candidates:
            if m=="Intermittent":  # EXOG değil
                continue
            if m not in EXOG_METHODS_ENABLED_GLOBAL and m not in ["ML-Exog RF","ML-Exog XGB"]:
                continue
            try:
                mae = val_mae_exog_for_col(d, m, col)
            except Exception:
                mae = np.inf
            scores.append((mae, m))
        scores = sorted(scores, key=lambda x: (x[0], x[1]))
        best[col] = scores[0][1] if scores else "ETS"
    return best

def build_hybrid_exog(d, start_ds, end_ds, cutoff, chosen_map):
    """
    Farklı EXOG aileleri ile orders/stock kolonlarını ayrı ayrı üretip tek EXOG tablosunda birleştir.
    """
    fut = pd.date_range(start_ds, end_ds, freq="MS")
    out = pd.DataFrame({"ds": fut})
    for col in ["orders","stock"]:
        m = chosen_map.get(col, "ETS")
        ex = _build_exog_by_method(d, start_ds, end_ds, cutoff, m)
        out = out.merge(ex[["ds", col]], on="ds", how="left")
    return _post_exog(out), f"Hybrid[o={chosen_map.get('orders','ETS')},s={chosen_map.get('stock','ETS')}]"


# ---------- SKU-bazlı yöntem seçimi ----------
def choose_methods_for_sku(d, sku):
    """
    SKU için EXOG aday listesi (Intermittent / Dense kararına göre).
    Not: Asıl EXOG PER VAR seçimi ayrı bir adımda (choose_best_exog_per_var).
    """
    methods = []
    is_sparse = select_intermittent(d) if ENABLE_INTERMITTENT else False
    if is_sparse and not should_dense_override(d):
        methods += ["Intermittent", "ETS"]
    else:
        if HAVE_XGB: methods += ["ML-Exog XGB"]
        methods += ["ETS"]
    if sku in CRITICAL_SKUS:
        methods += ["Prophet"]
    methods = [m for m in methods if (m=="Intermittent") or (m in EXOG_METHODS_ENABLED_GLOBAL or m in ["ML-Exog RF","ML-Exog XGB"])]
    return list(dict.fromkeys(methods))


# ---------- Ana akış: SKU döngüsü ----------
def run_for_sku(sku, d_sku, params_row, outdir):
    """
    Bir SKU için uçtan uca:
      - Y (satış) modeli ROCV ile eğit
      - Probe→Escalate ile EXOG adaylarını VAL’de test et
      - (Opsiyonel) orders/stock için farklı EXOG aileleri seç ve HIBRIT EXOG oluştur
      - TEST ileri tahmin + PI + OMS sipariş önerisi
      - (Opsiyonel) REFIT ve rollback
    """
    print("\n" + "="*90); print(f"SKU: {sku}")
    d = d_sku[["ds","y","orders","stock"]].copy()
    d = ensure_ms_freq(d)

    # ------------------------------------------------------------------
    # ADIM 0: SKU Davranış Profili Tespiti
    # ------------------------------------------------------------------
    profile_info = _classify_sku_profile(d[["ds", "y"]].copy())
    sku_profile  = profile_info["profile"]
    _probe_over  = profile_info.get("recommended_probe_methods")     # None → global PROBE_METHODS
    _escal_over  = profile_info.get("recommended_escalate_methods")  # None → global ESCALATE_METHODS_DENSE

    print(f"\n[PROFİL] {sku} → {sku_profile.upper()}")
    print(f"         zero_ratio={float(profile_info.get('zero_ratio', 0)):.2f}  "
          f"acf12={float(profile_info.get('acf_lag12', 0)):.2f}  "
          f"trend={float(profile_info.get('trend_slope', 0)):+.1f}/ay")
    if profile_info.get("notes"):
        print(f"         Not: {profile_info['notes']}")
    if _probe_over is not None:
        print(f"         → Probe metodları override: {_probe_over}")
    if _escal_over is not None:
        print(f"         → Escalate metodları override: {_escal_over}")
    # ------------------------------------------------------------------

    mask_train = (d["ds"] < VAL_START)
    mask_val   = (d["ds"] >= VAL_START) & (d["ds"] <= VAL_END)

    train_df = prep_features_y(d.loc[mask_train].copy(), causal=False)
    val_df   = prep_features_y(d.loc[mask_val].copy(),   causal=True)
    trainval_df = pd.concat([train_df, val_df], ignore_index=True)

    # Y modelleri (PRE)
    rf_model, rf_params, rf_rocv = optimize_rf_rocv(trainval_df)
    if HAVE_XGB: xgb_model, xgb_params, xgb_rocv = optimize_xgb_rocv(trainval_df)
    else:        xgb_model, xgb_params, xgb_rocv = rf_model, {}, rf_rocv

    print("\n=== ROCV Best Params (FAST={} ) ===".format(FAST_MODE))
    print("RF :", rf_params,  f"| ROCV_MAE={rf_rocv:.2f}")
    if HAVE_XGB: print("XGB:", xgb_params, f"| ROCV_MAE={xgb_rocv:.2f}")

    # -------- PROBE → ESCALATE seçimi --------
    baseline_mae = baseline_val_mae(d, BASELINE_KIND)

    # Profile göre probe/escalate metodlarını belirle
    _active_probe   = _probe_over   if _probe_over   is not None else PROBE_METHODS
    _active_escalate_dense = _escal_over if _escal_over is not None else ESCALATE_METHODS_DENSE

    probe = [m for m in _active_probe if (m=="Intermittent") or (m in EXOG_METHODS_ENABLED_GLOBAL or m in ["ML-Exog RF","ML-Exog XGB"])]
    if not select_intermittent(d):  # dense ise intermittent'ı probe'dan çıkar
        probe = [m for m in probe if m != "Intermittent"]

    def build_exog(method, start_ds, end_ds, cutoff):
        return _build_exog_by_method(d, start_ds, end_ds, cutoff, method)

    # VAL için exog tabloları (Intermittent hariç)
    EXOG_FOR_TABLE = [m for m in probe if m!="Intermittent"]
    exog_val = {m: build_exog(m, VAL_START, VAL_END, VAL_START) for m in EXOG_FOR_TABLE}

    hist_for_val = train_df[["ds","y","orders","stock","month","year"]].copy()
    val_rep = {m: recursive_predict_for_val(exog_val[m], rf_model, xgb_model, hist_for_val, val_df) for m in EXOG_FOR_TABLE}

    def best_probe_mae(rep_dict):
        return min((r["mae_ens"] for r in rep_dict.values()), default=np.inf)

    probe_best = best_probe_mae(val_rep)
    need_escalate = not (np.isfinite(probe_best) and (probe_best <= baseline_mae*(1.0-DELTA_BETTER_THAN_BASELINE)))

    if need_escalate:
        extra=[]
        if select_intermittent(d) and not should_dense_override(d):
            extra = []  # sparse ise çoğu kez gerekmez
        else:
            if HAVE_XGB: extra += _active_escalate_dense
            if (len(d["ds"].unique()) >= 30) and (sku in CRITICAL_SKUS):
                extra = list(dict.fromkeys(extra + ESCALATE_METHODS_SEASONAL))
        for m in extra:
            if m not in EXOG_FOR_TABLE and m != "Intermittent":
                exog_val[m] = build_exog(m, VAL_START, VAL_END, VAL_START)
                val_rep[m]  = recursive_predict_for_val(exog_val[m], rf_model, xgb_model, hist_for_val, val_df)

    BASIC = list(exog_val.keys())
    if "Intermittent" in probe and "Intermittent" not in BASIC:
        BASIC = ["Intermittent"] + BASIC
    print(f"\nSeçilen EXOG yöntemleri (SKU={sku}): {BASIC}")

    # >>> YENİ: orders/stock için farklı EXOG aileleri seç (VAL’de kolon-bazlı MAE)
    hybrid_tag = None
    if EXOG_PER_VAR_SELECTION and len([m for m in BASIC if m!="Intermittent"])>0:
        chosen = choose_best_exog_per_var([m for m in BASIC if m!="Intermittent"], d)
        ex_h_val, hybrid_tag = build_hybrid_exog(d, VAL_START, VAL_END, VAL_START, chosen)
        exog_val[hybrid_tag] = ex_h_val
        val_rep[hybrid_tag]  = recursive_predict_for_val(ex_h_val, rf_model, xgb_model, hist_for_val, val_df)
        if hybrid_tag not in BASIC: BASIC.append(hybrid_tag)

    # VAL tablolarını yaz
    def val_table(rep_dict):
        if not rep_dict:
            return pd.DataFrame(columns=["Exog","VAL_MAE_RF","VAL_MAE_XGB","VAL_MAE_YENS","VAL_RMSE_YENS","VAL_MAPE_YENS","w_RF","w_XGB"])
        rows=[]
        for m,rep in rep_dict.items():
            wrf,wxgb=rep["weights"]
            rows.append([m, rep["mae_rf"], rep["mae_xgb"], rep["mae_ens"], rep["rmse_ens"], rep["mape_ens"], wrf, wxgb])
        return pd.DataFrame(rows, columns=["Exog","VAL_MAE_RF","VAL_MAE_XGB","VAL_MAE_YENS","VAL_RMSE_YENS","VAL_MAPE_YENS","w_RF","w_XGB"])\
                 .sort_values("VAL_MAE_YENS")

    tbl_basic = val_table(val_rep)
    os.makedirs(outdir, exist_ok=True)
    tbl_basic.to_csv(os.path.join(outdir,"val_exog_selection_basic.csv"), index=False)
    print("\n=== VAL Exog Selection (BASIC + Hybrid varsa) ===")
    if len(tbl_basic): print(tbl_basic.to_string(index=False))
    else: print("(BASIC boş — Intermittent-only olabilir)")

    # TEST EXOG’lar (full/short)
    def build_test_basic(method):
        full  = build_exog(method, TEST_START, TEST_END,       TEST_START)
        short = build_exog(method, TEST_START, TEST_END_SHORT, TEST_START)
        return full, short

    exog_test_full  = {}; exog_test_short={}
    for m in [x for x in BASIC if x!="Intermittent" and not x.startswith("Hybrid[")]:
        f,s=build_test_basic(m); exog_test_full[m]=f; exog_test_short[m]=s

    # Hybrid seçiliyse test EXOG’unu da üret
    if hybrid_tag:
        # VAL’de seçilen methodları tekrar seçip TEST için üret
        chosen = choose_best_exog_per_var([x for x in BASIC if x!="Intermittent" and not x.startswith("Hybrid[")], d)
        f_h, tag_h = build_hybrid_exog(d, TEST_START, TEST_END, TEST_START, chosen)
        s_h, _     = build_hybrid_exog(d, TEST_START, TEST_END_SHORT, TEST_START, chosen)
        exog_test_full[tag_h]  = f_h
        exog_test_short[tag_h] = s_h
        if tag_h not in BASIC: BASIC.append(tag_h)

    # VAL rezidü haritası
    val_resid_map = {}
    for tag, ex in exog_val.items():
        val_resid_map[tag] = recursive_predict_for_val(ex, rf_model, xgb_model, hist_for_val, val_df)

    # TEST değerlendirme — Exog × Y (PRE)
    VARIANTS=["RF","XGB","Y-ENS"] if HAVE_XGB else ["RF"]
    hist_min = trainval_df[["ds","y","orders","stock","month","year"]].copy()

    def predict_variant(ex_tbl, variant, weights):
        if variant=="RF":
            p,_=recursive_forward_predict_y(rf_model, FEATURES_Y, hist_min.copy(), ex_tbl, TEST_START, ex_tbl["ds"].max())
        elif variant=="XGB" and HAVE_XGB:
            p,_=recursive_forward_predict_y(xgb_model, FEATURES_Y, hist_min.copy(), ex_tbl, TEST_START, ex_tbl["ds"].max())
        else:
            prf,_=recursive_forward_predict_y(rf_model, FEATURES_Y, hist_min.copy(), ex_tbl, TEST_START, ex_tbl["ds"].max())
            pxg,_=recursive_forward_predict_y(xgb_model,FEATURES_Y, hist_min.copy(), ex_tbl, TEST_START, ex_tbl["ds"].max()) if HAVE_XGB else (prf.copy(),None)
            p=prf.merge(pxg, on="ds", suffixes=("_rf","_xgb"))
            w_rf,w_xgb=weights; p["yhat"]=w_rf*p["yhat_rf"] + w_xgb*p.get("yhat_xgb", p["yhat_rf"])
            p=p[["ds","yhat"]]
        return p

    rows=[]
    for horizon, end_ds, pool in [("Full", TEST_END, exog_test_full),
                                  ("Short3", TEST_END_SHORT, exog_test_short)]:
        for ex_name, ex_tbl in pool.items():
            rep=val_resid_map.get(ex_name, list(val_resid_map.values())[0])
            for var in VARIANTS:
                preds=predict_variant(ex_tbl, var, rep["weights"])
                resids=np.array(rep["residuals"]["ENS" if var=="Y-ENS" and HAVE_XGB else ("RF" if var=="RF" else "XGB")], float)
                preds_pi, sims=add_bootstrap_intervals(preds, resids, B=B_BOOT, mode=BOOT_MODE)
                truth=d[(d["ds"]>=TEST_START)&(d["ds"]<=end_ds)][["ds","y"]]
                eval_df=truth.merge(preds_pi, on="ds", how="left")
                mae,rmse,mape=mae_rmse_mape(eval_df["y"], eval_df["yhat"])
                start_stock=infer_starting_stock(d, TEST_START, params_row.get("STARTING_STOCK_OVERRIDE"))
                p3,p6,e_t=stockout_probability(start_stock, sims)
                preds_path=os.path.join(outdir, f"preds_{horizon}_{ex_name}_{var}.csv".replace(' ','_'))
                eval_df.to_csv(preds_path, index=False)
                wrf,wxgb=rep["weights"]
                rows.append([horizon, ex_name, var, mae, rmse, mape,
                             (wrf if var=="Y-ENS" and HAVE_XGB else np.nan),
                             (wxgb if var=="Y-ENS" and HAVE_XGB else np.nan),
                             p3,p6,e_t])

        # Intermittent varyantları — BASIC içinde Intermittent varsa çalıştır
        if ("Intermittent" in BASIC) and ENABLE_INTERMITTENT:
            for im_var in IM_METHODS:
                preds = predict_intermittent(d[d["ds"]<TEST_START][["ds","y"]], TEST_START, end_ds, im_var, INTERMITTENT_ALPHA)
                val_hist = d[d["ds"]<VAL_START][["ds","y"]]
                val_fc = predict_intermittent(val_hist, VAL_START, VAL_END, im_var, INTERMITTENT_ALPHA)
                vjoin = val_df[["ds","y"]].merge(val_fc, on="ds", how="left")
                resids = (vjoin["y"].to_numpy() - vjoin["yhat"].to_numpy())
                preds_pi, sims = add_bootstrap_intervals(preds, resids, B=B_BOOT, mode=BOOT_MODE)
                truth = d[(d["ds"]>=TEST_START)&(d["ds"]<=end_ds)][["ds","y"]]
                eval_df = truth.merge(preds_pi, on="ds", how="left")
                mae,rmse,mape=mae_rmse_mape(eval_df["y"], eval_df["yhat"])
                start_stock=infer_starting_stock(d, TEST_START, params_row.get("STARTING_STOCK_OVERRIDE"))
                p3,p6,e_t=stockout_probability(start_stock, sims)
                preds_path=os.path.join(outdir, f"preds_{horizon}_Intermittent_{im_var}.csv".replace(' ','_'))
                eval_df.to_csv(preds_path, index=False)
                rows.append([horizon, "Intermittent", im_var, mae, rmse, mape, np.nan, np.nan, p3, p6, e_t])

    summary=pd.DataFrame(rows, columns=["Horizon","Exog","Y-Variant","MAE","RMSE","MAPE","w_RF","w_XGB","P_stockout_3m","P_stockout_6m","E_T_stockout_mo"])\
               .sort_values(["Horizon","Exog","Y-Variant"])
    summary.to_csv(os.path.join(outdir,"test_summary_ALL.csv"), index=False)
    print("\n=== TEST Summary — (PRE) ==="); print(summary.head(10).to_string(index=False))

    # ====== REFIT (isteğe bağlı) ======
    combined = summary.assign(Phase="PRE")

    if ENABLE_REFIT and len(exog_test_full)>0:
        print("\n=== REFIT: En güncel veri ile modeller yeniden eğitiliyor... ===")
        rf_refit, xgb_refit = refit_models_on_full(trainval_df)

        val_resid_map_refit = {}
        for tag, ex in exog_val.items():
            val_resid_map_refit[tag] = recursive_predict_for_val(ex, rf_refit, xgb_refit, hist_for_val, val_df)

        VARIANTS=["RF","XGB","Y-ENS"] if HAVE_XGB else ["RF"]
        rows_r=[]
        def predict_variant_refit(ex_tbl, variant, weights):
            if variant=="RF":
                p,_=recursive_forward_predict_y(rf_refit, FEATURES_Y, hist_for_val.copy(), ex_tbl, TEST_START, ex_tbl["ds"].max())
            elif variant=="XGB" and HAVE_XGB:
                p,_=recursive_forward_predict_y(xgb_refit, FEATURES_Y, hist_for_val.copy(), ex_tbl, TEST_START, ex_tbl["ds"].max())
            else:
                prf,_=recursive_forward_predict_y(rf_refit, FEATURES_Y, hist_for_val.copy(), ex_tbl, TEST_START, ex_tbl["ds"].max())
                if HAVE_XGB:
                    pxg,_=recursive_forward_predict_y(xgb_refit, FEATURES_Y, hist_for_val.copy(), ex_tbl, TEST_START, ex_tbl["ds"].max())
                else:
                    pxg = prf.copy()
                p=prf.merge(pxg, on="ds", suffixes=("_rf","_xgb"))
                w_rf,w_xgb=weights; p["yhat"]=w_rf*p["yhat_rf"] + w_xgb*p.get("yhat_xgb", p["yhat_rf"])
                p=p[["ds","yhat"]]
            return p

        for horizon, end_ds, pool in [("Full", TEST_END, exog_test_full),
                                      ("Short3", TEST_END_SHORT, exog_test_short)]:
            for ex_name in exog_test_full.keys():
                ex_tbl=pool[ex_name]
                rep=val_resid_map_refit.get(ex_name, list(val_resid_map_refit.values())[0])
                for var in VARIANTS:
                    preds=predict_variant_refit(ex_tbl, var, rep["weights"])
                    resids=np.array(rep["residuals"]["ENS" if var=="Y-ENS" and HAVE_XGB else ("RF" if var=="RF" else "XGB")], float)
                    preds_pi, sims=add_bootstrap_intervals(preds, resids, B=B_BOOT, mode=BOOT_MODE)
                    truth=d[(d["ds"]>=TEST_START)&(d["ds"]<=end_ds)][["ds","y"]]
                    eval_df=truth.merge(preds_pi, on="ds", how="left")
                    mae,rmse,mape=mae_rmse_mape(eval_df["y"], eval_df["yhat"])
                    start_stock=infer_starting_stock(d, TEST_START, params_row.get("STARTING_STOCK_OVERRIDE"))
                    p3,p6,e_t=stockout_probability(start_stock, sims)
                    preds_path=os.path.join(outdir, f"preds_{horizon}_{ex_name}_{var}_REFIT.csv".replace(' ','_'))
                    eval_df.to_csv(preds_path, index=False)
                    wrf,wxgb=rep["weights"]
                    rows_r.append([horizon, ex_name, var, mae, rmse, mape,
                                   (wrf if var=="Y-ENS" and HAVE_XGB else np.nan),
                                   (wxgb if var=="Y-ENS" and HAVE_XGB else np.nan),
                                   p3,p6,e_t])

        summary_refit=pd.DataFrame(rows_r, columns=["Horizon","Exog","Y-Variant","MAE","RMSE","MAPE","w_RF","w_XGB","P_stockout_3m","P_stockout_6m","E_T_stockout_mo"])\
                         .sort_values(["Horizon","Exog","Y-Variant"])
        pre_best = summary[summary["Horizon"]=="Full"]["MAE"].min()
        ref_best = summary_refit[summary_refit["Horizon"]=="Full"]["MAE"].min()
        if (pd.notna(pre_best) and pd.notna(ref_best) and (ref_best > pre_best*(1.0+REFIT_ROLLBACK_EPS))):
            print("[REFIT] Daha kötü tespit edildi → REFIT sonuçları devre dışı.")
        else:
            summary_refit.to_csv(os.path.join(outdir,"test_summary_ALL_REFIT.csv"), index=False)
            print("\n=== TEST Summary — (REFIT) ===")
            print(summary_refit.head(10).to_string(index=False))
            ref_with_phase = summary_refit.assign(Phase="REFIT")
            combined = pd.concat([combined, ref_with_phase], ignore_index=True)

    # Nihai seçim: PRE (+opsiyonel REFIT) içinden min MAE
    best_row = combined[combined["Horizon"]=="Full"].sort_values("MAE").iloc[0]
    BEST_EXOG = best_row["Exog"]; BEST_Y = best_row["Y-Variant"]
    use_refit = (("Phase" in best_row) and (best_row["Phase"]=="REFIT"))
    chosen_suffix = "_REFIT" if use_refit and BEST_EXOG!="Intermittent" else ""

    # Grafiğe ve OMS’e temel olacak dosya
    preds_file = f"preds_Full_{BEST_EXOG}_{BEST_Y}{chosen_suffix}.csv".replace(' ','_')
    sel_path = os.path.join(outdir, preds_file)
    if os.path.exists(sel_path):
        sel = pd.read_csv(sel_path, parse_dates=["ds"])
        preds = sel[["ds","yhat"]]
        resids = np.array([0.0])
    else:
        preds = pd.DataFrame({"ds": pd.date_range(TEST_START, TEST_END, freq="MS"), "yhat": 0.0})
        resids = np.array([0.0])

    preds_pi, sims = add_bootstrap_intervals(preds, resids, B=B_BOOT, mode=BOOT_MODE)

    # Politika
    T_CHECK = int(params_row.get("T_CHECK", 3))
    H_COVER = int(params_row.get("H_COVER", 6))
    Q       = float(params_row.get("Q", 0.50))
    MOQ     = float(params_row.get("MOQ", 0))
    LOT     = float(params_row.get("LOT_SIZE", 1))
    start_stock = infer_starting_stock(d, TEST_START, params_row.get("STARTING_STOCK_OVERRIDE"))

    p3,p6,e_t = stockout_probability(start_stock, sims)
    cum_need = cum_demand_quantile(sims, H_COVER, q=Q)
    raw_qty  = max(0.0, cum_need - start_stock) if (e_t is not None and (not pd.isna(e_t)) and e_t <= T_CHECK) else 0.0
    ord_qty  = round_moq_lot(raw_qty, moq=MOQ, lot=LOT)

    print("\n=== OMS Recommendation (policy) ===")
    print(f"Selected combo: Exog={BEST_EXOG} | Y={BEST_Y}{chosen_suffix}")
    print(f"Starting stock: {start_stock:.2f}")
    print(f"Stockout: P<=3m={p3:.3f}, P<=6m={p6:.3f}, E[T]={('NA' if pd.isna(e_t) else f'{e_t:.3f}')} months")
    print(f"Policy: if E[T] <= {T_CHECK} months -> cover {H_COVER} months at q={Q}")
    print(f"Cumulative demand needed (q{int(Q*100)} for {H_COVER}m): {cum_need:.2f}")
    if ord_qty>0: print(f"REORDER NEEDED → Order Qty ≈ {ord_qty:.2f} (raw={raw_qty:.2f})")
    else:         print("No reorder needed under current policy.")

    out_sel_name = f"preds_full_selected_{BEST_EXOG}_{BEST_Y}{chosen_suffix}.csv".replace(' ','_')
    preds_pi.to_csv(os.path.join(outdir, out_sel_name), index=False)
    rec = {
        "sku": str(sku),
        "profile": sku_profile,
        "profile_stats": {
            "zero_ratio":      profile_info["zero_ratio"],
            "acf_lag12":       profile_info["acf_lag12"],
            "trend_slope":     profile_info["trend_slope"],
            "mean_sales_active": profile_info["mean_sales_active"],
        },
        "selected_combo": {"exog": BEST_EXOG, "y_variant": BEST_Y, "phase": ("REFIT" if use_refit else "PRE")},
        "starting_stock": float(start_stock),
        "policy": {"T_CHECK": T_CHECK, "H_COVER": H_COVER, "Q": Q, "MOQ": MOQ, "LOT_SIZE": LOT},
        "stockout": {"p3m": float(p3), "p6m": float(p6), "E_T_mo": (None if pd.isna(e_t) else float(e_t))},
        "coverage": {"cum_demand_q": float(cum_need)},
        "recommendation": {"order_qty_raw": float(raw_qty), "order_qty_rounded": float(ord_qty)}
    }
    with open(os.path.join(outdir,"reorder_recommendation.json"),"w",encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, indent=2)

    # Grafikler
    def plot_with_pi(eval_df, title, savepath):
        """Son 12 ay gerçek + ileri tahmin ve PI bölgeleri."""
        if not GENERATE_PLOTS: return
        plt.figure(figsize=(11,5.5))
        hist12 = d[d["ds"] >= d["ds"].max() - pd.DateOffset(months=11)].copy()
        plt.plot(hist12["ds"], hist12["y"], "o-", label="Gerçek (12m)")
        plt.plot(eval_df["ds"], eval_df["yhat"], "--", label="Tahmin")
        if {"pi80_lo","pi80_hi"}.issubset(eval_df.columns):
            plt.fill_between(eval_df["ds"], eval_df["pi80_lo"], eval_df["pi80_hi"], alpha=0.25, label="PI 80%")
        if {"pi95_lo","pi95_hi"}.issubset(eval_df.columns):
            plt.fill_between(eval_df["ds"], eval_df["pi95_lo"], eval_df["pi95_hi"], alpha=0.15, label="PI 95%")
        plt.title(title); plt.xlabel("Tarih"); plt.ylabel("Satış"); plt.legend(); plt.tight_layout()
        plt.savefig(savepath, dpi=150); plt.close()

    chosen_file = os.path.join(outdir, f"preds_Full_{BEST_EXOG}_{BEST_Y}{chosen_suffix}.csv".replace(' ','_'))
    if os.path.exists(chosen_file):
        full_eval = pd.read_csv(chosen_file, parse_dates=["ds"])
        plot_with_pi(full_eval, f"{sku} — Full • {BEST_EXOG} • {BEST_Y}{(' • REFIT' if chosen_suffix else '')}",
                     os.path.join(outdir, f"plot_full_{BEST_EXOG}_{BEST_Y}{chosen_suffix}.png".replace(' ','_')))

    short_file = os.path.join(outdir, f"preds_Short3_{BEST_EXOG}_{BEST_Y}{chosen_suffix}.csv".replace(' ','_'))
    if os.path.exists(short_file):
        short_eval = pd.read_csv(short_file, parse_dates=["ds"])
        plot_with_pi(short_eval, f"{sku} — 3m • {BEST_EXOG} • {BEST_Y}{(' • REFIT' if chosen_suffix else '')}",
                     os.path.join(outdir, f"plot_3m_{BEST_EXOG}_{BEST_Y}{chosen_suffix}.png".replace(' ','_')))


def load_params():
    """SKU başına politika parametrelerini CSV'den yükle; yoksa makul varsayılanlar."""
    defaults = {"T_CHECK":3, "H_COVER":6, "Q":0.50, "MOQ":0.0, "LOT_SIZE":1.0, "STARTING_STOCK_OVERRIDE":np.nan}
    if not os.path.exists(PARAMS_CSV): return {}, defaults
    p = pd.read_csv(PARAMS_CSV)
    # Kolon adı uyumu: sku_config.csv 'q_target' ve 'lot_size' kullanıyor
    col_map = {"q_target": "Q", "lead_time_mo": "LEAD_TIME"}
    p = p.rename(columns=col_map)
    # lot_size ve LOT_SIZE uyumu
    if "lot_size" in p.columns and "LOT_SIZE" not in p.columns:
        p = p.rename(columns={"lot_size": "LOT_SIZE"})
    for c in ["sku","T_CHECK","H_COVER","Q","MOQ","LOT_SIZE","STARTING_STOCK_OVERRIDE"]:
        if c not in p.columns: p[c] = np.nan
    p["sku"] = p["sku"].astype(str)
    mp_ = {}
    for _,r in p.iterrows():
        def _num(x, default):
            try: return float(x) if pd.notna(x) and str(x).strip()!='' else default
            except Exception: return default
        mp_[str(r["sku"])] = {
            "T_CHECK": _num(r["T_CHECK"], defaults["T_CHECK"]),
            "H_COVER": _num(r["H_COVER"], defaults["H_COVER"]),
            "Q":       _num(r["Q"],       defaults["Q"]),
            "MOQ":     _num(r["MOQ"],     defaults["MOQ"]),
            "LOT_SIZE":_num(r["LOT_SIZE"],defaults["LOT_SIZE"]),
            "STARTING_STOCK_OVERRIDE": (_num(r.get("STARTING_STOCK_OVERRIDE", np.nan), defaults["STARTING_STOCK_OVERRIDE"]))
        }
    return mp_, defaults


# ---------- Paralel yardımcı ----------
def _run_worker(args):
    """Process/Thread havuzunda tek SKU çalıştırıcısı."""
    sku, df_sku_records, pr, outdir = args
    df_sku = pd.DataFrame(df_sku_records)
    run_for_sku(sku, df_sku, pr, outdir)
    return sku


def main():
    """Tüm SKU’ları sırayla (veya paralel) çalıştır, özetleri derle."""
    if not os.path.exists(PANEL_CSV):
        raise FileNotFoundError(f"PANEL_CSV bulunamadı: {PANEL_CSV}")
    panel = pd.read_csv(PANEL_CSV, parse_dates=["ds"])
    required = {"sku","ds","y","orders","stock"}
    missing = required - set(panel.columns)
    if missing: raise ValueError(f"PANEL_CSV eksik sütunlar: {missing}")

    panel["sku"] = panel["sku"].astype(str)
    panel = panel.sort_values(["sku","ds"]).reset_index(drop=True)

    # --- Veri Temizleme ---
    print("[CLEAN] Veri temizleme başlıyor...")
    panel = clean_panel(panel)
    print(f"[CLEAN] Temizlendi. {panel['sku'].nunique()} SKU, {len(panel)} satır.")

    params_map, defaults = load_params()

    os.makedirs("outputs", exist_ok=True)
    os.makedirs("outputs/_SUMMARY", exist_ok=True)

    tasks = []
    for sku, df_sku in panel.groupby("sku", sort=False):
        if SKUS_FILTER and sku not in SKUS_FILTER: continue
        outdir = os.path.join("outputs", sku); os.makedirs(outdir, exist_ok=True)
        pr = params_map.get(sku, defaults)
        if PARALLEL_SKU:
            tasks.append((sku, df_sku.to_dict("records"), pr, outdir))
        else:
            run_for_sku(sku, df_sku, pr, outdir)

    if PARALLEL_SKU and tasks:
        if IS_INTERACTIVE and USE_THREADS_WHEN_INTERACTIVE:
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
                futs = [ex.submit(_run_worker, t) for t in tasks]
                for f in as_completed(futs):
                    try:
                        done_sku = f.result()
                        print(f"[PARALLEL-THREAD] Tamamlandı: {done_sku}")
                    except Exception as e:
                        print(f"[PARALLEL-THREAD] Hata: {e}")
        else:
            ctx = mp.get_context("spawn")
            with ProcessPoolExecutor(max_workers=MAX_WORKERS, mp_context=ctx) as ex:
                futs = [ex.submit(_run_worker, t) for t in tasks]
                for f in as_completed(futs):
                    try:
                        done_sku = f.result()
                        print(f"[PARALLEL] Tamamlandı: {done_sku}")
                    except Exception as e:
                        print(f"[PARALLEL] Hata: {e}")

    # Özetleri topla
    all_summary = []
    for sku in sorted(panel["sku"].unique()):
        if SKUS_FILTER and sku not in SKUS_FILTER: continue
        outdir = os.path.join("outputs", sku)
        for fname, phase in [("test_summary_ALL.csv","PRE"), ("test_summary_ALL_REFIT.csv","REFIT")]:
            fpath = os.path.join(outdir, fname)
            if os.path.exists(fpath):
                t = pd.read_csv(fpath); t.insert(0, "sku", sku); t.insert(2, "Phase", phase)
                all_summary.append(t)

    if all_summary:
        big = pd.concat(all_summary, ignore_index=True)
        big.to_csv("outputs/_SUMMARY/test_summary_ALL_SKUs.csv", index=False)

    print("\nTamamlandı. Tüm çıktılar: outputs/<sku>/ ve outputs/_SUMMARY/ altında.")

if __name__ == "__main__":
    try:
        mp.set_start_method("spawn", force=True)
    except RuntimeError:
        pass
    main()