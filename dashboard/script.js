// Verileri tutacağımız global değişken
let dashboardData = null;

let currentHorizon = 6;
let isCriticalFilterOn = false;

// DOM Yüklendiğinde
document.addEventListener("DOMContentLoaded", () => {
    fetchData();
    
    // Toggle Event Listener
    const toggle = document.getElementById("filter-critical-toggle");
    toggle.addEventListener("change", (e) => {
        isCriticalFilterOn = e.target.checked;
        renderTable(dashboardData, isCriticalFilterOn, currentHorizon);
    });

    const horizonSlider = document.getElementById("horizon-slider");
    const horizonLabel = document.getElementById("horizon-label");
    horizonSlider.addEventListener("input", (e) => {
        currentHorizon = parseInt(e.target.value, 10);
        horizonLabel.textContent = currentHorizon + " Ay";
        if (dashboardData) {
            renderTable(dashboardData, isCriticalFilterOn, currentHorizon);
        }
    });
});

async function fetchData() {
    try {
        // Sunucu kök dizininde çalıştığını varsayıyoruz. 
        // /outputs/_SUMMARY/warehouse_summary.json adresine istek atacağız.
        const response = await fetch("../outputs/_SUMMARY/warehouse_summary.json");
        if (!response.ok) {
            throw new Error("Veri yüklenemedi: " + response.statusText);
        }
        dashboardData = await response.json();
        
        // Veriyi Tarih Saat formtla
        const dateObj = new Date(dashboardData.generated_at);
        document.getElementById("last-updated").textContent = "Son Güncelleme: " + dateObj.toLocaleString("tr-TR");

        // KPI'ları doldur
        document.getElementById("kpi-total").textContent = dashboardData.total_skus;
        
        // Tabloyu çiz
        renderTable(dashboardData, false, currentHorizon);
    } catch (error) {
        console.error("Fetch error:", error);
        document.getElementById("last-updated").textContent = "Hata: Veri çekilemedi.";
        document.getElementById("table-body").innerHTML = `<tr><td colspan="6">Veri yüklenemedi. Lütfen JSON dosyasının var olduğundan ve sunucunun çalıştığından emin olun.</td></tr>`;
    }
}

