# CLAUDE.md (Türkçe)

> Bu dosya, kök dizindeki İngilizce [`CLAUDE.md`](../CLAUDE.md) dosyasının Türkçe referans çevirisidir. Claude Code aslında kök dizindeki İngilizce versiyonu otomatik yükler; bu dosya sadece insan okuyucular için saklanır.

Bu repoda çalışırken Claude Code için çalışma notları. Tam mimari anlatımı için önce [`PROJECT_OVERVIEW_TR.md`](PROJECT_OVERVIEW_TR.md) dosyasını oku.

---

## Tek paragrafta proje

Türkçe bitirme tezi projesi. Motul benzeri bir yağ distribütörü için SKU bazlı aylık satış tahmini + otomatik satın alma sipariş önerisi. Kanonik üretim scripti `scripts/model_v3.py`; SKU başına 8-adımlı bir pipeline çalıştırır (feature hazırlığı → ROCV grid search → EXOG probe/escalate → değişken bazlı hibrit EXOG → özyinelemeli Y tahmini → bootstrap PI → REFIT rollback → MOQ-kısıtlı sipariş politikası). Girdi: `panel_sales_orders_stock.csv` + `sku_config.csv`. Çıktı: `outputs/{SKU}/preds_*.csv` + `reorder_recommendation.json`.

---

## Kanonik dosyalar (önce buralara bak)

| Dosya | Rol |
|---|---|
| `scripts/model_v3.py` | **Birincil üretim scripti.** En güncel, hız-budanmış. Giriş noktası: satır 1347'deki `main()`. |
| `scripts/model_v2.py` | v3'ün yakın ikizi — sadece ~10 config sabitinde farklı. Araştırma-ayarlı (yüksek B_BOOT, time-decay NNLS açık). |
| `scripts/OMS.py` | Önceki bağımsız pipeline. Probe→Escalate yok, değişken bazlı EXOG yok. Referans olarak tut, üretim olarak değil. |
| `Sales Forecast v7_full.ipynb` | En güncel araştırma notebook'u (v7). Yerini başkası almamış. |
| `panel_sales_orders_stock.csv` | Kanonik girdi paneli: `ds, sku, y, orders, stock`. |
| `sku_config.csv` | SKU bazlı politika: `T_CHECK, H_COVER, q_target, lead_time_mo, MOQ, lot_size`. |
| `proje_ozeti.md` | Türkçe tez özeti. |
| `docs/PROJECT_OVERVIEW.md` / `docs/PROJECT_OVERVIEW_TR.md` | Mühendislik odaklı mimari dokümanı (İng/TR). |

---

## Nereye BAKMA

Repo kökü, geliştirmenin Faz 1–4'ünden **düzinelerce arşiv Jupyter notebook** içerir (`303-104092` üzerinde tek-SKU deneyleri, Auto-Exog keşifleri, Sales Forecast v2–v6 iterasyonları, `Untitled*.ipynb`). `scripts/model_v3.py` + `Sales Forecast v7_full.ipynb` tarafından yerine geçilmişlerdir. `.claudeignore` onları hariç tutar. Kullanıcı açıkça belirli bir notebook hakkında sormadığı sürece context'e yükleme.

Ayrıca hariç tutulanlar:
- `outputs/` — türetilmiş SKU başına tahmin artefaktları (binlerce CSV + PNG)
- `v7_full/`, `mnt/data/v7_*` — daha fazla türetilmiş çıktı
- `serialized_models/*.joblib` — ikili model dosyaları
- `motul_data.csv`, `veri_matrisi_final_*.csv` — büyük ham/ara veri
- `__MACOSX/`, `.DS_Store`, `.idea/`, `Archive.zip`, `.ipynb_checkpoints/`

---

## Pipeline zihinsel modeli

```
ham → panel_sales_orders_stock.csv → [SKU başına model_v3.run_for_sku] → outputs/{SKU}/
                                                │
                                                └── reorder_recommendation.json
```

`run_for_sku` içinde (`scripts/model_v3.py:983`):

1. `prep_features_y` — lag'ler (y_lag1, orders_lag1/3, stock_lag1/3), takvim, winsorize
2. `optimize_rf_rocv` + `optimize_xgb_rocv` — train+val üzerinde ROCV grid search
3. **EXOG probe** — ucuz adaylar (ETS, intermittent, ML-Exog-RF) VAL üzerinde puanlanır
4. **EXOG escalate** — probe < seasonal naive + %2 ise sadece XGB + Prophet ekle
5. `choose_best_exog_per_var` — her dışsal değişken (`orders`, `stock`) için en iyi yöntemi seç
6. `recursive_forward_predict_y` — özyinelemeli T+1 → T+2 → … tahmini
7. `add_bootstrap_intervals` — %80/95 PI için Laplace bootstrap
8. `refit_models_on_full` — train+val üzerinde yeniden eğit; **test MAE'si daha kötüyse rollback**
9. `stockout_probability` → `cum_demand_quantile` → `round_moq_lot` — OMS politikası
10. Kombinasyon başına CSV + `reorder_recommendation.json` + grafikleri yaz

---

## Yük taşıyan değişmezler (bozma)

