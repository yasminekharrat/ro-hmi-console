import os
import time
import threading
import serial.tools.list_ports
from flask import Blueprint, jsonify, request, render_template

# ==============================================================================
# --- BLUEPRINT CONFIGURATION ---
# ==============================================================================
vfd_blueprint = Blueprint(
    'vfd',
    __name__,
    template_folder=os.path.join('..', '..', 'main', 'templates'),
    static_folder=os.path.join('..', '..', 'static'),
    static_url_path='/static'
)

# ==============================================================================
# --- HARDWARE PROTECTION & GLOBAL STATE ---
# ==============================================================================
try:
    import minimalmodbus
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False

vfd_settings = {
    "port": "COM3",
    "baud_rate": 9600,
    "slave_address": 1
}

instrument = None
serial_lock = threading.Lock()

# Runtime telemetry counters
_tx_count = 0
_rx_count = 0
_crc_errors = 0


# ==============================================================================
# --- SINGLE UNIFIED INSTRUMENT FACTORY ---
# ==============================================================================

def _build_instrument(port, slave_id, baud):
    """
    Low-level: construct a fresh minimalmodbus.Instrument with the
    standard RS-485 / Veichi AC10 settings.  Caller holds serial_lock.
    """
    inst = minimalmodbus.Instrument(port, slave_id)
    inst.serial.baudrate  = baud
    inst.serial.bytesize  = 8
    inst.serial.parity    = minimalmodbus.serial.PARITY_NONE
    inst.serial.stopbits  = 1
    inst.serial.timeout   = 0.8
    inst.mode             = minimalmodbus.MODE_RTU
    inst.wait_time        = 0.05
    inst.clear_buffers_before_each_transaction = True
    return inst


def init_vfd(port=None, baud=None, slave_id=None):
    """
    Public entry point: initialise (or re-initialise) the global instrument.
    """
    global instrument

    if not SERIAL_AVAILABLE:
        print("[VFD] minimalmodbus not installed — running in offline mode.")
        return

    if port:     vfd_settings["port"]          = port
    if baud:     vfd_settings["baud_rate"]     = int(baud)
    if slave_id: vfd_settings["slave_address"] = int(slave_id)

    with serial_lock:
        try:
            if instrument and hasattr(instrument, 'serial') and instrument.serial.is_open:
                instrument.serial.close()
        except Exception:
            pass

        try:
            instrument = _build_instrument(
                vfd_settings["port"],
                vfd_settings["slave_address"],
                vfd_settings["baud_rate"],
            )
            print(
                f"[VFD] Initialised on {vfd_settings['port']} "
                f"[Baud:{vfd_settings['baud_rate']} "
                f"ID:{vfd_settings['slave_address']}]"
            )
        except Exception as e:
            print(f"[VFD] Warning: Could not bind port ({e}). Ready for re-link.")
            instrument = None


# ==============================================================================
# --- VEICHI AC10 REGISTER MAP ---
# ==============================================================================

# Core telemetry / control
REG_CONTROL_CMD   = 0x3000
REG_FREQ_SETPOINT = 0x0109
REG_OUTPUT_FREQ   = 0x2101
REG_OUTPUT_CURR   = 0x2102
REG_IN_AN         = 0x2110

