# CP/M File Manager — Software Requirements Specification

| Field | Value |
|-------|-------|
| Document title | CP/M File Manager Software Requirements Specification (SRS) |
| Document ID | CPM-FM-SRS |
| Version | 1.7.2 |
| Status | Reviewed |
| Standard | ISO/IEC/IEEE 29148:2018 |
| Owner | Project maintainer |
| Date | 2026-06-13 |
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
to the remote CP/M system, list remote files, and (in future) copy files in both directions. A
non-modal terminal window enables direct serial interaction with the remote system.

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
| FR-004 | On exit, the application shall persist the size and position (geometry) of each of its windows and dialogs — the main window, the Terminal Window, and the Serial and General Configuration Dialogs — to host-native persistent storage, and shall restore each window's saved geometry the next time that window is shown. The Host/Remote splitter position is excluded (UIR-072). Geometry is stored via `QSettings` under organisation `turbo-gecko`, application `cpm-fm`. | Mandatory | D | impl. `app.py:__init__`, `app.py:closeEvent`, `config_dialogs.py:__init__`, `config_dialogs.py:done`, `window_state.py:WindowState`, `window_state.py:__init__`, `window_state.py:save_geometry`, `window_state.py:restore_geometry` |
| FR-005 | The application shall remember the filesystem path of the most recently loaded (FR-010) or saved (FR-013) configuration file and, on the next startup, automatically reload and apply that file (subject to FR-003). The remembered path is persisted via `QSettings` alongside the window geometry (FR-004). | Mandatory | T | impl. `app.py:load_config`, `menu_save` |
| FR-006 | The application shall remember the folder of the most recently loaded (FR-010) or saved (FR-013) configuration file and shall default the File > Load and File > Save dialogs to that folder. This remembered config folder is persisted via `QSettings` alongside the window geometry (FR-004) and is maintained separately from the Host Files directory (FR-060). When no config folder is remembered, the dialogs default to the host system's standard behaviour (current working directory). | Mandatory | T | impl. `app.py:menu_load`, `app.py:menu_save`, `window_state.py:last_config_dir` |

### 3.2 File menu

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| FR-010 | The File > Load menu item shall present a file-select dialog defaulting to the JSON file type for selecting a configuration file to load. The dialog shall open in the last-used config folder (FR-006). | Mandatory | D | App_Requirements §Load; impl. `app.py:menu_load` |
| FR-011 | On loading a configuration file, the application shall replace its entire internal settings store with the contents of the file (a full replace, not a per-key merge). | Mandatory | T | impl. `app.py:load_config` |
| FR-012 | Settings keys present in a loaded file that are not consumed by the application shall be retained verbatim in the settings store but shall not alter application behaviour; the application shall not reject a file on account of unrecognised keys. | Mandatory | T | impl. `app.py:load_config` |
| FR-013 | The File > Save menu item shall present a file-select dialog defaulting to the JSON file type for selecting a configuration file to save to. The dialog shall open in the last-used config folder (FR-006). | Mandatory | D | App_Requirements §Save; impl. `app.py:menu_save` |
| FR-014 | On saving, the application shall write the internal serial configuration and general configuration settings to the selected file in JSON format. | Mandatory | T | App_Requirements §Save; impl. `app.py:menu_save`, `config_handler.py:save_json` |
| FR-015 | The File > Exit menu item shall close any open COM ports. | Mandatory | D | App_Requirements §Exit; impl. `app.py:closeEvent`, `serial_manager.py:close_ports` |
| FR-016 | The File > Exit menu item shall close all open dialogs and windows. | Mandatory | D | App_Requirements §Exit; impl. `app.py:closeEvent` |
| FR-017 | On loading a configuration file, the application shall clear the Remote Files list. The previously displayed remote listing was captured under the prior configuration (potentially a different port, drive, or system) and is no longer valid (consistent with the empty-at-startup state, FR-070). | Mandatory | T | impl. `app.py:load_config` |

### 3.3 Config menu

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| FR-020 | When the Config > Serial menu option is selected, the application shall present the Serial Configuration Dialog to allow the user to modify the serial settings. | Mandatory | D | App_Requirements §Serial; impl. `app.py:menu_serial_config`, `config_dialogs.py:save` |
| FR-021 | When the Config > General menu option is selected, the application shall present the General Configuration Dialog to allow the user to modify the general settings. | Mandatory | D | App_Requirements §General; impl. `app.py:menu_general_config`, `config_dialogs.py:save` |

### 3.4 Connecting to the remote system

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| FR-030 | When the Connect button is pressed, the application shall open the Terminal Port serial port if it is not already open. | Mandatory | T | App_Requirements §Connecting; impl. `app.py:do_connect`, `serial_manager.py:open_port` |
| FR-031 | If the Terminal Port cannot be opened, the application shall display an error dialog containing the text "Terminal port is unable to be opened" and cancel the current workflow. | Mandatory | T | App_Requirements §Connecting; impl. `app.py:do_connect` |
| FR-032 | If the Terminal Port is successfully opened, the application shall set the Terminal status flag to true. | Mandatory | T | App_Design §Connecting; impl. `app.py:do_connect`, `serial_manager.py:open_port` |
| FR-033 | If the Terminal Port cannot be opened, the application shall set the Terminal status flag to false. | Mandatory | T | App_Design §Connecting |
| FR-034 | When the Terminal Port is opened, the application shall display the text "Terminal port open" in the status bar. | Mandatory | D | App_Requirements §Connecting; impl. `app.py:do_connect` |
| FR-035 | *Removed in v1.2.* (Was: "When the Connect button is pressed, the application shall open the Terminal Window.") The Terminal Window is opened exclusively via the Terminal button (FR-097); the Connect action does not open it. See §10 OI-10. | — | — | superseded by FR-097 |
| FR-036 | The application shall display data received from the Terminal Port in the receive text area of the Terminal Window. | Mandatory | T | App_Requirements §Connecting; impl. `serial_manager.py:_read_loop` |
| FR-037 | On connect, if the Transport Port is the same as the Terminal Port, the application shall set the Transport status flag to connected. | Mandatory | T | App_Design §Connecting; impl. `app.py:do_connect` |
| FR-038 | On connect, if the Transport Port is different from the Terminal Port and is not currently open, the application shall attempt to open the Transport Port. | Mandatory | T | App_Design §Connecting; impl. `app.py:do_connect`, `serial_manager.py:open_port` |
| FR-039 | If the Transport Port cannot be opened, the application shall display an error dialog containing the text "Transport port is unable to be opened". | Mandatory | T | App_Design §Connecting; impl. `app.py:do_connect` |
| FR-040 | If the Transport Port is successfully opened, the application shall set the Transport status flag to connected. | Mandatory | T | App_Design §Connecting; impl. `app.py:do_connect`, `serial_manager.py:open_port` |

### 3.5 Disconnecting from the remote system

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| FR-050 | When the Disconnect button is pressed, if the Terminal Port is currently open, the application shall attempt to close the Terminal Port serial port. | Mandatory | T | App_Requirements §Disconnecting; impl. `app.py:do_disconnect`, `serial_manager.py:close_terminal_port` |
| FR-051 | If the Terminal Port cannot be closed, the application shall display an error dialog containing the text "Terminal port is unable to be closed" and cancel the current workflow. | Mandatory | T | App_Requirements §Disconnecting; impl. `app.py:do_disconnect` |
| FR-052 | When the Terminal Port is closed, the application shall set the Terminal status flag to false. | Mandatory | T | App_Design §Disconnecting; impl. `app.py:do_disconnect`, `serial_manager.py:close_terminal_port` |
| FR-053 | When the Terminal Port is closed, the application shall display the text "Terminal port closed" in the status bar. | Mandatory | D | App_Requirements §Disconnecting; impl. `app.py:do_disconnect` |
| FR-054 | On disconnect, if the Transport Port is the same as the Terminal Port, the application shall set the Transport status flag to false. | Mandatory | T | App_Design §Disconnecting; impl. `app.py:do_disconnect` |
| FR-055 | On disconnect, if the Transport Port is different from the Terminal Port and is currently open, the application shall attempt to close the Transport Port. | Mandatory | T | App_Design §Disconnecting; impl. `app.py:do_disconnect`, `serial_manager.py:close_transport_port` |
| FR-056 | If the Transport Port cannot be closed, the application shall display an error dialog containing the text "Transport port is unable to be closed". | Mandatory | T | App_Design §Disconnecting; impl. `app.py:do_disconnect` |
| FR-057 | If the Transport Port is successfully closed, the application shall set the Transport status flag to false. | Mandatory | T | App_Design §Disconnecting; impl. `app.py:do_disconnect`, `serial_manager.py:close_transport_port` |
| FR-058 | On disconnect, once the Terminal Port has been successfully closed, the application shall clear the Remote Files list. The listing was read over the now-closed Terminal Port and reflects the disconnected system, so it is no longer valid (consistent with the empty-at-startup state, FR-070). The list shall not be cleared if the Terminal Port could not be closed and the disconnect was cancelled (FR-051). | Mandatory | T | impl. `app.py:do_disconnect` |

