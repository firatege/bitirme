# -*- coding: utf-8 -*-
"""
v6_multi_sku.py — OMS Edition (Refit + Time-Decay NNLS + Intermittent + Parallel-safe)

Bu sürümde:
- time-decayed NNLS
- Croston/SBA/TSB intermittent
- Paralelde Jupyter/REPL'de ThreadPool fallback, script'te ProcessPool(spawn)
- nnls_adapt eklendi
"""

import os, json, warnings, sys, math, logging
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

# === Opsiyonel bağımlılıklar (yoksa otomatik devre dışı) ===
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
PARAMS_CSV = "sku_params.csv"                # sku, T_CHECK, H_COVER, Q, MOQ, LOT_SIZE, STARTING_STOCK_OVERRIDE

# --- Tarih bölmeleri ---
VAL_START        = pd.Timestamp("2024-08-01")
VAL_END          = pd.Timestamp("2025-01-01")
TEST_START       = pd.Timestamp("2025-02-01")
TEST_END         = pd.Timestamp("2025-08-01")
TEST_END_SHORT   = pd.Timestamp("2025-04-01")

# --- Bootstrap & adaptif ---
SEED         = 1337
B_BOOT       = 800
ADAPT_WINS   = [3,4,6]
RIDGE_ALPHA  = 1e-3
SMOOTH_BETA  = 0.15
EXOG_VAL_H   = 6
EPS_PROPHET  = 0.05
RANDOM_STATE = 42

# --- “Seçim sonrası refit” akışı ---
ENABLE_REFIT  = True
REFIT_TAIL_K  = 3

# --- Time-decayed NNLS (VAL kaybına zaman ağırlığı) ---
ENABLE_TIME_DECAY_NNLS = True
DECAY_GAMMA = 0.90   # her ay geriye gittikçe ağırlık *= gamma

# --- Intermittent talep (Croston/SBA/TSB) ---
ENABLE_INTERMITTENT   = True
INTERMITTENT_ALPHA    = 0.10
INTERMITTENT_SELECTOR = "auto"  # "auto" | "all" | "none"

