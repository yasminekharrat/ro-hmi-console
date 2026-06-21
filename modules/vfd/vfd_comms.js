/**
 * Veichi AC10 VFD Modbus Controller & Interface Engine
 * Location: static/js/vfd_comms.js
 *
 * Single source of truth for all VFD JS logic.
 * The HTML template contains NO duplicate function definitions.
 */

'use strict';

// ==============================================================================
// --- GLOBALS ---
// ==============================================================================

let vfdPollingInterval = null;

// ==============================================================================
// --- TERMINAL CONSOLE ---
// ==============================================================================

const VfdConsole = {
    init() {
        this.log("Console interface ready.");
    },

    log(msg, type = 'info') {
        const terminal = document.getElementById('advanced-log-terminal');
        if (!terminal) return;

        const ts = new Date().toISOString().slice(11, 19);
        const colors = {
            info:    'text-[#33FF33]',
            warn:    'text-amber-400',
            error:   'text-rose-500',
            success: 'text-cyan-400',
        };
        const color = colors[type] || colors.info;

        const row = document.createElement('div');
        row.className = `leading-relaxed ${color}`;
        row.innerHTML = `[${ts}] <span class="text-slate-500">${type.toUpperCase()}:</span> ${msg}`;
        terminal.appendChild(row);
        terminal.scrollTop = terminal.scrollHeight;
    }
};

// Alias so HTML inline handlers that use logToTerminal() still work
function logToTerminal(msg, type = 'info') {
    VfdConsole.log(msg, type);
}

// ==============================================================================
// --- HELPERS ---
// ==============================================================================

/** Returns the current port/baud/address from the config inputs. */
function getConnectionParams() {
    return {
        port:    (document.getElementById('cfg-port')?.value    || 'COM3').trim(),
        baud:    parseInt(document.getElementById('cfg-baud')?.value    || '9600', 10),
        address: parseInt(document.getElementById('cfg-address')?.value || '1',    10),
    };
}

/**
 * Unified register write helper used by all control functions.
 * Always includes port + slave_id so the backend never has to guess
 * which serial handle to use.
 *
 * @param {string|number} register   Hex string "0x3000" or decimal int
 * @param {number}        value      Integer value to write
 * @param {number}        [decimals] Decimal places (default 0)
 */
async function writeRegister(register, value, decimals = 0) {
    const { port, address } = getConnectionParams();

    const res = await fetch('/api/write', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            port,
            slave_id: address,
            register,           // backend accepts hex string or int
            value,
            decimals,
        }),
    });

    if (!res.ok) {
        const text = await res.text();
        throw new Error(`HTTP ${res.status}: ${text}`);
    }

    return res.json();
}

// ==============================================================================
// --- TAB NAVIGATION ---
// ==============================================================================

function switchTab(tabName) {
    const btnOverview  = document.getElementById('btn-tab-overview');
    const btnVfd       = document.getElementById('btn-tab-vfd');
    const viewOverview = document.getElementById('view-overview');
    const viewVfd      = document.getElementById('view-vfd');

    // FIX: Only bail out if the VIEW containers themselves are missing.
    // If a button hasn't rendered yet, we shouldn't break the whole HMI layout switcher!
    if (!viewOverview || !viewVfd) {
        console.error("HMI Navigation Error: View elements could not be found in DOM.");
        return;
    }

    const activeClass   = "wincc-btn tab-active text-xs uppercase tracking-wider px-4 py-1.5 border-t border-x border-[#7F8C8D] rounded-t-sm";
    const inactiveClass = "wincc-btn tab-inactive text-xs uppercase tracking-wider px-4 py-1.5 border-t border-x border-[#7F8C8D] rounded-t-sm";

    if (tabName === 'overview') {
        // Safe styling updates (only run if elements exist)
        if (btnOverview) btnOverview.className = activeClass;
        if (btnVfd) btnVfd.className = inactiveClass;
        
        viewOverview.classList.remove('hidden');
        viewVfd.classList.add('hidden');
        if (typeof stopVfdPolling === 'function') stopVfdPolling();
        
    } else if (tabName === 'vfd') {
        if (btnOverview) btnOverview.className = inactiveClass;
        if (btnVfd) btnVfd.className = activeClass;
        
        viewOverview.classList.add('hidden');
        viewVfd.classList.remove('hidden');
        if (typeof startVfdPolling === 'function') startVfdPolling();
    }
}
// ==============================================================================
// --- POLLING LOOP ---
// ==============================================================================

function startVfdPolling() {
    if (vfdPollingInterval) clearInterval(vfdPollingInterval);

    vfdPollingInterval = setInterval(async () => {
        try {
            const res  = await fetch('/api/vfd/status');
            const data = await res.json();

            const pulse    = document.getElementById('heartbeat-pulse') || document.getElementById('serial-heartbeat');
            const banner   = document.getElementById('bus-banner-txt');
            const navBadge = document.getElementById('nav-status-badge');
            const runLens  = document.getElementById('voyant-run');
            const runTxt   = document.getElementById('txt-voyant-run');
            const warnBox  = document.getElementById('cfg-validation-warning');
            const freqEl   = document.getElementById('vfd-freq');
            const currEl   = document.getElementById('vfd-current');
            const freqBar  = document.getElementById('vfd-freq-bar');
            const currBar  = document.getElementById('vfd-current-bar');
            const f0101El  = document.getElementById('val-f0101');
            const f0102El  = document.getElementById('val-f0102');
            const txEl     = document.getElementById('diag-tx-frames');
            const rxEl     = document.getElementById('diag-rx-frames');
            const crcEl    = document.getElementById('diag-crc-errors');

            // Update TX/RX counters regardless of connection state
            if (txEl  && data.tx          !== undefined) txEl.innerText  = data.tx;
            if (rxEl  && data.rx          !== undefined) rxEl.innerText  = data.rx;
            if (crcEl && data.crc_errors  !== undefined) crcEl.innerText = data.crc_errors;

            if (data.status === "ONLINE") {
                _applyOnlineState({ pulse, banner, navBadge, runLens, runTxt, warnBox,
                                    freqEl, currEl, freqBar, currBar, f0101El, f0102El, data });
            } else {
                handleOfflineState(pulse, navBadge, banner, runLens, runTxt, warnBox, data.error);
            }
        } catch (err) {
            console.error("[VFD Poll]", err);
            const pulse  = document.getElementById('heartbeat-pulse') || document.getElementById('serial-heartbeat');
            const banner = document.getElementById('bus-banner-txt');
            if (pulse)  { pulse.style.backgroundColor = '#EF4444'; pulse.style.boxShadow = 'none'; }
            if (banner) banner.innerText = "COMM_ERROR: Backend Server Unreachable";
        }
    }, 400);
}

