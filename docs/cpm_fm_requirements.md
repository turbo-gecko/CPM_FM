<!-- CONTEXT NOTE FOR LLMs: This file is large. Do NOT load it whole.
     For broad understanding read docs/requirements_views/requirements_index.md;
     for a specific file's requirements use docs/requirements_views/code_to_requirements.md.
     For architecture/design (module structure, layering, toolkit, threading model)
     see the companion docs/cpm_fm_architecture.md (holds the CR-/NFR- constraints).
     Open this spec only for the exact wording of a specific requirement. -->

# CP/M File Manager — Software Requirements Specification

| Field | Value |
|-------|-------|
| Document title | CP/M File Manager Software Requirements Specification (SRS) |
| Document ID | CPM-FM-SRS |
| Version | 2.18.0 |
| Status | Reviewed |
| Standard | ISO/IEC/IEEE 29148:2018 |
| Owner | Project maintainer |
| Date | 2026-07-01 |
| Source documents | `docs/legacy/App_Requirements.md`, `docs/legacy/App_Design.md` (archived) |

---

## 1. Introduction

### 1.1 Purpose
This Software Requirements Specification (SRS) defines the functional, interface, data, and
non-functional requirements for the **CP/M File Manager** (`cpm-fm`) application. It consolidates and
restructures the requirements previously held in `docs/legacy/App_Requirements.md` and `docs/legacy/App_Design.md`
into a single, uniquely identified and traceable requirement set conforming to ISO/IEC/IEEE 29148.

### 1.2 Scope
`cpm-fm` is a cross-platform desktop GUI application written in Python that transfers files between a
modern host system and a legacy CP/M system over a serial communications link using the X-Modem
protocol. The application provides a graphical file manager, a serial terminal, and serial/general
configuration management. As of v1.3 the graphical user interface is implemented with **PySide6
(Qt for Python)** using a Material Design visual theme (see CR-012, CR-013, UIR-070–UIR-073); prior
baselines used Tkinter.

### 1.3 Product overview
The product presents a host file list and a remote file list side by side, with controls to connect
to the remote CP/M system, list remote files, and transfer single or multiple files in both directions via the X-Modem protocol. It provides basic file management capabilities, including renaming, deleting, and viewing local and remote files, and whole-drive **Backup** and **Restore** operations that mirror every file between the remote drive and the host directory.
A non-modal terminal window enables direct serial interaction with the remote system.
The application includes comprehensive serial and general configuration management and supports a multi-language user interface.

### 1.4 Definitions and abbreviations
| Term | Definition |
|------|------------|
| Host | The modern computer running `cpm-fm`. |
| Remote | The legacy CP/M system connected over serial. |
| Terminal Port | The serial port used for CP/M terminal commands. |
| Transport / Transfer Port | The serial port used for X-Modem file transfers (may be the same physical port as the Terminal Port). |
| EOL | End of Line terminator character(s): CR, LF, or CR/LF. |
| X-Modem | The 128-byte, checksum-mode serial file transfer protocol used by this product. |
| SRS | Software Requirements Specification. |
| Qt / PySide6 | The Qt 6 GUI toolkit and its official Python bindings (PySide6), used to implement the GUI from v1.3 onward. |
| QSS | Qt Style Sheets — the CSS-like styling mechanism Qt uses for theming. |
| Material | The Material Design visual theme applied to the Qt widgets (via the `qt-material` stylesheet). |
| Snapshot | A point-in-time read of a file listing captured before a destructive operation begins, used to ensure the operation works against a fixed set of files regardless of subsequent filesystem changes (see FR-151). |

### 1.5 Requirement identification scheme
Requirements are uniquely identified using the prefixes below. Each requirement is atomic, verifiable,
and traceable to its source document section.

| Prefix | Category |
|--------|----------|
| `STR-` | Stakeholder / purpose requirement |
| `FR-`  | Functional requirement |
| `UIR-` | User interface requirement |
| `IFR-` | External interface requirement |
| `DR-`  | Data requirement |
| `CR-`  | Design constraint |
| `NFR-` | Non-functional requirement |

### 1.6 Verification methods
Each requirement specifies a verification method: **T** (Test), **D** (Demonstration),
**I** (Inspection), or **A** (Analysis).

### 1.7 Priority scheme
Priority is one of **Mandatory**, **Desirable**, or **Optional**.

---

## 2. Stakeholder / Product Requirements

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| STR-001 | The product shall enable the transfer of files between the host system and a remote CP/M system over a serial communications link. | Mandatory | D | App_Design §Purpose |
| STR-002 | The product shall provide a graphical user interface implemented in Python, using the PySide6 (Qt for Python) toolkit (see CR-012). | Mandatory | I | App_Design §Purpose; v1.3 UI migration; impl. `app.py:MainWindow`, `app.py:main` |
| STR-003 | The product shall be cross-platform. | Desirable | A | App_Design §Purpose |

---

## 3. Functional Requirements

### 3.1 Application lifecycle and state

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| FR-001 | The application shall maintain a Terminal status flag indicating whether the Terminal Port is open and available for communication. The default value at startup shall be *not set* (false). | Mandatory | T | App_Design §Program state; impl. `serial_manager.py:__init__` |
| FR-002 | The application shall maintain a Transport status flag indicating whether the Transport Port is open and available for communication. The default value at startup shall be *not set* (false). | Mandatory | T | App_Design §Program state; impl. `serial_manager.py:__init__` |
| FR-003 | The application shall start in an unconfigured state, with serial and general settings populated only via File > Load, the configuration dialogs, or the automatic reload of the last-used configuration file (FR-005). When no last-used configuration file is remembered, or the remembered file no longer exists or cannot be parsed, the application shall start unconfigured. | Mandatory | T | App_Design §Program state; CLAUDE.md; impl. `app.py:__init__` |
| FR-004 | On exit, the application shall persist the size and position (geometry) of each of its windows and dialogs — the main window, the Terminal Window, and the Serial and General Configuration Dialogs — to host-native persistent storage, and shall restore each window's saved geometry the next time that window is shown. The Host/Remote splitter position is excluded (UIR-072). Geometry is stored via `QSettings` under organisation `turbo-gecko`, application `cpm-fm`. | Mandatory | T | impl. `app.py:__init__`, `app.py:closeEvent`, `config_dialogs.py:__init__`, `config_dialogs.py:done`, `window_state.py:WindowState`, `window_state.py:__init__`, `window_state.py:save_geometry`, `window_state.py:restore_geometry` |
| FR-005 | The application shall remember the filesystem path of the most recently loaded (FR-010) or saved (FR-013) configuration file and, on the next startup, automatically reload and apply that file (subject to FR-003). The remembered path is persisted via `QSettings` alongside the window geometry (FR-004). | Mandatory | T | impl. `mw_config.py:load_config`, `mw_config.py:menu_save` |
| FR-006 | The application shall remember the folder of the most recently loaded (FR-010) or saved (FR-013) configuration file and shall default the File > Load and File > Save dialogs to that folder. This remembered config folder is persisted via `QSettings` alongside the window geometry (FR-004) and is maintained separately from the Host Files directory (FR-060). When no config folder is remembered, the dialogs default to the host system's standard behaviour (current working directory). | Mandatory | T | impl. `mw_config.py:menu_load`, `mw_config.py:menu_save`, `window_state.py:last_config_dir` |

### 3.2 File menu

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| FR-010 | The File > Load menu item shall present a file-select dialog defaulting to the JSON file type for selecting a configuration file to load. The dialog shall open in the last-used config folder (FR-006). | Mandatory | D | App_Requirements §Load; impl. `mw_config.py:menu_load` |
| FR-011 | On loading a configuration file, the application shall replace its entire internal settings store with the contents of the file (a full replace, not a per-key merge). | Mandatory | T | impl. `mw_config.py:load_config`, `config_handler.py:load_json`; tests `test_config_handler.py` |
| FR-012 | Settings keys present in a loaded file that are not consumed by the application shall be retained verbatim in the settings store but shall not alter application behaviour; the application shall not reject a file on account of unrecognised keys. | Mandatory | T | impl. `mw_config.py:load_config`, `config_handler.py:load_json`; tests `test_config_handler.py` |
| FR-013 | The File > Save menu item shall present a file-select dialog defaulting to the JSON file type for selecting a configuration file to save to. The dialog shall open in the last-used config folder (FR-006). | Mandatory | D | App_Requirements §Save; impl. `mw_config.py:menu_save` |
| FR-014 | On saving, the application shall write the **entire** internal settings store — both serial configuration and general configuration settings — to the selected file in JSON format. This is the full-store save, in contrast to the per-group saves performed by the configuration dialogs' own Save buttons (FR-020a, FR-021a). | Mandatory | T | App_Requirements §Save; impl. `mw_config.py:menu_save`, `config_handler.py:save_json`; tests `test_config_handler.py`, `test_gui_smoke.py` |
| FR-015 | The File > Exit menu item shall close any open COM ports. | Mandatory | D | App_Requirements §Exit; impl. `app.py:closeEvent`, `serial_manager.py:close_ports` |
| FR-016 | The File > Exit menu item shall close all open dialogs and windows. | Mandatory | D | App_Requirements §Exit; impl. `app.py:closeEvent` |
| FR-017 | On loading a configuration file, the application shall clear the Remote Files list. The previously displayed remote listing was captured under the prior configuration (potentially a different port, drive, or system) and is no longer valid (consistent with the empty-at-startup state, FR-070). | Mandatory | T | impl. `mw_config.py:load_config` |
| FR-018 | The File > New menu item (presented at the top of the File menu) shall first save the current configuration: to the most recently loaded/saved configuration file (FR-005) if one is remembered, otherwise via the Save dialog (FR-013). If no file is chosen, or the save fails, the File > New action shall be cancelled and the current configuration, ports, and lists shall be retained. | Mandatory | T | App_Requirements §New; impl. `mw_config.py:menu_new`, `mw_config.py:_save_to_path` |
| FR-019 | After the current configuration has been successfully saved (FR-018), the File > New menu item shall: close any open Terminal and Transport ports following the Disconnect behaviour (FR-050–FR-058); clear the Remote Files list (consistent with FR-070); replace the entire settings store with the default configuration (a full replace, per FR-011); forget the remembered configuration file path; and refresh the Host Files list to the default host directory (FR-060). | Mandatory | T | impl. `mw_config.py:menu_new`, `config_handler.py:DEFAULT_SETTINGS` |

### 3.3 Config menu

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| FR-020 | When the Config > Serial menu option is selected, the application shall present the Serial Configuration Dialog to allow the user to modify the serial settings. | Mandatory | D | App_Requirements §Serial; impl. `mw_config.py:menu_serial_config`, `config_dialogs.py:save` |
| FR-020a | When the Serial Configuration Dialog's Save button is pressed, the application shall update the running session's serial settings and shall persist **only** the serial settings to the currently active/loaded configuration file (FR-005), leaving every other setting already in that file unchanged. It shall **not** present a file-select dialog and shall **not** write the general settings. If no configuration file is currently loaded, the application shall apply the serial settings to the running session only, display a warning dialog informing the user that no configuration file is loaded and that File > Save (FR-013) must be used to persist the settings, and write no file. *(v2.13.)* | Mandatory | T | impl. `mw_config.py:menu_serial_config`, `mw_config.py:_save_subset_to_active_config`, `config_dialogs.py:save`; tests `test_gui_smoke.py` |
| FR-021 | When the Config > General menu option is selected, the application shall present the General Configuration Dialog to allow the user to modify the general settings. | Mandatory | D | App_Requirements §General; impl. `mw_config.py:menu_general_config`, `config_dialogs.py:save` |
| FR-021a | When the General Configuration Dialog's Save button is pressed, the application shall update the running session's general settings and shall persist **only** the general settings to the currently active/loaded configuration file (FR-005), leaving every other setting already in that file (including the serial settings) unchanged. It shall **not** present a file-select dialog and shall **not** write the serial settings. If no configuration file is currently loaded, the application shall apply the general settings to the running session only, display a warning dialog informing the user that no configuration file is loaded and that File > Save (FR-013) must be used to persist the settings, and write no file. *(v2.13.)* | Mandatory | T | impl. `mw_config.py:menu_general_config`, `mw_config.py:_save_subset_to_active_config`, `config_dialogs.py:save`; tests `test_gui_smoke.py` |

### 3.4 Help menu

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| FR-022 | When the Help > About menu item is selected, the application shall present the modal About Dialog (UIR-076). *(v1.10.)* | Mandatory | T | impl. `mw_config.py:menu_about`, `gui/about_dialog.py:AboutDialog` |
| FR-023 | When the Help > Manual menu item is selected, the application shall present the user manual in the Manual Window (UIR-091). If the window is already open, it shall be raised and activated rather than opening a second copy. *(v2.13.)* | Mandatory | T | impl. `mw_config.py:menu_manual`, `gui/manual_dialog.py:ManualDialog` |

### 3.5 Connecting to the remote system

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| FR-030 | When the Connect button is pressed, the application shall open the Terminal Port serial port if it is not already open. | Mandatory | T | App_Requirements §Connecting; impl. `mw_remote.py:do_connect`, `serial_manager.py:open_port`; tests `test_serial_manager.py` (parity map, numeric coercion, nested-key fallbacks, open-failure) |
| FR-031 | If the Terminal Port cannot be opened, the application shall display an error dialog containing the text "Terminal port is unable to be opened" and cancel the current workflow. | Mandatory | T | App_Requirements §Connecting; impl. `mw_remote.py:do_connect` |
| FR-032 | If the Terminal Port is successfully opened, the application shall set the Terminal status flag to true. | Mandatory | T | App_Design §Connecting; impl. `mw_remote.py:do_connect`, `serial_manager.py:open_port` |
| FR-033 | If the Terminal Port cannot be opened, the application shall set the Terminal status flag to false. | Mandatory | T | App_Design §Connecting |
| FR-034 | When the Terminal Port is opened, the application shall display the text "Terminal port open" in the status bar. | Mandatory | D | App_Requirements §Connecting; impl. `mw_remote.py:do_connect` |
| FR-035 | *Removed in v1.2.* (Was: "When the Connect button is pressed, the application shall open the Terminal Window.") The Terminal Window is opened exclusively via the Terminal button (FR-097); the Connect action does not open it. See the Issue Resolution Log, OI-10. | — | — | superseded by FR-097 |
| FR-036 | The application shall render data received from the Terminal Port on the Receive view of the Terminal Window as specified by FR-091 (the VT-100/ANSI screen model). *(v2.17: was a plain-text append to a receive text area; now deferred to the FR-091 screen model.)* | Mandatory | T | App_Requirements §Connecting; impl. `serial_manager.py:_read_loop`, `app.py:_on_term_write`; tests `test_serial_manager.py`, `test_vt100_engine.py` |
| FR-037 | On connect, if the Transport Port is the same as the Terminal Port, the application shall set the Transport status flag to connected. | Mandatory | T | App_Design §Connecting; impl. `mw_remote.py:do_connect` |
| FR-038 | On connect, if the Transport Port is different from the Terminal Port and is not currently open, the application shall attempt to open the Transport Port. | Mandatory | T | App_Design §Connecting; impl. `mw_remote.py:do_connect`, `serial_manager.py:open_port` |
| FR-039 | If the Transport Port cannot be opened, the application shall display an error dialog containing the text "Transport port is unable to be opened". | Mandatory | T | App_Design §Connecting; impl. `mw_remote.py:do_connect` |
| FR-040 | If the Transport Port is successfully opened, the application shall set the Transport status flag to connected. | Mandatory | T | App_Design §Connecting; impl. `mw_remote.py:do_connect`, `serial_manager.py:open_port` |
| FR-041 | After the Connect workflow has set both the Terminal status flag (FR-032) and the Transport status flag (FR-037/FR-040) to connected, the application shall probe whether the remote file system is reachable by sending the configured EOL character(s) on the Terminal Port with no preceding command and capturing the response using the FR-076 wait mechanism, expecting a CP/M drive prompt (DR-033) to appear. The probe and its retry (FR-043) run on a worker thread, with all UI updates marshalled back via Qt signals (NFR-004). While the probe is running the status bar shall display "Checking remote file system". *(v2.15.)* | Mandatory | T | impl. `mw_remote.py:do_connect`, `mw_remote.py:_do_connect_probe_logic`, `mw_remote.py:_capture_terminal_response`, `cpm_parser.py:drive_prompt_letter` |
| FR-042 | If a drive prompt is detected, the application shall set the remote drive-selection drop-down (UIR-017) to the returned drive letter (DR-033a) and populate the Remote Files list for that drive following the "Populating remote file list" process (FR-074–FR-079), then continue normally. | Mandatory | T | impl. `mw_remote.py:_on_connect_probe_ok`, `mw_remote.py:refresh_remote_files`, `connect_probe_ok` signal |
| FR-043 | If no drive prompt is detected, the application shall send the configured EOL character(s) on the Terminal Port once more and re-capture the response (exactly one retry). | Mandatory | T | impl. `mw_remote.py:_do_connect_probe_logic` |
| FR-044 | If no drive prompt is detected after the retry (FR-043), the application shall first attempt boot-sequence recovery (FR-048) when a non-empty boot sequence is configured; if no boot sequence is configured, or the post-recovery probe still detects no drive prompt, the application shall inform the user that it cannot access the remote computer's file system by presenting the modal Remote Filesystem Unavailable dialog (UIR-092). *(v2.16: boot-sequence recovery inserted ahead of the dialog.)* | Mandatory | T | impl. `mw_remote.py:_do_connect_probe_logic`, `mw_remote.py:_on_connect_probe_failed`, `connect_probe_failed` signal, `gui/remote_unavailable_dialog.py:RemoteUnavailableDialog` |
| FR-045 | The Remote Filesystem Unavailable dialog (UIR-092) shall offer three actions and the application shall act on the chosen one: **Abort** shall abort the connection and close the comm port(s) following the Disconnect close behaviour (FR-050–FR-057) and clear the Remote Files list; **Continue** shall take no action, leaving the port(s) open and the Remote Files list empty; **Terminal** shall open the Terminal Window (FR-097) for debugging, leaving the port(s) open. | Mandatory | T | impl. `mw_remote.py:_on_connect_probe_failed`, `mw_remote.py:do_disconnect`, `mw_remote.py:show_terminal` |
| FR-046 | The remote-file-system probe (FR-041–FR-045) shall be performed only when both the Terminal and Transport status flags are connected; if the Transport Port failed to open (FR-039), no probe shall be performed. | Mandatory | T | impl. `mw_remote.py:do_connect` |
| FR-047 | The application shall support an optional, user-configured **boot sequence** (the `boot_sequence` setting, UIR-059; default empty) that, when executed, drives a remote computer into CP/M by transmitting keystrokes on the Terminal Port. The sequence is a newline-separated script processed one directive per line; blank lines and lines whose first non-whitespace character is `#` are ignored. The supported directives (keyword case-insensitive) are: **`SEND <text>`** — transmit `<text>` followed by the configured EOL (UIR-047); **`SENDRAW <hh> [hh …]`** — transmit the given raw bytes (space-separated two-digit hex) with no EOL appended, for control keys such as `03` (Ctrl-C) or `1B` (ESC); **`WAIT <seconds>`** — pause for the given number of seconds (decimal permitted); **`WAITFOR <text> [seconds]`** — capture Terminal Port output until `<text>` appears or the optional timeout (default 10 s) elapses. An empty `boot_sequence` disables the feature entirely, so that FR-048 and FR-049 become no-ops. Execution runs on a worker thread with all UI updates marshalled via Qt signals (NFR-004). *(v2.16.)* | Mandatory | T | impl. `terminal/boot_sequence.py:parse_boot_sequence`, `mw_remote.py:run_boot_sequence` |
| FR-048 | If the post-connect probe detects no drive prompt after its retry (FR-043) and a non-empty boot sequence is configured (FR-047), the application shall execute the boot sequence and then repeat the probe once (the FR-041/FR-043 mechanism). If this post-recovery probe detects a drive prompt the application shall continue normally (FR-042); only if it still detects none shall the Remote Filesystem Unavailable dialog be presented (FR-044). Recovery is attempted at most once per Connect, so it cannot loop; if no boot sequence is configured, no recovery is attempted and FR-044 applies directly. *(v2.16.)* | Mandatory | T | impl. `mw_remote.py:_do_connect_probe_logic`, `mw_remote.py:run_boot_sequence` |
| FR-049 | When the Terminal Window's "Boot into CP/M" button (UIR-068) is pressed, the application shall execute the configured boot sequence (FR-047) on the Terminal Port and then repeat the remote-file-system probe (FR-041/FR-043). On success the remote drive drop-down and Remote Files list shall be updated as in FR-042; on failure the application shall report the failure in the status bar and take no further action (it shall not present the Remote Filesystem Unavailable dialog, since the user is already at the Terminal Window). *(v2.16.)* | Mandatory | T | impl. `mw_remote.py:run_boot_sequence`, `mw_remote.py:show_terminal`, `terminal_window.py:create_widgets` |