# --- Paralel SKU çalıştırma ---
PARALLEL_SKU = True          # güvenli başlangıç için kapalı
MAX_WORKERS  = max(1, (os.cpu_count() or 4)//2)

# Interaktif ortam algısı (Jupyter/REPL için thread fallback)
IS_INTERACTIVE = bool(getattr(sys, 'ps1', sys.flags.interactive)) or ('ipykernel' in sys.modules)
USE_THREADS_WHEN_INTERACTIVE = True

# --- Y modeli öznitelikleri ---
FEATURES_Y = [
    "orders","stock",
    "orders_lag1","orders_lag3",
    "stock_lag1","stock_lag3",
    "y_lag1",
    "orders_ratio",
    "month","year",
]

# --- İsteğe bağlı kısıt (yalnızca belirli SKU’lar) ---
SKUS_FILTER = None            # Örn: {"SKU1","SKU2"}  (None=hepsi)
GENERATE_PLOTS = True


# ======================================================================
# ============================ Ç E K I R D E K ==========================
# ======================================================================

rng_boot = np.random.default_rng(SEED)

# ---------- Yardımcılar ----------
def ensure_ms_freq(df):
    d = df.copy().sort_values("ds")
    d["ds"] = pd.to_datetime(d["ds"]).dt.to_period("M").dt.to_timestamp(how="start")
    d = d.drop_duplicates(["ds"]).set_index("ds").sort_index()
    d.index = pd.DatetimeIndex(d.index, freq="MS")
    return d.reset_index()

def add_calendar(df):
    d = df.copy()
    d["year"]  = d["ds"].dt.year
    d["month"] = d["ds"].dt.month
    return d

def rolling_impute(s, causal=False):
    x = pd.to_numeric(s, errors="coerce")
    if causal:
        x = x.ffill()
        x = x.rolling(window=3, min_periods=1).mean().bfill()
    else:
        roll = x.rolling(window=3, center=True, min_periods=1).mean()
        x = x.where(~x.isna(), roll).ffill().bfill()
    return x

def smooth_causal_ma(s, window=3):
    x = pd.to_numeric(s, errors="coerce").ffill()
    return x.rolling(window=window, min_periods=1).mean().bfill()

def winsorize_series(s, lq=0.05, uq=0.95):
    x = pd.to_numeric(s, errors="coerce")
    lo = np.nanpercentile(x, lq*100); hi = np.nanpercentile(x, uq*100)
    return x.clip(lo, hi)

def nonneg(s): return pd.to_numeric(s, errors="coerce").clip(lower=0.0)

def build_lags_y(df):
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

def cast_nan(s):
    return pd.to_numeric(s, errors="coerce")

def prep_features_y(df_in, causal=False):
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
    y_true = np.asarray(y_true, float); y_pred = np.asarray(y_pred, float)
    mae  = mean_absolute_error(y_true, y_pred)
    rmse = float(np.sqrt(np.mean((y_pred - y_true)**2)))
    denom = np.where(y_true==0, 1, y_true)
    mape = float(np.mean(np.abs((y_true - y_pred)/denom))*100)
    return mae, rmse, mape

# ---------- Univariate EXOG ----------
def fit_prophet(train_df, value_col):
    if not HAVE_PROPHET: raise RuntimeError("Prophet not available")
    m = Prophet(yearly_seasonality=True, weekly_seasonality=False)
    m.fit(train_df.rename(columns={value_col:"y"}))
    return m

def fc_prophet(model, steps):
    fut = model.make_future_dataframe(periods=steps, freq="MS")
    return model.predict(fut)[["ds","yhat"]].tail(steps).rename(columns={"yhat":"yhat"})

def sarima_fit_best(y, p_rng=(0,3), q_rng=(0,3), P_rng=(0,1), Q_rng=(0,1)):
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
    y = train_df.set_index("ds")[value_col]; y.index.freq = "MS"
    best = sarima_fit_best(y)
    if best is None: return None
    return SARIMAX(y, order=best[0], seasonal_order=best[1],
                   enforce_stationarity=False, enforce_invertibility=False).fit(disp=False)

def fc_sarima(model, steps, future_idx):
    pred = model.get_forecast(steps=steps).predicted_mean
    return pd.DataFrame({"ds": pd.DatetimeIndex(future_idx), "yhat": pred.values})

def fit_ets(train_df, value_col):
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
    d=dfv[["ds",col]].sort_values("ds").copy()
    d["lag1"]=d[col].shift(1); d["lag3"]=d[col].shift(3)
    d["month"]=d["ds"].dt.month; d["year"]=d["ds"].dt.year
    return d

def train_exog_rf(dfv, col, cutoff):
    d=make_exog_frame(dfv[dfv["ds"]<cutoff], col).dropna()
    if d.empty: return None
    X=d[EXOG_FEATS]; y=d[col]
    rf=RandomForestRegressor(n_estimators=400, max_depth=8, min_samples_split=2, min_samples_leaf=1,
                             random_state=RANDOM_STATE, n_jobs=-1)
    rf.fit(X,y); return rf

def train_exog_xgb(dfv,col,cutoff):
    if not HAVE_XGB: return None
    d=make_exog_frame(dfv[dfv["ds"]<cutoff], col).dropna()
    if d.empty: return None
    X=d[EXOG_FEATS].to_numpy(); y=d[col].to_numpy()
    xgb=XGBRegressor(n_estimators=500, learning_rate=0.08, max_depth=3, subsample=0.9,
                     colsample_bytree=0.9, reg_lambda=1.2, random_state=RANDOM_STATE)
    xgb.fit(X,y,verbose=False); return xgb

def recursive_fc_exog(model, hist_df, col, start_ds, end_ds):
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
    fut=pd.date_range(start_ds,end_ds,freq="MS")
    out=pd.DataFrame({"ds":fut})
    for col in ["orders","stock"]:
        s=df_all[["ds",col]].dropna().sort_values("ds"); s=s[s["ds"]<cutoff]
        if s.empty: out[col]=0.0; continue
        steps=len(fut)
        try:
            if method=="prophet":
                if not HAVE_PROPHET: raise RuntimeError("Prophet not available")
                m=fit_prophet(s,col); tmp=fc_prophet(m,steps)
            elif method=="sarima":
                m=fit_sarima(s,col);  tmp=fc_sarima(m,steps,fut)
            else:
                m=fit_ets(s,col);     tmp=fc_ets(m,steps,fut)
            tmp=tmp.rename(columns={"yhat":col})
        except Exception:
            tmp=pd.DataFrame({"ds":fut, col:np.nan})
        out=out.merge(tmp[["ds",col]], on="ds", how="left")
    return _post_exog(out)

def build_exog_inverse(df_all, start_ds, end_ds, cutoff, eps_prophet=EPS_PROPHET):
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
    """
    Örnek ağırlıklı NNLS (zaman-ağırlıklı kayıp için).
    """
    sw = np.asarray(sample_w, float).reshape(-1)
    sw = np.where(np.isfinite(sw)&(sw>0), sw, 1.0)
    r = np.sqrt(sw).reshape(-1,1)
    A_w = A * r
    y_w = y * r.ravel()
    return nnls_ridge(A_w, y_w, alpha=alpha, iters=iters)

def nnls_adapt(A, y, w_prev=None, alpha=0.0, beta=0.0, iters=600):
    """
    Adaptif NNLS (Ridge + smoothness):
      minimize ||A w - y||^2 + alpha*||w||^2 + beta*||w - w_prev||^2
    kısıt: w >= 0, sum(w) = 1  (simplex)
    """
    A = np.asarray(A, float)
    y = np.asarray(y, float).reshape(-1)
    K = A.shape[1]
    if K == 1:
        return np.array([1.0], dtype=float)

    # Başlangıç: önceki ağırlıklar varsa oradan, yoksa uniform
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

    # Adım boyu
    L = (np.linalg.norm(A, 2) ** 2) + alpha + beta + 1e-6
    step = 1.0 / L
    AT = A.T

    w = w_prev.copy()
    for _ in range(iters):
        grad = 2.0 * (AT @ (A @ w - y)) + 2.0 * alpha * w + 2.0 * beta * (w - w_prev)
        w = project_simplex(w - step * grad)
    return w

def fit_nnls_weights_on_val(exog_dict, df_true, alpha=0.0, time_decay=False, gamma=0.95):
    """
    VAL üzerinde (opsiyonel zaman çürümesi ile) NNLS/Ridge ağırlığı.
    """
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

# ---------- Intermittent talep (Croston / SBA / TSB) ----------
def select_intermittent(d):
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
    base = croston_forecast(y, alpha)
    return base * (1 - alpha/2.0)

def tsb_forecast(y, alpha=0.1, beta=None):
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

def predict_intermittent(hist_df, start_ds, end_ds, method="Croston", alpha=INTERMITTENT_ALPHA):
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

# ---------- Y ROCV ----------
def rolling_origin_splits(df, n_splits=3, min_train_months=24):
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
    grid={"n_estimators":[400,700], "max_depth":[None,8,12], "min_samples_split":[2,5], "min_samples_leaf":[1,2]}
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
    if not HAVE_XGB: return None, None, np.inf
    grid = {"n_estimators":[500,800],"learning_rate":[0.05,0.1],"max_depth":[3,4],
            "subsample":[0.8,1.0],"colsample_bytree":[0.8,1.0],"reg_lambda":[1.0,2.0]}
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
def add_bootstrap_intervals(pred_df, residuals, B=B_BOOT, mode="auto", clamp_nonneg=True):
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
    if override is not None and pd.notna(override): return float(override)
    prev=df_raw[df_raw["ds"]<test_start].tail(1)
    if "stock" in prev and len(prev): return float(max(0.0, prev["stock"].iloc[0]))
    return 0.0

def stockout_probability(start_stock, sims):
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
    months=int(months); 
    if months<=0: return 0.0
    sims=np.maximum(0.0,sims)
    sums=np.sum(sims[:months,:], axis=0)
    return float(np.nanquantile(sums, q))

def round_moq_lot(q, moq=0, lot=1):
    q=max(0.0,q)
    if q>0 and q<moq: q=moq
    lot = (lot if lot and lot>0 else 1)
    return float(math.ceil(q/lot)*lot)

# ---------- VAL skoru / Y-ENS ----------
def y_ensemble_weights(y_true, yhat_rf, yhat_xgb, eps=1e-6):
    mae_rf=mean_absolute_error(y_true, yhat_rf)
    mae_xgb=mean_absolute_error(y_true, yhat_xgb)
    wrf, wxgb = 1.0/(mae_rf+eps), 1.0/(mae_xgb+eps)
    s=wrf+wxgb
    return wrf/s, wxgb/s, mae_rf, mae_xgb

def recursive_predict_for_val(exog_tbl, rf_model, xgb_model, hist_for_val, val_df):
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
    rf_refit, rf_params, rf_score = optimize_rf_rocv(df_full)
    if HAVE_XGB: xgb_refit, xgb_params, xgb_score = optimize_xgb_rocv(df_full)
    else:        xgb_refit, xgb_params, xgb_score = rf_refit, {}, rf_score
    return rf_refit, xgb_refit


# ---------- Ana akış: SKU döngüsü ----------
def run_for_sku(sku, d_sku, params_row, outdir):
    print("\n" + "="*90); print(f"SKU: {sku}")
    d = d_sku[["ds","y","orders","stock"]].copy()
    d = ensure_ms_freq(d)

    mask_train = (d["ds"] < VAL_START)
    mask_val   = (d["ds"] >= VAL_START) & (d["ds"] <= VAL_END)

    train_df = prep_features_y(d.loc[mask_train].copy(), causal=False)
    val_df   = prep_features_y(d.loc[mask_val].copy(),   causal=True)
    trainval_df = pd.concat([train_df, val_df], ignore_index=True)

    # Y modelleri (PRE-REFIT)
    rf_model, rf_params, rf_rocv = optimize_rf_rocv(trainval_df)
    if HAVE_XGB: xgb_model, xgb_params, xgb_rocv = optimize_xgb_rocv(trainval_df)
    else:        xgb_model, xgb_params, xgb_rocv = rf_model, {}, rf_rocv

    print("\n=== ROCV Best Params ===")
    print("RF :", rf_params,  f"| ROCV_MAE={rf_rocv:.2f}")
    if HAVE_XGB: print("XGB:", xgb_params, f"| ROCV_MAE={xgb_rocv:.2f}")

    # EXOG’lar (VAL)
    BASIC=["Prophet","SARIMA","ETS","Ensemble","ML-Exog RF","ML-Exog XGB"]
    def build_exog(method, start_ds, end_ds, cutoff):
        if method=="Prophet":  return build_exog_univar(d, start_ds, end_ds, cutoff, "prophet")
        if method=="SARIMA":   return build_exog_univar(d, start_ds, end_ds, cutoff, "sarima")
        if method=="ETS":      return build_exog_univar(d, start_ds, end_ds, cutoff, "ets")
        if method=="Ensemble": return build_exog_inverse(d, start_ds, end_ds, cutoff)
        if method=="ML-Exog RF":  return build_exog_ml(d, start_ds, end_ds, cutoff, "rf")
        if method=="ML-Exog XGB": return build_exog_ml(d, start_ds, end_ds, cutoff, "xgb")
        raise ValueError(method)

    exog_val = {m: build_exog(m, VAL_START, VAL_END, VAL_START) for m in BASIC}

    # VAL skorları
    hist_for_val = train_df[["ds","y","orders","stock","month","year"]].copy()
    val_rep = {m: recursive_predict_for_val(exog_val[m], rf_model, xgb_model, hist_for_val, val_df) for m in BASIC}

    def val_table(rep_dict):
        rows=[]
        for m,rep in rep_dict.items():
            wrf,wxgb=rep["weights"]
            rows.append([m, rep["mae_rf"], rep["mae_xgb"], rep["mae_ens"], rep["rmse_ens"], rep["mape_ens"], wrf, wxgb])
        return pd.DataFrame(rows, columns=["Exog","VAL_MAE_RF","VAL_MAE_XGB","VAL_MAE_YENS","VAL_RMSE_YENS","VAL_MAPE_YENS","w_RF","w_XGB"])\
                 .sort_values("VAL_MAE_YENS")

    tbl_basic = val_table(val_rep)
    os.makedirs(outdir, exist_ok=True)
    tbl_basic.to_csv(os.path.join(outdir,"val_exog_selection_basic.csv"), index=False)
    print("\n=== VAL Exog Selection (BASIC) ==="); print(tbl_basic.to_string(index=False))

    ALL5=["Prophet","SARIMA","ETS","ML-Exog RF","ML-Exog XGB"]
    mae_all5={m:val_rep[m]["mae_ens"] for m in ALL5}
    ranked=sorted(ALL5, key=lambda x: (mae_all5[x], x))
    Top2=ranked[:2]; Top3=ranked[:3]

    def inv_weights(methods):
        inv=[]
        for m in methods:
            v=mae_all5[m]; inv.append(0.0 if (not np.isfinite(v) or v<=0) else 1.0/v)
        s=sum(inv) if sum(inv)>0 else 1.0
        return {m:inv[i]/s for i,m in enumerate(methods)}

    inv_all5=inv_weights(ALL5); inv_top2=inv_weights(Top2); inv_top3=inv_weights(Top3)

    # NNLS (VAL) — isteğe bağlı zaman çürümesi
    val_truth = d[(d["ds"]>=VAL_START)&(d["ds"]<=VAL_END)][["ds","orders","stock"]].reset_index(drop=True)
    nnls_all5       = fit_nnls_weights_on_val({m:exog_val[m] for m in ALL5}, val_truth, alpha=0.0,
                                              time_decay=ENABLE_TIME_DECAY_NNLS, gamma=DECAY_GAMMA)
    nnls_top2       = fit_nnls_weights_on_val({m:exog_val[m] for m in Top2}, val_truth, alpha=0.0,
                                              time_decay=ENABLE_TIME_DECAY_NNLS, gamma=DECAY_GAMMA)
    nnls_top3       = fit_nnls_weights_on_val({m:exog_val[m] for m in Top3}, val_truth, alpha=0.0,
                                              time_decay=ENABLE_TIME_DECAY_NNLS, gamma=DECAY_GAMMA)
    nnls_all5_ridge = fit_nnls_weights_on_val({m:exog_val[m] for m in ALL5}, val_truth, alpha=RIDGE_ALPHA,
                                              time_decay=ENABLE_TIME_DECAY_NNLS, gamma=DECAY_GAMMA)
    nnls_top2_ridge = fit_nnls_weights_on_val({m:exog_val[m] for m in Top2}, val_truth, alpha=RIDGE_ALPHA,
                                              time_decay=ENABLE_TIME_DECAY_NNLS, gamma=DECAY_GAMMA)
    nnls_top3_ridge = fit_nnls_weights_on_val({m:exog_val[m] for m in Top3}, val_truth, alpha=RIDGE_ALPHA,
                                              time_decay=ENABLE_TIME_DECAY_NNLS, gamma=DECAY_GAMMA)

    def combine_by_inv(methods, inv_w):
        return {"orders":{m:inv_w[m] for m in methods}, "stock":{m:inv_w[m] for m in methods}}

    composite_parts_val = {m: exog_val[m] for m in ALL5}

    def build_and_score(tag, wv):
        ex = combine_exogs_weighted(composite_parts_val, wv)
        rep = recursive_predict_for_val(ex, rf_model, xgb_model, hist_for_val, val_df)
        return tag, ex, rep

    extra_rep={}; tag_ex_val={}
    for tag, wv in [("All-5-INV", combine_by_inv(ALL5, inv_all5)),
                    ("Top2-INV",  combine_by_inv(Top2, inv_top2)),
                    ("Top3-INV",  combine_by_inv(Top3, inv_top3))]:
        t, ex, rep = build_and_score(tag, wv); tag_ex_val[t]=ex; extra_rep[t]=rep
    for tag, wv in [("All-5-NNLS", nnls_all5), ("Top2-NNLS", nnls_top2), ("Top3-NNLS", nnls_top3),
                    ("All-5-NNLS-Ridge", nnls_all5_ridge), ("Top2-NNLS-Ridge", nnls_top2_ridge), ("Top3-NNLS-Ridge", nnls_top3_ridge)]:
        t, ex, rep = build_and_score(tag, wv); tag_ex_val[t]=ex; extra_rep[t]=rep

    val_all = {**val_rep, **extra_rep}
    tbl_all = val_table(val_all)
    tbl_all.to_csv(os.path.join(outdir,"val_exog_selection_ALL_with_NNLS_Ridge.csv"), index=False)
    print("\n=== VAL Exog Selection — Inverse + (Time-decayed) NNLS (Ridge) ===")
    print(tbl_all.to_string(index=False))

    # TEST EXOG’lar
    def build_test_basic(method):
        full  = build_exog(method, TEST_START, TEST_END,       TEST_START)
        short = build_exog(method, TEST_START, TEST_END_SHORT, TEST_START)
        return full, short

    exog_test_full  = {}; exog_test_short={}
    for m in BASIC:
        f,s=build_test_basic(m); exog_test_full[m]=f; exog_test_short[m]=s

    def build_test_composite(wv):
        meth=list(wv["orders"].keys())
        parts_full  = {m: exog_test_full[m]  for m in meth}
        parts_short = {m: exog_test_short[m] for m in meth}
        return combine_exogs_weighted(parts_full, wv), combine_exogs_weighted(parts_short, wv)

    exog_test_full["All-5-INV"],  exog_test_short["All-5-INV"]  = build_test_composite(combine_by_inv(ALL5, inv_all5))
    exog_test_full["Top2-INV"],   exog_test_short["Top2-INV"]   = build_test_composite(combine_by_inv(Top2, inv_top2))
    exog_test_full["Top3-INV"],   exog_test_short["Top3-INV"]   = build_test_composite(combine_by_inv(Top3, inv_top3))
    exog_test_full["All-5-NNLS"],       exog_test_short["All-5-NNLS"]       = build_test_composite(nnls_all5)
    exog_test_full["Top2-NNLS"],        exog_test_short["Top2-NNLS"]        = build_test_composite(nnls_top2)
    exog_test_full["Top3-NNLS"],        exog_test_short["Top3-NNLS"]        = build_test_composite(nnls_top3)
    exog_test_full["All-5-NNLS-Ridge"], exog_test_short["All-5-NNLS-Ridge"] = build_test_composite(nnls_all5_ridge)
    exog_test_full["Top2-NNLS-Ridge"],  exog_test_short["Top2-NNLS-Ridge"]  = build_test_composite(nnls_top2_ridge)
    exog_test_full["Top3-NNLS-Ridge"],  exog_test_short["Top3-NNLS-Ridge"]  = build_test_composite(nnls_top3_ridge)

    # Adaptive NNLS
    def nnls_adapt_local(A,y,w_prev,alpha=RIDGE_ALPHA,beta=SMOOTH_BETA):
        return nnls_adapt(A,y,w_prev,alpha=alpha,beta=beta)

    def build_adaptive(methods_val, methods_test, df_true, start_ds, end_ds, win=6, alpha=RIDGE_ALPHA, beta=SMOOTH_BETA):
        fut=pd.date_range(start_ds,end_ds,freq="MS"); names=list(methods_test.keys())
        preds={m: pd.concat([methods_val[m][["ds","orders","stock"]], methods_test[m][["ds","orders","stock"]]]).reset_index(drop=True) for m in names}
        out=pd.DataFrame({"ds":fut}); w_prev_o=None; w_prev_s=None; co=[]; cs=[]
        for ds in fut:
            end_w=ds - pd.DateOffset(months=1)
            hist=df_true[(df_true["ds"]>=VAL_START)&(df_true["ds"]<=end_w)][["ds","orders","stock"]].tail(win)
            if len(hist)==0:
                w_o=np.ones(len(names))/len(names); w_s=w_o.copy()
            else:
                A_o=np.vstack([preds[m].merge(hist[["ds"]],on="ds",how="inner")["orders"].to_numpy() for m in names]).T
                A_s=np.vstack([preds[m].merge(hist[["ds"]],on="ds",how="inner")["stock"].to_numpy()  for m in names]).T
                y_o=hist["orders"].to_numpy(); y_s=hist["stock"].to_numpy()
                w_o=nnls_adapt_local(A_o,y_o,w_prev_o,alpha=alpha,beta=beta)
                w_s=nnls_adapt_local(A_s,y_s,w_prev_s,alpha=alpha,beta=beta)
            cur={m: methods_test[m][methods_test[m]["ds"]==ds] for m in names}
            co.append(sum(float(w_o[i])*float(cur[names[i]]["orders"].values[0]) for i in range(len(names))))
            cs.append(sum(float(w_s[i])*float(cur[names[i]]["stock"].values[0])  for i in range(len(names))))
            w_prev_o, w_prev_s = w_o, w_s
        out["orders"]=co; out["stock"]=cs
        return _post_exog(out)

    for w in ADAPT_WINS:
        tag=f"Adaptive5-NNLS-w{w}"
        af=build_adaptive({m:exog_val[m] for m in ALL5},{m:exog_test_full[m] for m in ALL5}, d[["ds","orders","stock"]], TEST_START, TEST_END, win=w)
        ashort=af[af["ds"]<=TEST_END_SHORT].copy()
        exog_test_full[tag]=af; exog_test_short[tag]=ashort

    # VAL rezidü haritası (PRE-REFIT)
    val_resid_map = {}
    for tag, ex in {**exog_val}.items():
        val_resid_map[tag] = recursive_predict_for_val(ex, rf_model, xgb_model, hist_for_val, val_df)
    for w in ADAPT_WINS:
        tag=f"Adaptive5-NNLS-w{w}"
        val_resid_map[tag]=val_resid_map.get("ML-Exog XGB", list(val_resid_map.values())[0])

    # TEST değerlendirme — Exog × Y (PRE-REFIT)
    VARIANTS=["RF","XGB","Y-ENS"] if HAVE_XGB else ["RF"]
    ALL_EXOG = ["Prophet","SARIMA","ETS","Ensemble","ML-Exog RF","ML-Exog XGB",
                "All-5-INV","Top2-INV","Top3-INV","All-5-NNLS","Top2-NNLS","Top3-NNLS",
                "All-5-NNLS-Ridge","Top2-NNLS-Ridge","Top3-NNLS-Ridge"] + [f"Adaptive5-NNLS-w{w}" for w in ADAPT_WINS]

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
        for ex_name in ALL_EXOG:
            ex_tbl=pool[ex_name]
            rep=val_resid_map.get(ex_name, val_resid_map["ML-Exog XGB"])
            for var in VARIANTS:
                preds=predict_variant(ex_tbl, var, rep["weights"])
                resids=np.array(rep["residuals"]["ENS" if var=="Y-ENS" and HAVE_XGB else ("RF" if var=="RF" else "XGB")], float)
                preds_pi, sims=add_bootstrap_intervals(preds, resids, B=B_BOOT)
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

        # Intermittent varyantları
        if ENABLE_INTERMITTENT and select_intermittent(d):
            for im_var in ["Croston","SBA","TSB"]:
                preds = predict_intermittent(d[d["ds"]<TEST_START][["ds","y"]], TEST_START, end_ds, im_var, INTERMITTENT_ALPHA)
                val_hist = d[d["ds"]<VAL_START][["ds","y"]]
                val_fc = predict_intermittent(val_hist, VAL_START, VAL_END, im_var, INTERMITTENT_ALPHA)
                vjoin = val_df[["ds","y"]].merge(val_fc, on="ds", how="left")
                resids = (vjoin["y"].to_numpy() - vjoin["yhat"].to_numpy())
                preds_pi, sims = add_bootstrap_intervals(preds, resids, B=B_BOOT)
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
    print("\n=== TEST Summary — ALL Variants (PRE) ==="); print(summary.to_string(index=False))

    # ====== REFIT ======
    if ENABLE_REFIT:
        print("\n=== REFIT: En güncel veri ile modeller yeniden eğitiliyor... ===")
        rf_refit, xgb_refit = refit_models_on_full(trainval_df)
        val_resid_map_refit = {}
        ALL5=["Prophet","SARIMA","ETS","ML-Exog RF","ML-Exog XGB"]
        composite_parts_val = {m: exog_val[m] for m in ALL5}
        ranked_local = sorted(ALL5, key=lambda x: (val_rep[x]["mae_ens"], x))
        nnls_recent_all5 = fit_nnls_weights_recent(composite_parts_val, d[["ds","orders","stock"]],
                                                   VAL_START, TEST_START, k_tail=REFIT_TAIL_K, alpha=RIDGE_ALPHA,
                                                   time_decay=ENABLE_TIME_DECAY_NNLS, gamma=DECAY_GAMMA)
        Top2=ranked_local[:2]; Top3=ranked_local[:3]
        nnls_recent_top2 = fit_nnls_weights_recent({m:exog_val[m] for m in Top2}, d[["ds","orders","stock"]],
                                                   VAL_START, TEST_START, k_tail=REFIT_TAIL_K, alpha=RIDGE_ALPHA,
                                                   time_decay=ENABLE_TIME_DECAY_NNLS, gamma=DECAY_GAMMA)
        nnls_recent_top3 = fit_nnls_weights_recent({m:exog_val[m] for m in Top3}, d[["ds","orders","stock"]],
                                                   VAL_START, TEST_START, k_tail=REFIT_TAIL_K, alpha=RIDGE_ALPHA,
                                                   time_decay=ENABLE_TIME_DECAY_NNLS, gamma=DECAY_GAMMA)
        def rebuild_with_weights(wv):
            meth=list(wv["orders"].keys())
            parts_full  = {m: exog_test_full[m]  for m in meth}
            parts_short = {m: exog_test_short[m] for m in meth}
            return combine_exogs_weighted(parts_full, wv), combine_exogs_weighted(parts_short, wv)
        exog_test_full["All-5-NNLS-RECENT"],       exog_test_short["All-5-NNLS-RECENT"]       = rebuild_with_weights(nnls_recent_all5)
        exog_test_full["Top2-NNLS-RECENT"],        exog_test_short["Top2-NNLS-RECENT"]        = rebuild_with_weights(nnls_recent_top2)
        exog_test_full["Top3-NNLS-RECENT"],        exog_test_short["Top3-NNLS-RECENT"]        = rebuild_with_weights(nnls_recent_top3)

        hist_for_val_refit = train_df[["ds","y","orders","stock","month","year"]].copy()
        for tag, ex in {**exog_val, 
                        "All-5-NNLS-RECENT": combine_exogs_weighted(composite_parts_val, nnls_recent_all5),
                        "Top2-NNLS-RECENT":  combine_exogs_weighted({m:exog_val[m] for m in Top2}, nnls_recent_top2),
                        "Top3-NNLS-RECENT":  combine_exogs_weighted({m:exog_val[m] for m in Top3}, nnls_recent_top3)}.items():
            val_resid_map_refit[tag] = recursive_predict_for_val(ex, rf_refit, xgb_refit, hist_for_val_refit, val_df)

        ALL_EXOG_REFIT = ALL_EXOG + ["All-5-NNLS-RECENT","Top2-NNLS-RECENT","Top3-NNLS-RECENT"]
        VARIANTS=["RF","XGB","Y-ENS"] if HAVE_XGB else ["RF"]
        rows_r=[]
        def predict_variant_refit(ex_tbl, variant, weights):
            if variant=="RF":
                p,_=recursive_forward_predict_y(rf_refit, FEATURES_Y, hist_min.copy(), ex_tbl, TEST_START, ex_tbl["ds"].max())
            elif variant=="XGB" and HAVE_XGB:
                p,_=recursive_forward_predict_y(xgb_refit, FEATURES_Y, hist_min.copy(), ex_tbl, TEST_START, ex_tbl["ds"].max())
            else:
                prf,_=recursive_forward_predict_y(rf_refit, FEATURES_Y, hist_min.copy(), ex_tbl, TEST_START, ex_tbl["ds"].max())
                if HAVE_XGB:
                    pxg,_=recursive_forward_predict_y(xgb_refit, FEATURES_Y, hist_min.copy(), ex_tbl, TEST_START, ex_tbl["ds"].max())
                else:
                    pxg = prf.copy()
                p=prf.merge(pxg, on="ds", suffixes=("_rf","_xgb"))
                w_rf,w_xgb=weights; p["yhat"]=w_rf*p["yhat_rf"] + w_xgb*p.get("yhat_xgb", p["yhat_rf"])
                p=p[["ds","yhat"]]
            return p

        for horizon, end_ds, pool in [("Full", TEST_END, exog_test_full),
                                      ("Short3", TEST_END_SHORT, exog_test_short)]:
            for ex_name in ALL_EXOG_REFIT:
                if ex_name not in pool: continue
                ex_tbl=pool[ex_name]
                rep=val_resid_map_refit.get(ex_name, list(val_resid_map_refit.values())[0])
                for var in VARIANTS:
                    preds=predict_variant_refit(ex_tbl, var, rep["weights"])
                    resids=np.array(rep["residuals"]["ENS" if var=="Y-ENS" and HAVE_XGB else ("RF" if var=="RF" else "XGB")], float)
                    preds_pi, sims=add_bootstrap_intervals(preds, resids, B=B_BOOT)
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

            if ENABLE_INTERMITTENT and select_intermittent(d):
                for im_var in ["Croston","SBA","TSB"]:
                    preds = predict_intermittent(d[d["ds"]<TEST_START][["ds","y"]], TEST_START, end_ds, im_var, INTERMITTENT_ALPHA)
                    val_hist = d[d["ds"]<VAL_START][["ds","y"]]
                    val_fc = predict_intermittent(val_hist, VAL_START, VAL_END, im_var, INTERMITTENT_ALPHA)
                    vjoin = val_df[["ds","y"]].merge(val_fc, on="ds", how="left")
                    resids = (vjoin["y"].to_numpy() - vjoin["yhat"].to_numpy())
                    preds_pi, sims = add_bootstrap_intervals(preds, resids, B=B_BOOT)
                    truth = d[(d["ds"]>=TEST_START)&(d["ds"]<=end_ds)][["ds","y"]]
                    eval_df = truth.merge(preds_pi, on="ds", how="left")
                    mae,rmse,mape=mae_rmse_mape(eval_df["y"], eval_df["yhat"])
                    start_stock=infer_starting_stock(d, TEST_START, params_row.get("STARTING_STOCK_OVERRIDE"))
                    p3,p6,e_t=stockout_probability(start_stock, sims)
                    preds_path=os.path.join(outdir, f"preds_{horizon}_Intermittent_{im_var}_REFIT.csv".replace(' ','_'))
                    eval_df.to_csv(preds_path, index=False)
                    rows_r.append([horizon, "Intermittent", im_var, mae, rmse, mape, np.nan, np.nan, p3, p6, e_t])

        summary_refit=pd.DataFrame(rows_r, columns=["Horizon","Exog","Y-Variant","MAE","RMSE","MAPE","w_RF","w_XGB","P_stockout_3m","P_stockout_6m","E_T_stockout_mo"])\
                         .sort_values(["Horizon","Exog","Y-Variant"])
        summary_refit.to_csv(os.path.join(outdir,"test_summary_ALL_REFIT.csv"), index=False)
        print("\n=== TEST Summary — ALL Variants (REFIT) ===")
        print(summary_refit.to_string(index=False))

    # En iyi kombinasyon & OMS
    select_df = pd.read_csv(os.path.join(outdir,"test_summary_ALL_REFIT.csv")) if ENABLE_REFIT and os.path.exists(os.path.join(outdir,"test_summary_ALL_REFIT.csv")) else summary
    best_row = select_df[select_df["Horizon"]=="Full"].sort_values("MAE").iloc[0]
    BEST_EXOG = best_row["Exog"]; BEST_Y = best_row["Y-Variant"]

    # Tahmin dosyası
    chosen_suffix = "_REFIT" if (ENABLE_REFIT and os.path.exists(os.path.join(outdir,"test_summary_ALL_REFIT.csv"))) else ""
    sel_path = os.path.join(outdir, f"preds_Full_{'Intermittent' if BEST_EXOG=='Intermittent' else BEST_EXOG}_{BEST_Y}{chosen_suffix}.csv".replace(' ','_'))
    if os.path.exists(sel_path):
        sel = pd.read_csv(sel_path, parse_dates=["ds"])
        preds = sel[["ds","yhat"]]
        # varsayılan residual kaynağı (güvenli)
        resids = np.array([0.0])
    else:
        preds = pd.DataFrame({"ds": pd.date_range(TEST_START, TEST_END, freq="MS"),
                              "yhat": 0.0})
        resids = np.array([0.0])

    preds_pi, sims = add_bootstrap_intervals(preds, resids, B=B_BOOT)

    # Politikalar
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
        "selected_combo": {"exog": BEST_EXOG, "y_variant": BEST_Y},
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

    chosen_file = os.path.join(outdir, f"preds_Full_{'Intermittent' if BEST_EXOG=='Intermittent' else BEST_EXOG}_{BEST_Y}{chosen_suffix}.csv".replace(' ','_'))
    if os.path.exists(chosen_file):
        full_eval = pd.read_csv(chosen_file, parse_dates=["ds"])
        plot_with_pi(full_eval, f"{sku} — Full • {BEST_EXOG} • {BEST_Y}{(' • REFIT' if chosen_suffix else '')}",
                     os.path.join(outdir, f"plot_full_{BEST_EXOG}_{BEST_Y}{chosen_suffix}.png".replace(' ','_')))

    short_file = os.path.join(outdir, f"preds_Short3_{'Intermittent' if BEST_EXOG=='Intermittent' else BEST_EXOG}_{BEST_Y}{chosen_suffix}.csv".replace(' ','_'))
    if os.path.exists(short_file):
        short_eval = pd.read_csv(short_file, parse_dates=["ds"])
        plot_with_pi(short_eval, f"{sku} — 3m • {BEST_EXOG} • {BEST_Y}{(' • REFIT' if chosen_suffix else '')}",
                     os.path.join(outdir, f"plot_3m_{BEST_EXOG}_{BEST_Y}{chosen_suffix}.png".replace(' ','_')))


def load_params():
    defaults = {"T_CHECK":3, "H_COVER":6, "Q":0.50, "MOQ":0.0, "LOT_SIZE":1.0, "STARTING_STOCK_OVERRIDE":np.nan}
    if not os.path.exists(PARAMS_CSV): return {}, defaults
    p = pd.read_csv(PARAMS_CSV)
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
            "STARTING_STOCK_OVERRIDE": (_num(r["STARTING_STOCK_OVERRIDE"], defaults["STARTING_STOCK_OVERRIDE"]))
        }
    return mp_, defaults


