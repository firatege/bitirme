# -*- coding: utf-8 -*-
"""
sku_profiler.py — SKU Davranış Profili Tespiti
===============================================

Her SKU'nun geçmiş satış serisine bakarak davranış profilini belirler
ve o profile en uygun model stratejisini önerir.

Profiller:
  - new_growing   : Geçmişte sıfır/çok düşük, yakın zamanda birden aktifleşmiş
  - stable_high   : Sürekli yüksek hacimli, istikrarlı
  - seasonal      : Belirli aylarda yoğunlaşan, yıllık periyodik davranış
  - intermittent  : Seyrek, çoğunlukla sıfır (Croston/TSB bölgesi)
  - declining     : Eskiden aktif, son dönemde belirgin düşüş
  - standard      : Yukarıdakilerden hiçbiri — genel amaçlı pipeline yeterli

Kullanım:
    from sku_profiler import classify_sku_profile
    info = classify_sku_profile(sku_df)  # ds, y, orders, stock kolonları
    print(info["profile"], info["recommended_probe_methods"])
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, List


# ---------------------------------------------------------------------------
# Profil → Model Stratejisi Haritası
# ---------------------------------------------------------------------------
PROFILE_STRATEGY: Dict[str, Dict[str, List[str]]] = {
    "new_growing": {
        "probe":    ["ML-Exog XGB", "ETS"],
        "escalate": ["Prophet"],          # Prophet changepoint büyümeyi iyi yakalar
    },
    "stable_high": {
        "probe":    ["ETS", "ML-Exog XGB"],
        "escalate": ["Prophet"],          # yıllık mevsimsellik için
    },
    "seasonal": {
        "probe":    ["Prophet", "ETS"],
        "escalate": ["ML-Exog XGB"],      # ML residual yakalaması için
    },
    "intermittent": {
        "probe":    ["Intermittent", "ETS"],
        "escalate": [],                   # ağır model gereksiz
    },
    "declining": {
        "probe":    ["ETS", "Intermittent"],
        "escalate": [],                   # az veri/düşük hacim, basit model yeterli
    },
    "standard": {
        "probe":    None,                 # None → model_v3 kendi PROBE_METHODS'unu kullanır
        "escalate": None,
    },
}


# ---------------------------------------------------------------------------
# Yardımcı Fonksiyonlar
# ---------------------------------------------------------------------------

def _safe_autocorr(series: pd.Series, lag: int) -> float:
    """NaN-güvenli otokorelasyon hesabı."""
    try:
        val = series.autocorr(lag=lag)
        return float(val) if np.isfinite(val) else 0.0
    except Exception:
        return 0.0


def _trend_slope(y: np.ndarray) -> float:
    """
    Aktif (sıfır olmayan) dönemlerin lineer regresyon eğimi.
    Pozitif → büyüme, negatif → düşüş.
    """
    mask = y > 0
    if mask.sum() < 3:
        return 0.0
    x = np.where(mask)[0].astype(float)
    yv = y[mask].astype(float)
    try:
        slope = float(np.polyfit(x, yv, 1)[0])
        return slope if np.isfinite(slope) else 0.0
    except Exception:
        return 0.0


def _adi(y: np.ndarray) -> float:
    """Average Demand Interval — sıfırlar arasındaki ortalama boşluk."""
    nonzero_idx = np.where(y > 0)[0]
    if len(nonzero_idx) < 2:
        return float("inf")
    gaps = np.diff(nonzero_idx)
    return float(gaps.mean()) + 1.0


def _first_active_month_ratio(y: np.ndarray) -> float:
    """İlk aktif ayın serinin kaçıncı %'sinde olduğunu verir (0-1)."""
    n = len(y)
    if n == 0:
        return 0.0
    idx = np.argmax(y > 0)
    return float(idx) / n


