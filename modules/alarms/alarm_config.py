"""
modules/alarms/alarm_config.py
══════════════════════════════════════════════════════════════════════════════
Single source of truth for every alarm rule.

To ADD a new alarm:  append one dict to ALARM_RULES — no code change needed.
To TUNE a threshold: change the "threshold" value here — frontend and backend
                     both read this at startup via /api/alarms/config.

Rule schema:
  id          str   Unique key.  Used as URL param in /api/alarms/test/<id>
  label       str   Human-readable name shown on alarm panel
  tag         str   PLC tag key as it appears in the bulk telemetry payload
                    format: "<component_id>-<var_key>"
  condition   str   One of: "gt" | "lt" | "gte" | "lte" | "eq" | "bool_true" | "bool_false"
  threshold   num   Comparison value (ignored for bool_true / bool_false)
  severity    str   "CRITICAL" | "WARNING" | "INFO"
  unit        str   Display unit string (µS/cm, Bar, …)
  whatsapp    bool  Whether to dispatch a WhatsApp message on trigger
  message     str   WhatsApp message body template.
                    Use {value} and {threshold} as placeholders.
  icon        str   FontAwesome class string for UI display
  group       str   Logical grouping for the alarm panel display
══════════════════════════════════════════════════════════════════════════════
"""

