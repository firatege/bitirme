# Bitirme Projesi: Zaman Serisi & Makine Öğrenmesi ile Çoklu SKU Satış Tahmini ve OMS (Order Management System) Uygulaması

Bu markdown dosyası, projenin bütün klasör yapısını, kodlarını, jupyter notebook gelişim aşamalarını ve son çalışan otomasyon script'lerinin (`OMS.py`, `model_v3.py`) detaylı teknik analizini içermektedir.

---

## 1. Projenin Amacı ve Temel Kavramları

Motul (veya benzeri bir marka) için geliştirilmiş bu satınalma ve stok tahmin sistemi, sıradan bir "zaman serisi analizi" projelerinden çok daha ileri bir noktadadır. Amacı sadece bir ürünün ne kadar satacağını hesaplamak değil; *Order Management System (Sipariş Yönetim Sistemi)* fonksiyonlarını çalıştırabilmektir. Mevcut hisse senedi/stok (stock) ve verilen siparişleri (orders) dışsal değişken (exogenous variables) olarak sisteme dahil eder, satış (y) verilerini baz alarak her ürün (SKU) için "Ne kadar sipariş vermeliyim? Hangi periyotta vermeliyim?" sorusuna kurumsal kısıtlarla (Lot büyüklüğü, Minimum Sipariş Miktarı - MOQ vb.) yanıt verir.

---

## 2. Gidişat ve Projenin Evrimi (Dosya Yapısı Analizi)

Proje, basit veri analizinden başlayıp kompleks paralel işlem (multiprocessing) yapan python modüllerine doğru evrilmiştir.

### Aşama 1: Veri Keşfi ve Kümeleme (EDA ve Clustering)
*   **`motul_data.csv` / `veri hazırlama.ipynb` / `motul_data_analysis.ipynb`:** Ham verinin içeriye alındığı kısımlar. Aylık/haftalık bazda ürün (ItemCode) satış (TotalQty) bazında incelenir. 
*   **Kümeleme Dosyaları (`Cluster0_AltKume2.csv`) & Adfuller Testleri:** Ürünler durağanlık ve satış karakteristiklerine göre ayrıştırılmıştır. (Hangi ürün çok satıyor, hangi üründe mevsimsellik var, hangisi nadir satıyor).
*   **`panel_sales_orders_stock.csv`:** Projenin asıl kalbi olan verisetidir. Temizlenmiş halinde 3 temel metrik barındırır:
    *   `y`: Gerçekleşen Satış miktarı
    *   `orders`: Verilen Sipariş miktarı
    *   `stock`: İlgili dönemdeki Stok adedi

### Aşama 2: Tekil Ürün Üzerinden Modelleri Anlama (Baseline Deneyler)
*   **`303-104092-3-Model.ipynb`, `303-104092-Probhet -XGBoost.ipynb` vs.:** Projenin ilk aşamalarında sadece `303-104092` kodlu popüler bir ürün üzerinde denemeler yapılmıştır. 
    *   Sadece XGBoost, sadece Prophet, sadece Random Forest çalıştırılarak bu algoritmaların sınırları ve Hyperparameter (HP) optimizasyonları manuel olarak gözlemlenmiştir.

### Aşama 3: Çoklu Model (Ensemble) & Exogenous Yaklaşımların Oluşumu
*   **`Auto-Exog Forecast 1.ipynb` -> `Auto-Exog Forecast (Prophet - SARIMA - ETS) + RF & XGB.ipynb`**: Burada temel amaç "Gelecekteki satışları tahmin etmek istiyorsak, gelecekteki 'Stok' ve 'Sipariş' miktarını da bilmeliyiz" gerçeği etrafında şekilleniyor.
    *   Sistem, gelecekteki dış değişkenleri (exogenous) tahmin etmek için Univariate (Tek değişkenli) modelleri (SARIMA, ETS, Prophet) kullanır.
    *   Ardından, bu dışsal değişkenlerin gelecekteki değerlerini (features) RF ve XGB modeline girdi olarak vererek asıl "Satış" tahminini yapar.
*   **Ağırlıklandırma Stratejileri:** Modeller yarışa sokulur. Tahmin sonuçları Inverse-MAE (Hatasının tersi) yöntemiyle ağırlıklandırılır. Hatası en düşük modele en yüksek ağırlık (güven) verilir.

### Aşama 4: Üretim/Otomasyon Aşaması (OMS Sürümü v6.x ve Python Scriptleri)
Artık jupyter notebooklar yerini sistemde çalışabilecek betiklere bırakmıştır (`OMS.py`, `model_v2.py`, `model_v3.py`).