def _recent_vs_early_ratio(y: np.ndarray, window: int = 6) -> float:
    """Son window ayın ortalaması / ilk window ayın ortalaması."""
    if len(y) < window * 2:
        return 1.0
    early = y[:window]
    recent = y[-window:]
    early_mean = np.mean(early[early > 0]) if (early > 0).any() else 0.0
    recent_mean = np.mean(recent[recent > 0]) if (recent > 0).any() else 0.0
    if early_mean == 0.0:
        return float("inf") if recent_mean > 0 else 1.0
    return recent_mean / early_mean


# ---------------------------------------------------------------------------
# Ana Profil Sınıflandırıcı
# ---------------------------------------------------------------------------

def classify_sku_profile(d: pd.DataFrame) -> Dict[str, Any]:
    """
    Bir SKU'nun satış serisini analiz edip davranış profili ve
    model stratejisi önerisi döndürür.

    Parametreler
    ------------
    d : pd.DataFrame
        Asgari kolonlar: ["ds", "y"] (orders ve stock olsa da kullanılmaz)

    Döndürür
    --------
    dict:
        profile                    : str  — ana profil adı
        zero_ratio                 : float
        adi                        : float
        acf_lag12                  : float
        trend_slope                : float  (birim/ay)
        mean_sales_active          : float  (sıfır olmayan ayların ortalaması)
        first_active_ratio         : float  (0-1, ilk satışın serinin kaçta kaçında)
        recent_vs_early            : float  (son 6ay / ilk 6ay oranı)
        recommended_probe_methods  : list[str] | None
        recommended_escalate_methods: list[str] | None
        notes                      : str
    """
    y_series = pd.to_numeric(d["y"], errors="coerce").fillna(0.0)
    y = y_series.values.astype(float)
    n = len(y)

    # Temel istatistikler
    zero_ratio        = float((y == 0).mean())
    adi_val           = _adi(y)
    acf12             = _safe_autocorr(y_series, lag=12)
    slope             = _trend_slope(y)
    nonzero           = y[y > 0]
    mean_active       = float(nonzero.mean()) if len(nonzero) > 0 else 0.0
    first_act_ratio   = _first_active_month_ratio(y)
    recent_vs_early   = _recent_vs_early_ratio(y, window=6)

    # -------------------------------------------------------------------
    # Kural Sıralaması (öncelik sırasıyla)
    # -------------------------------------------------------------------
    profile = "standard"
    notes   = ""

    # "early_all_zero": ilk 6 ayda hiç satış yok → veri seti sıfırla başlıyor
    early_all_zero = (recent_vs_early == float("inf"))

    # 1. Hiç satış yok → özel durum
    if np.all(y == 0):
        profile = "intermittent"
        notes   = "Serinin tamamı sıfır — hiç satış gerçekleşmemiş."

    # 2. Stable High — önce kontrol et (yüksek hacimli stabil, seyrek değil)
    elif (mean_active > 5_000) and (zero_ratio < 0.30):
        profile = "stable_high"
        notes   = (
            f"Yüksek hacimli istikrarlı ürün: ort={mean_active:.0f} birim/ay, "
            f"zero_ratio={zero_ratio:.2f}."
        )

    # 3. New Growing — başlangıç sıfır ama son dönem aktif
    elif early_all_zero and n >= 12:
        last12 = y[-12:] if n >= 12 else y
        last12_active_ratio = float((last12 > 0).mean())
        if last12_active_ratio >= 0.40 and mean_active >= 50:
            profile = "new_growing"
            notes   = (
                f"Erken dönem (ilk 6 ay) tamamen sıfır, son 12 ayın "
                f"%{last12_active_ratio*100:.0f}'ü satışlı. "
                f"Büyüme: {slope:+.1f}/ay."
            )
        else:
            profile = "intermittent"
            notes   = (
                f"Geç başlayan ancak seyrek/düşük hacim: "
                f"zero_ratio={zero_ratio:.2f}, mean_active={mean_active:.1f}."
            )

    # 4. Intermittent — seyrek talep (eşik yükseltildi)
    elif (zero_ratio > 0.45) or (adi_val > 2.0):
        profile = "intermittent"
        notes   = (f"Seyrek talep: zero_ratio={zero_ratio:.2f}, ADI={adi_val:.2f}.")

    # 5. Declining — son dönem belirgin düşüş
    elif (not early_all_zero) and (recent_vs_early < 0.40) and (mean_active > 50):
        profile = "declining"
        notes   = (
            f"Son dönem satışı erken döneme göre %{(1-recent_vs_early)*100:.0f} düşmüş."
        )

    # 6. Seasonal — güçlü 12 aylık otokorelasyon
    elif acf12 > 0.40 and n >= 24:
        profile = "seasonal"
        notes   = (
            f"Güçlü mevsimsellik: lag-12 otokorelasyon={acf12:.2f}. "
            f"Prophet/SARIMA önerilir."
        )

    # 7. Standard — diğer
    else:
        profile = "standard"
        notes   = "Belirgin bir davranış örüntüsü tespit edilmedi; genel pipeline yeterli."

    strategy = PROFILE_STRATEGY.get(profile, PROFILE_STRATEGY["standard"])

    return {
        "profile":                      profile,
        "zero_ratio":                   round(zero_ratio, 4),
        "adi":                          round(adi_val, 2),
        "acf_lag12":                    round(acf12, 4),
        "trend_slope":                  round(slope, 2),
        "mean_sales_active":            round(mean_active, 2),
        "first_active_ratio":           round(first_act_ratio, 4),
        "recent_vs_early":              round(recent_vs_early, 4),
        "recommended_probe_methods":    strategy["probe"],
        "recommended_escalate_methods": strategy["escalate"],
        "notes":                        notes,
    }