### 3.6 Disconnecting from the remote system

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| FR-050 | When the Disconnect button is pressed, the application shall attempt to close the Terminal Port serial port. The close attempt is **unconditional** — it does not depend on the Terminal status flag — so that a Disconnect always tries to release the physical port even if the status flag has drifted out of sync with the real port state. Closing an already-closed port is a safe no-op. *(v2.12: made unconditional for robustness; previously gated on the Terminal status flag — see the Issue Resolution Log, OI-24.)* | Mandatory | T | App_Requirements §Disconnecting; impl. `mw_remote.py:do_disconnect`, `serial_manager.py:close_terminal_port`; tests `test_serial_manager.py`, `test_gui_smoke.py` |
| FR-051 | If the Terminal Port cannot be closed, the application shall display an error dialog containing the text "Terminal port is unable to be closed" and cancel the current workflow. | Mandatory | T | App_Requirements §Disconnecting; impl. `mw_remote.py:do_disconnect` |
| FR-052 | When the Terminal Port is closed, the application shall set the Terminal status flag to false. | Mandatory | T | App_Design §Disconnecting; impl. `mw_remote.py:do_disconnect`, `serial_manager.py:close_terminal_port`; tests `test_serial_manager.py` |
| FR-053 | When the Terminal Port is closed, the application shall display the text "Terminal port closed" in the status bar. | Mandatory | D | App_Requirements §Disconnecting; impl. `mw_remote.py:do_disconnect` |
| FR-054 | On disconnect, if the Transport Port is the same as the Terminal Port, the application shall set the Transport status flag to false. | Mandatory | T | App_Design §Disconnecting; impl. `mw_remote.py:do_disconnect` |
| FR-055 | On disconnect, if the Transport Port is different from the Terminal Port, the application shall attempt to close the Transport Port. As with FR-050 this attempt is **unconditional** (independent of the Transport status flag); closing an already-closed port is a safe no-op. *(v2.12: made unconditional for robustness — see the Issue Resolution Log, OI-24.)* | Mandatory | T | App_Design §Disconnecting; impl. `mw_remote.py:do_disconnect`, `serial_manager.py:close_transport_port`; tests `test_serial_manager.py` |
| FR-056 | If the Transport Port cannot be closed, the application shall display an error dialog containing the text "Transport port is unable to be closed". | Mandatory | T | App_Design §Disconnecting; impl. `mw_remote.py:do_disconnect` |
| FR-057 | If the Transport Port is successfully closed, the application shall set the Transport status flag to false. | Mandatory | T | App_Design §Disconnecting; impl. `mw_remote.py:do_disconnect`, `serial_manager.py:close_transport_port`; tests `test_serial_manager.py` |
| FR-058 | On disconnect, once the Terminal Port has been successfully closed, the application shall clear the Remote Files list. The listing was read over the now-closed Terminal Port and reflects the disconnected system, so it is no longer valid (consistent with the empty-at-startup state, FR-070). The list shall not be cleared if the Terminal Port could not be closed and the disconnect was cancelled (FR-051). | Mandatory | T | impl. `mw_remote.py:do_disconnect` |

### 3.7 Host file management

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| FR-060 | On startup, the application shall populate the Host Files list with the files in the host directory specified in the loaded configuration file; if no configuration is loaded or no path is specified, it shall default to the current working directory of the host system. | Mandatory | T | App_Requirements §Host Files; impl. `mw_file_panes.py:refresh_host_files`, `mw_config.py:load_config` |
| FR-061 | The Change Directory button shall be enabled at startup. | Mandatory | I | App_Requirements §Change Directory; impl. `app.py:setup_toolbar` |
| FR-062 | When the Change Directory button is pressed, the application shall present a folder-select dialog for the user to choose the folder whose contents are loaded into the Host Files list. This action updates the active session directory but does not persist the change to the configuration file until File > Save is invoked. | Mandatory | D | App_Requirements §Change Directory; impl. `mw_file_panes.py:change_host_dir` |
| FR-063 | When the Host Files group's "Update" button (beside the "Change Directory" button — UIR-011) is pressed, the application shall refresh the Host Files list from the current host directory only. It shall **not** affect the Remote Files list. *(v2.1.1: the button was relabelled from "Refresh Host" to "Update" and moved from the row beneath the Host Files list to beside "Change Directory".) (v2.12: corrected to refresh the Host Files list only — it previously also re-populated the Remote Files list, which was unexpected; see the Issue Resolution Log, OI-14.)* | Mandatory | T | impl. `mw_file_panes.py:refresh_host_files`, `setup_layout` |