*   **`model_v3.py` & `v6_multi_sku.py`**: Projenin nihai zihniyeti. Bu dosyalardaki mimari akış şu şekildedir:
    1.  **Hazırlık (Data Prep & Lags):** Gecikmeli veriler (lags), hareketli ortalamalar (moving averages), tatil/takvim(calendar) matrisleri üretilir.
    2.  **Model Eğitimi (Recursive Feature Elimination):** XGBoost ve Random Forest ile satış y tahmini Time-Series Split ROVC yapısıyla eğitilir.
    3.  **PROBE / ESCALATE Mekanizması:** Önce hızlı ve ucuz (Computationally cheap) Yöntemler (Örn: Basit Hareketli Ortalamalar) denenir. Eğer geçerlilik (Validation) MAE skoru istenilen eşiğin altında değilse daha karmaşık modellere (XGB/Prophet) "Escalate" edilir.
    4.  **Zaman Kırınımlı Ağırlıklandırma (Time-Decay NNLS - Non-negative Least Squares):** Regresyon temelli Ridge-NNLS ile ensemble ağırlıkları bulunur. Üstelik *time_decay* parametresi ile **daha yakın zamandaki** hatalara daha fazla ceza verilerek modelin güncel trende adapte olması sağlanır.
    5.  **Intermittent Demand (Kesintili/Seyrek Talep):** Bazen aylarca sıfır çeken seyrek ürünler için `Croston`, `SBA` (Syntetos-Boylan) ve `TSB` istatistiksel metotları dinamik olarak tetiklenir ("Sıfır atlama" yoğunluğuna bakılarak).
    6.  **Refit Mekanizması:** Sadece Train datasında ağırlık bulup bırakmaz. Tüm test/gerçek data dahil edilerek modeller "yeni gerçekliğe" göre üretim aşamasına geçmeden baştan eğitilir.
    7.  **Bootstrap Yöntemiyle PI (Prediction Intervals):** Deterministik tek bir sayı vermek yerine (Örn: "230 tane satacak"), " %95 Güvenilirlikle 200 ile 260 arası satacak" şeklinde Güvenlik Aralığı üretilir. 
    8.  **Stok/Tedarik Kararı:** Elde edilen PI (Prediction Intervals), simülasyonlara dahil edilerek *Stockout Probability* (Stoksuz Kalma Olasılığı) hesaplanır ve kurgulanan `sku_config.csv` deki MOQ (Minimum Sipariş Adedi) gibi kısıtlara uygun Satınalma (Orders) rakamları önerilir.

---

## 3. Modelleme Seçimlerinin Mühendislik Mantığı ("Neden" Yapıldı?)

*   **Neden sadece Facebook Prophet Kullanılmadı?** Prophet tatil günleri ve pürüzsüz trendlerde harikadır, ama karmaşık non-linear etkileşimlerde (stok ile satış arasındaki asimetrik bağ) XGBoost gibi ağaç tabanlı modeller gerçeği daha iyi öğrenir.
*   **Neden Recursive (Özyinelemeli) Tahmin?** Direkt $T+6$ zamanını tahmin etmek yerine, $T+1$'i bulup, oradaki tahmini yeni gerçeklikmiş gibi girdi olarak kullanıp $T+2$'yi bulmak (Recursive Forecasting) Zaman serisi doğasına çok daha uygundur.
*   **Neden Inverse-MAE ve NNLS Ensembling?** Sadece modellerin ortalamasını almak (Average of RF & XGB) hatayı yükseltebilir. NNLS, modellerin valizasyon (Validation) setindeki geçmiş performanslarına bakarak onlara en ideal kredi oranlarını (Weight) dağıtır.
*   **Neden Stok & Sipariş Verisi (Exogenous Variables)?** Sadece satış verisine bakarak bir talebi tahmin etmek yanıltıcıdır. Ürün geçen ay 0 satmış olabilir, ama talep olmadığı için mi yoksa *stokta kalmadığı için mi?* Bu proje *kısıtlılıkları (censored demand)* modele Stock verisini göstererek aşmayı hedefler.

## Sonuç
Bu sistem sadece "bir tahminci" değil, başından sonuna tam teşekküllü bir **"Karar Destek Sistemi - Order Management Automation"** mimarisidir. Çoklu işlemcileri kullanarak (ThreadPoolExecutor/ProcessPoolExecutor) yüzlerce ürünü paralelde çözme kapasitesine sahip bir mimariye kavuşturulmuştur.

