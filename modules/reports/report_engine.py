# modules/reports/report_engine.py
# ---------------------------------------------------------------------------
# Background engine that:
#   1. Schedules and builds daily / weekly Excel bilans
#   2. Sends them via WhatsApp using the *same* Selenium session
#      already owned by alarm_engine (shared driver instance)
#
# Integration
# ───────────
# In app.py, after starting the alarm engine:
#
#     from modules.reports.report_engine import ReportEngine
#     report_engine = ReportEngine(alarm_engine.wa_driver)
#     report_engine.start()
#
# The engine borrows the WhatsApp Selenium driver from alarm_engine so both
# share the same authenticated browser session.
# If you prefer a standalone driver, pass driver=None and it will create its
# own (requires a separate WhatsApp Web login).
#
# Manual triggers are available via /api/reports/trigger-daily and
# /api/reports/trigger-weekly (see report_routes.py).
# ---------------------------------------------------------------------------

import os
import threading
import time
import datetime
import logging

from config.report_config import (
    DAILY_HOUR, DAILY_MINUTE, WEEKLY_DAY, REPORT_PHONE
)
from modules.reports.report_builder import build_report

log = logging.getLogger(__name__)

# Temp dir for generated Excel files
REPORT_OUTPUT_DIR = os.environ.get("REPORT_OUTPUT_DIR",
                                   os.path.join(os.getcwd(), "reports_output"))


class ReportEngine:
    def __init__(self, wa_driver=None):
        """
        wa_driver: Selenium WebDriver instance already logged in to
                   WhatsApp Web, or None to skip WhatsApp dispatch.
        """
        self._driver  = wa_driver
        self._thread  = None
        self._stop    = threading.Event()

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
        """Immediately generate and send today's daily report."""
        return self._run_report("daily")

    def trigger_weekly(self) -> dict:
        """Immediately generate and send this week's weekly report."""
        return self._run_report("weekly")

    def status(self) -> dict:
        return {
            **self.last_status,
            "last_daily_run":  str(self.last_daily_run)  or None,
            "last_weekly_run": str(self.last_weekly_run) or None,
            "next_daily":      self._next_run_str("daily"),
            "next_weekly":     self._next_run_str("weekly"),
        }

    # ── Internal loop ─────────────────────────────────────────────────────

    def _loop(self):
        while not self._stop.is_set():
            now = datetime.datetime.now()

            # Daily trigger
            if (now.hour == DAILY_HOUR and now.minute == DAILY_MINUTE
                    and self.last_daily_run != now.date()):
                self._run_report("daily")

            # Weekly trigger
            if (now.weekday() == WEEKLY_DAY
                    and now.hour == DAILY_HOUR and now.minute == DAILY_MINUTE
                    and self.last_weekly_run != now.date()):
                self._run_report("weekly")

            # Sleep until the next whole minute
            sleep_secs = 60 - now.second
            self._stop.wait(sleep_secs)

    # ── Report execution ──────────────────────────────────────────────────

    def _run_report(self, period: str) -> dict:
        now   = datetime.datetime.now()
        today = now.date()

        if period == "daily":
            # Yesterday 00:00 → yesterday 23:59:59
            yesterday = today - datetime.timedelta(days=1)
            since = datetime.datetime.combine(yesterday,
                    datetime.time.min).timestamp()
            until = datetime.datetime.combine(yesterday,
                    datetime.time.max).timestamp()
        else:
            # Last week Monday 00:00 → last week Sunday 23:59:59
            last_monday = today - datetime.timedelta(days=today.weekday() + 7)
            last_sunday = last_monday + datetime.timedelta(days=6)
            since = datetime.datetime.combine(last_monday,
                    datetime.time.min).timestamp()
            until = datetime.datetime.combine(last_sunday,
                    datetime.time.max).timestamp()

        try:
            log.info(f"[Reports] Building {period} report …")
            path = build_report(period, since, until,
                                output_dir=REPORT_OUTPUT_DIR)
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

    # ── WhatsApp dispatch ─────────────────────────────────────────────────

    def _send_whatsapp(self, file_path: str, period: str) -> str:
        """
        Send *file_path* to REPORT_PHONE via WhatsApp Web.
        Mirrors the approach used in alarm_engine.py.
        Returns a status string.
        """
        if self._driver is None:
            log.warning("[Reports] No WhatsApp driver — skipping WA send.")
            return "no_driver"

        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            import selenium.webdriver.common.keys as Keys

            driver = self._driver
            period_fr = "hebdomadaire" if period == "weekly" else "journalier"
            caption = (
                f"📊 *Bilan {period_fr} – Thermeco Industrie*\n"
                f"Généré automatiquement par le SCADA.\n"
                f"Fichier: {os.path.basename(file_path)}"
            )

            # Open chat
            url = f"https://web.whatsapp.com/send?phone={REPORT_PHONE}"
            driver.get(url)
            wait = WebDriverWait(driver, 30)

            # Wait for input box
            box = wait.until(
                EC.presence_of_element_located(
                    (By.XPATH, '//div[@contenteditable="true"][@data-tab="10"]')
                )
            )
            time.sleep(2)

            # Attach file via paperclip
            attach_btn = driver.find_element(
                By.XPATH, '//div[@title="Joindre"]'
            )
            attach_btn.click()
            time.sleep(1)

            file_input = driver.find_element(
                By.XPATH, '//input[@accept="*"]'
            )
            file_input.send_keys(os.path.abspath(file_path))
            time.sleep(2)

            # Add caption
            caption_box = wait.until(
                EC.presence_of_element_located(
                    (By.XPATH, '//div[@contenteditable="true"][@data-tab="10"]')
                )
            )
            caption_box.send_keys(caption)
            time.sleep(1)

            # Send
            send_btn = driver.find_element(
                By.XPATH, '//span[@data-icon="send"]'
            )
            send_btn.click()
            time.sleep(3)

            log.info(f"[Reports] WhatsApp file sent to {REPORT_PHONE}.")
            return "sent"

        except Exception as exc:
            log.error(f"[Reports] WhatsApp send failed: {exc}", exc_info=True)
            return f"error: {exc}"

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
            # Next occurrence of WEEKLY_DAY at DAILY_HOUR
            days_ahead = (WEEKLY_DAY - now.weekday()) % 7
            if days_ahead == 0 and now.hour >= DAILY_HOUR:
                days_ahead = 7
            next_day   = today + datetime.timedelta(days=days_ahead)
            candidate  = datetime.datetime.combine(
                next_day, datetime.time(DAILY_HOUR, DAILY_MINUTE)
            )

        return candidate.strftime("%d/%m/%Y %H:%M")