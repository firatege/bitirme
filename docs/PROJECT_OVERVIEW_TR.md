# Proje Genel Bakışı — Çoklu-SKU Satış Tahmini ve Sipariş Yönetim Sistemi

> Türkçe bitirme tezi projesi. Motul benzeri bir yağ distribütörü için SKU bazlı talep tahmini + otomatik satın alma sipariş önerisi sistemi. Tahmin çekirdeği: dışsal değişkenler için zaman serisi topluluğu (Prophet + SARIMA + ETS + Carry-Forward), hedef değişken için ağaç tabanlı topluluk (Random Forest + XGBoost), karıştırma için NNLS stacking, seyrek SKU'lar için kesintili talep modelleri (Croston / SBA / TSB), kalibre %80/%95 PI için bootstrap, MOQ/lot kısıtlı sipariş büyüklüğü. **Bu çekirdek, üretimde bir microservice yığını altında çalışır**: Rust controller + Python FastAPI worker + React dashboard + Postgres, hepsi Helm üzerinden tek-namespace k8s deployment.

Tez anlatımı için [`proje_ozeti.md`](../proje_ozeti.md), Claude Code çalışma notları için [`CLAUDE.md`](../CLAUDE.md). Bu dosya mühendislik bakışı: servis topolojisi, repo haritası, modül sorumlulukları, veri akışı, deployment, kod-sağlık notları.

---

## 1. Bu Proje Ne Yapıyor?

Aylık `(sku, ds, y, orders, stock)` paneli — gerçekleşen satışlar, gelen satın alma siparişleri, ay sonu stok — ve SKU bazlı politika dosyası `sku_config.csv` (MOQ, lot büyüklüğü, kapsam ufku, servis seviyesi kuantili, başlangıç stok override) verildiğinde sistem her SKU için iki soruya cevap üretir:

1. **Önümüzdeki 3 / 6 ayda ne kadar satacak?** — sadece nokta tahmini değil, %80 ve %95 tahmin aralıklı.
2. **Şu an kaç adet sipariş verilmeli, bu inceleme döneminde sipariş açılmalı mı?** — MOQ ve lot büyüklüğüne saygı göstererek, mevcut stoğa karşı stoksuz kalma olasılığı tarafından sürülerek.

