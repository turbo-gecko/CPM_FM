# CP/M File Manager — Software Requirements Specification

| Field | Value |
|-------|-------|
| Document title | CP/M File Manager Software Requirements Specification (SRS) |
| Document ID | CPM-FM-SRS |
| Version | 1.1 |
| Status | Reviewed |
| Standard | ISO/IEC/IEEE 29148:2018 |
| Owner | Project maintainer |
| Date | 2026-06-06 |
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
configuration management.

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
| STR-002 | The product shall provide a graphical user interface implemented in Python. | Mandatory | I | App_Design §Purpose |
| STR-003 | The product shall be cross-platform. | Desirable | A | App_Design §Purpose |

---

## 3. Functional Requirements

### 3.1 Application lifecycle and state

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| FR-001 | The application shall maintain a Terminal status flag indicating whether the Terminal Port is open and available for communication. The default value at startup shall be *not set* (false). | Mandatory | T | App_Design §Program state |
| FR-002 | The application shall maintain a Transport status flag indicating whether the Transport Port is open and available for communication. The default value at startup shall be *not set* (false). | Mandatory | T | App_Design §Program state |
| FR-003 | The application shall start in an unconfigured state, with serial and general settings populated only via File > Load or the configuration dialogs. | Mandatory | T | App_Design §Program state; CLAUDE.md |

### 3.2 File menu

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| FR-010 | The File > Load menu item shall present a file-select dialog defaulting to the JSON file type for selecting a configuration file to load. | Mandatory | D | App_Requirements §Load |
| FR-011 | On loading a configuration file, the application shall update its internal serial configuration and general configuration settings with the values contained in the file. | Mandatory | T | App_Requirements §Load |
| FR-012 | On loading a configuration file, the application shall ignore any settings that are not recognised. | Mandatory | T | App_Requirements §Load |
| FR-013 | The File > Save menu item shall present a file-select dialog defaulting to the JSON file type for selecting a configuration file to save to. | Mandatory | D | App_Requirements §Save |
| FR-014 | On saving, the application shall write the internal serial configuration and general configuration settings to the selected file in JSON format. | Mandatory | T | App_Requirements §Save |
| FR-015 | The File > Exit menu item shall close any open COM ports. | Mandatory | D | App_Requirements §Exit |
| FR-016 | The File > Exit menu item shall close all open dialogs and windows. | Mandatory | D | App_Requirements §Exit |

### 3.3 Config menu

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| FR-020 | When the Config > Serial menu option is selected, the application shall present the Serial Configuration Dialog to allow the user to modify the serial settings. | Mandatory | D | App_Requirements §Serial |
| FR-021 | When the Config > General menu option is selected, the application shall present the General Configuration Dialog to allow the user to modify the general settings. | Mandatory | D | App_Requirements §General |

### 3.4 Connecting to the remote system

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| FR-030 | When the Connect button is pressed, the application shall open the Terminal Port serial port if it is not already open. | Mandatory | T | App_Requirements §Connecting |
| FR-031 | If the Terminal Port cannot be opened, the application shall display an error dialog containing the text "Terminal port is unable to be opened" and cancel the current workflow. | Mandatory | T | App_Requirements §Connecting |
| FR-032 | If the Terminal Port is successfully opened, the application shall set the Terminal status flag to true. | Mandatory | T | App_Design §Connecting |
| FR-033 | If the Terminal Port cannot be opened, the application shall set the Terminal status flag to false. | Mandatory | T | App_Design §Connecting |
| FR-034 | When the Terminal Port is opened, the application shall display the text "Terminal port open" in the status bar. | Mandatory | D | App_Requirements §Connecting |
| FR-035 | When the Connect button is pressed, the application shall open the Terminal Window if it is not already open. | Mandatory | D | App_Requirements §Connecting |
| FR-036 | The application shall display data received from the Terminal Port in the receive text area of the Terminal Window. | Mandatory | T | App_Requirements §Connecting |
| FR-037 | On connect, if the Transport Port is the same as the Terminal Port, the application shall set the Transport status flag to connected. | Mandatory | T | App_Design §Connecting |
| FR-038 | On connect, if the Transport Port is different from the Terminal Port and is not currently open, the application shall attempt to open the Transport Port. | Mandatory | T | App_Design §Connecting |
| FR-039 | If the Transport Port cannot be opened, the application shall display an error dialog containing the text "Transport port is unable to be opened". | Mandatory | T | App_Design §Connecting |
| FR-040 | If the Transport Port is successfully opened, the application shall set the Transport status flag to connected. | Mandatory | T | App_Design §Connecting |

