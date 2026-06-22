# CP/M File Manager — User Manual

**Version 2.12.0**

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
9. [Browsing Files](#9-browsing-files)
10. [Transferring Files](#10-transferring-files)
11. [Managing Files (Rename, Delete, View/Edit)](#11-managing-files-rename-delete-viewedit)
12. [The Terminal Window](#12-the-terminal-window)
13. [Transfer History](#13-transfer-history)
14. [Backup and Restore](#14-backup-and-restore)
15. [Language Support](#15-language-support)
16. [Tips and Troubleshooting](#16-tips-and-troubleshooting)
17. [Reference: Default Settings](#17-reference-default-settings)

---

## 1. Overview

CP/M File Manager bridges the gap between a modern PC and a CP/M machine. Once you connect the two over a serial cable (or USB-to-serial adapter), the program lets you:

- **Browse** files on both the host (your PC) and the remote (CP/M) system side by side.
- **Copy files** in either direction using the X-Modem protocol.
- **Manage** remote files — rename, delete, and view them — using CP/M commands issued for you automatically.
- **Talk directly** to the CP/M system through a built-in serial terminal.
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
- **Help** — About

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
4. **Connect** using the toolbar **Connect** button. Watch the status-bar indicators turn green.
5. **Select a remote drive** (A: – P:) from the dropdown in the Remote pane and click **Update** to list its files.
6. **Transfer files** by selecting them and clicking **Copy to Remote** / **Copy to Host**, or by dragging between panes.
7. **Disconnect** when finished.

---

## 7. Configuration

Settings are stored in JSON configuration files that you create and save to a folder of your choosing. There are two configuration dialogs, both reached from the **Config** menu.

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

> **Terminal Port vs. Transport Port:** The *Terminal Port* carries interactive commands and directory listings; the *Transport Port* carries X-Modem file transfers. They may be the **same** physical port or **two different** ports. When they share one port, the program automatically pauses terminal reading during transfers to keep the data clean.

> **Msec per Char / Msec per Line** add small pacing delays when sending data — useful for slower CP/M systems that can drop characters if fed too fast.

### Config → General

Configure CP/M command templates and behavior:

**Remote command templates** (the `$1`/`$2` placeholders are filled in automatically):

| Setting | Purpose | Default |
|---------|---------|---------|
| **List Files Cmd** | Lists the directory | `DIR` |
| **Recv from Remote** | Tells CP/M to send a file to the PC | `PCPUT $1` |
| **Send to Remote** | Tells CP/M to receive a file from the PC | `PCGET $1` |
| **Rename** | Renames a remote file (`$1` = old, `$2` = new) | `REN $2=$1` |
| **Delete** | Deletes a remote file | `ERA $1` |

**Other settings:**

| Setting | Purpose | Default |
|---------|---------|---------|
| **Transfer Launch Delay** | Seconds to wait after issuing the CP/M command before starting the X-Modem handshake, giving the CP/M program time to start. | 3 |
| **Inter-File Delay** | Seconds to pause between files in a batch, so the CP/M prompt returns before the next command. | 2 |
| **EOL** | Line terminator used when sending text from the Terminal: CR, LF, or CRLF. | CR |
| **Debug Logging** | Writes verbose transfer tracing to standard output. | OFF |
| **Echo Transfer Data** | Shows raw X-Modem bytes as hex tokens (e.g. `<01><06>`) in the Terminal window. | OFF |
| **Viewer Command** | The program used to view/edit a file; `$1` is replaced with the file path. | `notepad $1` |
| **Host Directory** | The host working directory, saved with the configuration. | — |

> **The Save button in each dialog.** The **Save** button in the Serial dialog writes **only the serial settings** to the configuration file you currently have loaded, leaving the general settings in that file untouched. Likewise, the **Save** button in the General dialog writes **only the general settings**, leaving the serial settings untouched. Neither button opens a file picker. If no configuration file is loaded yet, the change is applied to the current session only and a warning reminds you to use **File → Save** to write it to a file. To save *everything* to a file (or to a new file), use **File → Save**.

### File Menu Actions

- **New** — Saves the current configuration, then resets all settings to their defaults and closes any open ports.
- **Load** — Opens a saved JSON configuration. The loaded file's name appears in the title bar, and its host directory (if stored) is restored.
- **Save** — Writes the **entire** current configuration (all serial and general settings) to a JSON file you choose. The saved configuration is remembered and reloaded automatically on the next launch.
- **Exit** — Closes all ports and saves your window geometry and the current configuration name.

---

## 8. Connecting and Disconnecting

Click **Connect** on the toolbar to open the serial port(s):

- The program opens the **Terminal Port** first. On success, the Terminal indicator turns green and the status bar reads "Terminal port open." On failure, an error dialog explains the problem.
- If the **Transport Port** is different from the Terminal Port, it is opened separately. If it is the same physical port, the program simply shares the already-open connection.

Click **Disconnect** to close the port(s). Both indicators turn red, and the remote file listing is cleared.

---

## 9. Browsing Files

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

## 10. Transferring Files

There are several ways to start a transfer:

- Select files and click **Copy to Remote** or **Copy to Host**.
- **Drag and drop** files from one pane to the other.
- **Drag files from your operating system's file manager** onto the Remote pane to upload them.
- Right-click selected files and choose **To Remote** / **To Host**.
- Re-run a previous transfer from the [Transfer History](#13-transfer-history).

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

## 11. Managing Files (Rename, Delete, View/Edit)

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

## 12. The Terminal Window

Open the Terminal from the toolbar **Terminal** button. It is a non-modal window — it stays available in the background and reopens in the same state when you click the button again.

### Layout

- **Receive area** (top) — A read-only, monospaced display of everything received from CP/M, plus optional local echo and transfer byte hex. Line endings are normalized and backspaces are handled.
- **Controls** — **Clear** (empties the buffers and display), **Local Echo** (echoes what you type into the receive area; off by default), and **Autoscroll** (keeps the newest text in view; on by default).
- **Transmit field** (bottom) — Type a command and press **Enter** or click **Send**.

### Sending Control Characters

The transmit field understands **caret notation** for control characters:

- `^C` sends Ctrl+C, `^A` sends Ctrl+A, and so on.
- `^^` sends a literal caret character.
- An empty field sends just the configured end-of-line character (default CR).
- Typing plain text such as `DIR` sends `DIR` followed by the EOL — equivalent to typing `DIR` and pressing Enter on the CP/M console.

A lone control character is sent exactly on its own, without a trailing EOL.

---

## 13. Transfer History

The program records **every transfer attempt** — success, failure, cancellation, or skip — in a persistent history file (`~/.cpm_fm_history.json`). Open it from the toolbar **History** button.

Each entry stores the timestamp, filename, path, direction, status, size, and any error message. History is automatically pruned to a maximum of 500 entries and 30 days.

In the History dialog you can:

- **Filter by direction** — All, Remote (uploads), or Host (downloads).
- **Filter by status** — All, Success, Failure, Cancelled, or Skipped.
- **Re-transfer** — Re-run a previous transfer; it is recorded as a retry.
- **Export** — Save the currently filtered history to a JSON file.
- **Clear** — Erase the entire history, after confirmation.

---

## 14. Backup and Restore

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

## 15. Language Support

The interface is fully translated into **12 languages**: English, Spanish, French, German, Italian, Dutch, Polish, Greek, Mandarin, Cantonese, Korean — and a Pirate Easter egg.

Switch languages at any time via **Config → Language**. The change is applied live: every menu, button, dialog, and indicator is re-translated immediately, and your choice is remembered for future sessions.

---

## 16. Tips and Troubleshooting

- **A transfer never starts / times out.** Make sure the CP/M side launched its X-Modem helper. Increase the **Transfer Launch Delay** if your CP/M program is slow to start.
- **Characters get dropped during terminal use or transfers.** Increase **Msec per Char** and/or **Msec per Line**, or lower the baud rate.
- **The remote drive shows no files or "Drive Not Found."** Confirm you are connected (Terminal indicator green), the drive letter exists on the CP/M system, and the **List Files Cmd** matches your CP/M's directory command.
- **Files fail with name errors on upload.** This is the 8.3 validation step — accept the suggested CP/M-compatible name in the dialog.
- **Sharing one serial port** for both Terminal and Transport is supported; the program pauses terminal reading during transfers automatically.
- **Need to see what's happening on the wire?** Enable **Debug Logging** and/or **Echo Transfer Data** in Config → General, and launch with `python -m cpm_fm` to view the console output.
- **Settings didn't persist.** Use **File → Save** to write your configuration; the saved file is reloaded automatically on the next launch.

---

## 17. Reference: Default Settings

| Setting | Default |
|---------|---------|
| Speed | 115200 baud |
| Data Bits | 8 |
| Parity | NONE |
| Stop Bits | 1 |
| Flow Control | NONE |
| Msec per Char / Line | 0 / 0 |
| List Files Cmd | `DIR` |
| Recv from Remote | `PCPUT $1` |
| Send to Remote | `PCGET $1` |
| Rename | `REN $2=$1` |
| Delete | `ERA $1` |
| Transfer Launch Delay | 3 seconds |
| Inter-File Delay | 2 seconds |
| EOL | CR |
| Debug Logging | OFF |
| Echo Transfer Data | OFF |
| Viewer Command | `notepad $1` |

---

*CP/M File Manager — https://github.com/turbo-gecko/CPM_FM — Licensed under Apache 2.0*
