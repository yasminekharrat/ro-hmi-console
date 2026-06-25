/**
 * Synoptic View Controller
 * main/static/js/synoptic.js
 *
 * Handles all synoptic canvas updates, the detail side-panel,
 * view tab switching, and backwash modal actions.
 */
class SynopticController {

    constructor() {
        this._panelOpen = false;
        this._currentPanelComp = null;

        // Tag definitions for the detail panel by component_id
        this._panelConfig = {
            instruments: {
                sections: [
                    {
                        title: "Pressions (Bar)",
                        tags: [
                            { id: "instruments-p_in_filter",   name: "P Entrée Filtre Sable",  unit: "Bar",   cls: "pressure" },
                            { id: "instruments-p_out_filter",  name: "P Sortie Filtre Sable",  unit: "Bar",   cls: "pressure" },
                            { id: "instruments-p_out_5u",      name: "P Sortie Filtre 5µ",     unit: "Bar",   cls: "pressure" },
                            { id: "instruments-p_out_1u",      name: "P Sortie Filtre 1µ",     unit: "Bar",   cls: "pressure" },
                            { id: "instruments-p_hp_pump_out", name: "P Sortie Pompe HP",      unit: "Bar",   cls: "pressure" },
                            { id: "instruments-p_reject",      name: "P Rejet Membranes",      unit: "Bar",   cls: "pressure" },
                            { id: "instruments-p_permeat",     name: "P Perméat Membranes",    unit: "Bar",   cls: "pressure" },
                        ]
                    },
                    {
                        title: "Débitmétrie (m³/h)",
                        tags: [
                            { id: "instruments-flow_permeat",   name: "Débit Perméat",    unit: "m³/h", cls: "flow" },
                            { id: "instruments-flow_concentrat",name: "Débit Concentrat", unit: "m³/h", cls: "flow" },
                        ]
                    },
                    {
                        title: "Conductivité (µS/cm)",
                        tags: [
                            { id: "instruments-cond_permeat", name: "Conductivité Perméat", unit: "µS/cm", cls: "cond" },
                            { id: "instruments-cond_mix",     name: "Conductivité Mélange", unit: "µS/cm", cls: "cond" },
                        ]
                    }
                ]
            },
            sand_filter: {
                sections: [
                    {
                        title: "État Filtre à Sable",
                        tags: [
                            { id: "instruments-p_in_filter",  name: "P Entrée",       unit: "Bar", cls: "pressure" },
                            { id: "instruments-p_out_filter", name: "P Sortie",        unit: "Bar", cls: "pressure" },
                            { id: "sand_filter-dp_max",       name: "ΔP Seuil BW",    unit: "Bar", cls: "pressure" },
                            { id: "sand_filter-backwash_timer", name: "Timer BW",     unit: "min", cls: "" },
                            { id: "sand_filter-in_backwash",  name: "En Contre-Lavage", unit: "",  cls: "bool" },
                            { id: "sand_filter-valve_in",     name: "Vanne Entrée",   unit: "",    cls: "bool" },
                            { id: "sand_filter-valve_out",    name: "Vanne Sortie",   unit: "",    cls: "bool" },
                            { id: "sand_filter-valve_drain",  name: "Vanne Vidange",  unit: "",    cls: "bool" },
                        ]
                    }
                ],
                actions: [
                    { label: "Lancer Contre-Lavage", onclick: "document.getElementById('backwash-modal').classList.add('open')", color: "amber" }
                ]
            },
            cartridge_filters: {
                sections: [
                    {
                        title: "Filtres Cartouches",
                        tags: [
                            { id: "instruments-p_out_5u",      name: "P Sortie 5µ",    unit: "Bar", cls: "pressure" },
                            { id: "instruments-p_out_1u",      name: "P Sortie 1µ",    unit: "Bar", cls: "pressure" },
                            { id: "cartridge_filters-dp_5u",   name: "ΔP Filtre 5µ",   unit: "Bar", cls: "pressure" },
                            { id: "cartridge_filters-dp_1u",   name: "ΔP Filtre 1µ",   unit: "Bar", cls: "pressure" },
                            { id: "cartridge_filters-alarm_5u",name: "Alarme 5µ",       unit: "",    cls: "bool" },
                            { id: "cartridge_filters-alarm_1u",name: "Alarme 1µ",       unit: "",    cls: "bool" },
                        ]
                    }
                ]
            },
            feed_pump: {
                sections: [
                    {
                        title: "Pompe Alimentation",
                        tags: [
                            { id: "feed_pump-cmd",   name: "Commande Marche",  unit: "", cls: "bool" },
                            { id: "feed_pump-fault", name: "Défaut",           unit: "", cls: "bool" },
                            { id: "feed_pump-p_low", name: "Seuil P Basse",   unit: "Bar", cls: "pressure" },
                        ]
                    }
                ],
                actions: [
                    { label: "MARCHE", onclick: "HmiApp.triggerWriteByTag('feed_pump-cmd', true)",  color: "green" },
                    { label: "ARRÊT",  onclick: "HmiApp.triggerWriteByTag('feed_pump-cmd', false)", color: "red"   },
                ]
            },
            hp_pump: {
                sections: [
                    {
                        title: "Pompe Haute Pression",
                        tags: [
                            { id: "hp_pump-cmd",         name: "Commande Marche",  unit: "",    cls: "bool" },
                            { id: "hp_pump-fault",       name: "Défaut",           unit: "",    cls: "bool" },
                            { id: "hp_pump-p_max",       name: "P Max Admissible", unit: "Bar", cls: "pressure" },
                            { id: "hp_pump-speed_ref",   name: "Réf. Vitesse VFD", unit: "Hz",  cls: "" },
                            { id: "instruments-p_hp_pump_out", name: "P Sortie Mesurée", unit: "Bar", cls: "pressure" },
                        ]
                    }
                ],
                actions: [
                    { label: "MARCHE HP", onclick: "HmiApp.triggerWriteByTag('hp_pump-cmd', true)",  color: "green" },
                    { label: "ARRÊT HP",  onclick: "HmiApp.triggerWriteByTag('hp_pump-cmd', false)", color: "red"   },
                ]
            },
            tanks: {
                sections: [
                    {
                        title: "Niveaux Réservoirs",
                        tags: [
                            { id: "tanks-level_raw",     name: "Niveau Eau Brute",  unit: "%", cls: "level" },
                            { id: "tanks-level_permeat", name: "Niveau Perméat",    unit: "%", cls: "level" },
                            { id: "tanks-low_raw",       name: "Alarme Bas Brute",  unit: "",  cls: "bool" },
                            { id: "tanks-high_permeat",  name: "Alarme Haut Perméat", unit: "", cls: "bool" },
                        ]
                    }
                ]
            },
            global_management: {
                sections: [
                    {
                        title: "Gestion Système",
                        tags: [
                            { id: "global_management-auto",          name: "Mode Auto",       unit: "", cls: "bool" },
                            { id: "global_management-manual",        name: "Mode Manuel",     unit: "", cls: "bool" },
                            { id: "global_management-alarm_general", name: "Alarme Générale", unit: "", cls: "bool" },
                            { id: "global_management-cond_max",      name: "Cond. Max",       unit: "µS/cm", cls: "cond" },
                            { id: "global_management-runtime_hr",    name: "Heures Marche",   unit: "h",     cls: "" },
                            { id: "global_management-runtime_min",   name: "Minutes Marche",  unit: "min",   cls: "" },
                        ]
                    }
                ],
                actions: [
                    { label: "Mode AUTO",   onclick: "HmiApp.triggerWriteByTag('global_management-auto', true)",   color: "blue"   },
                    { label: "Mode MANUEL", onclick: "HmiApp.triggerWriteByTag('global_management-manual', true)", color: "purple" },
                ]
            }
        };

        // Last received data cache for panel
        this._lastData = {};
    }

