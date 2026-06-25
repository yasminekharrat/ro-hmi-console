"""
routes/telemetry.py
Flask blueprint for all PLC communication endpoints.

REV: moved fully to DB2 — area reads (read_area / I/Q) are gone.
───────────────────────────────────────────────────────────────────
All tags in config/tags_config.py now live in DB2 ("Declaration hmi").
/api/telemetry's bulk loop used to call client.read_area() directly
for physical I/Q tags; that logic has been removed and replaced with
a call into main/services/telemetry_reader.py, which reads every
enabled DB tag through plc_service's typed DB readers (read_bit,
read_int, read_dint, read_word, read_real).

/api/read and /api/read-analog (single-tag reads) are unchanged —
they were already DB-only.

/api/diag/db-dump is unchanged — it was already an explicit-DB
diagnostic tool.

NetToPLCSim compatibility notes (still apply to plc_service under
the hood, even though this file no longer touches read_area itself):
  - NEVER call db_read() with an odd byte count — PLCSim rejects
    non-even PDUs. plc_service._db_read_bytes() already enforces this.
  - DB reads (read_db_block) are only used in /api/diag/db-dump where
    the DB number is explicitly provided by the caller.
"""

import sys
import math
import struct
from pathlib import Path
from flask import Blueprint, request, jsonify

root_path = Path(__file__).resolve().parent.parent
if str(root_path) not in sys.path:
    sys.path.append(str(root_path))

from main.services.plc_service import plc_service
from main.services.telemetry_reader import read_all_tags, write_tag_by_id
from config.tags_config import PLC_TAGS

telemetry_bp = Blueprint('telemetry', __name__)


# ──────────────────────────────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────────────────────────────
@telemetry_bp.route('/api/tags-config', methods=['GET'])
def get_tags():
    return jsonify(PLC_TAGS)


# ──────────────────────────────────────────────────────────────────────
# CONNECTION
# ──────────────────────────────────────────────────────────────────────
@telemetry_bp.route('/api/connect', methods=['POST'])
def handle_connect():
    data = request.get_json() or {}
    ip = data.get('ip', '192.168.1.10')
    success, msg = plc_service.connect(ip)
    return jsonify({"status": "success" if success else "error", "message": msg})


# ──────────────────────────────────────────────────────────────────────
# BIT READ/WRITE  (DB-backed)
# ──────────────────────────────────────────────────────────────────────
@telemetry_bp.route('/api/read', methods=['POST'])
def handle_read_bit():
    data = request.get_json() or {}
    db = data.get('db')
    offset = data.get('offset')
    if db is None or offset is None:
        return jsonify({"status": "error", "message": "Missing db or offset"}), 400
    try:
        val = plc_service.read_bit(int(db), offset)
        return jsonify({"status": "success", "value": val})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@telemetry_bp.route('/api/write', methods=['POST'])
def handle_write_bit():
    data = request.get_json() or {}
    db = data.get('db')
    offset = data.get('offset')
    value = data.get('value')
    if db is None or offset is None or value is None:
        return jsonify({"status": "error", "message": "Missing db, offset, or value"}), 400
    try:
        plc_service.write_bit(int(db), offset, bool(value))
        return jsonify({"status": "success", "message": f"DB{db}.{offset} = {value}"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ──────────────────────────────────────────────────────────────────────
# TAG-NAME WRITE — frontend writes by tag_id, db/offset looked up from
# config/tags_config.py. This is the endpoint synoptic.js's
# HmiApp.triggerWriteByTag() calls — see main/static/js/hmi-app.js.
# Unlike /api/write above, this refuses any tag not explicitly marked
# "writable": True in tags_config.py, so a misconfigured or read-only
# tag can never be written by accident from a stale frontend button.
# ──────────────────────────────────────────────────────────────────────
@telemetry_bp.route('/api/write-tag', methods=['POST'])
def handle_write_tag():
    data = request.get_json() or {}
    tag_id = data.get('tag_id')
    value = data.get('value')
    if tag_id is None or value is None:
        return jsonify({"status": "error", "message": "Missing tag_id or value"}), 400

    if not plc_service.is_connected:
        return jsonify({"status": "error", "message": "PLC offline"}), 503

    success, msg = write_tag_by_id(tag_id, value, PLC_TAGS)
    return jsonify({"status": "success" if success else "error", "message": msg})


# ──────────────────────────────────────────────────────────────────────
# ANALOG READ  (DB-backed REAL tags)
# ──────────────────────────────────────────────────────────────────────
@telemetry_bp.route('/api/read-analog', methods=['POST'])
def handle_read_analog():
    data = request.get_json() or {}
    db = data.get('db')
    offset = data.get('offset')
    if db is None or offset is None:
        return jsonify({"status": "error", "message": "Missing db or offset"}), 400
    try:
        val = plc_service.read_real(int(db), offset)
        return jsonify({"status": "success", "value": round(val, 3)})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ──────────────────────────────────────────────────────────────────────
# BULK TELEMETRY — now 100% DB2, via telemetry_reader.read_all_tags()
# ──────────────────────────────────────────────────────────────────────
@telemetry_bp.route('/api/telemetry', methods=['GET'])
def get_bulk_telemetry():
    """
    Reads every enabled tag in PLC_TAGS via telemetry_reader.read_all_tags().
    All tags are DB2-based — see config/tags_config.py for the full map.

    Per-tag read failures do not fail the whole request — a failed tag
    comes back as None in the response (read_all_tags() logs the
    underlying exception with tag id / db / offset / type for debugging).
    """
    if not plc_service.is_connected:
        return jsonify({"status": "error", "message": "PLC offline"}), 503

    telemetry_data = read_all_tags(PLC_TAGS)
    return jsonify(telemetry_data)


# ──────────────────────────────────────────────────────────────────────
# DIAGNOSTICS — safe DB dump with PLCSim-friendly even-byte chunks
# ──────────────────────────────────────────────────────────────────────
@telemetry_bp.route('/api/diag/db-dump', methods=['POST'])
def diag_db_dump():
    """
    Developer tool: dump raw bytes from a specific DB.
    Enforces even byte count and a hard cap of 16 bytes per call
    to stay within NetToPLCSim PDU limits.
    """
    data   = request.get_json() or {}
    db     = int(data.get('db',     2))
    start  = int(data.get('start',  0))
    length = int(data.get('length', 8))

    if not plc_service.is_connected:
        return jsonify({"status": "error", "message": "PLC offline"}), 503

    try:
        safe_len = min(length, 16)                        # hard PDU cap
        safe_len = safe_len if safe_len % 2 == 0 else safe_len + 1  # even bytes

        raw = plc_service.read_db_block(db, start, safe_len)
        hex_dump = raw.hex()

        floats = {}
        for i in range(0, len(raw) - 3, 4):
            try:
                f = struct.unpack_from('>f', raw, i)[0]
                floats[f"offset_{start + i}"] = round(f, 4) if not math.isnan(f) else 0.0
            except Exception:
                pass

        return jsonify({
            "status":        "success",
            "db":            db,
            "start":         start,
            "length_bytes":  len(raw),
            "hex":           hex_dump,
            "decoded_floats": floats,
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500