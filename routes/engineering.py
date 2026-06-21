import os
import json
from flask import Blueprint, request, jsonify

# Create the blueprint
engineering_bp = Blueprint('engineering_bp', __name__)

# Path to persist engineering settings
CONFIG_PATH = os.path.join(os.path.abspath(os.path.dirname(__file__)), '..', 'config', 'engineering_settings.json')

def load_settings():
    """Loads current settings from disk, or returns default structure."""
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {"plc": {}, "calibration": {}}

def save_settings(settings_dict):
    """Saves settings to disk."""
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, 'w') as f:
        json.dump(settings_dict, f, indent=4)


# ── PLC CONFIGURATION ENDPOINT ──────────────────────────────────────────

@engineering_bp.route('/api/plc-config', methods=['POST'])
def save_plc_config():
    payload = request.get_json()
    if not payload:
        return jsonify({"success": False, "message": "No payload provided"}), 400

    try:
        settings = load_settings()
        settings['plc'] = payload
        save_settings(settings)
        
        # TODO: Here you would normally import your PLC comms module 
        # and trigger a reconnect with the new IP/Rack/Slot parameters.
        
        return jsonify({"success": True, "message": "PLC configuration saved."})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


# ── CALIBRATION OFFSETS ENDPOINT ────────────────────────────────────────

@engineering_bp.route('/api/engineering/calibration', methods=['POST'])
def save_calibration():
    payload = request.get_json()
    if not payload or 'offsets' not in payload:
        return jsonify({"success": False, "message": "Invalid payload format"}), 400

    try:
        settings = load_settings()
        settings['calibration'] = payload['offsets']
        save_settings(settings)
        
        # TODO: Here you would normally update the live memory map/tags 
        # so the HMI immediately reflects the new offsets.
        
        return jsonify({"success": True, "message": "Calibration offsets saved."})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500