    // ──────────────────────────────────────────────────────────────
    // SYNOPTIC UPDATE — called every 500ms with fresh telemetry
    // ──────────────────────────────────────────────────────────────
    updateSynoptic(data) {
        this._lastData = data;

        // ── Helper shortcuts ──────────────────────────────────────
        const num  = (k, d=0) => parseFloat(data[k] ?? d);
        const bool = (k)      => data[k] === true || data[k] === 1;
        const fmt  = (v, dec=2) => isNaN(v) ? '---' : Number(v).toFixed(dec);
        const setText = (id, txt) => { const e = document.getElementById(id); if (e) e.innerHTML = txt; };

        // ── KPI Strip ─────────────────────────────────────────────
        const isAuto = bool('global_management-auto');
        const isManual = bool('global_management-manual');
        setText('kpi-mode',         isAuto ? 'AUTO' : (isManual ? 'MANUEL' : '---'));
        setText('kpi-flow-permeat', fmt(num('instruments-flow_permeat')));
        setText('kpi-cond',         fmt(num('instruments-cond_permeat'), 1));
        setText('kpi-p-hp',         fmt(num('instruments-p_hp_pump_out')));

        const hr  = parseInt(data['global_management-runtime_hr']  ?? 0);
        const min = parseInt(data['global_management-runtime_min'] ?? 0);
        setText('kpi-runtime', `${hr}h ${min}m`);

        // ── TANK RAW ─────────────────────────────────────────────
        const lvRaw = num('tanks-level_raw', 50);
        this._updateTank('tank-raw', lvRaw, bool('tanks-low_raw'), false);
        this._setDot('dot-tank-low', bool('tanks-low_raw') ? 'warn' : 'on');

        // ── TANK PERMEAT ──────────────────────────────────────────
        const lvPerm = num('tanks-level_permeat', 50);
        this._updateTank('tank-permeat', lvPerm, false, bool('tanks-high_permeat'));
        this._setDot('dot-tank-high', bool('tanks-high_permeat') ? 'warn' : 'on');

        // ── POMPE ALIMENTATION ────────────────────────────────────
        const feedOn    = bool('feed_pump-cmd');
        const feedFault = bool('feed_pump-fault');
        this._setDot('dot-feed-pump', feedFault ? 'warn' : (feedOn ? 'on' : 'off'));
        this._setBoxState('box-feed-pump', feedOn, feedFault);
        setText('syn-val-p-low', fmt(num('feed_pump-p_low')) + '<span class="syn-unit">B</span>');

        // ── FILTRE SABLE ──────────────────────────────────────────
        const pInSand  = num('instruments-p_in_filter');
        const pOutSand = num('instruments-p_out_filter');
        const dpSand   = Math.max(0, pInSand - pOutSand);
        const dpSandMax = num('sand_filter-dp_max', 0.5) || 0.5;
        const inBW     = bool('sand_filter-in_backwash');

        setText('syn-val-p-in-filter',  fmt(pInSand)  + '<span class="syn-unit">B</span>');
        setText('syn-val-p-out-filter', fmt(pOutSand) + '<span class="syn-unit">B</span>');
        setText('syn-val-dp-sand',      fmt(dpSand) + ' B');
        this._updateDpBar('dp-bar-sand', dpSand, dpSandMax);
        this._setDot('dot-sand-bw', inBW ? 'warn' : (dpSand < dpSandMax * 0.8 ? 'on' : 'off'));
        const boxSand = document.getElementById('box-sand-filter');
        if (boxSand) {
            boxSand.classList.toggle('backwash', inBW);
            boxSand.classList.toggle('alarm',    dpSand >= dpSandMax);
        }

        // ── FILTRE 5µ ─────────────────────────────────────────────
        const pOut5u = num('instruments-p_out_5u');
        const dp5u   = num('cartridge_filters-dp_5u');
        const dp5uMax = 0.5;
        setText('syn-val-p-out-5u', fmt(pOut5u) + '<span class="syn-unit">B</span>');
        setText('syn-val-dp-5u',    fmt(dp5u) + ' B');
        this._updateDpBar('dp-bar-5u', dp5u, dp5uMax);
        this._setDot('dot-filter-5u', bool('cartridge_filters-alarm_5u') ? 'warn' : 'on');
        const box5u = document.getElementById('box-filter-5u');
        if (box5u) box5u.classList.toggle('alarm', bool('cartridge_filters-alarm_5u'));

        // ── FILTRE 1µ ─────────────────────────────────────────────
        const pOut1u = num('instruments-p_out_1u');
        const dp1u   = num('cartridge_filters-dp_1u');
        const dp1uMax = 0.5;
        setText('syn-val-p-out-1u', fmt(pOut1u) + '<span class="syn-unit">B</span>');
        setText('syn-val-dp-1u',    fmt(dp1u) + ' B');
        this._updateDpBar('dp-bar-1u', dp1u, dp1uMax);
        this._setDot('dot-filter-1u', bool('cartridge_filters-alarm_1u') ? 'warn' : 'on');
        const box1u = document.getElementById('box-filter-1u');
        if (box1u) box1u.classList.toggle('alarm', bool('cartridge_filters-alarm_1u'));

        // ── POMPE HP ──────────────────────────────────────────────
        const hpOn    = bool('hp_pump-cmd');
        const hpFault = bool('hp_pump-fault');
        this._setDot('dot-hp-pump', hpFault ? 'warn' : (hpOn ? 'on' : 'off'));
        this._setBoxState('box-hp-pump', hpOn, hpFault);
        setText('syn-val-p-hp-out',  fmt(num('instruments-p_hp_pump_out')) + '<span class="syn-unit">B</span>');
        setText('syn-val-hp-speed',  fmt(num('hp_pump-speed_ref'), 1) + '<span class="syn-unit">Hz</span>');

        // ── MEMBRANES RO ──────────────────────────────────────────
        setText('syn-val-p-reject',     fmt(num('instruments-p_reject'))       + '<span class="syn-unit">B</span>');
        setText('syn-val-p-permeat',    fmt(num('instruments-p_permeat'))      + '<span class="syn-unit">B</span>');
        setText('syn-val-flow-permeat', fmt(num('instruments-flow_permeat'))   + '<span class="syn-unit">m³/h</span>');
        setText('syn-val-flow-conc',    fmt(num('instruments-flow_concentrat'))+ '<span class="syn-unit">m³/h</span>');

        // ── CONDUCTIVITÉ ──────────────────────────────────────────
        setText('syn-val-cond-permeat', fmt(num('instruments-cond_permeat'), 1) + '<span class="syn-unit">µS/cm</span>');
        setText('syn-val-cond-mix',     fmt(num('instruments-cond_mix'), 1)     + '<span class="syn-unit">µS/cm</span>');

        // ── PANEL UPDATE (if open) ─────────────────────────────────
        if (this._panelOpen && this._currentPanelComp) {
            this._refreshPanelValues();
        }
    }