### 3.8 Remote file listing

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| FR-070 | The Remote Files list shall be empty (unpopulated) at startup. | Mandatory | T | App_Requirements §Remote Files |
| FR-071 | The Update button shall be enabled at startup. | Mandatory | I | App_Requirements §Update |
| FR-072 | The Update button (Host Files group — UIR-011) shall be enabled at startup. | Mandatory | I | App_Requirements §Refresh |
| FR-073 | When the Update button (in the Remote Files group) is pressed, the application shall switch the remote to the drive currently shown in the drive-selection drop-down (UIR-017) and populate the Remote Files list, behaving exactly as if that drive letter had just been selected (the remote drive-change process, FR-100–FR-104). This ensures the listing always matches the displayed drive even if the remote's current drive was changed directly in the Terminal Window. It shall not affect the Host Files list. *(v1.7.2: Update now re-issues the displayed drive before listing — previously it listed the remote's then-current drive, which could differ from the drop-down. See the Issue Resolution Log, OI-22.)* | Mandatory | T | App_Requirements §Update; impl. `mw_remote.py:refresh_remote_files`, `mw_remote.py:_do_change_drive_logic` |
| FR-074 | If the Terminal Port is not open when populating the remote file list, the application shall set the status bar text to "Terminal port not open - cannot read file list" and clear the Remote Files list. | Mandatory | T | App_Requirements §Populating remote file list; impl. `mw_remote.py:refresh_remote_files` |
| FR-075 | If the Terminal status flag is true, the application shall send the configured List Files command followed by the configured EOL character(s) to the Terminal Port. The command is reflected in the receive text area by the remote's echo of the command over the serial link (or, if enabled, by local echo — FR-093); the application does not write the command to the receive area itself. *(v1.7.1: reworded to the as-built echo behaviour — see the Issue Resolution Log, OI-21.)* | Mandatory | T | App_Design §Populating remote file list; impl. `mw_remote.py:_capture_terminal_response` |
| FR-076 | After sending the List Files command, the application shall wait at least one second for output to begin accumulating, then continue waiting until the remote capture buffer has received no new data within an idle window of 0.5 s (the buffer "times out"), bounded by a maximum total wait of 10 s, before processing the received text. | Mandatory | T | App_Design §Populating remote file list; impl. `mw_remote.py:_capture_terminal_response` |
| FR-077 | The application shall process the captured remote output into a dictionary of filenames using the CP/M 4-column DIR parsing algorithm (see §6). | Mandatory | T | App_Design §Populating remote file list; impl. `mw_remote.py:_do_refresh_remote_logic`, `cpm_parser.py:parse_dir_output`; tests `test_cpm_parser.py` |
| FR-078 | The application shall populate the Remote Files list with the entries produced by the parsing algorithm, displaying the dictionary keys (filenames) sorted in ascending alphabetical order. *(v2.6: this ascending-alphabetical order is the **default** display; the list is rendered through the pane's filter/sort controls — FR-130–FR-133 — which default to no filter and Name-ascending, reproducing this behaviour.)* | Mandatory | T | App_Design §Populating remote file list; impl. `mw_remote.py:_update_remote_list_ui`, `mw_file_panes.py:_apply_remote_view` |
| FR-079 | On successful population of the remote file list, the application shall update the status bar with the text "Remote file list updated". | Mandatory | D | App_Requirements §Populating remote file list; impl. `mw_remote.py:_do_refresh_remote_logic`, `mw_remote.py:_update_remote_list_ui` |

### 3.8.1 Remote drive selection

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| FR-100 | When a drive letter is selected from the drive-selection drop-down (UIR-017), the application shall send that drive letter followed by `:` and the configured EOL character(s) to the Terminal Port. As with FR-075, the command is reflected in the receive text area by the remote's echo (or local echo, FR-093); the application does not write the command to the receive area itself. *(v1.7.1: reworded to the as-built echo behaviour — see the Issue Resolution Log, OI-21.)* | Mandatory | T | impl. `mw_remote.py:change_drive`, `mw_remote.py:_do_change_drive_logic`, `mw_remote.py:_capture_terminal_response` |
| FR-101 | After sending the drive-change command, the application shall capture the Terminal Port response using the same wait mechanism as FR-076, ignoring any blank lines returned by the terminal. | Mandatory | T | impl. `mw_remote.py:_capture_terminal_response`; `cpm_parser.py:has_drive_prompt`; tests `test_cpm_parser.py` |
| FR-102 | If a drive prompt of the form `<letter>>` (the selected drive letter followed by `>`) appears in the captured response, the application shall populate the Remote Files list following the "Populating remote file list" process (FR-074–FR-079), as if the Update button had been pressed. | Mandatory | T | impl. `mw_remote.py:_do_change_drive_logic`, `mw_remote.py:_do_refresh_remote_logic` |
| FR-103 | If the `<letter>>` drive prompt does not appear in the captured response, the application shall clear the Remote Files list and display a modal dialog with an OK button whose message names the selected drive, of the form "Drive `<letter>`: not found" (e.g. "Drive B: not found"). | Mandatory | T | impl. `mw_remote.py:_do_change_drive_logic`, `mw_remote.py:_on_drive_not_found`, `drive_not_found` signal |
| FR-104 | If the Terminal Port is not open when a drive is selected, the application shall set the status bar text to "Terminal port not open - cannot read file list" and clear the Remote Files list (consistent with FR-074). | Mandatory | T | impl. `mw_remote.py:change_drive` |

### 3.9 File transfers

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| FR-080 | A file transfer shall be permitted only when both the Terminal status flag and the Transport status flag are set to connected. | Mandatory | T | App_Requirements §File Transfers; App_Design §File Transfers; impl. `mw_transfer_batches.py:do_copy_to_remote`, `mw_transfer_batches.py:do_copy_to_host` |
| FR-081 | The application shall support file transfers in both directions: host-to-remote and remote-to-host. | Mandatory | T | App_Requirements §File Transfers; impl. `mw_transfer_batches.py:_send_one_to_remote`, `mw_transfer_batches.py:_recv_one_to_host`, `xmodem.py:send_file`, `xmodem.py:receive_file`; tests `test_xmodem.py` |
| FR-082 | The application shall use the X-Modem protocol for all file transfers. | Mandatory | T | App_Requirements §File Transfers; impl. `mw_transfer_batches.py:_send_one_to_remote`, `mw_transfer_batches.py:_recv_one_to_host`, `xmodem.py:XModem`, `xmodem.py:send_file`, `xmodem.py:receive_file`; tests `test_xmodem.py` |
| FR-083 | The application shall use the Transport (Transfer) Port for all file transfers. | Mandatory | T | App_Requirements §File Transfers; impl. `mw_transfer_batches.py:_send_one_to_remote`, `mw_transfer_batches.py:_recv_one_to_host`, `xmodem.py:send_file`, `xmodem.py:receive_file`; tests `test_xmodem.py` |
| FR-084 | The Copy to Remote button shall be enabled at startup. | Mandatory | I | App_Requirements §Copy to Remote; impl. `mw_transfer_batches.py:do_copy_to_remote` |
| FR-085 | The Copy to Host button shall be enabled at startup. | Mandatory | I | App_Requirements §Copy to Host; impl. `mw_transfer_batches.py:do_copy_to_host` |
| FR-086 | During an X-Modem file transfer (either direction), the application shall echo every byte sent to or received from the Transport Port to the Terminal Window Receive area, formatted as a hexadecimal byte token of the form `<HH>`, where `HH` is the byte value as two uppercase hexadecimal digits (e.g. byte 0xB5 is displayed as `<B5>`). This echo shall occur only while the Terminal Window exists, and only when the `echo_transfer_data` setting (UIR-058) holds an affirmative value (`ON`/`TRUE`/`1`/`YES`, case-insensitive); the default is off. When the setting is off the transfer byte echo is suppressed, independently of the verbose stdout trace of FR-088. *(v2.2: echo made optional via `echo_transfer_data`, off by default.)* | Mandatory | D | impl. `mw_transfers.py:_on_transfer_bytes`, `mw_transfers.py:_echo_transfer_enabled`; `xmodem.py` monitor hook; UIR-058 |
| FR-087 | Before starting the X-Modem transfer, the application shall launch the CP/M side of the transfer by sending a command on the Terminal Port: `send_remote_cmd` (default `PCGET $1`) for Copy to Remote, and `recv_remote_cmd` (default `PCPUT $1`) for Copy to Host, with the token `$1` replaced by the transferred file's name as shown in the file list. After sending the command the application shall wait the configured launch delay (FR-089) before beginning the X-Modem handshake. The transfer shall then proceed on the Transport Port (FR-083). If the configured command is empty, no command is sent. *(v1.3.1: supersedes the CR-011 deferral of these two settings.)* | Mandatory | T | impl. `mw_transfers.py:_issue_remote_cmd`, `_transfer_to_remote`, `_transfer_to_host`; UIR-045/UIR-046 |
| FR-088 | The application shall emit verbose transfer debug output (per-byte X-Modem trace and transfer flow messages) to standard output only when the `debug_logging` setting holds an affirmative value (`ON`/`TRUE`/`1`/`YES`, case-insensitive); the default is off. | Mandatory | T | impl. `mw_transfers.py:_debug`, `mw_transfers.py:_debug_enabled`, `mw_transfers.py:_on_transfer_bytes`; UIR-050 |
| FR-089 | After launching the CP/M side of a transfer (FR-087), the application shall wait `xfer_launch_delay` seconds (default 3) before sending the first X-Modem start character, so that start-character prompts do not arrive while the remote program is still starting up and not yet servicing its UART. | Mandatory | T | impl. `mw_transfers.py:_launch_delay`; UIR-049 |
| FR-099 | On a **successful** file transfer the application shall automatically refresh the destination file list so the transferred file appears without manual intervention. The per-direction refresh and the failure case are specified by FR-099a–FR-099b. *(v1.3.2: fixes the defect where a transferred file did not appear in the destination list until manually refreshed.)* | Mandatory | T | impl. `app.py:_on_transfer_completed`, `transfer_completed` signal, `_transfer_to_remote`, `_transfer_to_host` |
| FR-099a | After a successful Copy to Host the application shall refresh the Host Files list (per FR-060), and after a successful Copy to Remote it shall refresh the Remote Files list (per the FR-074–FR-079 process). | Mandatory | T | — |
| FR-099b | A failed transfer shall not trigger a refresh. | Mandatory | T | — |
| FR-105 | While an X-Modem file transfer is in progress, the application shall display a modal progress dialog (UIR-051) reporting progress. The dialog content, batch behaviour, auto-close, and threading are specified by FR-105a–FR-105e. *(v1.5; batch support v1.6.)* | Mandatory | T | impl. `xmodem.py` progress hook; `gui/transfer_dialog.py`; `app.py:_on_batch_started`, `_on_transfer_file_started`, `_on_transfer_progress`, `_close_transfer_dialog`, `mw_transfers.py:_on_transfer_progress_cb`, `batch_started`/`transfer_file_started`/`transfer_progress` signals |
| FR-105a | While an X-Modem file transfer (either direction) is in progress, the application shall display a modal progress dialog (UIR-051) showing the name of the file being transferred and the cumulative number of blocks and bytes transferred. | Mandatory | T | — |
| FR-105b | The blocks/bytes count shall be updated after each block is transferred (each acknowledged 128-byte packet on send; each accepted packet on receive). | Mandatory | T | — |
| FR-105c | When a batch of multiple files is transferred (FR-106), a single dialog shall serve the whole batch: it shall additionally show the batch position ("File `i` of `N`"), be created when the batch begins, switch to each successive file, and be closed once when the batch ends. *(v1.6.)* | Mandatory | T | — |
| FR-105d | The application shall close the dialog automatically when the transfer completes, on both success and failure. | Mandatory | T | — |
| FR-105e | Progress updates originate on the transfer worker thread and shall be delivered to the GUI thread via Qt signals (NFR-004). | Mandatory | T | — |
| FR-106 | The Copy to Remote and Copy to Host actions shall transfer **all** files currently selected in the respective file list (the lists are multi-select widgets — UIR-011, UIR-012). If no file is selected when the action is invoked, the application shall display a warning dialog with the body text "Please select one or more files to upload" (Copy to Remote) or "Please select one or more files to download" (Copy to Host) and shall not start a transfer. *(v1.6.)* | Mandatory | T | impl. `mw_transfer_batches.py:do_copy_to_remote`, `mw_transfer_batches.py:do_copy_to_host`, `mw_transfers.py:_selected_filenames` |
| FR-107 | When more than one file is selected, the files shall be transferred **sequentially** over the single Transport Port (FR-083), in the order they appear in the list (top to bottom). Each file shall be launched with its own CP/M-side command (FR-087) and transferred in a separate X-Modem session. *(v1.6.)* | Mandatory | T | impl. `mw_transfer_batches.py:_transfer_to_remote_batch`, `mw_transfer_batches.py:_transfer_to_host_batch`, `mw_transfers.py:_selected_filenames` |
| FR-108 | If any file in a multi-file batch fails to transfer, the application shall abort the batch. The abort and partial-success handling are specified by FR-108a–FR-108b. *(v1.6.)* | Mandatory | T | impl. `mw_transfer_batches.py:_transfer_to_remote_batch`, `mw_transfer_batches.py:_transfer_to_host_batch` |
| FR-108a | On any file's failure the application shall abort the batch — it shall not attempt the remaining files — and shall display an error dialog naming the failed file. | Mandatory | T | — |
| FR-108b | If at least one file in the batch transferred successfully before the failure, the destination file list shall be refreshed once (per FR-099). | Mandatory | T | — |
| FR-109 | In a multi-file batch, before issuing the FR-087 launch command for each file **after the first**, the application shall wait for the Terminal Port output to go idle (the previous CP/M transfer program having finished and the CCP command prompt having returned) and then wait an additional `xfer_interfile_delay` settle period (UIR-052, default 2 s). This prevents the leading characters of the next command from being lost while CP/M is still returning to the prompt and not yet servicing its UART (the multi-file analogue of FR-089). *(v1.6.1.)* | Mandatory | T | impl. `mw_transfers.py:_wait_for_terminal_idle`, `mw_transfers.py:_interfile_delay`, `mw_transfer_batches.py:_transfer_to_remote_batch`, `mw_transfer_batches.py:_transfer_to_host_batch` |

### 3.10 Terminal window — receive and transmit

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| FR-090 | All data received from the Terminal Port shall be accumulated in a receive **data buffer** (the retained raw receive log, `_rx_buffer` — distinct from the rendered character-cell screen of FR-091) that is retained until explicitly cleared by the Terminal Window Clear button (FR-095). Local-echo text (FR-093) is written only to the rendered screen and shall not enter this data buffer. | Mandatory | T | App_Design §Receiving data; impl. `mw_remote.py:handle_terminal_recv`, `_rx_buffer` |
| FR-091 | All data received from the Terminal Port shall be interpreted as a VT-100/ANSI terminal stream and rendered on the Terminal Window's character-cell screen (the Receive view) — including cursor positioning, erase, and character attributes (FR-157). The initial screen geometry is 80 columns × 24 rows; the grid reflows to the Terminal Window size per FR-091a, and a scrollback buffer retaining at least the most recent 1000 lines that have scrolled off the top of the screen is maintained and rendered per UIR-062. The engine behaviour is verified by unit test; the on-screen rendering is demonstrated per UIR-061/UIR-062. *(v2.17: was a plain-text append; now a VT-100 screen model.)* | Mandatory | T | impl. `terminal/vt100_engine.py:VT100Engine`, `gui/terminal_view.py:TerminalView`, `app.py:_on_term_write`, `mw_remote.py:handle_terminal_recv`, `serial_manager.py:_read_loop`; tests `test_vt100_engine.py`, `test_terminal_view.py` |
| FR-091a | The character-cell grid shall reflow to the Terminal Window size: on a Terminal Window resize the visible column and row counts shall be recomputed from the Receive view's viewport and the emulator screen resized to match (subject to a minimum usable grid of 20 columns × 5 rows), preserving on-screen content as far as the new geometry allows. Because the serial link provides no terminal-size-negotiation channel, the remote is **not** notified of the new geometry; remote software that assumes a fixed 80 × 24 page continues to address that page. *(v2.17.)* | Mandatory | T | impl. `gui/terminal_view.py:TerminalView.resizeEvent`, `gui/terminal_view.py:TerminalView._reflow_to_viewport`, `gui/terminal_view.py:grid_size_for`, `terminal/vt100_engine.py:VT100Engine.resize`; tests `test_vt100_engine.py`, `test_terminal_view.py` |
| FR-092 | All data transmitted to the Terminal Port (including the EOL, FR-094) shall be accumulated in a transmit data buffer that is retained until explicitly cleared by the Terminal Window Clear button (FR-095). | Mandatory | T | App_Design §Sending data; impl. `mw_remote.py:handle_terminal_send`, `mw_remote.py:handle_terminal_key`, `_tx_buffer` |
| FR-093 | When the Local Echo checkbox is enabled, transmitted data shall be copied to the Receive view of the Terminal Window — rendered through the engine (FR-091) only, and **not** added to the FR-090 receive data buffer. | Mandatory | T | App_Design §Sending data; impl. `app.py:_on_term_write`, `mw_remote.py:_set_local_echo`, `mw_remote.py:handle_terminal_send`, `mw_remote.py:handle_terminal_key` |
| FR-094 | Line-oriented data sent to the Terminal Port (boot-sequence `SEND`, remote command templates) shall have the configured EOL character(s) appended before being sent; the Enter key in the Terminal Window transmits the configured EOL directly (FR-096/FR-158). *(v2.17: was tied to the transmit field; the field was removed.)* | Mandatory | T | App_Design §Sending data; impl. `mw_remote.py:handle_terminal_send`, `gui/terminal_view.py:encode_key` |
| FR-095 | When the Clear button in the Terminal Window is pressed, the terminal screen shall be reset (cleared, including scrollback) and the receive and transmit data buffers (FR-090, FR-092) shall be cleared. | Mandatory | T | App_Requirements §Terminal Window; impl. `terminal_window.py:clear_text`, `terminal/vt100_engine.py:VT100Engine.reset`, `mw_remote.py:clear_terminal_buffers` |
| FR-096 | Characters and keys typed into the Terminal Window's receive area shall be transmitted to the Terminal Port per keystroke, encoded as their VT-100 byte sequences (FR-158); there is no separate transmit field or Send button. *(v2.17: replaced the transmit field and Send button with live keyboard input.)* | Mandatory | T | App_Requirements §Terminal Window; impl. `gui/terminal_view.py:keyPressEvent`, `gui/terminal_view.py:encode_key`, `mw_remote.py:handle_terminal_key`, `serial_manager.py:send_raw`; tests `test_terminal_view.py`, `test_gui_smoke.py` |
| FR-097 | When the Terminal button in the main window is pressed, the application shall open the Terminal Window if it is not already open, or restore (de-iconify) it if it is hidden. This action shall be independent of the Connect action and shall not require an open Terminal Port. | Mandatory | D | App_Requirements §Main Program GUI; impl. `mw_remote.py:show_terminal` |
| FR-098 | If the Terminal Port is not open when the user types in the Terminal Window, the application shall set the status bar text to "Terminal port not open - cannot send" and not transmit. | Mandatory | T | impl. `mw_remote.py:handle_terminal_key` |
| FR-155 | *Removed in v2.17.* (Was: with the transmit field empty, Send/Enter transmits a bare EOL.) The transmit field was removed with the interactive-keyboard migration; pressing Enter in the Terminal Window now transmits the configured EOL directly (FR-096/FR-094/FR-158). | — | — | superseded by FR-096, FR-158 |
| FR-156 | *Removed in v2.17.* (Was: the transmit field interpreted caret notation `^A`..`^?` for control characters.) The transmit field was removed; control characters are now produced by the corresponding keys and Ctrl-combinations, encoded live (FR-158). | — | — | superseded by FR-158 |
| FR-157 | The terminal shall interpret the VT-100/ANSI control and escape sequences emitted by the remote and render the result on the screen (FR-091). The specific sequence classes and the byte-decoding and robustness rules are specified by FR-157a–FR-157h. Application-cursor-key mode (DECCKM) is not tracked on the render side; the corresponding key-encoding rule is FR-158. *(v2.17.)* | Mandatory | T | impl. `terminal/vt100_engine.py:VT100Engine` (over the `pyte>=0.8.2` runtime dependency); tests `test_vt100_engine.py` |
| FR-157a | The terminal shall interpret cursor positioning and movement sequences — absolute addressing (CUP, `ESC[row;colH`) and relative movement (CUU/CUD/CUF/CUB, `ESC[nA`/`B`/`C`/`D`) — and show/hide the cursor (DECTCEM, `ESC[?25h`/`l`). | Mandatory | T | impl. `terminal/vt100_engine.py:VT100Engine`; tests `test_vt100_engine.py` |
| FR-157b | The terminal shall interpret erase-in-line (EL, `ESC[K`) and erase-in-display (ED, `ESC[J`) sequences. | Mandatory | T | impl. `terminal/vt100_engine.py:VT100Engine`; tests `test_vt100_engine.py` |
| FR-157c | The terminal shall interpret SGR character attributes (`ESC[…m`) — at least bold, underline, reverse-video, and the 8 ANSI foreground/background colours plus their bright variants — and expose them per rendered cell. | Mandatory | T | impl. `terminal/vt100_engine.py:VT100Engine`, `gui/terminal_view.py:TerminalView._colour`; tests `test_vt100_engine.py`, `test_terminal_view.py` |
| FR-157d | The terminal shall interpret the scrolling-region sequence (DECSTBM, `ESC[top;bottomr`) and confine scrolling to the defined margins. | Mandatory | T | impl. `terminal/vt100_engine.py:VT100Engine`; tests `test_vt100_engine.py` |
| FR-157e | The terminal shall honour horizontal tab stops (default every 8 columns), advancing the cursor to the next tab stop on a Tab (0x09). | Mandatory | T | impl. `terminal/vt100_engine.py:VT100Engine`; tests `test_vt100_engine.py` |
| FR-157f | The terminal shall recognise the DEC special-graphics (line-drawing) charset designation (`ESC(0` to select G0, `ESC(B` to restore ASCII). In raw 8-bit decoding mode (FR-157g) the designated code points shall be mapped to their Unicode box-drawing glyphs; under the default UTF-8 decoding the designation is consumed without desynchronising the stream (remote software targeting a UTF-8 terminal is expected to emit box-drawing code points directly — a limitation of the `pyte` backend). | Mandatory | T | impl. `terminal/vt100_engine.py:VT100Engine`; tests `test_vt100_engine.py` |
| FR-157g | Received bytes shall be decoded as UTF-8 by default, with invalid byte sequences replaced by the Unicode replacement character U+FFFD. A raw 8-bit decoding mode (each byte mapped to the code point of the same value, i.e. Latin-1 semantics) is available for legacy 8-bit CP/M output and is selected **by the remote** via the standard `ESC % G` (UTF-8) / `ESC % @` (raw 8-bit) sequences; there is no separate user control for the mode. | Mandatory | T | impl. `terminal/vt100_engine.py:VT100Engine`; tests `test_vt100_engine.py` |
| FR-157h | The terminal shall be robust to arbitrary remote output: an unsupported or malformed escape sequence shall be ignored without corrupting the rendering of subsequent output, and feeding any byte sequence shall never raise an exception (cf. DR-024 for the DIR parser). | Mandatory | T | impl. `terminal/vt100_engine.py:VT100Engine`; tests `test_vt100_engine.py` |
| FR-158 | Keys typed into the Terminal Window shall be encoded to VT-100 byte sequences and transmitted per keystroke (FR-096), per the following mapping. Printable characters: their UTF-8 encoding. Enter: the configured EOL (FR-094). Backspace: 0x08. Tab: 0x09; Shift-Tab (Backtab): `ESC [ Z`. Escape: 0x1B. Arrow keys Up/Down/Right/Left: `ESC [ A`/`B`/`C`/`D` — always the normal-mode form, as DECCKM is not tracked (FR-157). Home: `ESC [ H`; End: `ESC [ F`. Page Up: `ESC [ 5 ~`; Page Down: `ESC [ 6 ~`; Insert: `ESC [ 2 ~`; Delete: `ESC [ 3 ~`. Function keys F1–F4: `ESC O P`/`Q`/`R`/`S` (SS3); F5–F12: `ESC [ 15 ~`, `17 ~`, `18 ~`, `19 ~`, `20 ~`, `21 ~`, `23 ~`, `24 ~` respectively. Ctrl-A … Ctrl-Z: the C0 control bytes 0x01 … 0x1A. Ctrl-`[`: 0x1B; Ctrl-`\`: 0x1C; Ctrl-`]`: 0x1D; Ctrl-Space: 0x00. A modifier-only key press, or any key that maps to no sequence above, transmits nothing. *(v2.17.)* | Mandatory | T | impl. `gui/terminal_view.py:encode_key`, `gui/terminal_view.py:keyPressEvent`; tests `test_terminal_view.py` |

### 3.11 File context-menu actions

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| FR-110 | The Host Files list (UIR-011) shall provide a right-click context menu (UIR-018) offering the actions **To Remote** (FR-119), **View/Edit**, **Rename**, and **Delete**. **To Remote** (FR-119) and **Delete** (FR-115, FR-116) shall operate on **every selected file**; **View/Edit** and **Rename** operate on the single file the user right-clicked and shall be **disabled** when more than one file is selected (only a single file can be viewed or renamed). When the right-clicked file is not part of the current selection, the action operates on that one file alone. *(v1.8; To Remote added v1.8.1; multi-select Delete and disabled single-file actions v2.3; multi-select To Remote v2.3.)* | Mandatory | T | impl. `mw_context_menu.py:_host_context_menu`, `mw_context_menu.py:_host_to_remote`, `mw_context_menu.py:_host_view`, `mw_context_menu.py:_host_rename`, `mw_context_menu.py:_host_delete` |
| FR-111 | The Remote Files list (UIR-012) shall provide a right-click context menu (UIR-019) offering the actions **To Host** (FR-119), **View**, **Rename**, and **Delete**. **To Host** (FR-119) and **Delete** (FR-115, FR-117) shall operate on **every selected file**; **View** and **Rename** operate on the single file the user right-clicked and shall be **disabled** when more than one file is selected (only a single file can be viewed or renamed). When the right-clicked file is not part of the current selection, the action operates on that one file alone. *(v1.8; To Host added v1.8.1; multi-select Delete and disabled single-file actions v2.3; multi-select To Host v2.3.)* | Mandatory | T | impl. `mw_context_menu.py:_remote_context_menu`, `mw_context_menu.py:_remote_to_host`, `mw_context_menu.py:_remote_view`, `mw_context_menu.py:_remote_rename`, `mw_context_menu.py:_remote_delete` |
| FR-112 | The View/Edit action (host, FR-110) and the View action (remote, FR-111) shall open the target file in the configured viewer/editor command (`viewer_cmd`, UIR-054, default `notepad $1`), with the token `$1` replaced by the path of the file to open; if the command contains no `$1` token, the file path shall be appended as the final argument. If `viewer_cmd` is empty, the application shall instead open the file using the host operating system's default file association. *(v1.8.)* | Mandatory | T | impl. `app.py:_open_in_viewer`, `build_viewer_args`, `_os_open` |
| FR-113 | For a remote View (FR-111), the application shall download the file and open it. The behaviour and precondition are specified by FR-113a–FR-113b. *(v1.8.)* | Mandatory | T | impl. `mw_context_menu.py:_remote_view`, `mw_context_menu.py:_download_and_view`, `mw_context_menu.py:_on_view_file_ready`, `view_file_ready` signal |
| FR-113a | A remote View shall first download the selected file over X-Modem into a temporary folder on the host (reusing the Copy to Host transfer process, FR-080–FR-087, FR-105), and then open the downloaded copy per FR-112. | Mandatory | T | — |
| FR-113b | A remote View shall be permitted only when both the Terminal and Transport status flags are connected (FR-080); otherwise an error dialog with the body text "Transport port not connected" shall be shown and no download shall occur (consistent with CR-010). | Mandatory | T | — |
| FR-114 | The Rename action (host FR-110, remote FR-111) shall present a modal File Action Dialog (UIR-057) containing a single-line text field pre-populated with the selected file's name, an **Apply** button, and a **Cancel** button. Apply confirms the entered (possibly edited) name; Cancel makes no change. The action shall make no change when the entered name is empty or unchanged. *(v1.8.)* | Mandatory | T | impl. `mw_context_menu.py:_host_rename`, `mw_context_menu.py:_remote_rename`, `file_action_dialog.py:FileActionDialog` |
| FR-115 | The Delete action (host FR-110, remote FR-111) shall present a modal File Action Dialog (UIR-057) with an **Apply** button (confirm deletion) and a **Cancel** button (no change). When a single file is being deleted the dialog shall show that file's name in a **read-only** field; when more than one file is selected (FR-110/FR-111) the dialog shall show the list of selected file names in a **read-only**, non-editable list and confirm deletion of all of them. *(v1.8; multi-file list v2.3.)* | Mandatory | T | impl. `mw_context_menu.py:_host_delete`, `mw_context_menu.py:_remote_delete`, `file_action_dialog.py:FileActionDialog` |
| FR-116 | For **host** files, the Rename and Delete context actions shall operate on the host filesystem. Their behaviour and error handling are specified by FR-116a–FR-116c. *(v1.8; multi-file Delete v2.3.)* | Mandatory | T | impl. `mw_context_menu.py:_host_rename`, `mw_context_menu.py:_host_delete` |
| FR-116a | The Rename action shall rename the file on the host filesystem using a standard filesystem rename. On a Rename failure, an error dialog shall report the cause and the file list shall be left unchanged. | Mandatory | T | — |
| FR-116b | The Delete action shall delete **every selected file** (FR-110) using a standard filesystem delete, in list order. If the deletion of any file fails, an error dialog shall report the cause(s); files that were deleted successfully remain deleted. | Mandatory | T | — |
| FR-116c | After Delete the Host Files list shall be refreshed to reflect the result (FR-118). | Mandatory | T | — |
| FR-117 | For **remote** files, the Rename and Delete context actions shall send the configured commands on the Terminal Port. Their behaviour is specified by FR-117a–FR-117c. *(v1.8; multi-file Delete v2.3.)* | Mandatory | T | impl. `mw_context_menu.py:_remote_rename`, `mw_context_menu.py:_remote_delete`, `mw_context_menu.py:_do_remote_file_cmd`, `mw_context_menu.py:_do_remote_file_cmds` |
| FR-117a | The Rename action shall send the configured `rename_remote_cmd` (UIR-055, default `REN $2=$1`) on the Terminal Port, with `$1` replaced by the original filename and `$2` by the new filename. | Mandatory | T | — |
| FR-117b | The Delete action shall send the configured `delete_remote_cmd` (UIR-056, default `ERA $1`) on the Terminal Port **once for each selected file** (FR-111), in list order, with `$1` replaced by that filename. | Mandatory | T | — |
| FR-117c | If the configured command is empty, no command is sent; and no command shall be issued when the Terminal Port is closed (the status bar shall read "Terminal port not open - cannot rename"/"...cannot delete"). | Mandatory | T | — |
| FR-118 | After a successful Rename or Delete, the application shall refresh the affected file list so the change is reflected without manual intervention: a host action refreshes the Host Files list (FR-060); a remote action refreshes the Remote Files list (the FR-074–FR-079 process). After a multi-file Delete the list is refreshed **once**. *(v1.8; multi-file Delete refresh-once v2.3.)* | Mandatory | T | impl. `mw_context_menu.py:_host_rename`, `mw_context_menu.py:_host_delete`, `mw_context_menu.py:_do_remote_file_cmd`, `mw_context_menu.py:_do_remote_file_cmds` |
| FR-119 | The Host/Remote Files context menus (FR-110/FR-111) shall provide **To Remote** / **To Host** actions that transfer the selected files. Their behaviour is specified by FR-119a–FR-119d. *(v1.8.1; multi-select v2.3.)* | Mandatory | T | impl. `mw_context_menu.py:_host_to_remote`, `mw_context_menu.py:_remote_to_host`, `mw_transfer_batches.py:_transfer_to_remote_batch`, `mw_transfer_batches.py:_transfer_to_host_batch` |
| FR-119a | The Host Files context menu (FR-110) shall provide a **To Remote** action and the Remote Files context menu (FR-111) a **To Host** action, each initiating an X-Modem transfer of **every selected file**: **To Remote** copies the host files to the remote system, and **To Host** copies the remote files to the host. | Mandatory | T | — |
| FR-119b | When the right-clicked file is not part of the current selection, the action shall transfer that one file alone. | Mandatory | T | — |
| FR-119c | Each action shall behave exactly as the corresponding Copy to Remote / Copy to Host button (FR-080–FR-087, FR-105, FR-099) applied to the selected files — including sequential transfer of multiple files (FR-106/FR-107), the requirement that **both** the Terminal and Transport status flags be connected (FR-080/CR-010), the modal progress dialog (FR-105), and the automatic refresh of the destination list on success (FR-099). | Mandatory | T | — |
| FR-119d | If both flags are not connected, an error dialog with the body text "Transport port not connected" shall be shown and no transfer shall occur. | Mandatory | T | — |
| FR-120 | The user shall be able to cancel a file transfer while it is in progress, using the Transfer Progress Dialog's **Cancel** button (UIR-051). The detailed cancellation behaviour — aborting the X-Modem transfer, stopping the batch, tearing down the dialog, refreshing on partial completion, and keeping the worker responsive — is specified by FR-120a–FR-120g. *(v1.9.)* | Mandatory | T | impl. `app.py:_request_transfer_cancel`, `_on_transfer_cancelled`, `_transfer_cancel` flag, `transfer_cancelled` signal, batch drivers; `gui/transfer_dialog.py` Cancel button; `xmodem.py:send_file`, `receive_file` cancel checks, `_abort`, `_drain_tx` |
| FR-120a | The Transfer Progress Dialog (UIR-051) shall provide a **Cancel** button; pressing it shall request cancellation of the current transfer. | Mandatory | T | — |
| FR-120b | On a cancellation request the application shall signal the active X-Modem transfer to abort — transmitting the CAN sequence on the Transport Port (so the remote PCGET/PCPUT also aborts) and flushing the port in **both** directions with a bounded drain, per NFR-003m–NFR-003o — so the cancellation takes effect immediately rather than the transfer appearing to continue until the serial buffers empty. *(v2.13.1; v2.13.2.)* | Mandatory | T | — |
| FR-120c | On a cancellation request the application shall stop the batch so that no further files are attempted (the multi-file analogue of FR-108). | Mandatory | T | — |
| FR-120d | On a cancellation request the application shall close the progress dialog and set the status bar to a cancellation message. | Mandatory | T | — |
| FR-120e | If one or more files of a multi-file batch (FR-106) completed before the cancellation, the destination list shall be refreshed once (per FR-099); a file that was only partially received shall not be written to the host. | Mandatory | T | — |
| FR-120f | Cancellation shall be initiated on the GUI thread and observed by the transfer worker thread via a thread-safe flag, with the dialog teardown marshalled back to the GUI thread (NFR-004). | Mandatory | T | — |
| FR-120g | The blocking waits on the transfer worker thread — the post-launch handshake delay (FR-089), the between-files settle (FR-109), and the pre-upload remote listing read (FR-145) — shall observe the cancel flag and wake promptly rather than running their full interval, so a Cancel pressed during any of them takes effect without waiting out the delay. *(v2.13.2.)* | Mandatory | T | — |

### 3.12 Internationalisation

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| FR-121 | Every user-facing string displayed in the GUI (window and dialog titles, menu and submenu titles and items, toolbar and button labels, group-box titles, list context-menu items, connection-indicator names, status-bar messages, and error/warning/information dialog titles and bodies) shall be externalised into language files (DR-042) and resolved at run time by a placeholder key, rather than being hard-coded in source. Semantic or technical values that are not human-facing prose — drop-down option *values* (e.g. parity/flow/EOL/debug values), drive letters, configurable command templates, and numeric option lists — are excluded from translation (CR-015). *(v2.0.)* | Mandatory | T | impl. `utils/i18n.py:tr`; `app.py`, `gui/*.py` call sites; `lang/lang_english.txt` |
| FR-122 | The Config menu (UIR-003) shall contain a **Language** submenu listing every language for which a language file is available (DR-042), each entry displayed by its language name (capitalised). Selecting an entry shall make that language the active language. *(v2.0.)* | Mandatory | T | impl. `app.py:_setup_language_menu`, `menu_set_language`, `utils/i18n.py:available_languages`, `set_language` |
| FR-123 | Changing the active language (FR-122) shall re-translate all currently-visible user interface elements immediately, without requiring an application restart. On-demand dialogs and context menus, being rebuilt each time they are shown, shall always reflect the active language. *(v2.0.)* | Mandatory | T | impl. `app.py:retranslate_ui`, `_register_text`, `terminal_window.py:retranslate_ui` |
| FR-124 | The active language shall be persisted and restored on the next start (DR-042); the default and fallback language is English. When a key is absent from the active language, the application shall fall back to the English text; when absent from English as well, it shall fall back to the key string itself. *(v2.0.)* | Mandatory | T | impl. `gui/window_state.py:language`, `app.py:__init__`, `utils/i18n.py:tr`, `set_language` |
| FR-125 | The main window title bar (UIR-005) shall display the currently-loaded configuration name. Its content and updating are specified by FR-125a–FR-125c. *(v2.4.)* | Mandatory | I | impl. `app.py:_update_window_title`, `_config_name`, `mw_config.py:load_config`, `mw_config.py:menu_new`, `retranslate_ui` |
| FR-125a | The title bar shall display the application name followed by the base name of the currently-loaded configuration file — the file name only, with no directory path and no extension. | Mandatory | I | — |
| FR-125b | When no configuration file is loaded (at first start with no remembered config, or after File > New), the title shall show the application name alone. | Mandatory | I | — |
| FR-125c | The configuration name shall update whenever a config is loaded (File > Load or startup reload, FR-005) and shall be cleared by File > New (FR-019). | Mandatory | I | — |
| FR-126 | The Host Files group title (UIR-011) shall display the current host directory. Its content, eliding, and updating are specified by FR-126a–FR-126c. *(v2.4.)* | Mandatory | I | impl. `app.py:_update_host_group_title`, `mw_file_panes.py:refresh_host_files`, `resizeEvent`, `setup_layout`, `retranslate_ui` |
| FR-126a | The group title shall display the translated "Host Files" label followed by the current host directory. | Mandatory | I | — |
| FR-126b | When the directory text is wider than the space available in the group box, the application shall elide its leading portion (showing `…` followed by the trailing part of the path) so that the most specific, trailing part of the path remains visible. | Mandatory | I | — |
| FR-126c | The displayed directory shall track every change to the host directory (FR-060, FR-062) and shall be recomputed when the window is resized. | Mandatory | I | — |

### 3.13 File list filtering and sorting

*(v2.6. Feature 3 of the new-features plan. The Host Files (UIR-011) and Remote Files (UIR-012)
lists each gain a text filter and a sort control. The filter/sort logic is a pure, GUI-free module
(`utils/file_filter.py`, CR-014) shared by both panes so they behave identically. The lists remain the
existing `QListWidget` multi-select widgets — filtering and sorting are applied by re-deriving the
visible rows from a retained canonical list of names, rather than by migrating to a model/view
architecture; this preserves all existing list behaviour while delivering the same user-facing
capability.)*

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| FR-130 | Each file list pane (Host Files — UIR-011, Remote Files — UIR-012) shall provide a text filter field (UIR-079) positioned above its list. The filter shall restrict the list to the file names that match the entered text; an empty filter shows every file. The application shall retain the full (unfiltered) set of names for each pane so the filter and sort (FR-132) can be re-applied without re-reading the source (the host directory / the captured remote listing). *(v2.6.)* | Mandatory | T | impl. `mw_file_panes.py:_build_filter_sort_row`, `mw_file_panes.py:_render_file_list`, `mw_file_panes.py:_apply_host_view`, `mw_file_panes.py:_apply_remote_view`, `mw_file_panes.py:refresh_host_files`, `mw_remote.py:_update_remote_list_ui`; `utils/file_filter.py:filter_names`; tests `test_file_filter.py`, `test_gui_smoke.py` |
| FR-131 | The filter shall match by file name with the following rules: an empty or whitespace-only pattern matches every name; a pattern containing a wildcard (`*` matching any run of characters, `?` matching exactly one) is matched as a glob over the whole file name; a pattern with no wildcard is matched as a substring ("contains"). Matching shall be case-insensitive by default (the module also supports an opt-in case-sensitive mode). Filter input shall be debounced by a fixed 150 ms delay so the list is not re-rendered on every keystroke. *(v2.6.)* | Mandatory | T | impl. `utils/file_filter.py:matches`, `has_wildcard`, `filter_names`; `mw_file_panes.py:_build_filter_sort_row` (debounce `QTimer`); tests `test_file_filter.py` |
| FR-132 | Each pane shall provide a sort control (UIR-080) offering sort by **Name** and by **Extension**, each in ascending or descending order toggled by a direction control. Sorting shall be case-insensitive and stable, with the file name as the final tie-breaker so the order is deterministic; an unrecognised sort key falls back to name order. Sorting by file size is not provided, as the CP/M `DIR` listing parsed for the remote pane (FR-077, §6) carries no size information. *(v2.6.)* | Mandatory | T | impl. `utils/file_filter.py:sort_names`; `mw_file_panes.py:_build_filter_sort_row`, `mw_file_panes.py:_update_sort_arrow`, `mw_file_panes.py:_render_file_list`; tests `test_file_filter.py`, `test_gui_smoke.py` |
| FR-133 | The filter (FR-131) and sort (FR-132) shall be combined by applying the filter first and then sorting the survivors, so the displayed order is determined only by the files remaining after filtering. The same combined logic shall serve both panes. With the default controls (no filter text, sort by Name ascending) the Remote Files list display is identical to the prior FR-078 ascending-alphabetical behaviour. *(v2.6.)* | Mandatory | T | impl. `utils/file_filter.py:filter_and_sort`; `mw_file_panes.py:_render_file_list`, `mw_file_panes.py:_apply_host_view`, `mw_file_panes.py:_apply_remote_view`; tests `test_file_filter.py`, `test_gui_smoke.py` |
| FR-134 | The last-used filter text and sort settings (key and direction) shall be persisted **independently for each pane** and restored on the next start. These are UI/session preferences and shall be stored with the rest of the UI/session state (`QSettings`-backed `WindowState`, alongside geometry and language — FR-004/FR-124), kept separate from the per-configuration serial JSON. *(v2.6. The new-features plan suggested persisting via `ConfigHandler`; `WindowState` is used instead, consistent with the existing treatment of UI/session preferences and avoiding changes to the two coexisting config-JSON shapes.)* | Mandatory | T | impl. `gui/window_state.py:filter_text`/`sort_key`/`sort_descending` (+ setters); `mw_file_panes.py:_persist_filter_sort`, `mw_file_panes.py:_restore_filter_sort`; tests `test_gui_smoke.py` |
| FR-135 | The filter field shall provide an inline **clear** (×) control that empties it (restoring the full list), and the application shall give a clear visual indication when a filter is active (a non-empty filter). When a pane's list is cleared because its source is no longer valid (FR-017 load, FR-058 disconnect, FR-103 drive-not-found, FR-074/FR-104 terminal closed, FR-019 New), the retained canonical list (FR-130) shall also be emptied so a later filter/sort change cannot resurrect stale entries. *(v2.6.)* | Mandatory | T | impl. `mw_file_panes.py:_build_filter_sort_row` (`setClearButtonEnabled`), `mw_file_panes.py:_render_file_list` (active-filter border), `mw_file_panes.py:_clear_remote_files`; tests `test_gui_smoke.py` |

### 3.14 Drag-and-drop file transfer

*(v2.7. Feature 1 of the new-features plan. The two file-list panes (Host Files — UIR-011, Remote
Files — UIR-012) become both drag sources and drop targets so a transfer can be initiated by dragging
files between the panes, or by dropping files from the host OS file manager onto the Remote pane. The
drop is observed on the GUI thread and the transfer itself reuses the existing batch workers and the
signal-based cross-thread model (NFR-004), so drag-and-drop is purely an additional way to trigger the
already-specified Copy to Remote / Copy to Host transfers (FR-080–FR-085, FR-099, FR-105–FR-109) —
the transfer behaviour, progress dialog, sequencing, and refresh are unchanged.)*

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| FR-136 | Each file-list pane (Host Files — UIR-011, Remote Files — UIR-012) shall be a **drag source**: the user shall be able to drag its selected file(s) — honouring the existing multi-selection (FR-106) — using a drag payload that carries the originating pane and the selected file names under an application-private MIME type (`application/x-cpmfm-file`). A drag never moves or alters the source files (it is a copy gesture). *(v2.7.)* | Mandatory | T | impl. `gui/file_list_widget.py:FileListWidget.startDrag`, `MIME_CPM_FILES`; tests `test_gui_smoke.py` |
| FR-137 | Each pane shall be a **drop target** for an internal drag (FR-136) originating from the *other* pane, initiating a Copy transfer in the corresponding direction. The drop behaviour is specified by FR-137a–FR-137e. *(v2.7.)* | Mandatory | T | impl. `gui/file_list_widget.py:FileListWidget.decode_drop`, `dropEvent`; `mw_transfers.py:_on_files_dropped`, `mw_transfers.py:_confirm_dnd_transfer`, `_confirm_dialog`; tests `test_gui_smoke.py` |
| FR-137a | Dropping Host-pane files onto the Remote pane shall initiate Copy to Remote, and dropping Remote-pane files onto the Host pane shall initiate Copy to Host. | Mandatory | T | — |
| FR-137b | A drop onto the originating pane shall be a no-op. | Mandatory | T | — |
| FR-137c | A drop shall be permitted only when both the Terminal and Transport status flags are true (FR-080/CR-010); otherwise the application shall report "Transport port not connected" and start no transfer. | Mandatory | T | — |
| FR-137d | A drop shall be **confirmed** by the user before the transfer begins, via a confirmation dialog presenting Cancel and OK ordered per UIR-075 (Cancel far left, OK far right). *(v2.12: a custom Cancel/OK dialog obeying UIR-075 rather than a platform-ordered Yes/No QMessageBox.)* | Mandatory | T | — |
| FR-137e | An accepted drop shall reuse the existing batch transfer workers (`_transfer_to_remote_batch` / `_transfer_to_host_batch`), spawned on a worker thread from the GUI-thread drop, so all transfer behaviour (FR-099, FR-105–FR-109, FR-120) is identical to the Copy buttons. | Mandatory | T | — |
| FR-138 | The **Remote** pane shall additionally accept a drop of one or more files from the host operating system's file manager (an external drag carrying file URLs); the application shall treat the dropped absolute paths as the files to Copy to Remote (confirmed and flag-gated exactly as FR-137). The **Host** pane shall **not** accept such external OS drops — it is the local filesystem view, so dropping host files onto it is not a serial transfer. *(v2.7.)* | Mandatory | T | impl. `gui/file_list_widget.py:FileListWidget.decode_drop`; `mw_transfers.py:_on_files_dropped`; tests `test_gui_smoke.py` |
| FR-139 | While a drag is over a pane, the pane shall give drop-zone feedback. The accepted-payload and rejected-payload behaviour are specified by FR-139a–FR-139b. *(v2.7.)* | Mandatory | I | impl. `gui/file_list_widget.py:FileListWidget.dragEnterEvent`, `dragMoveEvent`, `dragLeaveEvent`, `_set_drop_active` |
| FR-139a | While a drag carrying an acceptable payload (FR-137/FR-138) is over a pane, that pane shall be visibly highlighted as a valid drop zone (a coloured border); the highlight shall be removed when the drag leaves the pane or the drop completes. | Mandatory | I | — |
| FR-139b | A drag whose payload the pane would reject (a same-pane internal drag, or an external OS drop onto the Host pane) shall not highlight the pane and shall not be accepted. | Mandatory | I | — |

### 3.15 Transfer history

*(v2.8. Feature 2 of the new-features plan. Every file-transfer *attempt* — successful, failed, or
cancelled — is recorded in a persistent history so the user can review past transfers and re-initiate
("re-transfer") a previous one. This is distinct from the raw serial receive/transmit data buffers
(`_rx_buffer`/`_tx_buffer`, FR-090/FR-092), which hold un-structured terminal bytes rather than
per-file transfer records. The history store is a pure, GUI-free module (`utils/transfer_history.py`,
CR-014) so it is safe to call from the transfer worker threads and is unit-testable without Qt; the
Transfer History dialog (UIR-082/UIR-083) is the GUI view over it.)*

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| FR-140 | The application shall maintain a **transfer history** in which each entry records one file-transfer attempt with: the file's base **name**, the host-side **path** involved (retained so the transfer can be re-initiated — FR-144), the **direction** (`remote` = Copy to Remote / host→remote upload, `host` = Copy to Host / remote→host download), a **timestamp** (ISO-8601 local time), the **status** (`success`, `failure`, `cancelled`, or `skipped` — the last when the user declined to overwrite an existing destination file (FR-146) or declined to give an invalid-named upload a conforming CP/M name (FR-149)), the transferred **size** in bytes (0 when unknown — e.g. a failed/cancelled/skipped download, whose length the X-Modem stream never carried), an **error** message (for a failure; empty otherwise), and a **retry** flag (true when the entry resulted from a re-transfer — FR-144). *(v2.8.)* | Mandatory | T | impl. `utils/transfer_history.py:TransferHistory.add_entry`; `mw_history.py:_record_history`; tests `test_transfer_history.py` |
| FR-141 | The transfer history shall be **persisted** across sessions. Its storage, retention policy, and failure handling are specified by FR-141a–FR-141c. *(v2.8.)* | Mandatory | T | impl. `utils/transfer_history.py:TransferHistory` (`_read_file`, `_write_file`, `_prune_locked`, `prune_old_entries`); tests `test_transfer_history.py` |
| FR-141a | The history shall be stored as a JSON list of entries (oldest first) in a file in the user's home directory (`~/.cpm_fm_history.json`, DR-045) and restored on the next start, kept separate from the per-configuration serial JSON (`ConfigHandler`) and the `QSettings`-backed UI/session state (`WindowState`). | Mandatory | T | — |
| FR-141b | A **retention policy** shall bound the file: at most 500 entries are kept (the oldest dropped first) and entries older than 30 days are pruned. | Mandatory | T | — |
| FR-141c | A missing, unreadable, or malformed history file shall degrade to an empty history rather than raising, and a write failure shall never abort a transfer. | Mandatory | T | — |
| FR-142 | Each transfer shall record its per-file outcome in the history (FR-140) as it completes: a **success** entry (with the transferred size) for each file that transfers, a **failure** entry (with the error message) for a file that errors or fails, and a **cancelled** entry for the in-progress file when the user cancels the batch (FR-120), and a **skipped** entry for a file the user chose not to overwrite at the destination (FR-146) or chose to skip rather than rename when its name was not CP/M 8.3-conforming (FR-149). Recording occurs on the transfer worker threads, so the history store shall be **thread-safe**; no Qt-signal marshalling is required for the record itself. *(v2.8.)* | Mandatory | T | impl. `mw_transfer_batches.py:_transfer_to_remote_batch`, `mw_transfer_batches.py:_transfer_to_host_batch`, `mw_history.py:_record_history`; `utils/transfer_history.py:TransferHistory.add_entry` (lock); tests `test_transfer_history.py`, `test_gui_smoke.py` |
| FR-143 | The application shall present a modal **Transfer History dialog** (UIR-082/UIR-083) showing the recorded entries (FR-140) newest-first in a table, with controls to **filter** by direction and by status, to **export** the history to a user-chosen JSON file, and to **clear** the entire history after a confirmation. *(v2.8.)* | Mandatory | T | impl. `gui/transfer_history_dialog.py:TransferHistoryDialog`; `mw_history.py:show_history`; tests `test_gui_smoke.py` |
| FR-144 | The Transfer History dialog shall allow the user to **re-transfer** a selected entry. The re-transfer behaviour is specified by FR-144a–FR-144c. *(v2.8.)* | Mandatory | T | impl. `gui/transfer_history_dialog.py:TransferHistoryDialog` (`_on_retransfer`, `retransfer_entry`); `mw_history.py:show_history`, `mw_history.py:_retransfer`, `mw_transfer_batches.py:_transfer_to_remote_batch`/`mw_transfer_batches.py:_transfer_to_host_batch` (`retry`); tests `test_gui_smoke.py` |
| FR-144a | Re-transfer shall restore the file path and direction from the entry and re-initiate the transfer through the existing batch flow (a `remote` entry re-runs Copy to Remote, a `host` entry re-runs Copy to Host), gated on both connection flags (FR-080/CR-010) exactly as the Copy actions, with an upload additionally requiring its source host file to still exist. | Mandatory | T | — |
| FR-144b | The new attempt shall be recorded in the history marked as a re-transfer (`retry`). | Mandatory | T | — |
| FR-144c | Re-transfer shall start only after the History dialog has closed, so its own modal progress dialog (FR-105) is not obscured. | Mandatory | T | — |

### 3.16 Transfer file-conflict handling

*(v2.9. Feature: when a file being transferred already exists at the destination, the user is prompted
to Overwrite, Skip, or Cancel — standard operating-system file-copy behaviour — with the option to apply
the chosen Overwrite/Skip action to all remaining conflicts in the batch. The detection differs by
direction: a remote→host download checks the host filesystem; a host→remote upload first refreshes the
remote directory listing so the check is against the live remote contents rather than a possibly-stale
cached list.)*

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| FR-145 | Before transferring each file in a batch (FR-106), the application shall determine whether a file of the same name already exists at the **destination**. The per-direction detection is specified by FR-145a–FR-145d. *(v2.9.)* | Mandatory | T | impl. `mw_transfer_guards.py:_destination_conflict`, `mw_transfer_guards.py:_fresh_remote_names`, `mw_transfer_batches.py:_transfer_to_remote_batch`, `mw_transfer_batches.py:_transfer_to_host_batch`; tests `test_conflict_resolution.py` |
| FR-145a | The conflict check shall run before transferring each file in a batch (FR-106), against the transfer's **destination**. | Mandatory | T | — |
| FR-145b | For a remote→host download (`host`), the destination is the host directory and the check is the existence of the target path on the host filesystem. | Mandatory | T | — |
| FR-145c | For a host→remote upload (`remote`), the destination is the remote CP/M drive: the application shall **refresh the remote directory listing once at the start of the upload batch** (reusing the listing/parse mechanism of FR-077–FR-079, which also updates the displayed Remote Files list and so satisfies FR-099 for the pre-transfer state) and check the file's base name, upper-cased (CP/M names are upper-case 8.3), against that fresh listing. | Mandatory | T | — |
| FR-145d | If the remote refresh yields no names (e.g. the capture failed or the listing could not be parsed), no conflict shall be detected and the upload shall proceed as before (overwrite-by-default). | Mandatory | T | — |
| FR-146 | When a destination conflict is detected (FR-145) and no batch-wide policy is in effect (FR-147), the application shall **prompt** the user (UIR-084) to resolve it. The prompt and its handling are specified by FR-146a–FR-146d. *(v2.9.)* | Mandatory | T | impl. `mw_transfer_guards.py:_resolve_conflict`, `mw_transfer_guards.py:_on_conflict_detected`, `conflict_detected` signal, `mw_backup_restore.py:_erase_remote_file` (Overwrite pre-delete); `gui/conflict_dialog.py:FileConflictDialog`; tests `test_conflict_resolution.py`, `test_gui_smoke.py` |
| FR-146a | The modal conflict dialog (UIR-084) shall name the conflicting file and offer three actions: **Overwrite** (replace the destination file), **Skip** (do not transfer this file and continue with the next), and **Cancel** (abort the whole batch, identical to the Cancel of FR-120). | Mandatory | T | — |
| FR-146b | On **Overwrite** of a host→remote upload, the application shall first delete the existing remote file by sending the configured `delete_remote_cmd` (FR-117) and waiting for the command to go idle, then perform the transfer; this guarantees the receiver writes to a clean slate and avoids receivers (notably XMODEM-1K variants — NFR-003b) that prompt or stall on an existing file rather than overwriting silently. A blank `delete_remote_cmd` is a no-op, leaving the prior overwrite-by-default behaviour. *(v2.13.)* | Mandatory | T | — |
| FR-146c | A skipped file shall be recorded in the transfer history (FR-142) with the status `skipped`. | Mandatory | T | — |
| FR-146d | Because the batch runs on a worker thread, the prompt shall be raised on the GUI thread and the worker shall block until the user answers, marshalled via a Qt signal and a thread-safe event (NFR-004). | Mandatory | T | — |
| FR-147 | The conflict prompt (FR-146) shall offer an **"apply to all remaining conflicts"** option (a checkbox). When the user resolves a conflict with that option ticked, the chosen action (Overwrite or Skip) shall be remembered as a **batch-wide policy** and applied automatically to every subsequent conflict in the same batch without prompting again. The policy shall be reset at the start of each batch so it never carries across separate transfers. Cancel always ends the batch immediately and so is unaffected by the option. *(v2.9.)* | Mandatory | T | impl. `mw_transfer_guards.py:_resolve_conflict`, `_conflict_policy`; `gui/conflict_dialog.py:FileConflictDialog` (`apply_to_all`); tests `test_conflict_resolution.py` |

### 3.17 Host→remote filename validation

*(v2.10. Feature: a host file's name may legally use characters or lengths that CP/M cannot store. Before
each host→remote upload the application validates the file's name against the CP/M 8.3 naming convention
(DR-046); if it does not conform, the user is prompted to **Rename** the file (supply a conforming name),
**Skip** the file, or **Cancel** the whole batch. A renamed file is uploaded to the remote under the new
name and is then subject to the normal destination-conflict handling of §3.15. This validation applies to
the upload direction only — a remote→host download writes to the host filesystem, which has no 8.3
restriction.)*

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| FR-148 | Before each host→remote upload the application shall validate the file's base name against the **CP/M 8.3 naming convention** (DR-046). The gating and scope are specified by FR-148a–FR-148b. *(v2.10.)* | Mandatory | T | impl. `mw_transfer_guards.py:_prompt_invalid_name`, `mw_transfer_guards.py:_on_invalid_name_detected`, `filename_validation_dialog.py:FilenameValidationDialog`, `cpm_parser.py:is_valid_8_3` (invoked from `mw_transfer_batches.py:_transfer_to_remote_batch`); tests `test_filename_validation.py` |
| FR-148a | The validation shall run before transferring each file in a host→remote upload batch (FR-106) and before the destination-conflict check of FR-145; a name that conforms shall be uploaded without prompting. | Mandatory | T | — |
| FR-148b | The validation shall apply to the upload (`remote`) direction only; a remote→host download (`host`) shall not be validated. | Mandatory | T | — |
| FR-149 | When an upload file's name does not conform (FR-148), the application shall **prompt** the user (UIR-085) to resolve it before uploading. The prompt and its handling are specified by FR-149a–FR-149e. *(v2.10.)* | Mandatory | T | impl. `mw_transfer_guards.py:_prompt_invalid_name`, `mw_transfer_guards.py:_on_invalid_name_detected`, `invalid_name_detected` signal, `mw_transfer_batches.py:_transfer_to_remote_batch`, `mw_transfer_batches.py:_send_one_to_remote`, `mw_transfer_guards.py:_destination_conflict`; `gui/filename_validation_dialog.py:FilenameValidationDialog`; `terminal/cpm_parser.py:CPMParser.suggest_8_3`; tests `test_filename_validation.py` |
| FR-149a | The modal dialog (UIR-085) shall name the offending file and offer three actions: **Rename**, **Skip** (do not transfer this file and continue with the next), and **Cancel** (abort the whole batch, identical to the Cancel of FR-120). | Mandatory | T | — |
| FR-149b | The **Rename** action shall pre-fill the replacement-name field with a conforming suggestion derived from the original name, and shall accept the entry only once it is itself a valid CP/M 8.3 name. | Mandatory | T | — |
| FR-149c | On **Rename**, the file shall be uploaded to the remote under the replacement name (the PCGET launch argument and the transfer-history record shall use it), and that name shall then be subject to the destination-conflict handling of FR-145–FR-147. | Mandatory | T | — |
| FR-149d | The **Skip** action shall record a `skipped` history entry (FR-142) and continue with the next file. | Mandatory | T | — |
| FR-149e | Because the batch runs on a worker thread, the prompt shall be raised on the GUI thread and the worker shall block until the user answers, marshalled via a Qt signal and a thread-safe event (NFR-004). | Mandatory | T | — |

### 3.18 Whole-drive backup and restore

*(v2.11. Feature: two toolbar actions that mirror every file between the remote drive and the host
directory as a single destructive operation. **Backup** copies the whole remote drive to the host
(remote→host); **Restore** copies the whole host directory to the remote drive (host→remote). Each first
refreshes the destination listing, then warns the user that ALL files at the destination will be deleted
and re-written and requires explicit confirmation; on confirmation it deletes every file at the
destination and then copies every file from the source, reusing the existing batch-transfer engine so the
operation shows the standard progress dialog and can be cancelled.)*

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| FR-150 | The application shall provide a **Backup** action (UIR-086) that mirrors the currently-selected remote drive to the current host directory (remote→host). Backup shall perform, in order, the steps specified by FR-150a–FR-150d, subject to the precondition of FR-150e. *(v2.11.)* | Mandatory | T | impl. `mw_backup_restore.py:do_backup`, `mw_backup_restore.py:_backup_drive`, `mw_backup_restore.py:_list_remote_file_names`, `mw_backup_restore.py:_wipe_host_dir`, `mw_transfer_batches.py:_transfer_to_host_batch`; tests `test_backup_restore.py` |
| FR-150a | Backup shall first refresh the destination (host) directory listing and the source (remote) drive listing (the latter reusing the FR-077–FR-079 listing/parse mechanism, which also updates the displayed Remote Files list). | Mandatory | T | — |
| FR-150b | Backup shall then obtain the user's confirmation of the destructive operation (FR-152). | Mandatory | T | — |
| FR-150c | On confirmation, Backup shall delete every file in the host directory (FR-153). | Mandatory | T | — |
| FR-150d | Backup shall then download every file on the remote drive into the host directory, reusing the Copy to Host batch transfer (FR-099/FR-105/FR-106/FR-107/FR-120/FR-154). | Mandatory | T | — |
| FR-150e | Backup shall run off the GUI thread and is permitted only when both the Terminal and Transport status flags are true (FR-080/CR-010); otherwise it shall show the "Transport port not connected" error and not proceed. | Mandatory | T | — |
| FR-151 | The application shall provide a **Restore** action (UIR-087) that mirrors the current host directory to the currently-selected remote drive (host→remote). Restore shall perform, in order, the steps specified by FR-151a–FR-151d, subject to the precondition of FR-151e. *(v2.11.)* | Mandatory | T | impl. `mw_backup_restore.py:do_restore`, `mw_backup_restore.py:_restore_drive`, `mw_backup_restore.py:_list_remote_file_names`, `mw_backup_restore.py:_wipe_remote_drive`, `mw_transfer_batches.py:_transfer_to_remote_batch`; tests `test_backup_restore.py` |
| FR-151a | Restore shall first snapshot the source (host) directory listing and refresh the destination (remote) drive listing (reusing the FR-077–FR-079 mechanism, which also yields the set of remote files to delete and updates the displayed Remote Files list). | Mandatory | T | — |
| FR-151b | Restore shall then obtain the user's confirmation of the destructive operation (FR-152). | Mandatory | T | — |
| FR-151c | On confirmation, Restore shall delete every file on the remote drive (FR-153). | Mandatory | T | — |
| FR-151d | Restore shall then upload every file in the host directory (using the listing snapshotted in FR-151a, before the confirmation prompt, so files added to the host directory after the remote drive is wiped are excluded) to the remote drive, reusing the Copy to Remote batch transfer (FR-099/FR-105/FR-106/FR-107/FR-120/FR-154), which continues to apply the host→remote filename validation of FR-148/FR-149. | Mandatory | T | — |
| FR-151e | Restore shall run off the GUI thread and is permitted only when both status flags are true (FR-080/CR-010); otherwise it shall show the "Transport port not connected" error and not proceed. | Mandatory | T | — |
| FR-152 | Before a Backup (FR-150) or Restore (FR-151) deletes anything, the application shall obtain the user's confirmation of the destructive operation. The refresh, dialog, abort/proceed semantics, and threading are specified by FR-152a–FR-152d. *(v2.11.)* | Mandatory | T | impl. `mw_backup_restore.py:_confirm_backup_restore`, `mw_backup_restore.py:_on_backup_restore_confirm`, `backup_restore_confirm` signal; tests `test_backup_restore.py` |
| FR-152a | Before the prompt, the application shall **refresh the destination listing** (and, for Backup, also the source (remote) drive listing — per FR-150); the refresh shall complete and be reflected in the relevant file pane(s) before the prompt is shown. | Mandatory | T | — |
| FR-152b | The application shall then display a modal **confirmation** dialog (UIR-088) warning that ALL files at the destination (the host directory for Backup, the remote drive for Restore) will be deleted and re-written, and offering **Continue** and **Cancel**. | Mandatory | T | — |
| FR-152c | Cancel (and a window-manager close) shall abort the operation before any deletion or transfer occurs; Continue shall proceed. | Mandatory | T | — |
| FR-152d | Because Backup/Restore run on a worker thread, the prompt shall be raised on the GUI thread and the worker shall block until the user answers, marshalled via a Qt signal and a thread-safe event (NFR-004). | Mandatory | T | — |
| FR-153 | On confirmation (FR-152), the application shall **delete every file at the destination** before transferring. The per-destination deletion and the listing it operates on are specified by FR-153a–FR-153d. *(v2.11.)* | Mandatory | T | impl. `mw_backup_restore.py:_wipe_host_dir`, `mw_backup_restore.py:_wipe_remote_drive`; tests `test_backup_restore.py` |
| FR-153a | The deletion shall occur on confirmation (FR-152) and before any file is transferred. | Mandatory | T | — |
| FR-153b | For Backup the destination is the host directory: each regular file in it shall be removed from the host filesystem; subdirectories within the host directory are not removed. | Mandatory | T | — |
| FR-153c | For Restore the destination is the remote drive: each file in the freshly-refreshed remote listing shall be removed by sending the configured delete command (`delete_remote_cmd`, default `ERA $1`, FR-117; UIR-056) once per file on the Terminal Port. | Mandatory | T | — |
| FR-153d | The wipe shall operate on the destination listing refreshed in FR-152, deleting files individually (the per-file delete avoids the interactive `ERA *.*` confirmation on the CP/M side). | Mandatory | T | — |
| FR-154 | The file-copying phase of Backup and Restore shall **reuse the existing batch-transfer engine** (`_transfer_to_host_batch` / `_transfer_to_remote_batch`), so that a single modal Transfer Progress Dialog (FR-105/UIR-051) serves the whole operation, files transfer sequentially over the single Transport Port (FR-106/FR-107), the operation can be **cancelled** mid-transfer via the dialog's Cancel button (FR-120), and each file's outcome is recorded in the transfer history (FR-142). Because the destination is emptied first (FR-153), the destination-conflict handling of FR-145–FR-147 detects no conflicts during a Backup/Restore. When the source contains no files, the operation completes after the wipe with nothing to transfer and refreshes the destination pane (FR-099). *(v2.11.)* | Mandatory | T | impl. `mw_backup_restore.py:_backup_drive`, `mw_backup_restore.py:_restore_drive`, `mw_transfer_batches.py:_transfer_to_host_batch`, `mw_transfer_batches.py:_transfer_to_remote_batch`; tests `test_backup_restore.py` |

---

## 4. User Interface Requirements

### 4.1 Menu bar

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| UIR-001 | The GUI shall present a menu bar at the top of the main window. | Mandatory | I | App_Requirements §Look and Feel, §Main Program GUI; impl. `app.py:setup_menu` |
| UIR-002 | The menu bar shall contain a File menu with the items New, Load, Save, and Exit. | Mandatory | I | App_Requirements §Look and Feel; impl. `app.py:setup_menu` |
| UIR-003 | The menu bar shall contain a Config menu with the items Serial, General, and Language (the Language submenu, UIR-077). *(Language added v2.0.)* | Mandatory | I | App_Requirements §Look and Feel; impl. `app.py:setup_menu`, `_setup_language_menu` |
| UIR-004 | The menu bar shall contain a Help menu with the items Manual (FR-023) and About (FR-022). *(v1.10; Manual added v2.13.)* | Mandatory | I | impl. `app.py:setup_menu` |
| UIR-005 | The main window title bar shall show the application name and, when a configuration file is loaded, the loaded config's base name (no path, no extension) per FR-125. *(v2.4.)* | Mandatory | I | impl. `app.py:_update_window_title` |

### 4.2 Main window layout

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| UIR-010 | The main window shall contain a status bar at the bottom. | Mandatory | I | App_Requirements §Main Program GUI; impl. `app.py:setup_status_bar`, `app.py:_on_status_changed` |
| UIR-011 | The main window shall contain a "Host Files" group containing a top row with the "Change Directory" and "Update" (FR-063) buttons sized equally side-by-side, a multi-select widget, and a row underneath the widget containing the "Copy to Remote" button. The group title shall include the current host directory, left-elided to fit the group width (FR-126). *(v2.1.1: the "Update" button — formerly "Refresh Host" beneath the widget — now sits beside "Change Directory", equally sized.)* *(v2.4: group title shows the host directory.)* | Mandatory | I | App_Requirements §Main Program GUI; impl. `app.py:setup_layout`, `_update_host_group_title` |
| UIR-012 | The main window shall contain a "Remote Files" group containing a drive-selection drop-down (UIR-017) followed by an equally-sized "Update" button, a multi-select widget, and a row underneath the widget containing the "Copy to Host" button. | Mandatory | I | App_Requirements §Main Program GUI; impl. `app.py:setup_layout` |
| UIR-013 | The main window shall provide the actions Connect, Disconnect, Copy to Remote, Copy to Host, Refresh Host, and Terminal. From v1.3 these are presented as a top toolbar (see UIR-071) or within the file panes rather than a central button column. | Mandatory | I | App_Requirements §Main Program GUI; impl. `app.py:setup_toolbar` |
| UIR-014 | The status bar shall be a single-line text label. When a status message exceeds 127 characters, the application shall truncate it to the first 127 characters before display. | Mandatory | T | App_Requirements §Status Bar; impl. `app.py:set_status` |
| UIR-015 | The Connect button shall be enabled at startup. | Mandatory | I | App_Requirements §Connect |
| UIR-016 | The main window shall provide a separate Disconnect button, enabled at startup, that invokes the disconnect behaviour (FR-050–FR-057). | Mandatory | I | App_Requirements §Disconnect; impl. `app.py` |
| UIR-017 | The Remote Files group shall contain a drive-selection drop-down, positioned immediately before the Update button and sized equally with it (UIR-012), listing the drive letters `A:` through `P:`. The drop-down shall be wide enough to display the selected drive without clipping. Selecting an item triggers the remote drive-change behaviour (FR-100–FR-104). | Mandatory | I | impl. `app.py:setup_layout`, `mw_remote.py:change_drive` |
| UIR-018 | The Host Files multi-select widget (UIR-011) shall present a context menu on right-click containing the items **To Remote** (FR-119), **View/Edit**, **Rename**, and **Delete** (FR-110), with **To Remote** at the top of the menu separated from the file actions. **To Remote** and **Delete** act on every selected file; **View/Edit** and **Rename** act on the file under the cursor and are disabled when more than one file is selected (FR-110). *(v1.8; To Remote added v1.8.1; multi-select v2.3.)* | Mandatory | I | impl. `app.py:setup_layout`, `mw_context_menu.py:_host_context_menu` |
| UIR-019 | The Remote Files multi-select widget (UIR-012) shall present a context menu on right-click containing the items **To Host** (FR-119), **View**, **Rename**, and **Delete** (FR-111), with **To Host** at the top of the menu separated from the file actions. **To Host** and **Delete** act on every selected file; **View** and **Rename** act on the file under the cursor and are disabled when more than one file is selected (FR-111). *(v1.8; To Host added v1.8.1; multi-select v2.3.)* | Mandatory | I | impl. `app.py:setup_layout`, `mw_context_menu.py:_remote_context_menu` |
| UIR-079 | Each file pane (Host Files — UIR-011, Remote Files — UIR-012) shall present, in a row immediately above its list, a single-line **filter** field (FR-130) carrying translated placeholder text and a tooltip explaining the wildcard syntax, an inline **clear** (×) button (FR-135), and a visible indication (a coloured border) when the filter is active. *(v2.6.)* | Mandatory | I | impl. `mw_file_panes.py:_build_filter_sort_row`, `mw_file_panes.py:_render_file_list`; `lang/*.txt` (`main.filter_placeholder`, `main.filter_tooltip`) |
| UIR-080 | The filter row (UIR-079) shall also contain a **sort** control: a drop-down offering **Name** and **Extension** (FR-132; the option labels are translated, their underlying sort keys are not — CR-015) and a checkable **direction** button showing an ascending (`↑`) / descending (`↓`) arrow. *(v2.6.)* | Mandatory | I | impl. `mw_file_panes.py:_build_filter_sort_row`, `mw_file_panes.py:_update_sort_arrow`, `retranslate_ui`; `lang/*.txt` (`main.sort.name`, `main.sort.extension`, `main.sort_by_tooltip`, `main.sort_direction_tooltip`) |
| UIR-081 | Both file-list multi-select widgets (UIR-011, UIR-012) shall support drag-and-drop file transfer as specified by FR-136–FR-139 — each acting as a drag source and a drop target (highlighting itself with a coloured border while a valid drag hovers, FR-139), with an accepted drop confirmed before the transfer starts (FR-137d). *(v2.7.)* | Mandatory | I | impl. `gui/file_list_widget.py:FileListWidget`; `app.py:setup_layout`, `mw_transfers.py:_on_files_dropped`, `mw_transfers.py:_confirm_dnd_transfer`; `lang/*.txt` (`dialog.dnd_confirm.*`) |

### 4.3 Serial Configuration Dialog

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| UIR-020 | The Serial Configuration Dialog shall be a modal dialog titled "Serial Config". | Mandatory | I | App_Requirements §Serial Configuration Dialog; impl. `config_dialogs.py:__init__`, `config_dialogs.py:SerialConfigDialog` |
| UIR-021 | The dialog shall present a "Port Settings" group laid out in two columns, with the setting name left-justified in the first column and the setting field right-justified in the second column. | Mandatory | I | App_Requirements §Serial Configuration Dialog; impl. `config_dialogs.py:ConfigDialog`, `config_dialogs.py:create_widgets`, `config_dialogs.py:SerialConfigDialog` |
| UIR-022 | The dialog shall provide a Terminal Port drop-down list populated by enumerating the serial ports installed on the host. | Mandatory | T | App_Requirements §Serial Configuration Dialog; impl. `config_dialogs.py:SerialConfigDialog`, `config_dialogs.py:__init__` |
| UIR-023 | The dialog shall provide a Transfer Port drop-down list populated by enumerating the serial ports installed on the host. | Mandatory | T | App_Requirements §Serial Configuration Dialog; impl. `config_dialogs.py:SerialConfigDialog`, `config_dialogs.py:__init__` |
| UIR-024 | The dialog shall provide a Speed drop-down list with the values 300, 1200, 2400, 4800, 9600, 14400, 19200, 38400, 57600, 115200, 230400, 460800, and 921600; the default shall be 115200. | Mandatory | T | App_Requirements §Serial Configuration Dialog; impl. `config_dialogs.py:SerialConfigDialog`, `config_dialogs.py:__init__` |
| UIR-025 | The dialog shall provide a Data drop-down list with the values 7 and 8; the default shall be 8. | Mandatory | T | App_Requirements §Serial Configuration Dialog; impl. `config_dialogs.py:SerialConfigDialog`, `config_dialogs.py:__init__` |
| UIR-026 | The dialog shall provide a Parity drop-down list with the values NONE, ODD, EVEN, MARK, and SPACE; the default shall be NONE. | Mandatory | T | App_Requirements §Serial Configuration Dialog; impl. `config_dialogs.py:SerialConfigDialog`, `config_dialogs.py:__init__` |
| UIR-027 | The dialog shall provide a Stop Bits drop-down list with the values 1 and 2; the default shall be 1. | Mandatory | T | App_Requirements §Serial Configuration Dialog; impl. `config_dialogs.py:SerialConfigDialog`, `config_dialogs.py:__init__` |
| UIR-028 | The dialog shall provide a Flow Control drop-down list with the values NONE, XON/XOFF, RTS/CTS, and DSR/DTR; the default shall be NONE. The selected value shall be applied to the serial port when it is opened, mapping XON/XOFF, RTS/CTS, and DSR/DTR onto the corresponding software/hardware handshake (NONE disables all). *(v1.7.1: flow control is now applied at port open — see the Issue Resolution Log, OI-20.)* | Mandatory | T | App_Requirements §Serial Configuration Dialog; impl. `serial_manager.py:open_port` |
| UIR-029 | The dialog shall present a "Transmit Delay" group laid out in two columns, formatted as in UIR-021. | Mandatory | I | App_Requirements §Serial Configuration Dialog; impl. `config_dialogs.py:SerialConfigDialog`, `config_dialogs.py:__init__` |
| UIR-030 | The dialog shall provide an "msec/char" text field that defaults to 0 and is limited to integer values between 0 and 255 inclusive. The value shall be persisted as the `msec_char` setting. *(Inter-character transmission delay is a stored setting only; it is not yet applied during transmission — see CR-011.)* | Mandatory | T | App_Requirements §Serial Configuration Dialog; impl. `config_dialogs.py:SerialConfigDialog`, `config_dialogs.py:__init__` |
| UIR-031 | The dialog shall provide an "msec/line" text field that defaults to 0 and is limited to integer values between 0 and 255 inclusive. The value shall be persisted as the `msec_line` setting. *(Inter-line transmission delay is a stored setting only; it is not yet applied during transmission — see CR-011.)* | Mandatory | T | App_Requirements §Serial Configuration Dialog; impl. `config_dialogs.py:SerialConfigDialog`, `config_dialogs.py:__init__` |
| UIR-032 | The dialog shall provide a "Terminal Timeout (ms)" text field that defaults to 100 and is limited to integer values between 10 and 5000 inclusive, persisted as the `terminal_timeout_ms` setting. The value (converted to seconds) is applied as the pyserial read timeout when the Terminal Port is opened. *(v2.13.)* | Mandatory | T | impl. `config_dialogs.py:SerialConfigDialog`; `serial_manager.py:open_port` |
| UIR-033 | The dialog shall provide a "Transfer Timeout (ms)" text field that defaults to 100 and is limited to integer values between 10 and 5000 inclusive, persisted as the `transport_timeout_ms` setting. The value (converted to seconds) is applied as the pyserial read timeout when the Transport Port is opened; it bounds how long each X-Modem read waits for frame bytes, so it must be long enough for a frame to accumulate at the configured baud rate (NFR-003i). *(v2.13.)* | Mandatory | T | impl. `config_dialogs.py:SerialConfigDialog`; `serial_manager.py:open_port`; NFR-003i |

### 4.4 General Configuration Dialog

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| UIR-040 | The General Configuration Dialog shall be a modal dialog titled "General Config". | Mandatory | I | App_Requirements §General Configuration Dialog; impl. `config_dialogs.py:__init__`, `config_dialogs.py:GeneralConfigDialog` |
| UIR-041 | The dialog shall present a "Remote" group, laid out in two columns as in UIR-021, as the **first** group in the dialog. The group shall contain, in order, the remote-command fields: "List Files" (UIR-042), "Receive from Remote" (UIR-045), "Send to Remote" (UIR-046), "Rename" (UIR-055), and "Delete" (UIR-056). *(v2.1: replaces the former "Terminal Commands"/"Xmodem Commands" grouping; the Rename/Delete fields are relabelled without the "Remote" suffix now that group membership conveys it.)* | Mandatory | T | App_Requirements §General Configuration Dialog; impl. `config_dialogs.py:GeneralConfigDialog`, `config_dialogs.py:create_widgets`, `config_dialogs.py:_build_field` |
| UIR-042 | The dialog shall provide a "List Files" text field limited to 79 characters with a default value of "DIR". | Mandatory | T | App_Requirements §General Configuration Dialog; impl. `config_dialogs.py:GeneralConfigDialog`, `config_dialogs.py:__init__` |
| UIR-043 | *Withdrawn.* Formerly a "Change Disk" text field persisted as `change_disk_cmd`. Removed because the command was never sent to the remote and the drive-change behaviour is now provided by the Remote Files drive drop-down (FR-100–FR-104, UIR-017). The field and setting are no longer present in the dialog or config files. | — | — | impl. `config_dialogs.py:GeneralConfigDialog` |
| UIR-044 | The remaining general settings — "Xfer Launch Delay (s)" (UIR-049), "Xfer Inter-file Delay (s)" (UIR-052), "End of Line" (UIR-047), "Debug Logging" (UIR-050), "Echo Transfer Data" (UIR-058), "Viewer/Editor" (UIR-054), "Default Host Directory" (UIR-053), and "Boot Sequence" (UIR-059) — shall be presented below the Remote group (UIR-041), ungrouped, in a two-column layout as in UIR-021. *(v2.1: replaces the former "Xmodem Commands" group; v2.2: adds "Echo Transfer Data"; v2.16: adds "Boot Sequence".)* | Mandatory | I | App_Requirements §General Configuration Dialog; impl. `config_dialogs.py:GeneralConfigDialog`, `config_dialogs.py:create_widgets` |
| UIR-045 | The dialog shall provide a "Receive from Remote" text field limited to 79 characters with a default value of "PCPUT $1". | Mandatory | T | App_Requirements §General Configuration Dialog; impl. `config_dialogs.py:GeneralConfigDialog`, `config_dialogs.py:__init__` |
| UIR-046 | The dialog shall provide a "Send to Remote" text field limited to 79 characters with a default value of "PCGET $1". | Mandatory | T | App_Requirements §General Configuration Dialog; impl. `config_dialogs.py:GeneralConfigDialog`, `config_dialogs.py:__init__` |
| UIR-047 | The dialog shall provide an "End of Line" drop-down offering the mutually exclusive values Carriage Return (CR), Line Feed (LF), and Carriage Return/Line Feed (CR/LF), presented within the ungrouped two-column layout (UIR-044). *(v2.5.2: reworded from a radio-button group to the as-built drop-down — see the Issue Resolution Log, OI-23.)* | Mandatory | I | App_Requirements §General Configuration Dialog; impl. `config_dialogs.py:GeneralConfigDialog`, `config_dialogs.py:create_widgets` |
| UIR-048 | The Carriage Return (CR) value shall be the default selection. *(v2.5.2: reworded from "radio button" to the as-built drop-down value — see the Issue Resolution Log, OI-23.)* | Mandatory | T | App_Requirements §General Configuration Dialog; impl. `config_dialogs.py:GeneralConfigDialog`, `config_dialogs.py:__init__` |
| UIR-049 | The dialog shall provide an "Xfer Launch Delay (s)" integer field (0..60 inclusive) with a default value of 3, setting the seconds to wait after launching the remote transfer program (FR-087) before the X-Modem handshake begins. *(v1.3.1.)* | Mandatory | T | impl. `config_dialogs.py:GeneralConfigDialog`, `config_dialogs.py:__init__` |
| UIR-050 | The dialog shall provide a "Debug Logging" dropdown (`OFF`/`ON`, default `OFF`) controlling the verbose transfer debug output of FR-088. *(v1.3.1.)* | Mandatory | T | impl. `config_dialogs.py:GeneralConfigDialog` |
| UIR-052 | The dialog shall provide an "Xfer Inter-file Delay (s)" integer field (0..60 inclusive) with a default value of 2, setting the additional settle time waited between files in a multi-file batch after the terminal output goes idle and before the next launch command is sent (FR-109). *(v1.6.1.)* | Mandatory | T | impl. `config_dialogs.py:GeneralConfigDialog` |
| UIR-053 | The dialog shall provide a "Default Host Directory" text field and an associated browse button to specify the host directory used at startup (FR-060). This value is persisted in the configuration JSON file. The field is seeded from the stored configuration value; on Save the application shall change the active session host directory to follow the field **only when the field's value differs from the value it was seeded with** — saving the dialog with the field left unedited shall not alter the active session host directory (which may already differ from the stored value following a Change Directory, FR-062) nor revert it to the stored value. *(v2.11.2.)* | Mandatory | T | App_Requirements §General Configuration Dialog; impl. `config_dialogs.py:create_widgets`, `config_dialogs.py:on_browse`, `config_dialogs.py:GeneralConfigDialog`, `mw_config.py:menu_general_config` |
| UIR-054 | The dialog shall provide a "Viewer/Editor" text field with a default value of `notepad $1`, persisted as the `viewer_cmd` setting, specifying the command used to open a file for viewing/editing (FR-112). The `$1` token denotes the file path. *(v1.8.)* | Mandatory | T | impl. `config_dialogs.py:GeneralConfigDialog` |
| UIR-055 | The dialog shall provide a "Rename" text field (within the Remote group, UIR-041) limited to 79 characters with a default value of `REN $2=$1`, persisted as the `rename_remote_cmd` setting, specifying the remote command used to rename a remote file (FR-117). `$1` denotes the original filename and `$2` the new filename. *(v1.8; v2.1 relabelled from "Rename Remote" and moved into the Remote group.)* | Mandatory | T | impl. `config_dialogs.py:GeneralConfigDialog` |
| UIR-056 | The dialog shall provide a "Delete" text field (within the Remote group, UIR-041) limited to 79 characters with a default value of `ERA $1`, persisted as the `delete_remote_cmd` setting, specifying the remote command used to delete a remote file (FR-117). `$1` denotes the filename. *(v1.8; v2.1 relabelled from "Delete Remote" and moved into the Remote group.)* | Mandatory | T | impl. `config_dialogs.py:GeneralConfigDialog` |

### 4.5 Terminal Window

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| UIR-060 | The Terminal Window shall be a non-modal window titled "Terminal". | Mandatory | I | App_Requirements §Terminal Window; impl. `terminal_window.py:TerminalWindow`, `terminal_window.py:__init__` |
| UIR-061 | The Terminal Window shall contain a character-cell terminal view named "Receive" that renders the VT-100 screen (FR-091). *(v2.17: was a plain multi-line text area.)* | Mandatory | I | App_Requirements §Terminal Window; impl. `gui/terminal_view.py:TerminalView`, `terminal_window.py:create_widgets` |
| UIR-062 | The Receive view shall maintain a scrollback buffer retaining at least the most recent 1000 lines that have scrolled off the top of the screen, and shall auto-scroll to the newest output when the Autoscroll control (UIR-066) is enabled. *(v2.17: scrollback depth quantified; character-cell view.)* | Mandatory | D | App_Requirements §Terminal Window; impl. `gui/terminal_view.py:TerminalView`, `gui/terminal_view.py:refresh`, `gui/terminal_view.py:set_autoscroll` |
| UIR-063 | The Receive view shall not be an editable text field — its content is rendered from the engine — but it shall accept keyboard focus so that keys typed into it are transmitted to the Terminal Port (FR-096) rather than inserted as editable text. *(v2.17.)* | Mandatory | T | App_Requirements §Terminal Window; impl. `gui/terminal_view.py:TerminalView`, `gui/terminal_view.py:keyPressEvent` |
| UIR-064 | The Terminal Window shall provide a "Clear" button, left-aligned, below the Receive view. | Mandatory | I | App_Requirements §Terminal Window; impl. `terminal_window.py:TerminalWindow`, `terminal_window.py:create_widgets`, `terminal_window.py:clear_text` |
| UIR-065 | The Terminal Window shall provide a "Local Echo" checkbox, centred, that is unchecked (local echo off) by default. | Mandatory | T | App_Requirements §Terminal Window; impl. `terminal_window.py:TerminalWindow`, `terminal_window.py:create_widgets` |
| UIR-066 | The Terminal Window shall provide an "Autoscroll" checkbox, right-aligned, that is enabled by default. | Mandatory | T | App_Requirements §Terminal Window; impl. `terminal_window.py:TerminalWindow`, `terminal_window.py:create_widgets` |
| UIR-067 | The Terminal Window shall not provide a separate transmit field or Send button; the operator types directly into the Receive view and each keystroke is transmitted live (FR-096). A non-editable hint label below the control row shall indicate this. *(v2.17: replaced the transmit field and Send button with live keyboard input.)* | Mandatory | I | App_Requirements §Terminal Window; impl. `terminal_window.py:create_widgets` |
| UIR-068 | The Terminal Window shall provide a "Boot into CP/M" button, in the control row (UIR-064) to the right of the Clear button, that executes the configured boot sequence (FR-049). The button shall be disabled whenever the `boot_sequence` setting is empty and enabled when it is non-empty; its enabled state shall be re-evaluated whenever the configuration changes while the window is open. *(v2.16.)* | Mandatory | T | impl. `terminal_window.py:TerminalWindow`, `terminal_window.py:create_widgets`, `terminal_window.py:set_boot_enabled`, `mw_remote.py:show_terminal` |

### 4.6 Visual theme and modern layout (v1.3)

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| UIR-070 | The GUI shall apply a modern Material Design visual theme to all windows, dialogs, and widgets (via the `qt-material` stylesheet over PySide6 widgets), in place of the platform-default Tk appearance. | Mandatory | D | v1.3 UI migration; impl. `theme.py:apply_theme` |
| UIR-071 | The main window shall present the Connect, Disconnect, and Terminal actions of UIR-013 as a toolbar at the top of the window (above the file panes), with each action shown as a labelled, icon-bearing button. | Mandatory | I | v1.3 UI migration; impl. `app.py:setup_toolbar` |
| UIR-072 | The Host Files and Remote Files panes shall be separated by a user-draggable splitter that lets the user re-apportion horizontal space between the two panes; the split position is not required to persist between sessions. | Mandatory | D | v1.3 UI migration; impl. `app.py:setup_layout` |
| UIR-073 | The application shall, at startup, detect the host operating system's light/dark colour-scheme preference and apply the corresponding (light or dark) variant of the Material theme. If the preference cannot be determined, the application shall default to the dark variant. | Mandatory | T | v1.3 UI migration; impl. `theme.py:prefers_dark`, `theme.py:apply_theme` |
| UIR-074 | The status bar (UIR-010) shall display two connection indicators — one for the Terminal status flag (FR-001) and one for the Transport status flag (FR-002) — each rendering a distinct visual state for connected versus not-connected: coloured **green** when connected and **red** when not connected. *(v2.1.1: not-connected colour changed from grey to red.)* | Desirable | D | v1.3 UI migration; impl. `app.py:setup_status_bar`, `app.py:_make_indicator`, `app.py:_update_indicators` |
| UIR-078 | The application shall set a branded application icon at start-up, applied centrally to the `QApplication` (like the theme, CR-013) so that every window and dialog and the host operating system's taskbar/dock entry display it. The icon shall be the CP/M File Manager artwork, supplied as package data (DR-044). If the icon resource is absent the application shall fall back to the toolkit default icon and continue to start (consistent with the optional packaging icons, CR-006). *(v2.5.)* | Desirable | D | v2.5 application icon; impl. `theme.py:app_icon`, `app.py:main` |

### 4.7 Transfer Progress Dialog

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| UIR-051 | The Transfer Progress Dialog (FR-105) shall be a modal dialog reporting the progress of a transfer and offering cancellation. Its appearance and behaviour are specified by UIR-051a–UIR-051f. *(v1.5.)* | Mandatory | T | impl. `gui/transfer_dialog.py:TransferProgressDialog`; FR-105, FR-120 |
| UIR-051a | The dialog shall be modal and titled "Sending File" (Copy to Remote) or "Receiving File" (Copy to Host). | Mandatory | T | — |
| UIR-051b | The dialog shall display a label naming the file being transferred, a label showing the running "Blocks" and "Bytes" counts, a progress bar, and a centred **Cancel** button (FR-120, laid out per UIR-075). | Mandatory | T | — |
| UIR-051c | When more than one file is being transferred (FR-106), the dialog shall also display a "File `i` of `N`" batch-position label. *(v1.6.)* | Mandatory | T | — |
| UIR-051d | When the total size is known (sends) the progress bar shall track bytes transferred against the file size; when the total is unknown (receives) the progress bar shall be indeterminate. | Mandatory | T | — |
| UIR-051e | The dialog shall not present a window manual-close control — its lifetime is owned by the transfer, which closes it on completion, failure, or cancellation (FR-105/FR-120); the Cancel button requests cancellation rather than merely closing the dialog. | Mandatory | T | — |
| UIR-051f | On a cancellation request the Cancel button shall become disabled and indicate that cancellation is in progress. *(v1.9.)* | Mandatory | T | — |

### 4.8 File Action Dialog

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| UIR-057 | The File Action Dialog (FR-114/FR-115) shall be a modal dialog for a single file action. Its layout, per-action field behaviour, and title are specified by UIR-057a–UIR-057c. *(v1.8.)* | Mandatory | T | impl. `gui/file_action_dialog.py:FileActionDialog` |
| UIR-057a | The dialog shall contain a single-line filename text field, an **Apply** button, and a **Cancel** button laid out per UIR-075. | Mandatory | T | — |
| UIR-057b | For the Rename action the field shall be editable and pre-populated with the file's name (with the text pre-selected for quick replacement); for the Delete action the field shall be read-only and display the file's name. | Mandatory | T | — |
| UIR-057c | The dialog title shall name the action and target (e.g. "Rename File", "Delete Remote File"). | Mandatory | T | — |
| UIR-058 | The General Configuration Dialog shall provide an "Echo Transfer Data" dropdown (`OFF`/`ON`, default `OFF`), persisted as the `echo_transfer_data` setting, controlling whether X-Modem transfer bytes are echoed to the Terminal Window as `<HH>` hex tokens (FR-086). *(v2.2.)* | Mandatory | T | impl. `config_dialogs.py:GeneralConfigDialog`; FR-086 |
| UIR-059 | The General Configuration Dialog shall provide a multi-line "Boot Sequence" text field, persisted as the `boot_sequence` setting (default empty), in which the user enters the boot-sequence script (FR-047). The field shall be presented below the Remote group within the ungrouped layout (UIR-044) and rendered as a multi-line text editor. *(v2.16.)* | Mandatory | T | impl. `config_dialogs.py:GeneralConfigDialog`, `config_dialogs.py:_build_field` |
| UIR-089 | The General Configuration Dialog shall provide, in the "Remote" group below the Send to Remote field, a "Use XMODEM-1K" checkbox (persisted as the `xmodem_1k` setting, `OFF`/`ON`, default `OFF`). When enabled, host→remote sends shall use 1024-byte STX framing (NFR-003b) and the receive handshake shall poll CRC first (NFR-003g). *(v2.13.)* | Mandatory | T | impl. `config_dialogs.py:GeneralConfigDialog`, `ConfigDialog._build_field` checkbox type; `mw_transfers.py:_xmodem_1k_enabled`; NFR-003b, NFR-003g |
| UIR-090 | The General Configuration Dialog shall provide two text fields (limited to 79 characters, default blank) below the "Use XMODEM-1K" checkbox: "Receive from Remote (1K)" and "Send to Remote (1K)", persisted as `recv_remote_cmd_1k` and `send_remote_cmd_1k`. When XMODEM-1K mode is enabled (UIR-089), a non-blank `_1k` command shall replace the standard `recv_remote_cmd`/`send_remote_cmd` (UIR-045/UIR-046) used to launch the CP/M side of the transfer (`$1` = filename); a blank `_1k` command shall fall back to its standard counterpart. *(v2.13.)* | Mandatory | T | impl. `config_dialogs.py:GeneralConfigDialog`; `mw_transfers.py:_issue_remote_cmd` |

### 4.9 Common dialog conventions

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| UIR-075 | All dialogs shall lay out their confirm/cancel buttons consistently: when **both** buttons are present, the Cancel (reject) button shall be placed at the far left of the button row and the affirmative button (accept — e.g. "Apply" or "Save") at the far right, with the space between them filled by a flexible stretch; when **only one** button is present, that button shall be horizontally centred. This applies to the Serial and General Configuration Dialogs (Save/Cancel), the File Action Dialog (Apply/Cancel), and the About Dialog (OK). *(v1.8.2; About added v1.10.)* | Mandatory | T | impl. `gui/dialog_buttons.py:build_button_row`, `config_dialogs.py:create_widgets`, `file_action_dialog.py:FileActionDialog`, `about_dialog.py:AboutDialog` |

### 4.10 About Dialog

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| UIR-076 | The About Dialog (FR-022) shall be a modal dialog titled "About" displaying: the program name "CP/M File Manager"; the application version (DR-040), shown as "Version `<x.y.z>`"; a clickable hyperlink to the project's GitHub repository at `https://github.com/turbo-gecko/CPM_FM` that opens in the host's default browser; and a single **OK** button (centred per UIR-075) that closes the dialog. *(v1.10.)* | Mandatory | T | impl. `gui/about_dialog.py:AboutDialog`; FR-022, DR-040 |

### 4.11 Language Menu

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| UIR-077 | The Config > Language submenu (FR-122) shall present one entry per available language file (DR-042), the entry text being the language name capitalised (e.g. "English", "German", "French"); the language names themselves shall not be translated. The entries shall be mutually exclusive, with the entry for the active language shown checked. *(v2.0.)* | Mandatory | T | impl. `app.py:_setup_language_menu`, `menu_set_language`; FR-122 |

### 4.12 Transfer History Dialog

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| UIR-082 | The main-window toolbar (UIR-071) shall provide a **History** action that opens the Transfer History dialog (FR-143). *(v2.8.)* | Mandatory | I | impl. `app.py:setup_toolbar`, `mw_history.py:show_history`; `lang/*.txt` (`toolbar.history`) |
| UIR-083 | The Transfer History dialog (FR-143) shall be a modal dialog titled "Transfer History". Its filter row, table, buttons, and geometry persistence are specified by UIR-083a–UIR-083d. *(v2.8.)* | Mandatory | T | impl. `gui/transfer_history_dialog.py:TransferHistoryDialog`; `lang/*.txt` (`history.*`) |
| UIR-083a | The dialog shall contain a **filter row** with a **Direction** drop-down (All / To Remote / To Host) and a **Status** drop-down (All / Success / Failure / Cancelled / Skipped) whose option labels are translated while their underlying filter values are not (CR-015). *(Skipped status added v2.9.)* | Mandatory | T | — |
| UIR-083b | The dialog shall contain a read-only **table** with the columns Time, File, Direction, Status, Size, and Error, one row per entry, newest-first, with whole-row single selection. | Mandatory | T | — |
| UIR-083c | The dialog shall contain a button row with **Re-transfer** (enabled only when a row is selected — FR-144), **Export** and **Clear** (enabled only when the history is non-empty), and a **Close** button. | Mandatory | T | — |
| UIR-083d | The dialog's geometry shall persist across sessions (FR-004). | Mandatory | T | — |

### 4.13 Transfer File-Conflict Dialog

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| UIR-084 | The Transfer File-Conflict Dialog (FR-146) shall be a modal dialog titled "File Exists" that names the conflicting file and explains that it already exists at the destination, and presents three buttons — **Overwrite**, **Skip**, and **Cancel** — together with an **"Apply to all remaining conflicts"** checkbox (FR-147). The dialog shall not present a window manual-close control; closing it via the window manager shall be equivalent to **Cancel** (the safest default). *(v2.9.)* | Mandatory | T | impl. `gui/conflict_dialog.py:FileConflictDialog`; `lang/*.txt` (`dialog.conflict.*`); FR-146, FR-147 |

### 4.14 Invalid Filename Dialog

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| UIR-085 | The Invalid Filename Dialog (FR-149) shall be a modal dialog titled "Invalid CP/M File Name" for resolving a non-conforming upload name. Its content and behaviour are specified by UIR-085a–UIR-085c. *(v2.10.)* | Mandatory | T | impl. `gui/filename_validation_dialog.py:FilenameValidationDialog`; `lang/*.txt` (`dialog.invalid_name.*`); FR-148, FR-149 |
| UIR-085a | The dialog shall name the offending file, explain the CP/M 8.3 naming convention, and present an **editable name field** (pre-filled with a conforming suggestion) together with three buttons — **Rename**, **Skip**, and **Cancel**. | Mandatory | T | — |
| UIR-085b | **Rename** shall be accepted only when the entered name is a valid CP/M 8.3 name (DR-046); otherwise the dialog shall show an inline error and remain open. | Mandatory | T | — |
| UIR-085c | The dialog shall not present a window manual-close control; closing it via the window manager shall be equivalent to **Cancel** (the safest default). | Mandatory | T | — |

### 4.15 Backup and Restore

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| UIR-086 | The main-window toolbar (UIR-071) shall provide a **Backup** action — a labelled, icon-bearing button — that initiates the whole-drive backup of FR-150 (remote→host). *(v2.11.)* | Mandatory | I | impl. `app.py:setup_toolbar`, `mw_backup_restore.py:do_backup`; `lang/*.txt` (`toolbar.backup`) |
| UIR-087 | The main-window toolbar (UIR-071) shall provide a **Restore** action — a labelled, icon-bearing button — that initiates the whole-drive restore of FR-151 (host→remote). *(v2.11.)* | Mandatory | I | impl. `app.py:setup_toolbar`, `mw_backup_restore.py:do_restore`; `lang/*.txt` (`toolbar.restore`) |
| UIR-088 | The Backup/Restore confirmation dialog (FR-152) shall be a modal dialog titled "Confirm Backup"/"Confirm Restore" that warns that ALL files at the destination will be deleted and re-written, and presents a **Continue** button and a **Cancel** button with **Cancel** as the default (the safest choice). Closing the dialog via the window manager shall be equivalent to **Cancel**. *(v2.11.)* | Mandatory | T | impl. `mw_backup_restore.py:_on_backup_restore_confirm`; `lang/*.txt` (`dialog.backup_restore.*`, `button.continue`); FR-152 |

---

### 4.16 Manual Window

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| UIR-091 | The Manual Window (FR-023) shall be a non-modal, resizable window titled "User Manual" that displays the bundled user manual (DR-047). Its rendering, navigation, controls, and error handling are specified by UIR-091a–UIR-091d. *(v2.13.)* | Mandatory | T | impl. `gui/manual_dialog.py:ManualDialog`, `render_manual_html`; `lang/*.txt` (`manual.title`, `manual.load_error`, `button.close`); FR-023, DR-047 |
| UIR-091a | The window shall display the manual rendered from Markdown to HTML in a scrollable, read-only text view. | Mandatory | T | — |
| UIR-091b | Headings shall carry GitHub-style anchors so the manual's table-of-contents links navigate within the document; external `http(s)` links shall open in the host's default browser. | Mandatory | T | — |
| UIR-091c | The window shall provide a single **Close** button (centred per UIR-075) that dismisses it. | Mandatory | T | — |
| UIR-091d | If the manual file cannot be read, the window shall display an explanatory message rather than failing to open. | Mandatory | T | — |
| UIR-092 | The Remote Filesystem Unavailable dialog (FR-044) shall be a modal dialog whose body informs the user that the remote computer's file system cannot be accessed. It shall present exactly three buttons in a single row in the fixed left-to-right order **Abort**, **Continue**, **Terminal** (this fixed three-button order overrides the two-button arrangement of UIR-075, which does not define a three-button layout). Each button triggers the corresponding action in FR-045. *(v2.15.)* | Mandatory | T | impl. `gui/remote_unavailable_dialog.py:RemoteUnavailableDialog`; `lang/*.txt` (`dialog.remote_unavailable.title`, `dialog.remote_unavailable.body`, `button.abort`, `button.continue`, `button.terminal`); FR-044, FR-045 |

---

## 5. External Interface Requirements

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| IFR-001 | The application shall communicate with the remote CP/M system over a serial (RS-232 style) communications link. | Mandatory | T | App_Design §Purpose; impl. `serial_manager.py:SerialManager` |
| IFR-002 | The application shall support configuring two logical serial ports — a Terminal Port and a Transport Port — which may map to the same physical port. | Mandatory | T | App_Requirements §Serial Configuration Dialog; CLAUDE.md; impl. `config_dialogs.py:SerialConfigDialog`, `serial_manager.py:SerialManager` |
| IFR-003 | The application shall enumerate the serial ports installed on the host and present them for selection. | Mandatory | T | App_Requirements §Serial Configuration Dialog; impl. `mw_config.py:menu_serial_config` |
| IFR-004 | Configuration data shall be exchanged with the file system as JSON files. | Mandatory | T | App_Requirements §Load, §Save; impl. `config_handler.py:ConfigHandler`, `config_handler.py:load_json`, `config_handler.py:save_json`; tests `test_config_handler.py` |

---

## 6. Data Requirements — CP/M 4-Column DIR Parsing Algorithm

The following requirements define the algorithm for extracting remote file names from standard CP/M
2.2 four-column `DIR` output. All testable requirements in §6.1–§6.3 (DR-001–DR-026, DR-033 and
DR-033a) are verified by the unit tests in `tests/test_cpm_parser.py`, which cover line filtering, the
standard drive-prefix and vertical-bar formats, single-file and extensionless entries, multi-token base
join, whitespace/CRLF robustness, de-duplication, empty/edge inputs, and drive-prompt detection
(including ZCPR-style user-area prefixes) and drive-letter extraction.

### 6.1 Line filtering

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| DR-001 | The parser shall ignore lines that are empty or contain only whitespace. | Mandatory | T | App_Design §Ignore non-file lines; impl. `cpm_parser.py:CPMParser`, `cpm_parser.py:parse_dir_output` |
| DR-002 | The parser shall ignore lines that begin with a shell prompt of the form `C>` where `C` may be any drive letter. | Mandatory | T | App_Design §Ignore non-file lines; impl. `cpm_parser.py:CPMParser`, `cpm_parser.py:parse_dir_output` |
| DR-003 | The parser shall ignore lines that contain the substring "NO FILE". | Mandatory | T | App_Design §Ignore non-file lines; impl. `cpm_parser.py:CPMParser`, `cpm_parser.py:parse_dir_output` |
| DR-004 | The parser shall process only lines that start with the literal prefix `C:` (where `C` may be any drive letter). | Mandatory | T | App_Design §Identify file listing lines; impl. `cpm_parser.py:CPMParser`, `cpm_parser.py:parse_dir_output` |
| DR-005 | The parser shall process every line that starts with the drive prefix (DR-004), whether or not it contains the separator sequence space-colon-space (" : "). The separator only delimits multiple file entries on a line (DR-011); a directory containing a single file produces a line with no separator, which shall still be processed. *(v1.3.3: fixes the defect where a directory with a single file showed no entries because the separator was wrongly required as a line filter.)* | Mandatory | T | App_Design §Identify file listing lines; impl. `cpm_parser.py:parse_dir_output` |
| DR-006 | The parser shall additionally process file listing lines produced by CP/M variants (e.g. ZCPR/ZSDOS) that use the vertical bar `\|` as both the entry separator and a leading line marker, in place of the drive prefix and the space-colon-space delimiter. Such a line begins (after trimming) with `\|`, has no drive prefix, separates entries with `\|`, and presents each entry with a literal dot between the space-padded filename base and extension (e.g. `\|  ASM     .COM  \|  FILEATTR.COM`). Both this format and the standard drive-prefix format (DR-004/DR-005) shall be supported. | Mandatory | T | impl. `cpm_parser.py:CPMParser`, `cpm_parser.py:parse_dir_output` |

### 6.2 Entry extraction

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| DR-010 | For each identified file listing line, the parser shall remove the leading drive prefix and process only the remainder of the line. | Mandatory | T | App_Design §Strip drive identifier; impl. `cpm_parser.py:CPMParser`, `cpm_parser.py:parse_dir_output` |
| DR-011 | The parser shall split each processed line into individual file entries using the space-colon-space delimiter. | Mandatory | T | App_Design §Split file entries; impl. `cpm_parser.py:CPMParser`, `cpm_parser.py:parse_dir_output` |
| DR-012 | For each file entry, the parser shall replace any sequence of one or more consecutive spaces with a single space and trim leading and trailing whitespace. | Mandatory | T | App_Design §Normalise whitespace; impl. `cpm_parser.py:CPMParser`, `cpm_parser.py:parse_dir_output` |
| DR-013 | For each normalised entry, the parser shall split into tokens by whitespace. If two or more tokens are present, the last token is the file extension and all preceding tokens are the filename base concatenated without spaces. If exactly one token is present, it is a filename with no extension (CP/M leaves the space-padded extension field blank, e.g. `LICENCE`). | Mandatory | T | App_Design §Parse filename and extension; impl. `cpm_parser.py:CPMParser`, `cpm_parser.py:parse_dir_output` |
| DR-014 | The parser shall construct each canonical filename in the format `<filename_base>.<extension>`, except for an extensionless entry (DR-013) which is constructed as `<filename_base>` with no trailing dot, so the listed name matches the host filename. | Mandatory | T | App_Design §Construct full filename; impl. `cpm_parser.py:CPMParser`, `cpm_parser.py:parse_dir_output` |
| DR-015 | For vertical-bar format lines (DR-006), where the dot delimiting the extension is already present in the output, the parser shall construct each canonical filename by removing all internal whitespace from the entry (the filename base is space-padded), yielding `<filename_base>.<extension>`. A trailing dot left by an empty extension field shall be removed so the result matches the extensionless convention of DR-014. | Mandatory | T | impl. `cpm_parser.py:parse_dir_output` |

### 6.3 Output and robustness

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| DR-020 | The parser shall store each constructed filename as a key in a dictionary with the boolean value `True`; duplicate filenames shall overwrite the existing key (no duplicate keys). | Mandatory | T | App_Design §Store filenames; impl. `cpm_parser.py:CPMParser`, `cpm_parser.py:parse_dir_output` |
| DR-021 | The parser shall return a Python `dict` whose keys are filename strings — of the form "NAME.EXT", or "NAME" for an extensionless file (DR-013/DR-014) — and whose values are the boolean literal `True`, containing only valid filenames extracted from the input. | Mandatory | T | App_Design §Output format; impl. `cpm_parser.py:CPMParser`, `cpm_parser.py:parse_dir_output` |
| DR-022 | The parser shall preserve the exact case of filename and extension characters as provided in the input. | Mandatory | T | App_Design §Case sensitivity; impl. `cpm_parser.py:CPMParser`, `cpm_parser.py:parse_dir_output` |
| DR-023 | The parser shall skip empty entries (those with no tokens after whitespace normalisation). A single-token entry is not malformed: it is an extensionless filename and shall be listed (DR-013). | Mandatory | T | App_Design §Handle edge cases; impl. `cpm_parser.py:CPMParser`, `cpm_parser.py:parse_dir_output` |
| DR-024 | The parser shall not raise exceptions for invalid or unexpected input. | Mandatory | T | App_Design §Handle edge cases; impl. `cpm_parser.py:CPMParser`, `cpm_parser.py:parse_dir_output` |
| DR-025 | The parser shall return an empty dictionary if no valid file entries are found. | Mandatory | T | App_Design §Handle edge cases; impl. `cpm_parser.py:CPMParser`, `cpm_parser.py:parse_dir_output` |
| DR-026 | The parser shall tolerate irregular spacing, extra colons within filenames, and mixed line endings (`\n`, `\r\n`). | Mandatory | T | App_Design §Input robustness; impl. `cpm_parser.py:CPMParser`, `cpm_parser.py:parse_dir_output` |
| DR-033 | The drive-prompt detection routine shall report a drive prompt for drive `X` as present when any non-blank line of the captured terminal text, after stripping surrounding whitespace and comparing case-insensitively, matches a CP/M drive prompt for drive `X`: an optional run of decimal digits (a ZCPR-style user-area number), the drive letter `X`, an optional run of decimal digits, then a closing `>` (e.g. `X>`, `X0>`, `4X>`). Blank lines shall be ignored. Path-style prompts that contain a `:` (e.g. `A0:BASE>`) are out of scope. *(v2.15: generalised from a bare `X>` prefix to also accept ZCPR-style user-area digits — see the Issue Resolution Log, OI-30.)* | Mandatory | T | impl. `cpm_parser.py:has_drive_prompt`; FR-101, FR-102; tests `test_cpm_parser.py` |
| DR-033a | The application shall provide a drive-prompt letter-extraction routine that, applying the same matching rule as DR-033 but without a target drive letter, returns the drive letter (`A`–`P`, upper-cased) of the first CP/M drive prompt appearing on a non-blank line of the captured terminal text, or no value when none is present. It is used by the post-connect probe (FR-041/FR-042) to discover the remote's current drive. *(v2.15.)* | Mandatory | T | impl. `cpm_parser.py:drive_prompt_letter`; FR-041, FR-042; tests `test_cpm_parser.py` |

### 6.4 Parser constraints

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| DR-030 | The parser assumes input conforming to standard CP/M 2.2 `DIR` output format (8.3 filenames, space-padded). | Mandatory | A | App_Design §Constraints; impl. `cpm_parser.py:CPMParser` |
| DR-031 | The parser is not required to support long filenames or non-ASCII characters. | Optional | A | App_Design §Constraints; impl. `cpm_parser.py:CPMParser` |
| DR-032 | The parser is not required to parse file sizes, dates, or attributes — only names and extensions. | Mandatory | A | App_Design §Constraints; impl. `cpm_parser.py:CPMParser` |

### 6.5 Application version

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| DR-040 | The application version number shall be stored in a plain-text file named `version.txt` located in the `src/` folder (a sibling of the `cpm_fm` package). The file shall contain a single semantic-version string (e.g. `2.0.0`); surrounding whitespace is insignificant. The application shall read its version from this file. *(v1.10.)* | Mandatory | T | impl. `version.py:get_version` |
| DR-041 | The application version (DR-040) shall match the version of this SRS (the document Version field). If `version.txt` cannot be read, the application shall fall back to the sentinel version string `0.0.0` and continue to operate rather than failing to start. *(v1.10. The application version tracks the SRS Version field at every release; the per-version record is the Change History companion, [`docs/requirements_change_history.md`](requirements_change_history.md) — it is no longer duplicated here.)* | Mandatory | T | impl. `version.py:get_version`, `__init__.py:__version__` |

### 6.6 Language files

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| DR-042 | User-facing strings (FR-121) shall be stored in per-language text files. Their location, naming, format, comment/blank-line handling, placeholder substitution, and persistence are specified by DR-042a–DR-042f. *(v2.0.)* | Mandatory | T | impl. `utils/i18n.py:_parse`, `available_languages`, `_lang_path`; `gui/window_state.py:language`; `lang/*.txt`; `pyproject.toml` package-data |
| DR-042a | The per-language files shall be located in the `lang/` folder inside the `cpm_fm` package (`src/cpm_fm/lang/`), shipped as package data so they are present in an installed distribution. | Mandatory | T | — |
| DR-042b | Each file shall be UTF-8 and named `lang_<language>.txt`, where `<language>` is the language name (e.g. `lang_english.txt`, `lang_german.txt`, `lang_french.txt`). | Mandatory | T | — |
| DR-042c | The file format shall be one `key = value` entry per line, split on the **first** `=` (so a value may itself contain `=`); whitespace around the key and value is insignificant. | Mandatory | T | — |
| DR-042d | Blank lines and lines whose first non-whitespace character is `#` (comments) shall be permitted and ignored. | Mandatory | T | — |
| DR-042e | Values shall be `str.format` templates whose named placeholders (e.g. `{name}`, `{index}`, `{count}`, `{error}`, `{drive}`) are substituted at run time. | Mandatory | T | — |
| DR-042f | The active language shall be persisted (with the rest of the UI/session state, see FR-124) and restored on the next start. | Mandatory | T | — |
| DR-043 | The English language file (`lang_english.txt`) shall be the complete reference language. Its completeness and fallback role are specified by DR-043a–DR-043b. *(v2.0.)* | Mandatory | T | impl. `lang/lang_english.txt`, `utils/i18n.py:tr`; tests `test_i18n.py` |
| DR-043a | `lang_english.txt` shall define a value for every key used by the application, and its values shall reproduce the application's canonical English text. | Mandatory | T | — |
| DR-043b | It shall serve as the fallback for any key missing from another language (FR-124); other shipped language files shall define the same set of keys. | Mandatory | T | — |

### 6.7 Application icon

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| DR-044 | The runtime application icon (UIR-078) shall be stored as a PNG named `cpm-fm.png` in the `icons/` folder inside the `cpm_fm` package (`src/cpm_fm/icons/`), shipped as package data so it is present in an installed distribution and in a frozen (PyInstaller) bundle. The application shall resolve it relative to the package location so the same lookup works from a source checkout, an installed wheel, and a one-file bundle. The per-platform packaging icons (`assets/icon.ico`/`.icns`/`.png` and the freedesktop `assets/icons/hicolor/` tree) and all icon sizes are generated from the single source artwork `src/icons/cpm-fm-2.png` by `tools/make_icons.py`. *(v2.5.)* | Desirable | T | impl. `gui/theme.py:app_icon` (`APP_ICON_PATH`); `pyproject.toml` package-data; `_pyinstaller_common.py:build_datas`; `tools/make_icons.py` |

### 6.8 Transfer history file

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| DR-045 | The transfer history (FR-140/FR-141) shall be stored as a UTF-8 JSON file — a list of entry objects, oldest first — at `~/.cpm_fm_history.json` by default (the path is injectable for testing). Each entry object holds the flat fields of FR-140 (`timestamp`, `filename`, `path`, `direction`, `status` — one of `success`/`failure`/`cancelled`/`skipped`, `size`, `error`, `retry`). The file is rewritten after each mutation (add/clear) and re-read on construction; a missing/unreadable/malformed file, or a document that is not a JSON list, yields an empty history. *(v2.8.)* | Mandatory | T | impl. `transfer_history.py:TransferHistory`, `transfer_history.py:default_history_path`, `transfer_history.py:_read_file`, `transfer_history.py:_write_file` (default name `DEFAULT_HISTORY_FILENAME`); tests `test_transfer_history.py` |

### 6.9 CP/M file-naming convention

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| DR-046 | A **CP/M 8.3 file name** (used by the upload validation of FR-148/FR-149) shall consist of a **base** of 1–8 characters and an optional **extension** of up to 3 characters, separated by a single `.`; a name with no `.` is a base-only name, and a trailing `.` (empty extension, e.g. `FOO.`) is non-conforming. Every character of the base and extension shall be drawn from the permitted set: the space and the reserved CP/M delimiter/wildcard characters `< > . , ; : = ? * [ ] \| / \` (and any non-printable or non-ASCII character) shall **not** appear. Case shall not be significant for conformance — the CP/M CCP folds command-line arguments to upper case, so a lower-case host name uploads unchanged. A conforming-name **suggestion** (FR-149) shall be derivable from an arbitrary host name by upper-casing, removing disallowed characters, and truncating the base/extension to 8/3 characters, falling back to a base of `FILE` when nothing usable remains. *(v2.10.)* | Mandatory | T | impl. `cpm_parser.py:is_valid_8_3`, `cpm_parser.py:suggest_8_3`, `cpm_parser.py:CPM_INVALID_CHARS`; tests `test_filename_validation.py` |

### 6.10 Bundled user manual

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| DR-047 | The user manual (FR-023) shall ship with the application as a UTF-8 Markdown file `cpm_fm_manual.md`. Its location/resolution, rendering, and missing-file handling are specified by DR-047a–DR-047c. *(v2.13.)* | Mandatory | T | impl. `manual_dialog.py:load_manual_markdown`, `manual_dialog.py:render_manual_html` (manual at `MANUAL_PATH`); `_pyinstaller_common.py:build_datas`/`HIDDEN_IMPORTS`; `pyproject.toml` (`markdown` dependency, `docs/*.md` package data) |
| DR-047a | The file shall be located inside the package at `src/cpm_fm/docs/`, resolved at run time relative to the module file so the same lookup works from source, from an installed wheel (shipped as package data), and from a frozen (PyInstaller) bundle, where the file is placed at `cpm_fm/docs/`. | Mandatory | T | — |
| DR-047b | The file shall be rendered to HTML for display (UIR-091) using the `markdown` library with the `toc`/`tables`/`fenced_code`/`attr_list`/`sane_lists` extensions and a GitHub-compatible heading slugify. | Mandatory | T | — |
| DR-047c | A missing or unreadable file shall not block opening the Manual Window (UIR-091); the window shall instead show an explanatory message. | Mandatory | T | — |

---

## 7. Design Constraints

> **Architectural design constraints have moved.** The constraints governing project structure and
> module organisation (CR-001–CR-009), GUI toolkit and visual theme (CR-012, CR-013), and layer
> decoupling (CR-014) now live in the companion **Software Architecture Description**,
> [`docs/cpm_fm_architecture.md`](cpm_fm_architecture.md) (§A4–A6). Their IDs are unchanged. The
> behavioural/functional constraints below remain here.

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| CR-010 | The Copy to Remote and Copy to Host actions shall be guarded so that a transfer is only attempted when **both** the Terminal status flag and the Transport status flag are true (consistent with FR-080); otherwise an error dialog with the body text "Transport port not connected" shall be shown and the transfer shall not proceed. | Mandatory | T | App_Requirements §Copy to Remote, §Copy to Host; impl. `mw_transfer_batches.py:do_copy_to_remote`, `mw_transfer_batches.py:do_copy_to_host` |
| CR-011 | The following settings are persisted but their behaviour is deferred to a future release and is not implemented in the current baseline: `msec_char` (UIR-030) and `msec_line` (UIR-031). *(v1.3.1: `recv_remote_cmd`/`send_remote_cmd` are no longer deferred — see FR-087. Later: `change_disk_cmd` was removed entirely rather than deferred — see UIR-043 (Withdrawn), FR-100–FR-104.)* | Mandatory | I | impl. survey of `app.py` |
| CR-015 | Internationalisation (FR-121) shall translate only human-facing prose. Values that are semantically significant or part of a protocol/command — drop-down option *values* (parity, flow control, speed, data/stop bits, EOL `CR`/`LF`/`CRLF`, debug `ON`/`OFF`), CP/M drive letters, and configurable command templates (e.g. `DIR`, `PCGET $1`, `REN $2=$1`) — shall not be translated, so that saved configuration and serial behaviour are unaffected by the active language. *(v2.0.)* | Mandatory | T | impl. `config_dialogs.py:ConfigDialog` (field `label_key` translated, option values not), `transfer_history_dialog.py:_cell_text`; FR-121 |

---

## 8. Non-Functional Requirements

> **Architectural NFRs have moved.** The concurrency/threading model (NFR-001, NFR-004) and the
> internationalisation extensibility constraint (NFR-005) now live in the companion **Software
> Architecture Description**, [`docs/cpm_fm_architecture.md`](cpm_fm_architecture.md) (§A7). Their IDs
> are unchanged. The remaining non-functional requirements below stay here.

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| NFR-002 | The application shall support both the flat and nested JSON configuration file shapes for serial settings: it shall first normalise an optional outer `serial` sub-dict (falling back to the top-level dict when absent), then resolve each pyserial parameter from the accepted config key(s) below, in the order listed. Port: `terminal_port` (Terminal Port) / `transport_port` (Transport Port), falling back respectively to `transfer_port` / `terminal_port` when the primary key is absent. Baud rate: `speed`. Byte size: `data`, then `data_bits`. Stop bits: `stopbits`, then `stop_bits`. Parity: `parity` (case-insensitive `NONE`/`EVEN`/`ODD`/`MARK`/`SPACE`, defaulting to `NONE`). Flow control: `flow`, then `flow_control`. Per-port read timeout: `terminal_timeout_ms` (Terminal Port) / `transport_timeout_ms` (Transport Port). This list is exhaustive; any other key is ignored. | Mandatory | T | CLAUDE.md §Two config JSON formats; impl. `serial_manager.py:open_port`; tests `test_serial_manager.py` |

### 8.1 X-Modem transfer protocol

The following requirements define the X-Modem implementation used for all file transfers
(FR-080–FR-086). They are functional protocol requirements retained under the `NFR-` prefix for
traceability continuity (they replace the former monolithic NFR-003, decomposed for atomicity per
ISO/IEC/IEEE 29148 *singularity*); their reclassification to a functional/data category is tracked as a
future refactor in the Issue Resolution Log (OI-27).

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| NFR-003a | By default the X-Modem implementation shall transmit each packet as a 128-byte data field framed with the SOH (0x01) start byte. | Mandatory | T | impl. `xmodem.py:send_file`; tests `test_xmodem.py` (per-packet progress) |
| NFR-003b | When XMODEM-1K mode is enabled (UIR-089), host→remote sends shall instead transmit each packet as a 1024-byte data field framed with the STX (0x02) start byte, independent of the error-check mode. *(v2.13.)* | Mandatory | T | UIR-089; impl. `xmodem.py:send_file`; tests `test_xmodem.py` (1K STX send) |
| NFR-003c | The final transmitted packet shall be padded to a full data field (128 or 1024 bytes per the selected packet size) using the pad byte 0x1A (SUB / Ctrl-Z, the CP/M end-of-file convention), and the trailer shall be computed over the padded field. | Mandatory | T | impl. `xmodem.py:send_file`; tests `test_xmodem.py` (EOF padding) |
| NFR-003d | The implementation shall support **checksum** error-check mode — the arithmetic sum of the data bytes modulo 256, carried as a 1-byte trailer — selected when the receiver polls with NAK (0x15). | Mandatory | T | impl. `xmodem.py:_calculate_checksum`, `_trailer`, `_trailer_ok`; tests `test_xmodem.py` (independent checksum/trailer vectors) |
| NFR-003e | The implementation shall support **CRC** error-check mode — CRC-16/XMODEM (polynomial 0x1021, initial value 0x0000), carried as a 2-byte big-endian trailer — selected when the receiver polls with `'C'` (0x43). *(v1.3.1.)* | Mandatory | T | impl. `xmodem.py:_crc16`, `_trailer`, `_trailer_ok`; tests `test_xmodem.py` (canonical CRC/trailer vectors) |
| NFR-003f | When receiving, the application shall by default poll with NAK (checksum) **first** and fall back to `'C'` (CRC) only if the sender does not answer NAK, because the CP/M-side senders are checksum-only and abort on a stray `'C'` ("Unknown response from host"). *(v1.6.1.)* | Mandatory | T | impl. `xmodem.py:receive_file`; tests `test_xmodem.py` (polls checksum not CRC first; falls through to CRC) |
| NFR-003g | When XMODEM-1K mode is enabled (UIR-089), the receive handshake shall instead poll with `'C'` (CRC) **first** (falling back to NAK), because a 1K-capable sender only switches to 1024-byte STX frames once the receiver has requested CRC mode. *(v2.13.)* | Mandatory | T | UIR-089; impl. `xmodem.py:receive_file`; tests `test_xmodem.py` (1K polls CRC first) |
| NFR-003h | The receiver shall accept both SOH frames carrying 128 data bytes and STX (0x02) frames carrying 1024 data bytes (XMODEM-1K) from 1K-capable senders such as PCPUT1K. *(v1.3.1.)* | Mandatory | T | impl. `xmodem.py:receive_file`; tests `test_xmodem.py` (accepts 1K STX frame) |
| NFR-003i | The receiver shall reassemble each frame field (header, data, trailer) across as many underlying port reads as needed, because the transport port's read timeout is short relative to the time to transmit a 1024-byte frame; a single read would otherwise return only part of a frame and desynchronise the stream (a stray byte downstream being misread as EOT, ending the transfer early with a truncated file). *(v2.13.)* | Mandatory | T | impl. `xmodem.py:_read_exact`, `receive_file`; tests `test_xmodem.py` (1K frame split across short reads) |
| NFR-003j | If the sender falls **silent** after the final packet (e.g. its EOT is lost or corrupted while every data byte has already been received), the receiver shall, after a bounded number of consecutive read time-outs, finish with the data received rather than retrying indefinitely. Only silence (a read time-out) shall count toward this bound — any byte that arrives (a frame, an EOT, or a stray byte) resets it — so the receiver keeps NAKing and resynchronises on the retransmitted frame and never abandons a still-active transfer part-way (which would otherwise truncate it, a particular risk on 1K where a single lost frame-start byte turns a 1024-byte payload into stray bytes). *(v2.13.)* | Mandatory | T | impl. `xmodem.py:receive_file`; tests `test_xmodem.py` (completes when EOT lost; resyncs after stray bytes) |
| NFR-003k | When a correctly-framed packet carries the sequence number of the previously-accepted packet (a duplicate the sender may resend if its prior ACK was lost), the receiver shall re-ACK it without storing its payload a second time, per the X-Modem protocol. | Mandatory | T | impl. `xmodem.py:receive_file`; tests `test_xmodem.py` (re-ACKs duplicate packet once) |
| NFR-003l | When a received frame fails validation — a short header or payload, a sequence/complement mismatch (`seq + ~seq != 255`), or a failed trailer check — the receiver shall respond with NAK to request retransmission and resynchronise on the retransmitted frame rather than aborting. | Mandatory | T | impl. `xmodem.py:receive_file`, `_trailer_ok`; tests `test_xmodem.py` (recovers from corrupt trailer) |
| NFR-003m | On a cancellation request (FR-120) the implementation shall abort the transfer by transmitting the CAN (0x18) byte sequence on the Transport Port, by which the remote program also aborts. *(v1.9.)* | Mandatory | T | FR-120; impl. `xmodem.py:_abort`, `send_file`, `receive_file`; tests `test_xmodem.py` (cancel aborts and sends CAN) |
| NFR-003n | On abort the implementation shall flush the Transport Port in **both** directions — discarding any partially-transmitted packet still queued for transmit and any data the remote was still sending — in the order: transmit-buffer discard, then CAN sent and given a bounded wait to drain, then receive-buffer discard, so the CAN itself is not discarded and the abort takes effect immediately rather than appearing to continue until the buffers empty. *(v2.13.1.)* | Mandatory | T | impl. `xmodem.py:_abort`; tests `test_xmodem.py` (cancel flushes serial in both directions) |
| NFR-003o | The wait for the CAN bytes to drain shall be time-bounded rather than an unbounded `flush()` (`serial.Serial.flush()` busy-waits on `out_waiting` with no timeout), so that a flow-control stall — e.g. hardware (RTS/CTS) or software (XON/XOFF) flow control held off because the aborting remote has stopped asserting CTS or sent XOFF — cannot block the abort, and therefore the transfer worker thread, indefinitely; any CAN bytes still queued when the bound elapses are transmitted by the OS in the background while the port remains open. *(v2.13.2.)* | Mandatory | T | impl. `xmodem.py:_drain_tx`, `_abort`; tests `test_xmodem.py` (does not hang when TX cannot drain) |
| NFR-003p | When a transmitted packet is NAK'd or goes unanswered, the sender shall retransmit the same packet (its sequence number unchanged) for up to a bounded number of attempts (10); if the packet is still not acknowledged after the final attempt, the sender shall abort the transfer and return failure rather than retransmitting indefinitely. *(v2.14.1.)* | Mandatory | T | impl. `xmodem.py:send_file`; tests `test_xmodem.py` (aborts after NAK exhaustion) |
| NFR-003q | When the sender transmits EOT before any data packet, the receiver shall accept it as a valid, empty transfer — ACKing the EOT and writing a zero-length file — rather than treating the absent data as an error. *(v2.14.1.)* | Mandatory | T | impl. `xmodem.py:receive_file`; tests `test_xmodem.py` (empty transfer writes empty file) |

---

## 9. Requirements Traceability Summary

| Source section | Requirement IDs |
|----------------|-----------------|
| App_Design §Purpose | STR-001, STR-002, STR-003, IFR-001 |
| App_Requirements §Look and Feel / Main Program GUI | UIR-001 – UIR-015 |
| App_Requirements §Load / Save / Exit | FR-010 – FR-016 |
| App_Requirements §Serial / General (menu) | FR-020, FR-021 |
| App_Requirements / App_Design §Connecting | FR-030 – FR-040 (FR-035 removed in v1.2) |
| App_Requirements / App_Design §Disconnecting | FR-050 – FR-057 |
| App_Requirements §Host Files / Change Directory / Refresh | FR-060 – FR-063 |
| App_Requirements §General Configuration Dialog | UIR-040 – UIR-053 |
| App_Requirements / App_Design §Populating remote file list | FR-070 – FR-079 |
| App_Requirements / App_Design §File Transfers | FR-080 – FR-086, FR-082→NFR-003a–NFR-003q, FR-086 impl. |
| App_Design §Receiving / Sending data | FR-090 – FR-098 |
| App_Requirements §Main Program GUI (Terminal/Disconnect buttons) | UIR-016, FR-097 |
| App_Requirements §Serial Configuration Dialog | UIR-020 – UIR-033, IFR-002, IFR-003 |
| App_Requirements §General Configuration Dialog | UIR-040 – UIR-050 |
| App_Requirements §Terminal Window | UIR-060 – UIR-068 |
| v1.3 UI migration (PySide6 + Material) | UIR-070 – UIR-074, CR-012 – CR-014, NFR-004; revises STR-002, UIR-013, NFR-001 |
| App_Design §DIR parsing algorithm | DR-001 – DR-032 |
| App_Design §Project Structure / Class Files / Code Quality | CR-001 – CR-009 |
| Deferred / as-built constraints (impl. survey) | CR-010, CR-011, NFR-001, NFR-002, NFR-003a – NFR-003q |
| App_Design §Program state | FR-001 – FR-003 |
| v1.8 file context-menu actions | FR-110 – FR-119, UIR-018, UIR-019, UIR-054 – UIR-057 |
| v1.8.2 common dialog conventions | UIR-075 |
| v1.9 cancel in-progress transfer | FR-120; revises UIR-051, NFR-003m |
| v1.10 versioning and About dialog | FR-022, UIR-004, UIR-076, DR-040, DR-041; revises UIR-075 |
| v2.0 internationalisation | FR-121 – FR-124, UIR-077, DR-042, DR-043, CR-015, NFR-005; revises UIR-003, DR-041, CR-014 |
| v2.1 General Config "Remote" group | revises UIR-041, UIR-044, UIR-055, UIR-056, DR-041 |
| v2.1.1 main-window layout & indicator colour | revises FR-063, UIR-011, UIR-012, UIR-017, UIR-074, DR-041 |
| v2.2 optional transfer-data echo | UIR-058; revises FR-086, UIR-044, DR-041 |
| v2.3 multi-file context-menu actions (Delete, To Remote/To Host) | revises FR-110, FR-111, FR-115, FR-116, FR-117, FR-119, UIR-018, UIR-019 |
| v2.4 title bar config name & Host Files directory in group title | FR-125, FR-126, UIR-005; revises UIR-011 |
| v2.5 application icon | UIR-078, DR-044; revises CR-006, DR-041 |
| v2.6 file list filter / sort | FR-130 – FR-135, UIR-079, UIR-080; revises FR-078, DR-041 |
| v2.7 drag-and-drop file transfer | FR-136 – FR-139, UIR-081; revises DR-041 |
| v2.8 transfer history | FR-140 – FR-144, UIR-082, UIR-083, DR-045; revises DR-041 |
| v2.9 transfer file-conflict handling | FR-145 – FR-147, UIR-084; revises FR-140, FR-142, UIR-083, DR-045 |
| v2.10 host→remote filename validation | FR-148, FR-149, UIR-085, DR-046; revises FR-140, FR-142 |
| v2.11 whole-drive backup and restore | FR-150 – FR-154, UIR-086 – UIR-088; revises DR-041 |
| v2.13 selectable XMODEM-1K transfer mode | UIR-089, UIR-090; revises NFR-003b, NFR-003g, NFR-003i, NFR-003j, FR-146 |
| v2.13 configurable per-port serial read timeouts | UIR-032, UIR-033 |
| v2.13 in-app user manual (Help > Manual) | FR-023, UIR-091, DR-047; revises UIR-004 |
| v2.16 configurable boot-into-CP/M sequence | FR-047 – FR-049, UIR-059, UIR-068; revises FR-044, UIR-044 |
| v2.17 interactive VT-100 terminal | FR-157, FR-158; revises FR-091 – FR-096, FR-098, UIR-061 – UIR-063, UIR-067; removes FR-155, FR-156 |
| v2.18 requirements-quality pass (ISO 29148) + terminal grid reflow | FR-091a, FR-157a – FR-157h; revises FR-004, FR-036, FR-090, FR-091, FR-093, FR-131, FR-157, FR-158, NFR-002, UIR-062, UIR-064, UIR-065; FR-155/FR-156 priority corrected to `—` |

---

## 10. Issue Resolution Log

The Issue Resolution Log has been moved to a companion file to keep this document small:
**[`docs/requirements_issue_log.md`](requirements_issue_log.md)**. It records the resolution of
ambiguities and gaps (OI-01–OI-26) found during requirements reviews; all are closed.

---

## 11. Change History

The Change History has been moved to a companion file to keep this document small:
**[`docs/requirements_change_history.md`](requirements_change_history.md)**. It records every
versioned change to this SRS and the application (the version field, DR-040/DR-041, is updated
with each entry).
