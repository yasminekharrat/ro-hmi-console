import time
import serial
import threading
from flask import Blueprint, jsonify, request

vfd_bp = Blueprint('vfd', __name__)

try:
    import minimalmodbus
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False

vfd_settings = {
    "port": "COM3",
    "baud_rate": 9600,
    "slave_address": 1,
    "data_format": "N-8-1"
}

instrument = None
# Global hardware mutual-exclusion lock to prevent half-duplex collisions
serial_lock = threading.Lock()

def init_vfd():
    global instrument
    if SERIAL_AVAILABLE:
        try:
            if instrument and instrument.serial and instrument.serial.is_open:
                instrument.serial.close()
            
            instrument = minimalmodbus.Instrument(vfd_settings["port"], vfd_settings["slave_address"])
            instrument.serial.baudrate = vfd_settings["baud_rate"]
            instrument.serial.bytesize = 8
            instrument.serial.parity = serial.PARITY_NONE
            instrument.serial.stopbits = 1
            instrument.serial.timeout = 0.6  # Stable window for industrial packet capture
            
            # Critical delay to clear line turnaround echoes
            instrument.wait_time = 0.05
            instrument.clear_buffers_before_each_transaction = True
            return True
        except Exception:
            instrument = None
            return False
    return False

# Self-initialize on startup
init_vfd()

# --- THE DEFINITIVE VEICHI AC10 SYSTEM REGISTER MAP (BASE-10 INTEGERS) ---
REG_CONTROL_CMD   = 12288 # 0x3000: Master Run/Stop Control Command Word
REG_FREQ_SETPOINT = 8448   # 0x0109: F01.09 Keyboard Digital Target Frequency (Hz)

# Monitoring registers
REG_OUTPUT_FREQ   = 8449  # 0x2201: C01.01 Live Display Output Frequency
REG_OUTPUT_CURR   = 8450  # 0x2202: C01.02 Live Display Output Current


def _execute_safe_write(register, value, decimals=0):
    """
    Internal helper executing the validated write routine within an active lock.
    Forces Function Code 16 first, with an automatic fallback to Function Code 06.
    """
    if not instrument:
        raise Exception("VFD device connection handle unavailable.")
    try:
        # Strategy A: Attempt forced multi-register write (FC16)
        instrument.write_register(register, value, number_of_decimals=decimals, functioncode=16)
    except Exception:
        # Strategy B: Automatic fallback to single register write (FC06)
        instrument.write_register(register, value, number_of_decimals=decimals, functioncode=6)


# --- THREAD-SAFE AUTO-SCAN CONNECTIONS ENGINE ---
@vfd_bp.route('/api/vfd/scan', methods=['POST'])
def scan_bus_connections():
    """Sweeps target serial port across Modbus node addresses to identify hardware presence."""
    global instrument
    if not SERIAL_AVAILABLE:
        return jsonify({"success": False, "devices": [], "msg": "minimalmodbus library missing"})
        
    data = request.get_json() or {}
    scan_port = data.get("port", vfd_settings["port"])
    
    baud_sweep = [9600, 19200]
    address_range = range(1, 11) 
    discovered_devices = []
    
    with serial_lock:
        if instrument and instrument.serial and instrument.serial.is_open:
            instrument.serial.close()

        for baud in baud_sweep:
            for address in address_range:
                scan_inst = None
                try:
                    scan_inst = minimalmodbus.Instrument(scan_port, address)
                    scan_inst.serial.baudrate = baud
                    scan_inst.serial.timeout = 0.15
                    scan_inst.wait_time = 0.02
                    scan_inst.clear_buffers_before_each_transaction = True
                    
                    # Interrogate using verified live monitoring register
                    scan_inst.read_register(REG_OUTPUT_FREQ, number_of_decimals=2, functioncode=3)
                    
                    discovered_devices.append({
                        "port": scan_port,
                        "baud_rate": baud,
                        "slave_address": address,
                        "device_type": "Veichi AC10 VFD" if address == 1 else "Unknown Modbus Device"
                    })
                except Exception:
                    continue 
                finally:
                    if scan_inst and scan_inst.serial and scan_inst.serial.is_open:
                        scan_inst.serial.close()
                    
        init_vfd()
        
    return jsonify({"success": True, "devices": discovered_devices})