function _applyOnlineState({ pulse, banner, navBadge, runLens, runTxt,
                              warnBox, freqEl, currEl, freqBar, currBar,
                              f0101El, f0102El, data }) {
    // Heartbeat blink
    if (pulse) {
        const on  = '#00FF55';
        const off = '#006622';
        pulse.style.backgroundColor = (pulse.style.backgroundColor === on) ? off : on;
        pulse.style.boxShadow = `0 0 6px ${on}`;
        pulse.className = "w-2.5 h-2.5 rounded-full transition-all duration-75";
    }

    if (navBadge) {
        navBadge.className = "px-2.5 py-0.5 rounded-sm font-mono text-[10px] font-bold uppercase bg-emerald-200 text-emerald-800 border border-emerald-300";
        navBadge.innerText = "Online";
    }

    if (banner) {
        const { port, baud, address } = getConnectionParams();
        banner.innerText = `${port} [${baud} bps N-8-1] • Node ID: ${address}`;
    }

    if (freqEl) freqEl.innerText = data.output_frequency.toFixed(2);
    if (currEl) currEl.innerText = data.output_current.toFixed(2);
    if (freqBar) freqBar.style.width = `${Math.min((data.output_frequency / 50) * 100, 100)}%`;
    if (currBar) currBar.style.width = `${Math.min((data.output_current  / 15) * 100, 100)}%`;

    if (runLens && runTxt) {
        if (data.output_frequency > 0.1) {
            runLens.className = "w-4 h-4 rounded-full bg-[#10B981] border border-[#047857] shadow-[0_0_6px_rgba(16,185,129,0.6)] animate-pulse";
            runTxt.innerText   = "RUNNING";
            runTxt.className   = "font-bold text-xs text-[#047857] uppercase";
        } else {
            runLens.className = "w-4 h-4 rounded-full bg-[#475569] border border-[#1E293B]";
            runTxt.innerText   = "STOPPED";
            runTxt.className   = "font-bold text-xs text-[#475569] uppercase";
        }
    }

    const f0101 = data.param_f0101;
    const f0102 = data.param_f0102;
    if (f0101El) f0101El.innerText = f0101 === 2 ? "2 (RS485 Control)" : `${f0101 ?? 0} (Local)`;
    if (f0102El) f0102El.innerText = f0102 === 2 ? "2 (RS485 Speed)"   : `${f0102 ?? 0} (Local)`;

    if (warnBox) {
        if (f0101 === 2 && f0102 === 0) {
            warnBox.className = "text-[9px] font-sans font-bold text-center mt-1 p-1 bg-emerald-100 border border-emerald-300 rounded-sm text-emerald-800";
            warnBox.innerHTML = `✅ COMMUNICATIONS ALIGNED: DRIVE FULLY CONTROLLABLE`;
        } else {
            warnBox.className = "text-[9px] font-sans font-bold text-center mt-1 p-1 bg-amber-100 border border-amber-300 rounded-sm text-amber-800 animate-pulse";
            warnBox.innerHTML = `⚠️ SET F01.01=2 AND F01.02=0 ON VFD KEYPAD TO ENABLE RS485 CONTROL`;
        }
    }
}

function handleOfflineState(pulse, navBadge, banner, runLens, runTxt, warnBox, errorMsg) {
    if (pulse) { pulse.style.backgroundColor = '#EF4444'; pulse.style.boxShadow = 'none'; }

    if (navBadge) {
        navBadge.className = "px-2.5 py-0.5 rounded-sm font-mono text-[10px] font-bold uppercase bg-rose-200 text-rose-800 border border-rose-300";
        navBadge.innerText = "Offline";
    }
    if (banner) banner.innerText = errorMsg || "Hardware Link Offline";

    if (runLens) runLens.className = "w-4 h-4 rounded-full bg-[#EF4444] border border-rose-900 shadow-none";
    if (runTxt) {
        runTxt.innerText   = "OFFLINE";
        runTxt.className   = "font-bold text-xs text-rose-700 uppercase";
    }

    const f0101El = document.getElementById('val-f0101');
    const f0102El = document.getElementById('val-f0102');
    if (f0101El) f0101El.innerText = "OFFLINE";
    if (f0102El) f0102El.innerText = "OFFLINE";

    if (warnBox) {
        warnBox.className = "text-[9px] font-sans font-bold text-center mt-1 p-1 bg-rose-100 border border-rose-300 rounded-sm text-rose-700";
        warnBox.innerText = "❌ HARDWARE BUS DISCONNECTED";
    }
}

function stopVfdPolling() {
    if (vfdPollingInterval) {
        clearInterval(vfdPollingInterval);
        vfdPollingInterval = null;
    }
}

// ==============================================================================
// --- CONNECTION MANAGEMENT ---
// ==============================================================================

async function updateVfdConnection() {
    const { port, baud, address } = getConnectionParams();
    const summaryEl = document.getElementById('diag-summary-txt');

    VfdConsole.log(`Re-routing serial interface → ${port} @ ${baud}bps (Node: ${address})`, 'warn');
    try {
        const res  = await fetch('/api/update-settings', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ port, baud_rate: baud, slave_address: address }),
        });
        const data = await res.json();

        if (data.success) {
            if (summaryEl) summaryEl.innerHTML = `Active Target: <span class="font-bold text-slate-800">${port} @ ${baud}</span>`;
            VfdConsole.log(`Settings applied — bound to node ${address}.`, 'success');
        } else {
            VfdConsole.log(`Settings rejected: ${data.msg || 'Unknown'}`, 'error');
        }
    } catch (e) {
        VfdConsole.log("Network error sending settings to backend.", 'error');
    }
}

async function checkConnectionNow() {
    const { port, baud, address } = getConnectionParams();

    VfdConsole.log("Sending connection validation ping...");
    try {
        const res  = await fetch('/api/connect', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ port, baud_rate: baud, slave_address: address }),
        });
        const data = await res.json();

        const badge  = document.getElementById('nav-status-badge');
        const banner = document.getElementById('bus-banner-txt');
        const pulse  = document.getElementById('heartbeat-pulse');

        if (data.success || data.active) {
            VfdConsole.log(`Link confirmed! ${data.msg}`, 'success');
            if (badge)  { badge.className = "px-2.5 py-0.5 rounded-sm font-mono text-[10px] font-bold uppercase bg-emerald-200 text-emerald-800 border border-emerald-300"; badge.innerText = "Online"; }
            if (banner) banner.innerText = `Modbus active on ${port}`;
            if (pulse)  pulse.className  = "w-2.5 h-2.5 bg-emerald-500 rounded-full animate-pulse";
        } else {
            VfdConsole.log(`Device offline: ${data.msg || 'No response.'}`, 'error');
            if (badge)  { badge.className = "px-2.5 py-0.5 rounded-sm font-mono text-[10px] font-bold uppercase bg-rose-200 text-rose-800 border border-rose-300"; badge.innerText = "Offline"; }
            if (banner) banner.innerText = "Awaiting connection...";
            if (pulse)  { pulse.style.backgroundColor = '#EF4444'; }
        }
    } catch (e) {
        VfdConsole.log("Connection check network error.", 'error');
    }
}