# F01.xx — Motor / frequency parameters
F01_REGS = {
    "F01.00": {"addr": 0x0100, "name": "Control Mode",            "dec": 0, "min": 0,    "max": 33,      "unit": ""},
    "F01.01": {"addr": 0x0101, "name": "Run Command Channel",     "dec": 0, "min": 0,    "max": 65535,   "unit": ""},
    "F01.02": {"addr": 0x0102, "name": "Freq Source Channel A",   "dec": 0, "min": 0,    "max": 11,      "unit": ""},
    "F01.03": {"addr": 0x0103, "name": "Channel A Gain",          "dec": 1, "min": 0.0,  "max": 500.0,   "unit": "%"},
    "F01.04": {"addr": 0x0104, "name": "Freq Source Channel B",   "dec": 0, "min": 0,    "max": 11,      "unit": ""},
    "F01.05": {"addr": 0x0105, "name": "Channel B Gain",          "dec": 1, "min": 0.0,  "max": 500.0,   "unit": "%"},
    "F01.06": {"addr": 0x0106, "name": "Channel B Reference",     "dec": 0, "min": 0,    "max": 1,       "unit": ""},
    "F01.07": {"addr": 0x0107, "name": "Freq Reference Source",   "dec": 0, "min": 0,    "max": 5,       "unit": ""},
    "F01.08": {"addr": 0x0108, "name": "Run Command Bundle",      "dec": 0, "min": 0,    "max": 65535,   "unit": ""},
    "F01.09": {"addr": 0x0109, "name": "Keyboard Setpoint Freq",  "dec": 2, "min": 0.0,  "max": 600.0,   "unit": "Hz"},
    "F01.10": {"addr": 0x010A, "name": "Maximum Frequency",       "dec": 2, "min": 0.0,  "max": 600.0,   "unit": "Hz"},
    "F01.12": {"addr": 0x010C, "name": "Upper Frequency Limit",   "dec": 2, "min": 0.0,  "max": 600.0,   "unit": "Hz"},
    "F01.13": {"addr": 0x010D, "name": "Lower Frequency Limit",   "dec": 2, "min": 0.0,  "max": 600.0,   "unit": "Hz"},
    "F01.14": {"addr": 0x010E, "name": "Freq Cmd Resolution",     "dec": 0, "min": 0,    "max": 1,       "unit": ""},
    "F01.20": {"addr": 0x0114, "name": "Accel/Decel Base Freq",   "dec": 0, "min": 0,    "max": 65535,   "unit": ""},
    "F01.21": {"addr": 0x0115, "name": "Accel Time Unit",         "dec": 0, "min": 0,    "max": 65535,   "unit": ""},
    "F01.22": {"addr": 0x0116, "name": "Acceleration Time 1",     "dec": 2, "min": 0.0,  "max": 650.0,   "unit": "s"},
    "F01.23": {"addr": 0x0117, "name": "Deceleration Time 1",     "dec": 2, "min": 0.0,  "max": 650.0,   "unit": "s"},
    "F01.24": {"addr": 0x0118, "name": "Acceleration Time 2",     "dec": 2, "min": 0.0,  "max": 650.0,   "unit": "s"},
    "F01.25": {"addr": 0x0119, "name": "Deceleration Time 2",     "dec": 2, "min": 0.0,  "max": 650.0,   "unit": "s"},
    "F01.26": {"addr": 0x011A, "name": "Acceleration Time 3",     "dec": 2, "min": 0.0,  "max": 650.0,   "unit": "s"},
    "F01.27": {"addr": 0x011B, "name": "Deceleration Time 3",     "dec": 2, "min": 0.0,  "max": 650.0,   "unit": "s"},
    "F01.28": {"addr": 0x011C, "name": "Acceleration Time 4",     "dec": 2, "min": 0.0,  "max": 650.0,   "unit": "s"},
    "F01.29": {"addr": 0x011D, "name": "Deceleration Time 4",     "dec": 2, "min": 0.0,  "max": 650.0,   "unit": "s"},
    "F01.30": {"addr": 0x011E, "name": "S-Curve Enable",          "dec": 0, "min": 0,    "max": 650,     "unit": ""},
    "F01.31": {"addr": 0x011F, "name": "S-Curve Accel Start",     "dec": 2, "min": 0.0,  "max": 650.0,   "unit": "s"},
    "F01.32": {"addr": 0x0120, "name": "S-Curve Accel End",       "dec": 2, "min": 0.0,  "max": 650.0,   "unit": "s"},
    "F01.33": {"addr": 0x0121, "name": "S-Curve Decel Start",     "dec": 2, "min": 0.0,  "max": 650.0,   "unit": "s"},
}

# F12.xx — RS485 / Modbus communication parameters
F12_REGS = {
    "F12.00": {"addr": 0x0C00, "name": "Master/Slave Select",       "dec": 0, "min": 0,    "max": 1,       "unit": ""},
    "F12.01": {"addr": 0x0C01, "name": "485 Node Address",          "dec": 0, "min": 1,    "max": 247,     "unit": ""},
    "F12.02": {"addr": 0x0C02, "name": "Baud Rate Selection",       "dec": 0, "min": 0,    "max": 6,       "unit": ""},
    "F12.03": {"addr": 0x0C03, "name": "Modbus Data Format",        "dec": 0, "min": 0,    "max": 5,       "unit": ""},
    "F12.04": {"addr": 0x0C04, "name": "Write Response Mode",       "dec": 0, "min": 0,    "max": 1,       "unit": ""},
    "F12.05": {"addr": 0x0C05, "name": "Response Delay",            "dec": 0, "min": 0,    "max": 500,     "unit": "ms"},
    "F12.06": {"addr": 0x0C06, "name": "Timeout Fault Time",        "dec": 1, "min": 0.1,  "max": 100.0,   "unit": "s"},
    "F12.07": {"addr": 0x0C07, "name": "Timeout Fault Action",      "dec": 0, "min": 0,    "max": 3,       "unit": ""},
    "F12.08": {"addr": 0x0C08, "name": "0x3000 Zero Offset",        "dec": 2, "min": -500.0,"max": 500.0,  "unit": "ms"},
    "F12.09": {"addr": 0x0C09, "name": "0x3000 Gain",               "dec": 1, "min": 0.0,  "max": 500.0,   "unit": "ms"},
    "F12.10": {"addr": 0x0C0A, "name": "Cyclic Tx Param Select",    "dec": 0, "min": 0,    "max": 65535,   "unit": ""},
    "F12.11": {"addr": 0x0C0B, "name": "Freq Setpoint Custom Addr", "dec": 0, "min": 0,    "max": 65535,   "unit": ""},
    "F12.12": {"addr": 0x0C0C, "name": "Cmd Given Custom Addr",     "dec": 0, "min": 0,    "max": 65535,   "unit": ""},
    "F12.13": {"addr": 0x0C0D, "name": "Forward Run Value",         "dec": 0, "min": 0,    "max": 65535,   "unit": ""},
    "F12.14": {"addr": 0x0C0E, "name": "Reverse Run Value",         "dec": 0, "min": 0,    "max": 65535,   "unit": ""},
    "F12.15": {"addr": 0x0C0F, "name": "Stop Command Value",        "dec": 0, "min": 0,    "max": 65535,   "unit": ""},
    "F12.16": {"addr": 0x0C10, "name": "Reset Command Value",       "dec": 0, "min": 0,    "max": 65535,   "unit": ""},
    "F12.19": {"addr": 0x0C13, "name": "Host Send Cmd Select",      "dec": 0, "min": 0,    "max": 65535,   "unit": ""},
}