### 3.5 Disconnecting from the remote system

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| FR-050 | When the Disconnect button is pressed, if the Terminal Port is currently open, the application shall attempt to close the Terminal Port serial port. | Mandatory | T | App_Requirements §Disconnecting |
| FR-051 | If the Terminal Port cannot be closed, the application shall display an error dialog containing the text "Terminal port is unable to be closed" and cancel the current workflow. | Mandatory | T | App_Requirements §Disconnecting |
| FR-052 | When the Terminal Port is closed, the application shall set the Terminal status flag to false. | Mandatory | T | App_Design §Disconnecting |
| FR-053 | When the Terminal Port is closed, the application shall display the text "Terminal port closed" in the status bar. | Mandatory | D | App_Requirements §Disconnecting |
| FR-054 | On disconnect, if the Transport Port is the same as the Terminal Port, the application shall set the Transport status flag to false. | Mandatory | T | App_Design §Disconnecting |
| FR-055 | On disconnect, if the Transport Port is different from the Terminal Port and is currently open, the application shall attempt to close the Transport Port. | Mandatory | T | App_Design §Disconnecting |
| FR-056 | If the Transport Port cannot be closed, the application shall display an error dialog containing the text "Transport port is unable to be closed". | Mandatory | T | App_Design §Disconnecting |
| FR-057 | If the Transport Port is successfully closed, the application shall set the Transport status flag to false. | Mandatory | T | App_Design §Disconnecting |

### 3.6 Host file management

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| FR-060 | On startup, the application shall populate the Host Files list with the files in the current working directory of the host system. | Mandatory | T | App_Requirements §Host Files |
| FR-061 | The Change Directory button shall be enabled at startup. | Mandatory | I | App_Requirements §Change Directory |
| FR-062 | When the Change Directory button is pressed, the application shall present a folder-select dialog for the user to choose the folder whose contents are loaded into the Host Files list. | Mandatory | D | App_Requirements §Change Directory |

### 3.7 Remote file listing

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| FR-070 | The Remote Files list shall be empty (unpopulated) at startup. | Mandatory | T | App_Requirements §Remote Files |
| FR-071 | The Update button shall be enabled at startup. | Mandatory | I | App_Requirements §Update |
| FR-072 | The Refresh button shall be enabled at startup. | Mandatory | I | App_Requirements §Refresh |
| FR-073 | When the Update or Refresh button is pressed, the application shall populate the Remote Files list following the "Populating remote file list" process. | Mandatory | T | App_Requirements §Update, §Refresh |
| FR-074 | If the Terminal Port is not open when populating the remote file list, the application shall set the status bar text to "Terminal port not open - cannot read file list" and clear the Remote Files list. | Mandatory | T | App_Requirements §Populating remote file list |
| FR-075 | If the Terminal status flag is true, the application shall send the configured List Files command followed by the configured EOL character(s) to the Terminal Port and to the receive text area. | Mandatory | T | App_Design §Populating remote file list |
| FR-076 | After sending the List Files command, the application shall wait for at least one second and then wait for the receive buffer to time out before processing the received text. | Mandatory | T | App_Design §Populating remote file list |
| FR-077 | The application shall process the captured remote output into a dictionary of filenames using the CP/M 4-column DIR parsing algorithm (see §6). | Mandatory | T | App_Design §Populating remote file list |
| FR-078 | The application shall populate the Remote Files list with the entries produced by the parsing algorithm, displaying the dictionary keys (filenames) sorted in ascending alphabetical order. | Mandatory | T | App_Design §Populating remote file list; impl. `app.py:_update_remote_list_ui` |
| FR-079 | On successful population of the remote file list, the application shall update the status bar with the text "Remote file list updated". | Mandatory | D | App_Requirements §Populating remote file list |