# ---------- Paralel yardımcı (opsiyonel) ----------
def _run_worker(args):
    sku, df_sku_records, pr, outdir = args
    df_sku = pd.DataFrame(df_sku_records)
    run_for_sku(sku, df_sku, pr, outdir)
    return sku


def main():
    if not os.path.exists(PANEL_CSV):
        raise FileNotFoundError(f"PANEL_CSV bulunamadı: {PANEL_CSV}")
    panel = pd.read_csv(PANEL_CSV, parse_dates=["ds"])
    required = {"sku","ds","y","orders","stock"}
    missing = required - set(panel.columns)
    if missing: raise ValueError(f"PANEL_CSV eksik sütunlar: {missing}")

    panel["sku"] = panel["sku"].astype(str)
    panel = panel.sort_values(["sku","ds"]).reset_index(drop=True)

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
            # Notebook/REPL → Thread pool (pickling derdi yok)
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
                futs = [ex.submit(_run_worker, t) for t in tasks]
                for f in as_completed(futs):
                    try:
                        done_sku = f.result()
                        print(f"[PARALLEL-THREAD] Tamamlandı: {done_sku}")
                    except Exception as e:
                        print(f"[PARALLEL-THREAD] Hata: {e}")
        else:
            # Script/CLI → gerçek süreç havuzu (spawn context ile)
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

    print("\nTamamlandı. Tüm çıktılar: outputs/<sku>/ altında.")

if __name__ == "__main__":
    try:
        mp.set_start_method("spawn", force=True)
    except RuntimeError:
        pass
    main()
