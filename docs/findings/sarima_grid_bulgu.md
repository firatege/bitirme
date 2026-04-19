# SARIMA Grid Search Bulgusu

## Sorun
`model_v3.py`'deki `sarima_fit_best` fonksiyonu 64 kombinasyonluk grid search yapıyor (p∈[0,3], q∈[0,3], P∈[0,1], Q∈[0,1]). Her SKU için ~13 saniye sürüyor, 21 SKU × 2 kolon (orders+stock) = toplam **~272 saniye** sadece SARIMA'ya harcanıyor.

## Bulgu
`sarima_playground.py` ile 5 farklı konfigürasyon tüm SKU'larda test edildi (VAL_H=6, hedef: orders kolonu):

| Config | Ort. MAE | Ort. Süre | Hız Kazanımı |
|--------|----------|-----------|--------------|
| sabit ARIMA(1,1,1) | **119.2** | 0.78s | **16.65×** |
| minimal (0-1 × 0-1) | 126.1 | 1.70s | 7.62× |
| sabit (1,1,1)(1,1,1) | 141.9 | 0.46s | 27.96× |
| mevcut (0-3 × 0-3) | 158.9 | 12.95s | 1.0× (referans) |
| küçük (0-2 × 0-2) | 180.3 | 5.33s | 2.43× |

Mevcut config hem en yavaş hem en kötü MAE.

## Neden
Grid search AIC ile model seçiyor ancak AIC train verisi üzerinde hesaplanıyor. Daha fazla kombinasyon → train'e overfit → validation'da kötü genelleşme. Basit ARIMA(1,1,1) robust yapısı sayesinde daha iyi genelleşiyor.

## Çözüm
`sarima_fit_best` yerine sabit `ARIMA(1,1,1)(0,1,0,12)` kullan.

Periyodik kontrol: Yeni veri geldiğinde `sarima_playground.py` tekrar çalıştırılmalı. Eğer başka config kazanırsa güncelle.

## Sonuç
- MAE: 158.9 → 119.2 (**%25 iyileşme**)
- Süre: 272s → 16s (**16.65× hızlanma**)
- 21 SKU toplam SARIMA süresi ~4.5 dakikadan ~16 saniyeye düşüyor
- Tez bulgusu: "Daha karmaşık grid search her zaman daha iyi sonuç vermez"

## Açık Soru: SARIMA'nın Doğrudan Doğruluğu

### Sorun
SARIMA şu an sadece **dolaylı olarak** test ediliyor:
```
SARIMA orders/stock tahmini → RF/XGB → satış tahmini → TEST MAE
```
SARIMA'nın orders ve stock'u ne kadar doğru tahmin ettiği ayrıca ölçülmüyor.

### Yapılacak
Her model çalıştırmasında SARIMA'nın doğrudan doğruluğunu logla:
```
SKU: 303-104092
  SARIMA orders MAE (VAL): 45.2
  SARIMA stock  MAE (VAL): 12.8
  Final satış   MAE (TEST): 18.4
```
Bu loglardan şu soru cevaplanabilir:
**"EXOG tahmin kalitesi ile nihai satış tahmin kalitesi arasında ilişki var mı?"**

Yani SARIMA orders'ı ne kadar iyi tahmin ederse satış tahmini o kadar mı iyileşiyor?

### Tez Değeri
EXOG kalitesi → satış MAE ilişkisini gösteren scatter plot güçlü bir analiz bölümü olur.
Şu an `val_exog_selection_basic.csv` bu logları kısmen tutuyor — karşılaştırma buradan yapılabilir.

## Tarih
2026-04-19 — `sarima_playground.py` ile test edildi (81 aylık veri, 21 SKU)