### 3.8 File transfers

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| FR-080 | A file transfer shall be permitted only when both the Terminal status flag and the Transport status flag are set to connected. | Mandatory | T | App_Requirements §File Transfers; App_Design §File Transfers |
| FR-081 | The application shall support file transfers in both directions: host-to-remote and remote-to-host. | Mandatory | T | App_Requirements §File Transfers |
| FR-082 | The application shall use the X-Modem protocol for all file transfers. | Mandatory | T | App_Requirements §File Transfers |
| FR-083 | The application shall use the Transport (Transfer) Port for all file transfers. | Mandatory | T | App_Requirements §File Transfers |
| FR-084 | The Copy to Remote button shall be enabled at startup. *(Note: the current handler is specified as an empty stub — see CR-010.)* | Mandatory | I | App_Requirements §Copy to Remote |
| FR-085 | The Copy to Host button shall be enabled at startup. *(Note: the current handler is specified as an empty stub — see CR-010.)* | Mandatory | I | App_Requirements §Copy to Host |

### 3.9 Terminal window — receive and transmit

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| FR-090 | Data received from the Terminal Port shall be stored in a receive data buffer until explicitly cleared. | Mandatory | T | App_Design §Receiving data |
| FR-091 | All data received from the Terminal Port shall be displayed in the receive text area of the Terminal Window. | Mandatory | T | App_Design §Receiving data |
| FR-092 | Data transmitted to the Terminal Port shall be stored in a transmit data buffer until explicitly cleared. | Mandatory | T | App_Design §Sending data |
| FR-093 | When the Local Echo checkbox is enabled, transmitted data shall be copied to the receive text area of the Terminal Window. | Mandatory | T | App_Design §Sending data |
| FR-094 | Transmitted data shall have the configured EOL character(s) appended before being sent. | Mandatory | T | App_Design §Sending data |
| FR-095 | When the Clear button in the Terminal Window is pressed, the receive text area shall be cleared. | Mandatory | D | App_Requirements §Terminal Window |
| FR-096 | When the Send button in the Terminal Window is pressed, the contents of the transmit text field shall be sent to the Terminal Port. | Mandatory | T | App_Requirements §Terminal Window |
| FR-097 | When the Terminal button in the main window is pressed, the application shall open the Terminal Window if it is not already open, or restore (de-iconify) it if it is hidden. This action shall be independent of the Connect action and shall not require an open Terminal Port. | Mandatory | D | App_Requirements §Main Program GUI; impl. `app.py:show_terminal` |
| FR-098 | If the Terminal Port is not open when the user attempts to send data from the Terminal Window, the application shall set the status bar text to "Terminal port not open - cannot send" and not transmit. | Mandatory | T | impl. `app.py:handle_terminal_send` |

---

## 4. User Interface Requirements

### 4.1 Menu bar

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| UIR-001 | The GUI shall present a menu bar at the top of the main window. | Mandatory | I | App_Requirements §Look and Feel, §Main Program GUI |
| UIR-002 | The menu bar shall contain a File menu with the items Load, Save, and Exit. | Mandatory | I | App_Requirements §Look and Feel |
| UIR-003 | The menu bar shall contain a Config menu with the items Serial and General. | Mandatory | I | App_Requirements §Look and Feel |

