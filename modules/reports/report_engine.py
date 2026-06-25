# modules/reports/report_engine.py
# ---------------------------------------------------------------------------
# Background engine that schedules and sends daily / weekly Excel bilans via
# WhatsApp, sharing the Selenium session already owned by alarm_engine.
#
# Integration (app.py):
#   from modules.reports.report_engine import ReportEngine
#   report_engine = ReportEngine()
#   report_engine.start()
#
# Manual triggers:
#   POST /api/reports/trigger-daily
#   POST /api/reports/trigger-weekly
# ---------------------------------------------------------------------------

import os
import threading
import time
import datetime
import logging

from config.report_config import DAILY_HOUR, DAILY_MINUTE, WEEKLY_DAY
from modules.alarms.alarm_config import WHATSAPP_NUMBERS
from modules.reports.report_builder import build_report

log = logging.getLogger(__name__)

REPORT_OUTPUT_DIR = os.environ.get(
    "REPORT_OUTPUT_DIR", os.path.join(os.getcwd(), "reports_output")
)

# CSS selectors tried in order — extend this list when WA Web updates its DOM
ATTACH_BTN_SELECTORS = [
    '[data-testid="attach-menu-plus"]',
    '[data-testid="clip"]',
    '[data-icon="attach-menu-plus"]',
    '[data-icon="clip"]',
    'button[title="Joindre"]',
    'button[title="Attach"]',
    'div[title="Joindre"]',
    'div[title="Attach"]',
    '[aria-label="Joindre"]',
    '[aria-label="Attach"]',
    'span[data-icon="attach"]',
]

SEND_BTN_SELECTORS = [
    '[data-testid="send"]',
    'span[data-icon="send"]',
    'span[data-icon="send-light"]',
    'button[aria-label="Envoyer"]',
    'button[aria-label="Send"]',
    '[data-testid="media-send-button"]',
    '[data-testid="compose-btn-send"]',
]


COMPOSE_BOX_SELECTORS = [
    'div[data-testid="conversation-compose-box-input"]',
    'div[contenteditable="true"][data-tab]',
    'div[contenteditable="true"]',
]

# JS snippet that walks every known icon name and returns the closest
# button/div ancestor — survives WhatsApp Web DOM reshuffles
_JS_FIND_ATTACH = """
const icons = ['attach-menu-plus', 'clip', 'attach'];
for (const name of icons) {
    const el = document.querySelector('[data-icon="' + name + '"]');
    if (el) {
        const btn = el.closest('button') || el.closest('[role="button"]') || el;
        if (btn) return btn;
    }
}
// aria-label fallback
for (const lbl of ['Joindre', 'Attach', 'Attach file']) {
    const el = document.querySelector('[aria-label="' + lbl + '"]');
    if (el) return el;
}
return null;
"""