### 3.6 Host file management

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| FR-060 | On startup, the application shall populate the Host Files list with the files in the host directory specified in the loaded configuration file; if no configuration is loaded or no path is specified, it shall default to the current working directory of the host system. | Mandatory | T | App_Requirements §Host Files; impl. `app.py:refresh_host_files`, `app.py:load_config` |
| FR-061 | The Change Directory button shall be enabled at startup. | Mandatory | I | App_Requirements §Change Directory |
| FR-062 | When the Change Directory button is pressed, the application shall present a folder-select dialog for the user to choose the folder whose contents are loaded into the Host Files list. This action updates the active session directory but does not persist the change to the configuration file until File > Save is invoked. | Mandatory | D | App_Requirements §Change Directory; impl. `app.py:change_host_dir` |
| FR-063 | When the Refresh Host button (underneath the Host Files list) is pressed, the application shall refresh the Host Files list from the current host directory and then populate the Remote Files list following the "Populating remote file list" process (FR-074–FR-079). The Refresh Host button thus acts on both lists, whereas the Update button (FR-073) acts on the Remote Files list only. | Mandatory | T | impl. `app.py:refresh_all` |

### 3.7 Remote file listing

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| FR-070 | The Remote Files list shall be empty (unpopulated) at startup. | Mandatory | T | App_Requirements §Remote Files |
| FR-071 | The Update button shall be enabled at startup. | Mandatory | I | App_Requirements §Update |
| FR-072 | The Refresh Host button shall be enabled at startup. | Mandatory | I | App_Requirements §Refresh |
| FR-073 | When the Update button (in the Remote Files group) is pressed, the application shall populate the Remote Files list following the "Populating remote file list" process (FR-074–FR-079). It shall not affect the Host Files list. | Mandatory | T | App_Requirements §Update; impl. `app.py:refresh_remote_files` |
| FR-074 | If the Terminal Port is not open when populating the remote file list, the application shall set the status bar text to "Terminal port not open - cannot read file list" and clear the Remote Files list. | Mandatory | T | App_Requirements §Populating remote file list; impl. `app.py:refresh_remote_files` |
| FR-075 | If the Terminal status flag is true, the application shall send the configured List Files command followed by the configured EOL character(s) to the Terminal Port. The command is reflected in the receive text area by the remote's echo of the command over the serial link (or, if enabled, by local echo — FR-093); the application does not write the command to the receive area itself. *(v1.7.1: reworded to the as-built echo behaviour — see §10 OI-21.)* | Mandatory | T | App_Design §Populating remote file list; impl. `app.py:_capture_terminal_response` |
| FR-076 | After sending the List Files command, the application shall wait at least one second for output to begin accumulating, then continue waiting until the remote capture buffer has received no new data within an idle window of 0.5 s (the buffer "times out"), bounded by a maximum total wait of 10 s, before processing the received text. | Mandatory | T | App_Design §Populating remote file list; impl. `app.py:_capture_terminal_response` |
| FR-077 | The application shall process the captured remote output into a dictionary of filenames using the CP/M 4-column DIR parsing algorithm (see §6). | Mandatory | T | App_Design §Populating remote file list; impl. `app.py:_do_refresh_remote_logic`, `cpm_parser.py:parse_dir_output` |
| FR-078 | The application shall populate the Remote Files list with the entries produced by the parsing algorithm, displaying the dictionary keys (filenames) sorted in ascending alphabetical order. | Mandatory | T | App_Design §Populating remote file list; impl. `app.py:_update_remote_list_ui` |
| FR-079 | On successful population of the remote file list, the application shall update the status bar with the text "Remote file list updated". | Mandatory | D | App_Requirements §Populating remote file list; impl. `app.py:_do_refresh_remote_logic`, `app.py:_update_remote_list_ui` |

### 3.7.1 Remote drive selection

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| FR-100 | When a drive letter is selected from the drive-selection drop-down (UIR-017), the application shall send that drive letter followed by `:` and the configured EOL character(s) to the Terminal Port. As with FR-075, the command is reflected in the receive text area by the remote's echo (or local echo, FR-093); the application does not write the command to the receive area itself. *(v1.7.1: reworded to the as-built echo behaviour — see §10 OI-21.)* | Mandatory | T | impl. `app.py:change_drive`, `_do_change_drive_logic`, `_capture_terminal_response` |
| FR-101 | After sending the drive-change command, the application shall capture the Terminal Port response using the same wait mechanism as FR-076, ignoring any blank lines returned by the terminal. | Mandatory | T | impl. `app.py:_capture_terminal_response`; `cpm_parser.py:has_drive_prompt` |
| FR-102 | If a drive prompt of the form `<letter>>` (the selected drive letter followed by `>`) appears in the captured response, the application shall populate the Remote Files list following the "Populating remote file list" process (FR-074–FR-079), as if the Update button had been pressed. | Mandatory | T | impl. `app.py:_do_change_drive_logic`, `_do_refresh_remote_logic` |
| FR-103 | If the `<letter>>` drive prompt does not appear in the captured response, the application shall clear the Remote Files list and display a modal dialog with an OK button whose message names the selected drive, of the form "Drive `<letter>`: not found" (e.g. "Drive B: not found"). | Mandatory | T | impl. `app.py:_do_change_drive_logic`, `_on_drive_not_found`, `drive_not_found` signal |
| FR-104 | If the Terminal Port is not open when a drive is selected, the application shall set the status bar text to "Terminal port not open - cannot read file list" and clear the Remote Files list (consistent with FR-074). | Mandatory | T | impl. `app.py:change_drive` |