### 4.2 Main window layout

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| UIR-010 | The main window shall contain a status bar at the bottom. | Mandatory | I | App_Requirements §Main Program GUI |
| UIR-011 | The main window shall contain a "Host Files" group containing a "Change Directory" button and a multi-select widget. | Mandatory | I | App_Requirements §Main Program GUI |
| UIR-012 | The main window shall contain a "Remote Files" group containing an "Update" button and a multi-select widget. | Mandatory | I | App_Requirements §Main Program GUI |
| UIR-013 | The main window shall present, between the Host Files and Remote Files groups, the buttons: Connect, Disconnect, Copy to Remote, Copy to Host, Refresh, and Terminal. | Mandatory | I | App_Requirements §Main Program GUI; impl. `app.py` |
| UIR-014 | The status bar shall be a single-line text label. When a status message exceeds 127 characters, the application shall truncate it to the first 127 characters before display. | Mandatory | T | App_Requirements §Status Bar; impl. `app.py:set_status` |
| UIR-015 | The Connect button shall be enabled at startup. | Mandatory | I | App_Requirements §Connect |
| UIR-016 | The main window shall provide a separate Disconnect button, enabled at startup, that invokes the disconnect behaviour (FR-050–FR-057). | Mandatory | I | App_Requirements §Disconnect; impl. `app.py` |

### 4.3 Serial Configuration Dialog

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| UIR-020 | The Serial Configuration Dialog shall be a modal dialog titled "Serial Config". | Mandatory | I | App_Requirements §Serial Configuration Dialog |
| UIR-021 | The dialog shall present a "Port Settings" group laid out in two columns, with the setting name left-justified in the first column and the setting field right-justified in the second column. | Mandatory | I | App_Requirements §Serial Configuration Dialog |
| UIR-022 | The dialog shall provide a Terminal Port drop-down list populated by enumerating the serial ports installed on the host. | Mandatory | T | App_Requirements §Serial Configuration Dialog |
| UIR-023 | The dialog shall provide a Transfer Port drop-down list populated by enumerating the serial ports installed on the host. | Mandatory | T | App_Requirements §Serial Configuration Dialog |
| UIR-024 | The dialog shall provide a Speed drop-down list with the values 300, 1200, 2400, 4800, 9600, 14400, 19200, 38400, 57600, 115200, 230400, 460800, and 921600; the default shall be 115200. | Mandatory | T | App_Requirements §Serial Configuration Dialog |
| UIR-025 | The dialog shall provide a Data drop-down list with the values 7 and 8; the default shall be 8. | Mandatory | T | App_Requirements §Serial Configuration Dialog |
| UIR-026 | The dialog shall provide a Parity drop-down list with the values NONE, ODD, EVEN, MARK, and SPACE; the default shall be NONE. | Mandatory | T | App_Requirements §Serial Configuration Dialog |
| UIR-027 | The dialog shall provide a Stop Bits drop-down list with the values 1 and 2; the default shall be 1. | Mandatory | T | App_Requirements §Serial Configuration Dialog |
| UIR-028 | The dialog shall provide a Flow Control drop-down list with the values NONE, XON/XOFF, RTS/CTS, and DSR/DTR; the default shall be NONE. | Mandatory | T | App_Requirements §Serial Configuration Dialog |
| UIR-029 | The dialog shall present a "Transmit Delay" group laid out in two columns, formatted as in UIR-021. | Mandatory | I | App_Requirements §Serial Configuration Dialog |
| UIR-030 | The dialog shall provide an "msec/char" text field that defaults to 0 and is limited to integer values between 0 and 255 inclusive. The value shall be persisted as the `msec_char` setting. *(Inter-character transmission delay is a stored setting only; it is not yet applied during transmission — see CR-011.)* | Mandatory | T | App_Requirements §Serial Configuration Dialog |
| UIR-031 | The dialog shall provide an "msec/line" text field that defaults to 0 and is limited to integer values between 0 and 255 inclusive. The value shall be persisted as the `msec_line` setting. *(Inter-line transmission delay is a stored setting only; it is not yet applied during transmission — see CR-011.)* | Mandatory | T | App_Requirements §Serial Configuration Dialog |