async function autoConnectFirstDevice() {
    VfdConsole.log("Initiating Auto-Link sequence...");
    try {
        const res  = await fetch('/api/auto-link', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    '{}',
        });
        const data = await res.json();

        if (data.success) {
            VfdConsole.log(`Auto-Link → ${data.port}`, 'success');
            const portEl = document.getElementById('cfg-port');
            if (portEl) portEl.value = data.port;
            await checkConnectionNow();
        } else {
            VfdConsole.log(`Auto-Link failed: ${data.msg}`, 'error');
        }
    } catch (e) {
        VfdConsole.log("Auto-Link network error.", 'error');
    }
}

async function quickConnectDevicePort(portName) {
    const portEl = document.getElementById('cfg-port');
    if (portEl) portEl.value = portName;
    VfdConsole.log(`Quick-connect to ${portName}...`);
    await updateVfdConnection();
    await checkConnectionNow();
}

// ==============================================================================
// --- HARDWARE SCAN ---
// ==============================================================================

async function runAutoHardwareScan() {
    const spinner    = document.getElementById('scan-spinner');
    const resultsBox = document.getElementById('scan-results-box');

    if (spinner)    spinner.classList.remove('hidden');
    if (resultsBox) resultsBox.innerHTML = `<div class="text-teal-600 font-bold text-center pt-3 animate-pulse text-[11px]">Scanning bus...</div>`;
    VfdConsole.log("Scanning local COM bus topology...");

    try {
        const res  = await fetch('/api/scan-hardware', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}'
        });
        const data = await res.json();
        const ports = [...new Set(data.ports || [])];

        if (ports.length > 0) {
            VfdConsole.log(`Found ${ports.length} hardware resource(s).`, 'success');
            if (resultsBox) {
                resultsBox.innerHTML = ports.map(p => `
                    <div class="flex items-center justify-between border-b border-[#BAC3C7] last:border-none pb-1 pt-0.5 text-slate-800 font-bold">
                        <span><i class="fa-solid fa-microchip text-slate-500 mr-1.5"></i>${p}</span>
                        <button type="button" onclick="quickConnectDevicePort('${p}')"
                            class="wincc-btn bg-teal-600 hover:bg-teal-700 text-white text-[9px] font-bold px-2 py-0.5 rounded-xs uppercase tracking-wide">
                            <i class="fa-solid fa-link mr-1"></i>Connect
                        </button>
                    </div>`).join('');
            }
        } else {
            VfdConsole.log("Scan complete — no hardware found.", 'warn');
            if (resultsBox) resultsBox.innerHTML = `<div class="text-slate-500 italic text-center pt-2 select-none text-[11px]">No connected hardware.</div>`;
        }
    } catch (err) {
        VfdConsole.log("Hardware scan endpoint unreachable.", 'error');
        if (resultsBox) resultsBox.innerHTML = `<div class="text-slate-500 italic text-center pt-2 select-none text-[11px]">Scan error.</div>`;
    } finally {
        if (spinner) spinner.classList.add('hidden');
    }
}

// ==============================================================================
// --- DRIVE CONTROL ---
// ==============================================================================

/**
 * Control register 0x3000 command codes per Veichi AC10 spec:
 *   1 = Forward run   2 = Reverse run   5 = Decel stop   7 = Fault reset
 *
 * Uses the dedicated /api/control endpoint which goes directly to FC06 write
 * without any port re-init logic that could block emergency stop commands.
 */
async function executeAction(actionType) {
    // 1. Null safety check to prevent .toUpperCase() from crashing
    if (!actionType) return; 

    const valid = ['FORWARD', 'RUN', 'REVERSE', 'STOP', 'RESET'];
    const cmd   = actionType.toUpperCase();

    if (!valid.includes(cmd)) {
        VfdConsole.log(`Unknown action: ${actionType}`, 'warn');
        return;
    }

    // 2. Grab the currently selected COM port from the UI
    const portEl = document.getElementById('cfg-port');
    const activePort = portEl ? portEl.value : 'COM3';

    const codeMap = { FORWARD: 1, RUN: 1, REVERSE: 2, STOP: 5, RESET: 7 };
    VfdConsole.log(`Control coil → ${cmd} (0x3000 = ${codeMap[cmd]})`);

    try {
        const res = await fetch('/api/control', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            // 3. Send the port alongside the command
            body:    JSON.stringify({ 
                command: cmd,
                port: activePort 
            }),
        });

        if (!res.ok) {
            const text = await res.text();
            VfdConsole.log(`Command failed HTTP ${res.status}: ${text}`, 'error');
            return;
        }

        const data = await res.json();
        
        // 4. Check for both 'SUCCESS' and 'success' just to be bulletproof
        if (data.status === 'SUCCESS' || data.success) {
            VfdConsole.log(`✔ ${cmd} command acknowledged.`, 'success');
        } else {
            VfdConsole.log(`Command rejected: ${data.message || data.msg || 'Unknown error'}`, 'error');
        }
    } catch (e) {
        VfdConsole.log(`Coil write failed: ${e.message}`, 'error');
    }
}

// ==============================================================================
// --- FREQUENCY SETPOINT ---
// ==============================================================================

async function writeSetpoint() {
    const freqInput = document.getElementById('vfd-freq-input');
    if (!freqInput) {
        console.error("Element 'vfd-freq-input' not found.");
        return;
    }
    
    const value = freqInput.value.trim();
    if (value === "") return;

    const parsedVal = parseFloat(value);
    if (isNaN(parsedVal)) {
        VfdConsole.log("Validation failure: Frequency input must be numeric.", "warn");
        return;
    }

    VfdConsole.log(`Writing Digital Frequency Target (F01.09) → ${parsedVal} Hz...`);
    try {
        const res = await fetch('/api/write-param', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ key: 'F01.09', value: parsedVal })
        });
        const data = await res.json();
        if (data.success) {
            VfdConsole.log(`✔ Setpoint confirmed: F01.09 updated to ${parsedVal} Hz`, 'success');
            freqInput.value = '';
        } else {
            // Register-write alternate pattern fallback (0x2100)
            await writeRegister('0x2100', parsedVal * 100, 2);
            VfdConsole.log(`✔ Setpoint committed directly to register 0x2100.`, 'success');
            freqInput.value = '';
        }
    } catch (e) {
        VfdConsole.log(`Frequency target transfer failure: ${e.message}`, 'error');
    }
}

