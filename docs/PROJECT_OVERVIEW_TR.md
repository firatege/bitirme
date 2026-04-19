# Proje Genel Bakışı — Çoklu-SKU Satış Tahmini ve Sipariş Yönetim Sistemi

> Türkçe bitirme tezi projesi. Motul benzeri bir yağ distribütörü için SKU bazlı talep tahmini + otomatik satın alma sipariş önerisi sistemi. Dışsal değişkenler için zaman serisi topluluğu (Prophet + SARIMA + ETS), hedef değişken için ağaç tabanlı topluluk (Random Forest + XGBoost), karıştırma için NNLS stacking, seyrek SKU'lar için kesintili talep modelleri, bootstrap tahmin aralıkları ve MOQ/lot kısıtlı sipariş büyüklüğü kullanılır.

Türkçe, tez odaklı bir anlatım [`proje_ozeti.md`](../proje_ozeti.md) dosyasında mevcuttur. Bu dokümanın amacı mühendislik bakış açısıyla tamamlayıcı olmak: dosya haritası, modül sorumlulukları, veri akışı ve mimari.

---

## 1. Bu Proje Ne Yapıyor?

Aylık `(sku, ds, y, orders, stock)` paneli — gerçekleşen satışlar, gelen satın alma siparişleri, ay sonu stok — ve SKU bazlı politika dosyası `sku_config.csv` (MOQ, lot büyüklüğü, kapsam ufku, servis seviyesi kuantili) verildiğinde sistem her SKU için iki soruya cevap üretir:

1. **Önümüzdeki 3 / 6 ayda ne kadar satacak?** — sadece nokta tahmini değil, %80 ve %95 tahmin aralıklı.
2. **Şu an kaç adet sipariş verilmeli, bu inceleme döneminde sipariş açılmalı mı?** — MOQ ve lot büyüklüğüne saygı göstererek, mevcut eldeki stoğa karşı stoksuz kalma olasılığı tarafından sürülerek.

Tahmin sisteminin temel mantığı şu gözlemdir: **talep stok tarafından sansürlendiğinde (censored demand)** naif satış tahmini yanıltıcıdır — geçen ay sıfır satan bir SKU'nun aslında yüksek talebi olup stoğu tükenmiş olabilir. Model bu gerçek sinyali geri kazanmak için stok ve gelen siparişleri dışsal regresör olarak kullanır.

---

## 2. Teknoloji Yığını

| Katman | Yığın |
|---|---|
| Dil | Python 3 (üretim scriptleri), Jupyter notebook (araştırma) |
| Veri | `pandas`, `numpy` |
| Klasik zaman serisi | `prophet`, `statsmodels` (`SARIMAX`, `ExponentialSmoothing`) |
| ML modelleri | `scikit-learn` (`RandomForestRegressor`), `xgboost` (`XGBRegressor`) |
| Kesintili talep | El yazımı `Croston`, `SBA` (Syntetos-Boylan), `TSB` |
| Stacking | El yazımı NNLS — projeksiyon gradyanı ile (harici `scipy.optimize.nnls` bağımlılığı yok) |
| Paralellik | `concurrent.futures.ProcessPoolExecutor` (CLI) / `ThreadPoolExecutor` (Jupyter fallback), `multiprocessing.get_context("spawn")` |
| Grafikler | `matplotlib` |
| Kalıcılık | Serileştirilmiş modeller için `joblib`, çıktılar için düz CSV + JSON |

Web framework yok, veritabanı yok, paket yöneticisi lock dosyası yok — saf script + notebook iş akışı.

---

## 3. Repo Yapısı