### 3.8 File transfers

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| FR-080 | A file transfer shall be permitted only when both the Terminal status flag and the Transport status flag are set to connected. | Mandatory | T | App_Requirements §File Transfers; App_Design §File Transfers; impl. `app.py:do_copy_to_remote`, `app.py:do_copy_to_host` |
| FR-081 | The application shall support file transfers in both directions: host-to-remote and remote-to-host. | Mandatory | T | App_Requirements §File Transfers; impl. `app.py:_send_one_to_remote`, `app.py:_recv_one_to_host`, `xmodem.py:send_file`, `xmodem.py:receive_file` |
| FR-082 | The application shall use the X-Modem protocol for all file transfers. | Mandatory | T | App_Requirements §File Transfers; impl. `app.py:_send_one_to_remote`, `app.py:_recv_one_to_host`, `xmodem.py:XModem`, `xmodem.py:send_file`, `xmodem.py:receive_file` |
| FR-083 | The application shall use the Transport (Transfer) Port for all file transfers. | Mandatory | T | App_Requirements §File Transfers; impl. `app.py:_send_one_to_remote`, `app.py:_recv_one_to_host`, `xmodem.py:send_file`, `xmodem.py:receive_file` |
| FR-084 | The Copy to Remote button shall be enabled at startup. | Mandatory | I | App_Requirements §Copy to Remote; impl. `app.py:do_copy_to_remote` |
| FR-085 | The Copy to Host button shall be enabled at startup. | Mandatory | I | App_Requirements §Copy to Host; impl. `app.py:do_copy_to_host` |
| FR-086 | During an X-Modem file transfer (either direction), the application shall echo every byte sent to or received from the Transport Port to the Terminal Window Receive area, formatted as a hexadecimal byte token of the form `<HH>`, where `HH` is the byte value as two uppercase hexadecimal digits (e.g. byte 0xB5 is displayed as `<B5>`). This echo shall occur only while the Terminal Window exists. | Mandatory | D | impl. `app.py:_on_transfer_bytes`, `xmodem.py` monitor hook |
| FR-087 | Before starting the X-Modem transfer, the application shall launch the CP/M side of the transfer by sending a command on the Terminal Port: `send_remote_cmd` (default `PCGET $1`) for Copy to Remote, and `recv_remote_cmd` (default `PCPUT $1`) for Copy to Host, with the token `$1` replaced by the transferred file's name as shown in the file list. After sending the command the application shall wait the configured launch delay (FR-089) before beginning the X-Modem handshake. The transfer shall then proceed on the Transport Port (FR-083). If the configured command is empty, no command is sent. *(v1.3.1: supersedes the CR-011 deferral of these two settings.)* | Mandatory | T | impl. `app.py:_issue_remote_cmd`, `_transfer_to_remote`, `_transfer_to_host`; UIR-045/UIR-046 |
| FR-088 | The application shall emit verbose transfer debug output (per-byte X-Modem trace and transfer flow messages) to standard output only when the `debug_logging` setting holds an affirmative value (`ON`/`TRUE`/`1`/`YES`, case-insensitive); the default is off. | Mandatory | T | impl. `app.py:_debug`, `_debug_enabled`, `_on_transfer_bytes`; UIR-050 |
| FR-089 | After launching the CP/M side of a transfer (FR-087), the application shall wait `xfer_launch_delay` seconds (default 3) before sending the first X-Modem start character, so that start-character prompts do not arrive while the remote program is still starting up and not yet servicing its UART. | Mandatory | T | impl. `app.py:_launch_delay`; UIR-049 |
| FR-099 | On a **successful** file transfer the application shall automatically refresh the destination file list so the transferred file appears without manual intervention: after a successful Copy to Host it shall refresh the Host Files list (per FR-060), and after a successful Copy to Remote it shall refresh the Remote Files list (per the FR-074–FR-079 process). A failed transfer shall not trigger a refresh. *(v1.3.2: fixes the defect where a transferred file did not appear in the destination list until manually refreshed.)* | Mandatory | T | impl. `app.py:_on_transfer_completed`, `transfer_completed` signal, `_transfer_to_remote`, `_transfer_to_host` |
| FR-105 | While an X-Modem file transfer (either direction) is in progress, the application shall display a modal progress dialog (UIR-051) showing the name of the file being transferred and the cumulative number of blocks and bytes transferred. The blocks/bytes count shall be updated after each block is transferred (each acknowledged 128-byte packet on send; each accepted packet on receive). When a batch of multiple files is transferred (FR-106), a single dialog shall serve the whole batch: it shall additionally show the batch position ("File `i` of `N`"), be created when the batch begins, switch to each successive file, and be closed once when the batch ends (success or failure). The application shall close the dialog automatically when the transfer completes, on both success and failure. Progress updates originate on the transfer worker thread and shall be delivered to the GUI thread via Qt signals (NFR-004). *(v1.5; batch support v1.6.)* | Mandatory | T | impl. `xmodem.py` progress hook; `gui/transfer_dialog.py`; `app.py:_on_batch_started`, `_on_transfer_file_started`, `_on_transfer_progress`, `_close_transfer_dialog`, `_on_transfer_progress_cb`, `batch_started`/`transfer_file_started`/`transfer_progress` signals |
| FR-106 | The Copy to Remote and Copy to Host actions shall transfer **all** files currently selected in the respective file list (the lists are multi-select widgets — UIR-011, UIR-012). If no file is selected when the action is invoked, the application shall display a warning dialog with the body text "Please select one or more files to upload" (Copy to Remote) or "Please select one or more files to download" (Copy to Host) and shall not start a transfer. *(v1.6.)* | Mandatory | T | impl. `app.py:do_copy_to_remote`, `do_copy_to_host`, `_selected_filenames` |
| FR-107 | When more than one file is selected, the files shall be transferred **sequentially** over the single Transport Port (FR-083), in the order they appear in the list (top to bottom). Each file shall be launched with its own CP/M-side command (FR-087) and transferred in a separate X-Modem session. *(v1.6.)* | Mandatory | T | impl. `app.py:_transfer_to_remote_batch`, `_transfer_to_host_batch`, `_selected_filenames` |
| FR-108 | If any file in a multi-file batch fails to transfer, the application shall abort the batch — it shall not attempt the remaining files — and shall display an error dialog naming the failed file. If at least one file in the batch transferred successfully before the failure, the destination file list shall be refreshed once (per FR-099). *(v1.6.)* | Mandatory | T | impl. `app.py:_transfer_to_remote_batch`, `_transfer_to_host_batch` |
| FR-109 | In a multi-file batch, before issuing the FR-087 launch command for each file **after the first**, the application shall wait for the Terminal Port output to go idle (the previous CP/M transfer program having finished and the CCP command prompt having returned) and then wait an additional `xfer_interfile_delay` settle period (UIR-052, default 2 s). This prevents the leading characters of the next command from being lost while CP/M is still returning to the prompt and not yet servicing its UART (the multi-file analogue of FR-089). *(v1.6.1.)* | Mandatory | T | impl. `app.py:_wait_for_terminal_idle`, `_interfile_delay`, `_transfer_to_remote_batch`, `_transfer_to_host_batch` |

### 3.9 Terminal window — receive and transmit

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| FR-090 | All data received from the Terminal Port shall be accumulated in a receive data buffer that is retained until explicitly cleared by the Terminal Window Clear button (FR-095). Local-echo text (FR-093) is not received data and shall not enter this buffer. | Mandatory | T | App_Design §Receiving data; impl. `app.py:handle_terminal_recv`, `_rx_buffer` |
| FR-091 | All data received from the Terminal Port shall be displayed in the receive text area of the Terminal Window. | Mandatory | T | App_Design §Receiving data; impl. `app.py:_on_term_write`, `app.py:handle_terminal_recv`, `terminal_window.py:write_text`, `serial_manager.py:_read_loop` |
| FR-092 | All data transmitted to the Terminal Port (including the appended EOL, FR-094) shall be accumulated in a transmit data buffer that is retained until explicitly cleared by the Terminal Window Clear button (FR-095). | Mandatory | T | App_Design §Sending data; impl. `app.py:handle_terminal_send`, `_tx_buffer` |
| FR-093 | When the Local Echo checkbox is enabled, transmitted data shall be copied to the receive text area of the Terminal Window. | Mandatory | T | App_Design §Sending data; impl. `app.py:_on_term_write`, `app.py:_set_local_echo`, `app.py:handle_terminal_send` |
| FR-094 | Transmitted data shall have the configured EOL character(s) appended before being sent. | Mandatory | T | App_Design §Sending data; impl. `app.py:handle_terminal_send` |
| FR-095 | When the Clear button in the Terminal Window is pressed, the receive text area shall be cleared, and the receive and transmit data buffers (FR-090, FR-092) shall be cleared. | Mandatory | T | App_Requirements §Terminal Window; impl. `terminal_window.py:clear_text`, `app.py:clear_terminal_buffers` |
| FR-096 | When the Send button in the Terminal Window is pressed, the contents of the transmit text field shall be sent to the Terminal Port. | Mandatory | T | App_Requirements §Terminal Window; impl. `terminal_window.py:send_text`, `serial_manager.py:send_data` |
| FR-097 | When the Terminal button in the main window is pressed, the application shall open the Terminal Window if it is not already open, or restore (de-iconify) it if it is hidden. This action shall be independent of the Connect action and shall not require an open Terminal Port. | Mandatory | D | App_Requirements §Main Program GUI; impl. `app.py:show_terminal` |
| FR-098 | If the Terminal Port is not open when the user attempts to send data from the Terminal Window, the application shall set the status bar text to "Terminal port not open - cannot send" and not transmit. | Mandatory | T | impl. `app.py:handle_terminal_send` |