# --- CONFIGURATION INTERFACES ---
@vfd_bp.route('/api/vfd/config', methods=['GET', 'POST'])
def handle_config():
    global vfd_settings
    if request.method == 'POST':
        data = request.get_json() or {}
        vfd_settings["port"] = data.get("port", vfd_settings["port"])
        vfd_settings["baud_rate"] = int(data.get("baud_rate", vfd_settings["baud_rate"]))
        vfd_settings["slave_address"] = int(data.get("slave_address", vfd_settings["slave_address"]))
        
        with serial_lock:
            init_vfd()
            
        return jsonify({"success": True, "current_settings": vfd_settings})
    return jsonify(vfd_settings)

# --- READ REALTIME STATUS ENGINE ---
@vfd_bp.route('/api/vfd/status', methods=['GET'])
def get_status():
    if not SERIAL_AVAILABLE or instrument is None:
        return jsonify({"status": "OFFLINE", "output_frequency": 0.0, "output_current": 0.0, "error": "Offline"})
    
    with serial_lock:
        try:
            if not instrument.serial.is_open:
                instrument.serial.open()
                
            # Clear line noise residues before transaction
            instrument.serial.reset_input_buffer()
            
            out_freq = instrument.read_register(REG_OUTPUT_FREQ, number_of_decimals=2, functioncode=3)
            time.sleep(0.015)  # Brief wire settling delay
            out_curr = instrument.read_register(REG_OUTPUT_CURR, number_of_decimals=2, functioncode=3)
            
            return jsonify({
                "status": "ONLINE", 
                "output_frequency": out_freq, 
                "output_current": out_curr, 
                "settings": vfd_settings,
                "error": None
            })
        except Exception as e:
            return jsonify({"status": "COMM_ERROR", "output_frequency": 0.0, "output_current": 0.0, "error": str(e)}), 200

# --- WRITE SEQUENCE CONTROL COILS ---
@vfd_bp.route('/api/vfd/command', methods=['POST'])
def send_command():
    data = request.get_json() or {}
    action = data.get("action")
    
    if not SERIAL_AVAILABLE or instrument is None: 
        return jsonify({"success": False, "msg": "Hardware interface uninitialized"}), 400
        
    with serial_lock:
        try:
            if not instrument.serial.is_open:
                instrument.serial.open()
                
            instrument.serial.reset_input_buffer()
            instrument.serial.reset_output_buffer()

            # Map the action string to the exact integer requested by the control register
            if action == "START_FWD":
                cmd = 1
            elif action == "START_REV":
                cmd = 2
            elif action == "STOP":
                cmd = 5
            elif action == "RESET":
                cmd = 7
            else:
                return jsonify({"success": False, "msg": f"Invalid dynamic action requested: {action}"}), 400

            # Execute write via robust dual-strategy function
            _execute_safe_write(REG_CONTROL_CMD, cmd, decimals=0)
            return jsonify({"success": True})
            
        except Exception as e: 
            return jsonify({"success": False, "msg": str(e)}), 500

# --- WRITE FREQUENCY SETPOINT VALUE ---
@vfd_bp.route('/api/vfd/setpoint', methods=['POST'])
def change_setpoint():
    data = request.get_json() or {}
    if not SERIAL_AVAILABLE or instrument is None:
        return jsonify({"success": False, "msg": "Hardware interface uninitialized"}), 400
        
    with serial_lock:
        try:
            val = float(data.get("value", 0.0))
            
            if not (0.0 <= val <= 50.0):
                return jsonify({"success": False, "msg": "Frequency out of range (0-50Hz)"}), 400
                
            if not instrument.serial.is_open:
                instrument.serial.open()
                
            instrument.serial.reset_input_buffer()
            instrument.serial.reset_output_buffer()
            
            # Execute write via robust dual-strategy function (maintaining 2 decimal scales)
            _execute_safe_write(REG_FREQ_SETPOINT, val, decimals=2)
            return jsonify({"success": True})
        except Exception as e: 
            return jsonify({"success": False, "msg": str(e)}), 500