import os
import sys
import threading

# Ensure the project root is in the Python path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from flask import Flask, render_template, send_from_directory, jsonify
from flask_cors import CORS
from jinja2 import ChoiceLoader, FileSystemLoader

# ── BLUEPRINT IMPORTS ─────────────────────────────────────────────────────────
from routes.telemetry import telemetry_bp
from routes.engineering import engineering_bp  # <-- Integrated engineering blueprint
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
app.register_blueprint(engineering_bp)      # Registered engineering blueprint
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

# ── STATIC & MODULE ASSET ROUTES (DYNAMIC) ────────────────────────────────────

@app.route("/static/js/<path:filename>")
def serve_hmi_js(filename):
    """Dynamically serves JS files, gracefully handling underscore/hyphen mismatches."""
    js_path = os.path.join(app.root_path, "main", "static", "js")
    
    # Handle specific known naming mismatches for core scripts
    if filename in ("hmi-comms.js", "hmi_comms.js"):
        fname = "hmi_comms.js" if os.path.exists(os.path.join(js_path, "hmi_comms.js")) else "hmi-comms.js"
    elif filename in ("hmi-app.js", "hmi_app.js"):
        fname = "hmi_app.js" if os.path.exists(os.path.join(js_path, "hmi_app.js")) else "hmi-app.js"
    else:
        fname = filename

    return send_from_directory(js_path, fname)

@app.route("/modules/<module_name>/<path:filename>")
def serve_module_assets(module_name, filename):
    """Dynamically serves HTML/JS assets directly from any module's directory."""
    module_path = os.path.join(app.root_path, "modules", module_name)
    return send_from_directory(module_path, filename)

# ── ENTRY POINT ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # WERKZEUG guard — only start background services in the real worker process.
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not os.environ.get("DEBUG"):
        from modules.alarms import alarm_engine
        alarm_engine.start_engine()

        # WhatsApp Web auto-launch on startup:
        threading.Thread(target=alarm_engine.init_whatsapp_session, daemon=True).start()

    # Issue #4: read debug flag from environment. Never hardcode True in production.
    debug_mode = os.environ.get("DEBUG", "0").strip().lower() in ("1", "true")

    app.run(host="0.0.0.0", port=5000, debug=debug_mode)