---

## 4. User Interface Requirements

### 4.1 Menu bar

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| UIR-001 | The GUI shall present a menu bar at the top of the main window. | Mandatory | I | App_Requirements §Look and Feel, §Main Program GUI; impl. `app.py:setup_menu` |
| UIR-002 | The menu bar shall contain a File menu with the items Load, Save, and Exit. | Mandatory | I | App_Requirements §Look and Feel; impl. `app.py:setup_menu` |
| UIR-003 | The menu bar shall contain a Config menu with the items Serial and General. | Mandatory | I | App_Requirements §Look and Feel; impl. `app.py:setup_menu` |

### 4.2 Main window layout

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| UIR-010 | The main window shall contain a status bar at the bottom. | Mandatory | I | App_Requirements §Main Program GUI; impl. `app.py:setup_status_bar`, `app.py:_on_status_changed` |
| UIR-011 | The main window shall contain a "Host Files" group containing a "Change Directory" button, a multi-select widget, and a row underneath the widget containing "Refresh Host" and "Copy to Remote" buttons. | Mandatory | I | App_Requirements §Main Program GUI; impl. `app.py:setup_layout` |
| UIR-012 | The main window shall contain a "Remote Files" group containing a drive-selection drop-down (UIR-017) followed by an "Update" button, a multi-select widget, and a row underneath the widget containing the "Copy to Host" button. | Mandatory | I | App_Requirements §Main Program GUI; impl. `app.py:setup_layout` |
| UIR-013 | The main window shall provide the actions Connect, Disconnect, Copy to Remote, Copy to Host, Refresh Host, and Terminal. From v1.3 these are presented as a top toolbar (see UIR-071) or within the file panes rather than a central button column. | Mandatory | I | App_Requirements §Main Program GUI; impl. `app.py:setup_toolbar` |
| UIR-014 | The status bar shall be a single-line text label. When a status message exceeds 127 characters, the application shall truncate it to the first 127 characters before display. | Mandatory | T | App_Requirements §Status Bar; impl. `app.py:set_status` |
| UIR-015 | The Connect button shall be enabled at startup. | Mandatory | I | App_Requirements §Connect |
| UIR-016 | The main window shall provide a separate Disconnect button, enabled at startup, that invokes the disconnect behaviour (FR-050–FR-057). | Mandatory | I | App_Requirements §Disconnect; impl. `app.py` |
| UIR-017 | The Remote Files group shall contain a drive-selection drop-down, positioned immediately before the Update button, listing the drive letters `A:` through `P:`. The drop-down shall be wide enough to display the selected drive without clipping. Selecting an item triggers the remote drive-change behaviour (FR-100–FR-104). | Mandatory | I | impl. `app.py:setup_layout`, `change_drive` |

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
| UIR-028 | The dialog shall provide a Flow Control drop-down list with the values NONE, XON/XOFF, RTS/CTS, and DSR/DTR; the default shall be NONE. The selected value shall be applied to the serial port when it is opened, mapping XON/XOFF, RTS/CTS, and DSR/DTR onto the corresponding software/hardware handshake (NONE disables all). *(v1.7.1: flow control is now applied at port open — see §10 OI-20.)* | Mandatory | T | App_Requirements §Serial Configuration Dialog; impl. `serial_manager.py:open_port` |
| UIR-029 | The dialog shall present a "Transmit Delay" group laid out in two columns, formatted as in UIR-021. | Mandatory | I | App_Requirements §Serial Configuration Dialog; impl. `config_dialogs.py:SerialConfigDialog`, `config_dialogs.py:__init__` |
| UIR-030 | The dialog shall provide an "msec/char" text field that defaults to 0 and is limited to integer values between 0 and 255 inclusive. The value shall be persisted as the `msec_char` setting. *(Inter-character transmission delay is a stored setting only; it is not yet applied during transmission — see CR-011.)* | Mandatory | T | App_Requirements §Serial Configuration Dialog; impl. `config_dialogs.py:SerialConfigDialog`, `config_dialogs.py:__init__` |
| UIR-031 | The dialog shall provide an "msec/line" text field that defaults to 0 and is limited to integer values between 0 and 255 inclusive. The value shall be persisted as the `msec_line` setting. *(Inter-line transmission delay is a stored setting only; it is not yet applied during transmission — see CR-011.)* | Mandatory | T | App_Requirements §Serial Configuration Dialog; impl. `config_dialogs.py:SerialConfigDialog`, `config_dialogs.py:__init__` |

### 4.4 General Configuration Dialog

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| UIR-040 | The General Configuration Dialog shall be a modal dialog titled "General Config". | Mandatory | I | App_Requirements §General Configuration Dialog; impl. `config_dialogs.py:__init__`, `config_dialogs.py:GeneralConfigDialog` |
| UIR-041 | The dialog shall present a "Terminal Commands" group laid out in two columns as in UIR-021. | Mandatory | I | App_Requirements §General Configuration Dialog; impl. `config_dialogs.py:GeneralConfigDialog` |
| UIR-042 | The dialog shall provide a "List Files" text field limited to 79 characters with a default value of "DIR". | Mandatory | T | App_Requirements §General Configuration Dialog; impl. `config_dialogs.py:GeneralConfigDialog`, `config_dialogs.py:__init__` |
| UIR-043 | *Withdrawn.* Formerly a "Change Disk" text field persisted as `change_disk_cmd`. Removed because the command was never sent to the remote and the drive-change behaviour is now provided by the Remote Files drive drop-down (FR-100–FR-104, UIR-017). The field and setting are no longer present in the dialog or config files. | — | — | impl. `config_dialogs.py:GeneralConfigDialog` |
| UIR-044 | The dialog shall present an "Xmodem Commands" group laid out in two columns as in UIR-021. | Mandatory | I | App_Requirements §General Configuration Dialog; impl. `config_dialogs.py:GeneralConfigDialog` |
| UIR-045 | The dialog shall provide a "Receive from Remote" text field limited to 79 characters with a default value of "PCPUT $1". | Mandatory | T | App_Requirements §General Configuration Dialog; impl. `config_dialogs.py:GeneralConfigDialog`, `config_dialogs.py:__init__` |
| UIR-046 | The dialog shall provide a "Send to Remote" text field limited to 79 characters with a default value of "PCGET $1". | Mandatory | T | App_Requirements §General Configuration Dialog; impl. `config_dialogs.py:GeneralConfigDialog`, `config_dialogs.py:__init__` |
| UIR-047 | The dialog shall present an "End of Line" group of mutually exclusive radio buttons: Carriage Return (CR), Line Feed (LF), and Carriage Return/Line Feed (CR/LF). | Mandatory | I | App_Requirements §General Configuration Dialog; impl. `config_dialogs.py:GeneralConfigDialog`, `config_dialogs.py:__init__` |
| UIR-048 | The Carriage Return (CR) radio button shall be the default selection. | Mandatory | T | App_Requirements §General Configuration Dialog; impl. `config_dialogs.py:GeneralConfigDialog`, `config_dialogs.py:__init__` |
| UIR-049 | The dialog shall provide an "Xfer Launch Delay (s)" integer field (0..60 inclusive) with a default value of 3, setting the seconds to wait after launching the remote transfer program (FR-087) before the X-Modem handshake begins. *(v1.3.1.)* | Mandatory | T | impl. `config_dialogs.py:GeneralConfigDialog`, `config_dialogs.py:__init__` |
| UIR-050 | The dialog shall provide a "Debug Logging" dropdown (`OFF`/`ON`, default `OFF`) controlling the verbose transfer debug output of FR-088. *(v1.3.1.)* | Mandatory | T | impl. `config_dialogs.py:GeneralConfigDialog` |
| UIR-052 | The dialog shall provide an "Xfer Inter-file Delay (s)" integer field (0..60 inclusive) with a default value of 2, setting the additional settle time waited between files in a multi-file batch after the terminal output goes idle and before the next launch command is sent (FR-109). *(v1.6.1.)* | Mandatory | T | impl. `config_dialogs.py:GeneralConfigDialog` |
| UIR-053 | The dialog shall provide a "Default Host Directory" text field and an associated browse button to specify the host directory used at startup (FR-060). This value is persisted in the configuration JSON file. | Mandatory | T | App_Requirements §General Configuration Dialog; impl. `config_dialogs.py:create_widgets`, `config_dialogs.py:on_browse`, `config_dialogs.py:GeneralConfigDialog` |

