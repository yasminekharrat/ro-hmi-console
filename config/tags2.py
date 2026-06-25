"""
config/tags_config.py
Single source of truth for every PLC tag the HMI reads or writes.

═══════════════════════════════════════════════════════════════════
EVERYTHING LIVES IN DB2 ("Declaration hmi")
═══════════════════════════════════════════════════════════════════
This file was reorganized to move off physical I/Q areas entirely.
Every tag below is now "area": "DB", "db": 2, with an offset that
matches the TIA Portal variable table for DB2 exactly (as of the
2026-06-25 screenshots of "Declaration hmi [DB2]", rows 1-68, plus
one new tag added after row 68).

HOW TO EDIT THIS FILE
───────────────────────────────────────────────────────────────────
- Each tag is one dict: {"offset": <byte or "byte.bit">, "type": <TYPE>}
- "type" must be one of: BOOL, INT, DINT, WORD, REAL
    (these are the only types main/services/plc_service.py knows how
    to read/write — see read_bit/read_int/read_dint/read_word/read_real)
- offset format:
    - BOOL   → "byte.bit"  e.g. "150.1"  (byte 150, bit 1)
    - INT/WORD → byte only, 2 bytes wide   e.g. "212"
    - DINT/REAL → byte only, 4 bytes wide  e.g. "2"
- If you add a new tag: pick the next free byte offset (check the
  byte map comment above each block below) and make sure you are not
  overlapping bytes used by a neighboring tag. Width matters:
    BOOL = shares a byte (multiple BOOLs can share one byte, by bit)
    INT/WORD = 2 bytes
    DINT/REAL = 4 bytes
- If a tag is wrong or you need to disable it without deleting the
  offset reservation, set "enabled": False. Disabled tags are skipped
  by telemetry_reader.py but stay visible here so nobody accidentally
  reuses that byte range for something else.

WHAT WAS DELIBERATELY DROPPED / CHANGED FROM THE RAW DB2 TABLE
───────────────────────────────────────────────────────────────────
- All Time_Of_Day fields (activation s1-s4, desactivaton s1-s4,
  "HEURE DE LAVAGE FILTRE SABLE...") are NOT modeled as live tags.
  Custom scheduling will be built instead of using PLC Time_Of_Day.
  Their byte ranges (offsets 14-59... see RESERVED block below) are
  kept here as disabled placeholders so nothing else gets assigned
  on top of them by mistake.
- "Time" type fields (retard pompe en second, temps bachwache real,
  etc.) are also not modeled yet — plc_service.py has no TIME reader.
  Skip/placeholder for now; ask before wiring these up since TIME
  needs its own decode (S5TIME / IEC TIME, not a struct we have yet).
- The row-13/14 offset collision in the screenshot was confirmed:
    "start filtre a sable" = 48.0 (BOOL)
    "lundi hmi"            = 48.1 (BOOL)   ← corrected, not 48.0
- "entre pression filtre a sable" (originally added after row 68 as
  REAL offset 222) is now modeled as instruments-p_in_filter.
  It was moved out of totals_and_instruments and into the instruments
  placeholder group so that synoptic.js reads it under the correct
  key ('instruments-p_in_filter') with zero JS changes required.
═══════════════════════════════════════════════════════════════════
"""