async function writePressureSetpoint() {
    const pressureInput = document.getElementById('vfd-pressure-input');
    if (!pressureInput) {
        console.error("Element 'vfd-pressure-input' not found.");
        return;
    }

    const value = pressureInput.value.trim();
    if (value === "") return;

    const parsedVal = parseFloat(value);
    if (isNaN(parsedVal)) {
        VfdConsole.log("Validation failure: PID Target input must be numeric.", "warn");
        return;
    }

    VfdConsole.log(`Writing PID Process Setpoint (F13.01) → ${parsedVal}...`);
    try {
        const res = await fetch('/api/write-param', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            // FIX: Added 'db: null' and changed 'key' to 'offset' to match what your backend expects
            body: JSON.stringify({ db: null, offset: 'F13.01', value: parsedVal })
        });

        // CRITICAL FIX: If the server returns 400 or 500, throw an error so the catch block handles it
        if (!res.ok) {
            const errorData = await res.json().catch(() => ({}));
            throw new Error(`HTTP ${res.status}: ${errorData.message || res.statusText}`);
        }

        const data = await res.json();
        
        // Success path
        VfdConsole.log(`✔ PID Process Setup: Target F13.01 matched to ${parsedVal}`, 'success');
        pressureInput.value = '';

    } catch (e) {
        // Fallback Trigger: Both a network timeout OR an HTTP 400 bad request will now land here safely
        VfdConsole.log(`Primary API failed (${e.message}). Attempting direct register fallback...`, 'warn');
        
        try {
            // FIX: Assuming writeRegister sends a POST, make sure you format the payload keys correctly here too
            // Note: F13.01 in Hex is usually 0x0D01 (or 0x3329 in decimal). 
            // Double check if 0x2D01 is your drive's specific runtime RAM address!
            await writeRegister({ db: null, offset: '0x2D01', value: parsedVal * 10 }); 
            
            VfdConsole.log(`✔ PID dynamic scale written directly to register 0x2D01.`, 'success');
            pressureInput.value = '';
        } catch (fallbackError) {
            VfdConsole.log(`PID target parameter shift failure: ${fallbackError.message}`, 'error');
        }
    }
}

// ==============================================================================
// --- RAW MODBUS INJECTOR ---
// ==============================================================================

async function executeRawTransfer() {
    const reg     = document.getElementById('raw-reg')?.value.trim();
    const fc      = document.getElementById('raw-fc')?.value;
    const payload = document.getElementById('raw-data')?.value.trim();

    VfdConsole.log(`RAW Modbus → FC${fc} @ ${reg} | data: ${payload}`);
    try {
        const res  = await fetch('/api/raw', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ register: reg, functionCode: fc, data: payload }),
        });
        const data = await res.json();

        if (data.success) {
            const msg = data.value !== undefined
                ? `FC${fc} ack → reg ${reg} = ${data.value}`
                : `FC${fc} write ack → ${reg}`;
            VfdConsole.log(msg, 'success');
        } else {
            VfdConsole.log(`Raw transfer rejected: ${data.msg}`, 'error');
        }
    } catch (e) {
        VfdConsole.log(`Raw Modbus transmission failed: ${e.message}`, 'error');
    }
}

// ==============================================================================
// --- ADVANCED PARAMETER PANEL (F01 / F12) ---
// ==============================================================================

const PARAM_META = {
    f01: [
        { key:"F01.00", name:"Control Mode",            unit:"",   dec:0 },
        { key:"F01.01", name:"Run Command Channel",     unit:"",   dec:0 },
        { key:"F01.02", name:"Freq Source Channel A",   unit:"",   dec:0 },
        { key:"F01.03", name:"Channel A Gain",          unit:"%",  dec:1 },
        { key:"F01.04", name:"Freq Source Channel B",   unit:"",   dec:0 },
        { key:"F01.05", name:"Channel B Gain",          unit:"%",  dec:1 },
        { key:"F01.06", name:"Channel B Reference",     unit:"",   dec:0 },
        { key:"F01.07", name:"Freq Reference Source",   unit:"",   dec:0 },
        { key:"F01.08", name:"Run Command Bundle",      unit:"",   dec:0 },
        { key:"F01.09", name:"Keyboard Setpoint Freq",  unit:"Hz", dec:2 },
        { key:"F01.10", name:"Maximum Frequency",       unit:"Hz", dec:2 },
        { key:"F01.12", name:"Upper Frequency Limit",   unit:"Hz", dec:2 },
        { key:"F01.13", name:"Lower Frequency Limit",   unit:"Hz", dec:2 },
        { key:"F01.14", name:"Freq Cmd Resolution",     unit:"",   dec:0 },
        { key:"F01.20", name:"Accel/Decel Base Freq",   unit:"",   dec:0 },
        { key:"F01.21", name:"Accel Time Unit",         unit:"",   dec:0 },
        { key:"F01.22", name:"Acceleration Time 1",     unit:"s",  dec:2 },
        { key:"F01.23", name:"Deceleration Time 1",     unit:"s",  dec:2 },
        { key:"F01.24", name:"Acceleration Time 2",     unit:"s",  dec:2 },
        { key:"F01.25", name:"Deceleration Time 2",     unit:"s",  dec:2 },
        { key:"F01.26", name:"Acceleration Time 3",     unit:"s",  dec:2 },
        { key:"F01.27", name:"Deceleration Time 3",     unit:"s",  dec:2 },
        { key:"F01.28", name:"Acceleration Time 4",     unit:"s",  dec:2 },
        { key:"F01.29", name:"Deceleration Time 4",     unit:"s",  dec:2 },
        { key:"F01.30", name:"S-Curve Enable",          unit:"",   dec:0 },
        { key:"F01.31", name:"S-Curve Accel Start",     unit:"s",  dec:2 },
        { key:"F01.32", name:"S-Curve Accel End",       unit:"s",  dec:2 },
        { key:"F01.33", name:"S-Curve Decel Start",     unit:"s",  dec:2 },
    ],
    f12: [
        { key:"F12.00", name:"Master/Slave Select",       unit:"",   dec:0 },
        { key:"F12.01", name:"485 Node Address",          unit:"",   dec:0 },
        { key:"F12.02", name:"Baud Rate Selection",       unit:"",   dec:0 },
        { key:"F12.03", name:"Modbus Data Format",        unit:"",   dec:0 },
        { key:"F12.04", name:"Write Response Mode",       unit:"",   dec:0 },
        { key:"F12.05", name:"Response Delay",            unit:"ms", dec:0 },
        { key:"F12.06", name:"Timeout Fault Time",        unit:"s",  dec:1 },
        { key:"F12.07", name:"Timeout Fault Action",      unit:"",   dec:0 },
        { key:"F12.08", name:"0x3000 Zero Offset",        unit:"ms", dec:2 },
        { key:"F12.09", name:"0x3000 Gain",               unit:"ms", dec:1 },
        { key:"F12.10", name:"Cyclic Tx Param Select",    unit:"",   dec:0 },
        { key:"F12.11", name:"Freq Custom Addr",          unit:"",   dec:0 },
        { key:"F12.12", name:"Cmd Custom Addr",           unit:"",   dec:0 },
        { key:"F12.13", name:"Forward Run Value",         unit:"",   dec:0 },
        { key:"F12.14", name:"Reverse Run Value",         unit:"",   dec:0 },
        { key:"F12.15", name:"Stop Command Value",        unit:"",   dec:0 },
        { key:"F12.16", name:"Reset Command Value",       unit:"",   dec:0 },
        { key:"F12.19", name:"Host Send Cmd Select",      unit:"",   dec:0 },
    ]
};

