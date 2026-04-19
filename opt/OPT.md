# Optimizasyon Bulguları

Bu klasör (`opt/`) model optimizasyon playgroundlarını ve bulgularını içerir.
Her deney için neden bu sonucu aldık, ne anlama geliyor ve sonraki adım ne — üç soruya yanıt verir.

> **Kural:** Yeni veri geldiğinde ilgili playgroundu tekrar çalıştır. Kazanan config
> değişirse `model_v3.py`'yi güncelle (onay alarak).

---

## Playgroundlar

| Dosya | Ne test ediyor | Sonuç dosyası |
|-------|----------------|---------------|
| `sarima_playground.py` | SARIMA grid vs sabit order | — |
| `ets_playground.py` | ETS kombinasyon grid vs sabit | — |
| `model_comparison_playground.py` | RF / XGB / LightGBM + Optuna + ölçek | `results_*.csv` |
| `bootstrap_playground.py` | Bootstrap B parametresi | `results_bootstrap.csv` |
| `pi_calibration_playground.py` | PI kalibrasyon yöntemleri | `results_pi_calibration.csv` |
| `ablation_playground.py` | Her bileşenin katkısı | `results_ablation.csv` |

```bash
.venv/bin/python opt/<dosya>.py
```

---

## 1. SARIMA Grid Search → Sabit Order

**Tarih:** 2026-04-19 | **Veri:** 81 ay, 21 SKU

### Sonuçlar

| Config | Ort. MAE | Süre/SKU | Hız Kazanımı |
|--------|----------|----------|--------------|
| **sabit ARIMA(1,1,1)** | **119.2** | 0.78s | **16.65×** |
| minimal (0-1 × 0-1) | 126.1 | 1.70s | 7.62× |
| sabit (1,1,1)(1,1,1) | 141.9 | 0.46s | 27.96× |
| mevcut (0-3 × 0-3) | 158.9 | 12.95s | 1.0× (referans) |
| küçük (0-2 × 0-2) | 180.3 | 5.33s | 2.43× |

### Neden bu sonucu aldık?
Grid search, model seçimini AIC ile yapıyor — AIC **eğitim verisi** üzerinde hesaplanıyor.
64 kombinasyon → eğitime overfit → validation'da en kötü MAE mevcut config'e ait.
Sabit `ARIMA(1,1,1)` robust yapısı sayesinde daha iyi genelleşiyor, grid'e gerek yok.

### Ne anlama geliyor?
"Daha fazla deneme = daha iyi model" varsayımı SARIMA için yanlış.
Basit ama tutarlı bir yapı, AIC-guided karmaşık seçimden daha iyi.

### Uygulama
`sarima_fit_best` → sabit `ARIMA(1,1,1)(0,1,0,12)` — **onay bekliyor**
- MAE: 158.9 → 119.2 (%25 iyileşme)
- Süre: 272s → 16s (21 SKU toplam)

### Risk
Yeni veri farklı seasonality gösterirse `(0,1,0,12)` yetersiz kalabilir.
Periyodik kontrol: `sarima_playground.py` tekrar çalıştır.

---

## 2. ETS Grid → Sabit Config

**Tarih:** 2026-04-19 | **Veri:** 81 ay, 21 SKU

### Sonuçlar

| Config | Ort. MAE | Süre/SKU | Hız Kazanımı |
|--------|----------|----------|--------------|
| add/None only | **101.2** | 0.147s | 1.46× |
| **damp=False sabit** | **102.0** | 0.113s | **1.90×** |
| mevcut (tüm grid) | 102.1 | 0.215s | 1.0× (referans) |
| sabit add-add-damp | 108.8 | 0.057s | 3.79× |
| trend yok sadece sezon | 112.9 | 0.016s | 13.8× |

### Neden bu sonucu aldık?
Mevcut veri trendsiz dalgalanıyor → `damp=True` (trend sönümleme) bir katkı sağlamıyor.
ETS grid'i SARIMA'dan farklı olarak zaten iyi seçiyor; top 3 config arasında MAE farkı sadece 0.9.