    // ──────────────────────────────────────────────────────────────
    // HELPERS
    // ──────────────────────────────────────────────────────────────
    _updateTank(prefix, pct, isLow, isHigh) {
        const fill = document.getElementById(`${prefix}-fill`);
        const pctEl = document.getElementById(`${prefix}-pct`);
        if (!fill) return;
        const clampedPct = Math.max(0, Math.min(100, pct));
        fill.style.height = `${clampedPct}%`;
        fill.className = 'tank-fill' + (isLow ? ' low' : isHigh ? ' high' : '');
        if (pctEl) pctEl.textContent = `${Math.round(clampedPct)}%`;
    }

    _setDot(id, state) {
        const el = document.getElementById(id);
        if (!el) return;
        el.className = `syn-status-dot ${state}`;
    }

    _setBoxState(id, isOn, isFault) {
        const el = document.getElementById(id);
        if (!el) return;
        el.classList.toggle('active-running', isOn && !isFault);
        el.classList.toggle('alarm', isFault);
    }

    _updateDpBar(id, dp, maxDp) {
        const bar = document.getElementById(id);
        if (!bar) return;
        const pct = Math.min(100, (dp / (maxDp || 1)) * 100);
        bar.style.width = `${pct}%`;
        bar.classList.toggle('warn', pct > 60 && pct <= 85);
        bar.classList.toggle('crit', pct > 85);
    }

