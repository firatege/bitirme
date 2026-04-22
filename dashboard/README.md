# Depo Yönetim Paneli (Dashboard)

Bitirme projesinin React tabanlı depo yönetim paneli. Backend'i değiştirmez; Rust controller'ın REST API'sine ve Grafana panellerine bağlanır.

## Kurulum

```bash
cd dashboard
npm install
cp .env.example .env
npm run dev   # http://localhost:5173
```

Backend ayakta olmalı:

```bash
docker compose up -d postgres api controller grafana
```

## Komutlar

| Komut | Açıklama |
|---|---|
| `npm run dev` | Geliştirme sunucusu |
| `npm run build` | Üretim derlemesi |
| `npm run typecheck` | TypeScript kontrolü |
| `npm run test` | Vitest birim testleri |
| `npm run lint` | ESLint |

## Ortam değişkenleri (`.env`)

| Anahtar | Varsayılan | Açıklama |
|---|---|---|
| `VITE_API_BASE_URL` | `http://localhost:9000` | Rust controller REST tabanı |
| `VITE_GRAFANA_URL` | `http://localhost:3000` | Grafana embed hedefi |
| `VITE_USE_STATIC_SOURCE` | `false` | `pipeline_results.json` offline modu |

## SKU listesi

Controller'da toplu `/skus` endpoint'i yok. Dashboard başlangıçta `public/sku_list.json` dosyasını okur:

```json
{ "skus": ["303-104092", "303-104093", "..."] }
```

Oluşturmak için:

```bash
jq '{skus: [.[].sku]}' panel_sales_orders_stock.csv  # örnek
# veya
python -c "import pandas as pd, json; df=pd.read_csv('panel_sales_orders_stock.csv'); open('dashboard/public/sku_list.json','w').write(json.dumps({'skus': sorted(df['sku'].unique().tolist())}))"
```

## Mimari

```
src/
├── app/         → Bootstrap, router, providers, shell layout
├── pages/       → Route seviyesi bileşenler (ince)
├── features/    → İş akışları (sku-list, sku-detail, order-cart, run-control)
├── entities/    → Backend tip ve şemaları, saf seçiciler
├── shared/      → UI, API client, i18n, lib, config
├── styles/
└── test/
```

Detay için `ARCHITECTURE.md`.

## Grafana entegrasyonu

`deploy/grafana/` altında 4 pano kod olarak:
- `model-performance.json` — MAE trendi
- `portfolio-kpi.json` — Toplam sipariş, kritik SKU, ortalama MAE
- `stockout-calibration.json` — p3m/p6m dağılımları, reliability
- `run-ops.json` — Run süresi, başarı oranı, hatalı joblar

Dashboard içinde `/analytics` sayfası panelleri iframe ile gösterir. Tam ekran için Grafana'yı `http://localhost:3000` üzerinden aç.
