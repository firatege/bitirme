# Dashboard Mimarisi

## Katmanlar (Feature-Sliced Design)

```
app        → bootstrap, router, providers, layouts
pages      → route-level bileşenler (ince; feature + shared kullanır)
features   → iş akışı parçaları (SKU list, SKU detail, cart, run-control)
entities   → domain modelleri + Zod şema + saf seçiciler (urgency, policy)
shared     → UI primitives, API client, i18n, lib, config
```

Bağımlılık yönü **her zaman aşağıya**: `app → pages → features → entities → shared`.
Asla ters yönlü import yok (lint kuralı).

## Veri akışı

```
Controller REST  ──▶ Axios interceptor (ApiError)
                      │
                      ▼
              Zod schema.parse()  (runtime doğrulama)
                      │
                      ▼
           TanStack Query cache (queryKeys factory)
                      │
                      ▼
             Saf seçiciler (urgencyOf, roundMoqLot)
                      │
                      ▼
                React komponentleri
                      │
                      ▼ (kullanıcı aksiyonu)
          Mutation (useCreateRun, useTriggerSkuForecast)
                      │
                      ▼
           queryClient.invalidateQueries
```

## Desenler

- **Ports & Adapters** — `ForecastDataSource` arayüzü. `ControllerAdapter` üretim; ileri sürümlerde `StaticJsonAdapter` (offline `pipeline_results.json`), `MockAdapter` (MSW).
- **Query Key Factory** — [shared/api/queryKeys.ts](src/shared/api/queryKeys.ts). Magic string yok; invalidation anahtarları tek kaynaktan.
- **Zod runtime validation** — Backend şeması değişirse uyumsuzluk anında görünür bir hata olarak yüzeye çıkar.
- **Pure selectors** — `urgencyOf`, `recomputeOrderQty` kütüphane bağımlılığı olmadan yazılır → birim test dostu.
- **Zustand persist** — sepet localStorage'da; yönetici tarayıcıyı yenilediğinde kaybetmez.

## Test stratejisi

- **Birim**: saf seçiciler ve politika (`policy.test.ts`, `selectors.test.ts`, `exportCsv.test.ts`)
- **Entegrasyon** (sonraki iterasyon): MSW handlers + Testing Library
- **E2E** (sonraki iterasyon): Playwright — ana ekran → detay → sepet → CSV

## Performans notları

- `useQueries` ile SKU listesi paralel çekilir; her SKU kendi cache'ine sahiptir.
- TanStack Query `staleTime: 30s` — arka arkaya sayfa geçişlerinde ağ isteği yok.
- Tablo 10K+ satıra çıkarsa `@tanstack/react-virtual` eklemesi önerilir.

## Grafana köprüsü

Dashboard Grafana'yı yalnızca iframe ile embed eder — veri çekme yok. Grafana doğrudan Postgres'e (read-only kullanıcı) bağlanır. Bu sayede:
- Ağır SQL sorguları React tarafında bellek/CPU tüketmez
- Analist Grafana editorunde pano özelleştirebilir → kaydedilip repo'ya commit edilebilir (provisioning)
- Dashboard iframe boyutu küçük kalır (React bundle'ı Grafana'dan bağımsız)

## Genişletme noktaları

- Yeni sayfa: `src/pages/FooPage.tsx` → `src/app/router.tsx`'a rota
- Yeni endpoint: `shared/api/endpoints.ts` + `ForecastDataSource` arayüzü + `ControllerAdapter`
- Yeni feature: `features/<name>/` altında bağımsız modül; `pages/` çağırır
