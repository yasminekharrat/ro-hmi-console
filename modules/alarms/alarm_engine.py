"""
modules/alarms/alarm_engine.py
══════════════════════════════════════════════════════════════════════════════
Background alarm engine — runs in a daemon thread, independently of any
browser tab or HTTP request.

Responsibilities:
  1. Poll PLC telemetry via telemetry_reader every POLL_INTERVAL_SECONDS
  2. Evaluate each rule in alarm_config.ALARM_RULES
  3. Edge-trigger: only dispatch on OFF→ON transition (never re-sends)
  4. Dispatch WhatsApp messages (text only) via Selenium / WhatsApp Web
  5. Maintain in-memory state for /api/alarms/status and /api/alarms/log
══════════════════════════════════════════════════════════════════════════════
"""

import time
import threading
import traceback
import requests
import os, glob
import urllib.parse
from datetime import datetime

from modules.alarms.alarm_config import (
    ALARM_RULES,
    WHATSAPP_NUMBERS,
    POLL_INTERVAL_SECONDS,
    SEVERITY_COLORS,
)

# ── STATE ─────────────────────────────────────────────────────────────────────

active_alarms: dict = {r["id"]: False for r in ALARM_RULES}
_unevaluable_counts: dict = {r["id"]: 0 for r in ALARM_RULES}
_UNEVALUABLE_WARN_THRESHOLD = 10

recent_log: list = []
last_evaluated: dict = {r["id"]: None for r in ALARM_RULES}

_log_lock = threading.Lock()
_state_lock = threading.Lock()

_wa_driver = None
_wa_ready = False
_wa_lock = threading.Lock()

_engine_thread = None
_engine_running = False

# Fallback selectors for resiliency against WhatsApp DOM mutations
COMPOSE_BOX_SELECTORS = [
    'div[data-testid="conversation-compose-box-input"]',
    'div[contenteditable="true"]',
    '#main footer role="textbox"',
]

# ── LOGGING ──────────────────────────────────────────────────────────────────

def _push_log(rule_id: str, label: str, severity: str, value, status: str, msg: str = ""):
    """Append one event to recent_log. Thread-safe. Caps at 200 entries."""
    entry = {
        "time": datetime.now().strftime("%H:%M:%S"),
        "date": datetime.now().strftime("%Y-%m-%d"),
        "rule_id": rule_id,
        "label": label,
        "severity": severity,
        "value": value,
        "status": status,  # "ACTIVE" | "RESOLVED" | "DISPATCHED" | "DISPATCH_FAIL" | "TEST"
        "msg": msg,
        "colors": SEVERITY_COLORS.get(severity, SEVERITY_COLORS.get("INFO", {})),
    }
    with _log_lock:
        recent_log.insert(0, entry)
        del recent_log[200:]


# ── ALARM EVALUATION ─────────────────────────────────────────────────────────

def evaluate_condition(rule: dict, value) -> bool | None:
    """
    Returns:
      True  — condition is met (alarm active)
      False — condition is clear
      None  — value unreadable / None (hold previous state)
    """
    if value is None:
        return None

    cond = rule["condition"]
    thresh = rule.get("threshold")

    try:
        if cond == "bool_true":
            return bool(value) is True
        if cond == "bool_false":
            return bool(value) is False
        v = float(value)
        t = float(thresh)
        if cond == "gt":   return v >  t
        if cond == "gte":  return v >= t
        if cond == "lt":   return v <  t
        if cond == "lte":  return v <= t
        if cond == "eq":   return v == t
    except (TypeError, ValueError):
        return None

    return None


