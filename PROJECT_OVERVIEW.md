# Thermeco Industrie SCADA/HMI — Project Overview & Known Issues

Last updated: 2026-06-21

This document explains what the system currently does, how the pieces fit
together, and — most importantly — what's fragile, incomplete, or risky
enough to need attention before this runs an actual plant unattended.

---

## 2. Where it lives and how to run it

Currently sitting at:
```
D:\Downloads\web-plc-tester\
```
(the exact folder name may have a suffix, e.g. `web-plc-tester-main` —
that's why the commands below use a wildcard to `cd` into it.)

### Starting the server (PowerShell)

```powershell
cd D:\Downloads
cd web-plc-tester*
$pyPath = (Get-ChildItem "$env:USERPROFILE\AppData\Local\Programs\Python\Python*\python.exe" | Select-Object -First 1).FullName
& $pyPath app.py
```

What each line does:
- `cd web-plc-tester*` — wildcard match in case the extracted folder has a
  suffix (e.g. from a GitHub zip download).
- The `$pyPath = ...` line finds whichever Python version is installed
  under the user's local `AppData\Local\Programs\Python\` folder rather
  than relying on `python` being on `PATH` — useful if there are multiple
  Pythons installed or `python`/`py` isn't aliased the way you expect on
  this machine.
- `& $pyPath app.py` — runs the app with that specific interpreter.

Once running, the HMI is reachable at:
- `http://127.0.0.1:5000` (local machine only)
- `http://192.168.1.7:5000` (from any other device on the same LAN —
  this is the machine's LAN IP, will differ on a different network)

### What a normal startup looks like

```
[VFD] Warning: Could not bind port (could not open port 'COM3': ...). Ready for re-link.
 * Serving Flask app 'app'
 * Debug mode: on
WARNING: This is a development server. Do not use it in a production deployment.
 * Running on all addresses (0.0.0.0)
 * Running on http://127.0.0.1:5000
 * Running on http://192.168.1.7:5000
Press CTRL+C to quit
 * Restarting with stat
[VFD] Warning: Could not bind port (could not open port 'COM3': ...). Ready for re-link.
 * Debugger is active!
 * Debugger PIN: 144-989-135
```

Two things worth knowing about this exact output:

1. **The `[VFD] Warning: Could not bind port 'COM3'` line is expected** if
   no VFD/USB-RS485 adapter is plugged in (or it enumerated on a different
   COM port). This is `vfd_routes.py`'s `init_vfd()` failing to open the
   serial port — by design it doesn't crash the app, it just logs and
   leaves `instrument = None` so the VFD tab shows OFFLINE until you fix
   the port (Settings tab, or check Device Manager for the actual COM
   number) and the connection is retried.

2. **The VFD warning prints twice, and that's Issue #4 from this doc made
   visible.** `Restarting with stat` is Werkzeug's debug-mode auto-reloader
   spawning a second process. Everything at module level — including
   `init_vfd()`, which runs on import — executes once in the parent
   watcher process and once again in the actual worker process. The
   `WERKZEUG_RUN_MAIN` guard added in `app.py` was specifically written to
   stop the **alarm engine's** WhatsApp/poll threads from double-starting
   the same way; the VFD module doesn't have that guard, which is why its
   warning legitimately prints twice here. This is a live demonstration of
   why `debug=True` should come off before this runs unattended — every
   module-level side effect in this codebase currently runs twice per
   boot.

### Stopping it

`Ctrl+C` in the same terminal. There's currently no graceful shutdown
hook for the alarm engine's background threads or the VFD's open serial
handle — they're daemon threads, so the whole process just dies, which is
fine for a dev workflow but is its own small item if you ever want a
clean "drain in-flight WhatsApp sends before exiting" shutdown path.

---

## 3. What this system is

A browser-based HMI (Human-Machine Interface) for a reverse-osmosis water
treatment skid, built as a Flask backend + vanilla-JS frontend styled to
look like a Siemens SIMATIC Comfort Panel. It does three jobs:

1. **Telemetry** — polls a PLC over S7 (via `python-snap7`) every 500ms and
   displays pump states, tank levels, pressures, flows, and conductivity on
   a synoptic (process flow diagram) view.
2. **VFD control** — talks Modbus RTU over RS-485 to a Veichi AC10 variable
   frequency drive (the HP pump's speed controller), as an isolated module
   with its own register map and serial connection.
3. **Alarm dispatch** — (new) independently polls the same PLC tags against
   a declarative rule set and sends WhatsApp text alerts when a fault
   condition transitions from clear to active.

---

## 4. Project tree

```
app.py                              Composition root: creates the Flask app,
                                     registers all blueprints, starts the
                                     alarm engine, serves a few cross-cutting
                                     static/template routes.

routes/
└── telemetry.py                    Generic PLC I/O blueprint (telemetry_bp).
                                    Bit read/write, analog read, bulk area
                                    poll, raw DB diagnostic dump.

modules/
├── vfd/
│   ├── vfd_routes.py               VFD blueprint (vfd_blueprint). Owns its
│   │                                own Modbus/serial connection, register
│   │                                maps (F01/F12/F13/C00/C01), and all
│   │                                /api/vfd/*, /api/control, /api/connect,
│   │                                /api/monitor endpoints.
│   ├── vfd-panel.html               Standalone page template for the VFD tab.
│   └── vfd_comms.js                 VFD tab's frontend controller.
│
└── alarms/                          (new)
    ├── __init__.py
    ├── alarm_config.py              Declarative alarm rules — edit this to
    │                                 add/remove/retune alarms, no code change.
    ├── alarm_engine.py               Background poll loop + WhatsApp dispatch
    │                                 via Selenium. Runs independently of any
    │                                 browser tab.
    ├── alarm_routes.py               Alarm blueprint (alarm_blueprint).
    │                                 Status/config/log/test-trigger endpoints.
    ├── alarm-panel.html              Standalone page template for the alarm tab.
    └── alarm_comms.js                Alarm tab's frontend controller.

config/
└── tags_config.py                   PLC_TAGS: the single source of truth for
                                    every readable point — component_id →
                                    variables → {type, offset, area}.

main/
├── services/
│   ├── plc_service.py                Singleton holding the snap7 client,
│   │                                  is_connected flag, and low-level
│   │                                  read_bit/write_bit/read_real/
│   │                                  read_db_block methods.
│   └── telemetry_reader.py           (new) Shared S7 area-read loop, factored
│                                      out of routes/telemetry.py so the HTTP
│                                      endpoint and the alarm engine read PLC
│                                      data through exactly one implementation.
│
├── templates/
│   ├── index.html                    Page shell. Renders the Comfort Panel
│   │                                  frame and {% include %}s every component.
│   └── components/                   NOTE: none of these template files were
│       │                              directly reviewed — descriptions below
│       │                              are inferred from index.html's include
│       │                              list and from what synoptic.js/hmi-app.js
│       │                              reference (element IDs, onclick targets).
│       │                              Verify against the actual files.
│       ├── header.html               likely the top status bar (connection dot).
│       ├── tab_bar.html               (inferred, not reviewed) likely the
│       │                              tab switcher (Synoptic / Data / Settings).
│       ├── synoptic_canvas.html       The process-flow diagram itself.
│       ├── view_dataview.html         Raw tag grid (auto-built from PLC_TAGS).
│       ├── view_settings.html         Connection settings form.
│       ├── event_logger.html          On-screen scrolling log panel.
│       ├── detail_panel.html          Slide-out panel for per-component detail.
│       ├── backwash_modal.html        Modal for sand-filter backwash controls.
│       ├── footer.html
│       └── scripts.html               Likely where hmi-comms.js / synoptic.js
│                                       / etc. get <script> tags injected.
│
└── static/
    ├── css/
    │   ├── hmi-styles.css             Comfort Panel chrome (bezel, screen inset).
    │   └── synoptic.css               Process diagram specific styling.
    └── js/
        ├── hmi-app.js                  Master controller. init() loads tag
        │                               config, starts a 500ms setInterval that
        │                               fetches telemetry, fans it out to the
        │                               synoptic renderer + data grid, and runs
        │                               _evalAlarms() — frontend threshold
        │                               checks that only write to the on-screen
        │                               event log (see Issue #1 below).
        ├── synoptic.js                  SynopticController: draws pump/tank/
        │                               filter states, the detail side-panel,
        │                               tab switching, backwash modal actions.
        └── hmi-comms.js                 (not reviewed directly) — presumed
                                         thin fetch() wrapper around the
                                         /api/* endpoints used by hmi-app.js.
```

---

## 5. What each file is actually responsible for

| File | Responsibility | Owns state? |
|---|---|---|
| `app.py` | Wires blueprints together, starts background services | App-level only |
| `routes/telemetry.py` | HTTP surface for PLC reads/writes | No (delegates to `plc_service`) |
| `main/services/plc_service.py` | The actual S7 client connection | **Yes** — `is_connected`, snap7 client |
| `main/services/telemetry_reader.py` | One shared "read all tags" function | No (pure function over `plc_service`) |
| `config/tags_config.py` | Defines what tags exist | **Yes** — the canonical tag map |
| `modules/vfd/vfd_routes.py` | HTTP surface + register maps for the VFD | **Yes** — separate Modbus connection, `vfd_settings`, telemetry counters |
| `modules/alarms/alarm_config.py` | Defines what counts as an alarm | **Yes** — the canonical rule map |
| `modules/alarms/alarm_engine.py` | Detects + dispatches alarms | **Yes** — `active_alarms`, `recent_log`, WhatsApp Selenium session |
| `modules/alarms/alarm_routes.py` | HTTP surface for the alarm tab | No (delegates to `alarm_engine`) |
| `main/static/js/hmi-app.js` | Frontend poll loop + **duplicate** alarm evaluation | **Yes** — `activeAlarms` (frontend copy) |
| `main/static/js/synoptic.js` | Renders telemetry onto the diagram | No (pure render over data passed in) |

---

## 6. Known issues / things to fix

Ordered roughly by how much it matters for a system that's supposed to
alert someone about a real fault.

### Issue #0 — `/api/write` is registered by two different blueprints (real bug, not hypothetical)
**Where:** `routes/telemetry.py` (`telemetry_bp.route('/api/write', ...)` →
`handle_write_bit`, writes a single PLC bit by `db`/`offset`) and
`modules/vfd/vfd_routes.py` (`vfd_blueprint.route('/api/write', ...)` →
`write_hardware_bus`, writes an arbitrary Modbus register on the VFD by
`register`/`value`).

Both blueprints are registered on the same Flask app in `app.py`. Flask
blueprints don't get a URL prefix here (neither blueprint sets
`url_prefix=`), so **these are the literal same route path on the same
app**. Two different things happen depending on registration order and
Flask/Werkzeug version: either Flask raises `AssertionError: View function
mapping is overwriting an existing endpoint function` at startup and the
app refuses to boot, or one handler silently shadows the other and you get
PLC bit-writes routed into the VFD's Modbus write path (or vice versa) with
totally different payload shapes (`db`/`offset`/`value` vs.
`register`/`value`/`decimals`).

**This is the single most urgent fix in this document** — it's not a
"someday" cleanup, it's a startup-time collision (or worse, a silent
misroute) in code that writes to physical actuators.

**Fix direction:** give each blueprint a distinct prefix, e.g.
```python
app.register_blueprint(telemetry_bp)                       # /api/write  (PLC bit)
app.register_blueprint(vfd_blueprint, url_prefix='/vfd')    # /vfd/api/write (Modbus)
```
or rename one of the two routes (e.g. VFD's becomes `/api/vfd/write` to
match its sibling `/api/vfd/status`, which already follows that
convention). Check every other route in `vfd_routes.py` for the same
collision risk while you're in there — `/api/connect`, `/api/control`,
`/api/read`, and `/api/update-settings` are all also unprefixed and at
least `/api/connect` exists in `telemetry.py` too with a different payload
shape (`ip` vs. `port`/`baud_rate`/`slave_address`).

### Issue #1 — Alarm logic now exists in two places, and they can disagree
**Where:** `hmi-app.js`'s `_evalAlarms()` vs. `modules/alarms/alarm_config.py`

The frontend still runs its own hardcoded threshold checks (HP overpressure
at hardcoded fallback `16`, conductivity at hardcoded fallback `500`, plus
feed/HP pump fault bits) and writes them to the on-screen event log only.
The new backend engine runs a *second*, separately-maintained set of the
same checks and is the one that actually sends WhatsApp messages.

**Why this matters:** if someone tunes a threshold in one place and not the
other, the on-screen log and the WhatsApp alert will disagree about whether
something is currently in alarm. That's a confusing — and for a safety
system, dangerous — state to be in.

**Fix direction:** pick one source of truth. Either (a) delete `_evalAlarms`
from `hmi-app.js` and have the on-screen log subscribe to
`/api/alarms/log` + `/api/alarms/status` instead, or (b) have `hmi-app.js`
fetch `/api/alarms/config` at startup and evaluate against those rules
instead of hardcoded numbers. (a) is simpler and was flagged as a pending
decision — not yet implemented.

### Issue #2 — Selenium/WhatsApp Web is a fundamentally fragile delivery channel
**Where:** `modules/alarms/alarm_engine.py`

This automates the WhatsApp Web browser UI by clicking through it — it is
not the official WhatsApp Business API. Concretely:

- **It breaks every time WhatsApp changes their web client's DOM.** This
  already happened once in this project (the original voice-note attach
  button selector went stale and silently timed out).
- **It's against WhatsApp's Terms of Service** for automated/bulk messaging,
  which carries a real risk of the number being banned with no warning.
- **No retry/backoff logic** — if a send fails (timeout, disconnected
  session, WhatsApp UI update), the alarm is logged as `"failed"` and
  nothing retries it. For a fire/gas/intrusion-class alarm, a single silent
  failure with no retry is a real gap.
- **Single Chrome session, single lock (`wa_lock`)** — alarms are dispatched
  to each number sequentially, with `time.sleep()` waits between each. If
  three alarms fire within a few seconds of each other, they queue up
  behind each other; the second and third alarms could be delayed by
  10–20+ seconds before anyone is notified.

**Fix direction (in order of effort):** at minimum, add retry-with-backoff
and a "WhatsApp session died, restart it automatically" watchdog. Longer
term, evaluate the official WhatsApp Business Platform API (Meta-hosted,
or via a provider like Twilio) — it's a paid service but removes the
"breaks when WhatsApp updates their website" failure mode entirely, and
removes the ToS risk.

### Issue #3 — No persistence: every list, log, and alarm state lives in memory
**Where:** `alarm_engine.py` (`recent_log`, `active_alarms`), `vfd_routes.py`
(telemetry counters), `app.py`'s Flask process in general.

If the Flask process restarts (crash, deploy, server reboot, `debug=True`
reloader triggering unexpectedly), you lose:
- The entire alarm dispatch history (`recent_log`)
- Current alarm active/inactive state (`active_alarms`) — meaning an alarm
  that's still actively firing will be treated as "new" again on restart
  and may re-notify, or conversely won't be detected as "already known"
- VFD comms counters (`_tx_count`/`_rx_count`/`_crc_errors`)

**Why this matters:** for any kind of incident review ("what alarms fired
overnight and were they acknowledged?"), in-memory-only state means the
answer is "we don't know, the server restarted." This also means there's no
record of plant alarm history beyond whatever's currently in RAM.

**Fix direction:** at minimum, append `recent_log` entries to a flat file
or SQLite as well as memory. SQLite is a reasonable first step — no new
infra, durable across restarts, queryable for reporting.

### Issue #4 — `debug=True` in production-facing code
**Where:** `app.py`, `app.run(host='0.0.0.0', port=5000, debug=True)`

Flask's debug mode:
- Exposes the **Werkzeug interactive debugger** on any unhandled exception
  — which, if this is reachable from the plant network (and it explicitly
  binds `0.0.0.0` to accept connections from PLCs/simulators), means anyone
  who can trigger a server error gets an interactive Python shell on your
  HMI server.
- Auto-reloads on file changes, which is what required the
  `WERKZEUG_RUN_MAIN` guard added when wiring in the alarm engine — a
  reasonable proxy that more "this is actually a dev convenience flag
  left on" problems exist nearby.

**Fix direction:** `debug=False` for anything other than active local
development, full stop. If you need auto-reload during development, that's
fine locally, but it shouldn't be the same flag that's live when this is
deployed near real hardware.

### Issue #5 — No authentication anywhere
**Where:** every blueprint.

Every endpoint — including `/api/control` (which can send FORWARD/REVERSE/
STOP/RESET to the VFD), `/api/write` (arbitrary PLC bit writes), and
`/api/alarms/test/<rule_id>` (fires a real WhatsApp dispatch) — is
unauthenticated. Combined with `CORS(app)` enabling all origins and
`host='0.0.0.0'`, anyone who can reach port 5000 on the network can drive
the pumps or spam the alarm WhatsApp numbers.

**Fix direction:** this matters in proportion to how exposed the network
actually is. If this is genuinely isolated on a private plant VLAN with no
outside routing, the risk is lower but still real (anyone on that VLAN,
including a compromised device, has full control). At minimum, scope CORS
to known origins instead of `CORS(app)` wide open, and put basic auth or an
API key in front of write/control endpoints before this is reachable from
anywhere beyond a single trusted machine.

### Issue #6 — Alarm poll interval vs. telemetry poll interval mismatch
**Where:** `alarm_engine.py` (`POLL_INTERVAL_SECONDS = 2`) vs. `hmi-app.js`
(`setInterval(() => this._scanCycle(), 500)`).

The frontend sees new data every 500ms; the alarm engine only checks every
2 seconds. For fast-transient faults (a fault bit that pulses briefly), the
alarm engine could miss it between polls while the frontend log catches it
— another flavor of Issue #1's "two systems disagree" problem, this time
caused by timing rather than logic.

**Fix direction:** decide what "fast enough" means for your actual fault
characteristics (a trip relay's contact dwell time, say), and either match
the intervals or document why they intentionally differ.

### Issue #7 — `evaluate_condition` returning `None` is a silent no-op
**Where:** `alarm_config.py`

By design, if a tag read fails (`value is None`) or a rule has a bad
threshold, `evaluate_condition` returns `None` and the engine "holds
previous state" rather than guessing. This is the *correct* choice to avoid
false resolves on a comms blip — but it currently fails **silently**. There's
no metric or log line distinguishing "this rule has been unevaluable for
the last 40 polls because the tag name has a typo" from "this rule is
healthy and just hasn't fired."

**Fix direction:** track a per-rule "last successfully evaluated" timestamp
and surface it on the alarm tab (or log a warning after N consecutive
unevaluable polls) — a typo'd `tag` field in a rule should be loud, not
silent.

### Issue #8 — Inconsistent error-message shapes across blueprints
**Where:** compare `routes/telemetry.py` (`{"status": "error", "message": ...}`)
vs. `vfd_routes.py` (`{"status": "ERROR", "message": ...}` *and*
`{"success": False, "msg": ...}` depending on the endpoint).

Three different shapes for "this failed" across the codebase
(`status`/`message` lowercase, `status`/`message` uppercase,
`success`/`msg`) means any frontend code that wants to handle errors
generically can't — it has to know which endpoint family it's talking to.

**Fix direction:** not urgent, but worth standardizing the next time you're
touching any of these files — pick one shape and migrate opportunistically
rather than as a dedicated rewrite.

### Issue #9 — Hardcoded phone numbers and PLC IP defaults in source
**Where:** `alarm_engine.py` (`NUMBERS`), `routes/telemetry.py`
(`ip = data.get('ip', '192.168.1.10')`), `vfd_routes.py` (`"port": "COM3"`).

These are fine for a single-site deployment but mean every config change
requires a code edit and redeploy, and the WhatsApp numbers are sitting in
plaintext in version control.

**Fix direction:** move to environment variables or a `.env`/config file
that's gitignored, especially for the phone numbers.

---

## 7. Things that are working correctly and don't need touching

To be clear about what's *not* broken:

- The S7 area-read logic (`telemetry_reader.py`) correctly distinguishes
  I/Q area codes, handles BOOL bit-extraction and INT/WORD struct unpacking,
  and the PLCSim-safety constraints (even byte counts, no DB reads for I/Q
  tags) are respected throughout.
- The VFD module's `safe_write`'s FC06-then-FC16 fallback is a sensible,
  defensive pattern for Modbus device quirks.
- The alarm engine's edge-triggering (`active_alarms` dict, only dispatch
  on OFF→ON transition) correctly avoids re-sending the same alarm every
  poll cycle.
- The "hold previous state on disconnected/unreadable data" behavior in
  both the alarm engine and `evaluate_condition` is the right call — it
  would be easy to get this wrong (treating `None`/disconnected as "all
  clear") and it wasn't.

---

## 8. Suggested next steps, in priority order

1. Fix the `/api/write` / `/api/connect` blueprint route collision
   (Issue #0) — this can prevent the app from starting at all, or silently
   misroute writes, and should be fixed before anything else in this list.
2. Resolve Issue #1 (duplicate alarm logic) — pick frontend-log-reads-
   backend-state as the model, since the backend is now the actual source
   of truth for dispatch.
3. Turn off `debug=True` (Issue #4) before this is anywhere near a real
   network, even temporarily.
4. Add a minimal persistence layer for alarm history (Issue #3) — SQLite
   is enough to start.
5. Decide on an authentication story (Issue #5) before this is reachable
   from more than one trusted machine.
6. Add retry/watchdog logic to the WhatsApp dispatch path (Issue #2), or
   begin evaluating the official Business API as a replacement.