- **Tarih frekansı ay-başıdır (`MS`)**. `ensure_ms_freq` bunu zorunlu kılar. Tarihe göre indekslenen her yeni feature bunu korumalı.
- **Özyinelemeli tahmin yalnızca nedensel lag feature'ları gerektirir.** `build_lags_y` içinde gelecek verisi yok. Burada nedenselliği bozmak, sahte düşük MAE elde etmenin bir numaralı yoludur.
- **NNLS ağırlıkları negatif değildir ve simpleks üzerine projekte edilir.** `project_simplex` + `nnls_ridge`. Kısıtsız en küçük kareler ile değiştirme.
- **REFIT rollback muhafazakârdır.** `ref_best > pre_best` ise → PRE'yi koru. Karşılaştırmayı ters çevirme.
- **`panel_sales_orders_stock.csv` iki yerde bulunur** — repo kökü ve `mnt/data/`. Paneli yeniden oluşturursan senkronize tut.
- **`scripts/model_v2.py` ve `scripts/model_v3.py` serbest driftleniyor.** Birindeki bir bug fix diğerine yayılmaz — her iki dosyaya da fix uygula veya hangisinin otoriter olduğunu kullanıcıya sor.

---

## Bilinen kod-sağlık sorunları

(Sessizce temizleme — önce kullanıcıya bildir.)

- **`val_mae_exog_for_col` iki kez tanımlı** `scripts/model_v3.py` içinde (satır 899 ve 909). İlki ölü. Satır 848–897 arası ölü kod olarak bırakılmış bozuk refactoring denemeleri. Sadece 909'daki versiyon çalışır.
- **`choose_methods_for_sku`** (`scripts/model_v3.py:964`) asla çağrılmıyor. `run_for_sku` mantığı inline yapıyor.
- **v2 ve v3 neredeyse ikiz**. Değişiklikler her iki dosyaya manuel uygulanmalı.
- **scripts/OMS.py'deki `ENABLE_*_ENSEMBLES` bayrakları sadece dosya çıktısını kontrol eder**, hesaplamayı değil. Bayraklar `False` olsa bile pahalı döngüler çalışır.

---

## Yaygın görevler

### "Tüm SKU'lar için tahmin çalıştır"
```
python scripts/model_v3.py
```
Çıktılar `outputs/{SKU}/` altına düşer.

### "Pipeline'a yeni SKU ekle"
1. `panel_sales_orders_stock.csv`'ye satırlar ekle (ve `mnt/data/panel_sales_orders_stock.csv`'ye de)
2. `sku_config.csv`'ye MOQ, lot size, H_COVER, q_target ile bir satır ekle
3. `python scripts/model_v3.py` tekrar çalıştır

### "Tahmin ufkunu veya test penceresini değiştir"
`scripts/model_v3.py`'nin başındaki sabitler (satır 1–155): `TEST_START`, `TEST_END`, `TEST_END_SHORT`, `H_COVER` (SKU başına `sku_config.csv` ile override edilir).

### "Hız için ayarla"
v3 config bloğunda `FAST_MODE`, `B_BOOT`, `ADAPT_WINS`, `IM_METHODS`. v3 zaten v2'ye göre hız-budanmış; daha fazla budama v3 üzerinden yapılmalı.

### "Yeni bir EXOG tahmin yöntemi ekle"
1. `scripts/model_v3.py:270–476` içindeki `build_exog_univar` imzasını yansıtarak `build_exog_<name>` uygula
2. `_build_exog_by_method` içine kaydet (~satır 838)
3. İsmi `PROBE_METHODS` veya `ESCALATE_METHODS`'a ekle
4. Yeni yöntem değişken bazlı rekabet etmeliyse `choose_best_exog_per_var`'ı güncelle

---

## Bu repo için stil tercihleri

- **Mevcut Python stilini eşleştir.** Type annotation yok, dataclass yok, ağır modül seviyesi config sabitleri kullanımı, alt çizgili fonksiyon isimleri, en alta `main()`.
- **Paket yapısı ekleme** (`src/`, `__init__.py`, `setup.py`) istenmediği sürece. Bu bir tez reposu, kütüphane değil.
- **`requirements.txt` veya `pyproject.toml` ekleme** istenmediği sürece — import'ları incele ve kullanıcının yaptığı gibi ad-hoc `pip install` kullan.
- **Yeni modüller oluşturmak yerine `scripts/model_v3.py`'yi düzenlemeyi tercih et.** Kullanıcının zihinsel modeli "sürüm başına bir script".
- **Halihazırda bulunan Türkçe yorumları koru.** `proje_ozeti.md` ve inline yorumlar tasarım gereği çiftdillidir.
- **Dosyaları yeniden adlandırma veya arşiv notebook'ları taşıma** açık izin olmadan. Birçoğunun tez için referans değeri var.

---

## Kullanıcı bir soru sorduğunda

- "X nasıl çalışır" soruları için → önce `scripts/model_v3.py`'den oku (v2 değil, OMS değil, notebook'lar değil).
- Tez anlatımı / "neden böyle yaptık" soruları için → `proje_ozeti.md`'den oku.
- Geçmiş deneyler / "daha önce ne denedik" soruları için → kullanıcının sorduğu faza uyan notebook dosyasını oku; bir seferde sadece bir tane yükle, çok büyükler.
- Çıktı artefaktları hakkında sorular için → isimlendirme kuralı `preds_{Horizon}_{EnsembleMethod}_{YVariant}[_REFIT].csv`. Çözme tablosu için `PROJECT_OVERVIEW_TR.md` §6'ya bak.
