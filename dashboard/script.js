// Verileri tutacağımız global değişken
let dashboardData = null;

// DOM Yüklendiğinde
document.addEventListener("DOMContentLoaded", () => {
    fetchData();
    
    // Toggle Event Listener
    const toggle = document.getElementById("filter-critical-toggle");
    toggle.addEventListener("change", (e) => {
        renderTable(dashboardData, e.target.checked);
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
        document.getElementById("kpi-orders").textContent = dashboardData.order_count;
        document.getElementById("kpi-urgent").textContent = dashboardData.urgent_count;

        // Tabloyu çiz
        renderTable(dashboardData, false);
    } catch (error) {
        console.error("Fetch error:", error);
        document.getElementById("last-updated").textContent = "Hata: Veri çekilemedi.";
        document.getElementById("table-body").innerHTML = `<tr><td colspan="6">Veri yüklenemedi. Lütfen JSON dosyasının var olduğundan ve sunucunun çalıştığından emin olun.</td></tr>`;
    }
}

function renderTable(data, criticalOnly) {
    const tbody = document.getElementById("table-body");
    tbody.innerHTML = ""; // Temizle

    if (!data || !data.skus) return;

    // Kopyasını alıp sıralayalım (Kritik olanlar üstte: p_stockout_3m'ye göre veya urgency'ye göre)
    let skus = [...data.skus];
    
    // Sıralama (Kritikler üstte)
    skus.sort((a, b) => {
        // Önce Aciliyet
        if (a.urgency.includes("ACİL") && !b.urgency.includes("ACİL")) return -1;
        if (!a.urgency.includes("ACİL") && b.urgency.includes("ACİL")) return 1;
        // Sonra Sipariş miktarı (büyükten küçüğe)
        return b.order_qty - a.order_qty;
    });

    if (criticalOnly) {
        skus = skus.filter(s => s.urgency.includes("ACİL"));
    }

    skus.forEach(item => {
        const isCritical = item.urgency.includes("ACİL");
        const isSafe = item.urgency.includes("GÜVENDE");
        
        // Row sınıfı belirleme
        let rowClass = "row-safe";
        let badgeClass = "badge-safe";
        
        if (isCritical) {
            rowClass = "row-critical";
            badgeClass = "badge-critical";
        } else if (!isSafe) { // "NORMAL" veya uyarı durumu varsa (yok gerçi ama fallback)
            rowClass = "row-warning";
            badgeClass = "badge-warning";
        }

        const tr = document.createElement("tr");
        tr.className = rowClass;

        // Tooltip içerik hazırlığı (Mini data)
        const p3mVal = (item.p_stockout_3m * 100).toFixed(0);
        const p6mVal = (item.p_stockout_6m * 100).toFixed(0);
        
        tr.innerHTML = `
            <td>
                <div class="sku-col">
                    <span class="sku-name tooltip-container">
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
            <td class="tabular-nums">${item.cum_demand_6m ? item.cum_demand_6m.toLocaleString() : "-"}</td>
            <td>
                <div class="tooltip-container">
                    <strong>%${p3mVal}</strong> / %${p6mVal}
                    <div class="tooltip-card">
                        <div style="margin-bottom:4px;">Stoksuz Kalma Olasılığı</div>
                        <div class="sparkline-row">
                            <span style="width:20px;">3 Ay:</span>
                            <div class="bar-bg">
                                <div class="bar-fill" style="width: ${p3mVal}%; background: ${p3mVal > 50 ? 'var(--color-red)' : 'var(--color-green)'}"></div>
                            </div>
                        </div>
                        <div class="sparkline-row">
                            <span style="width:20px;">6 Ay:</span>
                            <div class="bar-bg">
                                <div class="bar-fill" style="width: ${p6mVal}%; background: ${p6mVal > 50 ? 'var(--color-red)' : 'var(--color-green)'}"></div>
                            </div>
                        </div>
                    </div>
                </div>
            </td>
            <td>
                <span class="badge ${badgeClass}">${item.urgency}</span>
            </td>
            <td class="text-right tabular-nums" style="font-weight: 700; font-size: 1.1rem; color: ${isCritical ? 'var(--color-red)' : 'inherit'}">
                ${item.order_qty.toLocaleString()}
            </td>
        `;

        tbody.appendChild(tr);
    });
}