# ==============================================================================
# --- F13.xx — PID CONTROLLER PARAMETERS ---
# ==============================================================================
F13_REGS = {
    "F13.00": {"addr": 0x0D00, "name": "PID Enable",                  "dec": 0, "min": 0,    "max": 1,       "unit": ""},
    "F13.01": {"addr": 0x0D01, "name": "PID Setpoint (Pressure)",     "dec": 2, "min": 0.0,  "max": 100.0,   "unit": "Bar"},
    "F13.02": {"addr": 0x0D02, "name": "PID Setpoint Source",         "dec": 0, "min": 0,    "max": 5,       "unit": ""},
    "F13.03": {"addr": 0x0D03, "name": "PID Feedback Source",         "dec": 0, "min": 0,    "max": 9,       "unit": ""},
    "F13.04": {"addr": 0x0D04, "name": "PID Feedback Filter",         "dec": 2, "min": 0.0,  "max": 100.0,   "unit": "s"},
    "F13.05": {"addr": 0x0D05, "name": "PID Action Direction",        "dec": 0, "min": 0,    "max": 1,       "unit": ""},
    "F13.06": {"addr": 0x0D06, "name": "Proportional Gain (Kp)",      "dec": 2, "min": 0.0,  "max": 100.0,   "unit": ""},
    "F13.07": {"addr": 0x0D07, "name": "Integral Time (Ti)",          "dec": 2, "min": 0.0,  "max": 100.0,   "unit": "s"},
    "F13.08": {"addr": 0x0D08, "name": "Derivative Time (Td)",        "dec": 2, "min": 0.0,  "max": 100.0,   "unit": "s"},
    "F13.09": {"addr": 0x0D09, "name": "PID Output Limit High",       "dec": 2, "min": 0.0,  "max": 100.0,   "unit": "%"},
    "F13.10": {"addr": 0x0D0A, "name": "PID Output Limit Low",        "dec": 2, "min": 0.0,  "max": 100.0,   "unit": "%"},
    "F13.11": {"addr": 0x0D0B, "name": "PID Deviation Limit",         "dec": 2, "min": 0.0,  "max": 100.0,   "unit": "%"},
    "F13.12": {"addr": 0x0D0C, "name": "PID Sleep Freq Threshold",    "dec": 2, "min": 0.0,  "max": 600.0,   "unit": "Hz"},
    "F13.13": {"addr": 0x0D0D, "name": "PID Sleep Delay Time",        "dec": 1, "min": 0.0,  "max": 3600.0,  "unit": "s"},
    "F13.14": {"addr": 0x0D0E, "name": "PID Wake-Up Threshold",       "dec": 2, "min": 0.0,  "max": 100.0,   "unit": "%"},
    "F13.15": {"addr": 0x0D0F, "name": "PID Wake-Up Detection Time",  "dec": 1, "min": 0.0,  "max": 3600.0,  "unit": "s"},
    "F13.16": {"addr": 0x0D10, "name": "PID Integral Separation",     "dec": 2, "min": 0.0,  "max": 100.0,   "unit": "%"},
    "F13.17": {"addr": 0x0D11, "name": "PID Feedback Loss Det. Time", "dec": 1, "min": 0.0,  "max": 3600.0,  "unit": "s"},
    "F13.18": {"addr": 0x0D12, "name": "PID Feedback Loss Low Limit", "dec": 2, "min": 0.0,  "max": 100.0,   "unit": "%"},
    "F13.19": {"addr": 0x0D13, "name": "PID Feedback Loss Hi Limit",  "dec": 2, "min": 0.0,  "max": 100.0,   "unit": "%"},
    "F13.20": {"addr": 0x0D14, "name": "PID Output Freq Gain",        "dec": 2, "min": 0.0,  "max": 200.0,   "unit": "%"},
    "F13.21": {"addr": 0x0D15, "name": "PID Error Deadband",          "dec": 2, "min": 0.0,  "max": 100.0,   "unit": "%"},
    "F13.22": {"addr": 0x0D16, "name": "PID Feedback Upper Limit",    "dec": 2, "min": 0.0,  "max": 100.0,   "unit": "%"},
    "F13.23": {"addr": 0x0D17, "name": "PID Feedback Lower Limit",    "dec": 2, "min": 0.0,  "max": 100.0,   "unit": "%"},
    "F13.24": {"addr": 0x0D18, "name": "PID Setpoint Ramp Time",      "dec": 1, "min": 0.0,  "max": 3600.0,  "unit": "s"},
    "F13.25": {"addr": 0x0D19, "name": "PID Kp2 (Switch Gain)",       "dec": 2, "min": 0.0,  "max": 100.0,   "unit": ""},
    "F13.26": {"addr": 0x0D1A, "name": "PID Ti2 (Switch Int. Time)",  "dec": 2, "min": 0.0,  "max": 100.0,   "unit": "s"},
    "F13.27": {"addr": 0x0D1B, "name": "PID Td2 (Switch Deriv. Time)","dec": 2, "min": 0.0,  "max": 100.0,   "unit": "s"},
    "F13.28": {"addr": 0x0D1C, "name": "PID Gain Switch Condition",   "dec": 0, "min": 0,    "max": 3,       "unit": ""},
    "F13.29": {"addr": 0x0D1D, "name": "PID Gain Switch Threshold",   "dec": 2, "min": 0.0,  "max": 100.0,   "unit": "%"},
    "F13.30": {"addr": 0x0D1E, "name": "Multi-pump Enable",           "dec": 0, "min": 0,    "max": 1,       "unit": ""},
    "F13.31": {"addr": 0x0D1F, "name": "Multi-pump Quantity",         "dec": 0, "min": 1,    "max": 8,       "unit": ""},
    "F13.32": {"addr": 0x0D20, "name": "Pump Add Freq Threshold",     "dec": 2, "min": 0.0,  "max": 600.0,   "unit": "Hz"},
    "F13.33": {"addr": 0x0D21, "name": "Pump Add Delay Time",         "dec": 1, "min": 0.0,  "max": 3600.0,  "unit": "s"},
    "F13.34": {"addr": 0x0D22, "name": "Pump Remove Freq Threshold",  "dec": 2, "min": 0.0,  "max": 600.0,   "unit": "Hz"},
    "F13.35": {"addr": 0x0D23, "name": "Pump Remove Delay Time",      "dec": 1, "min": 0.0,  "max": 3600.0,  "unit": "s"},
}