# ---------------------------------------------------------------------------
# Toplu Analiz (log / debug için)
# ---------------------------------------------------------------------------

def profile_all_skus(panel: pd.DataFrame) -> pd.DataFrame:
    """
    Tüm SKU'lar için profil tespiti yapar ve özet DataFrame döndürür.

    Parametreler
    ------------
    panel : pd.DataFrame
        Kolonlar: sku, ds, y, [orders, stock]

    Döndürür
    --------
    pd.DataFrame — her satır bir SKU
    """
    rows = []
    for sku, g in panel.groupby("sku", sort=True):
        info = classify_sku_profile(g[["ds", "y"]].copy())
        rows.append({
            "sku":               sku,
            "profile":           info["profile"],
            "zero_ratio":        info["zero_ratio"],
            "adi":               info["adi"],
            "acf_lag12":         info["acf_lag12"],
            "trend_slope":       info["trend_slope"],
            "mean_sales_active": info["mean_sales_active"],
            "recent_vs_early":   info["recent_vs_early"],
            "probe_methods":     str(info["recommended_probe_methods"]),
            "notes":             info["notes"],
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Komut Satırı: python sku_profiler.py
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys, os
    panel_path = os.path.join(os.path.dirname(__file__), "panel_sales_orders_stock.csv")
    if not os.path.exists(panel_path):
        print(f"HATA: {panel_path} bulunamadı."); sys.exit(1)

    panel = pd.read_csv(panel_path, parse_dates=["ds"])
    df = profile_all_skus(panel)

    print("\n" + "=" * 90)
    print("SKU DAVRANIŞ PROFİLİ RAPORU")
    print("=" * 90)
    print(df[["sku", "profile", "zero_ratio", "acf_lag12", "trend_slope",
              "mean_sales_active", "recent_vs_early"]].to_string(index=False))
    print("\nProfil Dağılımı:")
    print(df["profile"].value_counts().to_string())

    out_path = os.path.join(os.path.dirname(__file__), "outputs", "_SUMMARY", "sku_profiles.csv")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    df.to_csv(out_path, index=False)
    print(f"\n→ Kaydedildi: {out_path}")
