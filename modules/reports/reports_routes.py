# modules/reports/report_routes.py
# ---------------------------------------------------------------------------
# Blueprint: report_bp  (url_prefix = /api/reports)
#
# Routes
# ──────
# GET  /api/reports/status           → engine status + next scheduled runs
# POST /api/reports/trigger-daily    → immediately build & send daily bilan
# POST /api/reports/trigger-weekly   → immediately build & send weekly bilan
# ---------------------------------------------------------------------------

import os
from flask import Blueprint, jsonify, send_from_directory

report_bp = Blueprint("report_bp", __name__, url_prefix="/api/reports")

# Injected by app.py after the engine is created
_engine = None


def set_engine(engine):
    global _engine
    _engine = engine


@report_bp.route("/status", methods=["GET"])
def status():
    if _engine is None:
        return jsonify({"status": "not_started"}), 503
    return jsonify(_engine.status())


@report_bp.route("/trigger-daily", methods=["POST"])
def trigger_daily():
    if _engine is None:
        return jsonify({"status": "error", "message": "Engine not started"}), 503
    result = _engine.trigger_daily()
    return jsonify(result), 200 if result["status"] == "ok" else 500


@report_bp.route("/trigger-weekly", methods=["POST"])
def trigger_weekly():
    if _engine is None:
        return jsonify({"status": "error", "message": "Engine not started"}), 503
    result = _engine.trigger_weekly()
    return jsonify(result), 200 if result["status"] == "ok" else 500


@report_bp.route("/list", methods=["GET"])
def list_reports():
    """Return sorted list of generated .xlsx files (newest first)."""
    from modules.reports.report_engine import REPORT_OUTPUT_DIR
    try:
        os.makedirs(REPORT_OUTPUT_DIR, exist_ok=True)
        files = sorted(
            [f for f in os.listdir(REPORT_OUTPUT_DIR) if f.endswith(".xlsx")],
            reverse=True,
        )
        return jsonify({"files": files})
    except Exception as exc:
        return jsonify({"files": [], "error": str(exc)})


@report_bp.route("/download/<filename>", methods=["GET"])
def download_report(filename):
    """Download a single .xlsx report file."""
    from modules.reports.report_engine import REPORT_OUTPUT_DIR
    if not filename.endswith(".xlsx") or "/" in filename or "\\" in filename:
        return jsonify({"error": "Invalid filename"}), 400
    return send_from_directory(REPORT_OUTPUT_DIR, filename, as_attachment=True)