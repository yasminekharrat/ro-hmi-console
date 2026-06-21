/**
 * Hydraulics Instrumentation Telemetry Script
 * Location: modules/hydraulics/hyd_comms.js
 */

let hydPollingInterval = null;

function startHydraulicsPolling() {
    if (hydPollingInterval) clearInterval(hydPollingInterval);

    hydPollingInterval = setInterval(async () => {
        try {
            const response = await fetch('/api/hydraulics/status');
            const data = await response.json();

            if (data.status === "ONLINE") {
                // Update numerical values
                document.getElementById('hyd-press').innerText = data.pressure.toFixed(1);
                document.getElementById('hyd-flow').innerText = data.flow_rate.toFixed(1);
                document.getElementById('hyd-temp').innerText = data.temperature.toFixed(1);

                // Update progress bars (Assuming 3000 PSI max, 50 GPM max, 100°C max bounds)
                const pressPct = Math.min((data.pressure / 3000) * 100, 100);
                const flowPct = Math.min((data.flow_rate / 50) * 100, 100);
                const tempPct = Math.min((data.temperature / 100) * 100, 100);

                document.getElementById('hyd-press-bar').style.width = `${pressPct}%`;
                document.getElementById('hyd-flow-bar').style.width = `${flowPct}%`;
                document.getElementById('hyd-temp-bar').style.width = `${tempPct}%`;
            }
        } catch (err) {
            console.error("Hydraulics Fieldbus Communication Error:", err);
        }
    }, 500); // 500ms analog loop refresh cycle
}

document.addEventListener("DOMContentLoaded", startHydraulicsPolling);