function renderTable(data, criticalOnly, horizon) {
    const tbody = document.getElementById("table-body");
    tbody.innerHTML = ""; // Temizle

    if (!data || !data.skus) return;

    let totalOrders = 0;
    let totalUrgent = 0;

    // Verileri dinamik dinamik hesapla
    let processedSkus = data.skus.map(item => {
        // Dinamik tahmin hesabı
        let cumDemand = 0;
        if (item.forecast_monthly && item.forecast_monthly.length > 0) {
            // Slider değeri kadar ayı topla
            const limit = Math.min(horizon, item.forecast_monthly.length);
            for (let i = 0; i < limit; i++) {
                cumDemand += item.forecast_monthly[i];
            }
        } else {
            // Fallback (eski json ise)
            cumDemand = horizon <= 3 ? item.forecast_3m : item.forecast_6m;
        }

        let rawOrder = cumDemand - item.current_stock;
        let finalOrder = 0;
        let urgencyObj = "🟢 Güvenli";
        
        if (rawOrder > 0) {
            finalOrder = Math.max(rawOrder, item.moq || 0);
            if (item.lot_size && item.lot_size > 1) {
                finalOrder = Math.ceil(finalOrder / item.lot_size) * item.lot_size;
            } else {
                finalOrder = Math.ceil(finalOrder); // Tamsayıya yuvarla
            }
            urgencyObj = "🔴 Kritik"; // Stok bu ufukta tükenecek, sipariş şart.
            totalUrgent++;
        } else if (cumDemand > 0 && item.current_stock <= cumDemand * 1.25) {
            // Sipariş gerekmese de eldeki stok ihtiyacın yalnızca %25 veya daha azı kadar kalmış
            urgencyObj = "🟡 Riskli";
        }
        
        if (finalOrder > 0) totalOrders++;

        return {
            ...item,
            dyn_cum_demand: cumDemand,
            dyn_order_qty: finalOrder,
            dyn_urgency: urgencyObj
        };
    });

    // KPI Güncelle
    document.getElementById("kpi-orders").textContent = totalOrders;
    document.getElementById("kpi-urgent").textContent = totalUrgent;

    // Sıralama (Kritik > Riskli > Güvenli)
    processedSkus.sort((a, b) => {
        const pA = a.dyn_urgency.includes("Kritik") ? 1 : a.dyn_urgency.includes("Riskli") ? 2 : 3;
        const pB = b.dyn_urgency.includes("Kritik") ? 1 : b.dyn_urgency.includes("Riskli") ? 2 : 3;
        
        if (pA !== pB) return pA - pB;
        // Sonra Sipariş miktarı (büyükten küçüğe)
        return b.dyn_order_qty - a.dyn_order_qty;
    });

    if (criticalOnly) {
        processedSkus = processedSkus.filter(s => s.dyn_urgency.includes("Kritik"));
    }

    processedSkus.forEach(item => {
        const isCritical = item.dyn_urgency.includes("Kritik");
        const isRisk = item.dyn_urgency.includes("Riskli");
        
        // Row sınıfı belirleme
        let rowClass = "row-safe";
        let badgeClass = "badge-safe";
        
        if (isCritical) {
            rowClass = "row-critical";
            badgeClass = "badge-critical";
        } else if (isRisk) { 
            rowClass = "row-warning";
            badgeClass = "badge-warning";
        }

        const tr = document.createElement("tr");
        tr.className = rowClass;

        const p3mVal = (item.p_stockout_3m * 100).toFixed(0);
        const p6mVal = (item.p_stockout_6m * 100).toFixed(0);
        
        tr.innerHTML = `
            <td>
                <div class="sku-col">
                    <span class="sku-name tooltip-container tooltip-left">
                        ${item.sku}
                        <div class="tooltip-card">
                            <div><strong>Model:</strong> ${item.model}</div>
                            <div style="margin-top:4px;"><strong>3A Tahmin:</strong> ${item.forecast_3m.toFixed(1)}</div>
                            <div><strong>6A Tahmin:</strong> ${item.forecast_6m.toFixed(1)}</div>
                        </div>
                    </span>
                    <span class="badge badge-profile">${item.profile}</span>
                </div>
            </td>
            <td class="tabular-nums">${item.current_stock.toLocaleString()}</td>
            <td class="tabular-nums">${Math.ceil(item.dyn_cum_demand).toLocaleString()} <span style="font-size:0.75rem; color:#888;">(${horizon} Ay)</span></td>
            <td>
                <div class="tooltip-container">
                    <strong>%${p3mVal}</strong> / %${p6mVal}
                    <div class="tooltip-card">
                        <div style="margin-bottom:4px;">Stoksuz Kalma Olasılığı</div>
                        <div class="sparkline-row">
                            <span style="min-width:35px;">3 Ay:</span>
                            <div class="bar-bg">
                                <div class="bar-fill" style="width: ${p3mVal}%; background: ${p3mVal > 50 ? 'var(--color-red)' : 'var(--color-green)'}"></div>
                            </div>
                            <span style="margin-left:4px; font-weight:600; font-size:0.7rem;">%${p3mVal}</span>
                        </div>
                        <div class="sparkline-row">
                            <span style="min-width:35px;">6 Ay:</span>
                            <div class="bar-bg">
                                <div class="bar-fill" style="width: ${p6mVal}%; background: ${p6mVal > 50 ? 'var(--color-red)' : 'var(--color-green)'}"></div>
                            </div>
                            <span style="margin-left:4px; font-weight:600; font-size:0.7rem;">%${p6mVal}</span>
                        </div>
                    </div>
                </div>
            </td>
            <td>
                <span class="badge ${badgeClass}">${item.dyn_urgency}</span>
            </td>
            <td class="text-right tabular-nums" style="font-weight: 700; font-size: 1.1rem; color: ${isCritical ? 'var(--color-red)' : 'inherit'}">
                ${item.dyn_order_qty.toLocaleString()}
            </td>
        `;

        tbody.appendChild(tr);
    });
}