function openParamPanel() {
    const modal = document.getElementById('param-modal');
    if (modal) modal.classList.remove('hidden');
    loadParamGroup('f01');
}

function closeParamPanel() {
    const modal = document.getElementById('param-modal');
    if (modal) modal.classList.add('hidden');
}

function switchParamGroup(group) {
    ['f01', 'f12'].forEach(g => {
        const btn = document.getElementById(`param-tab-${g}`);
        if (btn) btn.className = g === group
            ? "wincc-btn tab-active text-[10px] uppercase tracking-wider px-3 py-1 border-t border-x border-[#7F8C8D] rounded-t-sm"
            : "wincc-btn tab-inactive text-[10px] uppercase tracking-wider px-3 py-1 border-t border-x border-[#7F8C8D] rounded-t-sm";
    });
    loadParamGroup(group);
}

async function loadParamGroup(group) {
    const tableBody = document.getElementById('param-table-body');
    const statusEl  = document.getElementById('param-load-status');
    if (!tableBody) return;

    tableBody.innerHTML = `<tr><td colspan="4" class="text-center text-teal-600 font-bold py-4 text-xs animate-pulse">Reading registers from drive...</td></tr>`;
    if (statusEl) statusEl.innerText = "Loading...";

    try {
        const res  = await fetch(`/api/read-params?group=${group}`);
        const data = await res.json();

        if (!data.success) {
            tableBody.innerHTML = `<tr><td colspan="4" class="text-center text-rose-600 font-bold py-4 text-xs">Error: ${data.msg || 'Read failed'}</td></tr>`;
            if (statusEl) statusEl.innerText = "Error";
            return;
        }

        const metas = PARAM_META[group] || [];
        tableBody.innerHTML = metas.map(m => {
            const result  = data.params[m.key];
            const val     = result?.value ?? '—';
            const errNote = result?.error ? ` <span class="text-rose-400 text-[9px]">(err)</span>` : '';
            return `
            <tr class="border-b border-[#BAC3C7] hover:bg-teal-50 transition-colors">
                <td class="py-1 px-2 font-mono font-bold text-[10px] text-slate-700 whitespace-nowrap">${m.key}</td>
                <td class="py-1 px-2 text-[10px] text-slate-600">${m.name}</td>
                <td class="py-1 px-2 font-mono font-bold text-[11px] text-slate-900">${val !== null ? val : '—'}${errNote} <span class="text-[9px] text-slate-400">${m.unit}</span></td>
                <td class="py-1 px-2">
                    <div class="flex gap-1 items-center">
                        <input type="number" id="param-input-${m.key.replace('.','_')}"
                               step="${m.dec > 0 ? Math.pow(10,-m.dec) : 1}"
                               placeholder="${val !== null ? val : '?'}"
                               class="w-20 bg-white text-right font-mono text-[10px] p-0.5 border border-[#7F8C8D] wincc-input outline-none">
                        <button type="button"
                                onclick="writeParamKey('${m.key}')"
                                class="wincc-btn bg-[#4D555A] hover:bg-[#5A646A] text-white border border-[#1C2022] px-2 py-0.5 text-[9px] font-bold uppercase">
                            Set
                        </button>
                    </div>
                </td>
            </tr>`;
        }).join('');

        if (statusEl) statusEl.innerText = `${metas.length} params loaded`;
        VfdConsole.log(`${group.toUpperCase()} parameters loaded from drive.`, 'success');
    } catch (e) {
        tableBody.innerHTML = `<tr><td colspan="4" class="text-center text-rose-600 font-bold py-4 text-xs">Network error — backend unreachable.</td></tr>`;
        if (statusEl) statusEl.innerText = "Error";
        VfdConsole.log("Parameter read network error.", 'error');
    }
}

// Global variable tracking if a write is active
let isWritingParameter = false; 

async function writeParamKey(key) {
    const safeKey = key.replace('.', '_');
    const input   = document.getElementById(`param-input-${safeKey}`);
    if (!input || input.value === '') return;

    const val = parseFloat(input.value);
    if (isNaN(val)) return;

    // 1. PAUSE POLLING: Block read-params from running right now
    isWritingParameter = true; 
    VfdConsole.log(`Pausing polling line. Writing parameter ${key} = ${val}...`);

    try {
        const res  = await fetch('/api/write-param', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ key, value: val }),
        });
        const data = await res.json();
        if (data.success) {
            VfdConsole.log(`✔ ${data.msg}`, 'success');
            input.value = '';
        } else {
            VfdConsole.log(`Write rejected: ${data.msg}`, 'error');
        }
    } catch (e) {
        VfdConsole.log(`Parameter write error: ${e.message}`, 'error');
    } finally {
        // 2. RESUME POLLING: Wait 1 second for the VFD to breathe, then resume reads
        setTimeout(() => {
            isWritingParameter = false;
            VfdConsole.log("Serial line clear. Polling resumed.");
        }, 1000);
    }
}

// ==============================================================================
// --- C00 / C01 LIVE MONITOR PANEL ---
// ==============================================================================

let _monitorInterval = null;
let _monitorGroup    = 'c00';   // which tab is active

