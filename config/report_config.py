# config/report_config.py
# ---------------------------------------------------------------------------
# Declares which PLC tags appear in the daily / weekly Excel report,
# their human-readable labels, units, and display groups.
#
# Convention
# ----------
# - tag_id      : must match a key in PLC_TAGS (tags_config.py)
# - label       : French label shown in the Excel sheet header row
# - unit        : appended to the label in parentheses, e.g. "bar"
# - group       : sheet-tab / section the tag belongs to in the report
# - precision   : decimal places for float values (default 2)
# ---------------------------------------------------------------------------

REPORT_TAGS = [
    # ── Instruments / Pressions ─────────────────────────────────────────────
    {
        "tag_id":    "instruments-pressure_in",
        "label":     "Pression entrée",
        "unit":      "bar",
        "group":     "Pressions",
        "precision": 2,
    },
    {
        "tag_id":    "instruments-pressure_out",
        "label":     "Pression sortie",
        "unit":      "bar",
        "group":     "Pressions",
        "precision": 2,
    },
    {
        "tag_id":    "instruments-dp_sand",
        "label":     "ΔP filtre à sable",
        "unit":      "bar",
        "group":     "Pressions",
        "precision": 2,
    },
    {
        "tag_id":    "instruments-dp_cartridge",
        "label":     "ΔP filtres à cartouches",
        "unit":      "bar",
        "group":     "Pressions",
        "precision": 2,
    },
    # ── Débit / Conductivité ────────────────────────────────────────────────
    {
        "tag_id":    "instruments-flow",
        "label":     "Débit perméat",
        "unit":      "m³/h",
        "group":     "Débit & Qualité",
        "precision": 2,
    },
    {
        "tag_id":    "instruments-conductivity",
        "label":     "Conductivité",
        "unit":      "µS/cm",
        "group":     "Débit & Qualité",
        "precision": 1,
    },
    # ── Niveaux cuves ───────────────────────────────────────────────────────
    {
        "tag_id":    "tanks-level_raw",
        "label":     "Niveau cuve eau brute",
        "unit":      "%",
        "group":     "Cuves",
        "precision": 1,
    },
    {
        "tag_id":    "tanks-level_product",
        "label":     "Niveau cuve eau produite",
        "unit":      "%",
        "group":     "Cuves",
        "precision": 1,
    },
    # ── États pompes ────────────────────────────────────────────────────────
    {
        "tag_id":    "feed_pump-running",
        "label":     "Pompe alimentation – marche",
        "unit":      "",
        "group":     "Pompes",
        "precision": 0,
    },
    {
        "tag_id":    "hp_pump-running",
        "label":     "Pompe HP – marche",
        "unit":      "",
        "group":     "Pompes",
        "precision": 0,
    },
    # ── Alarmes / Défauts ───────────────────────────────────────────────────
    {
        "tag_id":    "feed_pump-fault",
        "label":     "Défaut pompe alimentation",
        "unit":      "",
        "group":     "Alarmes",
        "precision": 0,
    },
    {
        "tag_id":    "hp_pump-fault",
        "label":     "Défaut pompe HP",
        "unit":      "",
        "group":     "Alarmes",
        "precision": 0,
    },
]

# ── Schedule ─────────────────────────────────────────────────────────────────
# Daily report:  sent every day at DAILY_HOUR:DAILY_MINUTE (24h clock)
# Weekly report: sent every WEEKLY_DAY (0=Mon … 6=Sun) at the same hour
DAILY_HOUR    = 7       # 07:00
DAILY_MINUTE  = 0
WEEKLY_DAY    = 0       # Monday

# ── WhatsApp recipient ───────────────────────────────────────────────────────
# Same format as alarm_config.py — international number without "+"
REPORT_PHONE  = "21600000000"   # ← replace with the real recipient

# ── History window ───────────────────────────────────────────────────────────
# The telemetry buffer keeps at most this many samples per tag.
# At 500 ms / poll:  2 samples/s × 86 400 s/day = 172 800  → ~175 000 is safe.
# Set to 7 days of samples for the weekly report.
MAX_HISTORY_SAMPLES = 7 * 172_800   # ≈ 1 209 600