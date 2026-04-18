# -*- coding: utf-8 -*-
"""
model_accuracy_report.py — Tahmin Performans Analizi
===================================================

model_v3.py çalıştırıldıktan sonra çalıştırılır.
outputs/_SUMMARY/test_summary_ALL_SKUs.csv dosyasını okuyarak:
  1. Her SKU için en iyi modeli listeler.
  2. Profil bazlı performans özetini çıkarır.
  3. Hata metriklerini (MAE, RMSE, MAPE) karşılaştırır.
"""

import os
import pandas as pd
import numpy as np

SUMMARY_PATH = "outputs/_SUMMARY/test_summary_ALL_SKUs.csv"
PROFILE_PATH = "outputs/_SUMMARY/sku_profiles.csv"

def generate_accuracy_report():
    if not os.path.exists(SUMMARY_PATH):
        print(f"HATA: {SUMMARY_PATH} bulunamadı. Önce model_v3.py'yi çalıştırın.")
        return

    # Verileri yükle
    df = pd.read_csv(SUMMARY_PATH)
    
    # Sadece 'Full' horizon (6 aylık genel performans) üzerinden analiz yapalım
    df_full = df[df["Horizon"] == "Full"].copy()
    
    if df_full.empty:
        print("HATA: Özette 'Full' horizon verisi bulunamadı.")
        return

    # Her SKU için en iyi modeli (min MAE) bul
    best_models = df_full.sort_values(["sku", "MAE"]).groupby("sku").head(1)
    
    # Profil bilgilerini ekle (varsa)
    if os.path.exists(PROFILE_PATH):
        profiles = pd.read_csv(PROFILE_PATH)[["sku", "profile"]]
        best_models = best_models.merge(profiles, on="sku", how="left")
    
    print("\n" + "="*100)
    print("SKU BAZLI EN İYİ MODEL PERFORMANSI")
    print("="*100)
    
    display_cols = ["sku", "profile", "Phase", "Exog", "Y-Variant", "MAE", "RMSE", "MAPE"]
    # Profil yoksa listeden çıkar
    display_cols = [c for c in display_cols if c in best_models.columns]
    
    print(best_models[display_cols].to_string(index=False))
    
    print("\n" + "="*100)
    print("PROFİL BAZLI ORTALAMA PERFORMANS")
    print("="*100)
    
    if "profile" in best_models.columns:
        profile_summary = best_models.groupby("profile").agg({
            "sku": "count",
            "MAE": "mean",
            "RMSE": "mean",
            "MAPE": "mean"
        }).rename(columns={"sku": "SKU_Sayisi"})
        print(profile_summary.round(2).to_string())
    else:
        print("Profil bilgisi bulunamadı.")

    # Genel özet
    avg_mae = best_models["MAE"].mean()
    print("\n" + "="*100)
    print(f"GENEL ÖZET:")
    print(f"Toplam Analiz Edilen SKU: {len(best_models)}")
    print(f"Ortalama MAE (Tüm SKUlar): {avg_mae:.2f}")
    print("="*100)

    # Kazanan kombinasyonların dağılımı
    print("\nMODEL KULLANIM DAĞILIMI:")
    usage = best_models.groupby(["Exog", "Y-Variant"]).size().reset_index(name="Adet")
    print(usage.to_string(index=False))

if __name__ == "__main__":
    generate_accuracy_report()