```
bitirme/
├── proje_ozeti.md                      # Türkçe tez özeti (mevcut)
├── CLAUDE.md                           # Claude Code için çalışma notları (kök dizinde olmalı)
├── .claudeignore                       # Claude bağlamından büyük artefaktları hariç tutar
├── docs/
│   ├── PROJECT_OVERVIEW.md             # İngilizce mühendislik dokümanı
│   ├── PROJECT_OVERVIEW_TR.md          # Bu dosya
│   └── CLAUDE_TR.md                    # CLAUDE.md'in Türkçe çevirisi (referans)
│
├── scripts/
│   ├── __init__.py
│   ├── model_v3.py     (1416 satır)    # BİRİNCİL üretim scripti — en güncel
│   ├── model_v2.py     (1417 satır)    # v3'ün yakın ikizi, araştırma-ayarlı sabitler
│   └── OMS.py          (1237 satır)    # Önceki bağımsız pipeline (prototip)
│
├── Sales Forecast v7_full.ipynb        # En güncel araştırma notebook'u (v7, ~1.7 MB)
│
├── panel_sales_orders_stock.csv        # Kanonik aylık panel girdisi
├── sku_config.csv                      # SKU bazlı politika parametreleri
├── motul_data.csv                      # Ham işlem bazlı satış verisi
├── veri_matrisi_final_sales_orders_stock_calendar_lags_fx.csv  # Ara geniş matris
│
├── serialized_models/
│   └── best_y_model_rf_full.joblib     # Dondurulmuş deneysel RF (v3/v2 kullanmıyor)
│
├── outputs/
│   └── {SKU}/                          # SKU başına tahmin artefaktları
│       ├── preds_Full_*.csv            #   plot_*.png, reorder_recommendation.json,
│       ├── preds_Full_*_REFIT.csv      #   test_summary_ALL*.csv, …
│       ├── test_summary_ALL.csv
│       ├── test_summary_ALL_REFIT.csv
│       ├── reorder_recommendation.json
│       ├── plot_full_*.png
│       └── plot_3m_*.png
│
├── v7_full/
│   ├── forecasts/                      # v7 notebook çıktıları (düz format)
│   └── plots/
│
├── mnt/data/                           # Colab/bulut bağlama aynaları
│   ├── panel_sales_orders_stock.csv
│   ├── sku_config.csv
│   ├── v7_per_sku_outputs/
│   └── v7_select/
│
├── logs/
├── .idea/                              # JetBrains (yok say)
├── __MACOSX/                           # macOS zip artığı (yok say)
└── Archive.zip                         # (yok say)
```

**Kök dizinde düzinelerce arşiv Jupyter notebook** (Faz 1–4; bkz. §5) bulunmaktadır. Tek bir SKU deneyinden (`303-104092`) başlayarak dışsal topluluk keşfi, NNLS karıştırma, çoklu-SKU paralelleştirme, REFIT rollback ve kesintili talep işleme evrimini belgeliyorlar. Artık `scripts/model_v3.py` + `Sales Forecast v7_full.ipynb` tarafından yerine geçilmişlerdir ve context penceresini temiz tutmak için `.claudeignore` ile hariç tutulurlar.

---

## 4. Birincil Modül: `scripts/model_v3.py`

`scripts/model_v3.py` kanonik üretim giriş noktasıdır. `python scripts/model_v3.py` ile çalıştırıldığında `panel_sales_orders_stock.csv`'deki her SKU için tahmin + sipariş önerisi üretir.

### 4.1 Üst seviye yerleşim