    // ──────────────────────────────────────────────────────────────
    // DETAIL PANEL
    // ──────────────────────────────────────────────────────────────
    openPanel(compId, title) {
        this._currentPanelComp = compId;
        document.getElementById('dp-title').textContent = title;
        document.getElementById('dp-subtitle').textContent = `ID: ${compId}`;

        this._buildPanelHTML(compId);
        this._refreshPanelValues();

        document.getElementById('detail-panel').classList.add('open');
        this._panelOpen = true;
    }

    closePanel() {
        document.getElementById('detail-panel').classList.remove('open');
        this._panelOpen = false;
        this._currentPanelComp = null;
    }

    _buildPanelHTML(compId) {
        const cfg = this._panelConfig[compId];
        const body = document.getElementById('dp-body');
        if (!body || !cfg) {
            if (body) body.innerHTML = '<p class="text-slate-400 text-xs p-4">No detail config for this component.</p>';
            return;
        }

        let html = '';
        for (const section of cfg.sections) {
            html += `<div class="section-title">${section.title}</div>`;
            for (const tag of section.tags) {
                html += `
                    <div class="param-row">
                        <span class="param-name">${tag.name}</span>
                        <div class="flex items-baseline">
                            <span id="dp-val-${tag.id}" class="param-value ${tag.cls || ''}">—</span>
                            <span class="param-unit">${tag.unit}</span>
                        </div>
                    </div>`;
            }
        }

        if (cfg.actions && cfg.actions.length) {
            html += `<div class="section-title">Commandes</div><div class="flex flex-wrap gap-2">`;
            const colors = { green:'#065F46', red:'#7F1D1D', blue:'#1D4ED8', amber:'#78350F', purple:'#4C1D95' };
            const borders = { green:'#064E3B', red:'#6B1A1A', blue:'#1E3A8A', amber:'#92400E', purple:'#3B0764' };
            for (const a of cfg.actions) {
                const bg = colors[a.color] || colors.blue;
                const br = borders[a.color] || borders.blue;
                html += `<button onclick="${a.onclick}" style="background:${bg};border-color:${br}"
                         class="wincc-btn flex-1 text-white font-bold py-1.5 text-[9px] border uppercase tracking-wider">${a.label}</button>`;
            }
            html += `</div>`;
        }

        body.innerHTML = html;
    }