def evaluate_all(telemetry: dict):
    """
    Called by the poll loop with a full telemetry snapshot.
    Detects OFF→ON and ON→OFF transitions per rule.
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for rule in ALARM_RULES:
        rid = rule["id"]
        tag = rule["tag"]
        value = telemetry.get(tag)

        result = evaluate_condition(rule, value)

        if result is None:
            _unevaluable_counts[rid] = _unevaluable_counts.get(rid, 0) + 1
            n = _unevaluable_counts[rid]
            if n == _UNEVALUABLE_WARN_THRESHOLD:
                _push_log(
                    rid, rule["label"], "INFO", None, "EVAL_FAIL",
                    f"Tag '{tag}' unreadable for {n} polls. Check tag name or PLC."
                )
            continue

        _unevaluable_counts[rid] = 0
        last_evaluated[rid] = now_str

        with _state_lock:
            was_active = active_alarms.get(rid, False)

        if result and not was_active:
            with _state_lock:
                active_alarms[rid] = True

            _push_log(rid, rule["label"], rule["severity"], value, "ACTIVE")

            if rule.get("whatsapp"):
                msg_body = _format_message(rule, value, now_str)
                _dispatch_whatsapp(rid, rule["label"], rule["severity"], value, msg_body)

        elif not result and was_active:
            with _state_lock:
                active_alarms[rid] = False
            _push_log(rid, rule["label"], rule["severity"], value, "RESOLVED")


def _format_message(rule: dict, value, timestamp: str) -> str:
    thresh = rule.get("threshold", "N/A")
    try:
        return rule["message"].format(
            value=float(value) if value is not None else 0,
            threshold=thresh,
            time=timestamp,
        )
    except (KeyError, ValueError):
        return rule["message"]


# ── WHATSAPP DISPATCH ─────────────────────────────────────────────────────────

def _dispatch_whatsapp(rule_id: str, label: str, severity: str, value, message: str):
    """Fire WhatsApp dispatch in a separate daemon thread to avoid blocking the poll loop."""
    t = threading.Thread(
        target=_send_whatsapp_to_all,
        args=(rule_id, label, severity, value, message),
        daemon=True,
        name=f"wa-dispatch-{rule_id}",
    )
    t.start()


def _send_whatsapp_to_all(rule_id: str, label: str, severity: str, value, message: str):
    """
    Sends WhatsApp message to every number in WHATSAPP_NUMBERS.
    Requires the WhatsApp Web session to be active (_wa_ready=True).
    """
    if not _wa_ready or _wa_driver is None:
        _push_log(rule_id, label, severity, value, "DISPATCH_FAIL",
                  "WhatsApp session not ready — QR not yet scanned.")
        return

    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    encoded = urllib.parse.quote(message)

    with _wa_lock:
        for number in WHATSAPP_NUMBERS:
            try:
                # 1. Open the deep-link with URL payload parameters
                _wa_driver.get(f"https://web.whatsapp.com/send?phone={number}&text={encoded}")
                
                # 2. Strict 6-second sleep interval from original working code to let React parse layout
                time.sleep(6)
                
                # 3. Dynamic multi-selector processing block to target the active editable wrapper
                msg_box = None
                last_err = None
                for selector in COMPOSE_BOX_SELECTORS:
                    try:
                        wait = WebDriverWait(_wa_driver, 15)
                        msg_box = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, selector)))
                        break
                    except Exception as e:
                        last_err = e
                        continue
                
                if not msg_box:
                    raise RuntimeError("Unable to locate conversation compose box canvas elements") from last_err

                # 4. Explicit element interaction to execute input focus context and commit dispatch
                msg_box.click()
                time.sleep(0.5)
                msg_box.send_keys(Keys.ENTER)
                
                # 5. Buffer time for local network loop stack to process and sync outbound buffer
                time.sleep(3) 
                
                _push_log(rule_id, label, severity, value, "DISPATCHED", f"WhatsApp sent → {number}")
            except Exception as e:
                _push_log(rule_id, label, severity, value, "DISPATCH_FAIL",
                          f"Send failed → {number}: {str(e)[:120]}")
            
            time.sleep(2)


# ── WHATSAPP SESSION INIT ─────────────────────────────────────────────────────

lock_pattern = os.path.join(os.path.expanduser("~"), ".wdm", ".wdm-lock-*")
for lock_file in glob.glob(lock_pattern):
    try:
        os.remove(lock_file)
        print(f"[ALARM] Removed stale wdm lock: {lock_file}")
    except Exception:
        pass


def init_whatsapp_session(session_path: str | None = None):
    """Launch Chrome + WhatsApp Web and block until authentication check passes."""
    global _wa_driver, _wa_ready

    import os, tempfile
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    try:
        from webdriver_manager.chrome import ChromeDriverManager
        driver_path = ChromeDriverManager().install()
    except ImportError:
        print("[ALARM] webdriver_manager not installed — WhatsApp dispatch disabled.")
        return

    if session_path is None:
        session_path = os.path.join(tempfile.gettempdir(), "thermeco_wa_session")
    os.makedirs(session_path, exist_ok=True)

    opts = webdriver.ChromeOptions()
    opts.add_argument(f"--user-data-dir={session_path}")
    opts.add_argument("--profile-directory=Default")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_experimental_option("excludeSwitches", ["enable-logging"])

    try:
        _wa_driver = webdriver.Chrome(service=Service(driver_path), options=opts)
        _wa_driver.get("https://web.whatsapp.com")
        print("[ALARM] WhatsApp Web opened — scan QR code in Chrome window (5 min timeout).")

        WebDriverWait(_wa_driver, 300).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'div[data-testid="chat-list"]'))
        )
        _wa_ready = True
        print("[ALARM] WhatsApp Web session ready ✓")
        _push_log("__system__", "WhatsApp Session", "INFO", None, "DISPATCHED",
                  "WhatsApp Web session authenticated successfully.")
    except Exception as e:
        print(f"[ALARM] WhatsApp init failed: {e}")
        _wa_ready = False


# ── POLL LOOP ─────────────────────────────────────────────────────────────────

def _poll_loop():
    """Background engine thread processing telemetry arrays via REST mock endpoints."""
    global _engine_running
    print(f"[ALARM] Poll engine started. Interval: {POLL_INTERVAL_SECONDS}s.")

    while _engine_running:
        try:
            try:
                r = requests.get("http://127.0.0.1:5000/api/alarms/mock-data", timeout=2)
                telemetry = r.json() if r.ok else {}
            except Exception:
                telemetry = {}

            if telemetry:
                evaluate_all(telemetry)

        except Exception:
            traceback.print_exc()

        time.sleep(POLL_INTERVAL_SECONDS)

    print("[ALARM] Poll engine stopped.")


# ── PUBLIC API ────────────────────────────────────────────────────────────────

def start_engine():
    """Start the background poll thread. Safe to call multiple times."""
    global _engine_thread, _engine_running
    if _engine_running:
        return
    _engine_running = True
    _engine_thread = threading.Thread(
        target=_poll_loop,
        daemon=True,
        name="alarm-engine",
    )
    _engine_thread.start()
    print("[ALARM] Engine thread started.")


def stop_engine():
    """Request graceful stop."""
    global _engine_running
    _engine_running = False
    print("[ALARM] Engine stop requested.")


def get_status() -> dict:
    """Return a snapshot of all rule states."""
    with _state_lock:
        states = dict(active_alarms)

    result = []
    for rule in ALARM_RULES:
        rid = rule["id"]
        result.append({
            "id": rid,
            "label": rule["label"],
            "group": rule["group"],
            "severity": rule["severity"],
            "icon": rule.get("icon", "🚨"),
            "unit": rule.get("unit", ""),
            "active": states.get(rid, False),
            "threshold": rule.get("threshold"),
            "whatsapp": rule.get("whatsapp", False),
            "last_evaluated": last_evaluated.get(rid),
            "colors": SEVERITY_COLORS.get(rule["severity"], {}),
            "unevaluable": _unevaluable_counts.get(rid, 0) >= _UNEVALUABLE_WARN_THRESHOLD,
        })
    return {"rules": result, "wa_ready": _wa_ready}


def trigger_test(rule_id: str) -> dict:
    """Manually fire a test alarm dispatch without needing real PLC data."""
    rule = next((r for r in ALARM_RULES if r["id"] == rule_id), None)
    if not rule:
        return {"ok": False, "msg": f"Unknown rule id: {rule_id}"}

    test_value = rule.get("threshold", 0) or 0
    if rule["condition"] in ("bool_true", "bool_false"):
        test_value = True

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    msg_body = _format_message(rule, test_value, now_str)
    msg_body = f"[TEST DISPATCH]\n{msg_body}"

    _push_log(rule_id, rule["label"], rule["severity"], test_value, "TEST",
              "Manual test trigger from HMI panel.")

    if rule.get("whatsapp"):
        _dispatch_whatsapp(rule_id, rule["label"], rule["severity"], test_value, msg_body)
        return {"ok": True, "msg": f"Test dispatch queued for '{rule['label']}' → WhatsApp"}
    else:
        return {"ok": True, "msg": f"Test logged for '{rule['label']}' (whatsapp=False, log only)"}


def get_log(limit: int = 50) -> list:
    """Return the most recent log entries."""
    with _log_lock:
        return recent_log[:limit]


def get_config() -> list:
    """Return the full rule config without message templates."""
    return [
        {k: v for k, v in r.items() if k != "message"}
        for r in ALARM_RULES
    ]