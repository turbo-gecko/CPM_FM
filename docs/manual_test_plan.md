# CP/M File Manager — Manual Test Plan

| Field | Value |
|-------|-------|
| Document title | CP/M File Manager Manual Test Plan |
| Document ID | CPM-FM-MTP |
| Version | 1.57 |
| Status | Draft |
| Date | 2026-07-15 |
| Traces to | `docs/cpm_fm_requirements.md` (SRS v2.25.0) |

---

## 1. Purpose and scope

This plan covers functionality that the automated test suite **cannot** exercise and that therefore
must be verified by hand. The automated suite (`pytest`) already covers:

- The CP/M 4-column DIR parser and drive-prompt detection — all of `DR-*` (`tests/test_cpm_parser.py`).
- `SerialManager.open_port` flow-control / key-name mapping — `UIR-028`, `NFR-002`
  (`tests/test_serial_manager.py`).
- The X-Modem progress hook, the checksum/CRC receive handshake, and cancel/abort (CAN) — `FR-105`,
  `FR-120`, `NFR-003a`–`NFR-003q` (`tests/test_xmodem.py`), using an in-memory fake port.
- Headless GUI logic under the `offscreen` Qt platform — transfer/batch orchestration, progress-dialog
  state, transfer cancellation wiring, dialog button layout, drive-change logic, list-clearing on
  load/disconnect, geometry/last-config persistence, Config > New Config, the context-menu file actions, and
  transfer-history recording/dialog/re-transfer (`tests/test_gui_smoke.py`), all with serial I/O,
  sleeps, threads, and modal dialogs stubbed out.
- The persistent transfer-history store — entry schema, JSON persistence, retention (count + age),
  thread-safe recording, and export — `FR-140`–`FR-142`, `DR-045` (`tests/test_transfer_history.py`).

What remains for **manual** verification, and is the subject of this plan:

1. **Real serial behaviour** — opening/closing physical ports, two-port vs. shared-port operation,
   port enumeration, and the error paths when a port cannot be opened/closed (`FR-030`–`FR-058`,
   `IFR-001`–`IFR-003`).
2. **End-to-end X-Modem transfers** against a real (or emulated) CP/M system, in both directions,
   single and batch, including the CP/M-side launch commands, timing, and live cancellation
   (`FR-080`–`FR-109`, `FR-120`).
3. **Real remote listing and drive selection** — the capture/idle-timeout mechanism and the live
   `DIR` round-trip (`FR-070`–`FR-079`, `FR-100`–`FR-104`).
4. **Visual / look-and-feel** — the Material theme, OS light/dark following, toolbar, splitter,
   status-bar indicators, every dialog's on-screen layout and field constraints, and the consistent
   Cancel/affirmative button placement across dialogs (`UIR-*`, `UIR-075`, `CR-012`/`CR-013`).
5. **OS integration** — File dialogs, geometry persistence across real sessions, viewer/editor launch
   and OS-default fallback, and `python -m cpm_fm` debug output (`FR-004`–`FR-006`, `FR-088`, `FR-112`).
6. **Terminal Window** interactive VT-100/VT-52/ADM-3A behaviour over a live link (`FR-090`–`FR-098`, `FR-157`, `FR-157i`, `FR-157j`, `FR-158`, `FR-158a`, `FR-158b`, `UIR-034`, `UIR-060`–`UIR-068`, `UIR-106`).

Each test case lists the requirement IDs it verifies so coverage can be traced back to the SRS.

---

## 2. Test environment and prerequisites

### 2.1 Hardware / connectivity options

A real serial round-trip is required for most of §5–§9. Use whichever of the following is available;
note which was used in the results.

- **Option A — Real CP/M system.** A legacy CP/M 2.2 machine connected over RS-232 (directly or via a
  USB-to-serial adapter), with `PCGET`/`PCPUT` (or equivalents) installed on the CP/M side.
- **Option B — CP/M emulator.** An emulator (e.g. RunCPM, z80pack) exposing a serial endpoint, with
  the X-Modem helper programs available.
- **Option C — Loopback / port pair (partial).** A null-modem pair (`com0com` on Windows, `socat`
  PTY pair on Linux/macOS) or a hardware loopback plug. This validates *port open/close*, *enumeration*,
  *terminal send/receive*, and *byte echo*, but **not** a genuine CP/M `DIR` parse or a real X-Modem
  handshake (there is no CP/M peer). Mark CP/M-dependent steps **N/A** when using Option C.

For the **two-port** cases you need two distinct ports (e.g. two adapters, or two `com0com` pairs).
For the **shared-port** cases the Terminal and Transport ports are set to the same device.

### 2.2 Software setup

```
python -m pip install -e .[dev]
```

Launch under each of the two entry points as the case requires:

- `cpm-fm` — windowed launcher (no console). Use for normal GUI testing. Debug Logging still
  writes `cpm_fm_debug.log` to the folder you launched from under this launcher (`FR-088`).
- `python -m cpm_fm` — keeps a console; **required** for any case that inspects stdout
  (debug logging *stdout* trace, serial error prints — `FR-088`).

### 2.3 Test data

- The example configs in `examples/` (e.g. `RC2014_Z_Pro.json`, flat shape) for the config cases. No
  nested-shape example ships; for the nested-format compatibility case (MT-L02) derive one by hand by
  wrapping the serial keys under a `serial` object (see `NFR-002`). The nested shape is also covered by
  the automated suite (`tests/test_serial_manager.py`).
- A small **host** file set in a scratch folder: at least one short text file, one binary file, one
  file whose name has no extension, and one file ≥ ~1 KB (to span multiple X-Modem blocks).
- On the CP/M side, a drive (e.g. `A:`) holding a few files including one extensionless file and one
  single-file directory if you can arrange it.

### 2.4 Clean-state note (QSettings)

Geometry, the last-used config file, and the last-used config folder persist in host-native storage
(`QSettings`, org `turbo-gecko`, app `cpm-fm` — on Windows, `HKCU\Software\turbo-gecko\cpm-fm`).
For a true "first run" (`FR-003` unconfigured start, `FR-005` no remembered file) clear that key
first, and restore/back it up afterwards if you care about your own settings.

### 2.5 Pass/fail recording

For each case record: **Pass / Fail / Blocked / N/A**, the environment option used (A/B/C), the OS,
the app version, and any observation. A case is **Pass** only if every "Expected" bullet is observed.

---

## 3. How to use this plan

Run §4 (smoke) first; if the app will not start, stop and fix that. Then §5–§13 may be run in any
order, subject to their preconditions. Cases that need a live CP/M peer are marked **[CP/M]**; cases
that need two physical ports are marked **[2-port]**; visual-only cases are marked **[visual]**.

---

## 4. Smoke / start-up

| ID | Req | Steps | Expected |
|----|-----|-------|----------|
| MT-S01 | STR-002, CR-012, CR-013 | Launch `cpm-fm` with QSettings cleared (§2.4). | Main window appears; no console error; the Material theme is visibly applied (not the default Qt/native look). |
| MT-S02 | FR-003, FR-060, FR-070 | Observe the freshly-launched window. | App is unconfigured (no settings loaded); Host Files list shows the current working directory's files; Remote Files list is **empty**. |
| MT-S03 | UIR-001, UIR-002, UIR-003, UIR-004 | Inspect the menu bar. | A **File** menu with **New, Load, Save, Exit** (New at top), a **Config** menu with **Serial, General**, and a **Help** menu with **About**. |
| MT-S04 | UIR-013, UIR-071, UIR-015, UIR-016, UIR-082, UIR-086, UIR-087 | Inspect the top toolbar. | A toolbar with **Connect, Disconnect, Terminal, History, Backup, Restore** as labelled, icon-bearing buttons; Connect and Disconnect both enabled at startup. |
| MT-S05 | UIR-011, UIR-012, UIR-017, UIR-061..067 | Inspect the panes. | Host Files group (title shows **Host Files — `<current directory>`**, FR-126; top row with equally-sized **Change Directory** + **Update** buttons, multi-select list, row with **Copy to Remote**); Remote Files group (equally-sized drive drop-down + **Update** button, multi-select list, **Copy to Host** row). |

---

## 5. Serial connect / disconnect (real ports)

Preconditions: a valid serial configuration is loaded (Config > Load Config `examples/RC2014_Z_Pro.json`,
then edit ports via Config > Serial to match your hardware), unless a case says otherwise.

