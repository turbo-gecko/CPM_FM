# CP/M File Manager — User Manual

**Version 2.26.0**

CP/M File Manager (`cpm-fm`) is a cross-platform desktop application for transferring and managing files between a modern host computer and a legacy **CP/M** (Control Program for Microcomputers) system over a serial connection. It uses the **X-Modem** protocol for reliable file transfer and presents a familiar two-pane file-browser interface with drag-and-drop, filtering, sorting, a built-in serial terminal, transfer history, and whole-drive backup/restore.

It works with real vintage CP/M hardware as well as emulators, provided they expose a serial link and run a CP/M-side X-Modem helper (such as `PCGET`/`PCPUT`).

---

## Table of Contents

1. [Overview](#1-overview)
2. [Requirements](#2-requirements)
3. [Installation](#3-installation)
4. [Launching the Program](#4-launching-the-program)
5. [The Main Window](#5-the-main-window)
6. [Getting Started — A Typical Session](#6-getting-started--a-typical-session)
7. [Configuration](#7-configuration)
8. [Connecting and Disconnecting](#8-connecting-and-disconnecting)
9. [Booting the Remote into CP/M](#9-booting-the-remote-into-cpm)
10. [Browsing Files](#10-browsing-files)
11. [Transferring Files](#11-transferring-files)
12. [Managing Files (Rename, Delete, View/Edit)](#12-managing-files-rename-delete-viewedit)
13. [The Terminal Window](#13-the-terminal-window)
14. [Transfer History](#14-transfer-history)
15. [Backup and Restore](#15-backup-and-restore)
16. [Language Support](#16-language-support)
17. [Tips and Troubleshooting](#17-tips-and-troubleshooting)
18. [Reference: Default Settings](#18-reference-default-settings)

---

## 1. Overview

CP/M File Manager bridges the gap between a modern PC and a CP/M machine. Once you connect the two over a serial cable (or USB-to-serial adapter), the program lets you:

- **Browse** files on both the host (your PC) and the remote (CP/M) system side by side.
- **Copy files** in either direction using the X-Modem protocol.
- **Manage** remote files — rename, delete, and view them — using CP/M commands issued for you automatically.
- **Talk directly** to the CP/M system through a built-in serial terminal.
- **Drive a reluctant machine into CP/M** automatically with a configurable boot sequence, for systems that start at a ROM monitor or boot menu rather than booting straight into CP/M.
- **Back up an entire CP/M drive** to your PC, or **restore** files from your PC to a CP/M drive in one operation.
- **Track every transfer** in a persistent, searchable history.

The interface follows a Material Design theme that respects your operating system's light or dark mode.

---

## 2. Requirements

- **Python 3.9 or newer** (if running from source).
- A **serial connection** between your PC and the CP/M system — typically a USB-to-serial adapter and a null-modem or appropriate cable.
- On the CP/M side, an **X-Modem transfer helper**. The defaults assume `PCGET` (to send a file from CP/M to your PC) and `PCPUT` (to receive a file on CP/M). These can be changed in configuration to match your toolset.

**Software dependencies** (installed automatically when you install the package):

- **PySide6** (≥ 6.6) — the Qt GUI framework
- **qt-material** (≥ 2.14) — the Material Design theme
- **pyserial** (≥ 3.5) — serial port access
- **markdown** (≥ 3.5) — renders this manual inside the application

---

## 3. Installation

If you have a packaged executable, simply run it — no installation is required.

To install from source:

```bash
pip install .
```

This makes the `cpm-fm` command available on your system.

---

## 4. Launching the Program

There are two ways to start the application:

- **`cpm-fm`** — Launches the graphical application normally. On Windows, no console window is shown.
- **`python -m cpm_fm`** — Launches the same application but keeps a console window open, which is useful for viewing debug output.

On the first launch, the program starts with built-in default settings. On subsequent launches, it automatically reloads the last configuration you saved, along with the window size, position, and your per-pane filter and sort preferences.

---

## 5. The Main Window

The main window is organized into four areas:

### Menu Bar

- **File** — New, Load, Save, Exit
- **Config** — Serial, General, Language
- **Help** — Manual, About

The **Help → Manual** item opens this user manual in a built-in viewer.

### Toolbar

| Button | Action |
|--------|--------|
| **Connect** | Opens the configured serial port(s). |
| **Disconnect** | Closes the serial port(s). |
| **Terminal** | Shows (or brings to the front) the Terminal window. |
| **History** | Opens the Transfer History dialog. |
| **Backup** | Copies an entire remote drive to the host directory. |
| **Restore** | Copies all host files to the remote drive. |

### Two-Pane File Browser

- **Left pane — Host Files:** files in the current directory on your PC.
- **Right pane — Remote Files:** files on the currently selected CP/M drive.

A draggable splitter sits between the panes so you can resize them.

### Status Bar

- **Left:** the current status message (updates as you work).
- **Right:** two connection indicators — **Terminal** and **Transport**. Each shows a green dot (●) when connected and a red dot (●) when not.

---

## 6. Getting Started — A Typical Session

1. **Configure your serial port(s).** Open **Config → Serial**, select the correct port(s) and matching speed/parity/etc., and click Save to apply them. (On a first run, before you have saved a configuration file, a notice reminds you that these settings apply to this session only until you do **File → Save** in step 3.) (See [Section 7](#7-configuration).)
2. **Set your host working directory.** Open **Config → General** and choose a Host Directory, or use the **Change Directory** button in the Host pane later.
3. **Save your configuration** via **File → Save** so it reloads automatically next time.
4. **Connect** using the toolbar **Connect** button. Watch the status-bar indicators turn green. The program then checks that the remote is at the CP/M prompt and, if so, automatically selects the current drive and lists its files (see [Section 8](#8-connecting-and-disconnecting)).
5. **Select a remote drive** (A: – P:) from the dropdown in the Remote pane and click **Update** to list its files.
6. **Transfer files** by selecting them and clicking **Copy to Remote** / **Copy to Host**, or by dragging between panes.
7. **Disconnect** when finished.

---

## 7. Configuration

Settings are stored in JSON configuration files that you create and save to a folder of your choosing. There are three configuration dialogs — **Serial**, **Terminal**, and **General** — all reached from the **Config** menu.

### Config → Serial

Configure how the program talks to the serial hardware:

| Field | Options | Default |
|-------|---------|---------|
| **Terminal Port** | Auto-detected ports | — |
| **Transport Port** | Auto-detected ports | — |
| **Speed** | 300 – 921600 baud | 115200 |
| **Data Bits** | 7 or 8 | 8 |
| **Parity** | NONE, ODD, EVEN, MARK, SPACE | NONE |
| **Stop Bits** | 1 or 2 | 1 |
| **Flow Control** | NONE, XON/XOFF, RTS/CTS, DSR/DTR | NONE |
| **Msec per Char** | 0 – 255 | 0 |
| **Msec per Line** | 0 – 255 | 0 |
| **Terminal Timeout (ms)** | 10 – 5000 | 100 |
| **Transfer Timeout (ms)** | 10 – 5000 | 100 |

> **Terminal Port vs. Transport Port:** The *Terminal Port* carries interactive commands and directory listings; the *Transport Port* carries X-Modem file transfers. They may be the **same** physical port or **two different** ports. When they share one port, the program automatically pauses terminal reading during transfers to keep the data clean.

> **Msec per Char / Msec per Line** add small pacing delays when sending data — useful for slower CP/M systems that can drop characters if fed too fast.

> **Terminal Timeout / Transfer Timeout** set the serial read timeout (in milliseconds) for each port. The default is **100 ms**. When using **XMODEM 1K** transfers, it is recommended to increase these to **1000 ms** to improve reliability, as the larger 1024-byte blocks take longer to arrive than the default timeout allows for in a single read.

### Config → Terminal

Configure the Terminal Window and its macro buttons. The dialog has two tabs.

**Terminal tab:**

| Field | Options | Default |
|-------|---------|---------|
| **Terminal Type** | VT100, VT52, ADM-3A | VT100 |
| **Local Echo** | On / Off | Off |
| **Autoscroll** | On / Off | On |

> **Terminal Type** selects the terminal emulation the Terminal Window uses to interpret the remote's output and to encode the cursor keys you type. The default **VT100** is a VT-100/ANSI terminal. Choose **VT52** for software written for a DEC VT-52, or **ADM-3A** for the classic Lear Siegler ADM-3A that much CP/M software (WordStar, Turbo Pascal, etc.) targets. VT-52 and ADM-3A output is translated into the same on-screen VT-100 model, so cursor positioning, screen clearing, and (for VT-52) line-drawing all work; the ADM-3A has no colour or text attributes. A change takes effect immediately in an open Terminal Window. (You can also switch the type on the fly from the Terminal Window's right-click menu — see [Section 13](#13-the-terminal-window).)

> **Local Echo** shows what you type in the Terminal Window on screen. Leave it **Off** when the remote already echoes your keystrokes (the usual case); turn it **On** if what you type does not appear.

> **Autoscroll** keeps the newest output visible as it arrives. Leave it **On** for normal use; turn it **Off** to stop the view jumping to the bottom while you scroll back through earlier output.

**Macros tab:**

Program the ten macro buttons offered by the Terminal Window's right-click **Macros** submenu. The tab has one inner **tab per button**, **Button 1** through **Button 10**; select a tab to edit that button. Each tab has:

- **Label** — the caption shown for the macro (up to 30 characters). A slot is offered only when it has both a label and a keystroke sequence.
- **Keystrokes** — a short script in the same directive language as the boot sequence (`SEND`, `SENDRAW`, `WAIT`, `WAITFOR` — see [Section 9](#9-booting-the-remote-into-cpm)). For example, `SEND DIR` sends `DIR` followed by the end-of-line; `SENDRAW 03` sends a raw Ctrl-C.
- **Test** — sends the slot's currently entered script (even before saving) to the remote so you can check it. This requires the Terminal Port to be open.

Like the other config dialogs, **Save** writes only the terminal and macro settings to the loaded configuration file (applying them immediately to a running Terminal Window); with no file loaded the change applies to the session only.

### Config → General

Configure CP/M command templates and behavior. The remote-command fields are gathered into a **Remote** group at the top; the remaining settings follow below it.

**Remote command templates** (the `$1`/`$2` placeholders are filled in automatically):

| Setting | Purpose | Default |
|---------|---------|---------|
| **List Files Cmd** | Lists the directory | `DIR` |
| **Recv from Remote** | Tells CP/M to send a file to the PC | `PCPUT $1` |
| **Send to Remote** | Tells CP/M to receive a file from the PC | `PCGET $1` |
| **Use XMODEM-1K** | Send host→remote transfers as 1024-byte blocks | OFF |
| **Recv from Remote (1K)** | The 1K-mode receive command (blank = use the standard one) | *(blank)* |
| **Send to Remote (1K)** | The 1K-mode send command (blank = use the standard one) | *(blank)* |
| **Rename** | Renames a remote file (`$1` = old, `$2` = new) | `REN $2=$1` |
| **Delete** | Deletes a remote file | `ERA $1` |

> **XMODEM-1K.** When **Use XMODEM-1K** is ON, host→remote transfers use 1024-byte STX frames instead of the standard 128-byte frames, which is faster over a reliable link. If your CP/M helper needs a different command for 1K mode, set it in the **(1K)** fields; a blank 1K field falls back to its standard counterpart. When enabling 1K mode, also raise the **Transfer Timeout** (see Config → Serial) — 1000 ms is a good starting point.

> **Test button.** A **Test** button sits beside the Recv from Remote and Send to Remote fields. It requires an active connection, and sends the field's currently entered command (even if not yet saved) exactly as a real transfer would, then reports whether the remote answered within the Transfer Handshake Timeout — without transferring any file. Use it while working out a command's exact syntax, before running a real transfer.

**Other settings:**

| Setting | Purpose | Default |
|---------|---------|---------|
| **Transfer Launch Delay** | Seconds to wait after issuing the CP/M command before starting the X-Modem handshake, giving the CP/M program time to start. | 3 |
| **Transfer Handshake Timeout** | Seconds to wait for the remote's first response after the launch delay before treating the transfer as a misconfigured command (see [Section 17](#17-tips-and-troubleshooting)). | 10 |
| **Inter-File Delay** | Seconds to pause between files in a batch, so the CP/M prompt returns before the next command. | 2 |
| **EOL** | Line terminator used when sending text from the Terminal and the boot sequence: CR, LF, or CRLF. | CR |
| **Debug Logging** | Writes verbose transfer tracing to standard output. | OFF |
| **Echo Transfer Data** | Shows raw X-Modem bytes as hex tokens (e.g. `<01><06>`) in the Terminal window. | OFF |
| **Viewer Command** | The program used to view/edit a file; `$1` is replaced with the file path. | `notepad $1` |
| **Host Directory** | The host working directory, saved with the configuration. | — |
| **Boot Sequence** | An optional script of keystrokes that drives the remote into CP/M when it does not boot there on its own. See [Section 9](#9-booting-the-remote-into-cpm). | *(blank)* |

> **The Save button in each dialog.** The **Save** button in the Serial dialog writes **only the serial settings** to the configuration file you currently have loaded, leaving the other settings in that file untouched. The **Terminal** dialog likewise writes only the terminal and macro settings, and the **General** dialog writes only the general settings. No button opens a file picker. If no configuration file is loaded yet, the change is applied to the current session only and a warning reminds you to use **File → Save** to write it to a file. To save *everything* to a file (or to a new file), use **File → Save**.

### File Menu Actions

- **New** — Saves the current configuration, then resets all settings to their defaults and closes any open ports.
- **Load** — Opens a saved JSON configuration. The loaded file's name appears in the title bar, and its host directory (if stored) is restored.
- **Save** — Writes the **entire** current configuration (all serial and general settings) to a JSON file you choose. The saved configuration is remembered and reloaded automatically on the next launch.
- **Exit** — Closes all ports and saves your window geometry and the current configuration name. It also remembers which of the **Terminal Window** and **Transfer History** window were open and reopens them on the next launch.

---

## 8. Connecting and Disconnecting

Click **Connect** on the toolbar to open the serial port(s):

- The program opens the **Terminal Port** first. On success, the Terminal indicator turns green and the status bar reads "Terminal port open." On failure, an error dialog explains the problem.
- If the **Transport Port** is different from the Terminal Port, it is opened separately. If it is the same physical port, the program simply shares the already-open connection.
- If the Terminal Port is already open, pressing **Connect** again does nothing further — the status bar reads "Terminal port is already open."

### Checking the remote file system

Once both ports are open, the program automatically checks whether the remote is ready at the CP/M command prompt. It sends an end-of-line and looks for a CP/M **drive prompt** (such as `A>`, and ZCPR/NZCOM-style prompts like `A0>` are also recognized). The status bar briefly shows "Checking remote file system."

- **If a prompt is found**, the drive dropdown in the Remote pane is set to the remote's current drive and its files are listed for you — no need to press **Update** manually.
- **If no prompt is found**, the program sends one more end-of-line and checks again.
- **If there is still no prompt**, the program either runs your **boot sequence** (if one is configured — see [Section 9](#9-booting-the-remote-into-cpm)) and checks one more time, or — if no boot sequence is configured, or the remote still does not respond — shows the **Remote Filesystem Unavailable** dialog with three choices:
  - **Abort** — Close the port(s) (as **Disconnect** does) and clear the remote list.
  - **Continue** — Leave the port(s) open and take no further action.
  - **Terminal** — Open the Terminal window so you can interact with the remote directly to diagnose the problem.

### Disconnecting

Click **Disconnect** to close the port(s). Both indicators turn red, and the remote file listing is cleared.

---

## 9. Booting the Remote into CP/M

Some machines do not boot straight into CP/M — they may stop at a ROM monitor, a boot menu, or wait for a keypress. The **boot sequence** lets you record the keystrokes needed to drive such a machine into CP/M so you do not have to type them by hand every time.

You write the sequence as a short script in **Config → General → Boot Sequence**. It is empty by default, which leaves the feature switched off.

### When the boot sequence runs

The boot sequence is run **only when it is needed**, never against a machine that is already at the CP/M prompt:

- **Automatically on Connect.** If the post-connect check (see [Section 8](#8-connecting-and-disconnecting)) finds no CP/M drive prompt and a boot sequence is configured, the program runs the sequence and then checks once more. If CP/M is now responding, it continues normally; only if it still does not respond is the *Remote Filesystem Unavailable* dialog shown.
- **Manually.** The Terminal window has a **Boot into CP/M** button (see [Section 13](#13-the-terminal-window)) that runs the sequence on demand and then re-checks for the CP/M prompt. The button is disabled (greyed out) whenever the boot sequence is empty, and becomes enabled as soon as you save a sequence.

Because the automatic run happens **only** when the remote is *not* already at CP/M, restarting the application while the machine stays powered on (and therefore still in CP/M) will not send any unwanted keystrokes.

### Script format

The script has one instruction (a *directive*) per line:

- Blank lines are ignored.
- A line whose first non-blank character is `#` is a comment and is ignored.
- The directive keyword is **not** case-sensitive (`SEND`, `send`, and `Send` are equivalent).
- Directives run from top to bottom, in order.

If a line cannot be understood (an unknown keyword, an invalid hexadecimal byte, or a non-numeric delay), the sequence stops and the status bar reports the problem.

### Directives

| Directive | What it does |
|-----------|--------------|
| `SEND <text>` | Sends `<text>` followed by the configured end-of-line (the **EOL** setting in Config → General). This is the equivalent of typing the text and pressing Enter. `SEND` on its own (no text) sends just the end-of-line — a bare Enter. |
| `SENDRAW <hh> [hh …]` | Sends one or more raw bytes given as two-digit hexadecimal values, separated by spaces, with **no** end-of-line added. Use this for control keys and other non-printing characters. |
| `WAIT <seconds>` | Pauses for the given number of seconds before the next directive. Decimals are allowed (e.g. `WAIT 0.5`). |
| `WAITFOR <text> [seconds]` | Watches the incoming serial data and waits until `<text>` appears, or until the optional timeout (in seconds) elapses — whichever comes first. If no timeout is given, it waits up to **10 seconds**. Use this to synchronize with a prompt the machine prints. |

#### `SEND` — type a line

`SEND` transmits text exactly as typed, then appends the end-of-line character(s) chosen by the **EOL** setting (CR by default). For example, to type the CP/M boot command at a monitor:

```
SEND CPM
```

A bare `SEND` (with nothing after it) sends only the end-of-line, which is handy for "press Enter to continue" prompts.

#### `SENDRAW` — send control keys and raw bytes

`SENDRAW` sends the listed bytes verbatim, with nothing added. Each byte is written as two hexadecimal digits. Common values:

| Hex | Key / byte |
|-----|------------|
| `03` | Ctrl-C (interrupt / abort auto-boot) |
| `0D` | Carriage Return (Enter) |
| `0A` | Line Feed |
| `1B` | ESC (Escape) |
| `20` | Space |
| `01`–`1A` | Ctrl-A … Ctrl-Z |

For example, to press **ESC** then **Enter**:

```
SENDRAW 1B 0D
```

#### `WAIT` — pause

`WAIT` simply waits. Use it to give a monitor or boot ROM time to react before sending the next keystroke:

```
SEND
WAIT 1.5
SEND CPM
```

#### `WAITFOR` — wait for a prompt

`WAITFOR` is more reliable than a fixed `WAIT` when you know what text the machine prints. It watches the incoming data until the text appears (a substring match) or the timeout runs out:

```
WAITFOR Monitor>
```

You can give an explicit timeout in seconds as the last word:

```
WAITFOR Monitor> 5
```

The text being waited for may itself contain spaces — the program treats the final word as a timeout only when it is a number.

### Examples

**A monitor that needs Enter, then `C` to cold-boot CP/M:**

```
# Wake the monitor, then cold-boot CP/M
WAITFOR Monitor> 5
SEND C
WAITFOR A> 10
```

**Interrupt an auto-boot with Ctrl-C, then launch CP/M:**

```
SENDRAW 03        # Ctrl-C to stop the auto-boot countdown
WAIT 1
SEND CPM          # type the command that starts CP/M
```

**Simplest case — just nudge it with a couple of returns:**

```
SEND
WAIT 0.5
SEND
```

> **Tip:** Build your sequence interactively first. Open the Terminal window, perform the boot keystrokes by hand, and note exactly what the machine prints and what you type. Then translate each step into `SEND` / `SENDRAW` / `WAIT` / `WAITFOR` lines, using `WAITFOR` against the prompts you saw for the most reliable result.

---

## 10. Browsing Files

Each pane has its own controls for navigating, filtering, and sorting.

### Host Files Pane

- **Change Directory** — Browse to a different folder on your PC.
- **Update** — Refresh the file list.
- **Filter field** — Type to narrow the list (supports wildcards and substring matching). The field shows a colored border while a filter is active; click the **X** to clear it.
- **Sort dropdown** — Sort by **Name** or **Extension**.
- **Sort direction** — Toggle ascending (↑) / descending (↓).
- **Copy to Remote** — Transfer the selected files to the CP/M system.

### Remote Files Pane

- **Drive dropdown** — Choose a CP/M drive, **A:** through **P:**. Selecting a drive switches to it; if the drive doesn't respond, a "Drive Not Found" dialog appears.
- **Update** — Refresh the remote file list (issues the List Files command and parses the output).
- **Filter / Sort** — Same controls as the Host pane.
- **Copy to Host** — Download the selected files from CP/M.

**Selection:** Use Ctrl+click and Shift+click to select multiple files in either pane.

**Persistence:** Each pane remembers its filter text, sort field, and sort direction between sessions.

---

## 11. Transferring Files

There are several ways to start a transfer:

- Select files and click **Copy to Remote** or **Copy to Host**.
- **Drag and drop** files from one pane to the other.
- **Drag files from your operating system's file manager** onto the Remote pane to upload them.
- Right-click selected files and choose **To Remote** / **To Host**.
- Re-run a previous transfer from the [Transfer History](#14-transfer-history).

### The Transfer Progress Dialog

During a transfer, a dialog shows:

- The current filename.
- Blocks transferred and bytes completed.
- A batch position label (e.g. "File 3 of 10") for multi-file transfers.
- A progress bar — determinate for uploads (size is known), indeterminate for downloads (X-Modem does not report file length).
- A **Cancel** button to abort. After you click it, the button shows "Cancelling…" while the current operation stops cleanly.

### File Conflicts

If a file with the same name already exists at the destination, a dialog offers:

- **Overwrite** — Replace the existing file.
- **Skip** — Leave the existing file and move on.
- **Cancel** — Stop the whole batch.

Tick **Apply to all** to use your choice for every remaining conflict in the batch.

### CP/M Filename Validation (8.3)

CP/M filenames must follow the **8.3 convention**: a base name of 1–8 characters and an optional extension of up to 3 characters, with no spaces or reserved characters. When you upload a host file whose name doesn't conform, a dialog appears with a suggested valid name already filled in. You can:

- **Rename** — Accept or edit the suggested CP/M-compatible name (it is re-validated before being accepted).
- **Skip** — Skip this file.
- **Cancel** — Stop the batch.

---

## 12. Managing Files (Rename, Delete, View/Edit)

Right-click files in either pane for a context menu.

### Host Files (right-click)

- **To Remote** — Upload the selected file(s).
- **View/Edit** — Open a single file in the configured viewer/editor.
- **Rename** — Rename the file on your PC.
- **Delete** — Delete the selected file(s), after confirmation.

### Remote Files (right-click)

- **To Host** — Download the selected file(s).
- **View** — Download a single file to a temporary folder and open it in the viewer.
- **Rename** — Rename the file on CP/M using the configured Rename command.
- **Delete** — Delete the selected file(s) on CP/M using the configured Delete command, after confirmation.

> Remote rename and delete require an active Terminal connection, because they work by sending CP/M commands.

The rename and delete dialogs follow a consistent layout: **Cancel** on the left, the affirmative action (**Apply**) on the right.

---

## 13. The Terminal Window

Open the Terminal from the toolbar **Terminal** button. It is a non-modal window — it stays available in the background and reopens in the same state when you click the button again. If the Terminal Window is open when you exit the app, it is **reopened automatically** the next time you start (see [Section 7](#7-configuration), *Exit*).

The Terminal is a **functional VT-100 terminal**: it interprets the VT-100/ANSI escape sequences CP/M software emits (cursor positioning, screen and line erase, colour and text attributes, scrolling), so full-screen programs such as editors display correctly rather than as raw escape codes.

### Layout

- **Receive area** — A monospaced character-cell screen (80 × 24 initially) rendering the live terminal display, with at least 1000 lines of scrollback. It shows everything received from CP/M, plus optional local echo and transfer byte hex. This is also where you type (see below). The screen **reflows to the window size** — make the window larger or smaller and the number of visible columns and rows follows it. (Note: the remote is not told the new size, so a full-screen CP/M program that assumes an 80 × 24 screen still draws to that 80 × 24 area.)
- **Status bar** (bottom) — Shows the terminal emulation currently in use, e.g. `Emulation: VT100`. It updates immediately when you change the type from the right-click **Terminal Type** submenu or in **Config → Terminal**. (There is no separate text field — you type directly into the terminal.)

The window has **no buttons or checkboxes** — every terminal action is on the **right-click menu** (below). **Local Echo** and **Autoscroll** are set in **Config → Terminal** (see [Section 7](#7-configuration)), and the macro buttons are programmed on that dialog's **Macros** tab.

### The right-click menu

**Right-click** anywhere in the Receive area for a context menu:

- **Copy** — copies the currently highlighted text to the clipboard. To highlight, press and drag the left mouse button across the screen; trailing spaces are trimmed from each line. Copy is greyed out when nothing is selected.
- **Paste** — sends the clipboard's text to the CP/M system as if you had typed it. Line breaks in the pasted text are sent as the configured end-of-line character(s). (As with typing, the Terminal Port must be open, or the status bar reports that it cannot send.)
- **Clear Window** — resets the screen and empties the buffers.
- **Font…** — opens your system's standard font-selection dialog, where you can choose the family, style, and size used to draw the Receive area. The new font is applied straight away — the character grid reflows to the new character size — and is **remembered across sessions**, independently of which configuration file is loaded. The default is a monospaced **Courier New**; a monospaced font is recommended so full-screen CP/M programs line up correctly.
- **Reset Size (24×80)** — resizes the window so the character grid returns to the classic 80 columns × 24 rows.
- **Boot into CP/M** — runs the configured boot sequence (see [Section 9](#9-booting-the-remote-into-cpm)). It is greyed out until you configure a boot sequence in Config → General.
- **Terminal Type** (submenu) — lists **VT100**, **VT52**, and **ADM-3A** with the active type ticked. Choosing one switches the terminal emulation straight away — exactly like the **Terminal Type** dropdown in Config → Terminal (see [Section 7](#7-configuration)). The choice is kept with the rest of the terminal settings and saved next time you save the configuration.
- **Macros** (submenu) — lists your configured macro buttons by label. Choosing one runs that macro's keystrokes on the CP/M system. If no macros are configured the submenu is greyed out. You program the macros on the **Macros** tab of **Config → Terminal** (see [Section 7](#7-configuration)); each uses the same script directives as the boot sequence (`SEND`, `SENDRAW`, `WAIT`, `WAITFOR`), and running one requires the Terminal Port to be open.

### Typing to the Remote

Click into the receive area to give it focus, then type — **each keystroke is sent to the CP/M system immediately**, exactly like a real terminal. There is no separate transmit field or Send button.

- **Printable characters** are sent as you type them.
- **Enter** sends the configured end-of-line character(s) (default CR).
- **Backspace, Tab, and Escape** send their control codes; the **arrow, Home/End, Page Up/Down, Insert, Delete, and function keys** send their VT-100 sequences.
- **Ctrl-key combinations** send control characters — e.g. **Ctrl+C** sends Ctrl+C, **Ctrl+[** sends Escape.

> Because keystrokes go straight to the port, there is no line editing on the host side; editing (e.g. rubout) is handled by the CP/M program you are talking to.

---

## 14. Transfer History

The program records **every transfer attempt** — success, failure, cancellation, or skip — in a persistent history file (`~/.cpm_fm_history.json`). Open it from the toolbar **History** button. The History window is **non-modal**, so you can leave it open beside the main window and the Terminal; clicking **History** again simply brings the open window to the front. If it is open when you exit, it reopens on the next launch (see [Section 7](#7-configuration), *Exit*).

Each entry stores the timestamp, filename, path, direction, status, size, and any error message. History is automatically pruned to a maximum of 500 entries and 30 days.

In the History window you can:

- **Filter by direction** — All, Remote (uploads), or Host (downloads).
- **Filter by status** — All, Success, Failure, Cancelled, or Skipped.
- **Re-transfer** — Re-run a previous transfer; it is recorded as a retry.
- **Export** — Save the currently filtered history to a JSON file.
- **Clear** — Erase the entire history, after confirmation.

---

## 15. Backup and Restore

These operations move an entire drive's worth of files in one step. **Both are destructive at the destination** and require confirmation.

### Backup (Remote → Host)

1. Click **Backup** on the toolbar.
2. The program refreshes both file lists, then warns: *all files in the host directory will be deleted and replaced.* Cancel is the safe default.
3. On confirmation, it deletes the existing host files and downloads every file from the selected remote drive, with full progress and history tracking.

### Restore (Host → Remote)

1. Click **Restore** on the toolbar.
2. The program snapshots the host files and refreshes the remote list, then warns: *all files on the remote drive will be deleted and replaced.* Cancel is the safe default.
3. On confirmation, it deletes every remote file (using the Delete command) and uploads every host file, with CP/M filename validation, conflict handling, progress, and history tracking active.

> Because these operations delete files at the destination, double-check your host directory and selected remote drive before confirming.

---

## 16. Language Support

The interface is fully translated into **12 languages**: English, Spanish, French, German, Italian, Dutch, Polish, Greek, Mandarin, Cantonese, Korean — and a Pirate Easter egg.

Switch languages at any time via **Config → Language**. The change is applied live: every menu, button, dialog, and indicator is re-translated immediately, and your choice is remembered for future sessions.

---

## 17. Tips and Troubleshooting

- **A transfer never starts / times out.** Make sure the CP/M side launched its X-Modem helper. Increase the **Transfer Launch Delay** if your CP/M program is slow to start. If the remote never responds at all, the program now reports "No response from remote… check the Send to Remote / Receive from Remote command" instead of a generic failure — use the **Test** button beside those fields (Config → General) to check a command without running a real transfer.
- **The machine doesn't reach CP/M when you connect.** If it sits at a ROM monitor or boot menu, set up a **Boot Sequence** (see [Section 9](#9-booting-the-remote-into-cpm)); the program will run it automatically when the connect check finds no CP/M prompt, or you can run it on demand with the Terminal window's **Boot into CP/M** button.
- **Characters get dropped during terminal use or transfers.** Increase **Msec per Char** and/or **Msec per Line**, or lower the baud rate.
- **XMODEM-1K transfers are unreliable.** Raise the **Transfer Timeout** (try 1000 ms) so each larger 1024-byte block has time to arrive.
- **The remote drive shows no files or "Drive Not Found."** Confirm you are connected (Terminal indicator green), the drive letter exists on the CP/M system, and the **List Files Cmd** matches your CP/M's directory command.
- **Files fail with name errors on upload.** This is the 8.3 validation step — accept the suggested CP/M-compatible name in the dialog.
- **Sharing one serial port** for both Terminal and Transport is supported; the program pauses terminal reading during transfers automatically.
- **Need to see what's happening on the wire?** Enable **Debug Logging** and/or **Echo Transfer Data** in Config → General, and launch with `python -m cpm_fm` to view the console output.
- **Settings didn't persist.** Use **File → Save** to write your configuration; the saved file is reloaded automatically on the next launch.

---

## 18. Reference: Default Settings

| Setting | Default |
|---------|---------|
| Speed | 115200 baud |
| Data Bits | 8 |
| Parity | NONE |
| Stop Bits | 1 |
| Flow Control | NONE |
| Terminal Type | VT100 |
| Local Echo | OFF |
| Autoscroll | ON |
| Msec per Char / Line | 0 / 0 |
| Terminal / Transfer Timeout | 100 ms / 100 ms |
| List Files Cmd | `DIR` |
| Recv from Remote | `PCPUT $1` |
| Send to Remote | `PCGET $1` |
| Use XMODEM-1K | OFF |
| Recv / Send from Remote (1K) | *(blank)* |
| Rename | `REN $2=$1` |
| Delete | `ERA $1` |
| Transfer Launch Delay | 3 seconds |
| Transfer Handshake Timeout | 10 seconds |
| Inter-File Delay | 2 seconds |
| EOL | CR |
| Debug Logging | OFF |
| Echo Transfer Data | OFF |
| Viewer Command | `notepad $1` |
| Boot Sequence | *(blank)* |
| Macro Buttons (Label + Keystrokes, ×10) | *(blank)* |
| Terminal Font | Courier New (monospaced) |

---

*CP/M File Manager — https://github.com/turbo-gecko/CPM_FM — Licensed under Apache 2.0*