### 4.4 General Configuration Dialog

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| UIR-040 | The General Configuration Dialog shall be a modal dialog titled "General Config". | Mandatory | I | App_Requirements §General Configuration Dialog |
| UIR-041 | The dialog shall present a "Terminal Commands" group laid out in two columns as in UIR-021. | Mandatory | I | App_Requirements §General Configuration Dialog |
| UIR-042 | The dialog shall provide a "List Files" text field limited to 79 characters with a default value of "DIR". | Mandatory | T | App_Requirements §General Configuration Dialog |
| UIR-043 | The dialog shall provide a "Change Disk" text field limited to 79 characters with an empty default value, persisted as the `change_disk_cmd` setting. *(The command is stored for future use; no current functional requirement sends it to the remote — see CR-011.)* | Mandatory | T | App_Requirements §General Configuration Dialog |
| UIR-044 | The dialog shall present an "Xmodem Commands" group laid out in two columns as in UIR-021. | Mandatory | I | App_Requirements §General Configuration Dialog |
| UIR-045 | The dialog shall provide a "Receive from Remote" text field limited to 79 characters with a default value of "PCPUT $1". | Mandatory | T | App_Requirements §General Configuration Dialog |
| UIR-046 | The dialog shall provide a "Send to Remote" text field limited to 79 characters with a default value of "PCGET $1". | Mandatory | T | App_Requirements §General Configuration Dialog |
| UIR-047 | The dialog shall present an "End of Line" group of mutually exclusive radio buttons: Carriage Return (CR), Line Feed (LF), and Carriage Return/Line Feed (CR/LF). | Mandatory | I | App_Requirements §General Configuration Dialog |
| UIR-048 | The Carriage Return (CR) radio button shall be the default selection. | Mandatory | T | App_Requirements §General Configuration Dialog |

### 4.5 Terminal Window

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| UIR-060 | The Terminal Window shall be a non-modal window titled "Terminal". | Mandatory | I | App_Requirements §Terminal Window |
| UIR-061 | The Terminal Window shall contain a large multi-line text area named "Receive" for displaying incoming data. | Mandatory | I | App_Requirements §Terminal Window |
| UIR-062 | The Receive text area shall auto-scroll incoming text (subject to the Autoscroll control). | Mandatory | D | App_Requirements §Terminal Window |
| UIR-063 | The Receive text area shall be read-only. | Mandatory | T | App_Requirements §Terminal Window |
| UIR-064 | The Terminal Window shall provide a "Clear" button, left-aligned, below the Receive text area. | Mandatory | I | App_Requirements §Terminal Window |
| UIR-065 | The Terminal Window shall provide a "Local Echo" checkbox, centred, that is disabled by default. | Mandatory | T | App_Requirements §Terminal Window |
| UIR-066 | The Terminal Window shall provide an "Autoscroll" checkbox, right-aligned, that is enabled by default. | Mandatory | T | App_Requirements §Terminal Window |
| UIR-067 | The Terminal Window shall provide a "Transmit" group containing a single-line text field aligned left and a "Send" button aligned right in the same row. | Mandatory | I | App_Requirements §Terminal Window |

---

## 5. External Interface Requirements

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| IFR-001 | The application shall communicate with the remote CP/M system over a serial (RS-232 style) communications link. | Mandatory | T | App_Design §Purpose |
| IFR-002 | The application shall support configuring two logical serial ports — a Terminal Port and a Transport Port — which may map to the same physical port. | Mandatory | T | App_Requirements §Serial Configuration Dialog; CLAUDE.md |
| IFR-003 | The application shall enumerate the serial ports installed on the host and present them for selection. | Mandatory | T | App_Requirements §Serial Configuration Dialog |
| IFR-004 | Configuration data shall be exchanged with the file system as JSON files. | Mandatory | T | App_Requirements §Load, §Save |

---

## 6. Data Requirements — CP/M 4-Column DIR Parsing Algorithm

The following requirements define the algorithm for extracting remote file names from standard CP/M
2.2 four-column `DIR` output.

### 6.1 Line filtering

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| DR-001 | The parser shall ignore lines that are empty or contain only whitespace. | Mandatory | T | App_Design §Ignore non-file lines |
| DR-002 | The parser shall ignore lines that begin with a shell prompt of the form `C>` where `C` may be any drive letter. | Mandatory | T | App_Design §Ignore non-file lines |
| DR-003 | The parser shall ignore lines that contain the substring "NO FILE". | Mandatory | T | App_Design §Ignore non-file lines |
| DR-004 | The parser shall process only lines that start with the literal prefix `C:` (where `C` may be any drive letter). | Mandatory | T | App_Design §Identify file listing lines |
| DR-005 | The parser shall process only lines that contain at least one occurrence of the separator sequence space-colon-space (" : "). | Mandatory | T | App_Design §Identify file listing lines |