| ID | Req | Steps | Expected |
|----|-----|-------|----------|
| MT-C01 | FR-030, FR-032, FR-034, UIR-074 | With a valid Terminal Port configured and free, press **Connect**. | Terminal Port opens; status bar shows "Terminal port open"; the Terminal status indicator switches to its *connected* visual state. |
| MT-C02 | FR-031, FR-033 | Configure the Terminal Port to a non-existent or already-in-use port; press **Connect**. | An error dialog containing "Terminal port is unable to be opened" appears; workflow cancelled; Terminal indicator stays *not-connected*. |
| MT-C03 [2-port] | FR-038, FR-040, UIR-074 | Configure **different** Terminal and Transport ports, both free; press **Connect**. | Both ports open; Transport status flag/indicator becomes *connected*. |
| MT-C04 [2-port] | FR-039 | Configure a valid Terminal Port but a bad/busy **Transport** Port; press **Connect**. | An error dialog containing "Transport port is unable to be opened" appears. |
| MT-C05 | FR-037 | Configure the **same** physical port as both Terminal and Transport; press **Connect**. | Terminal opens; Transport flag/indicator also becomes *connected* without a second open. (Regression: no `NoneType … in_waiting` crash on a later Copy.) |
| MT-C06 | FR-035, FR-097 | After connecting, confirm the Terminal Window did **not** auto-open. | Connect does not open the Terminal Window; it opens only via the Terminal button. |
| MT-C11 | FR-041, FR-042 | With a real CP/M system at its CCP prompt on the configured port(s), press **Connect**. | After both ports open, the app sends an EOL and the remote returns a drive prompt; the status bar briefly shows "Checking remote file system"; the drive drop-down updates to the remote's current drive and the Remote Files list populates automatically. |
| MT-C12 | FR-041, FR-043, FR-044, FR-045, UIR-092 | Press **Connect** with the remote unreachable (cable unplugged at the CP/M end, or the remote not at the CCP prompt) so no drive prompt returns. | After two EOL attempts a **modal** dialog states the remote computer's file system cannot be accessed, presenting exactly three buttons in left-to-right order **Abort, Continue, Terminal**. |
| MT-C12a | FR-045 | In the MT-C12 dialog, press **Abort**. | The comm port(s) are closed (Disconnect behaviour) and the Remote Files list is cleared. |
| MT-C12b | FR-045 | Re-trigger MT-C12, press **Continue**. | The dialog closes; the port(s) remain open; the Remote Files list stays empty; no other action taken. |
| MT-C12c | FR-045, FR-097 | Re-trigger MT-C12, press **Terminal**. | The Terminal Window opens for debugging; the port(s) remain open. |
| MT-C13 | DR-033, FR-042 | On a ZCPR/NZCOM-style system whose prompt embeds the user area (e.g. `A0>` or `4A>`), press **Connect**. | The probe recognises the ZCPR prompt; the drive drop-down and Remote Files list update as in MT-C11 — the "file system unavailable" dialog (MT-C12) does **not** appear. |
| MT-C14 [CP/M] | FR-047, FR-048 | On a remote that does **not** boot straight into CP/M (sits at a monitor/boot prompt), configure a Boot Sequence (MT-G10) that drives it into CP/M, then press **Connect**. | The initial probe finds no drive prompt; the app runs the boot sequence, then re-probes once. On reaching CP/M the drive drop-down and Remote Files list populate as in MT-C11 — the "file system unavailable" dialog does **not** appear. |
| MT-C15 [CP/M] | FR-044, FR-048 | Press **Connect** with the remote unreachable and the Boot Sequence **empty**. | No boot sequence runs; after the two probe attempts the Remote Filesystem Unavailable dialog (MT-C12) appears directly, exactly as before this feature. |
| MT-C07 | FR-050, FR-052, FR-053 | While connected (shared or single port), press **Disconnect**. | Terminal Port closes; status bar shows "Terminal port closed"; Terminal indicator → *not-connected*. |
| MT-C08 [2-port] | FR-055, FR-057 | While connected on two ports, press **Disconnect**. | Both ports close; Transport flag/indicator → *not-connected*. |
| MT-C09 | FR-058 | Connect, Update to populate the Remote list, then Disconnect (clean close). | Remote Files list is **cleared** after the successful disconnect. |
| MT-C10 | FR-051, FR-058 | Force a close failure if you can (e.g. pull the adapter mid-session so close raises), then Disconnect. | Error dialog "Terminal port is unable to be closed"; disconnect cancelled; Remote list **not** cleared. *(May be Blocked if a close failure cannot be induced.)* |
| MT-C18 [2-port] | FR-030, FR-050 | Configure the Terminal and Transport COM ports **back-to-front** (swapped). Press **Connect**; when the "Remote Filesystem Unavailable" dialog appears, click **Abort**. Separately, repeat and instead press **Disconnect** immediately after Connect (before the dialog). | In **both** cases the application disconnects **promptly** (within a couple of seconds) — it does **not** hang or become unresponsive for tens of seconds. Both ports end *not-connected*. |
| MT-C19 | FR-017a, FR-050 | While **connected** (ports open), use **Config → Load Config** to load a different configuration file. | The original ports are closed before the new config is applied: both indicators go *not-connected*, the Remote Files list clears, and the app is **not** left reporting *connected* on the old ports. (Reconnect uses the newly loaded config's ports.) |

---

## 6. Serial port configuration & enumeration

| ID | Req | Steps | Expected |
|----|-----|-------|----------|
| MT-P01 | IFR-003, UIR-022, UIR-023 | Plug in a known USB adapter. Open Config > Serial (leave "Show all ports" unticked). Inspect the Terminal Port and Transfer Port drop-downs. | Both drop-downs list the host's **active** ports with the just-plugged USB adapter near the top; on Linux the inactive legacy nodes (`/dev/ttyS1`…`/dev/ttyS31`) are **not** shown, so the list is short. |
| MT-P01a | UIR-121 | In Config > Serial, tick **Show all ports**, then untick it. | Ticking immediately expands both drop-downs to every port the host reports (on Linux the full `/dev/ttyS*` run appears); the current selection is preserved. Unticking collapses them back to the active list. The checkbox is unticked again the next time the dialog is opened, and toggling it does not by itself change the saved configuration. |
| MT-P01b | UIR-022, UIR-023 | Configure Terminal Port to an inactive/unplugged port while "Show all ports" is ticked, save, close, then reopen the dialog with "Show all ports" unticked. | The configured port is still listed and selected in the drop-down even though it is otherwise hidden — the saved selection is never silently dropped. |
| MT-P02 [visual] | FR-020, UIR-020, UIR-021, UIR-029 | Open Config > Serial. | Modal dialog titled "Serial Config"; "Port Settings" and "Transmit Delay" groups laid out as two columns (name left, field right). |
| MT-P03 | UIR-024..028 | Inspect each drop-down's values and defaults. | Speed list = 300…921600, default 115200; Data = 7,8 default 8; Parity = NONE,ODD,EVEN,MARK,SPACE default NONE; Stop Bits = 1,2 default 1; Flow = NONE,XON/XOFF,RTS/CTS,DSR/DTR default RTS/CTS. |
| MT-P04 | UIR-030, UIR-031 | Try to type out-of-range / non-integer values into msec/char and msec/line. | Each field accepts only integers 0–255; default 0. |
| MT-P05 | UIR-028 | Set Flow = RTS/CTS, save, Connect to a port whose peer requires/asserts hardware flow control. | Handshake applied at open (transfer proceeds where a NONE setting would stall, or verify via a serial line monitor). *(Best-effort; mark N/A if no flow-control-sensitive peer.)* |
| MT-P06 | IFR-002 | Set Terminal and Transport to the same port; save; reopen the dialog. | Same physical port accepted for both logical ports; values round-trip. |

---

## 7. General configuration dialog

| ID | Req | Steps | Expected |
|----|-----|-------|----------|
| MT-G01 [visual] | FR-021, UIR-040, UIR-041, UIR-044, UIR-117 | Open Config → General. | Modal dialog titled "General Config". The fields are **ungrouped** (no group boxes) in a two-column form: Debug Logging, Viewer/Editor, Default Host Directory, Default Image Directory. The form sits in a **scrollable area** with the Save/Cancel row fixed below (a vertical scrollbar appears if the dialog is too short). |
| MT-G05 | UIR-050 | Inspect Debug Logging control. | Dropdown OFF/ON, default OFF. |
| MT-G06 | UIR-053 | Click the Default Host Directory browse button, pick a folder. | A folder-select dialog appears; the chosen path populates the field. |
| MT-G07 | UIR-054 | Inspect the Viewer/Editor field. | Default `notepad $1`. |
| MT-G15 | UIR-115 | Click the Default Image Directory browse button, pick a folder. | A folder-select dialog appears; the chosen path populates the field. |
| MT-G08 | UIR-043 | Confirm there is **no** "Change Disk" field. | The withdrawn field is absent. |

---

## 7.1 Terminal configuration dialog

| ID | Req | Steps | Expected |
|----|-----|-------|----------|
| MT-G12 [visual] | FR-021c, UIR-003, UIR-103, UIR-103a, UIR-103d | Open **Config → Terminal**. | The Config menu lists, from the top, **New Config / Load Config / Save Config**, then a separator, then **Serial / Terminal / General / Remote / Language**. The Terminal item opens a modal, resizable dialog titled "Terminal Config" with two tabs — **Terminal** and **Macros**. The Terminal tab shows **Terminal Type** (VT100/VT52/ADM-3A, default VT100), **Local Echo** (default off), **Autoscroll** (default on), **End of Line**, and **Echo Transfer Data**. The Macros tab has a **tab per macro**, labelled **Macro 1 … Macro 10**; each has a **Label** field, a multi-line **Keystrokes** editor, and a **Test** button. |
| MT-G03 | UIR-047, UIR-048 | On the Terminal tab, inspect the **End of Line** drop-down. | Drop-down offering the mutually exclusive values CR / LF / CRLF; **CR** selected by default. |
| MT-G09 | UIR-058 | On the Terminal tab, inspect the **Echo Transfer Data** control. | Dropdown OFF/ON, default OFF. |
| MT-G12a | FR-021c, UIR-034, UIR-103b, UIR-103c | On the Terminal tab set Terminal Type = ADM-3A, tick Local Echo, untick Autoscroll; Save. Reopen the dialog. | The three values round-trip. With a config file loaded, only the terminal + macro settings (including End of Line and Echo Transfer Data) are written to it (serial/general/remote settings unchanged); with no file loaded a warning is shown and the change applies to the session only. |
| MT-G13 | FR-021b, FR-021c, UIR-098, UIR-103d | On the Macros tab, in Macro 1 set Label `Dir` and Keystrokes `SEND DIR`; in Macro 2 set Label `Reset` and Keystrokes `SENDRAW 03`. Save. Reopen the dialog. | The entered labels and keystroke scripts are shown verbatim after reopen and are written to the loaded config file along with the terminal settings. |
| MT-G14 [CP/M] | FR-162, UIR-098, UIR-103d | Connected, on the Macros tab type a script (e.g. `SENDRAW 0D`) into a slot's Keystrokes editor (need not be saved) and press its **Test** button. Then repeat with the Terminal Port **closed**. | Connected: the script runs on the Terminal Port (the remote responds — e.g. the drive prompt appears in the Terminal Window). Disconnected: a "Terminal port not connected" error dialog is shown and nothing is sent. |

---

## 7.2 Remote configuration dialog

| ID | Req | Steps | Expected |
|----|-----|-------|----------|
| MT-G20 [visual] | FR-021d, UIR-003, UIR-116, UIR-117 | Open **Config → Remote**. | Modal dialog titled "Remote Config". The fields are **ungrouped** (no group boxes) in a two-column form, in order: List Files, Receive from Remote (+ Test), Send to Remote (+ Test), Use XMODEM-1K, Receive from Remote (1K), Send to Remote (1K), Rename, Delete, Erase All, Xfer Launch Delay, Xfer Handshake Timeout, Xfer Inter-file Delay, Boot Sequence. The form sits in a **scrollable area** with the Save/Cancel row fixed below. |
| MT-G02 | UIR-042, UIR-045, UIR-046 | Inspect defaults / length limits of List Files, Receive from Remote, Send to Remote. | List Files default "DIR"; Receive default "PCPUT $1"; Send default "PCGET $1"; each limited to 79 characters. |
| MT-G21 | UIR-055, UIR-056 | Inspect the "Rename" and "Delete" fields. | Defaults `REN $2=$1` and `ERA $1`; labelled just "Rename"/"Delete" (no "Remote" suffix) and limited to 79 characters. |
| MT-G22 | UIR-089, UIR-090 | Inspect the **Use XMODEM-1K** checkbox and the two **(1K)** command fields. | Checkbox default OFF; "Receive from Remote (1K)" and "Send to Remote (1K)" both blank by default and limited to 79 characters. Ticking the box and reopening the dialog (after Save) shows it ticked. |
| MT-G04 | UIR-049, UIR-052, UIR-093 | Inspect Xfer Launch Delay, Xfer Handshake Timeout, and Xfer Inter-file Delay fields. | Launch Delay integer 0–60 default 3; Handshake Timeout integer 1–60 default 10; Inter-file Delay integer 0–60 default 2. |
| MT-G10 | UIR-059 | Inspect the "Boot Sequence" field (last in the dialog). Type a multi-line script (e.g. `WAITFOR Boot:` then `SEND ` then `WAIT 1`), Save, reopen the dialog. | A multi-line text editor labelled "Boot Sequence", empty by default, accepting several lines. After Save and reopen the entered text (newlines included) is shown verbatim. |
| MT-G11 [CP/M] | UIR-094, UIR-095, FR-161 | Connected, with a deliberately wrong Send to Remote command (e.g. "NOSUCHCMD $1") typed but **not yet saved**. Click the **Test** button beside it. Repeat with the correct default command. | Wrong command: after the handshake timeout, a dialog reports no response from the remote. Correct command: a dialog reports the remote responded. Neither run actually transfers a file (no new file appears on either side). Repeat both for the **Receive from Remote** Test button. |
| MT-G23 | FR-021d | With a configuration file loaded, change a remote field (e.g. List Files) and Save. Inspect the file. Then repeat with **no** file loaded. | With a file loaded, only the remote settings are written to it (serial/general/terminal settings unchanged); no file picker appears. With no file loaded a warning is shown and the change applies to the session only. |

---

## 8. Configuration load / save (real file dialogs)

| ID | Req | Steps | Expected |
|----|-----|-------|----------|
| MT-L01 | FR-010, IFR-004 | Config > Load Config. | A file-select dialog defaulting to JSON appears. |
| MT-L02 | FR-011, NFR-002 | Load `examples/RC2014_Z_Pro.json` (flat). Then hand-create a nested variant — wrap its serial keys in a `{"serial": {…}}` object, renaming `transport_port`→`transfer_port`, `data`→`data_bits`, `stopbits`→`stop_bits` — and load that. | Each load **fully replaces** the settings store; both shapes are accepted; serial settings normalise (Connect works with either). |
| MT-L03 | FR-012 | Hand-edit a config to add an unknown key (e.g. `"foo": 123`), load it, then Save to a new file. | App accepts the file (no rejection); the unknown key survives verbatim in the saved output and does not change behaviour. |
| MT-L04 | FR-017 | Update to populate the Remote list, then Config > Load Config any config. | Remote Files list is **cleared** on load. |
| MT-L05 | FR-013, FR-014 | Config > Save Config to a new path; reopen the file in a text editor. | JSON file written with the **entire** settings store — all current serial + general settings (the full-store save, as opposed to the per-group dialog saves MT-L13/MT-L14). |
| MT-L06 | FR-006, FR-010, FR-013 | Save into folder X; then Config > Load Config. | The Load dialog opens in folder X (the last-used **config** folder), independent of the Host directory. |
| MT-L07 | FR-005 | Load a config, then fully quit and relaunch (`cpm-fm`). | On next start the app auto-reloads and applies that same config file. |
| MT-L08 | FR-005, FR-003 | After MT-L07, delete or rename the remembered config file, relaunch. | App starts **unconfigured** (no crash) because the remembered file no longer parses/exists. |
| MT-L09 | FR-018, FR-019 | Load a config (so a file is remembered), connect, Update, then File > **New**. | Current config is saved to the remembered file; ports closed (disconnect behaviour); Remote list cleared; settings replaced with defaults; remembered path forgotten; Host list refreshed to the default directory. |
| MT-L10 | FR-018 | With **no** remembered file, Config > New Config. | A Save dialog appears first; choosing a file then resets to defaults; **cancelling** the Save dialog cancels New entirely (config, ports, lists retained). |
| MT-L11 | FR-125, UIR-005 | Launch unconfigured, then Config > Load Config `examples/RC2014_Z_Pro.json`. | Before loading, the title bar reads **CP/M File Manager** alone; after loading it reads **CP/M File Manager — RC2014_Z_Pro** (file base name only — no path, no `.json`). |
| MT-L12 | FR-125 | After MT-L11, File > **New**. | The title bar reverts to **CP/M File Manager** alone (the config name is dropped). |
| MT-L13 | FR-020a | Load a config file. Open Config > **Serial**, change a serial value (e.g. Speed), and press **Save**. Reopen the loaded file in a text editor. | **No** Save dialog appears. The serial value is updated in the file; every general setting in the file (List Files, EOL, Host Directory, etc.) is **unchanged**. Status bar confirms the serial settings were saved. |
| MT-L14 | FR-021a | Load a config file. Open Config > **General**, change a general value (e.g. EOL), and press **Save**. Reopen the loaded file in a text editor. | **No** Save dialog appears. The general value is updated in the file; every serial setting in the file (ports, speed, parity, etc.) is **unchanged**. Status bar confirms the general settings were saved. |
| MT-L15 | FR-020a, FR-021a | Launch **unconfigured** (or Config > New Config so no file is loaded). Open Config > Serial (or General), change a value, and press **Save**. | A **warning** dialog states no configuration file is loaded and that Config > Save Config must be used to persist; **no file is written**. The change still takes effect for the running session (e.g. Connect uses the new serial value). |

---

## 9. Host file management

| ID | Req | Steps | Expected |
|----|-----|-------|----------|
| MT-H01 | FR-060 | Launch with a config whose Default Host Directory points at your scratch folder. | Host Files list shows that folder's files at startup. |
| MT-H02 | FR-061, FR-062 | Press **Change Directory**, pick a different folder. | Folder-select dialog appears; Host Files list reloads from the chosen folder (session-only; not written to the config until Save). |
| MT-H03 [CP/M] | FR-063 | Connect; populate the Remote list; then press the Host Files group's **Update** button (beside **Change Directory**). | Only the Host list refreshes; the Remote list is left untouched (this button acts on the Host list **only**). |
| MT-H04 | FR-126, UIR-011 | Observe the Host Files group title. Then **Change Directory** to a folder with a **long** absolute path, then narrow the window. | The group title reads **Host Files — `<current directory>`**, tracking the directory each time it changes. When the path is too wide for the group, its **leading** portion is replaced by `…` while the trailing (most specific) part stays visible; narrowing the window elides more, widening it reveals more. |

---

## 9.1 File list filter & sort  **[visual]**

Applies to **both** panes; the filter/sort core is unit-tested (`tests/test_file_filter.py`,
`tests/test_gui_smoke.py`) — these cases confirm the live wiring and on-screen behaviour. Host-pane
cases need only a populated Host Files list; the remote-pane case (MT-FS08) needs a remote listing
(**[CP/M]**). Use a scratch host folder containing a mix such as `A.TXT`, `b.txt`, `C.COM`, `D.COM`,
`LICENSE` (extensionless).

| ID | Req | Steps | Expected |
|----|-----|-------|----------|
| MT-FS01 | FR-130, FR-131, UIR-079 | In the Host filter field type a substring (e.g. `txt`). Then press the inline **×** (clear) button. | While typing, the list narrows to names containing `txt` (case-insensitive); the rest are hidden. Clearing restores the full list. |
| MT-FS02 | FR-131 | Type a wildcard pattern, e.g. `*.COM`, then `?.TXT`. | `*.COM` shows only the `.COM` files; `?.TXT` matches single-character base names ending `.TXT` (whole-name glob, anchored — a bare `TXT` would instead match as a substring). |
| MT-FS03 | FR-131 | Type quickly then pause. | The list updates shortly after you stop typing (≈150 ms debounce), not jerkily on every keystroke; no perceptible lag. |
| MT-FS04 | FR-132, UIR-080 | Use the **sort** drop-down to pick **Name**, then **Extension**; click the direction (`↑`/`↓`) button. | Name sorts alphabetically (case-insensitive); Extension groups by extension (extensionless first) with name as tie-breaker. The arrow flips `↑`↔`↓` and the order reverses accordingly. |
| MT-FS05 | FR-133 | Set a filter (e.g. `*.COM`) **and** a sort (Extension, descending). | The displayed files are the filtered subset, shown in the chosen sort order — filter applied first, then sort. |
| MT-FS06 | FR-135, UIR-079 | Type any non-empty filter, then clear it. | A clear visual indicator (coloured border on the field) shows while the filter is active; it disappears when the field is empty. |
| MT-FS07 | FR-134 | Set distinct filter text and sort settings on the **Host** and **Remote** panes. Close the app and relaunch. | Each pane reopens with its own last-used filter text, sort key, and direction restored independently. |
| MT-FS08 [CP/M] | FR-135 | With a remote listing shown, type a filter in the **Remote** filter. Then Disconnect (or Config > Load Config / Config > New Config). | The remote list clears on disconnect/load/new and stays empty — changing the remote filter afterwards does **not** resurrect the old (stale) entries. |
| MT-FS09 | UIR-080, FR-123 | Switch the GUI language (Config > Language). | The filter placeholder/tooltip and the sort drop-down options (**Name**/**Extension**) appear in the new language; the sort still works (the underlying keys are unchanged). |

---

## 9.2 CP/M disk image support

The read/geometry/detection core is unit-tested (`tests/test_disk_image/`, `tests/test_gui_smoke.py`);
these cases confirm the live menu wiring and on-screen behaviour. You need one real CP/M disk image
whose size matches a bundled geometry (e.g. an IBM-3740 8-inch image of 256256 bytes, or an RC2014
CompactFlash image), plus any non-disk file to use as the "foreign" input.

| ID | Req | Steps | Expected |
|----|-----|-------|----------|
| MT-DI01 | FR-169, UIR-108 | Choose **File → Open Disk Image…** and select a valid CP/M image. | The File menu contains **Open Disk Image…** (after **Save**). After selecting, the Host Files list shows the files contained in the image, and the Host Files group title changes to the temporary working directory. |
| MT-DI02 | FR-170 | Open an image whose size matches exactly one bundled geometry. | No geometry dialog appears; the status bar reports the image loaded and names the detected geometry. |
| MT-DI03 | FR-170 | Open an image whose size matches no bundled geometry (or is genuinely ambiguous). | A **Select Disk Geometry** dialog lists candidate formats (or all formats when none matched); picking one proceeds, **Cancel** aborts with the Host pane unchanged. |
| MT-DI04 | FR-171 | After MT-DI01, select one or more listed files and **Copy to Remote** (or drag-and-drop) to a connected CP/M machine. **[CP/M]** | The files transfer over X-Modem exactly as any host file would — the extracted files behave as ordinary files on disk. |
| MT-DI05 | FR-172 | Choose **File → Open Disk Image…** and select a non-CP/M file (e.g. a text file or a truncated image). | An error dialog reports the file could not be read as a CP/M disk image; the current Host pane is left unchanged (no crash). |
| MT-DI06 | FR-171 | After opening an image, move the Host pane off it: choose **Config → New Config**, **Load** a different configuration, use **Change Directory**, open a second image, or exit. | The previous temporary working directory is discarded each time and no stale image contents remain — **Image Details…** greys out again — while the Host pane repaints to the new directory. |
| MT-DI07 | FR-173, UIR-109 | After MT-DI01, choose **File → Image Details…**. | A read-only dialog opens with one row per file and the columns **Name**, **Size**, **User**, **Attributes** (R/S/A shown for flagged files, a dash otherwise). Closing it leaves the Host pane unchanged. |
| MT-DI08 | FR-173, UIR-109 | With no image open (e.g. right after **Config → New Config**), inspect the File menu. | **Image Details…** is present but greyed out (disabled); it becomes enabled only after an image is opened. |
| MT-DI10 | FR-174, DR-050 | With writing enabled and an image open (MT-DI01), optionally add or delete files in the Host working directory, then choose **File → Save Image…** and save to a **new** file name. Re-open that new file with **Open Disk Image…**. **[CP/M]** | A new image file is written (the source image is untouched — choosing the source path is refused with a warning). Re-opening it lists exactly the working-directory files with their content intact. If used on real hardware, the written image mounts and boots as the original did (boot tracks preserved). A too-full working directory (more/larger files than the geometry holds) or an invalid CP/M name aborts with an explanatory error and writes nothing. |
| MT-DI11 | FR-175 | With writing enabled and an image open (MT-DI01), **Copy to Host** one or more files from a connected CP/M machine into the Host pane, then **File → Save Image…** to a new file and re-open it. **[CP/M]** | The Host Files list shows the received files alongside the image's originals; the saved (and re-opened) new image contains both the originals and the received files — a file copied back from the remote is staged into the image and written on save (copy-to-image). |
| MT-DI12 | FR-175, UIR-111 | With writing enabled, open an image and make a change to the Host working directory (copy a file in, or add/delete one). Then try to leave it: **Config → New Config**, **Load** another config, **Change Directory**, open a second image, or exit the app. Try **Cancel**, **Discard** and **Save** on the prompt. | While an image is open the Host Files group title names the image file (not a temp path). Each leave attempt raises a **Save / Discard / Cancel** dialog. **Cancel** keeps the image open and aborts the action; **Discard** proceeds and drops the changes; **Save** opens the Save-As dialog and, once saved to a new file, proceeds. With writing off, or with no unsaved changes, no prompt appears. |
| MT-DI13 | FR-176, UIR-112 | Choose **File → Open Disk Image…**; in the mount-side dialog pick **Remote pane** and open an image. With writing enabled, select Host files and press **Copy to Remote**; then select image files and press **Copy to Host** (also try drag-and-drop each way). Save the image and re-open to confirm. **[no CP/M needed]** | The mount-side dialog offers Host/Remote (default Host). With Remote chosen: the image's files appear in the **Remote** pane (the drive drop-down is disabled and the Remote group title names the image), while the Host pane stays on its real folder. Copy to Remote stages the selected Host files into the image (a non-8.3 name prompts to rename; an existing name prompts Overwrite/Skip/Cancel); Copy to Host writes the selected image files into the host folder (no 8.3 prompt). Copies are instant (no serial progress dialog). Saving and re-opening shows the staged files. If you open a Remote-side image immediately after a Host-side image (without closing it first), the Host pane returns to a real folder rather than being left on a stale temporary path (v2.33.1). |
| MT-DI14 | FR-176 | While connected to a CP/M machine, open an image and choose **Remote pane**. Separately, mount an image Remote-side while disconnected, then press **Connect**. **[CP/M]** | Choosing Remote-pane while connected is refused with a message (disconnect first). Pressing Connect while a Remote-pane image is mounted is refused with a message (close the image first). Closing the image (Config → New Config, etc.) restores the Remote pane to the live device, re-enables the drive drop-down, and clears the image listing. |
| MT-DI16 | FR-178, UIR-114 | Choose **File → New Disk Image…**; pick a geometry and a mount pane (try both Host and Remote). Copy some files in (Copy to Remote for a Remote-side new image, or drag/Copy to Host from a device for a Host-side one), then **File → Save Image…** and re-open the saved file. **[no CP/M needed for the Remote-side path]** | **New Disk Image…** is always available (no enable step). Creating one asks for a disk format then the mount pane, and opens an **empty** image (the pane shows no files; the group title reads "(new image)"). Files copied in appear; the first **Save Image…** asks where to save, and from then on the image is named after that file (the title shows the file name and the unsaved-changes prompt no longer says "(new image)"). Re-opening the saved file lists the copied files. |
| MT-DI17 | FR-176, FR-179 | Set a **Default Image Directory** distinct from the host directory in **Config → General** and **Save Config**; reopen the app / reload the config. Open an image in the **Remote** pane, then use **Change Directory** to move the Host pane elsewhere. **[no CP/M needed]** | Open/New/Save Image dialogs browse the image directory, not the host folder; the two are tracked independently, and the image directory is remembered across Save Config/reload. Changing the host directory while an image is mounted in the Remote pane moves only the Host pane — the image stays in the Remote pane. |
| MT-DI18 | FR-174 | Rename check: the **Config** menu's first three items read **New Config / Load Config / Save Config**. Open an image, change a file, and **File → Save Image…**. Then create a new image and Save it. **[no CP/M needed]** | The menu items are relabelled. Saving an image that already has a file overwrites that file in place with no dialog (like any document save); saving a brand-new image asks once for a filename. There is no "enable disk image writing" setting anywhere. |
| MT-DI19 | FR-180 | Open an image in the **Remote** pane. Press **Backup** (remote→host), then **Restore** (host→remote), confirming each prompt. **[no CP/M needed]** | Backup copies every file from the image into the host folder (emptying the host folder first); Restore copies every host file into the image (emptying the image first). Both are instant local copies with the usual destructive-operation confirmation and no serial activity. (Host-side image + a connected CP/M machine still backs up/restores over serial as before.) |
| MT-DI15 | FR-177, UIR-113 | With an image open, choose **File → Close Disk Image…**. Try it (a) with a Host-side mount after **Change Directory** to a folder of your choice then opening the image; (b) with a Remote-side mount; and (c) with writing enabled and unsaved changes staged. **[no CP/M needed]** | **Close Disk Image…** is greyed out until an image is open. Closing a Host-side image discards the temporary folder and returns the Host pane to the directory that was showing **before** the image was opened. Closing a Remote-side image clears the Remote list, re-enables the drive drop-down, and restores the Remote group title (the Host pane is unaffected). With unsaved changes it first shows the **Save / Discard / Cancel** prompt; **Cancel** leaves the image open. After closing, the item is greyed out again. |
| MT-DI20 | FR-185, FR-186, UIR-119 | Open an image that has files in more than one user area (and, if available, the **same** filename in two areas). **[no CP/M needed]** | Each row in the pane shows the file's user area as a leading field (e.g. `U3  GAME.COM`); every area's files are listed at once. A name that exists in two areas appears twice (the second staged under a disambiguated host name, e.g. `FOO~3.COM`) with the correct per-area content — neither is lost. **Image Details…** shows the matching per-file user numbers. |
| MT-DI21 | FR-187, FR-188 | (a) Open such an image **Host-side** with a connected CP/M machine and **Copy to Remote** a file that lives in area 3; check the remote under `USER 3`/`USER 0`. Same precondition as MT-R11 (transfer utility reachable from area 3, i.e. SYS in user 0). **[CP/M]** (b) Open it, save it to a new file, and re-open the saved file. **[no CP/M needed]** | (a) With `image_area_mode` = `match` (default) the file arrives in the remote's area **3**, not area 0 (resolving issue #7) — subject to the utility being reachable from area 3; otherwise the transfer fails per FR-183. Set `image_area_mode` = `selected` and it instead goes to the Remote pane's selected area. (b) The saved/re-opened image preserves every file's original user area with **no** such limitation (write-back is local, area-aware, not forced to area 0). |
| MT-DI22 | FR-189, UIR-120 | Open an image that has files in more than one user area (in either pane). A **user-area filter** drop-down appears in that pane's filter/sort row (it is absent for a real host/remote directory). Select an area (e.g. `U3`), then choose **All**. Combine it with a name filter. Close the image. **[no CP/M needed]** | The drop-down lists **All** plus only the areas actually present in the image. Selecting `U3` shows only the area-3 files; **All** shows every area again. It narrows on top of the name filter/sort. The drop-down disappears (and its selection resets) when the image is closed. Selecting an area changes only what is shown — it does not move or transfer any file. |

---

## 10. Remote listing & drive selection (live)  **[CP/M]**

Preconditions: connected to a CP/M peer with files on at least drive `A:`.

| ID | Req | Steps | Expected |
|----|-----|-------|----------|
| MT-R01 | FR-073, FR-075..079 | Select the current drive in the drop-down and press **Update** (or just press Update). | List command sent over Terminal Port; after the capture wait the Remote Files list fills with filenames **sorted ascending**; status bar shows "Remote file list updated". |
| MT-R02 | FR-074, FR-104 | With the Terminal Port **closed**, press Update / select a drive. | Status bar: "Terminal port not connected - cannot read file list"; Remote list cleared; no hang. |
| MT-R03 | FR-076 | Time a list refresh against a directory that prints slowly / in bursts. | The app waits ≥1 s, keeps waiting until output is idle ~0.5 s, and caps at ~10 s — no truncated listing for a slow directory. |
| MT-R04 | FR-077, FR-078, DR-013 | List a drive containing an **extensionless** file and a **single-file** directory (if available). | Extensionless names appear without a trailing dot; a lone file still shows. (Parsing logic itself is unit-tested; this confirms the live capture feeds it correctly.) |
| MT-R04a [QPM] | FR-077, DR-007, DR-016 | Connect to a **QPM** peer (e.g. QPM 2.71) and press **Update**. QPM's `DIR` output has no drive prefix and embeds the extension dot (e.g. `INFO    .COM : ASM     .COM : AUTOEXEC.QSB`). | The Remote Files list populates with every file (`INFO.COM`, `ASM.COM`, `AUTOEXEC.QSB`, …) — the QPM listing is parsed correctly, not left empty. Copy to Host of a listed file then succeeds. (Parsing logic is unit-tested; this confirms the live QPM capture feeds it correctly.) |
| MT-R05 | FR-100, FR-102 | Select a different existing drive (e.g. `B:`) from the drop-down. | App sends `B:`; on seeing the `B>` prompt it lists that drive exactly as Update does. |
| MT-R06 | FR-103 | Select a drive letter that does not exist on the remote. | Remote list cleared; a modal OK dialog "Drive `<letter>`: not found" (e.g. "Drive B: not found"). |
| MT-R07 | FR-073 (OI-22) | In the Terminal Window type `A:` to change the remote drive directly; then in the main window, with `C:` shown in the drop-down, press Update. | Update first switches the remote to the **displayed** drive (`C:`) and lists that — the list matches the drop-down, not the drive typed in the terminal. |
| MT-R10 | FR-181, FR-182, UIR-118 | On a drive that has files in more than one user area, select a non-zero area (e.g. `3`) from the **user-area drop-down** (beside the drive drop-down). Then select area `0` again. | The app sends `USER 3` and re-lists — only that area's files show; selecting `0` re-lists area 0. On a ZCPR peer the prompt shows the area (`A3>`); on plain CP/M 2.2 the prompt is unchanged but the listing still reflects the area. |
| MT-R11 | FR-183, FR-184 | With user area `3` selected, **Copy to Remote** a host file, then in the Terminal Window run `USER 3` + `DIR` and `USER 0` + `DIR`. **Precondition:** the transfer utility (`PCGET`) must be reachable from area 3 — i.e. a **SYS file in user 0** — otherwise the launch fails (expected per FR-183). | The file arrives in area **3** (visible under `USER 3`, absent under `USER 0`) — the transfer set the area before launching the CP/M receiver. The tracked area starts at 0 on Connect. If the utility is not reachable from area 3, the transfer instead fails with the "No response from remote — check the … command" message (the documented best-effort limitation). |
| MT-R12 | FR-159, FR-183 | Force a non-zero-area transfer to fail: select a **non-zero** user area (e.g. `3`) whose transfer utility is **not** reachable from it (utility not present there and not SYS in user 0), then **Copy to Remote** a host file. (Or temporarily set a bogus Send to Remote command while in area 3.) | The error dialog now **names the user area** — e.g. "No response from remote for `X` in user area 3 — the Send to Remote command may not be reachable from user area 3 …" — rather than only pointing at the command config. Repeat in area **0**: the message is the original "check the Send to Remote command" wording with no user-area mention (the area-0 path is unchanged). |

---

## 11. File transfers (live X-Modem)  **[CP/M]**

Preconditions: connected (both Terminal and Transport flags set); `PCGET`/`PCPUT` available on the
CP/M side. Use the multi-block (≥1 KB) file plus small files from §2.3.

| ID | Req | Steps | Expected |
|----|-----|-------|----------|
| MT-T01 | CR-010, FR-080 | With Transport **not** connected, press Copy to Remote / Copy to Host. | Error dialog body "Transport port not connected"; no transfer starts. |
| MT-T02 | FR-106 | Connected, but **no** file selected, press Copy to Remote / Copy to Host. | Warning "Please select one or more files to upload" / "…to download"; no transfer. |
| MT-T03 | FR-081..083, FR-087, FR-089, FR-099 | Select one host file; **Copy to Remote**. | `PCGET <name>` issued on Terminal Port; after the launch delay the X-Modem send runs on the Transport Port; on success the **Remote** list auto-refreshes and the file appears there. Verify the file on the CP/M side opens/types correctly (content integrity). |
| MT-T04 | FR-081..083, FR-087, FR-099 | Select one remote file; **Copy to Host**. | `PCPUT <name>` issued; X-Modem receive runs; on success the **Host** list refreshes and the file appears; downloaded content matches the original (binary-compare for the binary file). |
| MT-T05 | FR-105, UIR-051 | During MT-T03/T04 watch the progress dialog. | Modal dialog titled "Sending File"/"Receiving File"; shows the filename, a live Blocks/Bytes count that increments per block, and a progress bar (tracking bytes on send; indeterminate on receive); a centred **Cancel** button (FR-120) is present but **no** window close (X) control; auto-closes on completion. |
| MT-T06 | FR-106, FR-107, FR-105 | Multi-select three host files; Copy to Remote. | Files transfer **sequentially in list order**, each with its own `PCGET`; a **single** progress dialog serves the batch and shows "File i of N"; on success the Remote list refreshes once. |
| MT-T07 | FR-108 | In a 3-file batch, arrange for the middle file to fail (e.g. abort it on the CP/M side / disconnect briefly). | Batch aborts (third file not attempted); error dialog names the failed file; because file 1 succeeded, the destination list refreshes once. |
| MT-T08 | FR-109 | Run a multi-file batch and watch the Terminal Window between files, and note the auto-refresh after the last file. | Before each file **after the first**, the app waits for the CCP prompt to return plus the inter-file settle delay; the second/third launch commands are not truncated ("command not found"). **After the final file, the app waits the inter-file settle delay before the auto-refresh `DIR`, so the just-transferred file(s) reliably appear in the refreshed Remote list even on a slow CP/M peer (no missing entry that only shows on a manual Update).** |
| MT-T09 | FR-086, UIR-058 | With Echo Transfer Data **OFF** (default), open the Terminal Window, then run a transfer. Then set Echo Transfer Data **ON** (Config > General) and run another transfer. | OFF: no `<HH>` tokens appear during the transfer (other terminal traffic is unaffected). ON: every byte sent/received on the Transport Port is echoed into the Receive area as `<HH>` hex tokens (uppercase two-digit). |
| MT-T10 | NFR-003c, NFR-003f, NFR-003h | Transfer to/from a 1K-capable sender (e.g. PCPUT1K) and a checksum-only sender (PCPUT V1.0). | Receive polls **NAK first** (no stray `C`); 1K (STX) frames accepted from 1K senders; final packet padded with 0x1A. Content round-trips intact. |
| MT-T11 | NFR-001 | During a large transfer, move/resize the main window and hover the toolbar. | UI stays responsive (transfer runs off the GUI thread); progress keeps updating. |
| MT-T12 | FR-119 | Right-click a single host file → **To Remote**; right-click a single remote file → **To Host**. | Each transfers just that one file exactly as the corresponding Copy button (progress dialog, refresh on success); with Transport disconnected, "Transport port not connected" and no transfer. |
| MT-T13 | FR-120, NFR-003m | Start a transfer of the multi-block (≥1 KB) file (either direction); while the progress dialog shows blocks incrementing, press **Cancel**. (Open the Terminal Window first to watch the byte echo.) | The Cancel button disables and shows "Cancelling…"; the transfer aborts promptly; the CAN sequence is sent (visible as `<18>` tokens in the Terminal Window — MT-T09) and the CP/M program reports an abort; the progress dialog closes; the status bar shows a "Transfer cancelled" message; **no** error dialog appears. |
| MT-T14 | FR-120 | Multi-select three files; start the batch; press **Cancel** during the **second** file (so file 1 already completed). | Remaining files are skipped (third never launched); the dialog closes with a cancellation status; because file 1 completed, the destination list refreshes once; on a cancelled **Copy to Host**, no partially-received file is left in the host folder. |
| MT-T15 | FR-159, FR-160 | Connected. Temporarily set Send to Remote (Config > General) to a wrong command (e.g. "NOSUCHCMD $1"); Copy to Remote. Repeat with Receive from Remote set wrong; Copy to Host. | Well under the old 60s, an error dialog reports "No response from remote for `<name>` - check the Send to Remote / Receive from Remote command in Config > General" — distinct from the generic "Transfer failed" wording. Restoring the correct command and retrying succeeds normally. |
| MT-T16 [CP/M] | FR-106a | Multi-select a normal file **and** a zero-byte host file, then Copy to Remote. | The zero-byte file is **skipped**: a status message notes it (e.g. "Skipped EMPTY.TXT: zero-byte files are not sent to the remote") and it is recorded as *skipped* in the transfer history; the batch **continues**, so the normal file transfers and the sequence neither stalls nor aborts. The normal file's transfer **starts promptly** — right after the configured launch delay — not after a multi-second wait. |

---

## 11.1 Drag-and-drop file transfer  **[CP/M]**

Drag-and-drop is an alternative trigger for the same Copy to Remote / Copy to Host transfers (§11), so
the transfer mechanics themselves are covered by §11 and the unit tests (`tests/test_gui_smoke.py`).
These cases confirm the live drag/drop wiring, the drop-zone highlight, the confirmation step, and the
guard rails. The decode/handoff logic is unit-tested; MT-D03..D06 need a connected CP/M peer (**[CP/M]**).

| ID | Req | Steps | Expected |
|----|-----|-------|----------|
| MT-D01 | FR-136, FR-139, UIR-081 | Connected, select one or more **Host** files and drag them; hover over the **Remote** pane, then over the **Host** pane (the source). | While dragging over the Remote pane it shows a green drop-zone border; hovering back over the originating Host pane shows **no** highlight (a same-pane drop is rejected). The source files are never moved/removed. |
| MT-D02 | FR-138, FR-139 | From the OS file manager (Explorer/Finder), drag one or more files over the **Remote** pane, then over the **Host** pane. | The Remote pane highlights as a valid drop zone; the Host pane does **not** accept the external files (no highlight). |
| MT-D03 [CP/M] | FR-137, FR-080, CR-010 | Select Host file(s) and **drop them onto the Remote pane**; confirm the dialog. | A "Confirm Transfer" dialog asks to copy N file(s) to the remote, with **Cancel** (far left) and **OK** (far right) per UIR-075; on **OK** the files transfer exactly as Copy to Remote (progress dialog, sequential, Remote list refreshes). On **Cancel**, nothing transfers. With Transport disconnected, the drop instead shows "Transport port not connected" and starts no transfer. |
| MT-D04 [CP/M] | FR-137 | Select Remote file(s) and **drop them onto the Host pane**; confirm. | "Confirm Transfer" asks to copy N file(s) to the host (Cancel left, OK right); on **OK** they transfer exactly as Copy to Host (progress dialog; Host list refreshes); on **Cancel**, nothing transfers. |
| MT-D05 [CP/M] | FR-138 | Drag file(s) from the OS file manager and **drop them onto the Remote pane**; confirm. | The dropped files (by their real OS paths, even outside the current host directory) transfer to the remote as Copy to Remote. |
| MT-D06 [CP/M] | FR-137 | Drag Host file(s) onto the Remote pane but click **Cancel** / press Esc on the confirmation. | No transfer starts; no progress dialog appears; the lists are unchanged. |

---

## 11.2 Transfer history  **[CP/M for live transfers]**

The transfer-history store and the dialog's list/filter/clear/re-transfer wiring are unit-tested
(`tests/test_transfer_history.py`, `tests/test_gui_smoke.py`). These cases confirm the on-screen
dialog, the real `~/.cpm_fm_history.json` persistence across sessions, the real Export file, and a
live re-transfer round-trip (**[CP/M]**).

| ID | Req | Steps | Expected |
|----|-----|-------|----------|
| MT-TH01 [CP/M] | FR-140, FR-142, UIR-082 | Do a couple of transfers (one each direction; let one fail if you can, e.g. by cancelling). Then click the toolbar **History** button. | The Transfer History dialog opens, listing one row per transferred file, **newest first**, each showing its time, file name, direction (To Remote / To Host), status (Success / Failure / Cancelled), size, and any error. |
| MT-TH02 | FR-143, UIR-083 | In the dialog, use the **Direction** filter (To Remote / To Host) and the **Status** filter (Success / Failure / Cancelled / Skipped), then set both back to **All**. | The table narrows to rows matching the chosen direction and/or status (including **Skipped** for files declined at a conflict); **All** restores the full list. |
| MT-TH03 | FR-143 | Click **Export**, choose a path, and save. Open the resulting file. | A `.json` file is written containing the history entries (the same fields shown in the table). |
| MT-TH04 | FR-143 | Click **Clear** and confirm the prompt. | After confirming, the table empties and the history is cleared (the file holds an empty list); clicking **No**/Cancel on the prompt leaves it untouched. |
| MT-TH05 | FR-141 | Do a transfer, close the app, relaunch, and open **History**. | The earlier transfers are still listed — the history persists across sessions (in `~/.cpm_fm_history.json`). |
| MT-TH06 [CP/M] | FR-144, FR-080 | Select a **success** upload entry whose source host file still exists and click **Re-transfer**; confirm any prompt. | The History dialog closes, the transfer re-runs exactly as Copy to Remote (progress dialog; list refreshes), and a **new** history entry appears marked as a retry. With Transport disconnected, Re-transfer instead reports "Transport port not connected" and starts nothing; if the source file is gone, it reports a "file not found" error and starts nothing. |

---

## 11.3 File-conflict prompt on transfer  **[CP/M]**

When a file being transferred already exists at the destination the app prompts with a standard
Overwrite / Skip / Cancel dialog plus an "apply to all remaining conflicts" option (FR-145–FR-147,
UIR-084). Detection differs by direction: a download checks the host folder; an upload refreshes the
remote `DIR` listing first. The policy/skip/cancel logic is unit-tested (`tests/test_conflict_resolution.py`);
these cases confirm the live dialog and the real overwrite/skip/refresh behaviour.

| ID | Req | Steps | Expected |
|----|-----|-------|----------|
| MT-CF01 [CP/M] | FR-145, FR-146, UIR-084 | Ensure a file named `FOO.TXT` exists on the **host**. Select `FOO.TXT` on the **Remote** pane and Copy to Host. | Before receiving, a modal **"File Exists"** dialog names `FOO.TXT`, states it already exists at the host directory, and offers **Overwrite**, **Skip**, **Cancel**, and an "Apply to all remaining conflicts" checkbox. It has no window close (X) control. |
| MT-CF02 [CP/M] | FR-146 | At the MT-CF01 prompt, click **Overwrite**. | The transfer proceeds and the host file is replaced with the downloaded version; the Host list refreshes; a **success** history entry is recorded. |
| MT-CF03 [CP/M] | FR-146 | Trigger the prompt again and click **Skip**. | The existing host file is left untouched (unchanged contents/timestamp); the batch continues with the next file; a **skipped** history entry is recorded for the skipped file. |
| MT-CF04 [CP/M] | FR-145 | Ensure a file `BAR.TXT` exists on the **remote** drive (check via Update). Select host `BAR.TXT` and Copy to Remote. | The app first refreshes the remote listing, detects the existing remote `BAR.TXT`, and shows the conflict prompt naming it (destination wording = the remote system). Overwrite proceeds (PCGET overwrites); Skip leaves it and records skipped. |
| MT-CF05 [CP/M] | FR-147 | Multi-select several files that **all** already exist at the destination. At the first prompt, tick **"Apply to all remaining conflicts"** and click **Skip** (then repeat the run choosing **Overwrite**). | Only **one** prompt appears; the chosen action is applied automatically to every remaining conflict (all skipped, or all overwritten) with no further prompts. Skipped files get skipped history entries; overwritten files get success entries. |
| MT-CF06 [CP/M] | FR-146, FR-120 | In a multi-file batch with conflicts, at a conflict prompt click **Cancel** (or close the dialog via the window manager). | The whole batch aborts immediately like the transfer Cancel (FR-120): no further files are transferred; the progress dialog closes; the status bar shows a cancellation message; no error dialog. |
| MT-CF07 [CP/M] | FR-145 | Copy to Host / Copy to Remote a file whose name does **not** exist at the destination. | **No** conflict prompt appears; the transfer proceeds directly as before. |

---

## 11.4 Host→remote filename validation  **[CP/M]**

Before each host→remote upload the app checks the file's name against the CP/M 8.3 convention
(FR-148, DR-046) and, if it does not conform, prompts to **Rename / Skip / Cancel** (FR-149, UIR-085).
The validation, suggestion, and batch handling are unit-tested (`tests/test_filename_validation.py`);
these cases confirm the live dialog and the real upload-under-new-name behaviour. To create a
non-conforming host file, use a name with a space or an over-length base/extension (e.g.
`bad name.txt` or `longfilename.text`).

| ID | Req | Steps | Expected |
|----|-----|-------|----------|
| MT-FV01 [CP/M] | FR-148, FR-149, UIR-085 | Select a host file whose name does **not** meet CP/M 8.3 (e.g. `bad name.txt`) and Copy to Remote. | Before uploading, a modal **"Invalid CP/M File Name"** dialog names the file, explains the 8.3 convention, shows an editable field pre-filled with a conforming suggestion (e.g. `BADNAME.TXT`), and offers **Rename**, **Skip**, **Cancel**. It has no window close (X) control. |
| MT-FV02 [CP/M] | FR-149 | At the MT-FV01 prompt, edit the field to a **valid** 8.3 name and click **Rename**. | The dialog closes and the file is uploaded to the remote under the entered name (verify via Update on the Remote pane); a **success** history entry is recorded under the new name. |
| MT-FV03 | FR-149 | At the prompt, type an **invalid** name (e.g. `still bad.text`) and click **Rename**. | The dialog stays open and shows an inline error; no transfer starts until a valid name is entered (or Skip/Cancel chosen). |
| MT-FV04 [CP/M] | FR-149, FR-142 | In a multi-file batch, at an invalid-name prompt click **Skip**. | The offending file is not uploaded; the batch continues with the next file; a **skipped** history entry is recorded for it. |
| MT-FV05 [CP/M] | FR-149, FR-120 | At an invalid-name prompt click **Cancel** (or close via the window manager). | The whole batch aborts immediately like the transfer Cancel: no further files upload; the progress dialog closes; the status bar shows a cancellation message; no error dialog. |
| MT-FV06 [CP/M] | FR-148 | Copy to Remote a host file whose name **already** meets CP/M 8.3 (e.g. `GOOD.TXT`). | **No** validation prompt appears; the upload proceeds directly. |
| MT-FV07 [CP/M] | FR-149, FR-145 | Rename an invalid-named upload to a name that **already exists** on the remote drive. | After Rename, the normal **"File Exists"** conflict prompt (UIR-084) appears for the new name; Overwrite/Skip/Cancel behave as in §11.3. |

---

## 11.5 Whole-drive backup and restore  **[CP/M]**

Two toolbar actions mirror every file between the remote drive and the host directory as a single
destructive operation: **Backup** copies the whole remote drive to the host (remote→host); **Restore**
copies the whole host directory to the remote drive (host→remote). Each first refreshes the destination
listing, then warns that ALL files at the destination will be deleted and re-written and requires
confirmation; on Continue it deletes every file at the destination and copies every file from the
source, reusing the normal batch-transfer progress dialog and Cancel (FR-150–FR-154, UIR-086–UIR-088).
The orchestration, wipe helpers, and confirmation slot are unit-tested (`tests/test_backup_restore.py`);
these cases confirm the live destructive behaviour. **Use scratch folders/drives with disposable
files** — these tests delete data by design.

| ID | Req | Steps | Expected |
|----|-----|-------|----------|
| MT-BR01 [CP/M] | FR-150, FR-152, UIR-088 | With both ports connected and the host folder + remote drive each holding a few different files, press **Backup**. | The Remote pane refreshes (source) and the Host pane refreshes (destination); then a modal **"Confirm Backup"** dialog warns that ALL files in the host directory will be deleted and replaced, with **Continue** and **Cancel** (Cancel default). No deletion has happened yet. |
| MT-BR02 [CP/M] | FR-152 | At the MT-BR01 prompt, press **Cancel** (or close via the window manager). | Nothing is deleted or transferred; the host folder is unchanged; status shows the operation was cancelled. |
| MT-BR03 [CP/M] | FR-150, FR-153, FR-154 | At the MT-BR01 prompt, press **Continue**. | Every file in the host folder is deleted first; then each remote file downloads via the normal progress dialog (one file at a time). On completion the host folder contains exactly the remote drive's files. |
| MT-BR04 [CP/M] | FR-151, FR-152, UIR-088 | Press **Restore**. | The Remote pane refreshes (destination); a modal **"Confirm Restore"** dialog warns that ALL files on the remote drive will be deleted and replaced, with **Continue**/**Cancel**. Cancel leaves the remote drive unchanged. |
| MT-BR05 [CP/M] | FR-151, FR-153, FR-154 | At the Restore prompt, press **Continue**. | Each remote file is deleted (one `ERA` per file on the Terminal Port); then each host file uploads via the normal progress dialog. On completion the remote drive contains exactly the host folder's files. |
| MT-BR06 [CP/M] | FR-154, FR-120 | During a Backup or Restore transfer, press **Cancel** in the progress dialog. | The transfer aborts like a normal batch cancel (the destination was already wiped; remaining files are not copied); status shows a cancellation message; no error dialog. |
| MT-BR07 [CP/M] | FR-151, FR-148, FR-149 | Restore a host folder containing a file whose name is **not** CP/M 8.3 (e.g. `bad name.txt`). | During the upload phase the normal **"Invalid CP/M File Name"** prompt (UIR-085) appears for that file; Rename/Skip/Cancel behave as in §11.4. |
| MT-BR08 | FR-080, CR-010 | Press **Backup** or **Restore** with a port **disconnected**. | "Transport port not connected" error; no refresh, no deletion, no transfer. |
| MT-BR09 [CP/M] | FR-154 | Backup with an **empty** remote drive (or Restore with an **empty** host folder). | After confirmation the destination is still wiped; nothing is transferred; status shows "Nothing to transfer"; the destination pane ends empty. |
| MT-BR10 [CP/M] | FR-153e, UIR-107 | Set **Config → General → Erase All** to a working whole-drive erase macro for the target (e.g. `SEND ERA *.*` / `WAITFOR (Y/N)` / `SEND Y`), save, then Restore over a remote drive holding several files (press **Continue** at the warning). | The remote drive is cleared by the macro run **once** (a single `ERA *.*`-style command answered by the script) rather than one `ERA` per file; then each host file uploads as normal. On completion the remote drive contains exactly the host folder's files. Clearing the **Erase All** field and repeating falls back to the per-file `ERA` wipe (MT-BR05). |

---

## 12. Terminal Window (live)  **[CP/M or loopback]**

| ID | Req | Steps | Expected |
|----|-----|-------|----------|
| MT-W01 | FR-097, UIR-060 | Press the **Terminal** toolbar button (port may be closed). | A non-modal window titled "Terminal" opens; pressing the button again when minimised restores it. |
| MT-W02 | UIR-061, UIR-063, UIR-064, UIR-067, UIR-106 | Inspect the window. | A monospaced character-cell "Receive" screen (not an editable text field); **no** transmit field, Send button, or control-row buttons/checkboxes below the screen; below the screen a **status bar** shows the active terminal emulation type (e.g. "Emulation: VT100"). There is no separate "type here" hint label. |
| MT-W03 | FR-091, FR-096 | Connected: click into the Receive area and type a CP/M command (e.g. `DIR`) then press **Enter**. | Each keystroke is transmitted live; Enter sends the configured EOL; the remote's response is rendered in the screen. |
| MT-W04 | UIR-103b, FR-093 | In **Config > Terminal**, tick **Local Echo**, Save, then type in the Terminal Window. Then untick it and type again. | With Local Echo on, what you type is copied into the Receive screen; with it off, only the remote echo appears. |
| MT-W05 | UIR-103c, UIR-104, UIR-062 | In **Config > Terminal**, with **Autoscroll** on (default) produce enough output to overflow; then untick Autoscroll, Save, and scroll up. | With Autoscroll on, the view follows new output to the bottom; with it off, the view stays put in the scrollback. |
| MT-W06 | FR-095, UIR-099 | After traffic, right-click the Receive area and choose **Clear Window**. | The screen (and scrollback) is reset and the retained RX/TX buffers are also cleared (subsequent behaviour reflects an empty buffer). |
| MT-W07 | FR-098 | With the Terminal Port **closed**, click into the Receive area and type. | Status bar: "Terminal port not connected - cannot send"; nothing transmitted. |
| MT-W08 [CP/M] | FR-158 | Connected: press **Ctrl+C** during a running command; also press the **arrow keys**, **Backspace**, and **Esc**. | Ctrl+C sends the single control byte 0x03 (remote interrupts); arrows send `ESC[A/B/C/D`, Backspace sends 0x08, Esc sends 0x1B — each transmitted on its own keystroke. |
| MT-W09 [CP/M] | FR-091, FR-157 | Connected: run a full-screen CP/M program that uses cursor addressing/attributes (e.g. a screen editor or `VT` demo). | The screen renders correctly — cursor positioning, screen/line erase, and colour/attributes are applied — rather than showing raw escape codes. |
| MT-W10 | UIR-105 | With the Boot Sequence (MT-G10) **empty**, right-click the Receive area and note the **Boot into CP/M** item; then set a non-empty Boot Sequence in General Config, Save, and reopen the context menu. | With an empty Boot Sequence the context-menu **"Boot into CP/M"** item is disabled (greyed); after saving a non-empty sequence it is enabled the next time the menu is opened (no need to reopen the window). |
| MT-W11 [CP/M] | FR-049, UIR-105 | Connected with a valid Boot Sequence configured, right-click the Receive area and choose **Boot into CP/M**. | The status bar shows the boot sequence running; the keystrokes are transmitted; on reaching CP/M the drive drop-down and Remote Files list update. If CP/M is not reached the status bar reports the failure and **no** modal "file system unavailable" dialog appears. |
| MT-W12 | FR-091a | Resize the Terminal Window larger and smaller (and maximise). | The character-cell grid reflows to fit the window — more/fewer columns and rows become visible — down to a usable minimum; it does not stay clamped to a fixed 80×24 box. (Note: the remote is not told the new size, so a full-screen CP/M app that assumes 80×24 keeps addressing that page.) |
| MT-W13 | UIR-069, UIR-099 | Right-click the Receive area and choose **Font…**. In the standard font dialog, scroll the **Font** (family), **Font style**, and **Size** lists and select a different family, a bold/italic style, and a larger size; confirm. Then close the app, relaunch, and reopen the Terminal Window. | A standard font-selection dialog opens seeded with the current font, cleanly laid out (not a cramped/overlapping mess). **The Font / Font style / Size lists each show multiple rows and scroll**, so every family, style, and size is selectable (they are *not* collapsed to a single unusable row). On OK the Receive screen immediately repaints in the new font and the character grid reflows to the new cell size (FR-091a). After relaunch the chosen font is still in effect (persisted); Cancelling the dialog leaves the font unchanged. |
| MT-W16 [CP/M] | UIR-034, UIR-103a, FR-157i, FR-157j, FR-158a, FR-158b | In **Config → Terminal** set **Terminal Type** to **ADM-3A** (or **VT52**) and Save, then connect and run software written for that terminal (e.g. an ADM-3A build of WordStar, or a VT-52 program). Press the arrow keys in the Terminal Window. Then switch Terminal Type back to **VT100**. | The Terminal Type dropdown offers VT100/VT52/ADM-3A (default VT100). Under the chosen type the remote's cursor positioning and screen/line clears render correctly — no raw escape codes or garbled layout. The arrow keys transmit the terminal-specific codes (VT-52 → `ESC A`/`B`/`C`/`D`; ADM-3A → Ctrl-K/Ctrl-J/Ctrl-H/Ctrl-L). Switching back to VT100 restores VT-100 rendering/keys immediately, without reopening the window. |
| MT-W17 [CP/M or loopback] | UIR-099, UIR-100, FR-165, FR-166 | Connected: produce some output in the Receive screen, then **click-drag** the mouse across part of it to highlight text. **Right-click** the Receive screen and choose **Copy**; paste into a text editor to check. Copy a short command (e.g. `DIR`) from elsewhere to the clipboard, right-click the Receive screen and choose **Paste**. | Dragging highlights the text (shown in the selection colour). The right-click menu shows six command items — **Copy**, **Paste**, **Clear Window**, **Font…**, **Reset Size (24×80)**, **Boot into CP/M** — with **Copy** greyed when nothing is selected. Copy places the highlighted text on the clipboard (trailing spaces trimmed per line). Paste transmits the clipboard text on the Terminal Port as if typed (newlines sent as the configured EOL); with the port closed it reports "Terminal port not connected - cannot send" and sends nothing. |
| MT-W18 | UIR-099, FR-095, UIR-069, FR-167 | Right-click the Receive screen and use **Clear Window**, then **Font…**, then **Reset Size (24×80)** (after first resizing the window to a non-80×24 shape). | **Clear Window** resets the screen and buffers. **Font…** opens the font dialog (MT-W13). **Reset Size (24×80)** resizes the window so the character-cell grid reflows to exactly 80 columns × 24 rows. |
| MT-W19 [CP/M] | UIR-099, UIR-101, UIR-034, UIR-106 | Right-click the Receive screen and open the **Terminal Type** submenu; note the tick against the active type, then choose a different type (e.g. **ADM-3A**). Reopen the submenu to confirm the tick moved. | The submenu lists **VT100**, **VT52**, **ADM-3A** with the currently active type checked. Choosing another type applies it to the running terminal immediately (matching the Config → Terminal **Terminal Type** dropdown, MT-W16) — subsequent output is interpreted and the cursor keys encoded per the new type — and the tick follows the selection. The bottom **status bar** updates to the newly selected type (e.g. "Emulation: ADM-3A"). |
| MT-W20 [CP/M or loopback] | UIR-099, UIR-102, FR-162 | Configure at least one macro button (MT-G13). Right-click the Receive screen and open the **Macros** submenu; choose a macro whose script sends a command (e.g. `SENDRAW 0D`). Then clear all macro definitions and reopen the submenu. | The submenu lists one item per configured macro (label shown; empty slots omitted). Selecting one runs its keystroke script on the Terminal Port and the remote responds in the Receive screen. With no macros configured the **Macros** submenu is present but greyed (disabled). |
| MT-W21 | FR-168 | Open the Terminal Window and the Transfer History window, then **Exit** the app and relaunch it. Then close both, Exit, and relaunch again. | First relaunch: both the Terminal Window and the Transfer History window reopen automatically (at their saved positions). Second relaunch: neither reopens (they were closed at exit). |

---

## 13. File context-menu actions

Host-side Rename/Delete/View are unit-tested at the logic level; manual testing confirms the **real**
dialog, real filesystem effect, and real viewer launch. Remote actions need a live peer.

| ID | Req | Steps | Expected |
|----|-----|-------|----------|
| MT-F01 [visual] | UIR-018, UIR-019 | Right-click a host file; right-click a remote file. | Host menu: **To Remote** (top, separated), View/Edit, Rename, Delete. Remote menu: **To Host** (top, separated), View, Rename, Delete. |
| MT-F01a [visual] | FR-110, FR-111, UIR-018, UIR-019 | Select **two or more** files in the Host list (and likewise the Remote list), then right-click a selected file. | **View/Edit** (host) / **View** (remote) and **Rename** are **disabled** (greyed). To Remote/To Host and Delete remain enabled. |
| MT-F02 | FR-112 | Host file → **View/Edit** with default `viewer_cmd` (`notepad $1`). | The file opens in Notepad (or the configured editor). |
| MT-F03 | FR-112 | Set `viewer_cmd` empty (General Config), then View/Edit a host file. | The file opens via the OS default association for its type. |
| MT-F04 | UIR-057, FR-114, FR-116, FR-118 | Host file → **Rename**: dialog shows an editable field pre-filled and pre-selected; change the name, Apply. | File renamed on disk; Host list refreshes. Cancel (or unchanged/empty name) makes no change. |
| MT-F05 | UIR-057, FR-115, FR-116, FR-118 | Host file → **Delete**: dialog shows a **read-only** name field; Apply. | File deleted from disk; Host list refreshes. Cancel makes no change. |
| MT-F05a | FR-110, FR-115, FR-116, FR-118 | Select **several** host files, right-click → **Delete**: the dialog lists **all** selected names (read-only) and asks "Delete these N files?"; Apply. | **Every** selected file is deleted from disk; Host list refreshes once. Cancel makes no change. |
| MT-F06 [CP/M] | FR-117, FR-118 | Remote file → Rename / Delete with the Terminal Port open. | `REN new=old` / `ERA name` sent on the Terminal Port; Remote list refreshes; the change is visible on the CP/M side. |
| MT-F06a [CP/M] | FR-111, FR-115, FR-117, FR-118 | Select **several** remote files, right-click → **Delete**: the dialog lists all selected names; Apply. | `ERA name` is sent **once per selected file** (in list order) on the Terminal Port; Remote list refreshes once; all files are gone on the CP/M side. |
| MT-F07 [CP/M] | FR-117 | Remote Rename/Delete with the Terminal Port **closed**. | No command sent; status bar "Terminal port not connected - cannot rename"/"…cannot delete". |
| MT-F08 [CP/M] | FR-113, FR-112 | Remote file → **View** while both flags connected. | File is first downloaded over X-Modem to a temp folder (progress dialog shows), then opened in the viewer. With Transport disconnected: "Transport port not connected", no download. |
| MT-F09 [CP/M] | FR-119, FR-106, FR-107 | Select **several** host files, right-click → **To Remote** (and likewise several remote files → **To Host**), with both flags connected. | **Every** selected file is transferred sequentially via the normal batch process (progress dialog shows each file); the destination list refreshes once on success. With a flag disconnected: "Transport port not connected", no transfer. |

---

## 14. Internationalisation (Language)  **[visual]**

The translator, file parsing, fallback chain, and key parity are unit-tested (`tests/test_i18n.py`);
manual testing confirms the **on-screen** live re-translation, real menu, and cross-session
persistence of the language choice.

| ID | Req | Steps | Expected |
|----|-----|-------|----------|
| MT-I01 [visual] | FR-122, UIR-003, UIR-077 | Open **Config > Language**. | A submenu lists **English**, **German**, **French** (one per `lang_*.txt`); entries are checkable and mutually exclusive; the active language (English by default) is checked. |
| MT-I02 [visual] | FR-123 | With the main window and Terminal Window open, choose **Config > Language > German**. | The menu bar, toolbar, "Host Files"/"Remote Files" group titles, all buttons, the status indicators, and the Terminal Window labels switch to German **immediately**, with no restart. The German entry is now checked. |
| MT-I03 [visual] | FR-121, FR-123 | While in German, open Config > Serial, Config > General, Help > About, and right-click a file. | The dialog titles, field labels, button captions (e.g. Speichern/Abbrechen), the About text, and the context-menu items are shown in German. |
| MT-I04 | CR-015 | While in German, open Config > Serial and Config > General and inspect the drop-downs (Parity, Flow Control, End of Line, Debug Logging) and command fields (List Files, Receive/Send, Rename/Delete in the Remote group). | Option **values** (NONE/ODD/…, CR/LF/CRLF, OFF/ON) and command templates (DIR, PCPUT $1, REN $2=$1, …) remain **untranslated**; only the row labels and the group title change. Saving and reloading the config preserves these values unchanged. |
| MT-I05 | FR-124 | Switch to French, then fully quit and relaunch (`cpm-fm`). | On next start the GUI is in **French** (the choice persisted); switching back to English persists likewise. |
| MT-I06 | FR-121, NFR-005 | Copy `src/cpm_fm/lang/lang_english.txt` to `lang_spanish.txt`, translate a few values, relaunch. | **Spanish** appears in the Config > Language menu with no code change; selecting it shows the translated strings and English for any keys left untranslated (fallback). |

---

## 15. Visual theme, layout, and window state  **[visual]**

| ID | Req | Steps | Expected |
|----|-----|-------|----------|
| MT-V01 | UIR-070, CR-013 | Inspect all windows/dialogs. | The Material theme is applied consistently across the main window, Terminal Window, and every dialog (centrally, not per-widget). |
| MT-V02 | UIR-073 | Set the host OS to **light** mode, launch; then set OS to **dark** mode, relaunch. | The app picks the matching light/dark Material variant at start-up. (If the OS preference is unavailable, it defaults to dark.) |
| MT-V03 | UIR-071 | Inspect the toolbar. | Connect/Disconnect/Terminal shown as labelled, icon-bearing toolbar buttons at the top. |
| MT-V04 | UIR-072 | Drag the splitter between Host and Remote panes. | The divider moves and re-apportions horizontal space. (Need not persist across sessions.) |
| MT-V05 | UIR-074 | Watch the status-bar indicators through a connect/disconnect cycle. | Two indicators (Terminal, Transport) each show a distinct visual state: **green** when connected and **red** when not connected. |
| MT-V06 | UIR-014 | Trigger a very long status message (e.g. a long error). | Status bar shows a single line truncated to 127 characters. |
| MT-V07 | FR-004 | Move/resize the main window, the Terminal Window, and the Serial & General dialogs; quit; relaunch and reopen each. | Each window/dialog reopens at its last size/position. (Splitter position is exempt — UIR-072.) |
| MT-V08 | FR-015, FR-016 | With ports open and the Terminal Window + a config dialog open, choose File > **Exit**. | All COM ports close and all dialogs/windows close cleanly; no orphaned process. |
| MT-V09 | UIR-075 | Open Config > Serial, Config > General, and a File Action dialog (right-click a host file → Rename); also glance at a transfer progress dialog (MT-T05). | In every two-button dialog the **Cancel** button is at the **far left** and the affirmative button (**Save** for the config dialogs, **Apply** for the File Action dialog) at the **far right**, with space between; the progress dialog's single **Cancel** button is **centred**. |
| MT-V10 | FR-022, UIR-076, UIR-075, DR-040, DR-041 | Choose **Help > About**. Read the dialog, then click the GitHub link, then click **OK**. | A modal dialog titled "About" shows: the program name **CP/M File Manager**; **Version `<x.y.z>`** matching `src/version.txt` and the SRS version field (both `2.5.2`); a clickable hyperlink to `https://github.com/turbo-gecko/CPM_FM`. Clicking the link opens that page in the host's default browser. A single **OK** button (centred) closes the dialog. |
| MT-V11 | UIR-078, DR-044 | Launch the app and inspect the window's title-bar icon and the OS taskbar/dock entry; open the Terminal Window and a dialog (e.g. Config > Serial) and check their icons too. | All windows and dialogs and the taskbar/dock show the branded **CP/M File Manager** icon (the blue monitor artwork), not the generic Qt/Python default. The same icon should appear at small (title-bar) and larger (taskbar/alt-tab) sizes without distortion. |
| MT-V12 | FR-016, FR-113a, FR-171 | Note your OS temp folder (e.g. `%TEMP%` / `$TMPDIR`). Open a CP/M disk image (creates a `cpm_fm_img_*` folder) and right-click → **View** a remote file (creates a `cpm_fm_*` folder). Confirm both folders exist. Then choose **File > Exit** and re-check the temp folder. Next, to simulate an unclean shutdown, create a dummy `cpm_fm_leftover` folder in the temp folder by hand and **relaunch** the app. | After Exit, **no** `cpm_fm*` folder created by the session remains in the temp folder. After the relaunch, the hand-made `cpm_fm_leftover` folder has been swept away too (start-up cleanup). A folder still held open by an external viewer is left in place and cleared on a later exit/launch. |

---

## 16. Cross-cutting / non-functional

| ID | Req | Steps | Expected |
|----|-----|-------|----------|
| MT-N01 | FR-088 | Run via `python -m cpm_fm` with Debug Logging **OFF**, do a transfer; then set it **ON** and repeat. Then launch via the console-less `cpm-fm` launcher with Debug Logging **ON** and do a transfer. | OFF: no verbose per-byte X-Modem trace on stdout, and **no `cpm_fm_debug.log`** is created in the launch folder. ON (`python -m cpm_fm`): verbose trace and transfer-flow messages appear on stdout **and** are written to `cpm_fm_debug.log` in the folder the app was launched from. ON (`cpm-fm` launcher): the same trace is written to `cpm_fm_debug.log` in the launch folder even though there is no console. |
| MT-N02 | STR-003, CR-012 | If feasible, repeat the §4 smoke and one transfer (§11) on a second OS (e.g. Linux/macOS as well as Windows). | App launches and core flows work cross-platform. *(Mark N/A if only one OS is available.)* |
| MT-N03 | NFR-001, NFR-004 | During a long transfer and a long remote listing, interact with the UI. | UI never freezes; no Qt "cannot create children for a parent in a different thread" warnings on the console. |

---

## 17. Traceability summary (manual-only coverage)

The cases above target requirements that are **not** fully exercised by `pytest` because they depend on
real serial hardware, a live CP/M peer, on-screen rendering, real OS dialogs/associations, real timing,
or real cross-session persistence:

- Lifecycle / persistence (real): `FR-004` (windows/dialogs), `FR-005`, `FR-006`, `FR-015`, `FR-016` (the temp-directory sweep logic in `utils/temp_cleanup.py` is covered automatically by `tests/test_temp_cleanup.py`; MT-V12 confirms real folders are removed on exit and start-up end-to-end).
- Connect/disconnect (real ports & error paths): `FR-030`–`FR-040`, `FR-050`–`FR-058`.
- Remote listing & drive selection (live capture/timing): `FR-074`–`FR-079`, `FR-100`–`FR-104`.
- Transfers (live X-Modem, CP/M launch, timing, byte echo, live cancel): `FR-080`–`FR-089`, `FR-099`, `FR-105`–`FR-109`, `FR-119`, `FR-120`, `NFR-003a`–`NFR-003q` (interop + CAN abort).
- Terminal Window (interactive VT-100/VT-52/ADM-3A over a link): `FR-090`–`FR-098`, `FR-157`, `FR-157i`, `FR-157j`, `FR-158`, `FR-158a`, `FR-158b`, `UIR-034`, `UIR-060`–`UIR-068`, `UIR-106`.
- File actions (real dialog/filesystem/viewer/remote cmd): `FR-112`, `FR-113`, `FR-114`–`FR-118`, `UIR-057`.
- Interfaces (real): `IFR-001`–`IFR-004`.
- Config dialogs (on-screen layout, field values/limits): `UIR-020`–`UIR-056`.
- Theme, layout & dialog button placement: `UIR-070`–`UIR-075`, `CR-012`, `CR-013`.
- Application icon (on-screen render across windows + OS taskbar/dock): `UIR-078` (the resource presence/loadability and missing-file fallback in `DR-044` are covered automatically by `tests/test_gui_smoke.py`; MT-V11 confirms the branded icon actually renders).
- About dialog (on-screen render + live browser launch): `FR-022`, `UIR-004`, `UIR-076` (the version-sourcing `DR-040`/`DR-041` are covered automatically by `tests/test_version.py`; MT-V10 confirms the displayed version matches end-to-end).
- Internationalisation (live on-screen re-translation, real menu, cross-session language persistence): `FR-122`, `FR-123`, `FR-124` (live), `UIR-003`, `UIR-077`, `CR-015`, `NFR-005` (the translator, parsing, and fallback in `FR-121`/`DR-042`/`DR-043` are covered automatically by `tests/test_i18n.py`; the manual cases confirm the rendered UI switches language live and that the choice persists).
- File list filter & sort (live on-screen filtering/sorting, debounce timing, active-filter indicator, cross-session persistence): `FR-130`–`FR-135` (live), `UIR-079`, `UIR-080` (the filter/sort logic itself in `utils/file_filter.py` and the GUI wiring are covered automatically by `tests/test_file_filter.py` and `tests/test_gui_smoke.py`; the manual cases confirm the on-screen rendering, the debounce feel, and real cross-session restore).
- Drag-and-drop file transfer (live drag gesture, drop-zone highlight, external OS drops, real transfer round-trip): `FR-136`–`FR-139` (live), `UIR-081` (the decode/handoff logic — drag payload, cross-pane vs same-pane, external-vs-host acceptance, flag-gating, confirmation — is covered automatically by `tests/test_gui_smoke.py`; the manual cases confirm the on-screen highlight, the real drag from the OS file manager, and the live transfer).
- Transfer history (on-screen dialog render, real cross-session persistence, real Export file, live re-transfer round-trip): `FR-140`–`FR-144` (live), `UIR-082`, `UIR-083`, `DR-045` (the history store — schema, persistence, retention, thread-safe recording, export — and the dialog's list/filter/clear/re-transfer wiring are covered automatically by `tests/test_transfer_history.py` and `tests/test_gui_smoke.py`; the manual cases confirm the rendered dialog, real `~/.cpm_fm_history.json` persistence across sessions, the real exported file, and a live re-transfer).
- File-conflict prompt on transfer (live dialog render, real overwrite/skip on the filesystem & remote, real pre-upload `DIR` refresh): `FR-145`–`FR-147` (live), `UIR-084` (the detection, the batch-wide policy, and the Skip/Cancel batch handling are covered automatically by `tests/test_conflict_resolution.py`; the manual cases confirm the on-screen dialog, that Overwrite/Skip really replace/preserve the destination file, and that an upload conflict is detected against a freshly refreshed remote listing).
- Host→remote filename validation (live dialog render, real upload under a renamed name, inline re-validation): `FR-148`, `FR-149` (live), `UIR-085` (the 8.3 validation/suggestion logic and the rename/skip/cancel batch handling are covered automatically by `tests/test_filename_validation.py`; the manual cases confirm the on-screen dialog, that Rename really uploads the file to the remote under the new name, and that a still-invalid replacement is rejected inline).
- Whole-drive backup and restore (live destructive round-trip, real destination wipe, on-screen confirmation): `FR-150`–`FR-154` (live), `UIR-086`–`UIR-088` (the orchestration ordering, the wipe helpers, the empty-source short-circuit, the connection guard, and the confirmation slot are covered automatically by `tests/test_backup_restore.py`; the manual cases confirm the on-screen confirmation dialog, that the destination is really emptied first, and the live transfer round-trip in both directions).
- Boot-into-CP/M sequence (live keystroke playback into a real remote, probe-failure recovery, live re-probe): `FR-047`, `FR-048`, `FR-049` (live), `UIR-068` (the script parser in `terminal/boot_sequence.py`, the directive execution, the auto-recovery/re-probe wiring, the button enable/disable, and the multi-line config field are covered automatically by `tests/test_boot_sequence.py` and `tests/test_gui_smoke.py`; the manual cases confirm the keystrokes really drive a non-auto-booting remote into CP/M and that the failed-probe recovery and manual button behave over a real link).
- CP/M disk image support (live menu wiring, on-screen geometry picker, real image on disk, live transfer of extracted files, on-screen details view): `FR-169`, `UIR-108`, `UIR-109` (live) (the geometry parsing, auto-detection ranking/ambiguity/allocation-pointer check, directory reconstruction, and the extract/reject/cleanup/details GUI orchestration in `FR-170`–`FR-173`/`DR-048`/`DR-049` are covered automatically by `tests/test_disk_image/` and `tests/test_gui_smoke.py`; the manual cases confirm the real File-menu actions, the on-screen picker on ambiguity, the read-only Image Details dialog, and that files extracted from a real image transfer over a live link).
- Non-functional (real): `NFR-001`, `NFR-004` (live), `STR-003`, `FR-088`.

Purely algorithmic and headless-logic requirements (`DR-*`, the X-Modem progress/handshake internals,
parser-fed list ordering, and the stubbed GUI orchestration in `test_gui_smoke.py`) are already covered
by the automated suite and are **not** re-tested here except where a live round-trip is needed to
confirm the real data path feeds them correctly (e.g. MT-R04).