class ReportEngine:
    def __init__(self):
        self._thread = None
        self._stop   = threading.Event()

        self.last_daily_run:  datetime.date | None = None
        self.last_weekly_run: datetime.date | None = None
        self.last_status: dict = {"status": "idle", "message": "Moteur démarré."}

        os.makedirs(REPORT_OUTPUT_DIR, exist_ok=True)

    # ── Public API ────────────────────────────────────────────────────────

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name="ReportEngine", daemon=True
        )
        self._thread.start()
        log.info("[Reports] Engine started.")

    def stop(self):
        self._stop.set()

    def trigger_daily(self) -> dict:
        return self._run_report("daily")

    def trigger_weekly(self) -> dict:
        return self._run_report("weekly")

    def status(self) -> dict:
        return {
            **self.last_status,
            "last_daily_run":  str(self.last_daily_run) if self.last_daily_run else None,
            "last_weekly_run": str(self.last_weekly_run) if self.last_weekly_run else None,
            "next_daily":      self._next_run_str("daily"),
            "next_weekly":     self._next_run_str("weekly"),
            "recipients":      WHATSAPP_NUMBERS,
        }

    # ── Internal loop ─────────────────────────────────────────────────────

    def _loop(self):
        while not self._stop.is_set():
            now = datetime.datetime.now()

            if (now.hour == DAILY_HOUR and now.minute == DAILY_MINUTE
                    and self.last_daily_run != now.date()):
                self._run_report("daily")

            if (now.weekday() == WEEKLY_DAY
                    and now.hour == DAILY_HOUR and now.minute == DAILY_MINUTE
                    and self.last_weekly_run != now.date()):
                self._run_report("weekly")

            sleep_secs = 60 - now.second
            self._stop.wait(sleep_secs)

    # ── Report execution ──────────────────────────────────────────────────

    def _run_report(self, period: str) -> dict:
        now   = datetime.datetime.now()
        today = now.date()

        if period == "daily":
            yesterday = today - datetime.timedelta(days=1)
            since = datetime.datetime.combine(yesterday, datetime.time.min).timestamp()
            until = datetime.datetime.combine(yesterday, datetime.time.max).timestamp()
        else:
            last_monday = today - datetime.timedelta(days=today.weekday() + 7)
            last_sunday = last_monday + datetime.timedelta(days=6)
            since = datetime.datetime.combine(last_monday, datetime.time.min).timestamp()
            until = datetime.datetime.combine(last_sunday, datetime.time.max).timestamp()

        try:
            log.info(f"[Reports] Building {period} report …")
            path = build_report(period, since, until, output_dir=REPORT_OUTPUT_DIR)
            log.info(f"[Reports] File ready: {path}")

            wa_result = self._send_whatsapp(path, period)

            if period == "daily":
                self.last_daily_run = today
            else:
                self.last_weekly_run = today

            msg = f"Bilan {period} envoyé: {os.path.basename(path)}"
            self.last_status = {"status": "ok", "message": msg,
                                "file": path, "wa": wa_result}
            log.info(f"[Reports] {msg}")
            return self.last_status

        except Exception as exc:
            msg = f"Erreur bilan {period}: {exc}"
            log.error(f"[Reports] {msg}", exc_info=True)
            self.last_status = {"status": "error", "message": msg}
            return self.last_status

    # ── WhatsApp file dispatch ────────────────────────────────────────────

    def _send_whatsapp(self, file_path: str, period: str) -> str:
        """
        Send the Excel file to every number in WHATSAPP_NUMBERS.
        Borrows the authenticated Selenium driver from alarm_engine.
        """
        from modules.alarms import alarm_engine as ae

        if not ae._wa_ready or ae._wa_driver is None:
            log.warning("[Reports] WhatsApp session not ready — skipping WA send.")
            return "no_driver"

        period_fr = "hebdomadaire" if period == "weekly" else "journalier"
        caption = (
            f"\U0001f4ca *Bilan {period_fr} – Thermeco Industrie*\n"
            f"Généré automatiquement par le THERMECO HMI.\n"
            f"Fichier: {os.path.basename(file_path)}"
        )
        abs_path = os.path.abspath(file_path)
        driver   = ae._wa_driver
        results  = []

        with ae._wa_lock:
            for number in WHATSAPP_NUMBERS:
                try:
                    results.append(self._send_file_to_number(
                        driver, number, abs_path, caption
                    ))
                except Exception as exc:
                    log.error(f"[Reports] Send failed → {number}: {exc}", exc_info=True)
                    results.append(f"error:{number}:{str(exc)[:100]}")
                time.sleep(2)

        return "; ".join(results) if results else "no_recipients"

    def _send_file_to_number(self, driver, number: str, abs_path: str, caption: str) -> str:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        clean = number.lstrip("+")
        driver.get(f"https://web.whatsapp.com/send?phone={clean}")
        wait = WebDriverWait(driver, 35)

        # ── 1. Wait for chat to load ──────────────────────────────────────
        compose_box = None
        for sel in COMPOSE_BOX_SELECTORS:
            try:
                compose_box = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, sel)))
                break
            except Exception:
                continue
        if not compose_box:
            raise RuntimeError("Compose box not found — chat did not load.")
        time.sleep(1.5)

        # ── 2. Find & click the attach (paperclip) button ─────────────────
        # Try CSS selectors first, then fall back to JavaScript DOM search.
        attach_btn = None
        for sel in ATTACH_BTN_SELECTORS:
            try:
                attach_btn = driver.find_element(By.CSS_SELECTOR, sel)
                break
            except Exception:
                continue

        if attach_btn is None:
            attach_btn = driver.execute_script(_JS_FIND_ATTACH)

        if attach_btn is None:
            raise RuntimeError(
                "Attach button not found. Add the current selector to ATTACH_BTN_SELECTORS."
            )

        # ── ActionChains click generates real OS mouse events ─────────────
        # This is required: JS execute_script clicks are "programmatic" and
        # Chrome blocks the subsequent file-picker open with
        # "File chooser dialog can only be shown with a user activation."
        # ActionChains move+click satisfies Chrome's user-activation check.
        from selenium.webdriver.common.action_chains import ActionChains
        from selenium.webdriver.common.keys import Keys

        ActionChains(driver).move_to_element(attach_btn).click().perform()
        time.sleep(1.2)

        # ── 3. Click "Document" without opening the OS file picker ────────
        # Snapshot existing file inputs BEFORE clicking Document so we can
        # reliably identify the NEW input WhatsApp adds for the document picker.
        inputs_before = len(driver.find_elements(By.CSS_SELECTOR, 'input[type="file"]'))

        driver.execute_script("""
            window.__origInputClick = HTMLInputElement.prototype.click;
            HTMLInputElement.prototype.click = function() {
                if (this.type === 'file') return;
                window.__origInputClick.call(this);
            };
        """)
        try:
            for doc_sel in [
                '[data-testid="mi-attach-document"]',
                '[aria-label="Document"]',
                '[title="Document"]',
                'li[data-animate-dropdown-item="true"]:last-child',
                'li[data-animate-dropdown-item]:last-child',
                'span[data-testid="attach-document"]',
            ]:
                try:
                    doc_el = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, doc_sel))
                    )
                    ActionChains(driver).move_to_element(doc_el).click().perform()
                    time.sleep(1.0)
                    break
                except Exception:
                    continue
        finally:
            driver.execute_script("""
                if (window.__origInputClick) {
                    HTMLInputElement.prototype.click = window.__origInputClick;
                    delete window.__origInputClick;
                }
            """)

        # Close OS file dialog if it opened despite the monkey-patch.
        try:
            import pyautogui
            time.sleep(0.4)
            pyautogui.press("escape")
            time.sleep(0.3)
        except Exception:
            pass

        # ── 4. Wait for the NEW document file input to appear in the DOM ──
        # WhatsApp appends a fresh <input type="file"> when the Document menu
        # item is clicked.  We wait until the total count exceeds what we saw
        # before, then grab the last element — that is always the document
        # input (not the persistent photo/video input which was already there).
        file_input = None
        for _ in range(25):   # up to 5 s
            time.sleep(0.2)
            all_inputs = driver.find_elements(By.CSS_SELECTOR, 'input[type="file"]')
            if len(all_inputs) > inputs_before:
                file_input = all_inputs[-1]   # newest = document input
                break

        if file_input is None:
            # Fallback: pick the last input that is NOT exclusively photo/video
            all_inputs = driver.find_elements(By.CSS_SELECTOR, 'input[type="file"]')
            for fi in reversed(all_inputs):
                accept = (fi.get_attribute("accept") or "").strip().lower()
                if "image/" in accept and "video/" in accept and "application" not in accept:
                    continue
                file_input = fi
                break
            if file_input is None and all_inputs:
                file_input = all_inputs[-1]

        if file_input is None:
            raise RuntimeError("Document file input not found after clicking Document option.")

        file_input.send_keys(abs_path)
        time.sleep(2.5)  # let preview render

        # ── 5. Find preview send button — broad JS search + DOM debug dump ────
        # This JS tries every known pattern AND logs the actual DOM attributes
        # so we can see what WhatsApp Web is using in this browser version.
        find_send_js = """
        var COMPOSE = '[data-testid="conversation-compose-box"]';
        var result = null;

        // 1. Explicit testids (outside compose box)
        var tids = ['media-send-button','send','compose-btn-send','msg-send','media-editor-send'];
        for (var t = 0; t < tids.length && !result; t++) {
            document.querySelectorAll('[data-testid="'+tids[t]+'"]').forEach(function(el) {
                if (!result && !el.closest(COMPOSE) && el.offsetParent !== null) result = el;
            });
        }

        // 2. Any data-icon whose value contains "send" (outside compose box)
        if (!result) {
            document.querySelectorAll('[data-icon]').forEach(function(el) {
                if (result) return;
                var icon = (el.getAttribute('data-icon') || '').toLowerCase();
                if (icon.indexOf('send') < 0) return;
                if (el.closest(COMPOSE)) return;
                var btn = el.closest('button') || el.closest('[role="button"]');
                if (btn && btn.offsetParent !== null) result = btn;
            });
        }

        // 3. aria-label variants (French + English)
        if (!result) {
            var lbls = ['Envoyer','Send','Envoyer le message','Send message','Envoyer maintenant'];
            for (var l = 0; l < lbls.length && !result; l++) {
                var el2 = document.querySelector('[aria-label="'+lbls[l]+'"]');
                if (el2 && !el2.closest(COMPOSE) && el2.offsetParent !== null) result = el2;
            }
        }

        // Collect unique values of data-icon / data-testid / aria-label for debug
        var icons=[],tlist=[],alabels=[];
        document.querySelectorAll('[data-icon]').forEach(function(e){ icons.push(e.getAttribute('data-icon')); });
        document.querySelectorAll('[data-testid]').forEach(function(e){ tlist.push(e.getAttribute('data-testid')); });
        document.querySelectorAll('[aria-label]').forEach(function(e){ alabels.push(e.getAttribute('aria-label')); });
        function uniq(a){ return a.filter(function(v,i,s){ return s.indexOf(v)===i; }); }
        window.__WA_PREVIEW_DEBUG = JSON.stringify({
            icons: uniq(icons), testids: uniq(tlist), ariaLabels: uniq(alabels)
        });

        return result;
        """

        preview_send = driver.execute_script(find_send_js)
        dom_debug    = driver.execute_script("return window.__WA_PREVIEW_DEBUG || 'unavailable';")
        log.info(f"[Reports] WA DOM debug (preview state): {dom_debug}")

        # ── 6. Send the file ───────────────────────────────────────────────────
        if preview_send:
            try:
                ActionChains(driver).move_to_element(preview_send).click().perform()
                log.info("[Reports] File sent via preview send button (ActionChains).")
            except Exception:
                driver.execute_script("arguments[0].click();", preview_send)
                log.info("[Reports] File sent via preview send button (JS click).")
        else:
            # Fallback: press Enter — works when the preview caption auto-focuses.
            # pyautogui sends at OS level (bypasses Selenium focus issues).
            try:
                import pyautogui
                pyautogui.press('enter')
                log.info("[Reports] File sent via pyautogui Enter (preview auto-focus).")
            except Exception:
                ActionChains(driver).send_keys(Keys.RETURN).perform()
                log.info("[Reports] File sent via Selenium Enter fallback.")

        # ── 7. Send caption as a separate follow-up text message ──────────────
        time.sleep(2.5)  # let file deliver and preview close
        try:
            text_box = None
            for sel in COMPOSE_BOX_SELECTORS:
                try:
                    text_box = WebDriverWait(driver, 8).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, sel))
                    )
                    break
                except Exception:
                    continue
            if text_box:
                text_box.click()
                time.sleep(0.2)
                # send_keys treats \n as Enter (sends msg). Use Shift+Enter for line breaks.
                lines = caption.split('\n')
                for i, line in enumerate(lines):
                    ActionChains(driver).send_keys(line).perform()
                    if i < len(lines) - 1:
                        ActionChains(driver).key_down(Keys.SHIFT).send_keys(Keys.RETURN).key_up(Keys.SHIFT).perform()
                time.sleep(0.3)
                ActionChains(driver).send_keys(Keys.RETURN).perform()
                log.info("[Reports] Caption sent as follow-up text message.")
        except Exception as e:
            log.warning(f"[Reports] Follow-up caption text failed (non-fatal): {e}")

        time.sleep(3)
        log.info(f"[Reports] File sent → {number}")
        return f"sent:{number}"

    # ── Helpers ───────────────────────────────────────────────────────────

    def _next_run_str(self, period: str) -> str:
        now   = datetime.datetime.now()
        today = now.date()

        if period == "daily":
            candidate = datetime.datetime.combine(
                today, datetime.time(DAILY_HOUR, DAILY_MINUTE)
            )
            if candidate <= now:
                candidate += datetime.timedelta(days=1)
        else:
            days_ahead = (WEEKLY_DAY - now.weekday()) % 7
            if days_ahead == 0 and now.hour >= DAILY_HOUR:
                days_ahead = 7
            next_day  = today + datetime.timedelta(days=days_ahead)
            candidate = datetime.datetime.combine(
                next_day, datetime.time(DAILY_HOUR, DAILY_MINUTE)
            )

        return candidate.strftime("%d/%m/%Y %H:%M")
