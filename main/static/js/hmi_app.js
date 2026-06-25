class HmiApplicationCore {
    // ─── CLASS FIELDS ────────────────────────────────────────────────────────
    isConnected = false;
    tagConfig = [];
    activeAlarms = {}; 
    mockAlarmsList = []; 
    _scanInterval = null;
    _alarmInterval = null;

    // FIX: Declare your top-level functional tab matrix right here!
    tabs = ['synoptic', 'dataview', 'alarms', 'settings'];
    currentTab = 'synoptic';

    constructor() {
        // Initialization handled in init()
    }

    // ─── INITIALIZATION & CONNECTION ─────────────────────────────────────────
    async init() {
        HmiRenderer.appendEventLog("System initialization sequence...", "SYS_INIT");
        
        // FIX: Force the initial active view state to show up on DOM mount!
        this.initializeDefaultRouting();

        try {
            this.tagConfig = await HmiCommsService.fetchConfig();
            HmiRenderer.buildDataGrid(this.tagConfig);
            HmiRenderer.appendEventLog(`Loaded ${this.tagConfig.length} component blocks. Ready.`, "SYS_RDY");
        } catch (e) {
            HmiRenderer.appendEventLog("Failed loading tag configuration.", "CRIT_ERR", true);
            console.error(e);
        }
        
        // Start telemetry loop at 500ms
        this._scanInterval = setInterval(() => this._scanCycle(), 500);

        // Start dedicated alarm state sync loop at 1000ms
        this._alarmInterval = setInterval(() => this._fetchServerAlarms(), 1000);

        // Set up Global handler for the Ack button inside the HTML component
        document.addEventListener('click', (e) => {
            if (e.target && e.target.id === 'btn-ack-all') {
                this.acknowledgeAllAlarms();
            }
        });
    }

    // FIX: Add this routing initialization helper method
    initializeDefaultRouting() {
        this.tabs.forEach(tab => {
            const viewElement = document.getElementById(`view-${tab}`);
            if (!viewElement) return;

            if (tab === this.currentTab) {
                viewElement.classList.remove('hidden');
                // Ensure synoptic container opens up with flex properties intact
                if (tab === 'synoptic') {
                    viewElement.classList.add('flex');
                } else {
                    viewElement.classList.add('block');
                }
            } else {
                viewElement.classList.remove('block', 'flex');
                viewElement.classList.add('hidden');
            }
        });
    }

    async establishConnection() {
        const ip = document.getElementById('ip')?.value || '192.168.1.10';
        const slot = document.getElementById('slot-select')?.value || 1;

        HmiRenderer.appendEventLog(`Connecting to ${ip} slot=${slot}...`, "NET_CONN");
        const res = await HmiCommsService.establishLink(ip, slot);

        const dot = document.getElementById('status-dot');
        if (res && res.status === 'success') {
            HmiRenderer.appendEventLog(`ONLINE: ${res.message}`, "S7_PROT");
            if (dot) dot.className = "w-3 h-3 bg-[#00FF55] border border-[#053614] shadow-[0_0_6px_#00FF55] rounded-full";
            this.isConnected = true;
        } else {
            HmiRenderer.appendEventLog(`OFFLINE: ${res?.message || 'Connection failed'}`, "NET_ERR", true);
            if (dot) dot.className = "w-3 h-3 bg-[#FF0044] border border-[#21020A] rounded-full";
            this.isConnected = false;
        }
    }

    // ─── TELEMETRY & SCAN CYCLE ──────────────────────────────────────────────
    async _scanCycle() {
        if (!this.isConnected) return;
        try {
            const data = await HmiCommsService.getBulkTelemetry();
            if (!data || data.status === 'error') return;

            // Route data to synoptic and data-view
            if (typeof SynopticHMI !== 'undefined') SynopticHMI.updateSynoptic(data);
            if (typeof HmiRenderer !== 'undefined') HmiRenderer.updateDataGrid(data);

        } catch (err) {
            // Silent — avoid flooding log on transient errors
            console.warn("Scan cycle gap:", err.message);
        }
    }

    // ─── ALARM ENGINE FETCH SYNC ─────────────────────────────────────────────
    async _fetchServerAlarms() {
        try {
            const res = await fetch('/api/alarms/status');
            if (!res.ok) return;
            
            const data = await res.json(); // Structure matches alarm_engine.get_status()
            if (!data || !data.rules) return;

            this._processEngineAlarms(data.rules);
        } catch (err) {
            console.warn("Alarm service status fetch gap:", err.message);
        }
    }

    _processEngineAlarms(rules) {
        const alarmBadge = document.getElementById('alarm-badge');
        let currentAlarmsList = [];
        let criticalCount = 0;
        let warningCount = 0;

        rules.forEach(rule => {
            // Check state changes to log actions transitions natively in event grid
            const wasActive = !!this.activeAlarms[rule.id];
            
            if (rule.active) {
                if (!wasActive) {
                    HmiRenderer.appendEventLog(`ALARME ACTIVE: ${rule.label} (${rule.severity})`, "CRIT_ALM", rule.severity === 'CRITICAL');
                    this.activeAlarms[rule.id] = { timestamp: rule.last_evaluated || new Date().toLocaleTimeString('fr-FR') };
                }

                currentAlarmsList.push({
                    id: rule.id,
                    timestamp: this.activeAlarms[rule.id].timestamp,
                    tag: rule.id.toUpperCase(),
                    message: rule.label,
                    value: rule.threshold !== null ? `Seuil: ${rule.threshold}` : "ACTIVE",
                    unit: rule.unit || "",
                    severity: rule.severity // "CRITICAL" | "WARNING"
                });

                if (rule.severity === 'CRITICAL') criticalCount++;
                else warningCount++;
            } else {
                if (wasActive) {
                    HmiRenderer.appendEventLog(`Résolu: ${rule.label} normalisé`, "SYS_NORM");
                    delete this.activeAlarms[rule.id];
                }
            }
        });

        // Update top-level KPI strip alarm badge visibility
        if (alarmBadge) {
            alarmBadge.classList.toggle('hidden', currentAlarmsList.length === 0);
        }

        // Render live changes directly onto UI layouts
        this.renderAlarmPanelUI(currentAlarmsList, criticalCount, warningCount);
    }

    // ─── MOCK ALARM LOGIC ────────────────────────────────────────────────────
    mockSystemAlarm(severity, tag, message, value, unit) {
        const now = new Date();
        const timestamp = now.toLocaleDateString() + ' ' + now.toLocaleTimeString();
        
        const newAlarm = {
            id: 'mock_' + Math.random().toString(36).substring(2, 11),
            timestamp: timestamp,
            tag: tag,
            message: message,
            value: value,
            unit: unit,
            severity: severity // 'CRITICAL' or 'WARNING'
        };

        this.mockAlarmsList.push(newAlarm);
        this.refreshMockUI();
    }

    refreshMockUI() {
        const critCount = this.mockAlarmsList.filter(a => a.severity === 'CRITICAL').length;
        const warnCount = this.mockAlarmsList.filter(a => a.severity === 'WARNING').length;
        
        this.renderAlarmPanelUI(this.mockAlarmsList, critCount, warnCount);
    }

    // ─── UI RENDERING ────────────────────────────────────────────────────────
    renderAlarmPanelUI(alarms, criticals, warnings) {
        const tbody = document.getElementById('alarm-table-body');
        const emptyRow = document.getElementById('alarm-empty-row');
        const countBadge = document.getElementById('alarm-count-badge');
        const systemStatus = document.getElementById('alarm-system-status');
        const critEl = document.getElementById('count-critical');
        const warnEl = document.getElementById('count-warning');

        if (!tbody) return;

        if (countBadge) countBadge.innerText = alarms.length;
        if (critEl) critEl.innerText = criticals;
        if (warnEl) warnEl.innerText = warnings;

        // No active alarms
        if (alarms.length === 0) {
            if (emptyRow) emptyRow.style.display = '';
            if (systemStatus) {
                systemStatus.innerText = 'OK';
                systemStatus.className = 'text-emerald-700 uppercase tracking-wide font-bold';
            }
            tbody.innerHTML = '';
            if (emptyRow) tbody.appendChild(emptyRow);
            return;
        }

        // Active alarms exist
        if (emptyRow) emptyRow.style.display = 'none';
        if (systemStatus) {
            systemStatus.innerText = 'ALERTE INSTABLE';
            systemStatus.className = 'text-[#FF0044] uppercase tracking-wide font-bold';
        }

        let rowsHtml = '';
        alarms.forEach(alarm => {
            const rowBg = alarm.severity === 'CRITICAL' ? 'bg-red-50 hover:bg-red-100/70' : 'bg-amber-50/60 hover:bg-amber-100/50';
            const textColor = alarm.severity === 'CRITICAL' ? 'text-red-700' : 'text-amber-800';
            const pulseColor = alarm.severity === 'CRITICAL' ? 'bg-red-600' : 'bg-amber-500';
            
            const statusButton = alarm.severity === 'CRITICAL' 
                ? `<button onclick="HmiApp.acknowledgeSingleAlarm('${alarm.id}')" class="px-1.5 py-0.5 bg-red-600 hover:bg-red-700 text-white font-bold rounded-sm text-[8px] uppercase tracking-wide transition-all shadow-sm active:translate-y-px">CRIT [Ack]</button>` 
                : `<button onclick="HmiApp.acknowledgeSingleAlarm('${alarm.id}')" class="px-1.5 py-0.5 bg-amber-500 hover:bg-amber-600 text-white font-bold rounded-sm text-[8px] uppercase tracking-wide transition-all shadow-sm active:translate-y-px">WARN [Ack]</button>`;

            rowsHtml += `
                <tr class="${rowBg} transition-colors border-b border-[#DFE4E6] text-[#111111]">
                    <td class="p-2 border-r border-[#DFE4E6] text-[#52575A] whitespace-nowrap font-sans">${alarm.timestamp}</td>
                    <td class="p-2 border-r border-[#DFE4E6] font-bold ${textColor}">${alarm.tag}</td>
                    <td class="p-2 border-r border-[#DFE4E6] font-sans font-medium text-gray-800">
                        <span class="inline-block w-1.5 h-1.5 rounded-full ${pulseColor} animate-pulse mr-2"></span>
                        ${alarm.message}
                    </td>
                    <td class="p-2 border-r border-[#DFE4E6] font-bold text-gray-700">${alarm.value} <span class="text-gray-400 font-normal text-[8px]">${alarm.unit}</span></td>
                    <td class="p-2 text-center">${statusButton}</td>
                </tr>
            `;
        });

        tbody.innerHTML = rowsHtml;
        if (emptyRow) tbody.appendChild(emptyRow);
    }

    // ─── PLC ACTIONS ─────────────────────────────────────────────────────────
    acknowledgeSingleAlarm(id) {
        if (typeof HmiRenderer !== 'undefined') HmiRenderer.appendEventLog(`Alarm manually acknowledged: [${id}]`, "SYS_ACK");
    }

    acknowledgeAllAlarms() {
        if (typeof HmiRenderer !== 'undefined') HmiRenderer.appendEventLog("Global clear issued: Acquitting all active system registers.", "SYS_ACK");
    }

    async triggerWrite(db, offset, value) {
        if (!this.isConnected) {
            HmiRenderer.appendEventLog("Action aborted: PLC offline.", "SYS_ERR", true);
            return;
        }
        try {
            const res = await HmiCommsService.writeTag(db, offset, value);
            if (res?.status === 'success') {
                HmiRenderer.appendEventLog(`Write OK: DB${db}.${offset} ← ${value}`, "PLC_WR");
            } else {
                HmiRenderer.appendEventLog(`Write failed: ${res?.message}`, "WR_ERR", true);
            }
        } catch (e) {
            HmiRenderer.appendEventLog("Write exception.", "WR_ERR", true);
        }
    }

    // ─── WRITE BY TAG NAME (looks up db/offset from tags_config.py server-side) ──
    // Use this instead of triggerWrite() for anything wired to a named tag in
    // config/tags_config.py — it calls /api/write-tag, which refuses to write
    // any tag not explicitly marked "writable": True server-side. This is the
    // only write path that keeps tags_config.py as the single edit point: no
    // db/offset is ever hardcoded in the frontend for these calls.
    async triggerWriteByTag(tagId, value) {
        if (!this.isConnected) {
            HmiRenderer.appendEventLog("Action aborted: PLC offline.", "SYS_ERR", true);
            return;
        }
        try {
            const res = await fetch('/api/write-tag', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ tag_id: tagId, value: value })
            });
            const data = await res.json();
            if (data?.status === 'success') {
                HmiRenderer.appendEventLog(`Write OK: ${tagId} ← ${value} (${data.message})`, "PLC_WR");
            } else {
                HmiRenderer.appendEventLog(`Write failed [${tagId}]: ${data?.message}`, "WR_ERR", true);
            }
        } catch (e) {
            HmiRenderer.appendEventLog(`Write exception [${tagId}].`, "WR_ERR", true);
        }
    }
}

// ─── INSTANTIATION ───────────────────────────────────────────────────────────
const HmiApp = new HmiApplicationCore();
document.addEventListener("DOMContentLoaded", () => HmiApp.init());