# ==============================================================================
# --- SERIAL CORE HELPERS ---
# ==============================================================================

def safe_read(register, decimals=0):
    """Thread-safe single register read (FC03). Updates telemetry counters."""
    global _tx_count, _rx_count, _crc_errors
    _tx_count += 1
    try:
        val = instrument.read_register(register, number_of_decimals=decimals, functioncode=3)
        _rx_count += 1
        return val
    except Exception as e:
        if "CRC" in str(e).upper():
            _crc_errors += 1
        raise


def safe_write(register, value, decimals=0):
    """
    Thread-safe register write.
    Try FC06 first, fall back to FC16.
    """
    global _tx_count, _rx_count, _crc_errors
    _tx_count += 1
    try:
        instrument.write_register(
            register, value,
            number_of_decimals=decimals,
            functioncode=6
        )
        _rx_count += 1
        print(f"[VFD] FC06 write OK → reg {hex(register)} = {value}")
    except Exception as e6:
        print(f"[VFD] FC06 failed ({e6}), trying FC16...")
        try:
            instrument.write_register(
                register, value,
                number_of_decimals=decimals,
                functioncode=16
            )
            _rx_count += 1
            print(f"[VFD] FC16 write OK → reg {hex(register)} = {value}")
        except Exception as e16:
            if "CRC" in str(e16).upper():
                _crc_errors += 1
            raise e16


def _rx_count_inc():
    global _rx_count, _tx_count
    _tx_count += 1
    _rx_count += 1


def _flush_buffers():
    """Clear serial RX/TX buffers if the port is open."""
    if instrument and instrument.serial.is_open:
        instrument.serial.reset_input_buffer()
        instrument.serial.reset_output_buffer()


def _ensure_open():
    """Re-open the serial port if it was closed, then flush."""
    if instrument and not instrument.serial.is_open:
        instrument.serial.open()
    _flush_buffers()


# Initialise on import
init_vfd()

# ==============================================================================
# --- C00.xx — RUNTIME MONITORING REGISTERS (read-only) ---
# ==============================================================================
C00_REGS = [
    {"code": "C00.00", "addr": 0x2100, "name": "Given frequency",                    "dec": 2,  "unit": "Hz"},
    {"code": "C00.01", "addr": 0x2101, "name": "Output frequency",                   "dec": 2,  "unit": "Hz"},
    {"code": "C00.02", "addr": 0x2102, "name": "Output current",                     "dec": 2,  "unit": "A"},
    {"code": "C00.03", "addr": 0x2103, "name": "Input voltage",                      "dec": 1,  "unit": "V"},
    {"code": "C00.04", "addr": 0x2104, "name": "Output voltage",                     "dec": 1,  "unit": "V"},
    {"code": "C00.05", "addr": 0x2105, "name": "Mechanical speed",                   "dec": 0,  "unit": "rpm"},
    {"code": "C00.06", "addr": 0x2106, "name": "Given torque",                       "dec": 1,  "unit": "%"},
    {"code": "C00.07", "addr": 0x2107, "name": "Output torque",                      "dec": 1,  "unit": "%"},
    {"code": "C00.08", "addr": 0x2108, "name": "PID given amount",                   "dec": 2,  "unit": "%"},
    {"code": "C00.09", "addr": 0x2109, "name": "PID feedback amount",                "dec": 2,  "unit": "%"},
    {"code": "C00.10", "addr": 0x210A, "name": "Output power",                       "dec": 1,  "unit": "%/kW"},
    {"code": "C00.11", "addr": 0x210B, "name": "Bus voltage",                        "dec": 1,  "unit": "V"},
    {"code": "C00.12", "addr": 0x210C, "name": "Module temperature 1",               "dec": 1,  "unit": "℃"},
    {"code": "C00.13", "addr": 0x210D, "name": "Module temperature 2",               "dec": 1,  "unit": "℃"},
    {"code": "C00.14", "addr": 0x210E, "name": "Input terminal X state",             "dec": 0,  "unit": "bits"},
    {"code": "C00.15", "addr": 0x210F, "name": "Output terminal Y state",            "dec": 0,  "unit": "bits"},
    {"code": "C00.16", "addr": 0x2110, "name": "Analog AI1 input",                   "dec": 3,  "unit": "V"},
    {"code": "C00.17", "addr": 0x2111, "name": "Analog AI2 input",                   "dec": 3,  "unit": "V"},
    {"code": "C00.18", "addr": 0x2112, "name": "Reserved",                           "dec": 3,  "unit": ""},
    {"code": "C00.19", "addr": 0x2113, "name": "Pulse PUL input",                    "dec": 3,  "unit": "kHz"},
    {"code": "C00.20", "addr": 0x2114, "name": "Analog output AO1",                  "dec": 2,  "unit": "V"},
    {"code": "C00.21", "addr": 0x2115, "name": "Analog output AO2",                  "dec": 2,  "unit": "V"},
    {"code": "C00.22", "addr": 0x2116, "name": "Counter count value",                "dec": 0,  "unit": ""},
    {"code": "C00.23", "addr": 0x2117, "name": "Running time (this power-on)",       "dec": 0,  "unit": "h"},
    {"code": "C00.24", "addr": 0x2118, "name": "Accumulated running time",           "dec": 0,  "unit": "h"},
    {"code": "C00.25", "addr": 0x2119, "name": "Inverter power level",               "dec": 1,  "unit": "kW"},
    {"code": "C00.26", "addr": 0x211A, "name": "Inverter rated voltage",             "dec": 0,  "unit": "V"},
    {"code": "C00.27", "addr": 0x211B, "name": "Inverter rated current",             "dec": 1,  "unit": "A"},
    {"code": "C00.28", "addr": 0x211C, "name": "Software version",                   "dec": 2,  "unit": ""},
    {"code": "C00.29", "addr": 0x211D, "name": "PG feedback frequency",              "dec": 2,  "unit": "Hz"},
    {"code": "C00.30", "addr": 0x211E, "name": "Timer",                              "dec": 0,  "unit": ""},
    {"code": "C00.31", "addr": 0x211F, "name": "PID output",                         "dec": 2,  "unit": ""},
    {"code": "C00.32", "addr": 0x2120, "name": "Software subversion",                "dec": 2,  "unit": ""},
    {"code": "C00.33", "addr": 0x2121, "name": "Encoder angle",                      "dec": 0,  "unit": "°"},
    {"code": "C00.34", "addr": 0x2122, "name": "Z pulse error",                      "dec": 0,  "unit": ""},
    {"code": "C00.35", "addr": 0x2123, "name": "Z pulse count",                      "dec": 0,  "unit": ""},
    {"code": "C00.36", "addr": 0x2124, "name": "Fault warning code",                 "dec": 0,  "unit": ""},
    {"code": "C00.37", "addr": 0x2125, "name": "Cumulative power (low)",             "dec": 0,  "unit": ""},
    {"code": "C00.38", "addr": 0x2126, "name": "Cumulative power (high)",            "dec": 0,  "unit": ""},
    {"code": "C00.39", "addr": 0x2127, "name": "Power factor angle",                 "dec": 1,  "unit": ""},
]