PLC_TAGS = [

    # ─────────────────────────────────────────────────────────────
    # GROUP: System / mode
    # Bytes: 0.0
    # ─────────────────────────────────────────────────────────────
    {
        "component_id": "system",
        "variables": {
            "auto": {"offset": "0.0", "type": "BOOL", "db": 2, "area": "DB"},
        }
    },

    # ─────────────────────────────────────────────────────────────
    # GROUP: HP pump start delay timers
    # Bytes: 2-9
    # ─────────────────────────────────────────────────────────────
    {
        "component_id": "hp_pump_timers",
        "variables": {
            "retard_pompe_hp": {"offset": "2", "type": "DINT", "db": 2, "area": "DB"},
            # "retard_pompe_en_second" (TIME, offset 6.0) — not modeled, TIME decode TBD
            "time_hp_heure": {"offset": "10", "type": "DINT", "db": 2, "area": "DB"},
        }
    },

    # ─────────────────────────────────────────────────────────────
    # RESERVED / DISABLED — Weekly schedule (Time_Of_Day block)
    # Bytes: 14-59 (activation/desactivation s1-s4 + wash schedule)
    # Custom scheduling will replace this. Kept here so these bytes
    # are not silently reused by a future tag.
    # ─────────────────────────────────────────────────────────────
    {
        "component_id": "schedule_RESERVED",
        "variables": {
            "activation_s1":          {"offset": "14", "type": "DINT", "db": 2, "area": "DB", "enabled": False, "note": "was Time_Of_Day, dropped"},
            "desactivation_s1":       {"offset": "18", "type": "DINT", "db": 2, "area": "DB", "enabled": False, "note": "was Time_Of_Day, dropped"},
            "activation_s2":          {"offset": "22", "type": "DINT", "db": 2, "area": "DB", "enabled": False, "note": "was Time_Of_Day, dropped"},
            "desactivation_s2":       {"offset": "26", "type": "DINT", "db": 2, "area": "DB", "enabled": False, "note": "was Time_Of_Day, dropped"},
            "activation_s3":          {"offset": "30", "type": "DINT", "db": 2, "area": "DB", "enabled": False, "note": "was Time_Of_Day, dropped"},
            "desactivation_s3":       {"offset": "34", "type": "DINT", "db": 2, "area": "DB", "enabled": False, "note": "was Time_Of_Day, dropped"},
            "activation_s4":          {"offset": "38", "type": "DINT", "db": 2, "area": "DB", "enabled": False, "note": "was Time_Of_Day, dropped"},
            "desactivation_s4":       {"offset": "44", "type": "DINT", "db": 2, "area": "DB", "enabled": False, "note": "was Time_Of_Day, dropped — gap to 48.0 confirmed as-is"},
            "heure_lavage_filtre_sable": {"offset": "56", "type": "DINT", "db": 2, "area": "DB", "enabled": False, "note": "was Time_Of_Day, dropped"},
        }
    },

    # ─────────────────────────────────────────────────────────────
    # GROUP: Sand filter — control bits & day-of-week selection
    # Bytes: 48.0 - 48.1, 54.0 - 54.5
    # NOTE: confirmed correction — "lundi hmi" is 48.1, NOT 48.0.
    # ─────────────────────────────────────────────────────────────
    {
        "component_id": "sand_filter_control",
        "variables": {
            "start_filtre_a_sable": {"offset": "48.0", "type": "BOOL", "db": 2, "area": "DB"},
            "lundi_hmi":            {"offset": "48.1", "type": "BOOL", "db": 2, "area": "DB"},
            "entre_filtre_sable":   {"offset": "TBD.0", "type": "BOOL", "db": 2, "area": "DB",
                                      "enabled": False,
                                      "note": "PLACEHOLDER — user will set real offset later. Screenshot showed 48.1, same bit as lundi_hmi (collision). Do not enable until offset is fixed in TIA and here."},
            "dimanche_hmi":         {"offset": "54.0", "type": "BOOL", "db": 2, "area": "DB"},
            "samedi_hmi":           {"offset": "54.1", "type": "BOOL", "db": 2, "area": "DB"},
            "vendredi_hmi":         {"offset": "54.2", "type": "BOOL", "db": 2, "area": "DB"},
            "jeudi_hmi":            {"offset": "54.3", "type": "BOOL", "db": 2, "area": "DB"},
            "mercredi_hmi":         {"offset": "54.4", "type": "BOOL", "db": 2, "area": "DB"},
            "mardi_hmi":            {"offset": "54.5", "type": "BOOL", "db": 2, "area": "DB"},
        }
    },

    # ─────────────────────────────────────────────────────────────
    # GROUP: Sand filter backwash / rinse timers
    # Bytes: 50, 60-81
    # ─────────────────────────────────────────────────────────────
    {
        "component_id": "sand_filter_timers",
        "variables": {
            "retard_pompe_en_minute":        {"offset": "50", "type": "DINT", "db": 2, "area": "DB"},
            "retard_filtre_bachwache_ms":     {"offset": "60", "type": "DINT", "db": 2, "area": "DB"},
            # "retard_filtre_bachwache_s" (TIME, offset 64.0) — not modeled, TIME decode TBD
            "retard_filtre_rincage_ms":       {"offset": "68", "type": "DINT", "db": 2, "area": "DB"},
            # "retard_filtre_rincage_s" (TIME, offset 72.0) — not modeled
            # "temps_bachwache_real" (TIME, offset 76.0) — not modeled
            # "temps_rincage_real" (TIME, offset 80.0) — not modeled
        }
    },

    # ─────────────────────────────────────────────────────────────
    # GROUP: Flushing
    # Bytes: 84-113
    # ─────────────────────────────────────────────────────────────
    {
        "component_id": "flushing",
        "variables": {
            "start_flushing":                  {"offset": "84", "type": "BOOL", "db": 2, "area": "DB"},
            "temps_flushing_ms":               {"offset": "86", "type": "DINT", "db": 2, "area": "DB"},
            # "temps_flushing_s" (TIME, offset 90.0) — not modeled
            "temps_hp_en_flushing_ms":         {"offset": "94", "type": "DINT", "db": 2, "area": "DB"},
            # "temps_hp_en_flushing_s" (TIME, offset 98.0) — not modeled
            "periode_temps_flushing_ms":       {"offset": "102", "type": "DINT", "db": 2, "area": "DB"},
            # "periode_temps_flushing_s" (TIME, offset 106.0) — not modeled
            # "flushing_periodique_compteur_1" (TIME, offset 110.0) — not modeled
        }
    },

    # ─────────────────────────────────────────────────────────────
    # GROUP: Feed pump — setpoints & alarms
    # Bytes: 114-150
    # ─────────────────────────────────────────────────────────────
    {
        "component_id": "feed_pump_setpoints",
        "variables": {
            "start_pompe_alimentation":          {"offset": "114", "type": "REAL", "db": 2, "area": "DB"},
            "stop_pompe_alimentation":            {"offset": "118", "type": "REAL", "db": 2, "area": "DB"},
            "mq_eau_pompe_alimentation":          {"offset": "122", "type": "REAL", "db": 2, "area": "DB"},
            "mq_eau_station":                     {"offset": "126", "type": "REAL", "db": 2, "area": "DB"},
            "temps_alarme_mq_eau_pompe_alim_ms":  {"offset": "130", "type": "DINT", "db": 2, "area": "DB"},
            # "temps_alarme_mq_eau_pompe_alim_s" (TIME, offset 134.0) — not modeled
            "minimant_de_rejet":                  {"offset": "138", "type": "REAL", "db": 2, "area": "DB"},
            "temps_alarme_minimant_rejet_ms":     {"offset": "142", "type": "DINT", "db": 2, "area": "DB"},
            # "temps_alarme_minimant_rejet_s" (TIME, offset 146.0) — not modeled
        }
    },

    # ─────────────────────────────────────────────────────────────
    # GROUP: Manual control buttons
    # Bytes: 150.0 - 150.1
    # ─────────────────────────────────────────────────────────────
    {
        "component_id": "manual_buttons",
        "variables": {
            "bouton_pompe_hp":            {"offset": "150.0", "type": "BOOL", "db": 2, "area": "DB"},
            "bouton_pompe_alimentation":   {"offset": "150.1", "type": "BOOL", "db": 2, "area": "DB"},
        }
    },

    # ─────────────────────────────────────────────────────────────
    # GROUP: Alarm thresholds — conductivity, filters, HP pump, membrane
    # Bytes: 152-195
    # ─────────────────────────────────────────────────────────────
    {
        "component_id": "alarm_thresholds",
        "variables": {
            "max_conductivity":                   {"offset": "152", "type": "REAL", "db": 2, "area": "DB"},
            "temps_alarme_max_conductivity_ms":   {"offset": "156", "type": "DINT", "db": 2, "area": "DB"},
            # "temps_alarme_max_conductivity_s" (TIME, offset 160.0) — not modeled
            "diff_pression_filtre_sable":         {"offset": "164", "type": "REAL", "db": 2, "area": "DB"},
            "diff_pression_filtre_20_micron":     {"offset": "168", "type": "REAL", "db": 2, "area": "DB"},
            "diff_pression_filtre_5_micron":      {"offset": "172", "type": "REAL", "db": 2, "area": "DB"},
            "alarme_pression_max_pompe_hp":       {"offset": "176", "type": "REAL", "db": 2, "area": "DB"},
            "alarme_pression_min_pompe_hp":       {"offset": "180", "type": "REAL", "db": 2, "area": "DB"},
            "colmatage_membrane":                 {"offset": "184", "type": "REAL", "db": 2, "area": "DB"},
            "temps_alarme_mq_eau_station_ms":     {"offset": "188", "type": "DINT", "db": 2, "area": "DB"},
            # "temps_alarme_mq_eau_station_s" (TIME, offset 192.0) — not modeled
        }
    },

    # ─────────────────────────────────────────────────────────────
    # GROUP: Water quality thresholds
    # Bytes: 196-200
    # ─────────────────────────────────────────────────────────────
    {
        "component_id": "water_quality_thresholds",
        "variables": {
            "max_orp": {"offset": "196", "type": "REAL", "db": 2, "area": "DB"},
            "max_ph":  {"offset": "200", "type": "REAL", "db": 2, "area": "DB"},
        }
    },

    # ─────────────────────────────────────────────────────────────
    # RESERVED / UNCLEAR — rows 62-64 of the screenshot
    # Bytes: 204, 208
    # Names in TIA literally show as "1997" (Time) and "1998" (DInt) —
    # almost certainly placeholder/unnamed variables never renamed.
    # Disabled until you tell me what these actually are.
    # ─────────────────────────────────────────────────────────────
    {
        "component_id": "unnamed_RESERVED",
        "variables": {
            "unnamed_1997": {"offset": "204", "type": "DINT", "db": 2, "area": "DB", "enabled": False,
                              "note": "TIA shows name '1997', type Time — not modeled, rename in TIA first"},
            "unnamed_1998": {"offset": "208", "type": "DINT", "db": 2, "area": "DB", "enabled": False,
                              "note": "TIA shows name '1998' — confirm purpose before enabling"},
        }
    },

    # ─────────────────────────────────────────────────────────────
    # GROUP: Dosing pump & HP frequency
    # Bytes: 212, 216.0-216.1
    # ─────────────────────────────────────────────────────────────
    {
        "component_id": "dosing_and_hp",
        "variables": {
            "hz":                       {"offset": "212", "type": "REAL", "db": 2, "area": "DB"},
            "pompe_dosuse":             {"offset": "216.0", "type": "BOOL", "db": 2, "area": "DB"},
            "pompe_doiseuse_manuelle":  {"offset": "216.1", "type": "BOOL", "db": 2, "area": "DB"},
        }
    },

    # ─────────────────────────────────────────────────────────────
    # GROUP: Totals
    # Bytes: 218
    # Note: "entre pression filtre a sable" (originally offset 222,
    # added after row 68) has been moved into the instruments group
    # below as "p_in_filter" so that synoptic.js reads it under the
    # correct key ('instruments-p_in_filter') with no JS changes.
    # ─────────────────────────────────────────────────────────────
    {
        "component_id": "totals_and_instruments",
        "variables": {
            "permeat_total": {"offset": "218", "type": "REAL", "db": 2, "area": "DB"},
        }
    },

    # ─────────────────────────────────────────────────────────────
    # PLACEHOLDER GROUPS — live process values read by synoptic.js
    # ─────────────────────────────────────────────────────────────
    # Every component_id and variable key below is copied EXACTLY
    # from main/static/js/synoptic.js's updateSynoptic() and its
    # _panelConfig (e.g. data['instruments-p_in_filter'],
    # bool('feed_pump-cmd'), etc.) so the names already match the
    # frontend with zero renaming once real offsets exist.
    #
    # ALL entries marked "enabled": False with offset/type = None are
    # NOT real addresses, just name reservations. telemetry_reader.py
    # skips any tag with enabled=False, so having these in the list
    # right now does not cause read attempts or errors. Fill in
    # "offset"/"type" and remove "enabled": False (default is True)
    # once each address exists in DB2.
    #
    # "writable": True marks tags that synoptic.js writes to (pump
    # start/stop buttons, auto/manual mode, backwash settings) — these
    # used to be hardcoded as HmiApp.triggerWrite(50, '<offset>', val)
    # directly in the JS, pointed at DB50. They have been rewired to
    # look up {db, offset} from THIS file by tag name instead (see
    # HmiApp.triggerWriteByTag in hmi-app.js and the updated onclick
    # handlers in synoptic.js's _panelConfig). Tags without "writable"
    # default to read-only — write attempts against them should be
    # rejected by the frontend/backend, not silently allowed.
    #
    # NetToPLCSim note: BOOL tags need "byte.bit" offsets, INT/WORD
    # need 2 free bytes, DINT/REAL need 4 free bytes — check for
    # overlap with neighboring tags before assigning real offsets.
    # ─────────────────────────────────────────────────────────────
    {
        "component_id": "instruments",
        "variables": {
            # ── LIVE — "entre pression filtre a sable", DB2 offset 222 ──
            # Confirmed REAL, 4 bytes (222-225). Moved here from
            # totals_and_instruments so synoptic.js key matches exactly.
            "p_in_filter":      {"offset": "222", "type": "REAL", "db": 2, "area": "DB"},

            # ── PLACEHOLDERS — awaiting real DB2 offsets ──────────────
            "p_out_filter":     {"offset": None, "type": None, "db": 2, "area": "DB", "enabled": False},
            "p_out_5u":         {"offset": None, "type": None, "db": 2, "area": "DB", "enabled": False},
            "p_out_1u":         {"offset": None, "type": None, "db": 2, "area": "DB", "enabled": False},
            "p_hp_pump_out":    {"offset": None, "type": None, "db": 2, "area": "DB", "enabled": False},
            "p_reject":         {"offset": None, "type": None, "db": 2, "area": "DB", "enabled": False},
            "p_permeat":        {"offset": None, "type": None, "db": 2, "area": "DB", "enabled": False},
            "flow_permeat":     {"offset": None, "type": None, "db": 2, "area": "DB", "enabled": False},
            "flow_concentrat":  {"offset": None, "type": None, "db": 2, "area": "DB", "enabled": False},
            "cond_permeat":     {"offset": None, "type": None, "db": 2, "area": "DB", "enabled": False},
            "cond_mix":         {"offset": None, "type": None, "db": 2, "area": "DB", "enabled": False},
        }
    },

    {
        "component_id": "sand_filter",
        "variables": {
            "dp_max":          {"offset": None, "type": None, "db": 2, "area": "DB", "enabled": False, "writable": True},
            "backwash_timer":  {"offset": None, "type": None, "db": 2, "area": "DB", "enabled": False},
            "in_backwash":     {"offset": None, "type": None, "db": 2, "area": "DB", "enabled": False},
            "valve_in":        {"offset": None, "type": None, "db": 2, "area": "DB", "enabled": False},
            "valve_out":       {"offset": None, "type": None, "db": 2, "area": "DB", "enabled": False},
            "valve_drain":     {"offset": None, "type": None, "db": 2, "area": "DB", "enabled": False},
            # NEW — previously hardcoded as triggerWrite(50, '4.0', dur) in synoptic.js,
            # no read-side tag existed for it before this pass.
            "backwash_duration":       {"offset": None, "type": None, "db": 2, "area": "DB", "enabled": False, "writable": True},
            # NEW — previously hardcoded as triggerWrite(50, '8.0', true) in synoptic.js,
            # fire-and-forget manual trigger bit, no read-side tag existed before this pass.
            "manual_backwash_trigger": {"offset": None, "type": None, "db": 2, "area": "DB", "enabled": False, "writable": True},
        }
    },

    {
        "component_id": "cartridge_filters",
        "variables": {
            "dp_5u":     {"offset": None, "type": None, "db": 2, "area": "DB", "enabled": False},
            "dp_1u":     {"offset": None, "type": None, "db": 2, "area": "DB", "enabled": False},
            "alarm_5u":  {"offset": None, "type": None, "db": 2, "area": "DB", "enabled": False},
            "alarm_1u":  {"offset": None, "type": None, "db": 2, "area": "DB", "enabled": False},
        }
    },

    {
        "component_id": "feed_pump",
        "variables": {
            "cmd":    {"offset": None, "type": None, "db": 2, "area": "DB", "enabled": False, "writable": True},
            "fault":  {"offset": None, "type": None, "db": 2, "area": "DB", "enabled": False},
            "p_low":  {"offset": None, "type": None, "db": 2, "area": "DB", "enabled": False},
        }
    },

    {
        "component_id": "hp_pump",
        "variables": {
            "cmd":        {"offset": None, "type": None, "db": 2, "area": "DB", "enabled": False, "writable": True},
            "fault":      {"offset": None, "type": None, "db": 2, "area": "DB", "enabled": False},
            "p_max":      {"offset": None, "type": None, "db": 2, "area": "DB", "enabled": False},
            "speed_ref":  {"offset": None, "type": None, "db": 2, "area": "DB", "enabled": False},
        }
    },

    {
        "component_id": "tanks",
        "variables": {
            "level_raw":     {"offset": None, "type": None, "db": 2, "area": "DB", "enabled": False},
            "level_permeat": {"offset": None, "type": None, "db": 2, "area": "DB", "enabled": False},
            "low_raw":       {"offset": None, "type": None, "db": 2, "area": "DB", "enabled": False},
            "high_permeat":  {"offset": None, "type": None, "db": 2, "area": "DB", "enabled": False},
        }
    },

    {
        "component_id": "global_management",
        "variables": {
            "auto":           {"offset": None, "type": None, "db": 2, "area": "DB", "enabled": False, "writable": True},
            "manual":         {"offset": None, "type": None, "db": 2, "area": "DB", "enabled": False, "writable": True},
            "alarm_general":  {"offset": None, "type": None, "db": 2, "area": "DB", "enabled": False},
            "cond_max":       {"offset": None, "type": None, "db": 2, "area": "DB", "enabled": False},
            "runtime_hr":     {"offset": None, "type": None, "db": 2, "area": "DB", "enabled": False},
            "runtime_min":    {"offset": None, "type": None, "db": 2, "area": "DB", "enabled": False},
        }
    },
]