Temel mantık: **talep stok tarafından sansürlendiğinde (censored demand)** naif satış tahmini yanıltıcıdır — geçen ay sıfır satan bir SKU'nun aslında yüksek talebi olup stoğu tükenmiş olabilir. Model bu sinyali geri kazanmak için stok ve gelen siparişleri dışsal regresör olarak kullanır. Ayrıca **dead-SKU bypass** (son 12 ayda satışı olmayan SKU'lar) ve **TSB override** (yüksek sıfır oranlı serilerde TSB'yi MAE yarışını atlatarak doğrudan kazanan ilan eder) gibi hızlı yollar mevcuttur.

---

## 2. Teknoloji Yığını

| Katman | Yığın |
|---|---|
| Controller (REST API + iş kuyruğu + dispatcher) | Rust 1.95, `actix-web 4`, `sqlx`, `tokio`, `tracing` |
| Worker (tahmin hesaplama servisi) | Python 3.11, `FastAPI`, `uvicorn`, `pydantic`, `structlog` |
| Tahmin modelleri | `pandas`, `numpy`, `scikit-learn` (RF), `xgboost`, `prophet`, `statsmodels` (SARIMAX, ETS), el-yazımı NNLS + Croston/SBA/TSB |
| Dashboard | React 18, TypeScript, Vite, TanStack Query/Table/Virtual, Recharts, Tailwind, Zustand, i18next |
| Veritabanı | Postgres 16 (`forecast_runs`, `forecast_jobs`, `sales_panel`, `sku_config`, `sku_run_*`, `sku_active_pin`) |
| Gözlem | Grafana (Postgres datasource, 4 dashboard: model-performance, portfolio-kpi, run-ops, stockout-calibration) |
| Konteynerleştirme | Docker multi-stage (cargo-chef Rust, nginx-served Vite SPA), `docker-compose.yml` lokal geliştirme için |
| Orkestrasyon | Kubernetes (k3s, Longhorn storage), nginx-ingress, cert-manager (`letsencrypt-prod`), CronJob ile gece otomatik eğitim |
| Paketleme | Tek generic Helm chart (`deploy/helm/`), per-servis values override |
| Build/Deploy araç akışı | `just` recipes (`justfile`), `deploy/scripts/{deploy,bootstrap}.sh` |

Lokal geliştirme için `docker-compose.yml` mevcut; üretim için `just deploy <service>` Helm chart üzerinden k8s'e push'lar.

---

## 3. Repo Yapısı

```
bitirme/
├── CLAUDE.md                       # Claude Code için çalışma notları
├── README.md
├── docker-compose.yml              # Lokal geliştirme yığını (postgres + api + controller + grafana + adminer)
├── docker-compose.test.yaml        # Test/CI yığını
├── justfile                        # build/push/deploy/seed/bootstrap recipes
├── pytest.ini
├── requirements.txt
│
├── docs/
│   ├── PROJECT_OVERVIEW.md         # İngilizce mühendislik dokümanı
│   ├── PROJECT_OVERVIEW_TR.md      # Bu dosya
│   └── CLAUDE_TR.md
│
├── controller/                     # Rust microservice — REST API + iş kuyruğu + worker dispatcher
│   ├── Cargo.toml
│   ├── migrations/                 # sqlx migration'ları (timestamp prefixed up/down çiftleri)
│   │   ├── 20260420120000_init_enums.{up,down}.sql
│   │   ├── 20260420120100_init_tables.{up,down}.sql
│   │   ├── 20260420120200_init_indexes.{up,down}.sql
│   │   ├── 20260512120000_sku_run_predictions.{up,down}.sql
│   │   ├── 20260512200000_sku_active_pin.{up,down}.sql
│   │   ├── 20260515120000_dead_sku_mode.{up,down}.sql
│   │   └── 20260515130000_zero_y_variant.{up,down}.sql
│   ├── src/
│   │   ├── main.rs                 # CLI: serve, migrate, seed, monthly-run, backfill-cached-spec
│   │   ├── server.rs               # actix-web rotaları
│   │   ├── orchestrator.rs         # cold/warm/dead dispatch, drift check
│   │   ├── queue.rs                # forecast_jobs claim/run/retry (FOR UPDATE SKIP LOCKED)
│   │   ├── api.rs                  # WorkerClient — Python api'ye HTTP istemci
│   │   ├── panel.rs                # CSV parser (sales_panel + sku_config seed)
│   │   ├── cached_spec.rs          # warm path için kazanan model spec'i serialize/load
│   │   ├── db.rs / types.rs / lib.rs
│   │   └── ...
│   └── tests/
│
├── services/worker/                # Python FastAPI tahmin servisi (model_v3.py'nin modülerize edilmiş hali)
│   ├── main.py                     # uvicorn entrypoint (services.worker.main:app)
│   ├── config.py                   # Tüm tunable'lar tek yerde (env override'lı)
│   ├── logging.py
│   ├── api/
│   │   ├── app.py                  # FastAPI app instance
│   │   └── routes/
│   │       ├── forecast.py         # POST /forecast/cold, /forecast/warm
│   │       ├── drift.py            # POST /drift/check
│   │       └── health.py           # GET /healthz, /readyz
│   ├── schemas/                    # pydantic request/response modelleri
│   │   ├── requests.py
│   │   └── responses.py
│   ├── features/                   # calendar, lags, winsorize, pipeline
│   ├── models/                     # exog_{ets,sarima,prophet,ml_rf,ml_xgb,carry_forward}, y_{rf,xgb}, intermittent, stacking
│   ├── selection/                  # rocv, y_search, baselines, probe_escalate, hybrid
│   ├── forecasting/                # exog, recursive, bootstrap, refit
│   ├── oms/                        # stockout, policy (MOQ + lot yuvarlama)
│   ├── pipelines/                  # cold.py, warm.py, drift.py — modülleri kompoze eder
│   └── io/blobs.py                 # joblib save/load yardımcıları
│
├── dashboard/                      # React + Vite + TypeScript SPA
│   ├── index.html
│   ├── package.json
│   ├── vite.config.ts
│   ├── public/
│   │   ├── sku_list.json           # build sırasında panel CSV'den üretilir
│   │   ├── supplier_map.json
│   │   └── mockServiceWorker.js
│   ├── scripts/gen-sku-list.mjs    # prebuild
│   └── src/
│       ├── pages/                  # SkuDetailPage, RunDetailPage, SettingsPage
│       ├── features/
│       │   ├── run-control/        # RunTrigger, RunProgressBadge
│       │   ├── run-detail/         # JobBreakdownTable
│       │   ├── sku-detail/         # AnomalyFlagCard, BaselineComparisonCard, DemandHistoryChart,
│       │   │                       # RunDeltaCard, RunPinControl, WhyThisNumberCard,
│       │   │                       # ModelProvenancePanel, OrderBreakdownCard
│       │   ├── sku-list/           # AbcMatrix, UrgencyLegend
│       │   └── order-cart/         # CartView, cartStore
│       ├── entities/{run,sku}/     # zod şemaları
│       └── shared/{api,i18n,...}
│
├── deploy/
│   ├── docker/
│   │   ├── Dockerfile.api          # python:3.11-slim, requirements + services/ + scripts/
│   │   ├── Dockerfile.controller   # cargo-chef → debian:trixie-slim
│   │   ├── Dockerfile.dashboard    # node:20 build → nginx:1.27-alpine serve
│   │   └── nginx.dashboard.conf    # SPA fallback + cache headers
│   ├── helm/                       # Tek generic chart, beş release
│   │   ├── Chart.yaml
│   │   ├── values.yaml             # default'lar
│   │   ├── templates/
│   │   │   ├── deployment.yaml
│   │   │   ├── service.yaml
│   │   │   ├── ingress.yaml        # nginx, cert-manager TLS
│   │   │   ├── pvc.yaml            # opsiyonel
│   │   │   ├── hpa.yaml            # opsiyonel
│   │   │   ├── cronjob.yaml        # gece eğitimi
│   │   │   ├── _helpers.tpl
│   │   │   └── NOTES.txt
│   │   └── values/
│   │       ├── api.yaml            # PVC=10Gi, /healthz HTTP probe, ingress kapalı (internal)
│   │       ├── controller.yaml     # cronjob: 0 2 * * * Europe/Istanbul, monthly-run --concurrency 4
│   │       ├── dashboard.yaml      # ingress: / (Prefix)
│   │       ├── postgres.yaml       # PVC=20Gi, pg_isready probe
│   │       └── grafana.yaml        # fsGroup=472, sub-path ingress (/grafana)
│   ├── scripts/
│   │   ├── deploy.sh               # build → push → helm upgrade; working tree dirty ise tag'e -dirty<ts> ekler
│   │   └── bootstrap.sh            # ns + postgres secret + regcred + grafana ConfigMap'ler
│   ├── grafana/
│   │   ├── dashboards/             # 4 .json (ConfigMap'lere bootstrap.sh basar)
│   │   └── provisioning/{datasources,dashboards}/
│   └── ofelia/config.ini           # docker-compose'da gece eğitimi için (k8s'de CronJob kullanılır)
│
├── scripts/                        # Tarihi / referans Python scriptleri (servis HTTP'den çağrılmıyor)
│   ├── model_v3.py     (1416 satır)# Eski monolitik üretim scripti — services/worker'ın kaynağı
│   ├── model_v2.py     (1417 satır)# v3'ün araştırma-ayarlı ikizi
│   └── OMS.py          (1237 satır)# Probe/Escalate'siz prototip
│
├── opt/                            # Tek-konu deneme scriptleri (ablation, bootstrap, ETS, PI calibration, SARIMA)
│   ├── ablation_playground.py
│   ├── bootstrap_playground.py
│   ├── ets_playground.py
│   ├── model_comparison_playground.py
│   ├── pi_calibration_playground.py
│   ├── sarima_playground.py
│   └── OPT.md
│
├── notebooks/                      # Yeni EDA / processing notebook'ları
│   ├── v1_eda.ipynb
│   ├── v1_processing.ipynb
│   ├── sku_types_after_fix.png
│   └── archive/                    # Faz 1–4 notebook'ları
│
├── Sales Forecast v7_full.ipynb    # Faz 5 araştırma notebook'u (~1.7 MB)
├── motul_data_analysis.ipynb
│
├── panel_sales_orders_stock.csv    # Kanonik aylık panel — image'a /app/ altında baked
├── sku_config.csv                  # SKU bazlı politika — image'a /app/ altında baked
├── veri_matrisi_final_sales_orders_stock_calendar_lags_fx.csv
├── pipeline_exporter.py            # outputs/ klasöründen pipeline_results.json üretir (offline export)
├── pipeline_results.json           # Bahsedilen export (servisler tüketmiyor; statik demo modu için rezerv)
└── tests/                          # pytest — parity_compare.py + birim testler
```

**Repo kökünde `outputs/`, `serialized_models/`, `v7_full/`, `mnt/`, `motul_data.csv` `.gitignore`'lı**. CI/build kapsamında değiller; üretim runtime'ı tüm state'i Postgres'te tutar.

---

## 4. Servis Topolojisi

Beş release tek namespace'te (`bitirme`):

```
                            ┌─────────────────────────────────────────────┐
                            │           https://bitirme.umceko.com        │
                            │            (nginx-ingress + TLS)             │
                            └────┬───────────┬────────────────────┬───────┘
                                 │ /         │ /api               │ /grafana
                                 ▼           ▼                    ▼
                         ┌──────────┐  ┌────────────┐      ┌─────────────┐
                         │ dashboard│  │ controller │      │   grafana   │
                         │ (nginx + │  │ (Rust /    │      │ (Postgres   │
                         │  Vite)   │  │  actix:80) │      │  datasource)│
                         └──────────┘  └─────┬──────┘      └──────┬──────┘
                                             │                    │
                                  HTTP (cluster DNS)              │
                                             │                    │
                                             ▼                    │
                                      ┌─────────────┐             │
                                      │     api     │             │
                                      │ (FastAPI    │             │
                                      │  :80)       │             │
                                      └─────┬───────┘             │
                                            │                     │
                                            │ joblib PVC          │
                                            │ (/app/models)       │
                                            ▼                     │
                                      ┌─────────────┐             │
                                      │  Longhorn   │             │
                                      │  RWO 10Gi   │             │
                                      └─────────────┘             │
                                                                  │
                                          ┌─────────────┐         │
                                          │  postgres   │◄────────┘
                                          │ (RWO 20Gi)  │
                                          └─────────────┘
                                                  ▲
                                                  │
                                          ┌───────┴────────┐
                                          │ controller-cron│  (gece 02:00 Europe/Istanbul,
                                          │  CronJob       │   `controller monthly-run`)
                                          └────────────────┘
```

**Sorumluluk dağılımı:**

- **`api`** — saf hesap: panel slice'ını + cached spec'ini gövdede alır, tahmin döndürür. State yok (PVC sadece joblib blob'ları için). Endpoint'ler: `POST /forecast/cold`, `POST /forecast/warm`, `POST /drift/check`, `GET /healthz`, `GET /readyz`.
- **`controller`** — Postgres'in tek yazarı + iş orkestratörü. Run/job tablolarını yönetir, drift'e göre cold/warm kararı verir, api'ye HTTP gönderir, sonuçları persist eder. Endpoint'ler: `POST /runs` (subset SKU filtresi), `GET /runs/{id}`, `GET /runs`, `GET /runs/{id}/jobs`, `GET /runs/{id}/skus/{sku}`, `POST /skus/{sku}/forecast` (tek-SKU), `GET /skus`, `GET /skus/{sku}/{latest,history,timeseries,predictions}`, `GET|POST|DELETE /skus/{sku}/pin`.
- **`dashboard`** — TypeScript SPA, nginx altında static serve. Controller'ı `/api` üzerinden, Grafana'yı `/grafana` üzerinden iframe ile tüketir.
- **`postgres`** — tüm üretim state'i: panel, config, runs, jobs, predictions, pin'ler.
- **`grafana`** — Postgres datasource, 4 önceden hazırlanmış dashboard. ConfigMap'lerle provisioning (`bootstrap.sh` `deploy/grafana/` içeriğini her güncellemede senkronize eder).
- **`controller-cron`** — CronJob (`0 2 * * *`, Europe/Istanbul, `Forbid` overlap, 4h hard cap). Her gece `controller monthly-run --concurrency 4` yürütür: tüm SKU'ları queue'ya basar, worker'lar drift'e göre cold/warm yapar.

---

## 5. SKU Başına Pipeline (`services/worker/pipelines/`)

Üç ana yol var; controller hangisinin tetikleneceğine karar verir (`orchestrator.rs`):

| Path | Tetiklendiği zaman | Tipik süre (concurrency=4) |
|---|---|---|
| **dead bypass** | Son `DEAD_SKU_WINDOW_MO` (varsayılan 12) ay içinde satış yok | **<1 saniye** |
| **warm** | Önceki başarılı run var, drift kontrolünden geçti | **~12 saniye** |
| **cold** | İlk run veya drift tespit edildi | **~3-5 dakika** (batched) |

### 5.1 Cold (`pipelines/cold.py` — `run_cold`)

```
 1. Veri hazırlığı       prep_features_y                       (lag'ler, takvim, winsorize)
 2. Dead SKU kontrolü    cutoff = test_start - DEAD_SKU_WINDOW (sıfırsa zero forecast döner, mode="dead_sku")
 3. Y model ROCV         optimize_rf_rocv, optimize_xgb_rocv   (3-fold rolling-origin CV)
 4. VAL üzerinde Probe   _build_exog_by_method                 (ETS, Intermittent, ML-Exog RF, Carry-Forward)
 5. Gerekirse Escalate   baseline_val_mae kontrolü             (probe < seasonal_naive + DELTA ise +XGB +Prophet)
 6. Değişken bazlı hibrit choose_best_exog_per_var             (orders ⨯ stock için en iyiler bağımsız)
 7. TSB override         zero_ratio kontrolü                   (yüksek sıfır oranlı serilerde TSB MAE yarışını atlatır)
 8. Test EXOG oluştur    build_exog_*                          (TEST_END / TEST_END_SHORT'a ileri yansıtma)
 9. TEST değerl. (PRE)   recursive_forward_predict_y,          (özyinelemeli tahmin + Laplace bootstrap PI +
                         add_bootstrap_intervals,               stoksuz kalma olasılığı + E[T])
                         stockout_probability + bias correction
10. REFIT                refit_models_on_full                  (train+val üzerinde yeniden eğit; kötüyse rollback)
11. OMS sipariş poltk.   stockout_probability,                 (order = max(0, cumDemand(H, q) - startStock),
                         cum_demand_quantile, round_moq_lot     MOQ + lot'a yuvarlanır)
12. Persist              controller insert sku_runs +          (combinations, exog_selection, models,
                         sku_run_{combinations,...}             predictions, recommendation, val_residuals)
                         + cached_spec blob (warm için)
```

### 5.2 Warm (`pipelines/warm.py` — `run_warm`)

ROCV / probe / escalate / choose_best_exog_per_var ADIMLARI **atlanır**. Cached spec'ten gelen kazanan Y-model ailesi + hyperparam'lar ile genişletilmiş train+val penceresinde **sadece final modeli yeniden eğitir**, sonra tahmin eder. Mode: `warm_with_refit`. Sonuç: 12 saniye vs cold'un 15 dakikası.

Drift kontrolü warm'un önündedir (`controller/src/orchestrator.rs`): VAL üzerinde yeni MAE cached MAE'den `DRIFT_EPS` (varsayılan %20) kötüyse → cold fallback.

### 5.3 Dead SKU (`pipelines/cold.py` — `_zero_result`)

Pipeline'a girmeden döner: tahmin sıfır, PI sıfır, öneri yok, mode="dead_sku". 360 SKU'luk panelimizde ~%23 (84 SKU) bu yola düşüyor.

---

## 6. Veri Şemaları

### `panel_sales_orders_stock.csv` → Postgres `sales_panel`

| Sütun | Tip | Açıklama |
|---|---|---|
| `ds` | date | Ayın ilk günü timestamp (MS frekansı) |
| `sku` | string | Ürün kodu (örn. `303-104092`, `IHR-780-AFL110AUV`) |
| `y` | float | Gerçekleşen aylık satış (adet) |
| `orders` | float | O ayda verilen gelen satın alma siparişleri |
| `stock` | int | Ay sonu eldeki stok |

PK: `(sku, ds)`. Upsert semantik (`ON CONFLICT DO UPDATE`). Şu an ~350 SKU × 70 ay = ~25k satır.

### `sku_config.csv` → Postgres `sku_config`

| Sütun | Açıklama |
|---|---|
| `sku` | Ürün kodu (PK) |
| `T_CHECK` | Ay bazında inceleme döngüsü; `E[T_stockout] ≤ T_CHECK` ise sipariş tetiklenir |
| `H_COVER` | Kapsam ufku — siparişin kaç aylık talebi karşılayacağı |
| `Q` | Kümülatif talep üzerinde servis seviyesi kuantili (örn. 0.5 = medyan) |
| `MOQ` | Minimum sipariş miktarı (0 = minimum yok) |
| `LOT_SIZE` | Yuvarlama granülarisi (1 = birim, aksi halde en yakın lot'a yukarı yuvarla) |
| `STARTING_STOCK_OVERRIDE` | 0 değilse `sales_panel.stock`'tan gelen son değeri override eder (manuel sayım sonrası) |

### Postgres tabloları (özet)

| Tablo | Rolü |
|---|---|
| `forecast_runs` | Run başına bir satır: `run_id`, `pipeline_version`, `config_json`, `status`, `started_at`, `completed_at`, `data_version_hash` |
| `forecast_jobs` | Run × SKU işleri: `status` (queued/claimed/completed/failed), `attempts`, claim için `FOR UPDATE SKIP LOCKED` |
| `sku_runs` | SKU × run terminal sonucu: mode, kazanan y_variant + phase (PRE/REFIT), mae, rmse, recommendation özeti |
| `sku_run_combinations` | Test edilen tüm (exog × y_variant × phase) kombinasyonları, kazanan tespiti için |
| `sku_run_exog_selection` | Değişken bazlı (`orders`, `stock`) seçilen EXOG yöntemi + skor |
| `sku_run_models` | Eğitilen modellerin hyperparam'ları + blob URI'si (warm için) |
| `sku_run_predictions` | Tahmin trayektorisi (her `ds` için yhat + PI sütunları) |
| `sku_run_recommendation` | Sipariş önerisi: `starting_stock`, `cum_demand_q`, `order_qty_{raw,rounded}`, `p_stockout_{3,6}m`, `e_t_stockout_mo` |
| `sku_run_val_residuals` | VAL penceresinde rezidüeller, drift karşılaştırması için |
| `sku_active_pin` | Dashboard'dan pin'lenen run'lar — "latest" çağrılarında bu run dönülür |

Migration'lar `controller/migrations/`; controller `serve` veya `migrate` subcommand'iyle açıldığında otomatik uygular.

---

## 7. Veri Akışı

```
       ┌──────────────────────────┐
       │  Ham veri (CSV drop)     │
       │  panel/config/attributes │
       └──────────┬───────────────┘
                  │  kubectl cp + controller seed
                  ▼
       ┌─────────────────────────┐         ┌────────────────────────┐
       │   postgres.sales_panel  │◄────────│ controller-cron        │
       │   postgres.sku_config   │         │ (gece 02:00 Istanbul,  │
       └──────────┬──────────────┘         │  monthly-run)          │
                  │                        └────────────────────────┘
                  │  (controller okur)
                  ▼
       ┌─────────────────────────────────┐
       │  controller `monthly-run`       │
       │  veya `POST /runs` (subset)     │
       │  veya `POST /skus/{sku}/forecast│
       │                                  │
       │  INSERT forecast_runs            │
       │  INSERT forecast_jobs (per SKU)  │
       │  tokio worker'lar claim eder     │
       │  → drift check → cold or warm    │
       └──────────┬──────────────────────┘
                  │  HTTP /forecast/{cold,warm}
                  ▼
       ┌─────────────────────────────────┐
       │  api (FastAPI worker)            │
       │  services/worker/pipelines/      │
       │  → cold.run_cold / warm.run_warm │
       │  → ForecastResult JSON döner     │
       └──────────┬──────────────────────┘
                  │  HTTP response
                  ▼
       ┌─────────────────────────────────┐
       │  controller persist             │
       │  sku_runs, predictions,         │
       │  recommendation, val_residuals  │
       │  cached_spec blob (PVC)         │
       └──────────┬──────────────────────┘
                  │
        ┌─────────┴───────────┐
        ▼                     ▼
  ┌──────────┐         ┌──────────┐
  │dashboard │         │ grafana  │
  │GET /api/ │         │ Postgres │
  │skus/...  │         │ panels   │
  └──────────┘         └──────────┘
```

---

## 8. Yük taşıyan kararlar + anti-pattern'lar

**Yük taşıyan tasarım kararları:**

- **Özyinelemeli Y tahmini** (`forecasting/recursive.py`). Doğrudan çoklu-adım (bir kerede T+6) yerine T+1'i T+2'nin lag feature'larına geri besler. Zaman serisi semantiğine sadık ama ilk adım yanlışsa hata birikir.
- **NNLS topluluk ağırlıkları + simplex projeksiyonu** (`models/stacking.py`). `time_decay` ile yakın doğrulama hataları uzak olanlardan daha fazla sayılır. Harici `scipy.optimize.nnls` bağımlılığı yok — el yazımı projeksiyon gradyanı.
- **Değişken bazlı EXOG seçimi** (`selection/hybrid.py`). `orders` ve `stock` bağımsız tahmin edilir — orders için en iyi yöntem stock için en iyi olmayabilir; naif birleştirme bunu gizler.
- **Probe → Escalate**. Önce ucuz EXOG yöntemleri (ETS, IM, ML-Exog-RF, Carry-Forward); ağır yöntemler (Prophet, XGB-Exog) sadece ucuzlar `seasonal_naive + DELTA_BETTER_THAN_BASELINE` eşiğini geçemezse devreye girer.
- **Dead SKU bypass + TSB override + zero_y_variant** (opt-branch'ten). Pipeline'a giren her SKU'nun cold yola gitmesi gerekmiyor — sıfır oranı yüksek serilerde TSB doğrudan kazanan ilan edilir, son 12 ayda satışı olmayanlar sıfır tahmin ile döner. Tipik portföyde %20-25'lik bir hız kazancı.
- **Bootstrap PI > parametrik CI**. `forecasting/bootstrap.py` tek bir nokta tahmini yerine kalibre %80/%95 aralıkları üretir; stoksuz kalma olasılığı tüm dağılım üzerinden integre edilir.
- **REFIT + rollback**. İlk eğitim/değerlendirme ayrımından sonra modeller train + val üzerinde yeniden eğitilir. Refit sonucu pre-refit'ten *kötüyse*, pre-refit saklanır. Yakın dönem gürültüye overfit etmeyi önler. (Load-bearing invariant; `pipelines/cold.py`'de kıyas yönünü ters çevirmek bug üretir.)
- **Drift gate'i warm önünde**. Cached spec varsa otomatik warm değil — VAL üzerinde yeni MAE cached MAE'den %20 (DRIFT_EPS) kötü gelirse cold fallback. Stale model riskini sınırlar.
- **Working tree dirty ise image tag'e `-dirty<unix_ts>` ekle** (`deploy/scripts/deploy.sh`). Aksi halde aynı git SHA tag'iyle iki farklı içerik push'larsanız k8s `IfNotPresent` ile eski image'i cache'leyebilir.

**Bilinen kod-sağlık sorunları (refaktör etmeden önce araştır):**

- ⚠ `val_mae_exog_for_col` `scripts/model_v3.py` içinde hâlâ **iki kez tanımlı** (satır 988 ve 998). İlki ölü kod. v3 artık üretim değil ama tarihi referans olarak burada — `services/worker/selection/hybrid.py:val_mae_exog_for_col` temiz versiyondur.
- ⚠ `scripts/model_v2.py` ve `scripts/model_v3.py` — eski monolit ikizler. Üretim mantığı `services/worker/` altına taşındı, bu iki dosya artık çağrılmıyor.
- ⚠ `scripts/OMS.py` — Probe/Escalate'siz prototip. Karşılaştırma için saklanıyor.
- ⚠ `controller/src/server.rs` REST endpoint'leri `actix-web` çoklu worker'la (`workers: 2`) çalışıyor. Yoğun yazma esnasında `GET /runs/{id}` farklı sqlx connection snapshot'ları döndürebiliyor (`completed`/`queued` count'ları kısa süreliğine inkonsistent). Cosmetic — pipeline'ı etkilemez ama dashboard polling'i kararsız görünebilir.
- ⚠ `controller` ve `api` image'larına `panel_sales_orders_stock.csv` + `sku_config.csv` baked. Veri güncellemesi için ya rebuild gerekir ya da `kubectl cp + controller seed` (önerilen yol — kodu kirletmez).
- ⚠ `pipeline_results.json` repo kökünde — şu an hiçbir servis tüketmiyor, statik demo modu için rezerv (dashboard'ın `VITE_USE_STATIC_SOURCE` flag'i ile).
- ⚠ Faz 1–4 notebook'ları `notebooks/archive/` altına taşındı, kök daha temiz. `.claudeignore` hâlâ büyük arşivleri context'ten dışlar.

---

## 9. Giriş Noktaları Özeti

| Amaç | Komut |
|---|---|
| Lokal geliştirme yığını | `docker compose up -d` (postgres + api + controller + grafana + adminer) |
| Lokal seed | `bash deploy/seed.sh` (compose içindeki controller'a `seed` çağırır) |
| k8s namespace + secret + grafana CMs | `just bootstrap` |
| Bir servisi build + push + deploy | `just deploy <api\|controller\|dashboard\|postgres\|grafana>` |
| Tüm servisleri sırayla deploy | `just deploy-all` |
| Lokal docker login (registry için) | `just login` |
| Postgres'i panel + config ile seed | `just seed` (kubectl cp + controller seed çalıştırır) |
| Tek SKU ad-hoc çalıştır | `curl -X POST https://bitirme.umceko.com/api/skus/{sku}/forecast` |
| Tüm portföy çalıştır | `curl -X POST https://bitirme.umceko.com/api/runs` |
| Alt-küme çalıştır | `curl -X POST https://bitirme.umceko.com/api/runs -d '{"skus":["A","B"]}'` |
| Sonuç çek | `GET https://bitirme.umceko.com/api/skus/{sku}/latest` |
| Pod log'u takip et | `just logs <service>` |
| Pod shell | `just shell <service>` |
| Helm release listesi | `just list` |
| Tarihi monolit (referans) | `python scripts/model_v3.py` |
| Araştırma notebook'u | `Sales Forecast v7_full.ipynb`, `notebooks/v1_eda.ipynb` |
| Paneli ham veriden yeniden oluştur | `notebooks/v1_processing.ipynb` |

---

## 10. Kodu Nereden Okumaya Başlamalı

Servis tarafı (üretim):

1. `services/worker/pipelines/cold.py` — Ana cold pipeline (`run_cold`)
2. `services/worker/pipelines/warm.py` — Warm refit pipeline (`run_warm`)
3. `services/worker/forecasting/recursive.py` — Özyinelemeli Y tahmin döngüsü
4. `services/worker/forecasting/bootstrap.py` — Laplace PI oluşturma
5. `services/worker/selection/hybrid.py` — Değişken bazlı EXOG seçimi (`val_mae_exog_for_col`, `choose_best_exog_per_var`)
6. `services/worker/selection/probe_escalate.py` — Probe → Escalate kapısı
7. `services/worker/models/stacking.py` — NNLS + simplex projeksiyonu
8. `services/worker/models/intermittent.py` — Croston / SBA / TSB + `select_intermittent`
9. `controller/src/orchestrator.rs` — Cold/warm/dead dispatch, drift check
10. `controller/src/queue.rs` — `forecast_jobs` claim/run/retry semantiği
11. `controller/src/server.rs` — REST endpoint'leri
12. `dashboard/src/pages/SkuDetailPage.tsx` — SKU başına dashboard kompozisyonu

Deploy + altyapı:

13. `justfile` — operasyonel komutlar
14. `deploy/scripts/deploy.sh` — build → push → helm upgrade akışı (dirty-tag detayı dahil)
15. `deploy/helm/templates/deployment.yaml` + `cronjob.yaml`
16. `deploy/helm/values/controller.yaml` — cron schedule, ingress regex/rewrite, resource limit'leri

Tarihi referans (yeni mantık eklerken karşılaştırmak için):

17. `scripts/model_v3.py:983` — eski monolitik `run_for_sku` (services/worker'a parçalanmadan önceki halini görmek için)
18. `proje_ozeti.md` — Tez anlatımı (model seçim mantığının "neden" tarafı)