| Satırlar | Bölüm |
|---|---|
| 1–155 | Modül docstring, import'lar, global yapılandırma sabitleri |
| 160–237 | Yardımcı araçlar (`ensure_ms_freq`, `add_calendar`, `build_lags_y`, `prep_features_y`, metrik yardımcıları) |
| 239–268 | Baseline tahminciler (`seasonal_naive_forecast`, `ma3_forecast`, `baseline_val_mae`) |
| 270–476 | EXOG model katmanı (Prophet / SARIMA / ETS fit & forecast; `build_exog_univar`, `build_exog_inverse`, `build_exog_ml`) |
| 477–584 | NNLS stacking (`project_simplex`, `nnls_ridge`, `nnls_ridge_weighted`, `nnls_adapt`, `fit_nnls_weights_on_val`) |
| 586–658 | Kesintili talep (`select_intermittent`, `croston_forecast`, `sba_forecast`, `tsb_forecast`, `predict_intermittent`) |
| 660–706 | Y-model ROCV (`rolling_origin_splits`, `optimize_rf_rocv`, `optimize_xgb_rocv`) |
| 708–728 | `recursive_forward_predict_y` — özyinelemeli Y tahmin döngüsü |
| 730–803 | Bootstrap PI + stockout + MOQ yuvarlama (`add_bootstrap_intervals`, `stockout_probability`, `cum_demand_quantile`, `round_moq_lot`) |
| 805–835 | Y-ensemble ağırlıkları + REFIT (`y_ensemble_weights`, `refit_models_on_full`) |
| 838–960 | Değişken bazlı EXOG seçimi — `choose_best_exog_per_var`, `build_hybrid_exog` (⚠ ölü refactoring enkazı içerir; bkz §8) |
| 963–979 | `choose_methods_for_sku` (tanımlı ama kullanılmıyor; ölü kod) |
| 982–1312 | **`run_for_sku`** — SKU başına ana orkestratör |
| 1314–1335 | `load_params` |
| 1338–1344 | `_run_worker` — paralel sarıcı |
| 1347–1412 | **`main`** — panel yükleme, SKU groupby, dispatch, özet |

### 4.2 SKU başına pipeline (`run_for_sku`)

```
 1. Veri hazırlığı       ensure_ms_freq, prep_features_y      (lag'ler, takvim, winsorize)
 2. Y model ROCV         optimize_rf_rocv, optimize_xgb_rocv  (3-fold rolling-origin CV)
 3. VAL üzerinde Probe   _build_exog_by_method                (ucuz adaylar: ETS, Intermittent, ML-Exog RF)
 4. Gerekirse Escalate   baseline_val_mae kontrolü            (probe < seasonal naive + %2 ise XGB + Prophet eklenir)
 5. Değişken bazlı hibrit choose_best_exog_per_var            (`orders` için en iyi yöntem ⨯ `stock` için en iyi)
 6. Test EXOG oluştur    build_exog_*                         (TEST_END / TEST_END_SHORT'a ileri yansıtma)
 7. TEST değerl. (PRE)   recursive_forward_predict_y,         (özyinelemeli tahmin + Laplace bootstrap PI +
                         add_bootstrap_intervals,              stoksuz kalma olasılığı + E[T])
                         stockout_probability
 8. REFIT                refit_models_on_full                 (train+val üzerinde yeniden eğit; kötüyse rollback)
 9. OMS sipariş poltk.   stockout_probability,                (order = max(0, cumDemand(H, q) - startStock),
                         cum_demand_quantile, round_moq_lot    MOQ + lot'a yuvarlanır)
10. Çıktı                varyant başına CSV, reorder JSON     (outputs/{SKU}/ altına yazar)
```

### 4.3 Paralellik

Çift modlu çalıştırma:

- **CLI (`python scripts/model_v3.py`)** — `ProcessPoolExecutor(mp.get_context("spawn"))`, worker başına bir SKU, `MAX_WORKERS = int(cpu_count * 0.75)`.
- **Jupyter / interaktif** — `IS_INTERACTIVE` bayrağı ile tespit, `ThreadPoolExecutor`'a düşer (spawn notebook yeniden yüklemelerinde hayatta kalmıyor).
- v3'te `PARALLEL_SKU = False` varsayılan (v2/OMS'de açık) — en güncel iterasyon varsayılan olarak seri çalışır, paralellik açıkça devreye alınır.

---

## 5. Notebook Evrimi (Faz 1–5)

