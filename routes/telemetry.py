"""
routes/telemetry.py
Flask blueprint for all PLC communication endpoints.

NetToPLCSim compatibility notes:
  - NEVER call db_read() for I/Q area tags — use client.read_area() with the
    correct S7 area code (0x81 = Inputs, 0x82 = Outputs).
  - NEVER call db_read() with an odd byte count — PLCSim rejects non-even PDUs.
  - DB reads (read_db_block) are only used in the /diag/db-dump endpoint where
    the DB number is explicitly provided by the caller.
  - The /api/telemetry endpoint is 100% area-read based when tags_config uses
    "area": "I" or "area": "Q" — no DB involvement at all.
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
# BIT READ/WRITE  (DB-backed — only call these for actual DB tags)
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
# ANALOG READ  (DB-backed — only call for actual DB REAL tags)
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
# BULK TELEMETRY — I/Q Area reads only, NetToPLCSim safe
# ──────────────────────────────────────────────────────────────────────
@telemetry_bp.route('/api/telemetry', methods=['GET'])
def get_bulk_telemetry():
    """
    Reads I/Q hardware tags via read_area().
    Tags must have "area": "I" or "area": "Q" in tags_config.
    DB tags (area "DB") are explicitly unsupported here — use /api/read-analog
    or /api/read for individual DB reads.

    S7 area codes:
        0x81 = Process Inputs  (%I / %IW)
        0x82 = Process Outputs (%Q / %QW)
    """
    if not plc_service.is_connected:
        return jsonify({"status": "error", "message": "PLC offline"}), 503

    telemetry_data = {}

    for component in PLC_TAGS:
        comp_id = component['component_id']
        for var_key, var_meta in component['variables'].items():

            tag_id    = f"{comp_id}-{var_key}"
            tag_type  = var_meta['type']
            offset_str = str(var_meta['offset'])
            area_letter = var_meta.get('area', 'I').upper()

            # Guard: skip any tag that accidentally still references a DB
            if area_letter not in ('I', 'Q'):
                print(f"⚠️  Skipping [{tag_id}]: area='{area_letter}' is not I or Q — "
                      f"DB reads must use /api/read or /api/read-analog")
                telemetry_data[tag_id] = None
                continue

            # S7 area code
            s7_area = 0x82 if area_letter == 'Q' else 0x81

            # Parse byte / bit index from offset string
            if '.' in offset_str:
                byte_idx = int(offset_str.split('.')[0])
                bit_idx  = int(offset_str.split('.')[1])
            else:
                byte_idx = int(offset_str)
                bit_idx  = 0

            try:
                if tag_type in ('INT', 'WORD'):
                    # %IW / %QW — read 2 bytes (always even, PLCSim safe)
                    raw = plc_service.client.read_area(s7_area, 0, byte_idx, 2)
                    fmt = '>H' if tag_type == 'WORD' else '>h'
                    telemetry_data[tag_id] = int(struct.unpack(fmt, bytes(raw[:2]))[0])

                elif tag_type == 'BOOL':
                    # %I / %Q — read the containing byte, extract the bit
                    raw = plc_service.client.read_area(s7_area, 0, byte_idx, 1)
                    telemetry_data[tag_id] = bool((raw[0] >> bit_idx) & 0x01)

                else:
                    print(f"⚠️  [{tag_id}]: unsupported type '{tag_type}' for I/Q area read")
                    telemetry_data[tag_id] = 0

            except Exception as io_err:
                print(f"⚠️  Error polling [{tag_id}] "
                      f"area={area_letter} offset={offset_str}: {io_err}")
                telemetry_data[tag_id] = None

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
    db     = int(data.get('db',     51))
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