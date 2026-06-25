"""
main/services/telemetry_reader.py
Shared "read all tags" function — factored out of routes/telemetry.py.

This is a pure function over plc_service: it does not own state, does
not touch Flask, and does not know about HTTP. It just walks PLC_TAGS
and returns a flat {tag_id: value} dict, suitable for jsonify()'ing
straight out of a route.

WHY THIS EXISTS
───────────────────────────────────────────────────────────────────
Previously /api/telemetry in routes/telemetry.py inlined this loop
itself, using client.read_area() for physical I/Q tags. Since all
tags now live in DB2 (see config/tags_config.py), the read path is
simpler — every tag goes through plc_service's typed DB readers
(read_bit / read_int / read_dint / read_word / read_real) instead of
read_area(). Pulling this into its own function keeps routes/telemetry.py
thin and makes the read loop testable on its own.

TAG SHAPE THIS EXPECTS (see config/tags_config.py)
───────────────────────────────────────────────────────────────────
    {
        "component_id": "feed_pump_setpoints",
        "variables": {
            "start_pompe_alimentation": {
                "offset": "114",      # byte, or "byte.bit" for BOOL
                "type": "REAL",       # BOOL | INT | DINT | WORD | REAL
                "db": 2,
                "area": "DB",
                "enabled": True,      # optional, defaults True
            },
            ...
        }
    }

Tags with "enabled": False are skipped entirely — they will not
appear in the returned dict at all (not even as None), so the
frontend/Engineering tab can tell "not wired up yet" apart from
"PLC read failed" (which returns None, see below).

ERROR HANDLING
───────────────────────────────────────────────────────────────────
Per-tag read failures do not abort the whole poll. A failed read is
recorded as None in the result dict and logged with the tag id, db,
offset, and type so a bad offset is easy to spot in the console.
This mirrors the existing behavior in routes/telemetry.py's old
inline loop (it never let one bad tag kill the whole /api/telemetry
response).
"""

import logging

from main.services.plc_service import plc_service

log = logging.getLogger(__name__)

# Maps a tag's "type" string to the plc_service method that reads it.
_READ_DISPATCH = {
    "BOOL": "read_bit",
    "INT":  "read_int",
    "DINT": "read_dint",
    "WORD": "read_word",
    "REAL": "read_real",
}

# Maps a tag's "type" string to the plc_service method that writes it.
# NOTE: plc_service.py only implements write_bit / write_int / write_real.
# There is no write_dint or write_word yet — tags of those types cannot
# be written through this path until those methods are added to
# plc_service.py. write_tag_by_id() below returns a clear error rather
# than guessing or silently failing if this is attempted.
_WRITE_DISPATCH = {
    "BOOL": "write_bit",
    "INT":  "write_int",
    "REAL": "write_real",
}


def find_tag(tag_id, tags_config=None):
    """
    Look up a single tag's full metadata dict by its "component-varkey" id
    (e.g. "feed_pump-cmd"). Returns the metadata dict, or None if not found.
    """
    if tags_config is None:
        from config.tags_config import PLC_TAGS
        tags_config = PLC_TAGS

    for component in tags_config:
        comp_id = component.get("component_id", "unknown")
        for var_key, var_meta in component.get("variables", {}).items():
            if f"{comp_id}-{var_key}" == tag_id:
                return var_meta
    return None