# ==============================================================================
# --- C01.xx — FAULT LOG REGISTERS (read-only) ---
# ==============================================================================
C01_REGS = [
    {"code": "C01.00", "addr": 0x2200, "name": "Fault type",                         "dec": 0,  "unit": ""},
    {"code": "C01.01", "addr": 0x2201, "name": "Fault diagnosis info",               "dec": 0,  "unit": ""},
    {"code": "C01.02", "addr": 0x2202, "name": "Fault running frequency",            "dec": 2,  "unit": "Hz"},
    {"code": "C01.03", "addr": 0x2203, "name": "Fault output voltage",               "dec": 1,  "unit": "V"},
    {"code": "C01.04", "addr": 0x2204, "name": "Fault output current",               "dec": 1,  "unit": "A"},
    {"code": "C01.05", "addr": 0x2205, "name": "Fault bus voltage",                  "dec": 1,  "unit": "V"},
    {"code": "C01.06", "addr": 0x2206, "name": "Fault module temperature",           "dec": 1,  "unit": "℃"},
    {"code": "C01.07", "addr": 0x2207, "name": "Faulty inverter status",             "dec": 0,  "unit": "bits"},
    {"code": "C01.08", "addr": 0x2208, "name": "Fault input terminal status",        "dec": 0,  "unit": "bits"},
    {"code": "C01.09", "addr": 0x2209, "name": "Fault output terminal status",       "dec": 0,  "unit": "bits"},
    {"code": "C01.10", "addr": 0x220A, "name": "Previous 1st fault type",            "dec": 0,  "unit": ""},
    {"code": "C01.11", "addr": 0x220B, "name": "Prev fault diagnosis info",          "dec": 0,  "unit": ""},
    {"code": "C01.12", "addr": 0x220C, "name": "Prev fault frequency",               "dec": 2,  "unit": "Hz"},
    {"code": "C01.13", "addr": 0x220D, "name": "Prev fault output voltage",          "dec": 1,  "unit": "V"},
    {"code": "C01.14", "addr": 0x220E, "name": "Prev fault output current",          "dec": 1,  "unit": "A"},
    {"code": "C01.15", "addr": 0x220F, "name": "Prev fault bus voltage",             "dec": 1,  "unit": "V"},
    {"code": "C01.16", "addr": 0x2210, "name": "Prev fault module temp",             "dec": 1,  "unit": "℃"},
    {"code": "C01.17", "addr": 0x2211, "name": "Prev fault inverter status",         "dec": 0,  "unit": "bits"},
    {"code": "C01.18", "addr": 0x2212, "name": "Prev fault input terminal",          "dec": 0,  "unit": "bits"},
    {"code": "C01.19", "addr": 0x2213, "name": "Prev fault output terminal",         "dec": 0,  "unit": "bits"},
    {"code": "C01.20", "addr": 0x2214, "name": "Previous 2nd fault type",            "dec": 0,  "unit": ""},
    {"code": "C01.21", "addr": 0x2215, "name": "2nd fault diagnosis info",           "dec": 0,  "unit": ""},
    {"code": "C01.22", "addr": 0x2216, "name": "Previous 3rd fault type",            "dec": 0,  "unit": ""},
    {"code": "C01.23", "addr": 0x2217, "name": "3rd fault diagnosis info",           "dec": 0,  "unit": ""},
]