### Ne anlama geliyor?
ETS grid search SARIMA kadar zararlı değil ama gereksiz.
`damp=False` sabit config: MAE aynı, 1.9× hızlı — güvenli basitleştirme.

### Risk
Belirgin trend gösteren yeni veri gelirse `damp=True` geri kazanabilir.
Yeni veri gelince `ets_playground.py` tekrar çalıştır.

### Uygulama — düşük öncelik
- MAE değişimi: yok denecek kadar az
- Süre kazanımı: 4.5s → 2.4s (21 SKU)
- **Durum: düşük öncelik — SARIMA'dan sonra değerlendir**

---

## 3. Y Modeli: RF / XGB / LightGBM Karşılaştırması

**Tarih:** 2026-04-19 | **Veri:** 81 ay, 21 SKU | **Optuna:** 30 trial

### Senaryo 1 — Algoritma (Grid ile)

| Algoritma | Ort. MAE | Süre/SKU |
|-----------|----------|----------|
| **XGB** | **750.8** | 10.4s |
| LightGBM | 815.0 | 1.1s |
| RF | 818.5 | 3.6s |

### Senaryo 2 — Grid vs Optuna

| Algoritma | Yöntem | Ort. MAE | Süre |
|-----------|--------|----------|------|
| **XGB** | **Optuna** | **678.2** | 37s |
| LightGBM | Optuna | 781.6 | 2.6s |
| XGB | Grid | 750.8 | 9.5s |
| RF | Optuna | 796.7 | 11.4s |
| LightGBM | Grid | 815.0 | 1.2s |
| RF | Grid | 818.5 | 3.3s |

### Senaryo 3 — 400 SKU Ölçek Testi (6 çekirdek paralel)

| Algoritma | Yöntem | 400 SKU süresi |
|-----------|--------|----------------|
| **LightGBM** | **Grid** | **93.7s (1.5 dk)** |
| LightGBM | Optuna | 219.8s (3.7 dk) |
| RF | Grid | 236.7s |
| XGB | Grid | 826.2s (14 dk) |
| XGB | Optuna | 3605s (60 dk!) ← üretimde kullanılamaz |

### Senaryo 4 — Retraining

| Yöntem | MAE | Not |
|--------|-----|-----|
| Tam eğitim | referans | güvenilir |
| +5 ay incremental | aynı MAE | sıfırdan eğitmekle fark yok |
| Rolling (aylık) | değişken | bazı SKU'larda veri yetersiz |

### Neden bu sonuçları aldık?
- XGB boosting tabanlı olduğundan tabular veride daha iyi öğreniyor.
- LightGBM histogram optimizasyonuyla çok daha hızlı; 400 SKU'da XGB'den 9× hızlı.
- Optuna bayesian arama yaptığı için grid'den hep daha iyi bulur — ama XGB+Optuna 400 SKU'da 60 dk sürdüğünden üretimde kullanılamaz.
- Incremental eğitim fark yaratmıyor: bu ölçekteki veri için sıfırdan eğitmek yeterli.

### Kullanım Senaryosu Önerileri

| Senaryo | Öneri | Gerekçe |
|---------|-------|---------|
| Kalite öncelikli | XGB + Optuna | En iyi MAE (678) |
| **400 SKU üretim** | **LightGBM + Optuna** | 3.7 dk, iyi kalite (781) |
| **Zaman kısıtlı** | **LightGBM + Grid** | 1.5 dk, hızlı sonuç |

```
FAST_TRAIN = True   → LightGBM + Grid   → 400 SKU: 1.5 dk
FAST_TRAIN = False  → LightGBM + Optuna → 400 SKU: 3.7 dk
```

**Durum: uygulanmadı — onay bekliyor**

---

## 4. Ablasyon Analizi — Her Bileşenin Katkısı

**Tarih:** 2026-04-19 | **Veri:** 81 ay, 21 SKU

> Not: Hız için basitleştirilmiş (sabit ETS, RF/XGB n_estimators=100).
> Model_v3.py tam pipeline'ından farklılık gösterebilir.