def write_tag_by_id(tag_id, value, tags_config=None):
    """
    Write a value to a tag by its tag_id (e.g. "feed_pump-cmd"), looking
    up db/offset/type from tags_config.py instead of trusting raw
    db/offset from the caller.

    This is the single point every write button in the frontend should
    go through (via /api/write-tag) so that tags_config.py stays the
    only place anyone has to edit to change what gets written where.

    Returns: (success: bool, message: str)

    Refuses to write if:
      - the tag_id is not found in tags_config.py
      - the tag is not marked "writable": True
      - the tag is disabled ("enabled": False)
      - the tag's type has no corresponding plc_service write_* method
    """
    meta = find_tag(tag_id, tags_config)

    if meta is None:
        return False, f"Unknown tag_id '{tag_id}' — not found in tags_config.py"

    if meta.get("enabled", True) is False:
        return False, f"Tag '{tag_id}' is disabled (enabled=False) in tags_config.py — no offset assigned yet"

    if not meta.get("writable", False):
        return False, f"Tag '{tag_id}' is not marked writable in tags_config.py"

    db = meta.get("db")
    offset = meta.get("offset")
    tag_type = meta.get("type")

    if db is None or offset is None or tag_type is None:
        return False, f"Tag '{tag_id}' is missing db/offset/type in tags_config.py"

    method_name = _WRITE_DISPATCH.get(tag_type)
    if method_name is None:
        return False, (
            f"Tag '{tag_id}' has type '{tag_type}', which has no write "
            f"method in plc_service.py yet (supported: {', '.join(_WRITE_DISPATCH.keys())})"
        )

    try:
        write_fn = getattr(plc_service, method_name)
        if tag_type == "BOOL":
            write_fn(int(db), offset, bool(value))
        elif tag_type == "REAL":
            write_fn(int(db), offset, float(value))
        elif tag_type == "INT":
            write_fn(int(db), offset, int(value))
        return True, f"DB{db}.{offset} ({tag_id}) = {value}"
    except Exception as write_err:
        log.warning("Error writing [%s] db=%s offset=%s type=%s: %s",
                    tag_id, db, offset, tag_type, write_err)
        return False, str(write_err)


def read_all_tags(tags_config=None):
    """
    Walk every component/variable in tags_config (defaults to the
    live PLC_TAGS import) and read each enabled DB tag from the PLC.

    Returns: dict of {"<component_id>-<var_key>": value_or_None}

    Does NOT check plc_service.is_connected itself — callers (routes)
    are expected to check that first and short-circuit with a 503,
    same as the current /api/telemetry behavior. This function will
    simply surface read exceptions as None per-tag if called while
    disconnected, rather than failing the whole poll.
    """
    if tags_config is None:
        # Local import avoids a hard import-time dependency for callers
        # that pass their own tags_config (e.g. unit tests).
        from config.tags_config import PLC_TAGS
        tags_config = PLC_TAGS

    telemetry_data = {}

    for component in tags_config:
        comp_id = component.get("component_id", "unknown")
        variables = component.get("variables", {})

        for var_key, var_meta in variables.items():
            tag_id = f"{comp_id}-{var_key}"

            # Skip disabled/placeholder tags entirely — not even None.
            if var_meta.get("enabled", True) is False:
                continue

            tag_type = var_meta.get("type")
            offset = var_meta.get("offset")
            db = var_meta.get("db")
            area = var_meta.get("area", "DB").upper()

            if area != "DB":
                log.warning(
                    "Skipping [%s]: area='%s' is not DB — this reader "
                    "only supports DB tags. Check tags_config.py.",
                    tag_id, area,
                )
                telemetry_data[tag_id] = None
                continue

            if db is None or offset is None or tag_type is None:
                log.warning(
                    "Skipping [%s]: missing db/offset/type in tags_config.py "
                    "(db=%r, offset=%r, type=%r)",
                    tag_id, db, offset, tag_type,
                )
                telemetry_data[tag_id] = None
                continue

            method_name = _READ_DISPATCH.get(tag_type)
            if method_name is None:
                log.warning(
                    "Skipping [%s]: unsupported type '%s' "
                    "(supported: %s)",
                    tag_id, tag_type, ", ".join(_READ_DISPATCH.keys()),
                )
                telemetry_data[tag_id] = None
                continue

            try:
                read_fn = getattr(plc_service, method_name)
                value = read_fn(int(db), offset)

                # Round REAL values for display, same as /api/read-analog does.
                if tag_type == "REAL" and isinstance(value, float):
                    value = round(value, 3)

                telemetry_data[tag_id] = value

            except Exception as read_err:
                log.warning(
                    "Error reading [%s] db=%s offset=%s type=%s: %s",
                    tag_id, db, offset, tag_type, read_err,
                )
                telemetry_data[tag_id] = None

    return telemetry_data