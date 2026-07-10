# CP/M File Manager — Manual Test Scorecard

> Fill this out while running `docs/manual_test_plan.md`. The **Results tables** (§3) give a fast
> pass/fail sweep; for **every Fail or Blocked**, also complete one **Fault Report** block (§4). The
> Fault Report fields are chosen to give Claude what it needs to locate and fix the bug without a
> back-and-forth — please be literal (paste exact text, don't paraphrase).

| Field | Value |
|-------|-------|
| Scorecard version | 1.49 |
| Scorecard for plan version | 1.50 (`docs/manual_test_plan.md`) |
| SRS version | (e.g. 2.11.0) |
| Tester | |
| Date(s) of run | |

---

## 1. Run environment (fill once per run)

| Item | Value |
|------|-------|
| App version / git commit | `git rev-parse --short HEAD` → |
| Host OS + version | |
| Python version | `python --version` → |
| PySide6 version | `python -c "import PySide6; print(PySide6.__version__)"` → |
| qt-material version | `python -c "import qt_material; print(qt_material.__version__)"` → |
| Entry point used | `cpm-fm` / `python -m cpm_fm` (note per case if it varies) |
| Connectivity option | A = real CP/M · B = emulator · C = loopback/port-pair (per §2.1 of the plan) |
| CP/M system / emulator details | (machine, CP/M version, X-Modem helpers e.g. PCGET/PCPUT version) |
| Terminal Port device | (e.g. COM3 / /dev/ttyUSB0) |
| Transport Port device | (same as Terminal? or COM4 / …) |
| Port settings | speed / data / parity / stop / flow |
| QSettings cleared before run? | yes / no (org `turbo-gecko`, app `cpm-fm`) |
| Config file(s) used | (paths) |
| Host scratch folder | (path + brief inventory of test files) |

**OS theme for MT-V02:** light run? ☐  dark run? ☐

---

## 2. Result legend

- **P** — Pass: every "Expected" bullet observed.
- **F** — Fail: one or more "Expected" bullets not observed → file a Fault Report (§4).
- **B** — Blocked: could not run (e.g. couldn't induce a close failure, no second port) → note why; a Fault Report is optional but helpful.
- **NA** — Not applicable for this environment (e.g. CP/M-only case on a loopback run).
- **NT** — Not tested / skipped this run.

In the **Env** column note the connectivity option actually used (A/B/C) if it differs from the run default.

---

## 3. Results tables

### §4 Smoke / start-up
| ID | Title | Req | Result | Env | Notes |
|----|-------|-----|:------:|:---:|-------|
| MT-S01 | Launch + Material theme applied | STR-002, CR-012/013 | | | |
| MT-S02 | Unconfigured start; host populated; remote empty | FR-003/060/070 | | | |
| MT-S03 | File, Config & Help menus present | UIR-001/002/003/004 | | | |
| MT-S04 | Toolbar Connect/Disconnect/Terminal/History/Backup/Restore enabled | UIR-013/071/015/016/082/086/087 | | | |
| MT-S05 | Pane layout correct (equal Change Dir/Update; equal drive/Update) | UIR-011/012/017/061-067 | | | |

### §5 Connect / disconnect (real ports)
| ID | Title | Req | Result | Env | Notes |
|----|-------|-----|:------:|:---:|-------|
| MT-C01 | Connect opens terminal; status + indicator | FR-030/032/034, UIR-074 | | | |
| MT-C02 | Bad terminal port → "unable to be opened" | FR-031/033 | | | |
| MT-C03 | Two-port connect opens both | FR-038/040 | | | |
| MT-C04 | Bad transport port → "unable to be opened" | FR-039 | | | |
| MT-C05 | Shared port → transport connected, no crash | FR-037 | | | |
| MT-C06 | Connect does NOT open Terminal Window | FR-035/097 | | | |
| MT-C11 | Connect probe → drive prompt sets drive + lists | FR-041/042 | | | |
| MT-C12 | No drive prompt → modal Abort/Continue/Terminal | FR-041/043/044/045, UIR-092 | | | |
| MT-C12a | Probe dialog Abort → ports closed, list cleared | FR-045 | | | |
| MT-C12b | Probe dialog Continue → no action, ports stay open | FR-045 | | | |
| MT-C12c | Probe dialog Terminal → Terminal Window opens, ports stay open | FR-045/097 | | | |
| MT-C13 | ZCPR prompt (A0>/4A>) recognised by probe | DR-033/FR-042 | | | |
| MT-C14 | Boot sequence recovers a non-auto-booting remote → lists populate | FR-047/048 | | | |
| MT-C15 | Empty boot sequence → failed probe shows dialog directly | FR-044/048 | | | |
| MT-C07 | Disconnect closes terminal; status + indicator | FR-050/052/053 | | | |
| MT-C08 | Two-port disconnect closes both | FR-055/057 | | | |
| MT-C09 | Clean disconnect clears remote list | FR-058 | | | |
| MT-C10 | Close failure cancels disconnect; list kept | FR-051/058 | | | |
| MT-C18 | Swapped ports: Disconnect/Abort stays prompt (no hang) | FR-030/050 | | | |
| MT-C19 | Load config while connected closes old ports | FR-017a/050 | | | |

### §6 Serial config & enumeration
| ID | Title | Req | Result | Env | Notes |
|----|-------|-----|:------:|:---:|-------|
| MT-P01 | Port drop-downs enumerate host ports | IFR-003, UIR-022/023 | | | |
| MT-P02 | Serial dialog title/layout | FR-020, UIR-020/021/029 | | | |
| MT-P03 | Drop-down values & defaults | UIR-024-028 | | | |
| MT-P04 | msec fields 0–255 integer only | UIR-030/031 | | | |
| MT-P05 | Flow control applied at open | UIR-028 | | | |
| MT-P06 | Same port for both logical ports | IFR-002 | | | |

### §7 General config dialog
| ID | Title | Req | Result | Env | Notes |
|----|-------|-----|:------:|:---:|-------|
| MT-G01 | Title; "Remote" group first; rest ungrouped | FR-021, UIR-040/041/044 | | | |
| MT-G02 | Command field defaults & limits | UIR-042/045/046 | | | |
| MT-G03 | EOL drop-down; CR default | UIR-047/048 | | | |
| MT-G04 | Launch/inter-file delay defaults & ranges | UIR-049/052 | | | |
| MT-G05 | Debug Logging dropdown OFF/ON | UIR-050 | | | |
| MT-G09 | Echo Transfer Data dropdown OFF/ON, default OFF | UIR-058 | | | |
| MT-G06 | Default Host Directory browse | UIR-053 | | | |
| MT-G07 | Viewer; Rename/Delete (in Remote group) defaults | UIR-054/055/056 | | | |
| MT-G08 | No "Change Disk" field | UIR-043 | | | |
| MT-G10 | Boot Sequence multi-line field round-trips | UIR-059 | | | |
| MT-G11 | Test button (Send/Receive): reports no-response vs. success, no real transfer | UIR-094/095, FR-161 | | | |
| MT-G12 | Config → Terminal dialog: menu item, Terminal tab (Type/Local Echo/Autoscroll) + Macros tab (ten Macro slots) | FR-021c, UIR-003, UIR-103, UIR-103a, UIR-103d | | | |
| MT-G12a | Terminal tab settings round-trip; Save persists terminal+macro subset only | FR-021c, UIR-034, UIR-103b, UIR-103c | | | |
| MT-G13 | Macro slots round-trip label + keystrokes; Save persists terminal+macro subset only | FR-021b, FR-021c, UIR-098, UIR-103d | | | |
| MT-G14 | Macros-tab Test runs typed script on the port; not-connected error when closed | FR-162, UIR-098, UIR-103d | | | |

### §8 Config load / save
| ID | Title | Req | Result | Env | Notes |
|----|-------|-----|:------:|:---:|-------|
| MT-L01 | Load dialog defaults to JSON | FR-010, IFR-004 | | | |
| MT-L02 | Full replace; flat & nested shapes | FR-011, NFR-002 | | | |
| MT-L03 | Unknown keys retained, inert | FR-012 | | | |
| MT-L04 | Load clears remote list | FR-017 | | | |
| MT-L05 | Save writes JSON | FR-013/014 | | | |
| MT-L06 | Dialogs reopen in last config folder | FR-006/010/013 | | | |
| MT-L07 | Auto-reload last config on relaunch | FR-005 | | | |
| MT-L08 | Missing remembered file → unconfigured | FR-005/003 | | | |
| MT-L09 | New saves to remembered file, resets | FR-018/019 | | | |
| MT-L10 | New prompts when none remembered; cancel aborts | FR-018 | | | |
| MT-L11 | Title bar shows loaded config base name | FR-125/UIR-005 | | | |
| MT-L12 | New clears config name from title bar | FR-125 | | | |

### §9 Host file management
| ID | Title | Req | Result | Env | Notes |
|----|-------|-----|:------:|:---:|-------|
| MT-H01 | Host list = default host dir at startup | FR-060 | | | |
| MT-H02 | Change Directory reloads host list | FR-061/062 | | | |
| MT-H03 | Host "Update" button refreshes Host list ONLY | FR-063 | | | |
| MT-H04 | Host group title shows current dir, left-elided | FR-126/UIR-011 | | | |

### §9.1 File list filter & sort (visual)
| ID | Title | Req | Result | Env | Notes |
|----|-------|-----|:------:|:---:|-------|
| MT-FS01 | Substring filter narrows list; × clears | FR-130/131, UIR-079 | | | |
| MT-FS02 | Wildcard `*`/`?` whole-name glob | FR-131 | | | |
| MT-FS03 | Filter debounced (~150 ms), no lag | FR-131 | | | |
| MT-FS04 | Sort Name/Extension + direction arrow | FR-132, UIR-080 | | | |
| MT-FS05 | Combined filter + sort (filter then sort) | FR-133 | | | |
| MT-FS06 | Active-filter visual indicator | FR-135, UIR-079 | | | |
| MT-FS07 | Filter/sort persist per pane across sessions | FR-134 | | | |
| MT-FS08 | Cleared remote list stays empty (no stale) | FR-135 | | | |
| MT-FS09 | Sort labels/placeholder retranslate | UIR-080, FR-123 | | | |

### §9.2 CP/M disk image support
| ID | Title | Req | Result | Env | Notes |
|----|-------|-----|:------:|:---:|-------|
| MT-DI01 | Open Disk Image… lists image files in Host pane | FR-169, UIR-108 | | | |
| MT-DI02 | Unambiguous image auto-detects; geometry in status | FR-170 | | | |
| MT-DI03 | Ambiguous/unknown image shows geometry picker | FR-170 | | | |
| MT-DI04 | Extracted files Copy to Remote over X-Modem | FR-171 | | | |
| MT-DI05 | Foreign/corrupt file rejected gracefully (no crash) | FR-172 | | | |
| MT-DI06 | Temp workdir discarded on New / reopen / exit | FR-171 | | | |
| MT-DI07 | Image Details… shows read-only name/size/user/attrs table | FR-173, UIR-109 | | | |
| MT-DI08 | Image Details… disabled when no image open | FR-173, UIR-109 | | | |
| MT-DI10 | Save Image… re-packs workdir to a new image; source untouched | FR-174, DR-050 | | | |
| MT-DI11 | Copy-to-image: file received into the Host pane is written on save | FR-175 | | | |
| MT-DI12 | Unsaved-changes Save/Discard/Cancel prompt + image-name group title | FR-175, UIR-111 | | | |
| MT-DI13 | Remote-pane mount: local host↔image copy (both directions) + affordance | FR-176, UIR-112 | | | |
| MT-DI14 | Remote-pane mount mutual exclusion with a live serial session | FR-176 | | | |
| MT-DI15 | Close Disk Image restores Host/Remote panes; save prompt on close | FR-177, UIR-113 | | | |
| MT-DI16 | New Disk Image creates empty image; copy in, save, adopt source | FR-178, UIR-114 | | | |
| MT-DI17 | Separate image directory; host-dir change keeps a Remote-mounted image | FR-176, FR-179 | | | |
| MT-DI18 | Menu items "… Config"; Save Image overwrites in place (KISS, no enable) | FR-174 | | | |
| MT-DI19 | Backup/Restore mirror host↔image locally for a Remote-mounted image | FR-180 | | | |

### §10 Remote listing & drive selection (live)
| ID | Title | Req | Result | Env | Notes |
|----|-------|-----|:------:|:---:|-------|
| MT-R01 | Update lists sorted; status message | FR-073/075-079 | | | |
| MT-R02 | Port closed → status msg, list cleared | FR-074/104 | | | |
| MT-R03 | Capture wait handles slow/bursty output | FR-076 | | | |
| MT-R04 | Live data path: extensionless / single file | FR-077/078, DR-013 | | | |
| MT-R05 | Select other drive lists it | FR-100/102 | | | |
| MT-R06 | Nonexistent drive → "Drive X: not found" | FR-103 | | | |
| MT-R07 | Update uses displayed drive (OI-22) | FR-073 | | | |

### §11 File transfers (live X-Modem)
| ID | Title | Req | Result | Env | Notes |
|----|-------|-----|:------:|:---:|-------|
| MT-T01 | Guard: transport not connected | CR-010, FR-080 | | | |
| MT-T02 | Guard: no file selected | FR-106 | | | |
| MT-T03 | Copy to Remote end-to-end + refresh | FR-081-083/087/089/099 | | | |
| MT-T04 | Copy to Host end-to-end + refresh | FR-081-083/087/099 | | | |
| MT-T05 | Progress dialog content/behaviour (Cancel button, no X) | FR-105, UIR-051 | | | |
| MT-T06 | Multi-file batch, sequential, "File i of N" | FR-106/107/105 | | | |
| MT-T07 | Batch abort on mid-file failure | FR-108 | | | |
| MT-T08 | Inter-file wait (no truncated command) + post-final-file settle before refresh | FR-109 | | | |
| MT-T09 | Hex byte echo `<HH>` to Terminal Window; suppressed when Echo Transfer Data OFF | FR-086, UIR-058 | | | |
| MT-T10 | NAK-first; 1K frames; 0x1A pad; integrity | NFR-003c, NFR-003f, NFR-003h | | | |
| MT-T11 | UI responsive during large transfer | NFR-001 | | | |
| MT-T12 | Context-menu To Remote / To Host | FR-119 | | | |
| MT-T13 | Cancel single live transfer; CAN abort; no error | FR-120, NFR-003m | | | |
| MT-T14 | Cancel mid-batch; skip rest; refresh; no partial file | FR-120 | | | |
| MT-T15 | Misconfigured remote command reports "No response" diagnosis, not generic failure | FR-159, FR-160 | | | |

### §11.1 Drag-and-drop file transfer
| ID | Title | Req | Result | Env | Notes |
|----|-------|-----|:------:|:---:|-------|
| MT-D01 | Drag host files; drop-zone highlight; same-pane rejected | FR-136/139, UIR-081 | | | |
| MT-D02 | External OS drag highlights Remote only, not Host | FR-138/139 | | | |
| MT-D03 | Drop host→remote transfers (confirm); guard when disconnected | FR-137, FR-080, CR-010 | | | |
| MT-D04 | Drop remote→host transfers (confirm) | FR-137 | | | |
| MT-D05 | External OS files dropped on Remote upload | FR-138 | | | |
| MT-D06 | Declining confirmation starts no transfer | FR-137 | | | |

### §11.2 Transfer history
| ID | Title | Req | Result | Env | Notes |
|----|-------|-----|:------:|:---:|-------|
| MT-TH01 | History button opens dialog; entries newest-first | FR-140/142, UIR-082 | | | |
| MT-TH02 | Filter by direction and status | FR-143, UIR-083 | | | |
| MT-TH03 | Export history to JSON file | FR-143 | | | |
| MT-TH04 | Clear history (with confirmation) | FR-143 | | | |
| MT-TH05 | History persists across sessions | FR-141 | | | |
| MT-TH06 | Re-transfer entry; guards; marked retry | FR-144, FR-080 | | | |

### §11.3 File-conflict prompt on transfer
| ID | Title | Req | Result | Env | Notes |
|----|-------|-----|:------:|:---:|-------|
| MT-CF01 | Download conflict shows Overwrite/Skip/Cancel + apply-all dialog | FR-145/146, UIR-084 | | | |
| MT-CF02 | Overwrite replaces the host file (success recorded) | FR-146 | | | |
| MT-CF03 | Skip leaves host file untouched (skipped recorded) | FR-146 | | | |
| MT-CF04 | Upload conflict detected against fresh remote DIR | FR-145 | | | |
| MT-CF05 | "Apply to all" prompts once, applies to remaining conflicts | FR-147 | | | |
| MT-CF06 | Cancel/close at a conflict aborts the whole batch | FR-146, FR-120 | | | |
| MT-CF07 | No prompt when the destination has no matching file | FR-145 | | | |

### §11.4 Host→remote filename validation
| ID | Title | Req | Result | Env | Notes |
|----|-------|-----|:------:|:---:|-------|
| MT-FV01 | Invalid 8.3 name shows Rename/Skip/Cancel dialog with suggestion | FR-148, FR-149, UIR-085 | | | |
| MT-FV02 | Rename uploads the file under the new name (success recorded) | FR-149 | | | |
| MT-FV03 | Still-invalid replacement is rejected inline (dialog stays open) | FR-149 | | | |
| MT-FV04 | Skip leaves file unsent and continues (skipped recorded) | FR-149, FR-142 | | | |
| MT-FV05 | Cancel/close at an invalid name aborts the whole batch | FR-149, FR-120 | | | |
| MT-FV06 | No prompt when the upload name already meets 8.3 | FR-148 | | | |
| MT-FV07 | Renamed name onto an existing remote file triggers the conflict prompt | FR-149, FR-145 | | | |

### §11.5 Whole-drive backup and restore
| ID | Title | Req | Result | Env | Notes |
|----|-------|-----|:------:|:---:|-------|
| MT-BR01 | Backup refreshes panes then warns before any delete | FR-150, FR-152, UIR-088 | | | |
| MT-BR02 | Backup Cancel/close leaves host folder unchanged | FR-152 | | | |
| MT-BR03 | Backup Continue wipes host then downloads all remote files | FR-150, FR-153, FR-154 | | | |
| MT-BR04 | Restore refreshes remote then warns before any delete | FR-151, FR-152, UIR-088 | | | |
| MT-BR05 | Restore Continue ERA-wipes remote then uploads all host files | FR-151, FR-153, FR-154 | | | |
| MT-BR06 | Cancel mid-transfer aborts the batch | FR-154, FR-120 | | | |
| MT-BR07 | Restore of a non-8.3 host name triggers the validation prompt | FR-151, FR-148, FR-149 | | | |
| MT-BR08 | Backup/Restore with a port disconnected → error, no action | FR-080, CR-010 | | | |
| MT-BR09 | Empty source still wipes; nothing transferred | FR-154 | | | |
| MT-BR10 | Restore Erase All macro wipes drive in one call (else per-file) | FR-153e, UIR-107 | | | |

### §12 Terminal Window (live)
| ID | Title | Req | Result | Env | Notes |
|----|-------|-----|:------:|:---:|-------|
| MT-W01 | Terminal button opens/restores window | FR-097, UIR-060 | | | |
| MT-W02 | Character-cell screen; no transmit field/Send; no control row; status bar shows emulation type | UIR-061/063/064/067/106 | | | |
| MT-W03 | Type + Enter sent live; remote responds | FR-091/096 | | | |
| MT-W04 | Local Echo (Config → Terminal) behaviour | UIR-103b, FR-093 | | | |
| MT-W05 | Autoscroll (Config → Terminal) + scrollback behaviour | UIR-103c/104/062 | | | |
| MT-W06 | Context-menu Clear Window resets screen + buffers | FR-095, UIR-099 | | | |
| MT-W07 | Type with port closed → status msg | FR-098 | | | |
| MT-W08 | Ctrl+C / arrows / Backspace / Esc keys encoded live | FR-158 | | | |
| MT-W09 | Full-screen VT-100 program renders correctly | FR-091/157 | | | |
| MT-W10 | Context-menu Boot item disabled when sequence empty; live enable on Save | UIR-105 | | | |
| MT-W11 | Context-menu "Boot into CP/M" runs sequence + re-probes | FR-049, UIR-105 | | | |
| MT-W12 | Terminal grid reflows to the window size | FR-091a | | | |
| MT-W13 | Context-menu Font… dialog lists usable (family/style/size scroll, not collapsed); change applies live, reflows, persists | UIR-069, UIR-099 | | | |
| MT-W16 | Terminal Type (Config → Terminal) VT52/ADM-3A renders + encodes cursor keys per type; switch back to VT100 | UIR-034, UIR-103a, FR-157i/j, FR-158a/b | | | |
| MT-W17 | Right-click menu (6 items, Copy greyed w/o selection); drag-select + Copy → clipboard; Paste → Terminal Port (EOL-normalised) | UIR-099/100, FR-165/166 | | | |
| MT-W18 | Right-click Clear Window / Font… / Reset Size (24×80) reflows grid to 80×24 | UIR-099, FR-095, UIR-069, FR-167 | | | |
| MT-W19 | Terminal Type submenu (VT100/VT52/ADM-3A; active checked); selecting switches emulation live; status bar updates | UIR-099/101, UIR-034, UIR-106 | | | |
| MT-W20 | Macros submenu lists configured macros + runs script; disabled when none | UIR-099/102, FR-162 | | | |
| MT-W21 | Terminal/History windows reopen on start-up when open at exit | FR-168 | | | |

### §13 File context-menu actions
| ID | Title | Req | Result | Env | Notes |
|----|-------|-----|:------:|:---:|-------|
| MT-F01 | Menu contents/order both panes | UIR-018/019 | | | |
| MT-F01a | Multi-select disables View/Rename | FR-110/111, UIR-018/019 | | | |
| MT-F02 | Host View/Edit via viewer_cmd | FR-112 | | | |
| MT-F03 | Empty viewer_cmd → OS default | FR-112 | | | |
| MT-F04 | Host Rename real dialog + effect | UIR-057, FR-114/116/118 | | | |
| MT-F05 | Host Delete read-only dialog + effect | UIR-057, FR-115/116/118 | | | |
| MT-F05a | Host multi-file Delete (all selected) | FR-110/115/116/118 | | | |
| MT-F06 | Remote Rename/Delete commands | FR-117/118 | | | |
| MT-F06a | Remote multi-file Delete (ERA per file) | FR-111/115/117/118 | | | |
| MT-F07 | Remote action with port closed | FR-117 | | | |
| MT-F08 | Remote View downloads then opens | FR-113/112 | | | |
| MT-F09 | Multi-file To Remote/To Host transfer | FR-119/106/107 | | | |

### §14 Internationalisation (Language)
| ID | Title | Req | Result | Env | Notes |
|----|-------|-----|:------:|:---:|-------|
| MT-I01 | Language submenu lists languages, active checked | FR-122, UIR-003/077 | | | |
| MT-I02 | Switch language re-translates UI live | FR-123 | | | |
| MT-I03 | Dialogs/menus translated in chosen language | FR-121/123 | | | |
| MT-I04 | Option values/commands NOT translated | CR-015 | | | |
| MT-I05 | Language choice persists across restart | FR-124 | | | |
| MT-I06 | New lang file discovered, no code change | FR-121, NFR-005 | | | |

### §15 Theme, layout, window state (visual)
| ID | Title | Req | Result | Env | Notes |
|----|-------|-----|:------:|:---:|-------|
| MT-V01 | Material theme consistent everywhere | UIR-070, CR-013 | | | |
| MT-V02 | OS light/dark variant selected | UIR-073 | | | |
| MT-V03 | Toolbar buttons labelled/iconned | UIR-071 | | | |
| MT-V04 | Splitter re-apportions panes | UIR-072 | | | |
| MT-V05 | Status-bar indicators green=connected/red=not | UIR-074 | | | |
| MT-V06 | Long status truncated to 127 | UIR-014 | | | |
| MT-V07 | Window/dialog geometry restored | FR-004 | | | |
| MT-V08 | Exit closes ports + all windows | FR-015/016 | | | |
| MT-V09 | Dialog button layout (Cancel left / affirmative right; lone centred) | UIR-075 | | | |
| MT-V10 | About dialog (name/version/GitHub link/OK; version matches) | FR-022, UIR-076, DR-040/041 | | | |
| MT-V11 | Branded app icon on all windows + taskbar/dock | UIR-078, DR-044 | | | |
| MT-V12 | Temp `cpm_fm*` folders removed on exit + swept at start-up | FR-016, FR-113a, FR-171 | | | |

### §16 Cross-cutting / non-functional
| ID | Title | Req | Result | Env | Notes |
|----|-------|-----|:------:|:---:|-------|
| MT-N01 | Debug logging OFF/ON on stdout | FR-088 | | | |
| MT-N02 | Cross-platform smoke + transfer | STR-003, CR-012 | | | |
| MT-N03 | No freeze / no cross-thread Qt warnings | NFR-001/004 | | | |

### Roll-up
| Section | P | F | B | NA | NT |
|---------|--:|--:|--:|---:|---:|
| §4 Smoke | | | | | |
| §5 Connect/disconnect | | | | | |
| §6 Serial config | | | | | |
| §7 General config | | | | | |
| §8 Load/save | | | | | |
| §9 Host files | | | | | |
| §9.1 Filter & sort | | | | | |
| §10 Remote listing | | | | | |
| §11 Transfers | | | | | |
| §11.5 Backup & restore | | | | | |
| §12 Terminal Window | | | | | |
| §13 Context actions | | | | | |
| §14 Internationalisation | | | | | |
| §15 Theme/layout | | | | | |
| §16 Non-functional | | | | | |
| **Total** | | | | | |

---

## 4. Fault Reports (one block per Fail / Blocked)

> Copy the block below for each failing case. The more literal the better — paste exact dialog text and
> console output rather than describing it. Anything you can't capture, mark "n/a".

### Fault Report — MT-____

| Field | Value |
|-------|-------|
| Case ID | MT- |
| Title | |
| Result | F / B |
| Severity | Blocker (can't proceed) · Major (feature broken) · Minor (cosmetic/edge) |
| Reproducibility | Always · Intermittent (≈ __ of __ tries) · Once |
| Connectivity option | A / B / C |
| Entry point | `cpm-fm` / `python -m cpm_fm` |

**Step at which it failed** (which numbered step / which Expected bullet):

```
```

**Expected** (from the plan):

```
```

**Actual** (what really happened):

```
```

**Exact dialog / status-bar text** (verbatim, including title bar):

```
```

**Console / stdout-stderr** (run via `python -m cpm_fm`; paste the traceback or relevant lines.
For transfer/timing/parser bugs, set Debug Logging ON — UIR-050 — and include the verbose trace):

```
```

**Terminal Window contents** (if relevant — paste the Receive area; for transfer-traffic bugs the
`<HH>` hex echo is gold for diagnosing X-Modem handshake/timing — MT-T09/T10):

```
```

**Config in use** (paste the JSON, or attach the file path; redact nothing serial-relevant):

```json
```

**Serial-line evidence** (if a bus analyser / `com0com` log / `socat -x` capture is available — bytes
on the wire, baud, flow-control state). Optional but decisive for FR-076/087/089/109/NFR-003a–q issues:

```
```

**Screenshot / screen recording** (attach for visual cases — UIR/theme/layout; reference filename):

```
```

**Timing details** (for FR-076 capture, FR-089 launch delay, FR-109 inter-file: what delays were
configured, and how long things actually took):

```
```

**File-integrity details** (for transfers — file name, size in bytes, and result of a binary compare
host↔remote; note the X-Modem mode negotiated: checksum / CRC / 1K, if known):

```
```

**Tester's suspected cause / area** (optional — your hunch helps, even if wrong):

```
```

---

## 5. Environment & blocker notes

> Anything that affected the whole run: hardware quirks, ports that wouldn't enumerate, an emulator
> limitation, cases you couldn't set up (and why), OS-specific oddities. This context prevents
> misreading an environment limitation as an application bug.

```
```