| Faz | Tema | Temsili notebook'lar |
|---|---|---|
| 1 | Tek SKU EDA + baseline (`303-104092`) | `motul_data_analysis.ipynb`, `veri hazırlama.ipynb`, `303-104092-3-Model.ipynb`, `303-104092-Probhet-XGBoost-Hybrid*.ipynb` |
| 2 | Dışsal topluluk keşfi | `Auto-Exog Forecast*.ipynb`, `3 Exog Strategy*.ipynb`, `Exog Ensemble Tuning + Sızıntısız-Kausal + PI.ipynb` |
| 3 | OMS entegrasyonu + senaryolar | `Sales Forecast v2–v6.1 — OMS Edition*.ipynb` |
| 4 | Çoklu-SKU paralelleştirme + REFIT + kesintili | `Sales Forecast V6_multi_sku*.ipynb`, `v6_multi_sku.py — OMS Edition*.ipynb` |
| 5 | **Güncel** — v7 tam üretim çalıştırması | `Sales Forecast v7_full.ipynb` (en son) |

Faz 1–4 arşivsel. Canlı artefaktlar: `scripts/model_v3.py`, `scripts/OMS.py` ve `Sales Forecast v7_full.ipynb`.

---

## 6. Veri Şemaları

### `panel_sales_orders_stock.csv`

| Sütun | Tip | Açıklama |
|---|---|---|
| `ds` | date | Ayın ilk günü timestamp (MS frekansı) |
| `sku` | string | Ürün kodu (örn. `303-104092`) |
| `y` | float | Gerçekleşen aylık satış (adet) |
| `orders` | float | O ayda verilen gelen satın alma siparişleri |
| `stock` | int | Ay sonu eldeki stok |

### `sku_config.csv`