# ==============================================================================
# --- FRONTEND PAGE ROUTE ---
# ==============================================================================

@vfd_blueprint.route('/vfd')
def vfd_page():
    return render_template('vfd-panel.html')

# ==============================================================================
# --- STATUS / TELEMETRY ---
# ==============================================================================

@vfd_blueprint.route('/api/vfd/status', methods=['GET'])
def get_status():
    if not SERIAL_AVAILABLE or instrument is None:
        return jsonify({
            "status": "OFFLINE",
            "output_frequency": 0.0,
            "output_current": 0.0,
            "analog_ai1": 0.0,
            "param_f0101": 0,
            "param_f0102": 0,
            "tx": _tx_count,
            "rx": _rx_count,
            "crc_errors": _crc_errors,
            "error": "Hardware engine unavailable"
        })

    with serial_lock:
        try:
            _ensure_open()

            out_freq  = safe_read(REG_OUTPUT_FREQ, decimals=2)
            time.sleep(0.015)
            out_curr  = safe_read(REG_OUTPUT_CURR, decimals=2)
            time.sleep(0.015)
            f0101     = safe_read(F01_REGS["F01.01"]["addr"])
            time.sleep(0.015)
            f0102     = safe_read(F01_REGS["F01.02"]["addr"])
            time.sleep(0.015)
            analog_ai1 = safe_read(REG_IN_AN, decimals=3)
            time.sleep(0.015)

            return jsonify({
                "status": "ONLINE",
                "output_frequency": out_freq,
                "output_current": out_curr,
                "analog_ai1": analog_ai1,
                "param_f0101": f0101,
                "param_f0102": f0102,
                "tx": _tx_count,
                "rx": _rx_count,
                "crc_errors": _crc_errors,
                "error": None
            })
        except Exception as e:
            return jsonify({
                "status": "COMM_ERROR",
                "output_frequency": 0.0,
                "output_current": 0.0,
                "analog_ai1": 0.0,
                "param_f0101": 0,
                "param_f0102": 0,
                "tx": _tx_count,
                "rx": _rx_count,
                "crc_errors": _crc_errors,
                "error": str(e)
            })

# ==============================================================================
# --- WRITE (UNIFIED) ---
# ==============================================================================
# NOTE: renamed from '/api/write' to '/api/vfd-write'. The original path
# collided with routes/telemetry.py's '/api/write' (PLC bit write) — both
# were registered on the same Flask app with no url_prefix, which either
# crashes Flask at startup (duplicate endpoint) or silently shadows one
# handler with the other. This module renames its own colliding routes
# rather than changing the blueprint registration in app.py, since VFD is
# meant to be a self-contained module independent of the HMI/alarm side.
# If anything (vfd_comms.js, external tooling) still calls '/api/write',
# update it to '/api/vfd-write'.

@vfd_blueprint.route('/api/vfd-write', methods=['POST'])
def write_hardware_bus():
    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({"status": "ERROR", "message": "Invalid or missing JSON body."}), 400

    raw_reg = payload.get('register') or payload.get('offset', 0)
    try:
        if isinstance(raw_reg, str) and raw_reg.lower().startswith('0x'):
            target_reg = int(raw_reg, 16)
        else:
            target_reg = int(raw_reg)
    except (ValueError, TypeError):
        return jsonify({"status": "ERROR", "message": f"Cannot parse register: {raw_reg!r}"}), 400

    decimals = int(payload.get('decimals', 0))
    try:
        raw_val = payload.get('value', 0)
        value_to_write = float(raw_val) if decimals > 0 else int(float(raw_val))
    except (ValueError, TypeError):
        return jsonify({"status": "ERROR", "message": "Cannot parse value."}), 400

    req_port  = payload.get('port', '').strip() or None
    req_slave = payload.get('slave_id')
    req_baud  = payload.get('baud_rate')

    needs_reinit = (
        (req_port  and req_port  != vfd_settings["port"])                or
        (req_slave and int(req_slave) != vfd_settings["slave_address"])  or
        (req_baud  and int(req_baud)  != vfd_settings["baud_rate"])
    )
    if needs_reinit:
        init_vfd(port=req_port, baud=req_baud, slave_id=req_slave)

    if instrument is None:
        return jsonify({
            "status": "OFFLINE",
            "message": "No active serial connection. Use /api/vfd-connect first."
        }), 503

    with serial_lock:
        try:
            _ensure_open()
            safe_write(target_reg, value_to_write, decimals=decimals)
            return jsonify({
                "status": "SUCCESS",
                "message": f"Wrote {value_to_write} → register {hex(target_reg)}"
            })
        except Exception as err:
            return jsonify({
                "status": "COMM_ERROR",
                "message": f"Write failed: {str(err)}"
            }), 500

# ==============================================================================
# --- CONTROL COMMANDS ---
# ==============================================================================