### 4.5 Terminal Window

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| UIR-060 | The Terminal Window shall be a non-modal window titled "Terminal". | Mandatory | I | App_Requirements §Terminal Window; impl. `terminal_window.py:TerminalWindow`, `terminal_window.py:__init__` |
| UIR-061 | The Terminal Window shall contain a large multi-line text area named "Receive" for displaying incoming data. | Mandatory | I | App_Requirements §Terminal Window; impl. `terminal_window.py:TerminalWindow`, `terminal_window.py:create_widgets` |
| UIR-062 | The Receive text area shall auto-scroll incoming text (subject to the Autoscroll control). | Mandatory | D | App_Requirements §Terminal Window; impl. `terminal_window.py:TerminalWindow`, `terminal_window.py:create_widgets`, `terminal_window.py:write_text` |
| UIR-063 | The Receive text area shall be read-only. | Mandatory | T | App_Requirements §Terminal Window; impl. `terminal_window.py:TerminalWindow`, `terminal_window.py:create_widgets` |
| UIR-064 | The Terminal Window shall provide a "Clear" button, left-aligned, below the Receive text area. | Mandatory | I | App_Requirements §Terminal Window; impl. `terminal_window.py:TerminalWindow`, `terminal_window.py:create_widgets`, `terminal_window.py:clear_text` |
| UIR-065 | The Terminal Window shall provide a "Local Echo" checkbox, centred, that is disabled by default. | Mandatory | T | App_Requirements §Terminal Window; impl. `terminal_window.py:TerminalWindow`, `terminal_window.py:create_widgets` |
| UIR-066 | The Terminal Window shall provide an "Autoscroll" checkbox, right-aligned, that is enabled by default. | Mandatory | T | App_Requirements §Terminal Window; impl. `terminal_window.py:TerminalWindow`, `terminal_window.py:create_widgets` |
| UIR-067 | The Terminal Window shall provide a "Transmit" group containing a single-line text field aligned left and a "Send" button aligned right in the same row. | Mandatory | I | App_Requirements §Terminal Window; impl. `terminal_window.py:TerminalWindow`, `terminal_window.py:create_widgets` |

### 4.6 Visual theme and modern layout (v1.3)

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| UIR-070 | The GUI shall apply a modern Material Design visual theme to all windows, dialogs, and widgets (via the `qt-material` stylesheet over PySide6 widgets), in place of the platform-default Tk appearance. | Mandatory | D | v1.3 UI migration; impl. `theme.py:apply_theme` |
| UIR-071 | The main window shall present the Connect, Disconnect, and Terminal actions of UIR-013 as a toolbar at the top of the window (above the file panes), with each action shown as a labelled, icon-bearing button. | Mandatory | I | v1.3 UI migration; impl. `app.py:setup_toolbar` |
| UIR-072 | The Host Files and Remote Files panes shall be separated by a user-draggable splitter that lets the user re-apportion horizontal space between the two panes; the split position is not required to persist between sessions. | Mandatory | D | v1.3 UI migration; impl. `app.py:setup_layout` |
| UIR-073 | The application shall, at startup, detect the host operating system's light/dark colour-scheme preference and apply the corresponding (light or dark) variant of the Material theme. If the preference cannot be determined, the application shall default to the dark variant. | Mandatory | T | v1.3 UI migration; impl. `theme.py:prefers_dark`, `theme.py:apply_theme` |
| UIR-074 | The status bar (UIR-010) shall display two connection indicators — one for the Terminal status flag (FR-001) and one for the Transport status flag (FR-002) — each rendering a distinct visual state for connected versus not-connected. | Desirable | D | v1.3 UI migration; impl. `app.py:setup_status_bar`, `app.py:_make_indicator`, `app.py:_update_indicators` |

### 4.7 Transfer Progress Dialog

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| UIR-051 | The Transfer Progress Dialog (FR-105) shall be a modal dialog titled "Sending File" (Copy to Remote) or "Receiving File" (Copy to Host). It shall display a label naming the file being transferred, a label showing the running "Blocks" and "Bytes" counts, and a progress bar. When more than one file is being transferred (FR-106), it shall also display a "File `i` of `N`" batch-position label. When the total size is known (sends) the progress bar shall track bytes transferred against the file size; when the total is unknown (receives) the progress bar shall be indeterminate. The dialog shall not present a manual close control — its lifetime is owned by the transfer (FR-105). *(v1.5; batch label v1.6.)* | Mandatory | T | impl. `gui/transfer_dialog.py:TransferProgressDialog`; FR-105 |

---

## 5. External Interface Requirements

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| IFR-001 | The application shall communicate with the remote CP/M system over a serial (RS-232 style) communications link. | Mandatory | T | App_Design §Purpose; impl. `serial_manager.py:SerialManager` |
| IFR-002 | The application shall support configuring two logical serial ports — a Terminal Port and a Transport Port — which may map to the same physical port. | Mandatory | T | App_Requirements §Serial Configuration Dialog; CLAUDE.md; impl. `config_dialogs.py:SerialConfigDialog`, `serial_manager.py:SerialManager` |
| IFR-003 | The application shall enumerate the serial ports installed on the host and present them for selection. | Mandatory | T | App_Requirements §Serial Configuration Dialog; impl. `app.py:menu_serial_config` |
| IFR-004 | Configuration data shall be exchanged with the file system as JSON files. | Mandatory | T | App_Requirements §Load, §Save; impl. `config_handler.py:ConfigHandler`, `config_handler.py:load_json`, `config_handler.py:save_json` |

---

## 6. Data Requirements — CP/M 4-Column DIR Parsing Algorithm

The following requirements define the algorithm for extracting remote file names from standard CP/M
2.2 four-column `DIR` output.

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
| DR-033 | The drive-prompt detection routine shall report a drive prompt for drive `X` as present when any non-blank line of the captured terminal text, after stripping surrounding whitespace and comparing case-insensitively, starts with `X>`. Blank lines shall be ignored. | Mandatory | T | impl. `cpm_parser.py:has_drive_prompt`; FR-101, FR-102 |

### 6.4 Parser constraints

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| DR-030 | The parser assumes input conforming to standard CP/M 2.2 `DIR` output format (8.3 filenames, space-padded). | Mandatory | A | App_Design §Constraints; impl. `cpm_parser.py:CPMParser` |
| DR-031 | The parser is not required to support long filenames or non-ASCII characters. | Optional | A | App_Design §Constraints; impl. `cpm_parser.py:CPMParser` |
| DR-032 | The parser is not required to parse file sizes, dates, or attributes — only names and extensions. | Mandatory | A | App_Design §Constraints; impl. `cpm_parser.py:CPMParser` |

---