| Sütun | Açıklama |
|---|---|
| `sku` | Ürün kodu |
| `T_CHECK` | Ay bazında inceleme döngüsü; `E[T_stockout] ≤ T_CHECK` ise sipariş tetiklenir |
| `H_COVER` | Kapsam ufku — siparişin kaç aylık talebi karşılayacağı |
| `q_target` | Kümülatif talep üzerinde servis seviyesi kuantili (örn. 0.5 = medyan) |
| `lead_time_mo` | Ay cinsinden tedarikçi teslim süresi |
| `MOQ` | Minimum sipariş miktarı (0 = minimum yok) |
| `lot_size` | Yuvarlama granülarisi (1 = birim, aksi halde en yakın lot'a yukarı yuvarla) |

### `outputs/{SKU}/` artefakt isimlendirme

`preds_{Horizon}_{EnsembleMethod}_{YVariant}[_REFIT].csv`

- **Horizon** — `Full` (6 aylık pencere) veya `Short3` (3 aylık pencere, grafik isimlerinde `3m` olarak da görülür)
- **EnsembleMethod** — EXOG regresörlerinin ileri nasıl tahmin edildiği. Örnekler: `Adaptive5-NNLS-w3` (5 temel model × 3-dönemlik pencere üzerinde NNLS ağırlıkları), `Top3-NNLS-Ridge`, `All-5-INV` (inverse-MAE), `Ensemble` (basit ortalama), `ML-Exog_XGB`, `Prophet`, `SARIMA`, `ETS`, `Intermittent` (Croston/SBA/TSB)
- **YVariant** — özyinelemeli tahmin için kullanılan Y-modeli: `RF`, `XGB` veya `Y-ENS` (RF + XGB'nin NNLS karışımı)
- **`_REFIT` son eki** — modeller train + val üzerinde yeniden eğitildikten sonraki tahminler (PRE-REFIT sonucundan kötü değilse korunur)

Tahmin CSV sütunları: `ds, yhat, pi80_lo, pi80_hi, pi95_lo, pi95_hi`.

`reorder_recommendation.json` — SKU başına terminal çıktı. Seçilen kombinasyonu, başlangıç stoğunu, `P(stockout ≤ 3m)`, `P(stockout ≤ 6m)`, `E[T_stockout]`, kümülatif talep kuantilini ve final `order_qty_rounded` değerini içerir.

---

## 7. Mimari Diyagram (Veri Akışı)

```
                     ┌────────────────────┐
                     │   motul_data.csv   │  (ham işlemler)
                     └─────────┬──────────┘
                               │ veri hazırlama.ipynb
                               ▼
                ┌──────────────────────────────┐
                │ panel_sales_orders_stock.csv │  (temizlenmiş aylık panel)
                └──────────────┬───────────────┘
                               │
                               ▼
   ┌──────────────────────────────────────────────────────────┐
   │              scripts/model_v3.py :: main                 │
   │                                                          │
   │   her SKU için (paralel opsiyonel):                      │
   │       run_for_sku(sku_df, sku_params)                    │
   │           │                                              │
   │           ├── prep_features_y           (lag, takvim)    │
   │           │                                              │
   │           ├── optimize_rf_rocv  ──┐                      │
   │           ├── optimize_xgb_rocv ──┴── ROCV grid search   │
   │           │                                              │
   │           ├── EXOG probe (ETS, IM, ML-Exog-RF)           │
   │           │      └── escalate → zayıfsa +XGB +Prophet    │
   │           │                                              │
   │           ├── choose_best_exog_per_var   (orders, stock) │
   │           │                                              │
   │           ├── build_hybrid_exog                          │
   │           │                                              │
   │           ├── recursive_forward_predict_y                │
   │           │      └── add_bootstrap_intervals (Laplace)   │
   │           │                                              │
   │           ├── refit_models_on_full  (+ rollback)         │
   │           │                                              │
   │           ├── stockout_probability, cum_demand_quantile  │
   │           │                                              │
   │           └── round_moq_lot  → reorder_recommendation    │
   └───────────────────────────┬──────────────────────────────┘
                               │
                               ▼
            ┌──────────────────────────────────┐
            │          outputs/{SKU}/          │
            │                                  │
            │  preds_*.csv  (PI sütunları ile) │
            │  preds_*_REFIT.csv               │
            │  test_summary_ALL.csv            │
            │  test_summary_ALL_REFIT.csv      │
            │  reorder_recommendation.json     │
            │  plot_full_*.png, plot_3m_*.png  │
            └──────────────────────────────────┘
                               │
                               ▼
                ┌──────────────────────────┐
                │ outputs/_SUMMARY/        │
                │  test_summary_ALL_SKUs.csv│
                └──────────────────────────┘
```

---

## 8. Desenler, Anti-desenler, Notlar

**Yük taşıyan tasarım kararları:**
- **Özyinelemeli Y tahmini.** Doğrudan çoklu-adım (bir kerede T+6) yerine, `recursive_forward_predict_y` her T+1 tahminini T+2 için lag feature'larına geri besler. Zaman serisi semantiğine daha sadık ama ilk adım yanlışsa hata birikir.
- **`time_decay` ile NNLS topluluk ağırlıkları.** Yakın doğrulama hataları uzak olanlardan daha fazla sayılır. `fit_nnls_weights_recent` son `REFIT_TAIL_K` ay üzerinde çalışır.
- **Değişken bazlı EXOG seçimi.** `orders` ve `stock` bağımsız tahmin edilir — orders için en iyi yöntem ailesi stock için en iyi olandan farklı olabilir; naif birleştirme bunu gizler.
- **Probe → Escalate.** Önce ucuz EXOG yöntemleri çalışır; ağır yöntemler (Prophet, XGB-Exog) sadece ucuz yöntemler `seasonal_naive + DELTA_BETTER_THAN_BASELINE` eşiğini geçemezse devreye girer. Hız optimizasyonu, kalite fedakarlığı değil.
- **Kesintili kapısı.** Yüksek sıfır oranlı / yüksek ADI SKU'lar sürekli modeller yerine Croston/SBA/TSB'ye geçer. `select_intermittent` içinde sıfır-oranı + ADI eşikleriyle tetiklenir.
- **Bootstrap PI > parametrik CI.** `add_bootstrap_intervals` tek bir nokta tahmini yerine stoksuz kalma olasılığı hesaplamasını besleyen kalibre edilmiş %80/%95 aralıkları üretir.
- **REFIT + rollback.** İlk eğitim/değerlendirme ayrımından sonra modeller train + val üzerinde yeniden eğitilir. Refit sonucu pre-refit sonucundan (test penceresi üzerinde ölçülerek) *daha kötüyse*, pre-refit sonucu saklanır. Yakın dönem gürültüye overfit etmeyi önler.

**Bilinen kod-sağlık sorunları (refaktör etmeden önce araştır):**
- ⚠ `val_mae_exog_for_col` `scripts/model_v3.py` içinde **iki kez tanımlı** (satır 899 ve 909). İlki gölgelenmiş ve ölü. Satır 848–897 arasında önceki 5 bozuk refactoring denemesi (`_val_mae_exog_col`, `_val_mae_col_clean`, …) ölü kod olarak bırakılmış. Sadece satır 909'daki son tanım doğru çalışıyor, ama bu blok dosyadaki ana okunabilirlik tehlikesi.
- ⚠ `choose_methods_for_sku` (satır 964) asla çağrılmıyor — `run_for_sku` mantığı inline olarak içerir.
- ⚠ `scripts/model_v2.py` ve `scripts/model_v3.py` neredeyse ikiz — sadece ~10 config sabitinde farklılar (`B_BOOT`, `ADAPT_WINS`, `ENABLE_TIME_DECAY_NNLS`, `IM_METHODS`, `FAST_MODE`, `PARALLEL_SKU`). v3, v2'nin hız-budanmış varyantı. Herhangi bir mantık düzeltmesi her iki dosyaya elle uygulanmalı.
- ⚠ `scripts/OMS.py`'deki `ENABLE_INV_ENSEMBLES` / `ENABLE_NNLS_ENSEMBLES` bayrakları (varsayılan False) sadece dosya çıktısını kontrol eder, hesaplamayı değil — 846–876 satırlarındaki adaptif NNLS bloğu koşulsuz çalışır, CPU'yu boşa harcar.
- ⚠ Faz 1–4'ten gelen Jupyter notebook'lar (düzinelerce dosya) repo kökünde commit edilmiş ve çok üst üste — gelecekteki bir temizlik geçişinde `archive/` alt klasörüne arşivlemeyi düşün.

---

## 9. Giriş Noktaları Özeti

| Amaç | Dosya | Komut |
|---|---|---|
| Tüm SKU'lar için pipeline'ı çalıştır | `scripts/model_v3.py` | `python scripts/model_v3.py` |
| Referans uygulama (Probe/Escalate'siz) | `scripts/OMS.py` | `python scripts/OMS.py` |
| Araştırma / tez anlatımı | `Sales Forecast v7_full.ipynb` | Jupyter'da aç |
| Paneli ham veriden yeniden oluştur | `veri hazırlama.ipynb` | Jupyter'da aç |

---

## 10. Kodu Nereden Okumaya Başlamalı

Önem sırasıyla:

1. `scripts/model_v3.py:983` — `run_for_sku` (ana pipeline)
2. `scripts/model_v3.py:709` — `recursive_forward_predict_y` (Y tahmin döngüsü)
3. `scripts/model_v3.py:731` — `add_bootstrap_intervals` (PI oluşturma)
4. `scripts/model_v3.py:909` — `val_mae_exog_for_col` (ikinci, canlı tanım)
5. `scripts/model_v3.py:928` — `choose_best_exog_per_var` (değişken bazlı hibrit)
6. `scripts/model_v3.py:676` — `optimize_rf_rocv` (ROCV grid search)
7. `scripts/model_v3.py:441` — `fit_nnls_weights_on_val` (stacking ağırlıkları)
8. `scripts/model_v3.py:586` — `select_intermittent` (seyrek/yoğun yönlendirme)
9. `scripts/model_v3.py:1347` — `main` (panel yükleme + paralel dispatch)
10. `scripts/OMS.py:715` — Probe→Escalate'siz referans `run_for_sku` (yeni yönlendirmenin neyin yerini aldığını anlamak için v3 ile karşılaştır)