@vfd_blueprint.route('/api/control', methods=['POST'])
def api_control():
    CMD_CODES = {"FORWARD": 1, "RUN": 1, "REVERSE": 2, "STOP": 5, "RESET": 7}

    if not SERIAL_AVAILABLE:
        return jsonify({"status": "OFFLINE", "message": "Serial library not installed."}), 503

    if instrument is None:
        return jsonify({
            "status": "OFFLINE",
            "message": "No active serial connection. Use /api/vfd-connect first."
        }), 503

    body     = request.get_json(silent=True) or {}
    cmd_name = str(body.get("command", "")).upper()
    cmd_code = body.get("code")

    if cmd_code is not None:
        code = int(cmd_code)
    elif cmd_name in CMD_CODES:
        code = CMD_CODES[cmd_name]
    else:
        return jsonify({
            "status": "ERROR",
            "message": f"Unknown command '{cmd_name}'. Use FORWARD/REVERSE/STOP/RESET or code 1/2/5/7."
        }), 400

    with serial_lock:
        try:
            _ensure_open()
            target_reg = 0x2001
            raw_value  = int(code) & 0xFFFF
            print(f"Sending Modbus Control Word: {raw_value} to register {hex(target_reg)}")
            try:
                instrument.write_register(target_reg, raw_value, number_of_decimals=0, functioncode=6)
            except Exception as e1:
                print(f"FC06 failed ({e1}), trying FC16 multi-register...")
                instrument.write_registers(target_reg, [raw_value])
            _rx_count_inc()
            return jsonify({
                "status": "SUCCESS",
                "message": f"Control command sent (0x2001 = {raw_value})"
            })
        except Exception as e:
            return jsonify({
                "status": "COMM_ERROR",
                "message": f"Control write failed: {str(e)}"
            }), 500

# ==============================================================================
# --- C00 / C01 MONITOR ENDPOINT ---
# ==============================================================================

@vfd_blueprint.route('/api/monitor', methods=['GET'])
def api_monitor():
    if not SERIAL_AVAILABLE or instrument is None:
        return jsonify({"success": False, "msg": "Device not connected.", "c00": {}, "c01": {}})

    group = request.args.get("group", "all").lower()

    c00_results = {}
    c01_results = {}

    with serial_lock:
        try:
            _ensure_open()

            if group in ("c00", "all"):
                for reg in C00_REGS:
                    try:
                        _flush_buffers()
                        val = safe_read(reg["addr"], decimals=reg["dec"])
                        time.sleep(0.018)
                        c00_results[reg["code"]] = {
                            "name":  reg["name"],
                            "value": val,
                            "unit":  reg["unit"],
                            "addr":  hex(reg["addr"]),
                            "error": None
                        }
                    except Exception as e:
                        c00_results[reg["code"]] = {
                            "name":  reg["name"],
                            "value": None,
                            "unit":  reg["unit"],
                            "addr":  hex(reg["addr"]),
                            "error": str(e)
                        }

            if group in ("c01", "all"):
                for reg in C01_REGS:
                    try:
                        _flush_buffers()
                        val = safe_read(reg["addr"], decimals=reg["dec"])
                        time.sleep(0.018)
                        c01_results[reg["code"]] = {
                            "name":  reg["name"],
                            "value": val,
                            "unit":  reg["unit"],
                            "addr":  hex(reg["addr"]),
                            "error": None
                        }
                    except Exception as e:
                        c01_results[reg["code"]] = {
                            "name":  reg["name"],
                            "value": None,
                            "unit":  reg["unit"],
                            "addr":  hex(reg["addr"]),
                            "error": str(e)
                        }

            return jsonify({"success": True, "c00": c00_results, "c01": c01_results})

        except Exception as e:
            return jsonify({
                "success": False,
                "msg": str(e),
                "c00": c00_results,
                "c01": c01_results
            })


@vfd_blueprint.route('/api/raw', methods=['POST'])
def api_raw_transfer():
    """FC03 read or FC06/16 write at arbitrary register addresses."""
    if not SERIAL_AVAILABLE or instrument is None:
        return jsonify({"success": False, "msg": "Device not connected."})

    body     = request.get_json(silent=True) or {}
    raw_reg  = body.get("register", "0x0000")
    fc_str   = str(body.get("functionCode", "03"))
    raw_data = body.get("data", "0")

    try:
        reg = int(str(raw_reg), 16) if str(raw_reg).lower().startswith('0x') else int(raw_reg)
        fc  = int(fc_str)
        val = int(str(raw_data), 16) if str(raw_data).lower().startswith('0x') else int(raw_data)
    except ValueError as e:
        return jsonify({"success": False, "msg": f"Parse error: {e}"})

    with serial_lock:
        try:
            _ensure_open()
            if fc == 3:
                result = safe_read(reg)
                return jsonify({"success": True,
                                "msg": f"Read reg {hex(reg)} = {result}",
                                "value": result})
            elif fc in (6, 16):
                safe_write(reg, val)
                return jsonify({"success": True, "msg": f"Wrote {val} → {hex(reg)}"})
            else:
                return jsonify({"success": False, "msg": f"Unsupported function code: {fc}"})
        except Exception as e:
            return jsonify({"success": False, "msg": str(e)})

# ==============================================================================
# --- PARAMETER PANEL: READ ALL F01 / F12 / F13 ---
# ==============================================================================

