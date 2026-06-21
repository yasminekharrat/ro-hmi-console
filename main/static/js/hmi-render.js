/**
 * HMI Renderer — shared UI utilities
 * main/static/js/hmi-renderer.js
 */
class HmiRenderer {

    static appendEventLog(msg, type = "INFO", isError = false) {
        const terminal = document.getElementById('terminal-msg');
        if (terminal) {
            terminal.innerText = msg;
            terminal.className = isError ? "text-[#CC0033] font-bold" : "text-[#006644] font-bold";
        }

        const tbody = document.getElementById('message-log-rows');
        if (!tbody) return;

        const emptyRow = document.getElementById('log-empty-row');
        if (emptyRow) emptyRow.remove();

        const row = document.createElement('tr');
        const isWarn = type.includes('WARN') || type.includes('ALM');

        if (isError) {
            row.className = 'log-row-err';
        } else if (isWarn) {
            row.className = 'log-row-warn';
        } else {
            row.className = (tbody.children.length % 2 === 0) ? 'log-row-even' : 'log-row-odd';
        }

        const t = new Date().toTimeString().split(' ')[0];
        row.innerHTML = `
            <td class="p-1 border-r border-[#D2D7DA] text-slate-500">${t}</td>
            <td class="p-1 border-r border-[#D2D7DA] font-bold text-[10px] uppercase text-slate-600">${type}</td>
            <td class="p-1 px-2">${msg}</td>
        `;
        tbody.insertBefore(row, tbody.firstChild);
    }

    static clearLog() {
        const tbody = document.getElementById('message-log-rows');
        if (tbody) tbody.innerHTML = `<tr id="log-empty-row"><td colspan="3" class="p-2 text-center text-[10px] text-slate-400 italic">No events.</td></tr>`;
    }

    /**
     * Build the data-view grid from PLC_TAGS config
     */
    static buildDataGrid(tagConfig) {
        const grid = document.getElementById('data-table-grid');
        if (!grid) return;
        grid.innerHTML = '';

        tagConfig.forEach(comp => {
            const card = document.createElement('div');
            card.className = 'wincc-panel bg-[#CCD2D5] p-3 rounded-sm';
            card.innerHTML = `
                <div class="text-[9px] font-bold uppercase text-slate-600 tracking-wider mb-2 border-b border-[#A2AEC2] pb-1 flex items-center gap-1.5">
                    <i class="fa-solid ${comp.icon || 'fa-gear'} text-slate-500"></i>${comp.component_name || comp.component_id}
                </div>
                ${Object.entries(comp.variables || {}).map(([k, v]) => `
                    <div class="flex justify-between items-center py-1 border-b border-dashed border-slate-300/60">
                        <span class="text-[9px] text-slate-600 font-medium">${v.name || k}</span>
                        <div class="flex items-baseline gap-1">
                            <span id="dv-${comp.component_id}-${k}" class="plc-mono text-xs font-bold text-[#1B4F72]">—</span>
                            <span class="text-[8px] text-slate-400">${v.unit || ''}</span>
                        </div>
                    </div>
                `).join('')}
            `;
            grid.appendChild(card);
        });
    }

    /**
     * Update data-view cells
     */
    static updateDataGrid(data) {
        Object.entries(data).forEach(([tagId, val]) => {
            const el = document.getElementById(`dv-${tagId}`);
            if (!el) return;
            if (typeof val === 'boolean') {
                el.textContent = val ? 'TRUE' : 'FALSE';
                el.className = `plc-mono text-xs font-bold ${val ? 'text-[#00AA33]' : 'text-[#AA0033]'}`;
            } else if (typeof val === 'number') {
                el.textContent = Number.isInteger(val) ? val : val.toFixed(2);
                el.className = 'plc-mono text-xs font-bold text-[#1B4F72]';
            } else {
                el.textContent = val;
                el.className = 'plc-mono text-xs font-bold text-[#1B4F72]';
            }
        });
    }
}
window.HmiRenderer = HmiRenderer;