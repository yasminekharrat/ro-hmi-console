/**
 * Siemens HMI Communication Services Layer
 * main/static/js/hmi-comms.js
 */
class HmiCommsService {

    static async fetchConfig() {
        const res = await fetch('/api/tags-config');
        return await res.json();
    }

    static async establishLink(ip, slot = 1) {
        const res = await fetch('/api/connect', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ip, rack: 0, slot: parseInt(slot) })
        });
        return await res.json();
    }

    static async readTag(type, db, offset) {
        const endpoint = (type === 'REAL') ? '/api/read-analog' : '/api/read';
        const res = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ db, offset })
        });
        return await res.json();
    }

    static async writeTag(db, offset, value) {
        const res = await fetch('/api/write', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ db, offset, value })
        });
        return await res.json();
    }

    static async getBulkTelemetry() {
        const res = await fetch('/api/telemetry');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return await res.json();
    }

    static async diagDbDump(db, start, length) {
        const res = await fetch('/api/diag/db-dump', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ db, start, length })
        });
        return await res.json();
    }
}
window.HmiCommsService = HmiCommsService;