@vfd_blueprint.route('/api/read-params', methods=['GET'])
def api_read_params():
    if not SERIAL_AVAILABLE or instrument is None:
        return jsonify({"success": False, "msg": "Device not connected.", "params": {}})

    group   = request.args.get("group", "all").lower()
    targets = {}
    if group in ("f01", "all"):
        targets.update(F01_REGS)
    if group in ("f12", "all"):
        targets.update(F12_REGS)
    if group in ("f13", "all"):
        targets.update(F13_REGS)

    results = {}
    with serial_lock:
        try:
            _ensure_open()
            for key, meta in targets.items():
                try:
                    _flush_buffers()
                    val = safe_read(meta["addr"], decimals=meta["dec"])
                    time.sleep(0.02)
                    results[key] = {
                        "value": val,
                        "name":  meta["name"],
                        "unit":  meta["unit"],
                        "error": None
                    }
                except Exception as e:
                    results[key] = {
                        "value": None,
                        "name":  meta["name"],
                        "unit":  meta["unit"],
                        "error": str(e)
                    }
            return jsonify({"success": True, "params": results})
        except Exception as e:
            return jsonify({"success": False, "msg": str(e), "params": results})


@vfd_blueprint.route('/api/write-param', methods=['POST'])
def api_write_param():
    if not SERIAL_AVAILABLE:
        return jsonify({"success": False, "msg": "minimalmodbus not installed."})

    body  = request.get_json(silent=True) or {}
    key   = body.get("key", "").upper().replace("_", ".")
    raw_v = body.get("value")

    all_regs = {**F01_REGS, **F12_REGS, **F13_REGS}
    meta = all_regs.get(key)
    if not meta:
        return jsonify({"success": False, "msg": f"Unknown parameter key: {key}"})

    try:
        value = float(raw_v) if meta["dec"] > 0 else int(float(raw_v))
    except (TypeError, ValueError):
        return jsonify({"success": False, "msg": "Invalid value."})

    if instrument is None:
        init_vfd()

    if instrument is None:
        return jsonify({"success": False, "msg": "No serial connection available."})

    with serial_lock:
        try:
            _ensure_open()
            safe_write(meta["addr"], value, decimals=meta["dec"])
            return jsonify({
                "success": True,
                "msg": f"Wrote {key} ({meta['name']}) = {value} {meta['unit']}"
            })
        except Exception as e:
            return jsonify({"success": False, "msg": str(e)})

# ==============================================================================
# --- CONNECTION, SETTINGS & SCANNING ---
# ==============================================================================
# NOTE: renamed from '/api/connect' to '/api/vfd-connect'. The original
# path collided with routes/telemetry.py's '/api/connect' (S7/PLC
# connect, takes {"ip": ...}) — same Flask app, same path, no
# url_prefix. See the note above '/api/vfd-write' for the full reasoning.

@vfd_blueprint.route('/api/vfd-connect', methods=['POST'])
def api_connect():
    if not SERIAL_AVAILABLE:
        return jsonify({"success": False, "active": False, "msg": "Serial library missing."})

    data = request.get_json(silent=True) or request.values
    port = data.get("port")    or data.get("com_port")
    baud = data.get("baud_rate") or data.get("baud")
    addr = data.get("slave_address") or data.get("address")

    init_vfd(port=port, baud=baud, slave_id=addr)

    if instrument is None:
        return jsonify({"success": False, "active": False, "msg": "No serial handle bound."})

    with serial_lock:
        try:
            _ensure_open()
            check = safe_read(F01_REGS["F01.01"]["addr"])
            return jsonify({
                "success": True,
                "active": True,
                "msg": f"Link active! F01.01 = {check}"
            })
        except Exception as e:
            return jsonify({
                "success": False,
                "active": False,
                "msg": f"Handshake failed: {str(e)}"
            })


@vfd_blueprint.route('/api/update-settings', methods=['POST'])
def api_update_settings():
    data = request.get_json(silent=True) or request.values
    try:
        port = data.get("port")
        baud = data.get("baud_rate") or data.get("baud")
        addr = data.get("slave_address") or data.get("address")
        init_vfd(port=port, baud=baud, slave_id=addr)
        return jsonify({
            "success": True,
            "msg": f"Settings updated: {vfd_settings['port']} "
                   f"@ {vfd_settings['baud_rate']} "
                   f"node {vfd_settings['slave_address']}"
        })
    except Exception as e:
        return jsonify({"success": False, "msg": f"Config exception: {str(e)}"})


@vfd_blueprint.route('/api/read', methods=['GET'])
def api_read_register():
    """Single register debug fetch via ?offset=0x2201"""
    if not SERIAL_AVAILABLE or instrument is None:
        return jsonify({"success": False, "msg": "Device not connected."})

    raw_offset = request.args.get('offset')
    if not raw_offset:
        return jsonify({"success": False, "msg": "Missing 'offset' param."})

    try:
        offset = int(str(raw_offset), 16) if str(raw_offset).lower().startswith('0x') else int(raw_offset)
        with serial_lock:
            _ensure_open()
            val = safe_read(offset)
        return jsonify({"success": True, "value": val})
    except Exception as e:
        return jsonify({"success": False, "msg": str(e)})


@vfd_blueprint.route('/api/scan-hardware', methods=['POST'])
def api_scan_hardware():
    try:
        ports = [p.device for p in serial.tools.list_ports.comports()]
        return jsonify({"success": True, "ports": ports, "active": len(ports) > 0})
    except Exception as e:
        return jsonify({"success": False, "ports": [], "active": False, "msg": str(e)})


@vfd_blueprint.route('/api/auto-link', methods=['POST'])
def api_auto_link():
    try:
        ports = [p.device for p in serial.tools.list_ports.comports()]
        if ports:
            init_vfd(port=ports[0])
            return jsonify({
                "success": True,
                "port": ports[0],
                "msg": f"Auto-linked to {ports[0]}"
            })
        return jsonify({"success": False, "msg": "No COM ports found."})
    except Exception as e:
        return jsonify({"success": False, "msg": str(e)})