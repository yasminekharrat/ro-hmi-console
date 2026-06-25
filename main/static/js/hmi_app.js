// Elapsed time formatter for alarm duration column
function _fmtDuration(ms) {
    const s = Math.floor(ms / 1000);
    if (s < 60)  return s + 's';
    const m = Math.floor(s / 60);
    if (m < 60)  return m + 'm ' + (s % 60) + 's';
    const h = Math.floor(m / 60);
    return h + 'h ' + (m % 60) + 'm';
}

class HmiApplicationCore {
    // ─── CLASS FIELDS ────────────────────────────────────────────────────────
    isConnected = false;
    tagConfig = [];
    activeAlarms = {};
    acknowledgedAlarms = new Set();
    mockAlarmsList = [];
    _scanInterval = null;
    _alarmInterval = null;
    _durationInterval = null;

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

        // Lightweight duration-column refresh every 5s (no full re-render)
        this._durationInterval = setInterval(() => this._refreshDurationCells(), 5000);

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
            const wasActive = !!this.activeAlarms[rule.id];

            if (rule.active) {
                if (!wasActive) {
                    HmiRenderer.appendEventLog(`ALARME ACTIVE: ${rule.label} (${rule.severity})`, "CRIT_ALM", rule.severity === 'CRITICAL');
                    this.activeAlarms[rule.id] = {
                        timestamp: rule.last_evaluated || new Date().toLocaleTimeString('fr-FR'),
                        onset_ms: Date.now()
                    };
                }

                currentAlarmsList.push({
                    id:        rule.id,
                    timestamp: this.activeAlarms[rule.id].timestamp,
                    onset_ms:  this.activeAlarms[rule.id].onset_ms,
                    tag:       rule.id.toUpperCase(),
                    message:   rule.label,
                    group:     rule.group  || '',
                    icon:      rule.icon   || 'fa-solid fa-triangle-exclamation',
                    threshold: rule.threshold,
                    unit:      rule.unit   || '',
                    whatsapp:  rule.whatsapp || false,
                    severity:  rule.severity,
                    acked:     this.acknowledgedAlarms.has(rule.id)
                });

                if (rule.severity === 'CRITICAL') criticalCount++;
                else warningCount++;
            } else {
                if (wasActive) {
                    HmiRenderer.appendEventLog(`Résolu: ${rule.label} normalisé`, "SYS_NORM");
                    delete this.activeAlarms[rule.id];
                    this.acknowledgedAlarms.delete(rule.id);
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
        const tbody       = document.getElementById('alarm-table-body');
        const emptyRow    = document.getElementById('alarm-empty-row');
        const countBadge  = document.getElementById('alarm-count-badge');
        const statusText  = document.getElementById('alarm-system-status');
        const statusDot   = document.getElementById('alarm-status-dot');
        const critEl      = document.getElementById('count-critical');
        const warnEl      = document.getElementById('count-warning');
        const pollEl      = document.getElementById('alarm-poll-indicator');

        if (!tbody) return;

        if (countBadge) { countBadge.innerText = alarms.length + ' ACT.'; countBadge.classList.toggle('hidden', alarms.length === 0); }
        if (critEl) critEl.innerText = criticals;
        if (warnEl) warnEl.innerText = warnings;
        if (pollEl) { pollEl.textContent = '● ACTIF'; pollEl.style.color = '#10b981'; }

        if (alarms.length === 0) {
            if (emptyRow) emptyRow.style.display = '';
            tbody.innerHTML = '';
            tbody.appendChild(emptyRow);
            if (statusText) { statusText.textContent = 'NOMINAL'; statusText.className = 'text-emerald-700 uppercase tracking-wide font-bold plc-mono'; }
            if (statusDot)  { statusDot.className = 'w-2 h-2 rounded-full bg-emerald-500 inline-block ml-1'; }
            const icon = document.getElementById('alarm-title-icon');
            if (icon) { icon.className = 'fa-solid fa-shield-check text-emerald-400 text-[11px]'; }
            return;
        }

        if (emptyRow) emptyRow.style.display = 'none';
        const hasCrit = criticals > 0;
        if (statusText) {
            statusText.textContent = hasCrit ? 'DÉFAUT CRITIQUE' : 'ALERTE';
            statusText.className = hasCrit
                ? 'text-[#FF0044] uppercase tracking-wide font-bold plc-mono animate-pulse'
                : 'text-amber-500 uppercase tracking-wide font-bold plc-mono';
        }
        if (statusDot) {
            statusDot.className = hasCrit
                ? 'w-2 h-2 rounded-full bg-red-600 inline-block ml-1 animate-pulse'
                : 'w-2 h-2 rounded-full bg-amber-500 inline-block ml-1';
        }
        const icon = document.getElementById('alarm-title-icon');
        if (icon) {
            icon.className = hasCrit
                ? 'fa-solid fa-triangle-exclamation text-[#FF0044] text-[11px] animate-pulse'
                : 'fa-solid fa-circle-exclamation text-amber-400 text-[11px]';
        }

        const now = Date.now();
        let rowsHtml = '';
        alarms.forEach(alarm => {
            const isCrit  = alarm.severity === 'CRITICAL';
            const isAcked = alarm.acked;

            // Light-theme row colors matching the HMI design language
            const rowCls  = isCrit
                ? 'bg-red-50 hover:bg-red-100/70'
                : 'bg-amber-50/60 hover:bg-amber-100/50';
            const sevText = isCrit ? 'text-red-700' : 'text-amber-800';
            const sevClr  = isCrit ? '#b91c1c' : '#92400e';
            const dotCls  = isCrit
                ? `w-2 h-2 rounded-full bg-red-600 mx-auto ${isAcked ? '' : 'animate-pulse'}`
                : `w-2 h-2 rounded-full bg-amber-500 mx-auto ${isAcked ? '' : 'animate-pulse'}`;

            const durStr  = alarm.onset_ms ? _fmtDuration(now - alarm.onset_ms) : '—';

            const valStr  = alarm.threshold !== null && alarm.threshold !== undefined
                ? `<span class="font-bold ${sevText}">${alarm.threshold}</span> <span class="text-[#8A9195] text-[8px]">${alarm.unit}</span>`
                : `<span class="font-bold ${sevText}">ACTIVE</span>`;

            const waIcon  = alarm.whatsapp
                ? `<i class="fa-brands fa-whatsapp text-[#059669] text-[11px]"></i>`
                : `<span class="text-[#C5CBD0]">—</span>`;

            const ackBtn  = isAcked
                ? `<span class="text-[8px] font-bold uppercase text-emerald-700 plc-mono">ACQ ✓</span>`
                : (isCrit
                    ? `<button onclick="HmiApp.acknowledgeSingleAlarm('${alarm.id}')" class="px-1.5 py-0.5 bg-red-600 hover:bg-red-700 text-white font-bold rounded-sm text-[8px] uppercase tracking-wide transition-all shadow-sm active:translate-y-px">ACQ</button>`
                    : `<button onclick="HmiApp.acknowledgeSingleAlarm('${alarm.id}')" class="px-1.5 py-0.5 bg-amber-500 hover:bg-amber-600 text-white font-bold rounded-sm text-[8px] uppercase tracking-wide transition-all shadow-sm active:translate-y-px">ACQ</button>`);

            rowsHtml += `
                <tr class="${rowCls} transition-colors border-b border-[#DFE4E6] text-[10px]">
                    <td class="p-2 text-center border-r border-[#DFE4E6]"><div class="${dotCls}"></div></td>
                    <td class="p-2 border-r border-[#DFE4E6] text-[#52575A] whitespace-nowrap plc-mono">${alarm.timestamp}</td>
                    <td class="p-2 border-r border-[#DFE4E6] text-[#8A9195] whitespace-nowrap plc-mono" data-onset="${alarm.onset_ms || 0}">${durStr}</td>
                    <td class="p-2 border-r border-[#DFE4E6] text-[#52575A] text-[9px] uppercase tracking-wide plc-mono">${alarm.group || '—'}</td>
                    <td class="p-2 border-r border-[#DFE4E6]">
                        <div class="flex items-center gap-1.5 ${sevText}">
                            <i class="${alarm.icon} text-[9px]"></i>
                            <span class="font-bold">${alarm.message}</span>
                        </div>
                    </td>
                    <td class="p-2 border-r border-[#DFE4E6] plc-mono whitespace-nowrap">${valStr}</td>
                    <td class="p-2 border-r border-[#DFE4E6] text-center">${waIcon}</td>
                    <td class="p-2 text-center">${ackBtn}</td>
                </tr>`;
        });

        tbody.innerHTML = rowsHtml;
    }

    // Update only the duration cells — avoids a full re-render on every tick
    _refreshDurationCells() {
        const now = Date.now();
        document.querySelectorAll('#alarm-table-body td[data-onset]').forEach(td => {
            const onset = parseInt(td.dataset.onset, 10);
            if (onset > 0) td.textContent = _fmtDuration(now - onset);
        });
    }

    // ─── PLC ACTIONS ─────────────────────────────────────────────────────────
    acknowledgeSingleAlarm(id) {
        this.acknowledgedAlarms.add(id);
        if (typeof HmiRenderer !== 'undefined') HmiRenderer.appendEventLog(`Acquitté: [${id}]`, "SYS_ACK");
        // Re-render immediately so ACQ button becomes ✓
        this._fetchServerAlarms();
    }

    acknowledgeAllAlarms() {
        Object.keys(this.activeAlarms).forEach(id => this.acknowledgedAlarms.add(id));
        if (typeof HmiRenderer !== 'undefined') HmiRenderer.appendEventLog("Acquittement global: toutes les alarmes actives.", "SYS_ACK");
        this._fetchServerAlarms();
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

// SynopticHMI is defined as window.SynopticHMI in synoptic.js (loaded before this file).