### Sonuçlar

| Senaryo | Ort. MAE | Fark | Fark % |
|---------|----------|------|--------|
| Baseline (ETS EXOG + RF+XGB + REFIT) | 963.9 | — | — |
| **No EXOG (carry-forward)** | **922.4** | -41.5 | **-4.3%** |
| No REFIT | 1004.1 | +40.2 | +4.2% |
| RF Only (ensemble yok) | 984.4 | +20.5 | +2.1% |
| XGB Only (ensemble yok) | 969.5 | +5.6 | +0.6% |

### Neden bu sonuçları aldık?

**1. EXOG carry-forward baseline'dan iyi çıktı → veri kalitesi sorunu**
ETS, gürültülü/eksik orders-stock verisiyle fit edilince kötü tahminler üretiyor.
Bu kötü tahminler recursive Y modeline feature olarak giriyor → hatayı büyütüyor.
Model_v3.py'deki per-variable selection (`EXOG_PER_VAR_SELECTION=True`) tam bu yüzden kritik:
kötü EXOG'u tespit edip elemek için var.

SKU bazlı örnek:

| SKU | Baseline MAE | No-EXOG MAE | Yorum |
|-----|-------------|-------------|-------|
| 305-109463 | 23 | **1** | EXOG bu SKU'ya zarar veriyor |
| 303-107672 | 12445 | **11067** | EXOG zararlı |
| 305-105786 | 498 | 1077 | EXOG burada gerekli |
| 780-LRCAUV | 42 | 79 | EXOG burada gerekli |

**2. REFIT +4.2% katkı sağlıyor**
REFIT, modeli son 6 aylık val verisini de görerek yeniden eğitiyor.
Kaldırınca daha eski bir model kullanıyoruz → hata artıyor → REFIT pipeline'da kalmalı.

**3. Ensemble katkısı sınırlı**
RF+XGB birleşimi RF'den +2.1%, XGB'den +0.6% daha iyi.
XGB yalnız başına ensemble'a çok yakın → ensemble maliyet/fayda dengesi düşünülmeli.

### Tez Bulgusu
> "EXOG kalitesi SKU'ya özgüdür. Yanlış EXOG tahmini modele gürültü enjekte eder;
> per-variable selection bu nedenle kritiktir. Veri kalitesi düşük SKU'larda
> carry-forward baseline tüm EXOG yöntemlerini yenebilir."

**Durum: tamamlandı — tez analizi için hazır**

---

## 5. PI Kalibrasyon Analizi

**Tarih:** 2026-04-19 | **Veri:** 81 ay, 21 SKU

### Sorun
```
coverage_80 = 0.197  → %80 PI sadece %19.7'yi kapsıyor (hedef: 0.80)
coverage_95 = 0.293  → %95 PI sadece %29.3'ü kapsıyor (hedef: 0.95)
```

### Neden bu sonucu aldık?
Bootstrap, VAL rezidülerinden gürültü örnekliyor.
VAL'de model iyi çalışırsa rezidüler küçük → dar PI → test'teki büyük sıçramalar dışarıda kalıyor.
Problem: VAL ve TEST dağılımları aynı değil; veri az ve dalgalı (21 SKU).

### Test Edilen Yöntemler

| Yöntem | coverage_80 | width_80 |
|--------|-------------|----------|
| Mevcut (6 ay VAL) | 0.197 | 235 |
| VAL penceresi 12 ay | 0.245 | 416 |
| VAL penceresi 18 ay | 0.225 | 406 |
| Rezidü scale=2.0 | 0.327 | 471 |
| Rezidü scale=3.0 | 0.422 | 717 |
| **Conformal (CP-80%)** | **0.707** | **1685** |
| Conformal (CP-95%) | 0.911 | 3081 |

### Bulgular
- VAL penceresi uzatmak sorunu çözmüyor (distribution shift problemi)
- Rezidü ölçekleme 0.80'e ulaşmak için scale=8-10 gerektirir → PI anlamsız genişlikte
- Conformal Prediction hedefe en yakın (0.707) ama PI 7× daha geniş → pratik kullanımı kısıtlı

