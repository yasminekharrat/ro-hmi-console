"""
modules/alarms/alarm_routes.py
══════════════════════════════════════════════════════════════════════════════
Flask blueprint: /api/alarms/*

All endpoints are read-only or fire-and-forget — no PLC writes happen here.
The alarm_engine module owns all state; this file is a thin HTTP surface.

Routes:
    GET    /api/alarms/status      → current active/clear state of all rules
    GET    /api/alarms/log         → recent event log (newest first)
    GET    /api/alarms/config      → rule definitions (for frontend thresholds)
    POST   /api/alarms/test/<id>   → manually fire a test dispatch
    GET    /api/alarms/wa-status   → is WhatsApp session ready?
    GET    /api/alarms/mock-data   → fake PLC data for isolated WhatsApp testing
══════════════════════════════════════════════════════════════════════════════
"""

import os
from flask import Blueprint, jsonify, request

alarm_blueprint = Blueprint(
    "alarms",
    __name__,
    template_folder=os.path.join("..", "..", "main", "templates"),
    url_prefix="/api/alarms",
)


@alarm_blueprint.route("/mock-data", methods=["GET"])
def get_mock_alarm_data():
    """
    Dedicated endpoint just for the alarm engine to test WhatsApp 
    dispatch without needing the physical PLC.
    """
    mock_data = {
        "instruments-p_hp_pump_out": 18.5,       # Overpressure CRITICAL
        "hp_pump-fault": True,                    # Drive Fault CRITICAL
        "instruments-cond_permeat": 620.0        # High Conductivity CRITICAL
    }
    return jsonify(mock_data)


@alarm_blueprint.route("/status", methods=["GET"])
def alarm_status():
    """
    Returns the current active/clear state of every alarm rule.
    Called by hmi-app.js every poll cycle to drive on-screen indicators.
    """
    import modules.alarms.alarm_engine as engine  # Local import breaks circularity
    return jsonify(engine.get_status())


@alarm_blueprint.route("/log", methods=["GET"])
def alarm_log():
    """
    Returns the N most recent alarm events.
    Frontend alarm panel calls this to populate the event table.
    """
    import modules.alarms.alarm_engine as engine  # Local import breaks circularity
    limit = int(request.args.get("limit", 100))
    return jsonify({"log": engine.get_log(limit)})


@alarm_blueprint.route("/config", methods=["GET"])
def alarm_config_endpoint():
    """
    Returns the full rule config (without raw message templates).
    Frontend uses this to know rule labels, thresholds, severity, and icons.
    """
    import modules.alarms.alarm_engine as engine  # Local import breaks circularity
    return jsonify({"rules": engine.get_config()})


@alarm_blueprint.route("/test/<rule_id>", methods=["POST"])
def alarm_test(rule_id: str):
    """
    Manually trigger a test dispatch for a specific rule.
    Used by the HMI alarm panel test buttons.
    """
    import modules.alarms.alarm_engine as engine  # Local import breaks circularity
    result = engine.trigger_test(rule_id)
    status_code = 200 if result["ok"] else 404
    return jsonify(result), status_code


@alarm_blueprint.route("/wa-status", methods=["GET"])
def wa_status():
    """Quick check: is the WhatsApp Web session authenticated?"""
    import modules.alarms.alarm_engine as engine  # Local import breaks circularity
    return jsonify({
        "ready": engine._wa_ready,
        "msg": "Session active" if engine._wa_ready else "Waiting for QR scan",
    })