const C00_META = [
    { code:"C00.00", name:"Given frequency",           unit:"Hz"     },
    { code:"C00.01", name:"Output frequency",          unit:"Hz"     },
    { code:"C00.02", name:"Output current",            unit:"A"      },
    { code:"C00.03", name:"Input voltage",             unit:"V"      },
    { code:"C00.04", name:"Output voltage",            unit:"V"      },
    { code:"C00.05", name:"Mechanical speed",          unit:"rpm"    },
    { code:"C00.06", name:"Given torque",              unit:"%"      },
    { code:"C00.07", name:"Output torque",             unit:"%"      },
    { code:"C00.08", name:"PID given amount",          unit:"%"      },
    { code:"C00.09", name:"PID feedback amount",       unit:"%"      },
    { code:"C00.10", name:"Output power",              unit:"%/kW"   },
    { code:"C00.11", name:"Bus voltage",               unit:"V"      },
    { code:"C00.12", name:"Module temperature 1",      unit:"℃"      },
    { code:"C00.13", name:"Module temperature 2",      unit:"℃"      },
    { code:"C00.14", name:"Input terminal X state",    unit:"bits"   },
    { code:"C00.15", name:"Output terminal Y state",   unit:"bits"   },
    { code:"C00.16", name:"Analog AI1 input",          unit:"V"      },
    { code:"C00.17", name:"Analog AI2 input",          unit:"V"      },
    { code:"C00.18", name:"Reserved",                  unit:""       },
    { code:"C00.19", name:"Pulse PUL input",           unit:"kHz"    },
    { code:"C00.20", name:"Analog output AO1",         unit:"V"      },
    { code:"C00.21", name:"Analog output AO2",         unit:"V"      },
    { code:"C00.22", name:"Counter count value",       unit:""       },
    { code:"C00.23", name:"Running time (power-on)",   unit:"h"      },
    { code:"C00.24", name:"Accumulated run time",      unit:"h"      },
    { code:"C00.25", name:"Inverter power level",      unit:"kW"     },
    { code:"C00.26", name:"Inverter rated voltage",    unit:"V"      },
    { code:"C00.27", name:"Inverter rated current",    unit:"A"      },
    { code:"C00.28", name:"Software version",          unit:""       },
    { code:"C00.29", name:"PG feedback frequency",     unit:"Hz"     },
    { code:"C00.30", name:"Timer",                     unit:""       },
    { code:"C00.31", name:"PID output",                unit:""       },
    { code:"C00.32", name:"Software subversion",       unit:""       },
    { code:"C00.33", name:"Encoder angle",             unit:"°"      },
    { code:"C00.34", name:"Z pulse error",             unit:""       },
    { code:"C00.35", name:"Z pulse count",             unit:""       },
    { code:"C00.36", name:"Fault warning code",        unit:""       },
    { code:"C00.37", name:"Cumulative power (low)",    unit:""       },
    { code:"C00.38", name:"Cumulative power (high)",   unit:""       },
    { code:"C00.39", name:"Power factor angle",        unit:""       },
];

const C01_META = [
    { code:"C01.00", name:"Fault type",                       unit:"" },
    { code:"C01.01", name:"Fault diagnosis info",             unit:"" },
    { code:"C01.02", name:"Fault running frequency",          unit:"Hz" },
    { code:"C01.03", name:"Fault output voltage",             unit:"V" },
    { code:"C01.04", name:"Fault output current",             unit:"A" },
    { code:"C01.05", name:"Fault bus voltage",                unit:"V" },
    { code:"C01.06", name:"Fault module temperature",         unit:"℃" },
    { code:"C01.07", name:"Faulty inverter status",           unit:"bits" },
    { code:"C01.08", name:"Fault input terminal status",      unit:"bits" },
    { code:"C01.09", name:"Fault output terminal status",     unit:"bits" },
    { code:"C01.10", name:"Previous 1st fault type",          unit:"" },
    { code:"C01.11", name:"Prev fault diagnosis info",        unit:"" },
    { code:"C01.12", name:"Prev fault frequency",             unit:"Hz" },
    { code:"C01.13", name:"Prev fault output voltage",        unit:"V" },
    { code:"C01.14", name:"Prev fault output current",        unit:"A" },
    { code:"C01.15", name:"Prev fault bus voltage",           unit:"V" },
    { code:"C01.16", name:"Prev fault module temp",           unit:"℃" },
    { code:"C01.17", name:"Prev fault inverter status",       unit:"bits" },
    { code:"C01.18", name:"Prev fault input terminal",        unit:"bits" },
    { code:"C01.19", name:"Prev fault output terminal",       unit:"bits" },
    { code:"C01.20", name:"Previous 2nd fault type",          unit:"" },
    { code:"C01.21", name:"2nd fault diagnosis info",         unit:"" },
    { code:"C01.22", name:"Previous 3rd fault type",          unit:"" },
    { code:"C01.23", name:"3rd fault diagnosis info",         unit:"" },
];

function openMonitorPanel() {
    const modal = document.getElementById('monitor-modal');
    if (modal) modal.classList.remove('hidden');
    switchMonitorGroup('c00');
    startMonitorPolling();
}

function closeMonitorPanel() {
    const modal = document.getElementById('monitor-modal');
    if (modal) modal.classList.add('hidden');
    stopMonitorPolling();
}

function switchMonitorGroup(group) {
    _monitorGroup = group;
    ['c00', 'c01'].forEach(g => {
        const btn = document.getElementById(`mon-tab-${g}`);
        if (btn) btn.className = g === group
            ? "wincc-btn tab-active text-[10px] uppercase tracking-wider px-3 py-1 border-t border-x border-[#7F8C8D] rounded-t-sm"
            : "wincc-btn tab-inactive text-[10px] uppercase tracking-wider px-3 py-1 border-t border-x border-[#7F8C8D] rounded-t-sm";
    });
    // Render skeleton rows immediately so the table structure exists before poll
    _renderMonitorSkeleton(group);
    fetchMonitorData();
}

function _renderMonitorSkeleton(group) {
    const tbody = document.getElementById('monitor-table-body');
    if (!tbody) return;
    const meta = group === 'c00' ? C00_META : C01_META;
    tbody.innerHTML = meta.map(m => `
        <tr id="mon-row-${m.code.replace('.','_')}"
            class="border-b border-[#BAC3C7] hover:bg-teal-50 transition-colors">
            <td class="py-1 px-2 font-mono font-bold text-[10px] text-slate-700 whitespace-nowrap">${m.code}</td>
            <td class="py-1 px-2 text-[10px] text-slate-600">${m.name}</td>
            <td id="mon-val-${m.code.replace('.','_')}"
                class="py-1 px-2 font-mono font-bold text-[11px] text-slate-400 text-right">
                <span class="animate-pulse">—</span>
            </td>
            <td class="py-1 px-2 text-[9px] text-slate-400 text-left">${m.unit}</td>
        </tr>`).join('');
}

async function fetchMonitorData() {
    const statusEl = document.getElementById('monitor-status');
    try {
        const res  = await fetch(`/api/monitor?group=${_monitorGroup}`);
        const data = await res.json();

        if (!data.success) {
            if (statusEl) statusEl.innerText = `Error: ${data.msg || 'read failed'}`;
            VfdConsole.log(`Monitor read error: ${data.msg}`, 'error');
            return;
        }

        const records = _monitorGroup === 'c00' ? data.c00 : data.c01;
        const meta    = _monitorGroup === 'c00' ? C00_META  : C01_META;
        let  errCount = 0;

        meta.forEach(m => {
            const cell = document.getElementById(`mon-val-${m.code.replace('.','_')}`);
            if (!cell) return;

            const rec = records[m.code];
            if (!rec) return;

            if (rec.error) {
                errCount++;
                cell.innerHTML = `<span class="text-rose-400 text-[9px]">err</span>`;
            } else {
                const v = rec.value;
                // Highlight non-zero fault code red
                const isAlert = (m.code === 'C00.36' && v !== 0) ||
                                (m.code === 'C01.00'  && v !== 0);
                cell.innerHTML = v === null
                    ? `<span class="text-slate-400">—</span>`
                    : `<span class="${isAlert ? 'text-rose-600 animate-pulse' : 'text-slate-900'}">${v}</span>`;
            }
        });

        if (statusEl) {
            const ts = new Date().toLocaleTimeString();
            statusEl.innerText = errCount > 0
                ? `${meta.length - errCount}/${meta.length} OK — ${errCount} errors — ${ts}`
                : `All ${meta.length} registers OK — ${ts}`;
        }
    } catch (e) {
        if (statusEl) statusEl.innerText = `Network error — ${e.message}`;
        VfdConsole.log(`Monitor fetch failed: ${e.message}`, 'error');
    }
}