## 7. Design Constraints

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| CR-001 | All source files shall reside under a `src` folder at the project root. | Mandatory | I | App_Design §Project Structure |
| CR-002 | The package shall provide a runnable module entry point at `src/cpm_fm/__main__.py` that invokes `cpm_fm.app:main()`, enabling `python -m cpm_fm`. | Mandatory | I | App_Design §Project Structure; impl. `app.py:main` |
| CR-003 | All GUI-related source files shall reside in a `gui` folder within the source tree. | Mandatory | I | App_Design §Project Structure |
| CR-004 | All serial and terminal related source files shall reside in a `terminal` folder within the source tree. | Mandatory | I | App_Design §Project Structure |
| CR-005 | All other source files shall reside in a `utils` folder within the source tree. | Mandatory | I | App_Design §Project Structure |
| CR-006 | A `resources` folder shall be provided at the project root for icons, images, and other non-Python files **if and when** such assets are introduced. *(Deferred: no non-Python assets exist in the current baseline, so the folder is not present.)* | Desirable | I | App_Design §Project Structure |
| CR-007 | Source files shall be organised as cohesive modules, one module per logical component (serial management, X-Modem, parser, configuration, each GUI window/dialog family). A module may contain more than one closely related class (e.g. `gui/config_dialogs.py` holds `ConfigDialog` and its subclasses). | Mandatory | I | App_Design §Class Files (relaxed in v1.2 to as-built) |
| CR-008 | Source files shall be named in `snake_case` after the component they implement (e.g. `serial_manager.py`, `cpm_parser.py`), not necessarily identically to a contained class name. | Mandatory | I | App_Design §Class Files (relaxed in v1.2 to as-built) |
| CR-009 | All Python source files shall adhere to the PEP 8 standard. | Mandatory | T | App_Design §Code Quality |
| CR-010 | The Copy to Remote and Copy to Host actions shall be guarded so that a transfer is only attempted when **both** the Terminal status flag and the Transport status flag are true (consistent with FR-080); otherwise an error dialog with the body text "Transport port not connected" shall be shown and the transfer shall not proceed. | Mandatory | T | App_Requirements §Copy to Remote, §Copy to Host; impl. `app.py:do_copy_to_remote`, `do_copy_to_host` |
| CR-011 | The following settings are persisted but their behaviour is deferred to a future release and is not implemented in the current baseline: `msec_char` (UIR-030) and `msec_line` (UIR-031). *(v1.3.1: `recv_remote_cmd`/`send_remote_cmd` are no longer deferred — see FR-087. Later: `change_disk_cmd` was removed entirely rather than deferred — see UIR-043 (Withdrawn), FR-100–FR-104.)* | Mandatory | I | impl. survey of `app.py` |
| CR-012 | The graphical user interface shall be implemented with **PySide6 (Qt for Python)**. Tkinter shall not be used for any GUI component. PySide6 shall be declared as a runtime dependency in `pyproject.toml`. | Mandatory | I | v1.3 UI migration |
| CR-013 | The Material Design visual theme (UIR-070) shall be supplied by the `qt-material` package, declared as a runtime dependency in `pyproject.toml`. The theme shall be applied centrally at application start-up (not per-widget), so that all current and future windows inherit it. | Mandatory | I | v1.3 UI migration; impl. `app.py:main`, `theme.py:apply_theme` |
| CR-014 | The GUI, serial/terminal (`terminal/`), and configuration (`utils/`) layers shall remain decoupled such that the `terminal/` and `utils/` modules contain no PySide6 (or other GUI-toolkit) imports and remain unit-testable without a running Qt application. | Mandatory | T | CLAUDE.md §Architecture; v1.3 UI migration |

---

