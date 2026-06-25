# Thermeco Industrie SCADA/HMI — Project Overview & Known Issues

Last updated: 2026-06-25 (rev. 4 — telemetry layer moved entirely off I/Q
areas onto DB2; tags_config.py is now the single source of truth for both
reads and writes; telemetry_reader.py and the write-by-tag path are new)

This document explains what the system currently does, how the pieces fit
together, and — most importantly — what's fragile, incomplete, or risky
enough to need attention before this runs an actual plant unattended.

> **What changed in this revision (rev. 4):**
> - **All telemetry tags moved off physical I/Q areas onto DB2.** Every tag
>   in `config/tags_config.py` is now `"area": "DB", "db": 2` with a real
>   (or explicitly placeholder) byte offset, matching the TIA Portal
>   "Declaration hmi [DB2]" variable table. `client.read_area()` is no
>   longer used anywhere in the telemetry path — see §5b.
> - **`main/services/telemetry_reader.py` now actually exists.** Rev. 3
>   described this file as already factored out; it was not. It has now
>   been written from scratch: a pure function (`read_all_tags()`) that
>   walks `PLC_TAGS` and dispatches each tag to the matching typed
>   `plc_service` reader. `routes/telemetry.py`'s `/api/telemetry` is now a
>   thin wrapper around it, as rev. 3 originally (inaccurately) claimed.
> - **`tags_config.py` was reorganized** into named functional groups that
>   mirror the DB2 layout (setpoints, alarm thresholds, manual buttons,
>   etc.), plus a second set of groups (`instruments`, `sand_filter`,
>   `cartridge_filters`, `feed_pump`, `hp_pump`, `tanks`,
>   `global_management`) whose component/variable names are copied
>   **exactly** from what `synoptic.js` reads and writes. See §5c for the
>   full convention (`enabled`, `writable`, placeholder `offset: None`).
> - **New write path: `/api/write-tag` + `write_tag_by_id()`.** Previously
>   `synoptic.js` hardcoded `HmiApp.triggerWrite(50, '20.0', true)`-style
>   calls — raw DB/offset pairs aimed at **DB50**, a different DB than
>   everything else in the system. All 9 of these call sites (pump
>   start/stop, auto/manual mode, backwash settings/trigger) have been
>   rewired to `HmiApp.triggerWriteByTag('tag-name', value)`, which calls
>   the new `/api/write-tag` endpoint. The backend looks up `db`/`offset`/
>   `type` from `tags_config.py` and refuses the write unless the tag is
>   explicitly marked `"writable": True`. See §5d.
> - **The old `/api/write` and `/api/connect` (telemetry_bp) are
>   untouched** — rev. 3's collision fixes against `vfd_blueprint` still
>   stand as documented below. Nothing in this revision changed VFD
>   routing, the alarm engine, or the navigation/tab-bar issues from §4/§4a/
>   §6a — all of that is carried forward unchanged and still open.
> - **Two real data-integrity issues surfaced and were fixed or flagged
>   during the DB2 transcription** — see new §6, Issue #10.

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
   a synoptic (process flow diagram) view. **As of rev. 4, every tag lives
   in DB2** — see §5b. There is no physical I/Q polling left in the
   telemetry path.