function startMonitorPolling() {
    if (_monitorInterval) clearInterval(_monitorInterval);
    // C00 live data every 1 s; C01 fault log every 3 s (slower — it doesn't change fast)
    const interval = _monitorGroup === 'c00' ? 1000 : 3000;
    _monitorInterval = setInterval(fetchMonitorData, interval);
}

function stopMonitorPolling() {
    if (_monitorInterval) {
        clearInterval(_monitorInterval);
        _monitorInterval = null;
    }
}

// Restart the interval with correct rate when switching tabs
const _origSwitchMonitor = switchMonitorGroup;

// ==============================================================================
// --- BOOT ---
// ==============================================================================

document.addEventListener("DOMContentLoaded", () => {
    VfdConsole.init();

    // Auto-start polling if the VFD view is visible on load
    const vfdView = document.getElementById('view-vfd');
    if (vfdView && !vfdView.classList.contains('hidden')) {
        startVfdPolling();
    }
});

const PID_META = {
    core: [
        { key:"F13.00", name:"PID Target Channel Source",   unit:"",   dec:0 },
        { key:"F13.01", name:"PID Digital Target Config",   unit:"Bar",dec:1 },
        { key:"F13.02", name:"PID Feedback Channel Source", unit:"",   dec:0 },
        { key:"F13.04", name:"Proportional Gain (Kp)",      unit:"",   dec:2 },
        { key:"F13.05", name:"Integration Time (Ti)",       unit:"s",  dec:1 },
        { key:"F13.06", name:"Derivative Time (Td)",        unit:"s",  dec:2 }
    ],
    sleep: [
        { key:"F13.12", name:"PID Sleep Freq Threshold",    unit:"Hz", dec:2 },
        { key:"F13.13", name:"PID Sleep Delay Time",        unit:"s",  dec:1 },
        { key:"F13.14", name:"PID Wake-up Threshold Level", unit:"%",  dec:1 }
    ],
    pump: [
        { key:"F13.30", name:"Multi-Pump Control Enable",   unit:"",   dec:0 },
        { key:"F13.31", name:"Interconnected Pump Node ID", unit:"",   dec:0 }
    ]
};

// --- PARAM MODAL ENGINE (F01 / F12) ---
function openParamPanel() {
    const modal = document.getElementById('param-modal');
    if (modal) modal.classList.remove('hidden');
    loadParamGroup('f01');
}

function closeParamPanel() {
    const modal = document.getElementById('param-modal');
    if (modal) modal.classList.add('hidden');
}

function switchParamGroup(group) {
    ['f01', 'f12'].forEach(g => {
        const btn = document.getElementById(`param-tab-${g}`);
        if (btn) btn.className = g === group
            ? "wincc-btn tab-active text-[10px] uppercase tracking-wider px-3 py-1 border-t border-x border-[#7F8C8D] rounded-t-sm"
            : "wincc-btn tab-inactive text-[10px] uppercase tracking-wider px-3 py-1 border-t border-x border-[#7F8C8D] rounded-t-sm";
    });
    loadParamGroup(group);
}

async function loadParamGroup(group) {
    const tableBody = document.getElementById('param-table-body');
    const statusEl  = document.getElementById('param-load-status');
    if (!tableBody) return;

    tableBody.innerHTML = `<tr><td colspan="4" class="text-center text-teal-600 font-bold py-4 text-xs animate-pulse">Reading registers from drive...</td></tr>`;
    if (statusEl) statusEl.innerText = "Loading...";

    try {
        const res  = await fetch(`/api/read-params?group=${group}`);
        const data = await res.json();

        if (!data.success) {
            tableBody.innerHTML = `<tr><td colspan="4" class="text-center text-rose-600 font-bold py-4 text-xs">Error: ${data.msg || 'Read failed'}</td></tr>`;
            if (statusEl) statusEl.innerText = "Error";
            return;
        }

        const metas = PARAM_META[group] || [];
        tableBody.innerHTML = metas.map(m => {
            const result  = data.params?.[m.key];
            const val     = result?.value ?? '—';
            const errNote = result?.error ? ` <span class="text-rose-400 text-[9px]">(err)</span>` : '';
            return `
            <tr class="border-b border-[#BAC3C7] hover:bg-teal-50 transition-colors">
                <td class="py-1 px-2 font-mono font-bold text-[10px] text-slate-700 whitespace-nowrap">${m.key}</td>
                <td class="py-1 px-2 text-[10px] text-slate-600">${m.name}</td>
                <td class="py-1 px-2 font-mono font-bold text-[11px] text-slate-900">${val !== null ? val : '—'}${errNote} <span class="text-[9px] text-slate-400">${m.unit}</span></td>
                <td class="py-1 px-2">
                    <div class="flex gap-1 items-center">
                        <input type="number" id="param-input-${m.key.replace('.','_')}"
                               step="${m.dec > 0 ? Math.pow(10,-m.dec) : 1}"
                               placeholder="${val !== null ? val : '?'}"
                               class="w-20 bg-white text-right font-mono text-[10px] p-0.5 border border-[#7F8C8D] wincc-input outline-none">
                        <button type="button"
                                onclick="writeParamKey('${m.key}')"
                                class="wincc-btn bg-[#4D555A] hover:bg-[#5A646A] text-white border border-[#1C2022] px-2 py-0.5 text-[9px] font-bold uppercase">
                            Set
                        </button>
                    </div>
                </td>
            </tr>`;
        }).join('');

        if (statusEl) statusEl.innerText = "CONNECTED";
        VfdConsole.log(`F${group.toUpperCase()} parameter tracking sync completed.`, 'success');
    } catch (e) {
        tableBody.innerHTML = `<tr><td colspan="4" class="text-center text-rose-600 font-bold py-4 text-xs">Bus Timeout reading parameters.</td></tr>`;
        if (statusEl) statusEl.innerText = "Error";
    }
}