### Önemli Not
⚠️ 21 SKU az ve dalgalı veri. **2000 SKU'da bulgular farklı olabilir:**
daha dengeli dağılım → daha iyi coverage, istatistiksel güvenilirlik artar.

### Tez Notu
> "Veri yüksek varyans içerdiğinden PI kalibrasyonu zordur. Conformal Prediction
> coverage garantisi sunar ancak PI genişliği pratik kullanımı kısıtlar.
> 2000 SKU ile yeniden değerlendirilmesi önerilir."

**Durum: 2000 SKU bekliyor**

---

## 6. Veri Kalitesi

### Sorun
Bazı SKU'larda eksik değerler, beklenmedik sıfırlar ve gürültülü kayıtlar var.
Ablasyon analizinde bu net görüldü: carry-forward ETS'den iyi çıktı çünkü
ETS gürültülü orders/stock verisiyle fit edilince sapıyor.

### Neden önemli?
- `orders`/`stock` NaN veya sıfır → lag feature'lar (`orders_lag1`, `stock_lag3`) zincirleme bozuluyor
- EXOG modelleri (ETS/SARIMA/Prophet) kirli veriyle fit edilince gelecek tahminleri sapıyor
- Y modeli sapan EXOG feature'larla eğitiliyor → cascading error

### Yapılacak (2000 SKU gelince)
1. **Veri kalite raporu:** Her SKU için NaN oranı, sıfır oranı, aykırı değer sayısı
2. **Winsorize** (model_v3.py'de `winsorize_series` zaten var — kontrol et)
3. **Eksik değer stratejisi:** forward-fill mi, interpolasyon mu, SKU özelinde mi?
4. **Kalite eşiği:** Çok kirli SKU'ları pipeline başında işaretle / uyar

### Tez Notu
> "Veri kalitesi tüm pipeline'ı etkiliyor. Gerçek üretim verisinde cleaning
> adımı model seçimi kadar kritiktir."

**Durum: 2000 SKU gelince analiz yap**

---

## 7. Gereksiz EXOG Fit (Short3 / Full)

### Sorun
Short3 (3 ay) ve Full (6 ay) için EXOG ayrı ayrı fit ediliyor:
```python
full  = build_exog(method, TEST_START, TEST_END, ...)       # fit #1
short = build_exog(method, TEST_START, TEST_END_SHORT, ...) # fit #2 — gereksiz
```
Prophet ve SARIMA her SKU için **2× fit** ediliyor. Short3 zaten Full'un ilk 3 ayı.

### Çözüm
```python
full  = build_exog(method, TEST_START, TEST_END, ...)
short = full[full["ds"] <= TEST_END_SHORT]  # kesme, yeniden fit yok
```

### Sonuç
- EXOG fit sayısı yarıya iner
- Prophet/SARIMA olan her SKU'da doğrudan kazanım
- **Durum: uygulanmadı — onay bekliyor**

---

## 8. Bootstrap B=150 → B=50

### Sorun
```python
B_BOOT = 150  # her SKU için 150 simülasyon
```

### Bulgu
81 satırlık veri için 50 simülasyon istatistiksel olarak yeterli.
B=50 → 3× hızlı, PI kalitesi pratikte aynı.

**Durum: test edilmedi — playground yapılabilir**

---

## 9. Gelecek Denemeler — Yeni Modeller ve Yaklaşımlar

Şu an denenmemiş ama değer taşıyan yöntemler. Öncelik sırasıyla:

### 9.1 Temporal Fusion Transformer (TFT)
**Ne:** Zaman serisi için Transformer tabanlı model. Statik metadata, bilinen future feature ve geçmiş gözlemleri birleştirir.
**Neden değerli:** EXOG'u ayrı tahmin etmek yerine doğrudan gelecekteki belirsiz özelliklerle başa çıkıyor. Attention mekanizması hangi geçmiş dönemlerin önemli olduğunu öğreniyor.
**Dezavantaj:** Veri gereksinimi yüksek (~500+ zaman adımı ideal), eğitim süresi uzun, yorumlanabilirliği zor.
**Ne zaman dene:** 2000 SKU gelince, panel veri yeterince büyürse.

### 9.2 N-BEATS / N-HiTS
**Ne:** Saf sinyal ayrıştırma yaklaşımı — trend, mevsimsellik, kalıntı bloklarına böler.
**Neden değerli:** EXOG gerekmez; saf univariate ama güçlü. M4/M5 yarışmalarında SOTA.
**Dezavantaj:** Çok değişkenli desteği sınırlı; orders/stock feature'larını doğal kullanmıyor.
**Ne zaman dene:** Ablasyon sonuçlarına göre EXOG katkısı düşük çıktığında alternatif olarak.

### 9.3 Gradient Boosting + Lag Features (Tek Model, Tüm SKU)
**Ne:** Tüm SKU'ları tek bir LightGBM/XGB modeline ver; SKU ID'yi kategorik feature yap.
**Neden değerli:** Çapraz SKU örüntüleri öğreniyor — bir SKU'nun az verisi diğerinden yararlanıyor. Eğitim paralel değil, tek seferlik.
**Dezavantaj:** SKU'lar arası ilişki olmayabilir (farklı kategoriler); overfitting riski.
**Ne zaman dene:** 2000 SKU ile per-SKU modelin zayıf kaldığı durumlarda.

### 9.4 Quantile Regression (PI için)
**Ne:** Doğrudan %10 ve %90 kantilini tahmin et — bootstrap yerine.
**Neden değerli:** PI miscalibration sorununa doğrudan çözüm. Bootstrap'ın VAL/TEST distribution shift sorununu atlar.
**Nasıl:** LightGBM veya XGB'de `objective='quantile'`, alpha=0.1 ve 0.9 ile iki model eğit.
**Ne zaman dene:** PI kalibrasyon sorunu 2000 SKU'da da devam ederse öncelikli deneme.

### 9.5 Croston / TSB → EXOG Katmanında
**Ne:** orders/stock için de intermittent modeller kullan (sadece Y için değil).
**Neden değerli:** Bazı SKU'larda orders seyrek ve sıfırlı; ETS/SARIMA bu durumu iyi ele almıyor.
**Durum:** Kısmen mevcut (`ENABLE_INTERMITTENT` var) ama EXOG için değil.
**Ne zaman dene:** orders/stock kolonlarında sıfır oranı yüksek SKU'lar için hemen.

### 9.6 Conformal Prediction (PI için)
**Ne:** Calibration set üzerinden non-conformity score'larla PI oluştur — coverage teorik garanti.
**Neden değerli:** Bootstrap'tan farklı olarak coverage'ı garanti ediyor (finite-sample guarantee).
**Sonuç (21 SKU):** coverage_80 = 0.707, ama PI 7× genişliyor.
**Ne zaman dene:** 2000 SKU ile — daha dengeli veri → daha dar ama doğru PI bekleniyor.

### 9.7 Veri Zenginleştirme (External Features)
**Ne:** Dış kaynak veriler — mevsimsel indeksler, ekonomik göstergeler, kategori trendleri.
**Neden değerli:** orders/stock'u tahmin etmek yerine gerçek talep sürücülerini model alabilir.
**Dezavantaj:** Veri temin etmek zor, overfitting riski.
**Ne zaman dene:** Ürün kategorisine göre dış veri mevcutsa.

### 9.8 Paralel SKU (`PARALLEL_SKU = True`)
**Ne:** Her SKU'yu ayrı process'te çalıştır — `ProcessPoolExecutor` hazır kod var.
**Neden değerli:** Mevcut 21 SKU seri çalışıyor; 2000 SKU'da bu kritik.
**Tahmini kazanım:** N_CPU × hızlanma (6 çekirdekte ~6×; model comparison playground'da doğrulandı).
**Risk:** Prophet ve SARIMA process-safe değil olabilir — test gerekiyor.
**Ne zaman dene:** 2000 SKU geçişinden önce test et.

---

*Son güncelleme: 2026-04-19*