## 8. Non-Functional Requirements

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| NFR-001 | The application shall remain responsive during serial reads and file transfers. Serial reads shall run on a background daemon thread; each file transfer shall run on its own background thread; and all GUI updates originating from those threads shall be marshalled onto the Qt GUI (main) thread via the Qt signal/slot mechanism (queued connections) — see NFR-004. *(Prior to v1.3 this marshalling was performed with Tkinter's `self.after(0, ...)`.)* | Mandatory | T | impl. `serial_manager.py:_read_loop`, `app.py` transfer threads; v1.3 UI migration |
| NFR-002 | The application shall support both the flat and nested JSON configuration file shapes for serial settings, normalising an outer `serial` sub-dict and falling back across the alternative key names (e.g. `transport_port`/`transfer_port`, `data`/`data_bits`, `stopbits`/`stop_bits`). | Mandatory | T | CLAUDE.md §Two config JSON formats; impl. `serial_manager.py:open_port` |
| NFR-003 | The X-Modem implementation shall transmit 128-byte packets framed with SOH (0x01) and shall support both error-check modes selected by the standard receiver-driven handshake: **CRC** (CRC-16/XMODEM, polynomial 0x1021, initial value 0x0000, transmitted as a 2-byte big-endian trailer), requested by the receiver polling with `'C'` (0x43); and **checksum** (arithmetic sum of the data bytes modulo 256, 1-byte trailer), requested by the receiver polling with NAK (0x15). When receiving, the application shall poll with NAK (checksum) **first** and fall back to `'C'` (CRC) only if the sender does not answer NAK, and shall additionally accept STX (0x02) frames carrying 1024 data bytes (XMODEM-1K) from 1K-capable senders such as PCPUT1K. The final transmitted packet shall be padded to a full 128-byte data field using the pad byte 0x1A (SUB / Ctrl-Z, the CP/M end-of-file convention), and the trailer shall be computed over the padded field. *(v1.3.1: extended from checksum-only to add CRC and XMODEM-1K receive for interoperability with PCGET/PCPUT. v1.6.1: receive polls NAK before `'C'` — the CP/M senders are checksum-only and abort on a stray `'C'` ("Unknown response from host").)* | Mandatory | T | impl. `xmodem.py:send_file`, `receive_file` |
| NFR-004 | No Qt widget shall be created or mutated from any thread other than the Qt GUI (main) thread. Cross-thread UI updates (serial receive callbacks, transfer progress/results, transfer byte echo) shall be delivered to the GUI thread exclusively via Qt signals connected with `Qt.QueuedConnection` (or the implicitly-queued cross-thread default), satisfying NFR-001. | Mandatory | T | v1.3 UI migration; impl. `app.py:_connect_signals` |

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
| App_Requirements / App_Design §File Transfers | FR-080 – FR-086, FR-082→NFR-003, FR-086 impl. |
| App_Design §Receiving / Sending data | FR-090 – FR-098 |
| App_Requirements §Main Program GUI (Terminal/Disconnect buttons) | UIR-016, FR-097 |
| App_Requirements §Serial Configuration Dialog | UIR-020 – UIR-031, IFR-002, IFR-003 |
| App_Requirements §General Configuration Dialog | UIR-040 – UIR-050 |
| App_Requirements §Terminal Window | UIR-060 – UIR-067 |
| v1.3 UI migration (PySide6 + Material) | UIR-070 – UIR-074, CR-012 – CR-014, NFR-004; revises STR-002, UIR-013, NFR-001 |
| App_Design §DIR parsing algorithm | DR-001 – DR-032 |
| App_Design §Project Structure / Class Files / Code Quality | CR-001 – CR-009 |
| Deferred / as-built constraints (impl. survey) | CR-010, CR-011, NFR-001 – NFR-003 |
| App_Design §Program state | FR-001 – FR-003 |

---

## 10. Issue Resolution Log

The ambiguities and gaps identified during the initial consolidation (v1.0) were resolved in v1.1 by
inspecting the authoritative implementation under `src/cpm_fm/`. A v1.2 requirements review (multi-agent
check against the as-built code) surfaced further code/spec discrepancies; the stakeholder decided each
direction (code-follows-spec or spec-follows-code), recorded as OI-09–OI-19 below. A v1.7.1 alignment
pass added OI-20–OI-21. All issues are now closed.

| ID | Issue | Resolution | Evidence | Affected requirements |
|----|-------|------------|----------|-----------------------|
| OI-01 | Whether a separate Disconnect control exists alongside Connect. | **Resolved.** A separate Disconnect button exists and is enabled at startup; Connect does not toggle. Added UIR-016 and updated UIR-013. | `app.py:75` (`btn_disconnect`) | UIR-013, UIR-016, FR-050–FR-057 |
| OI-02 | Behaviour when a status message exceeds 127 characters. | **Resolved.** The application truncates the message to its first 127 characters. Updated UIR-014. | `app.py:105` (`text[:127]`) | UIR-014 |
| OI-03 | When/how the "Change Disk" command is sent. | **Resolved.** The deferred `change_disk_cmd` setting and its "Change Disk" field were removed; remote drive changes are now performed via the Remote Files drive drop-down. UIR-043 withdrawn. | `app.py:change_drive`, `_do_change_drive_logic` | UIR-043, FR-100–FR-104, UIR-017 |
| OI-04 | NFR-001 lacked a measurable acceptance criterion. | **Resolved.** NFR-001 rewritten with concrete criteria: background daemon thread for reads, per-transfer daemon threads, GUI updates via `self.after(0, ...)`. | `serial_manager.py:_read_loop`; `app.py` transfer threads | NFR-001 |
| OI-05 | X-Modem mode and packet size unconfirmed. | **Resolved.** 128-byte packets, SOH framing, checksum mode (sum mod 256). NFR-003 firmed up. | `xmodem.py:36-38, 63-69` | NFR-003, FR-082 |
| OI-06 | Mapping between parser dictionary and displayed list. | **Resolved.** The dictionary keys are displayed sorted in ascending alphabetical order. Updated FR-078. | `app.py:194` (`sorted(files_dict.keys())`) | FR-077, FR-078, DR-021 |
| OI-07 | Behaviour of the Terminal button independent of Connect. | **Resolved.** The Terminal button opens or restores the Terminal Window without requiring an open port. Added FR-097. | `app.py:87, 126-131` (`show_terminal`) | UIR-013, FR-097 |
| OI-08 | How Transmit Delay settings affect transmission. | **Resolved.** `msec_char`/`msec_line` are stored settings only; they are not applied during transmission in the current baseline. Updated UIR-030/031 and added CR-011. | No use site in `serial_manager.py`/`app.py` | UIR-030, UIR-031, CR-011 |
| OI-09 | Whether Load merges settings and filters unrecognised keys, or fully replaces the store. | **Resolved (spec-follows-code).** Load is a full replace; unrecognised keys are retained verbatim but never alter behaviour. Reworded FR-011/FR-012. | `app.py:load_config` (`self.settings = load_json(...)`) | FR-011, FR-012 |
| OI-10 | Whether Connect opens the Terminal Window. | **Resolved (spec-follows-code).** Connect does not open the window; it opens exclusively via the Terminal button (FR-097). Removed FR-035. | `app.py:do_connect` (no window open) | FR-035, FR-097 |
| OI-11 | Whether a transfer requires both status flags or only Transport. | **Resolved (code-follows-spec).** A transfer now requires **both** the Terminal and Transport flags. Updated the guards in `do_copy_to_remote`/`do_copy_to_host` and aligned CR-010 with FR-080. | `app.py:do_copy_to_remote`, `do_copy_to_host` (both-flag guard) | FR-080, CR-010 |
| OI-12 | Whether the final X-Modem packet is padded to 128 bytes. | **Resolved (code-follows-spec).** The final packet is padded to 128 bytes with 0x1A (Ctrl-Z) before checksum; NFR-003 updated to specify the pad byte. | `xmodem.py:send_file` (PAD = 0x1A) | NFR-003 |
| OI-13 | The remote-list capture wait mechanism (fixed sleep vs. buffer timeout). | **Resolved (code-follows-spec).** Implemented a ≥1 s initial wait followed by a 0.5 s idle-timeout on the capture buffer (max 10 s); FR-076 reworded to this precise mechanism. | `app.py:_do_refresh_remote_logic` | FR-076 |
| OI-14 | Whether Update and Refresh differ functionally. | **Resolved.** Update (Remote Files group) refreshes the remote list only; the central Refresh refreshes both Host and Remote lists. Reworded FR-073; added FR-063. | `app.py:refresh_remote_files`, `refresh_all` | FR-063, FR-073 |
| OI-15 | Behaviour on a shared physical port / visibility of transfer traffic. | **Resolved.** Transfer bytes (both directions) are echoed to the Terminal Window as hex tokens `<HH>`; added FR-086 and a monitor hook in `XModem`. | `app.py:_on_transfer_bytes`; `xmodem.py` monitor | FR-086 |
| OI-16 | Project-structure constraints contradicted the as-built tree (no `main.py`, no `resources/`, multi-class module, snake_case file names). | **Resolved (spec-follows-code).** CR-002 restated to `__main__.py`; CR-006 marked deferred/Desirable; CR-007/CR-008 relaxed to the as-built module/naming convention. | `find src -name '*.py'`; no `main.py`/`resources/` | CR-002, CR-006, CR-007, CR-008 |
| OI-17 | Stale "empty stub" notes on FR-084/FR-085. | **Resolved.** The transfer handlers work; removed the stale stub notes. | `app.py:do_copy_to_remote`, `do_copy_to_host` | FR-084, FR-085 |
| OI-18 | FR-050–FR-057 disconnect sequence (conditional close, per-port failure dialogs, workflow cancellation) was not implemented; `do_disconnect` did an unconditional `close_ports()`. | **Resolved (code-follows-spec).** Added `close_terminal_port`/`close_transport_port` (returning success) and reimplemented `do_disconnect` to close the Terminal Port (abort with "Terminal port is unable to be closed" on failure), clear the Transport flag for a shared port, and otherwise close the Transport Port (error "Transport port is unable to be closed" on failure). | `app.py:do_disconnect`; `serial_manager.py:close_terminal_port`, `close_transport_port` | FR-050–FR-057 |
| OI-19 | FR-090/FR-092 mandated receive/transmit data buffers that did not exist. | **Resolved (code-follows-spec).** Added `_rx_buffer`/`_tx_buffer`, populated in `handle_terminal_recv`/`handle_terminal_send`; the Terminal Window Clear button now clears both buffers via a `clear_callback`. Reworded FR-090/FR-092 and extended FR-095. | `app.py:_rx_buffer`/`_tx_buffer`, `clear_terminal_buffers`; `terminal_window.py:clear_text` | FR-090, FR-092, FR-095 |
| OI-20 | The Flow Control setting (UIR-028) was collected and persisted by the Serial Config dialog but never applied when opening the port, and was not listed among the deferred settings (CR-011). | **Resolved (code-follows-spec).** `open_port` now maps the `flow` value (flat) / `flow_control` value (nested, NFR-002) onto pyserial's `xonxoff`/`rtscts`/`dsrdtr`; NONE/unknown disables all. UIR-028 updated to state the setting is applied; unit tests cover every dropdown value and both key shapes. | `serial_manager.py:open_port`; `tests/test_serial_manager.py` | UIR-028, NFR-002 |
| OI-21 | FR-075/FR-100 stated the list/drive command is sent "to the Terminal Port **and to the receive text area**", but the application writes the command to the receive area only when Local Echo is enabled (FR-093); otherwise it appears solely via the remote's serial echo. | **Resolved (spec-follows-code).** FR-075/FR-100 reworded: the command is sent to the Terminal Port and is reflected in the receive area by the remote's echo (or local echo, FR-093); the application does not echo it itself. No code change. | `app.py:handle_terminal_send` (local-echo-gated `term_write`) | FR-075, FR-100 |

> Historical note (v1.1): App_Requirements specified Copy to Remote / Copy to Host as *empty stubs*, but
> the implementation provides working X-Modem transfer handlers. This is captured in FR-080–FR-086 and
> CR-010, which reflect the as-built behaviour; the stale stub notes were removed in v1.2 (OI-17).

---

## 11. Change History

| Version | Date | Author | Description |
|---------|------|--------|-------------|
| 1.7.2 | 2026-06-13 | Software Engineer | Added persistence of the last-used configuration-file folder, kept separate from the Host Files directory. The File > Load and File > Save dialogs now reopen in the folder where a config was last loaded/saved. **Added:** FR-006 (remember the config-file folder, `QSettings`-backed, distinct from the host directory FR-060). **Modified:** FR-010, FR-013 (dialogs default to the remembered config folder). **Code changes:** `window_state.py` (`last_config_dir` property), `app.py` (`menu_load`/`menu_save` seed and update it). |
| 1.7.1 | 2026-06-13 | Requirements Checker | Code/spec alignment pass against the as-built source. **Resolved OI-20 (code-follows-spec):** the Flow Control setting (UIR-028), previously collected but never applied and not listed as deferred, is now applied at port open — `serial_manager.py:open_port` maps `flow`/`flow_control` onto pyserial's `xonxoff`/`rtscts`/`dsrdtr` (NFR-002 key-name fallback); added `tests/test_serial_manager.py`. **Modified:** UIR-028 (setting is applied). **Resolved OI-21 (spec-follows-code):** FR-075/FR-100 said the list/drive command is sent "to the receive text area", but the app echoes it there only when Local Echo is on; otherwise it appears via the remote's serial echo. **Modified:** FR-075, FR-100 (reworded to the as-built echo behaviour). |
| 1.7.0 | 2026-06-12 | Software Engineer | Added support for persisting the host directory per configuration file. **Modified:** FR-060 (startup directory logic), FR-062 (persistence timing). **Added:** UIR-053 (Default Host Directory field in General Config Dialog). |
| 1.6.1 | 2026-06-08 | Requirements Checker | Fixed a multi-file-batch timing defect: the leading characters of the second and subsequent launch commands (e.g. `PCPUT $1`) were lost because the command was sent while CP/M was still returning to the CCP prompt after the previous transfer and not yet servicing its UART, so the remote reported "command not found" and the transfer failed. **Added:** FR-109 (wait for the terminal prompt to return, plus a settle delay, before each launch command after the first), UIR-052 ("Xfer Inter-file Delay (s)" field, default 2). **Code changes:** `app.py` (`_wait_for_terminal_idle`, `_interfile_delay`, called between files in `_transfer_to_remote_batch`/`_transfer_to_host_batch`), `gui/config_dialogs.py` (new field). Also fixed a related receive-handshake defect exposed once the launch command stopped being truncated: the X-Modem receiver polled with the CRC start character `'C'` first, which the checksum-only CP/M senders (PCPUT V1.0) reject with "Unknown response from host". **Modified:** NFR-003 (receive polls NAK before `'C'`). **Code changes:** `terminal/xmodem.py:receive_file`. |
| 1.6 | 2026-06-08 | Requirements Checker | Added multi-file transfer. The Copy to Remote / Copy to Host actions now transfer every file selected in the (already multi-select) list. **Added:** FR-106 (transfer all selected files; warn if none selected), FR-107 (sequential transfer in list order, one X-Modem session per file), FR-108 (abort the batch on the first failure, naming the failed file; refresh once if any succeeded). **Modified:** FR-105 (single dialog serves the whole batch, showing "File `i` of `N`"), UIR-051 (batch-position label). **Code changes:** `gui/transfer_dialog.py` (constructor takes a file count, `batch_label`, `set_file`), `app.py` (`_selected_filenames`, `_send_one_to_remote`/`_recv_one_to_host` per-file helpers, `_transfer_to_remote_batch`/`_transfer_to_host_batch` drivers, `batch_started`/`transfer_file_started` signals replacing `transfer_started`). |
| 1.5 | 2026-06-08 | Requirements Checker | Added a transfer-progress dialog shown for the duration of every X-Modem transfer. **Added:** FR-105 (modal progress dialog: filename + cumulative blocks/bytes, updated per block, auto-closed on success or failure), UIR-051 (dialog contents/layout, new §4.7). **Code changes:** `xmodem.py` (per-packet `progress` hook in `send_file`/`receive_file`), new `gui/transfer_dialog.py:TransferProgressDialog`, `app.py` (`transfer_started`/`transfer_progress` signals, `_on_transfer_started`/`_on_transfer_progress`/`_close_transfer_dialog`, `_on_transfer_progress_cb`, dialog teardown in `_on_transfer_completed`/`_on_error_raised`). Progress is marshalled worker→GUI thread via Qt signals (NFR-004). |
| 1.4 | 2026-06-06 | Requirements Checker | Updated GUI layout requirements to reflect the move of transfer and refresh buttons from the toolbar to rows beneath their respective file lists. Renamed 'Refresh' to 'Refresh Host'. Affected IDs: FR-063, FR-072, UIR-011, UIR-012, UIR-013, UIR-071. |
| 1.3 | 2026-06-06 | UI Migration | Specified migration of the GUI from Tkinter to **PySide6 (Qt for Python)** with a Material Design theme, per stakeholder decision (framework: PySide6; theme: `qt-material`; default theme mode: follow OS; full requirement traceability requested). **Added:** UIR-070 (Material theme), UIR-071 (top toolbar), UIR-072 (draggable splitter between panes), UIR-073 (OS-following light/dark default, dark fallback), UIR-074 (status-bar connection indicators, Desirable), CR-012 (PySide6 mandated, no Tkinter), CR-013 (`qt-material` theme applied centrally at start-up), CR-014 (GUI/`terminal`/`utils` decoupling — no GUI imports in non-GUI layers), NFR-004 (Qt signal/slot thread-safety). **Modified:** §1.2 Scope and §1.4 Definitions (Qt/PySide6/QSS/Material added), STR-002 (PySide6 noted), UIR-013 (actions presented as a toolbar from v1.3), NFR-001 (cross-thread GUI updates via Qt signals/slots, replacing `self.after`). The X-Modem, serial-management, CP/M parsing, and configuration layers (`terminal/`, `utils/`) and all of §3 functional behaviour are unchanged by this migration. Status remains Reviewed; the new requirements are approved for implementation but not yet implemented. |
| 1.2 | 2026-06-06 | Requirements Checker | Reconciled code/spec discrepancies found by a multi-agent requirements review, per stakeholder decisions (OI-09–OI-17). **Added:** FR-063 (Refresh refreshes both lists), FR-086 (X-Modem transfer bytes echoed to the Terminal Window as hex `<HH>` tokens). **Removed:** FR-035 (Connect no longer opens the Terminal Window; superseded by FR-097). **Modified:** FR-011/FR-012 (Load is a full replace; unrecognised keys retained but inert), FR-073 (Update is Remote-list-only), FR-076 (≥1 s wait then 0.5 s buffer idle-timeout, max 10 s), FR-080/CR-010 (transfer requires **both** status flags), FR-084/FR-085 (removed stale "empty stub" notes), NFR-003 (final packet padded to 128 bytes with 0x1A), CR-002 (`__main__.py` entry point), CR-006 (resources folder deferred, Desirable), CR-007/CR-008 (relaxed to as-built cohesive-module / snake_case naming). Also resolved OI-18 (implemented the FR-050–FR-057 disconnect sequence with per-port failure dialogs and workflow cancellation) and OI-19 (implemented real receive/transmit data buffers cleared by the Clear button); **modified** FR-090/FR-092 (concrete buffers) and FR-095 (clears buffers too). **Code changes:** `app.py` (both-flag transfer guard, buffer idle-timeout, `refresh_all`, `_on_transfer_bytes` hex echo, full `do_disconnect` sequence, `_rx_buffer`/`_tx_buffer` + `clear_terminal_buffers`), `xmodem.py` (final-packet padding, monitor hook on all reads/writes), `serial_manager.py` (`close_terminal_port`/`close_transport_port`), `terminal_window.py` (Clear `clear_callback`). All v1.2 issues (OI-09–OI-19) closed. Updated §9 traceability and §10 issue log. |
| 1.1 | 2026-06-06 | Requirements Checker | Resolved all open issues (OI-01–OI-08) by inspecting the implementation under `src/cpm_fm/`. **Added:** UIR-016 (Disconnect button), FR-097 (Terminal button behaviour), FR-098 (send-with-port-closed status), CR-011 (deferred settings). **Modified:** UIR-013 (added Disconnect to button set), UIR-014 (127-char truncation behaviour), UIR-030/UIR-031 (transmit-delay stored-only note), UIR-043 (Change Disk stored-only note), FR-078 (sorted remote-list display), CR-010 (as-built transfer guarding vs. stub spec), NFR-001 (measurable threading criteria), NFR-002 (key-name normalisation detail), NFR-003 (SOH/checksum X-Modem detail). Converted §10 from an open-issues list to a closed issue-resolution log. Updated §9 traceability. Status advanced from Draft to Reviewed. |
| 1.0 | 2026-06-06 | Requirements Checker | Initial baseline. Consolidated and restructured all requirements from `docs/App_Requirements.md` and `docs/App_Design.md` into an ISO/IEC/IEEE 29148-conformant SRS. Assigned unique IDs across STR/FR/UIR/IFR/DR/CR/NFR categories (STR-001–003, FR-001–096, UIR-001–067, IFR-001–004, DR-001–032, CR-001–010, NFR-001–003). Added verification methods, priorities, source traceability, a traceability summary (§9), and an open-issues log (§10, OI-01–OI-08). |
