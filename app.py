import os
import sys
import threading

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from flask import Flask, render_template, send_from_directory, jsonify
from flask_cors import CORS
from jinja2 import ChoiceLoader, FileSystemLoader

from routes.telemetry import telemetry_bp
from modules.vfd.vfd_routes import vfd_blueprint
from modules.alarms.alarm_routes import alarm_blueprint
from config.tags_config import PLC_TAGS

# ── APP INIT ──────────────────────────────────────────────────────────────────

app = Flask(
    __name__,
    template_folder="main/templates",
    static_folder="main/static",
)

# Tell Jinja to search your default templates directory FIRST, 
# and fallback to the root directory for your custom modules layout.
app.jinja_loader = ChoiceLoader([
    FileSystemLoader("main/templates"),
    FileSystemLoader(".")  # "." points to your project root folder
])

# TODO (Issue #5): scope CORS to known origins before production deployment.
CORS(app)

# ── BLUEPRINT REGISTRATION ───────────────────────────────────────────────────

app.register_blueprint(telemetry_bp)
app.register_blueprint(vfd_blueprint)       # URL prefix configured internally (/vfd)
app.register_blueprint(alarm_blueprint)     # URL prefix configured internally (/api/alarms)

# ── ROUTES ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    """Main HMI dashboard."""
    return render_template("index.html")


@app.route("/api/tags-config", methods=["GET"])
def get_tags_config():
    """Exposes PLC_TAGS to the frontend initialization loop."""
    return jsonify(PLC_TAGS)


# ── STATIC FILE FALLBACK ROUTES ───────────────────────────────────────────────

@app.route("/static/js/hmi-comms.js")
@app.route("/static/js/hmi_comms.js")
def serve_hmi_comms():
    js_path = os.path.join(app.root_path, "main", "static", "js")
    fname = "hmi_comms.js" if os.path.exists(os.path.join(js_path, "hmi_comms.js")) else "hmi-comms.js"
    return send_from_directory(js_path, fname)


@app.route("/static/js/hmi-app.js")
@app.route("/static/js/hmi_app.js")
def serve_hmi_app():
    js_path = os.path.join(app.root_path, "main", "static", "js")
    fname = "hmi_app.js" if os.path.exists(os.path.join(js_path, "hmi_app.js")) else "hmi-app.js"
    return send_from_directory(js_path, fname)


# ── MODULE ASSET ROUTES ───────────────────────────────────────────────────────

@app.route("/modules/vfd/vfd-panel.html")
def serve_vfd_panel():
    return send_from_directory(os.path.join(app.root_path, "modules", "vfd"), "vfd-panel.html")


@app.route("/modules/vfd/vfd_comms.js")
def serve_vfd_js():
    return send_from_directory(os.path.join(app.root_path, "modules", "vfd"), "vfd_comms.js")


@app.route("/modules/alarms/alarm-panel.html")
def serve_alarm_panel():
    return send_from_directory(os.path.join(app.root_path, "modules", "alarms"), "alarm-panel.html")


@app.route("/modules/alarms/alarm_comms.js")
def serve_alarm_js():
    return send_from_directory(os.path.join(app.root_path, "modules", "alarms"), "alarm_comms.js")


# ── ENTRY POINT ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # WERKZEUG guard — only start background services in the real worker process.
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not os.environ.get("DEBUG"):
        from modules.alarms import alarm_engine
        alarm_engine.start_engine()

        # WhatsApp Web auto-launch on startup:
        threading.Thread(target=alarm_engine.init_whatsapp_session, daemon=True).start()

    # Issue #4: read debug flag from environment. Never hardcode True in production.
    debug_mode = os.environ.get("DEBUG", "0").strip() in ("1", "true", "True")

    app.run(host="0.0.0.0", port=5000, debug=debug_mode)