### 6.2 Entry extraction

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| DR-010 | For each identified file listing line, the parser shall remove the leading drive prefix and process only the remainder of the line. | Mandatory | T | App_Design §Strip drive identifier |
| DR-011 | The parser shall split each processed line into individual file entries using the space-colon-space delimiter. | Mandatory | T | App_Design §Split file entries |
| DR-012 | For each file entry, the parser shall replace any sequence of one or more consecutive spaces with a single space and trim leading and trailing whitespace. | Mandatory | T | App_Design §Normalise whitespace |
| DR-013 | For each normalised entry, the parser shall split into tokens by whitespace, treating the last token as the file extension and all preceding tokens as the filename base concatenated without spaces. | Mandatory | T | App_Design §Parse filename and extension |
| DR-014 | The parser shall construct each canonical filename in the format `<filename_base>.<extension>`. | Mandatory | T | App_Design §Construct full filename |

### 6.3 Output and robustness

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| DR-020 | The parser shall store each constructed filename as a key in a dictionary with the boolean value `True`; duplicate filenames shall overwrite the existing key (no duplicate keys). | Mandatory | T | App_Design §Store filenames |
| DR-021 | The parser shall return a Python `dict` whose keys are strings of the form "NAME.EXT" and whose values are the boolean literal `True`, containing only valid filenames extracted from the input. | Mandatory | T | App_Design §Output format |
| DR-022 | The parser shall preserve the exact case of filename and extension characters as provided in the input. | Mandatory | T | App_Design §Case sensitivity |
| DR-023 | The parser shall skip malformed entries with fewer than two tokens. | Mandatory | T | App_Design §Handle edge cases |
| DR-024 | The parser shall not raise exceptions for invalid or unexpected input. | Mandatory | T | App_Design §Handle edge cases |
| DR-025 | The parser shall return an empty dictionary if no valid file entries are found. | Mandatory | T | App_Design §Handle edge cases |
| DR-026 | The parser shall tolerate irregular spacing, extra colons within filenames, and mixed line endings (`\n`, `\r\n`). | Mandatory | T | App_Design §Input robustness |

### 6.4 Parser constraints

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| DR-030 | The parser assumes input conforming to standard CP/M 2.2 `DIR` output format (8.3 filenames, space-padded). | Mandatory | A | App_Design §Constraints |
| DR-031 | The parser is not required to support long filenames or non-ASCII characters. | Optional | A | App_Design §Constraints |
| DR-032 | The parser is not required to parse file sizes, dates, or attributes — only names and extensions. | Mandatory | A | App_Design §Constraints |

---

## 7. Design Constraints

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| CR-001 | All source files shall reside under a `src` folder at the project root. | Mandatory | I | App_Design §Project Structure |
| CR-002 | There shall be a `main.py` entry-point source file within the source tree. | Mandatory | I | App_Design §Project Structure |
| CR-003 | All GUI-related source files shall reside in a `gui` folder within the source tree. | Mandatory | I | App_Design §Project Structure |
| CR-004 | All serial and terminal related source files shall reside in a `terminal` folder within the source tree. | Mandatory | I | App_Design §Project Structure |
| CR-005 | All other source files shall reside in a `utils` folder within the source tree. | Mandatory | I | App_Design §Project Structure |
| CR-006 | There shall be a `resources` folder at the project root for icons, images, and other non-Python files. | Mandatory | I | App_Design §Project Structure |
| CR-007 | Each class shall have its own source file. | Mandatory | I | App_Design §Class Files |
| CR-008 | Each class source file shall be named the same as the class it contains. | Mandatory | I | App_Design §Class Files |
| CR-009 | All Python source files shall adhere to the PEP 8 standard. | Mandatory | T | App_Design §Code Quality |
| CR-010 | The Copy to Remote and Copy to Host actions shall be guarded so that a transfer is only attempted when the Transport status flag is connected; otherwise an error dialog "Transport port not connected" shall be shown. *(Note: although App_Requirements specifies empty stubs, the implementation provides working X-Modem transfer handlers — see FR-080–FR-085.)* | Mandatory | T | App_Requirements §Copy to Remote, §Copy to Host; impl. `app.py` |
| CR-011 | The following settings are persisted but their behaviour is deferred to a future release and is not implemented in the current baseline: `change_disk_cmd` (UIR-043), `msec_char` (UIR-030), `msec_line` (UIR-031), `recv_remote_cmd` (UIR-045), and `send_remote_cmd` (UIR-046). | Mandatory | I | impl. survey of `app.py` |