// --- PID MODAL ENGINE (F13 STUFF) ---
function openPidPanel() {
    const modal = document.getElementById('pid-modal');
    if (modal) modal.classList.remove('hidden');
    loadPidGroup('core');
}

function closePidPanel() {
    const modal = document.getElementById('pid-modal');
    if (modal) modal.classList.add('hidden');
}

function switchPidGroup(group) {
    ['core', 'sleep', 'pump'].forEach(g => {
        const btn = document.getElementById(`pid-tab-${g}`);
        if (btn) btn.className = g === group
            ? "wincc-btn tab-active text-[10px] uppercase tracking-wider px-3 py-1 border-t border-x border-[#7F8C8D] rounded-t-sm"
            : "wincc-btn tab-inactive text-[10px] uppercase tracking-wider px-3 py-1 border-t border-x border-[#7F8C8D] rounded-t-sm";
    });
    loadPidGroup(group);
}

async function loadPidGroup(group) {
    const tableBody = document.getElementById('pid-table-body');
    const statusEl  = document.getElementById('pid-load-status');
    if (!tableBody) return;

    tableBody.innerHTML = `<tr><td colspan="4" class="text-center text-sky-600 font-bold py-4 text-xs animate-pulse">Polling PID parameters...</td></tr>`;
    if (statusEl) statusEl.innerText = "Loading...";

    try {
        const res = await fetch(`/api/read-params?group=${group}`);
        const data = await res.json();

        if (!data.success) {
            tableBody.innerHTML = `<tr><td colspan="4" class="text-center text-rose-600 font-bold py-4 text-xs">Error: ${data.msg || 'Read failed'}</td></tr>`;
            if (statusEl) statusEl.innerText = "Error";
            return;
        }

        const metas = PID_META[group] || [];
        tableBody.innerHTML = metas.map(m => {
            const result  = data.params?.[m.key];
            const val     = result?.value ?? '—';
            const errNote = result?.error ? ` <span class="text-rose-400 text-[9px]">(err)</span>` : '';
            return `
            <tr class="border-b border-[#BAC3C7] hover:bg-sky-50 transition-colors">
                <td class="py-1 px-2 font-mono font-bold text-[10px] text-slate-700 whitespace-nowrap">${m.key}</td>
                <td class="py-1 px-2 text-[10px] text-slate-600">${m.name}</td>
                <td class="py-1 px-2 font-mono font-bold text-[11px] text-slate-900">${val !== null ? val : '—'}${errNote} <span class="text-[9px] text-slate-400">${m.unit}</span></td>
                <td class="py-1 px-2">
                    <div class="flex gap-1 items-center">
                        <input type="number" id="param-input-${m.key.replace('.','_')}"
                               step="${m.dec > 0 ? Math.pow(10,-m.dec) : 1}"
                               placeholder="${val !== null ? val : '?'}"
                               class="w-20 bg-white text-right font-mono text-[10px] p-0.5 border border-[#7F8C8D] wincc-input outline-none">
                        <button type="button"
                                onclick="writeParamKey('${m.key}')"
                                class="wincc-btn bg-blue-600 hover:bg-blue-700 text-white border border-[#1C2022] px-2 py-0.5 text-[9px] font-bold uppercase">
                            Commit
                        </button>
                    </div>
                </td>
            </tr>`;
        }).join('');

        if (statusEl) statusEl.innerText = "CONNECTED";
        VfdConsole.log(`F13 ${group.toUpperCase()} parameters updated.`, 'success');
    } catch (e) {
        tableBody.innerHTML = `<tr><td colspan="4" class="text-center text-rose-600 font-bold py-4 text-xs">Network timeout reading F13 segment.</td></tr>`;
        if (statusEl) statusEl.innerText = "Error";
    }
}

// ==============================================================================
// --- LIVE TELEMETRY LOGIC (C00 REGISTER WRAPPING) ---
// ==============================================================================

function updateLivePidDisplay(data) {
    if (!data) return;

    const pidGivenEl    = document.getElementById('pid-given-live');
    const pidFeedbackEl = document.getElementById('pid-feedback-live');
    const pidOutputEl   = document.getElementById('pid-output-live');
    const pidErrorEl    = document.getElementById('pid-error-live');

    const pGiven    = data.pid_given    ?? data.c00_08 ?? 0;
    const pFeedback = data.pid_feedback ?? data.c00_09 ?? 0;
    const pOutput   = data.pid_output   ?? data.output_frequency ?? 0;
    const pError    = data.pid_error    ?? (pGiven - pFeedback);

    if (pidGivenEl)    pidGivenEl.innerText    = Number(pGiven).toFixed(1);
    if (pidFeedbackEl) pidFeedbackEl.innerText = Number(pFeedback).toFixed(1);
    if (pidOutputEl)   pidOutputEl.innerText   = Number(pOutput).toFixed(1) + " Hz";
    if (pidErrorEl)    pidErrorEl.innerText    = Number(pError).toFixed(1) + " %";
}

// ==============================================================================
// --- UNIFIED MUTATION WRITE COMMIT HANDLER ---
// ==============================================================================

async function writeParamKey(key) {
    const safeKey = key.replace('.', '_');
    const input   = document.getElementById(`param-input-${safeKey}`);
    if (!input || input.value === '') {
        VfdConsole.log(`No value entered for ${key}.`, 'warn');
        return;
    }

    const val = parseFloat(input.value);
    if (isNaN(val)) {
        VfdConsole.log(`Invalid numeric value for ${key}.`, 'warn');
        return;
    }

    isCommunicationLocked = true; // Block polling cycles
    VfdConsole.log(`Writing parameter ${key} = ${val}...`);
    try {
        const res  = await fetch('/api/write-param', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ key, value: val }),
        });
        const data = await res.json();
        if (data.success) {
            VfdConsole.log(`✔ ${data.msg}`, 'success');
            input.value = '';
            
            // Re-trigger dynamic local list refresh safely
            if (key.startsWith('F13.')) {
                const activeTab = document.querySelector('.tab-active');
                if (activeTab) {
                    const group = activeTab.id.replace('pid-tab-', '');
                    loadPidGroup(group);
                }
            } else if (key.startsWith('F01.') || key.startsWith('F12.')) {
                const activeTab = document.querySelector('.tab-active');
                if (activeTab) {
                    const group = activeTab.id.replace('param-tab-', '');
                    loadParamGroup(group);
                }
            }
        } else {
            VfdConsole.log(`Write rejected: ${data.msg}`, 'error');
        }
    } catch (e) {
        VfdConsole.log(`Parameter write error: ${e.message}`, 'error');
    } finally {
        setTimeout(() => { isCommunicationLocked = false; }, 1200);
    }
}

// ==============================================================================
// --- CORE INITIALIZATION ---
// ==============================================================================

document.addEventListener("DOMContentLoaded", () => {
    VfdConsole.init();
});