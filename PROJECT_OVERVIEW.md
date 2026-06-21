# Thermeco Industrie SCADA/HMI — Project Overview & Known Issues

Last updated: 2026-06-21 (rev. 3 — route collision fixes documented, full API surface added)

This document explains what the system currently does, how the pieces fit
together, and — most importantly — what's fragile, incomplete, or risky
enough to need attention before this runs an actual plant unattended.

> **What changed in this revision (rev. 3):**
> - **Issue #0 is partially resolved.** `/api/write` and `/api/connect` were the
>   two confirmed route collisions between `telemetry_bp` and `vfd_blueprint`.
>   Both are now renamed in `vfd_routes.py`: `/api/write` → `/api/vfd-write`,
>   `/api/connect` → `/api/vfd-connect`. The full API surface table in §5a now
>   reflects these names.
> - **A third partial collision remains:** `/api/read` exists in both blueprints
>   but on different HTTP methods (POST in telemetry, GET in vfd). Flask routes
>   these correctly without crashing, but it is still confusing — see updated
>   Issue #0 below.
> - **`/api/update-settings` naming corrected.** The previous revision's §6a
>   described the VFD settings endpoint as `/api/vfd/update-settings` — the
>   actual route in `vfd_routes.py` is `/api/update-settings`. If
>   `view_engineering.html` currently calls `/api/vfd/update-settings`, that
>   call will 404.
> - **Full VFD API surface documented** for the first time (§5a) — several
>   routes (`/api/monitor`, `/api/raw`, `/api/read-params`, `/api/write-param`,
>   `/api/scan-hardware`, `/api/auto-link`) were not mentioned in any previous
>   revision.
> - Navigation model and §4/§6a content carried forward unchanged from rev. 2.

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
  than relying on `python` being on `PATH`.
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
   no VFD/USB-RS485 adapter is plugged in. `vfd_routes.py`'s `init_vfd()`
   fails to open the serial port — by design it doesn't crash the app, it
   just logs and leaves `instrument = None` so the VFD shows OFFLINE until
   you fix the port in the **Engineering Controls** tab and retry.

2. **The VFD warning prints twice** because Werkzeug's debug-mode
   auto-reloader spawns a second process. Everything at module level —
   including `init_vfd()`, which runs on import — executes once in the
   parent watcher and once in the worker. The `WERKZEUG_RUN_MAIN` guard in
   `app.py` stops the alarm engine's threads from double-starting; the VFD
   module has no such guard. This is a live demonstration of why `debug=True`
   needs to come off before unattended deployment.

### Stopping it

`Ctrl+C` in the same terminal. No graceful shutdown hook exists for the
alarm engine's background threads or the VFD's open serial handle — they
are daemon threads, so the process dies cleanly enough for dev use.

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
3. **Alarm dispatch** — independently polls the same PLC tags against
   a declarative rule set and sends WhatsApp text alerts when a fault
   condition transitions from clear to active.

---

## 4. Navigation model (rev. 2 — unchanged)

The tab bar moved from 5 tabs (Synoptic / Data / Settings / Alarms / VFD)
to **3 zones**, per the current `tab_bar.html`:

| Tab | id | View shown | Purpose |
|---|---|---|---|
| 📊 Vue Synoptique | `btn-synoptic` → `view-synoptic` | `synoptic_canvas.html` | Primary workspace — full process flow diagram. The HP pump is interactive *within this view* rather than linking to a separate tab (see §4a). |
| 📋 Alarmes | `btn-tab-alarms` → `view-alarms` | `alarm-panel.html` | Combined active-alarm panel + historical event log. |
| ⚙️ Configuration | `btn-tab-engineering` → `view-engineering` | `view_engineering.html` | Restricted maintenance zone: calibration offsets, PLC comms config, VFD connection settings. |

The old **"Consignes" / Settings tab is retired** — absorbed into Engineering
Controls. There is currently no tab button for `view_dataview.html`; if the
raw-tag-grid view is still wanted, it needs either its own button or a link
from within Engineering Controls.

All three are handled by `SynopticHMI.showView(viewId)` — in-page JS tab
switching, no page reload.

### 4a. The VFD tab → inline panel migration (in progress)

This is **mid-migration**, not finished:

- `tab_bar.html` **still contains** an `<a href="/modules/vfd/vfd-panel.html">`
  full-page-navigation link (`btn-tab-vfd`) as a fallback.