---

## 8. Non-Functional Requirements

| ID | Requirement | Priority | Verification | Source |
|----|-------------|----------|--------------|--------|
| NFR-001 | The application shall remain responsive during serial reads and file transfers. Serial reads shall run on a background daemon thread; each file transfer shall run on its own background daemon thread; and all GUI updates originating from those threads shall be marshalled onto the Tk main thread via `self.after(0, ...)`. | Mandatory | T | impl. `serial_manager.py:_read_loop`, `app.py` transfer threads |
| NFR-002 | The application shall support both the flat and nested JSON configuration file shapes for serial settings, normalising an outer `serial` sub-dict and falling back across the alternative key names (e.g. `transport_port`/`transfer_port`, `data`/`data_bits`, `stopbits`/`stop_bits`). | Mandatory | T | CLAUDE.md §Two config JSON formats; impl. `serial_manager.py:open_port` |
| NFR-003 | The X-Modem implementation shall use 128-byte packets framed with SOH (0x01) in checksum mode, where the checksum is the arithmetic sum of the 128 data bytes modulo 256. | Mandatory | T | impl. `xmodem.py` |

---

## 9. Requirements Traceability Summary

| Source section | Requirement IDs |
|----------------|-----------------|
| App_Design §Purpose | STR-001, STR-002, STR-003, IFR-001 |
| App_Requirements §Look and Feel / Main Program GUI | UIR-001 – UIR-015 |
| App_Requirements §Load / Save / Exit | FR-010 – FR-016 |
| App_Requirements §Serial / General (menu) | FR-020, FR-021 |
| App_Requirements / App_Design §Connecting | FR-030 – FR-040 |
| App_Requirements / App_Design §Disconnecting | FR-050 – FR-057 |
| App_Requirements §Host Files / Change Directory | FR-060 – FR-062 |
| App_Requirements / App_Design §Populating remote file list | FR-070 – FR-079 |
| App_Requirements / App_Design §File Transfers | FR-080 – FR-085, FR-082→NFR-003 |
| App_Design §Receiving / Sending data | FR-090 – FR-098 |
| App_Requirements §Main Program GUI (Terminal/Disconnect buttons) | UIR-016, FR-097 |
| App_Requirements §Serial Configuration Dialog | UIR-020 – UIR-031, IFR-002, IFR-003 |
| App_Requirements §General Configuration Dialog | UIR-040 – UIR-048 |
| App_Requirements §Terminal Window | UIR-060 – UIR-067 |
| App_Design §DIR parsing algorithm | DR-001 – DR-032 |
| App_Design §Project Structure / Class Files / Code Quality | CR-001 – CR-009 |
| Deferred / as-built constraints (impl. survey) | CR-010, CR-011, NFR-001 – NFR-003 |
| App_Design §Program state | FR-001 – FR-003 |

---

## 10. Issue Resolution Log

The ambiguities and gaps identified during the initial consolidation (v1.0) were resolved in v1.1 by
inspecting the authoritative implementation under `src/cpm_fm/`. All issues are now closed.