2. **VFD control** — talks Modbus RTU over RS-485 to a Veichi AC10 variable
   frequency drive (the HP pump's speed controller), as an isolated module
   with its own register map and serial connection. Unchanged this
   revision.
3. **Alarm dispatch** — independently polls the same PLC tags against
   a declarative rule set and sends WhatsApp text alerts when a fault
   condition transitions from clear to active. Unchanged this revision —
   `alarm_config.py` still defines its own rule set independently of
   `tags_config.py` (see Issue #1, still open).

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

This is **mid-migration**, not finished, and **untouched by this
revision**:

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
                                    REV. 4: bulk telemetry now delegates to
                                    telemetry_reader.read_all_tags() instead
                                    of looping with client.read_area() inline.
                                    New /api/write-tag endpoint added — see §5d.

modules/
├── vfd/
│   ├── vfd_routes.py               VFD blueprint (vfd_blueprint). No
│   │                                url_prefix — routes also live at /api/*
│   │                                (see §5a for full surface and collision
│   │                                status). Owns its own Modbus/serial
│   │                                connection and register maps.
│   │                                UNCHANGED this revision.
│   ├── vfd-panel.html               Standalone page — still the only
│   │                                 working VFD UI (see §4a). UNCHANGED.
│   └── vfd_comms.js                 VFD page's frontend controller.
│                                    ⚠ STILL outstanding from rev. 3: any
│                                    call to '/api/write' → '/api/vfd-write';
│                                    any call to '/api/connect' →
│                                    '/api/vfd-connect'. Not addressed this
│                                    revision — this file was not touched.
│
└── alarms/                         UNCHANGED this revision. All of rev. 3's
    ├── __init__.py                 Issues #1, #2, #3, #6, #7 below still
    ├── alarm_config.py              apply exactly as written.
    ├── alarm_engine.py
    ├── alarm_routes.py
    ├── alarm-panel.html
    └── alarm_comms.js

config/
└── tags_config.py                   PLC_TAGS: the single source of truth
                                    for every readable AND writable point.
                                    REV. 4: fully reorganized — see §5c.
                                    95 variables defined across 20 component
                                    groups; 43 enabled with real DB2 offsets,
                                    52 are named placeholders awaiting real
                                    offsets (enabled: False, offset: None).
                                    7 are marked writable: True.

main/
├── services/
│   ├── plc_service.py                Singleton holding the snap7 client,
│   │                                  is_connected flag, and low-level
│   │                                  read_bit/write_bit/read_real/
│   │                                  read_db_block methods. UNCHANGED —
│   │                                  still only DB-area methods; no
│   │                                  write_dint or write_word exist yet
│   │                                  (see Issue #11, new this revision).
│   └── telemetry_reader.py           REV. 4: NEWLY WRITTEN. Rev. 3 claimed
│                                      this already existed as "S7 area-read
│                                      loop, factored out of telemetry.py" —
│                                      it did not exist in the codebase.
│                                      Now contains:
│                                        - read_all_tags(tags_config) — walks
│                                          PLC_TAGS, dispatches each enabled
│                                          tag to the matching typed
│                                          plc_service reader, returns a flat
│                                          {tag_id: value} dict. Per-tag read
│                                          failures return None and log a
│                                          warning; they do not abort the
│                                          batch.
│                                        - find_tag(tag_id) — looks up a
│                                          single tag's full metadata dict.
│                                        - write_tag_by_id(tag_id, value) —
│                                          the backing function for
│                                          /api/write-tag. See §5d.
│
├── templates/
│   ├── index.html                    Page shell. ⚠ STILL not confirmed:
│   │                                  whether view_engineering.html is
│   │                                  actually {% include %}'d here (see
│   │                                  §6a). Not addressed this revision.
│   └── components/
│       ├── header.html
│       ├── tab_bar.html               3-tab model + VFD fallback link.
│       │                              UNCHANGED.
│       ├── synoptic_canvas.html       SVG technical drawing + HTML overlay.
│       │                              UNCHANGED this revision — every id
│       │                              synoptic.js reads/writes was already
│       │                              verified present exactly once (rev. 3).
│       ├── view_engineering.html      Configuration tab content. UNCHANGED
│       │                              this revision — all of rev. 3's ⚠
│       │                              notes about /api/update-settings and
│       │                              /api/engineering/calibration still
│       │                              apply exactly as written (see §6a).
│       ├── view_dataview.html         Raw tag grid. No tab button. UNCHANGED.
│       ├── view_settings.html         RETIRED — safe to delete. UNCHANGED.
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
    │                                 UNCHANGED.
    └── js/
        ├── hmi-app.js                Master controller + duplicate alarm
        │                             eval (Issue #1, still open, unchanged).
        │                             REV. 4: added triggerWriteByTag(tagId,
        │                             value) alongside the existing
        │                             triggerWrite(db, offset, value). The
        │                             old method is left in place — nothing
        │                             else in this codebase calls it anymore
        │                             after this revision's synoptic.js
        │                             changes, but it has not been deleted
        │                             in case vfd_comms.js or another file
        │                             still depends on it (not checked this
        │                             revision).
        ├── synoptic.js               Renderer + tab switching. 'engineering'
        │                             in showView() array (fixed rev. 2,
        │                             unchanged). REV. 4: all 9 write call
        │                             sites (feed pump on/off, HP pump
        │                             on/off, auto/manual mode, backwash ΔP/
        │                             duration/manual-trigger) rewired from
        │                             hardcoded triggerWrite(50, 'X.X', val)
        │                             to triggerWriteByTag('tag-name', val).
        │                             Zero hardcoded db/offset writes remain
        │                             in this file. Diagnostic dump default
        │                             DB changed 51 → 2 to match the rest of
        │                             the system.
        └── hmi-comms.js              Thin fetch() wrapper. ⚠ STILL
                                      outstanding from rev. 3: any call to
                                      '/api/write' → '/api/vfd-write';
                                      '/api/connect' (VFD) →
                                      '/api/vfd-connect'. Not addressed this
                                      revision — this file was not touched,
                                      and is unrelated to the new
                                      /api/write-tag path (different
                                      blueprint, different purpose).
```

---

## 5. What each file is actually responsible for

| File | Responsibility | Owns state? |
|---|---|---|
| `app.py` | Wires blueprints together, starts background services | App-level only |
| `routes/telemetry.py` | HTTP surface for PLC reads/writes | No (delegates to `plc_service` / `telemetry_reader`) |
| `main/services/plc_service.py` | The actual S7 client connection | **Yes** — `is_connected`, snap7 client |
| `main/services/telemetry_reader.py` | Bulk read loop + tag-name write lookup, over `tags_config.py` | No (pure functions over `plc_service` + `PLC_TAGS`) |
| `config/tags_config.py` | Defines what tags exist, their DB2 address, and which are writable | **Yes** — the canonical tag map, now also the canonical write-permission map |
| `modules/vfd/vfd_routes.py` | HTTP surface + register maps for the VFD | **Yes** — separate Modbus connection, `vfd_settings`, telemetry counters |
| `modules/alarms/alarm_config.py` | Defines what counts as an alarm | **Yes** — the canonical rule map |
| `modules/alarms/alarm_engine.py` | Detects + dispatches alarms | **Yes** — `active_alarms`, `recent_log`, WhatsApp Selenium session |
| `modules/alarms/alarm_routes.py` | HTTP surface for the alarm tab | No (delegates to `alarm_engine`) |
| `main/templates/components/view_engineering.html` | Configuration tab UI + `EngineeringPanel` JS controller | No (calls backend endpoints — some missing, see §6a) |
| `main/static/js/hmi-app.js` | Frontend poll loop + duplicate alarm evaluation + write dispatch (`triggerWrite`, `triggerWriteByTag`) | **Yes** — `activeAlarms` (frontend copy) |
| `main/static/js/synoptic.js` | Renders telemetry onto the diagram, tab switching, panels, write-button wiring | No (pure render over data passed in; writes go through `HmiApp`) |

---

## 5a. Full API surface (all blueprints)

This is the authoritative list of every HTTP endpoint registered in the
application, based on the actual route decorators in each file.
**Unchanged from rev. 3 except where marked REV. 4 below** — VFD and alarm
blueprints were not touched this revision.

### telemetry_bp (no url_prefix)

| Method | Path | Handler | Purpose |
|---|---|---|---|
| GET | `/api/tags-config` | `get_tags` | Returns `PLC_TAGS` to the frontend |
| POST | `/api/connect` | `handle_connect` | Connects snap7 client to PLC `{ip}` |
| POST | `/api/read` | `handle_read_bit` | Read single PLC bit `{db, offset}` |
| POST | `/api/write` | `handle_write_bit` | Write single PLC bit `{db, offset, value}` — raw, trusts caller-supplied db/offset, NOT looked up from `tags_config.py`. Still used by VFD "Tester Connexion" wiring per rev. 3 notes. |
| POST | `/api/read-analog` | `handle_read_analog` | Read single DB REAL `{db, offset}` |
| GET | `/api/telemetry` | `get_bulk_telemetry` | **REV. 4:** Bulk poll, now calls `telemetry_reader.read_all_tags(PLC_TAGS)` — no more inline `read_area()` loop, no more I/Q area codes anywhere in this handler |
| POST | `/api/write-tag` | `handle_write_tag` | **NEW, REV. 4.** `{tag_id, value}` → looks up `db`/`offset`/`type` from `PLC_TAGS`, refuses unless the tag has `"writable": True` and `"enabled": True`. See §5d. |
| POST | `/api/diag/db-dump` | `diag_db_dump` | Dev tool: raw DB byte dump `{db, start, length}`. **REV. 4:** default `db` changed from `51` → `2` |

Also registered on `app.py` directly (not in a blueprint):

| Method | Path | Handler | Purpose |
|---|---|---|---|
| GET | `/api/tags-config` | `get_tags_config` | **Duplicate** of `telemetry_bp`'s route — still unresolved, see Issue #0 below, unchanged this revision |
| GET | `/` | `index` | Main HMI page |

### vfd_blueprint (no url_prefix) — UNCHANGED THIS REVISION

> **Collision history:** `/api/write` and `/api/connect` were renamed in this
> blueprint to resolve hard Flask startup collisions with `telemetry_bp`.
> Update any frontend code (`vfd_comms.js`, `hmi-comms.js`) that still
> calls the old paths. **Still not done as of rev. 4** — `vfd_comms.js`
> and `hmi-comms.js` were not part of this revision's scope.

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
| POST | `/api/update-settings` | `api_update_settings` | Update VFD port/baud/slave and re-init | ⚠ Unique in backend, but `view_engineering.html` may call `/api/vfd/update-settings` (wrong path — will 404). Still unresolved. |
| GET | `/api/read` | `api_read_register` | Single register debug read `?offset=0x...` | ⚠ Same path as telemetry's `/api/read` — different HTTP method (GET vs POST), Flask routes correctly. Still unresolved; rename recommendation unchanged from rev. 3. |
| POST | `/api/scan-hardware` | `api_scan_hardware` | List available COM ports | ✅ Unique |
| POST | `/api/auto-link` | `api_auto_link` | Auto-connect to first available COM port | ✅ Unique |

### alarm_blueprint (url_prefix = `/api/alarms`) — UNCHANGED THIS REVISION

| Method | Path | Handler | Purpose |
|---|---|---|---|
| GET | `/api/alarms/mock-data` | `get_mock_alarm_data` | Fake PLC values for WhatsApp testing without PLC |
| GET | `/api/alarms/status` | `alarm_status` | Current active/clear state of all rules |
| GET | `/api/alarms/log` | `alarm_log` | Recent event log, newest first (`?limit=N`) |
| GET | `/api/alarms/config` | `alarm_config_endpoint` | Rule definitions (labels, thresholds, severity) |
| POST | `/api/alarms/test/<rule_id>` | `alarm_test` | Manually fire a test WhatsApp dispatch |
| GET | `/api/alarms/wa-status` | `wa_status` | Is the WhatsApp Web session authenticated? |

### Endpoints expected by frontend but not yet implemented — UNCHANGED

| Path | Expected by | Status |
|---|---|---|
| `POST /api/engineering/calibration` | `EngineeringPanel` save | ❌ Not implemented |
| `POST /api/update-settings` | `EngineeringPanel` PLC comms save | ✅ Exists in `vfd_blueprint` — but saves VFD serial settings, not PLC IP/rack/slot. Separate endpoint still missing. |

---

## 5b. DB2 migration — what actually changed and why

Before rev. 4, `tags_config.py` mixed physical I/Q tags (`"area": "I"` /
`"area": "Q"`, read via `client.read_area()`) with nothing from any DB. The
PLC program has since been changed so that **every signal the HMI needs now
lives in DB2** ("Declaration hmi"), confirmed directly against TIA Portal's
variable table.

Consequences of this:
- `routes/telemetry.py`'s `/api/telemetry` no longer branches on area code
  (`0x81`/`0x82` for I/Q) at all. It is 100% DB reads now, dispatched
  through `plc_service`'s typed methods (`read_bit`, `read_int`,
  `read_dint`, `read_word`, `read_real`).
- The NetToPLCSim-safety constraints that used to apply only to `db_read()`
  calls (even byte counts, no DB reads for I/Q tags) are now relevant to
  *every* tag in the system, not just the diagnostic dump tool — see the
  warning already baked into `plc_service.py`'s docstring.
- `plc_service.py` itself was **not modified** — it already had the typed
  DB readers/writers this migration needed (`read_bit`, `read_int`,
  `read_dint`, `read_word`, `read_real`, `write_bit`, `write_int`,
  `write_real`). No new methods were added to it.

---

## 5c. `tags_config.py` structure & editing convention (rev. 4)

`config/tags_config.py` is now organized into 20 named component groups,
falling into three categories:

1. **Real, enabled tags (43 total)** — setpoints, alarm thresholds, manual
   buttons, schedule-day bits, etc., transcribed directly from the TIA
   Portal DB2 variable table. These have real `offset`/`type`/`db` values
   and are actively polled by `/api/telemetry`.

2. **Reserved/disabled placeholders for things deliberately NOT modeled**
   (`schedule_RESERVED`, `unnamed_RESERVED`) — `Time_Of_Day` schedule
   fields (custom scheduling will replace these) and two PLC variables
   whose TIA names are literally `"1997"`/`"1998"` (unrenamed placeholders
   in the PLC program itself, purpose unconfirmed). All have
   `"enabled": False` so `telemetry_reader.py` skips them; their byte
   ranges are documented so nothing else gets assigned on top of them by
   mistake.

3. **Placeholder groups for tags `synoptic.js` needs but that don't exist
   in DB2 yet** (`instruments`, `sand_filter`, `cartridge_filters`,
   `feed_pump`, `hp_pump`, `tanks`, `global_management`) — 38 variable
   names, copied character-for-character from `synoptic.js`'s
   `updateSynoptic()` and `_panelConfig` (e.g. `data['feed_pump-cmd']`,
   `bool('hp_pump-fault')`). Every one of these currently has
   `"offset": None, "type": None, "enabled": False`. They exist purely as
   name reservations so that once the live process values are added to
   DB2, filling in `offset`/`type` and removing `enabled: False` is the
   *only* change needed — no renaming in any JS file, ever.

**Editing convention, going forward:**
- `"enabled": False` (or omitted defaults to `True`) → `telemetry_reader.py`
  skips this tag entirely; it will not appear in `/api/telemetry`'s
  response at all, not even as `null`.
- `"writable": True` → this tag may be written via `/api/write-tag`; see
  §5d. Tags without this key default to read-only.
- BOOL tags use `"offset": "byte.bit"` (e.g. `"150.1"`); INT/WORD use a
  byte offset only (2-byte width); DINT/REAL use a byte offset only
  (4-byte width). Check neighboring tags for overlap before assigning a
  real offset — `plc_service.py` will round odd byte-counts up for safety,
  which can silently extend a read into the next tag's bytes if offsets
  are packed too tightly.
- `"type"` must be one of `BOOL`, `INT`, `DINT`, `WORD`, `REAL` for reads.
  For writes, only `BOOL`, `INT`, `REAL` are currently supported — see
  Issue #11.

---

## 5d. Write-by-tag path (new, rev. 4)

**Problem this solves:** before this revision, 7 of `synoptic.js`'s action
buttons (feed pump start/stop, HP pump start/stop, auto/manual mode,
backwash ΔP threshold, and 2 backwash actions with no prior read-side tag
at all) called `HmiApp.triggerWrite(50, '<offset>', value)` directly —
hardcoding **DB50**, not DB2, with no relationship to `tags_config.py`
whatsoever. Editing `tags_config.py` would never have changed where these
writes actually landed.

**How it works now:**
1. `synoptic.js`'s `_panelConfig` action buttons and the backwash-modal
   methods (`applyBackwashSettings`, `startManualBackwash`) call
   `HmiApp.triggerWriteByTag('tag-name', value)` instead of
   `HmiApp.triggerWrite(db, offset, value)`.
2. `triggerWriteByTag` (new method in `hmi-app.js`) POSTs
   `{tag_id, value}` to `/api/write-tag`.
3. `handle_write_tag` (new route in `routes/telemetry.py`) calls
   `write_tag_by_id(tag_id, value, PLC_TAGS)`.
4. `write_tag_by_id` (new function in `telemetry_reader.py`) looks up the
   tag's `db`/`offset`/`type`/`writable`/`enabled` from `PLC_TAGS` and:
   - refuses if the tag_id isn't found at all,
   - refuses if `"enabled": False`,
   - refuses if `"writable"` isn't `True`,
   - refuses if the tag's `type` has no corresponding `plc_service`
     write method (see Issue #11),
   - otherwise dispatches to the correct typed writer and returns
     `(True, "DB{db}.{offset} ({tag_id}) = {value}")`.

**7 tags currently marked `"writable": True`** (all still `"enabled": False`
pending real DB2 offsets):
- `feed_pump-cmd`
- `hp_pump-cmd`
- `global_management-auto`
- `global_management-manual`
- `sand_filter-dp_max`
- `sand_filter-backwash_duration` *(new tag, no read-side equivalent existed before)*
- `sand_filter-manual_backwash_trigger` *(new tag, no read-side equivalent existed before)*

**The old `/api/write` (`{db, offset, value}`, raw, no tag lookup) was left
completely untouched** — it's still used elsewhere (VFD "Tester Connexion"
wiring per rev. 3), and changing its contract was out of scope. The two
write paths now coexist: `/api/write` for anything that still needs raw
db/offset, `/api/write-tag` for anything that should be governed by
`tags_config.py`.

---

## 6. Known issues / things to fix

Ordered roughly by how much it matters for a system that's supposed to
alert someone about a real fault. **Issues #0 through #9 are carried
forward unchanged from rev. 3** unless marked otherwise — none of that
underlying code was touched this revision. Two new issues (#10, #11) were
surfaced by the DB2 transcription and write-by-tag work.

### Issue #0 — Route collisions (partially resolved, one remaining) — UNCHANGED

**Resolved in rev. 3:**
- `/api/write` — renamed to `/api/vfd-write` in `vfd_routes.py`. ✅
- `/api/connect` — renamed to `/api/vfd-connect` in `vfd_routes.py`. ✅

**Frontend must still be updated:** any call to the old paths in
`vfd_comms.js` or `hmi-comms.js` will 404. Not addressed this revision.

**Still open — `/api/read` (low severity), `/api/update-settings` naming
mismatch, duplicate `/api/tags-config` registration:** all exactly as
described in rev. 3, unchanged.

### 6a. Issues introduced or surfaced by the tab bar restructure — UNCHANGED

All items from rev. 3 (VFD migration half-done, missing Engineering
Controls backend endpoints, `view_dataview.html` has no tab button,
orphaned `view_settings.html`, unconfirmed `index.html` include) remain
exactly as described. None of this was in scope this revision.

### Issue #1 — Alarm logic now exists in two places, and they can disagree — UNCHANGED

`hmi-app.js`'s `_evalAlarms()` vs. `modules/alarms/alarm_config.py` still
disagree independently. **Worth flagging explicitly now that `tags_config.py`
is the single source of truth for telemetry:** `alarm_config.py` is a
*separate* rule map that does not read from `tags_config.py` — a tag
renamed or re-offset in `tags_config.py` will not automatically update any
alarm rule that references it by name. This was already true before rev. 4
but is easier to miss now that tags_config.py *looks* authoritative for
everything.

### Issue #2 through #9 — UNCHANGED

Selenium/WhatsApp fragility, no persistence, `debug=True` risk, no
authentication, alarm/telemetry poll interval mismatch, silent
`evaluate_condition` no-op, inconsistent error shapes, hardcoded phone
numbers/IPs — all exactly as described in rev. 3. None were in scope this
revision.

### Issue #10 — DB2 transcription gaps (new, rev. 4)

**Where:** `config/tags_config.py`

Two real ambiguities surfaced while transcribing the TIA Portal DB2 table
and were resolved or flagged rather than guessed:
- **`lundi_hmi` vs `start_filtre_a_sable` offset collision** — both
  initially appeared at byte 48.0 in the source screenshot. Confirmed:
  `start_filtre_a_sable` = 48.0, `lundi_hmi` = 48.1.
- **`entre_filtre_sable`** — the same screenshot also showed this at 48.1,
  colliding with the corrected `lundi_hmi` offset. Left as
  `"offset": "TBD.0"`, `"enabled": False` — a real address was never
  confirmed. **Anyone enabling this tag must set its real offset first;
  "TBD.0" is not a valid address.**
- **`unnamed_1997` / `unnamed_1998`** (offsets 204, 208) — TIA shows these
  variables' names literally as `"1997"` and `"1998"`, almost certainly
  never renamed after creation. Left disabled pending a decision on
  whether to rename them in TIA and document their real purpose, or
  retire the bytes.

**Fix direction:** resolve `entre_filtre_sable`'s real offset and rename/
document `unnamed_1997`/`unnamed_1998` in TIA before enabling any of the
three.

### Issue #11 — `plc_service.py` has no `write_dint` or `write_word` (new, rev. 4)

**Where:** `main/services/plc_service.py`, `main/services/telemetry_reader.py`'s `_WRITE_DISPATCH`

`plc_service.py` implements `write_bit`, `write_int`, `write_real` — but
not `write_dint` or `write_word`. `telemetry_reader.write_tag_by_id()`
already accounts for this: a tag with `"writable": True` but `"type":
"DINT"` or `"type": "WORD"` will be cleanly refused with a clear error
message (`"...has no write method in plc_service.py yet..."`) rather than
crashing or silently doing the wrong thing. None of the 7 currently-writable
tags use DINT/WORD, so this hasn't bitten yet — but it will the first time
someone marks a DINT setpoint (e.g. one of the `temps_alarme_*_ms` timer
fields) as writable without first adding the corresponding method to
`plc_service.py`.

**Fix direction:** add `write_dint`/`write_word` to `plc_service.py`
(mirroring the existing `write_int`/`write_real` pattern) before marking
any DINT/WORD tag writable.

---

## 7. Things that are working correctly and don't need touching

- The S7 area-read logic described in earlier revisions is now retired —
  see §5b. **(rev. 4: no longer relevant; superseded by the DB2 read path.)**
- The VFD module's `safe_write`'s FC06-then-FC16 fallback is a sensible,
  defensive pattern for Modbus device quirks. Unchanged.
- The alarm engine's edge-triggering (`active_alarms` dict, only dispatch
  on OFF→ON transition) correctly avoids re-sending the same alarm every
  poll cycle. Unchanged.
- The "hold previous state on disconnected/unreadable data" behavior in
  the alarm engine, and the equivalent "failed read returns None, doesn't
  abort the batch" behavior in `telemetry_reader.read_all_tags()` (rev. 4),
  is the right call in both places.
- The rebuilt `synoptic_canvas.html` and its SVG/HTML-overlay split: every
  id `synoptic.js`'s `updateSynoptic()` reads or writes was verified to
  exist exactly once. Unchanged this revision.
- The `showView()` fix (§6a) is confirmed applied and working for the
  Configuration tab. Unchanged.
- The `WERKZEUG_RUN_MAIN` guard in `app.py` correctly prevents the alarm
  engine's background threads from double-starting under the debug reloader.
  Unchanged.
- `debug` mode is read from the `DEBUG` environment variable rather than
  hardcoded. Unchanged.
- **(New, rev. 4)** `telemetry_reader.write_tag_by_id()`'s refusal logic
  (unknown tag / disabled tag / non-writable tag / unsupported type for
  writes) was exercised directly against a mock `plc_service` and confirmed
  to reject all four bad cases with a specific, distinguishable message,
  and to dispatch correctly for both BOOL and REAL on the success path.
- **(New, rev. 4)** Cross-referenced all 38 tag IDs `synoptic.js` reads
  (`instruments-*`, `feed_pump-*`, `hp_pump-*`, `tanks-*`,
  `sand_filter-*`, `cartridge_filters-*`, `global_management-*`) against
  `tags_config.py` — confirmed all 38 now exist with exactly matching
  names. Confirmed disabled placeholder tags never leak into
  `/api/telemetry`'s response.

---

## 8. Suggested next steps, in priority order

1. **Send real DB2 offsets for the 38 placeholder tags in `instruments`,
   `sand_filter`, `cartridge_filters`, `feed_pump`, `hp_pump`, `tanks`, and
   `global_management`** once those live-process values are added to the
   PLC program. This is the single biggest remaining gap — until this is
   done, the synoptic view's gauges, dots, and fill bars have nowhere to
   read real data from, regardless of anything else in this document.
2. **Resolve `entre_filtre_sable`'s real offset** and **rename/document
   `unnamed_1997`/`unnamed_1998` in TIA** (Issue #10) before enabling any
   of the three.
3. **Add `write_dint`/`write_word` to `plc_service.py`** (Issue #11)
   before marking any DINT/WORD setpoint as writable.
4. **Update `vfd_comms.js` and `hmi-comms.js` for the renamed VFD routes**
   (`/api/write` → `/api/vfd-write`, `/api/connect` → `/api/vfd-connect`)
   — still outstanding from rev. 3, untouched this revision.
5. **Fix the `/api/update-settings` naming mismatch** between
   `view_engineering.html` and `vfd_routes.py` — still outstanding from
   rev. 3.
6. **Rename `/api/read` (GET) in `vfd_blueprint` to `/api/vfd-read`** —
   still outstanding from rev. 3.
7. **Remove the duplicate `/api/tags-config` registration from `app.py`**
   — still outstanding from rev. 3.
8. **Decide and build the HP-pump → VFD path (§4a)** — still outstanding.
9. **Implement the missing Engineering Controls backend endpoints**
   (`/api/engineering/calibration`, a real PLC comms config endpoint) —
   still outstanding.
10. **Resolve Issue #1 (duplicate alarm logic)** — delete `_evalAlarms`
    from `hmi-app.js`, subscribe the on-screen log to `/api/alarms/status`
    and `/api/alarms/log`. Worth doing now alongside a check of whether
    `alarm_config.py`'s rules reference any tag names that no longer match
    `tags_config.py` after the rev. 4 reorganization.
11. **Add persistence (Issue #3), decide on authentication (Issue #5),
    add WhatsApp retry/watchdog (Issue #2)** — all still outstanding,
    unchanged priority from rev. 3.
12. **Clean up navigation loose ends** (`view_dataview.html`,
    `view_settings.html`, confirm `index.html`'s include) — still
    outstanding.