    _refreshPanelValues() {
        const cfg = this._panelConfig[this._currentPanelComp];
        if (!cfg) return;

        for (const section of cfg.sections) {
            for (const tag of section.tags) {
                const el = document.getElementById(`dp-val-${tag.id}`);
                if (!el) continue;
                const raw = this._lastData[tag.id];
                if (raw === undefined) { el.textContent = '—'; continue; }

                if (typeof raw === 'boolean') {
                    el.textContent = raw ? 'TRUE' : 'FALSE';
                    el.className = `param-value ${raw ? 'bool-true' : 'bool-false'}`;
                } else if (typeof raw === 'number') {
                    el.textContent = Number.isInteger(raw) ? raw : raw.toFixed(2);
                    el.className = `param-value ${tag.cls || ''}`;
                } else {
                    el.textContent = raw;
                }
            }
        }
    }

    // ──────────────────────────────────────────────────────────────
    // TAB SWITCHING
    // ──────────────────────────────────────────────────────────────
    showView(view) {
        // 1. We added 'alarms' to the array
        ['synoptic', 'dataview', 'settings', 'alarms','engineering'].forEach(v => {
            const el = document.getElementById(`view-${v}`);
            
            // 2. We check for both ID naming conventions so it matches 'btn-tab-alarms'
            const btn = document.getElementById(`btn-${v}`) || document.getElementById(`btn-tab-${v}`);
            
            if (el) el.classList.toggle('hidden', v !== view);
            if (btn) {
                btn.classList.toggle('tab-active',   v === view);
                btn.classList.toggle('tab-inactive', v !== view);
            }
        });
    }

    // ──────────────────────────────────────────────────────────────
    // BACKWASH MODAL ACTIONS
    // ──────────────────────────────────────────────────────────────
    applyBackwashSettings() {
        const dp = parseFloat(document.getElementById('bw-dp-threshold')?.value || 0.5);
        const dur = parseFloat(document.getElementById('bw-duration')?.value || 5);
        HmiApp.triggerWriteByTag('sand_filter-dp_max', dp);
        HmiApp.triggerWriteByTag('sand_filter-backwash_duration', dur);
        HmiRenderer.appendEventLog(`Paramètres BW appliqués: ΔP=${dp}Bar, Durée=${dur}min`, "BW_CFG");
        document.getElementById('backwash-modal').classList.remove('open');
    }

    startManualBackwash() {
        HmiApp.triggerWriteByTag('sand_filter-manual_backwash_trigger', true);
        HmiRenderer.appendEventLog("Contre-lavage manuel déclenché!", "BW_CMD", false);
        document.getElementById('backwash-modal').classList.remove('open');
    }

    clearLog() {
        HmiRenderer.clearLog();
    }

    // ──────────────────────────────────────────────────────────────
    // DIAGNOSTIC DB DUMP
    // ──────────────────────────────────────────────────────────────
    async runDiagDump() {
        const db  = parseInt(document.getElementById('diag-db')?.value || 2);
        const start = parseInt(document.getElementById('diag-start')?.value || 0);
        const len = parseInt(document.getElementById('diag-len')?.value || 48);
        const out = document.getElementById('diag-output');
        if (out) out.textContent = 'Reading...';
        try {
            const res = await HmiCommsService.diagDbDump(db, start, len);
            if (res.status === 'success') {
                let txt = `DB${res.db} | Bytes: ${res.length_bytes}\nHEX: ${res.hex}\n\nDecoded REAL (big-endian):\n`;
                Object.entries(res.decoded_floats || {}).forEach(([k,v]) => {
                    txt += `  ${k}: ${v}\n`;
                });
                if (out) out.textContent = txt;
            } else {
                if (out) out.textContent = `ERROR: ${res.message}`;
            }
        } catch (e) {
            if (out) out.textContent = `EXCEPTION: ${e.message}`;
        }
    }
}

const SynopticHMI = new SynopticController();