| ID | Issue | Resolution | Evidence | Affected requirements |
|----|-------|------------|----------|-----------------------|
| OI-01 | Whether a separate Disconnect control exists alongside Connect. | **Resolved.** A separate Disconnect button exists and is enabled at startup; Connect does not toggle. Added UIR-016 and updated UIR-013. | `app.py:75` (`btn_disconnect`) | UIR-013, UIR-016, FR-050–FR-057 |
| OI-02 | Behaviour when a status message exceeds 127 characters. | **Resolved.** The application truncates the message to its first 127 characters. Updated UIR-014. | `app.py:105` (`text[:127]`) | UIR-014 |
| OI-03 | When/how the "Change Disk" command is sent. | **Resolved.** The command is stored as `change_disk_cmd` but is not sent in the current baseline; behaviour is deferred. Updated UIR-043 and added CR-011. | No send site in `app.py` | UIR-043, CR-011 |
| OI-04 | NFR-001 lacked a measurable acceptance criterion. | **Resolved.** NFR-001 rewritten with concrete criteria: background daemon thread for reads, per-transfer daemon threads, GUI updates via `self.after(0, ...)`. | `serial_manager.py:_read_loop`; `app.py` transfer threads | NFR-001 |
| OI-05 | X-Modem mode and packet size unconfirmed. | **Resolved.** 128-byte packets, SOH framing, checksum mode (sum mod 256). NFR-003 firmed up. | `xmodem.py:36-38, 63-69` | NFR-003, FR-082 |
| OI-06 | Mapping between parser dictionary and displayed list. | **Resolved.** The dictionary keys are displayed sorted in ascending alphabetical order. Updated FR-078. | `app.py:194` (`sorted(files_dict.keys())`) | FR-077, FR-078, DR-021 |
| OI-07 | Behaviour of the Terminal button independent of Connect. | **Resolved.** The Terminal button opens or restores the Terminal Window without requiring an open port. Added FR-097. | `app.py:87, 126-131` (`show_terminal`) | UIR-013, FR-097 |
| OI-08 | How Transmit Delay settings affect transmission. | **Resolved.** `msec_char`/`msec_line` are stored settings only; they are not applied during transmission in the current baseline. Updated UIR-030/031 and added CR-011. | No use site in `serial_manager.py`/`app.py` | UIR-030, UIR-031, CR-011 |

> During resolution, the implementation also revealed a discrepancy with the original specification:
> App_Requirements specifies Copy to Remote / Copy to Host as *empty stubs*, but the implementation
> provides working X-Modem transfer handlers guarded by the Transport status flag. This is captured in
> the functional requirements FR-080–FR-085 and design constraint CR-010, which now reflect the
> as-built behaviour rather than the stub specification.

---

## 11. Change History

| Version | Date | Author | Description |
|---------|------|--------|-------------|
| 1.0 | 2026-06-06 | Requirements Checker | Initial baseline. Consolidated and restructured all requirements from `docs/App_Requirements.md` and `docs/App_Design.md` into an ISO/IEC/IEEE 29148-conformant SRS. Assigned unique IDs across STR/FR/UIR/IFR/DR/CR/NFR categories (STR-001–003, FR-001–096, UIR-001–067, IFR-001–004, DR-001–032, CR-001–010, NFR-001–003). Added verification methods, priorities, source traceability, a traceability summary (§9), and an open-issues log (§10, OI-01–OI-08). |
| 1.1 | 2026-06-06 | Requirements Checker | Resolved all open issues (OI-01–OI-08) by inspecting the implementation under `src/cpm_fm/`. **Added:** UIR-016 (Disconnect button), FR-097 (Terminal button behaviour), FR-098 (send-with-port-closed status), CR-011 (deferred settings). **Modified:** UIR-013 (added Disconnect to button set), UIR-014 (127-char truncation behaviour), UIR-030/UIR-031 (transmit-delay stored-only note), UIR-043 (Change Disk stored-only note), FR-078 (sorted remote-list display), CR-010 (as-built transfer guarding vs. stub spec), NFR-001 (measurable threading criteria), NFR-002 (key-name normalisation detail), NFR-003 (SOH/checksum X-Modem detail). Converted §10 from an open-issues list to a closed issue-resolution log. Updated §9 traceability. Status advanced from Draft to Reviewed. |