- The **inline panel/modal** that's supposed to replace it — opening next
  to the HP pump icon on the synoptic canvas — **has not been built yet.**
- The HP pump icon's click handler currently calls `SynopticHMI.showView('vfd')`,
  which is not a real view in the 3-tab model. This call is silently inert
  until the inline panel is built.

**Action needed:** decide whether the HP pump opens an inline panel or a
modal, build it, and update the pump's `onclick` accordingly. Until then,
the `<a href="vfd-panel.html">` link in the tab bar is the only working path
to VFD control.

---

## 4b. Project tree (current)

```
app.py                              Composition root: creates the Flask app,
                                     registers all blueprints, starts the
                                     alarm engine, serves cross-cutting
                                     static/template routes.

routes/
└── telemetry.py                    Generic PLC I/O blueprint (telemetry_bp).
                                    No url_prefix — routes live at /api/*.
                                    Bit read/write, analog read, bulk area
                                    poll, raw DB diagnostic dump.

modules/
├── vfd/
│   ├── vfd_routes.py               VFD blueprint (vfd_blueprint). No
│   │                                url_prefix — routes also live at /api/*
│   │                                (see §5a for full surface and collision
│   │                                status). Owns its own Modbus/serial
│   │                                connection and register maps.
│   ├── vfd-panel.html               Standalone page — still the only
│   │                                 working VFD UI (see §4a).
│   └── vfd_comms.js                 VFD page's frontend controller.
│                                    ⚠ Must be updated: any call to
│                                    '/api/write' → '/api/vfd-write';
│                                    any call to '/api/connect' →
│                                    '/api/vfd-connect'.
│
└── alarms/
    ├── __init__.py
    ├── alarm_config.py              Declarative alarm rules — edit this to
    │                                 add/remove/retune alarms, no code change.
    ├── alarm_engine.py               Background poll loop + WhatsApp dispatch
    │                                 via Selenium. Runs independently of any
    │                                 browser tab.
    ├── alarm_routes.py               Alarm blueprint (alarm_blueprint).
    │                                 url_prefix="/api/alarms". All alarm
    │                                 endpoints live at /api/alarms/*.
    ├── alarm-panel.html              View shown by the Alarmes tab.
    └── alarm_comms.js                Alarm tab's frontend controller.

config/
└── tags_config.py                   PLC_TAGS: the single source of truth for
                                    every readable point.

main/
├── services/
│   ├── plc_service.py                Singleton holding the snap7 client,
│   │                                  is_connected flag, and low-level
│   │                                  read_bit/write_bit/read_real/
│   │                                  read_db_block methods.
│   └── telemetry_reader.py           Shared S7 area-read loop, factored
│                                      out of routes/telemetry.py.
│
├── templates/
│   ├── index.html                    Page shell. ⚠ Confirm
│   │                                  view_engineering.html is actually
│   │                                  {% include %}'d here (see §6a).
│   └── components/
│       ├── header.html
│       ├── tab_bar.html               3-tab model + VFD fallback link.
│       ├── synoptic_canvas.html       SVG technical drawing + HTML overlay.
│       ├── view_engineering.html      NEW — Configuration tab content.
│       │                              ⚠ Calls /api/update-settings for VFD
│       │                              settings (NOT /api/vfd/update-settings
│       │                              — that path does not exist). Also
│       │                              calls /api/engineering/calibration
│       │                              and /api/connect for PLC — the
│       │                              calibration endpoint does not exist
│       │                              yet (see §6a).
│       ├── view_dataview.html         Raw tag grid. No tab button.
│       ├── view_settings.html         RETIRED — safe to delete.
│       ├── event_logger.html
│       ├── detail_panel.html
│       ├── backwash_modal.html
│       ├── footer.html
│       └── scripts.html
│
└── static/
    ├── css/
    │   ├── hmi-styles.css
    │   └── synoptic.css              Old .loc-* pixel rules are dead code.
    └── js/
        ├── hmi-app.js                Master controller + duplicate alarm eval.
        ├── synoptic.js               Renderer + tab switching. 'engineering'
        │                             now in showView() array (fixed, §6a).
        └── hmi-comms.js              Thin fetch() wrapper.
                                      ⚠ Must be updated: any call to
                                      '/api/write' → '/api/vfd-write';
                                      '/api/connect' (VFD) → '/api/vfd-connect'.
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
| `main/templates/components/view_engineering.html` | Configuration tab UI + `EngineeringPanel` JS controller | No (calls backend endpoints — some missing, see §6a) |
| `main/static/js/hmi-app.js` | Frontend poll loop + **duplicate** alarm evaluation | **Yes** — `activeAlarms` (frontend copy) |
| `main/static/js/synoptic.js` | Renders telemetry onto the diagram, tab switching, panels | No (pure render over data passed in) |

---

## 5a. Full API surface (all blueprints)

This is the authoritative list of every HTTP endpoint registered in the
application, based on the actual route decorators in each file.

### telemetry_bp (no url_prefix)

| Method | Path | Handler | Purpose |
|---|---|---|---|
| GET | `/api/tags-config` | `get_tags` | Returns `PLC_TAGS` to the frontend |
| POST | `/api/connect` | `handle_connect` | Connects snap7 client to PLC `{ip}` |
| POST | `/api/read` | `handle_read_bit` | Read single PLC bit `{db, offset}` |
| POST | `/api/write` | `handle_write_bit` | Write single PLC bit `{db, offset, value}` |
| POST | `/api/read-analog` | `handle_read_analog` | Read single DB REAL `{db, offset}` |
| GET | `/api/telemetry` | `get_bulk_telemetry` | Bulk I/Q area poll for all tags |
| POST | `/api/diag/db-dump` | `diag_db_dump` | Dev tool: raw DB byte dump `{db, start, length}` |

Also registered on `app.py` directly (not in a blueprint):

| Method | Path | Handler | Purpose |
|---|---|---|---|
| GET | `/api/tags-config` | `get_tags_config` | **Duplicate** of `telemetry_bp`'s route — `app.py` registers this separately. Flask will use whichever was registered last. Consolidate to one. |
| GET | `/` | `index` | Main HMI page |

### vfd_blueprint (no url_prefix)

> **Collision history:** `/api/write` and `/api/connect` were renamed in this
> blueprint to resolve hard Flask startup collisions with `telemetry_bp`.
> Update any frontend code (`vfd_comms.js`, `hmi-comms.js`) that still
> calls the old paths.

| Method | Path | Handler | Purpose | Collision status |
|---|---|---|---|---|
| GET | `/vfd` | `vfd_page` | Renders `vfd-panel.html` | ✅ Unique |
| GET | `/api/vfd/status` | `get_status` | Live Hz, A, AI1, F01.01, F01.02, counters | ✅ Unique |
| POST | `/api/vfd-write` | `write_hardware_bus` | Write arbitrary Modbus register | ✅ Renamed (was `/api/write`) |
| POST | `/api/vfd-connect` | `api_connect` | Open serial, handshake F01.01 | ✅ Renamed (was `/api/connect`) |
| POST | `/api/control` | `api_control` | Send FORWARD/REVERSE/STOP/RESET to VFD | ✅ Unique — but unauthenticated pump control, see Issue #5 |
| GET | `/api/monitor` | `api_monitor` | Read all C00 / C01 monitor registers | ✅ Unique |
| POST | `/api/raw` | `api_raw_transfer` | FC03 read or FC06/16 write at any address | ✅ Unique |
| GET | `/api/read-params` | `api_read_params` | Read all F01 / F12 / F13 parameter registers | ✅ Unique |
| POST | `/api/write-param` | `api_write_param` | Write a single named F-parameter by key | ✅ Unique |
| POST | `/api/update-settings` | `api_update_settings` | Update VFD port/baud/slave and re-init | ⚠ Unique in backend, but `view_engineering.html` may call `/api/vfd/update-settings` (wrong path — will 404). Fix the frontend call. |
| GET | `/api/read` | `api_read_register` | Single register debug read `?offset=0x...` | ⚠ Same path as telemetry's `/api/read` — different HTTP method (GET vs POST), so Flask routes correctly. Still confusing; rename to `/api/vfd-read` for clarity. |
| POST | `/api/scan-hardware` | `api_scan_hardware` | List available COM ports | ✅ Unique |
| POST | `/api/auto-link` | `api_auto_link` | Auto-connect to first available COM port | ✅ Unique |

### alarm_blueprint (url_prefix = `/api/alarms`)

| Method | Path | Handler | Purpose |
|---|---|---|---|
| GET | `/api/alarms/mock-data` | `get_mock_alarm_data` | Fake PLC values for WhatsApp testing without PLC |
| GET | `/api/alarms/status` | `alarm_status` | Current active/clear state of all rules |
| GET | `/api/alarms/log` | `alarm_log` | Recent event log, newest first (`?limit=N`) |
| GET | `/api/alarms/config` | `alarm_config_endpoint` | Rule definitions (labels, thresholds, severity) |
| POST | `/api/alarms/test/<rule_id>` | `alarm_test` | Manually fire a test WhatsApp dispatch |
| GET | `/api/alarms/wa-status` | `wa_status` | Is the WhatsApp Web session authenticated? |

### Endpoints expected by frontend but not yet implemented

These are called by `view_engineering.html`'s `EngineeringPanel` JS
controller but have no handler in any blueprint:

| Path | Expected by | Status |
|---|---|---|
| `POST /api/engineering/calibration` | `EngineeringPanel` save | ❌ Not implemented |
| `POST /api/update-settings` | `EngineeringPanel` PLC comms save | ✅ Exists in `vfd_blueprint` — but this saves VFD serial settings, not PLC IP/rack/slot. A separate PLC settings endpoint is still missing. |

---

## 6. Known issues / things to fix

Ordered roughly by how much it matters for a system that's supposed to
alert someone about a real fault.

### Issue #0 — Route collisions (partially resolved, one remaining)

**Resolved in rev. 3:**
- `/api/write` — renamed to `/api/vfd-write` in `vfd_routes.py`. ✅
- `/api/connect` — renamed to `/api/vfd-connect` in `vfd_routes.py`. ✅

**Frontend must be updated:** any call to the old paths in `vfd_comms.js`
or `hmi-comms.js` will now 404. Search for `'/api/write'` and
`'/api/connect'` in all JS files and update to the new names. The
Engineering Controls tab's "Tester Connexion" button calls `/api/connect`
with `{ip}` — this should hit `telemetry_bp`'s handler (correct), but
verify no VFD-connect logic was accidentally wired to the same button.

**Still open — `/api/read` (low severity):**
- `telemetry_bp`: `POST /api/read` — payload `{db, offset}` → reads a PLC
  DB bit.
- `vfd_blueprint`: `GET /api/read` — query param `?offset=0x...` → reads a
  Modbus register.

Flask correctly dispatches these by HTTP method, so there is no startup
crash and no silent shadowing. However, the shared path is confusing and
fragile if either handler ever needs to add the other's method. **Fix
direction:** rename the VFD handler to `GET /api/vfd-read` to match the
convention already established by `/api/vfd-write` and `/api/vfd-connect`.

**Still open — `/api/update-settings` naming mismatch:**
The VFD blueprint registers this as `POST /api/update-settings`. The
previous overview revision (and likely `view_engineering.html`) referenced
it as `/api/vfd/update-settings` — a path that does not exist and will
return 404. **Fix direction:** update `view_engineering.html`'s
`EngineeringPanel` to call `/api/update-settings` (the actual path), or
rename the route to `/api/vfd/update-settings` to match the expectation.
Either is fine; just make the two sides agree.

**Still open — duplicate `/api/tags-config` registration:**
Both `telemetry_bp` and `app.py` register a `GET /api/tags-config` route.
Flask will use whichever was registered last (blueprint before direct
routes in the current `app.py` order, so `app.py`'s handler wins). Both
return `PLC_TAGS`, so functionally identical right now — but this is
fragile. Remove the one from `app.py` and let the blueprint own it.

### 6a. Issues introduced or surfaced by the tab bar restructure

**Fixed during rev. 2:**
- **`showView()` was missing `'engineering'` from its view-id array.**
  Confirmed fixed by adding `'engineering'` to that array in `synoptic.js`.

**Still open:**
- **VFD migration is half-done (§4a).** The HP pump's `onclick` calls
  `showView('vfd')`, which is not a real view in the 3-tab model. Clicking
  the pump does nothing. The tab bar's `<a href>` fallback to
  `vfd-panel.html` is the only working VFD path until the inline panel is
  built.
- **`view_engineering.html`'s backend endpoints are partially missing.**
  `/api/engineering/calibration` does not exist. `/api/update-settings`
  does exist (VFD serial settings) but is not the same as a PLC IP/rack/
  slot config endpoint. `/api/vfd/update-settings` — as referenced in the
  previous overview — does not exist; the actual path is
  `/api/update-settings`. The Save/Test buttons will fail until these are
  reconciled.
- **`view_dataview.html` has no tab button.** Needs either a 4th button
  or a link from within Engineering Controls, or retire it.
- **`view_settings.html` is now orphaned.** Confirm nothing includes it,
  then delete it.
- **Confirm `index.html` actually includes `view_engineering.html`.**
  If the `{% include %}` is missing, the Configuration tab will remain
  blank despite the JS fix being correct.

### Issue #1 — Alarm logic now exists in two places, and they can disagree
**Where:** `hmi-app.js`'s `_evalAlarms()` vs. `modules/alarms/alarm_config.py`

The frontend runs its own hardcoded threshold checks and writes them to
the on-screen event log only. The backend engine runs a separately-
maintained set of the same checks and is the one that sends WhatsApp
messages. If someone tunes a threshold in one place and not the other, the
on-screen log and the WhatsApp alert will disagree — dangerous in a safety
system.

**Fix direction:** delete `_evalAlarms` from `hmi-app.js` and have the
on-screen log subscribe to `/api/alarms/log` and `/api/alarms/status`
instead. The backend is already the authoritative source.

### Issue #2 — Selenium/WhatsApp Web is a fundamentally fragile delivery channel
**Where:** `modules/alarms/alarm_engine.py`

This automates the WhatsApp Web browser UI — it is not the official API.
It breaks when WhatsApp changes their DOM, violates WhatsApp's ToS, has no
retry/backoff logic, and serializes all dispatches through a single Chrome
session so simultaneous alarms queue up behind each other.

**Fix direction:** at minimum, add retry-with-backoff and a session watchdog.
Longer term, evaluate the official WhatsApp Business Platform API (Meta or
a provider like Twilio) to remove the DOM-fragility and ToS risk entirely.

### Issue #3 — No persistence: every list, log, and alarm state lives in memory
**Where:** `alarm_engine.py` (`recent_log`, `active_alarms`), `vfd_routes.py`
(telemetry counters).

A Flask restart loses the entire alarm dispatch history, active alarm state
(causing re-notification or missed detection on restart), and VFD comms
counters. No incident review is possible beyond what's currently in RAM.

**Fix direction:** append `recent_log` entries to a flat file or SQLite as
well as memory. SQLite is a reasonable first step — no new infra, durable
across restarts, queryable for reporting. Natural place to also persist
calibration offsets once `/api/engineering/calibration` is implemented.

### Issue #4 — `debug=True` in production-facing code
**Where:** `app.py`

The current `app.py` already reads the debug flag from the environment:
```python
debug_mode = os.environ.get("DEBUG", "0").strip() in ("1", "true", "True")
app.run(host="0.0.0.0", port=5000, debug=debug_mode)
```
This means `debug=False` by default unless `DEBUG=1` is set in the
environment — an improvement over the hardcoded `debug=True` that was
here previously. **Verify this is the version actually running.** If any
earlier copy of `app.py` with hardcoded `debug=True` is still on the
machine, it exposes the Werkzeug interactive debugger to anyone who can
reach port 5000 on the LAN — effectively a remote Python shell.

### Issue #5 — No authentication anywhere
**Where:** every blueprint.

Every endpoint — including `/api/control` (sends FORWARD/REVERSE/STOP/
RESET to the VFD drive), `/api/write` (arbitrary PLC bit writes),
`/api/vfd-write` (arbitrary Modbus register writes), and
`/api/alarms/test/<rule_id>` (fires a real WhatsApp dispatch) — is
unauthenticated. Combined with `CORS(app)` enabling all origins and
`host='0.0.0.0'`, anyone who can reach port 5000 on the network can drive
the pumps or spam the alarm WhatsApp numbers.

**Fix direction:** scope CORS to known origins instead of `CORS(app)` wide
open. Put basic auth or an API key in front of all write and control
endpoints — including the new Engineering ones once they exist.

### Issue #6 — Alarm poll interval vs. telemetry poll interval mismatch
**Where:** `alarm_engine.py` (`POLL_INTERVAL_SECONDS = 2`) vs. `hmi-app.js`
(`setInterval(..., 500)`).

Frontend sees new data every 500ms; the alarm engine only checks every 2
seconds. For fast-transient faults, the alarm engine could miss a trip that
the frontend log catches — another flavor of Issue #1.

**Fix direction:** decide what "fast enough" means for your actual fault
characteristics and either match the intervals or document why they differ.

### Issue #7 — `evaluate_condition` returning `None` is a silent no-op
**Where:** `alarm_config.py`

If a tag read fails or a rule has a bad threshold, `evaluate_condition`
returns `None` and the engine holds previous state rather than guessing.
Correct behavior — but currently fails **silently**. A typo'd tag field in
a rule looks identical to a healthy rule that hasn't fired.

**Fix direction:** track a per-rule "last successfully evaluated" timestamp
and surface it on the alarm tab, or log a warning after N consecutive
unevaluable polls.

### Issue #8 — Inconsistent error-message shapes across blueprints
**Where:** compare `routes/telemetry.py` (`{"status": "error", "message": ...}`)
vs. `vfd_routes.py` (`{"status": "ERROR", "message": ...}` and
`{"success": False, "msg": ...}` depending on the endpoint) vs.
`alarm_routes.py` (delegates to `alarm_engine`, which returns its own shapes).

Three different shapes for "this failed" means any generic frontend error
handler has to know which endpoint family it's calling. The `EngineeringPanel`
controller already has to check `(data.status === 'success' || data.success)`
everywhere as a result.

**Fix direction:** standardize on one shape (suggest `{"status": "success"|"error", "message": "..."}`) and migrate opportunistically when touching these files.

### Issue #9 — Hardcoded phone numbers and PLC IP defaults in source
**Where:** `alarm_engine.py` (`NUMBERS`), `routes/telemetry.py`
(`ip = data.get('ip', '192.168.1.10')`), `vfd_routes.py` (`"port": "COM3"`).

Config changes require a code edit and redeploy. WhatsApp numbers sit in
plaintext in version control. The Engineering Controls forms are a step
toward fixing IP/port/baud — once their backend endpoints exist, those
values stop needing code edits. The phone number list still needs the same
treatment.

**Fix direction:** move to environment variables or a `.env`/config file
that is gitignored, especially for the phone numbers.

---

## 7. Things that are working correctly and don't need touching

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
  both the alarm engine and `evaluate_condition` is the right call.
- The rebuilt `synoptic_canvas.html` and its SVG/HTML-overlay split: every
  id `synoptic.js`'s `updateSynoptic()` reads or writes was verified to
  exist exactly once.
- The `showView()` fix (§6a) is confirmed applied and working for the
  Configuration tab.
- The `WERKZEUG_RUN_MAIN` guard in `app.py` correctly prevents the alarm
  engine's background threads from double-starting under the debug reloader.
- `debug` mode is now read from the `DEBUG` environment variable rather than
  hardcoded (assuming the current `app.py` is the version running).

---

## 8. Suggested next steps, in priority order

1. **Update all frontend JS for the renamed VFD routes.** Search
   `vfd_comms.js` and `hmi-comms.js` for `/api/write` and `/api/connect`
   and update to `/api/vfd-write` and `/api/vfd-connect`. This is a
   prerequisite for VFD control working at all from the browser.

2. **Fix the `/api/update-settings` naming mismatch.** Either update
   `view_engineering.html` to call `/api/update-settings` (existing path),
   or rename the route in `vfd_routes.py` to `/api/vfd/update-settings` to
   match the frontend expectation. Pick one and make both sides consistent.

3. **Rename `/api/read` (GET) in `vfd_blueprint` to `/api/vfd-read`.**
   Eliminates the remaining same-path ambiguity with telemetry's `POST /api/read`.

4. **Remove the duplicate `/api/tags-config` registration from `app.py`.**
   Let `telemetry_bp` own it.

5. **Decide and build the HP-pump → VFD path (§4a).** Either finish the
   inline panel/modal and repoint the pump's `onclick`, or formally keep
   `view-vfd` as a 4th in-page tab. Right now the pump click does nothing.

6. **Implement the missing Engineering Controls backend endpoints.**
   `/api/engineering/calibration` does not exist. A PLC comms config
   endpoint (IP/rack/slot) also does not exist — `/api/update-settings`
   saves VFD settings, not PLC settings. Implement these so the
   Configuration tab is functional, not just visible.

7. **Resolve Issue #1 (duplicate alarm logic)** — delete `_evalAlarms`
   from `hmi-app.js` and subscribe the on-screen log to
   `/api/alarms/status` and `/api/alarms/log`.

8. **Add a minimal persistence layer for alarm history and calibration
   offsets (Issue #3)** — SQLite is enough to start.

9. **Decide on an authentication story (Issue #5)** before this is
   reachable from more than one trusted machine.

10. **Add retry/watchdog logic to the WhatsApp dispatch path (Issue #2)**,
    or begin evaluating the official Business API as a replacement.

11. **Clean up navigation loose ends:** decide where `view_dataview.html`
    lives (or retire it), delete the orphaned `view_settings.html`, and
    confirm `index.html` actually includes `view_engineering.html`.