ALARM_RULES = [

    # ── HIGH-PRESSURE PUMP ──────────────────────────────────────────────────
    {
        "id":         "hp_overpressure",
        "label":      "HP Pump — Overpressure",
        "tag":        "instruments-p_hp_pump_out",
        "condition":  "gt",
        "threshold":  16.0,
        "severity":   "CRITICAL",
        "unit":       "Bar",
        "whatsapp":   True,
        "message":    "🚨 CRITICAL — HP OVERPRESSURE\nStation: RO Skid 01\nValue: {value:.1f} Bar (limit: {threshold} Bar)\nTime: {time}\nImmediate action required!",
        "icon":       "fa-solid fa-gauge-high",
        "group":      "HP Pump",
    },
    {
        "id":         "hp_pump_fault",
        "label":      "HP Pump — Drive Fault",
        "tag":        "hp_pump-fault",
        "condition":  "bool_true",
        "threshold":  None,
        "severity":   "CRITICAL",
        "unit":       "",
        "whatsapp":   True,
        "message":    "🚨 FAULT — HP PUMP DRIVE FAULT\nStation: RO Skid 01\nTime: {time}\nCheck VFD panel immediately!",
        "icon":       "fa-solid fa-circle-exclamation",
        "group":      "HP Pump",
    },
    {
        "id":         "hp_pump_low_speed",
        "label":      "HP Pump — Speed Below Min",
        "tag":        "hp_pump-speed_hz",
        "condition":  "lt",
        "threshold":  10.0,
        "severity":   "WARNING",
        "unit":       "Hz",
        "whatsapp":   False,
        "message":    "⚠️ WARNING — HP PUMP SPEED LOW\nSpeed: {value:.1f} Hz (min: {threshold} Hz)",
        "icon":       "fa-solid fa-arrow-down",
        "group":      "HP Pump",
    },

    # ── FEED PUMP ────────────────────────────────────────────────────────────
    {
        "id":         "feed_pump_fault",
        "label":      "Feed Pump — Motor Fault",
        "tag":        "feed_pump-fault",
        "condition":  "bool_true",
        "threshold":  None,
        "severity":   "CRITICAL",
        "unit":       "",
        "whatsapp":   True,
        "message":    "🚨 FAULT — FEED PUMP FAULT\nStation: RO Skid 01\nTime: {time}\nCheck motor protection relay!",
        "icon":       "fa-solid fa-circle-exclamation",
        "group":      "Feed Pump",
    },
    {
        "id":         "feed_pump_low_pressure",
        "label":      "Feed Pump — Low Suction Pressure",
        "tag":        "feed_pump-p_low",
        "condition":  "lt",
        "threshold":  0.5,
        "severity":   "WARNING",
        "unit":       "Bar",
        "whatsapp":   False,
        "message":    "⚠️ WARNING — LOW SUCTION PRESSURE\nValue: {value:.2f} Bar (min: {threshold} Bar)",
        "icon":       "fa-solid fa-arrow-down",
        "group":      "Feed Pump",
    },

    # ── RAW WATER TANK ───────────────────────────────────────────────────────
    {
        "id":         "tank_raw_low",
        "label":      "Raw Water Tank — Low Level",
        "tag":        "tanks-level_raw_pct",
        "condition":  "lt",
        "threshold":  15.0,
        "severity":   "WARNING",
        "unit":       "%",
        "whatsapp":   True,
        "message":    "⚠️ WARNING — RAW WATER TANK LOW\nStation: RO Skid 01\nLevel: {value:.0f}% (alarm: {threshold}%)\nTime: {time}",
        "icon":       "fa-solid fa-water",
        "group":      "Tanks",
    },
    {
        "id":         "tank_permeat_full",
        "label":      "Permeate Tank — High Level",
        "tag":        "tanks-level_permeat_pct",
        "condition":  "gt",
        "threshold":  90.0,
        "severity":   "WARNING",
        "unit":       "%",
        "whatsapp":   False,
        "message":    "⚠️ WARNING — PERMEATE TANK FULL\nLevel: {value:.0f}% (limit: {threshold}%)",
        "icon":       "fa-solid fa-fill-drip",
        "group":      "Tanks",
    },

    # ── PERMEATE QUALITY ─────────────────────────────────────────────────────
    {
        "id":         "cond_high",
        "label":      "Permeate — High Conductivity",
        "tag":        "instruments-cond_permeat",
        "condition":  "gt",
        "threshold":  500.0,
        "severity":   "CRITICAL",
        "unit":       "µS/cm",
        "whatsapp":   True,
        "message":    "🚨 QUALITY ALARM — HIGH CONDUCTIVITY\nStation: RO Skid 01\nConductivity: {value:.0f} µS/cm (limit: {threshold} µS/cm)\nTime: {time}\nCheck membrane integrity!",
        "icon":       "fa-solid fa-droplet",
        "group":      "Permeate Quality",
    },

    # ── SAND FILTER ──────────────────────────────────────────────────────────
    {
        "id":         "sand_filter_dp_high",
        "label":      "Sand Filter — High ΔP (Clogged)",
        "tag":        "sand_filter-dp",
        "condition":  "gt",
        "threshold":  0.5,
        "severity":   "WARNING",
        "unit":       "Bar",
        "whatsapp":   False,
        "message":    "⚠️ WARNING — SAND FILTER CLOGGED\nΔP: {value:.2f} Bar (limit: {threshold} Bar)\nInitiate backwash.",
        "icon":       "fa-solid fa-filter-circle-xmark",
        "group":      "Filtration",
    },

    # ── CARTRIDGE FILTERS ────────────────────────────────────────────────────
    {
        "id":         "filter_5u_dp_high",
        "label":      "5µ Filter — High ΔP (Replace)",
        "tag":        "cartridge_filters-dp_5u",
        "condition":  "gt",
        "threshold":  1.0,
        "severity":   "WARNING",
        "unit":       "Bar",
        "whatsapp":   False,
        "message":    "⚠️ WARNING — 5µ CARTRIDGE CLOGGED\nΔP: {value:.2f} Bar. Replace cartridge.",
        "icon":       "fa-solid fa-filter",
        "group":      "Filtration",
    },
    {
        "id":         "filter_1u_dp_high",
        "label":      "1µ Filter — High ΔP (Replace)",
        "tag":        "cartridge_filters-dp_1u",
        "condition":  "gt",
        "threshold":  1.0,
        "severity":   "WARNING",
        "unit":       "Bar",
        "whatsapp":   False,
        "message":    "⚠️ WARNING — 1µ CARTRIDGE CLOGGED\nΔP: {value:.2f} Bar. Replace cartridge.",
        "icon":       "fa-solid fa-filter",
        "group":      "Filtration",
    },
]

# ── NOTIFICATION RECIPIENTS ───────────────────────────────────────────────────
# Move to environment variables / .env before production deployment.
# Only CRITICAL severity alarms with whatsapp=True are sent here.
WHATSAPP_NUMBERS = [
    "+21698760727",
 #   "+21698760700",
    # perfect it worked just the gestionnaire de fichier in ouvrir is still open it didnt close on it s own and it s till saying generation des fichiers "+21693760724",
]

# ── POLLING INTERVAL ──────────────────────────────────────────────────────────
POLL_INTERVAL_SECONDS = 2

# ── SEVERITY → DISPLAY COLOR MAP ─────────────────────────────────────────────
SEVERITY_COLORS = {
    "CRITICAL": {"bg": "#7F1D1D", "border": "#EF4444", "text": "#FCA5A5", "badge": "#DC2626"},
    "WARNING":  {"bg": "#78350F", "border": "#F59E0B", "text": "#FCD34D", "badge": "#D97706"},
    "INFO":     {"bg": "#1E3A5F", "border": "#60A5FA", "text": "#93C5FD", "badge": "#3B82F6"},
}