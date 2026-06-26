# AGENTS.md

This file provides guidance to AI agents when working with code in this repository.

## What this is

`cpm-fm` is a **PySide6 (Qt for Python)** desktop app that transfers files between a modern host and
legacy [CP/M](https://en.wikipedia.org/wiki/CP/M) systems over a serial link using X-Modem. Beyond
single/multi-file transfers it offers drag-and-drop, file-conflict resolution, CP/M 8.3 filename
validation, a persistent transfer history, whole-drive backup/restore, and a 12-language UI. The GUI
applies a Material Design theme via the `qt-material` package (set centrally at start-up in
`gui/theme.py`; the light/dark variant follows the host OS — UIR-070/UIR-073). As of v1.3 the UI was
migrated from Tkinter to PySide6; there is no remaining `tkinter` code, and the stray `wxPython` in
`.venv` is unused (ignore it). The current version is in `src/version.txt`.

## Commands

Install (editable, with dev tools): `python -m pip install -e .[dev]`

Run:
- `cpm-fm` — installed GUI launcher (bound to `pythonw.exe`, no console window on Windows)
- `python -m cpm_fm` — equivalent, keeps a console for `print()` debug output (serial errors are
  printed to stdout, not surfaced in the UI)

Test / lint / type-check (CI runs all of these on Python 3.12, see `.github/workflows/ci.yml`):
- `pytest` — full suite (`-q` is set in `pyproject.toml`)
- `pytest tests/test_cpm_parser.py::test_parse_dir_output_extracts_filenames` — single test
- `ruff check src tests` and `ruff format --check src tests` (CI uses `--check`; drop it to apply)
- `mypy src`

## Architecture

`src/`-layout package under `src/cpm_fm/`. `app.py:MainWindow` (a `QMainWindow` subclass) is the hub
that owns all components and wires UI events to them. `main()` creates the `QApplication`, applies the
theme, shows the window, and runs `app.exec()`; it is the entry point for both launchers.

Three layers, intentionally decoupled from the GUI so they are unit-testable without a running Qt app
(CR-014 forbids GUI-toolkit imports in `terminal/` and `utils/`):
- `terminal/serial_manager.py` — `SerialManager` owns two `pyserial` ports: a **terminal** port (for
  CP/M commands) and a **transport** port (for X-Modem transfers). They may be the same physical port.
  A background daemon thread (`_read_loop`) polls the terminal port and pushes received text to the
  `on_data_received` callback.
- `terminal/xmodem.py` — `XModem` is a hand-rolled X-Modem implementation (128-byte SOH-framed
  packets, supporting both **checksum** and **CRC** modes selected by the receiver-driven handshake;
  receive also accepts STX/1024-byte XMODEM-1K frames). `send_file`/`receive_file` are blocking and
  run on worker threads.
- `terminal/cpm_parser.py` — `CPMParser.parse_dir_output` is a pure static method that scrapes
  filenames from CP/M 2.2 four-column `DIR` text output. This is the most-tested logic.
- `utils/config_handler.py` — `ConfigHandler` loads/saves settings as JSON.
- `utils/i18n.py` — process-wide internationalisation singleton: `tr(key, ...)` resolves a placeholder
  key to text in the active language, `set_language` switches it. Strings live in `lang/lang_<language>.txt`
  (`key = value`, UTF-8); `lang_english.txt` is the complete reference/fallback (FR-121, FR-124, DR-042/043).
- `utils/file_filter.py` — pure wildcard/substring filtering and sorting used by both file panes.
- `utils/transfer_history.py` — `TransferHistory`, a GUI-free, thread-safe JSON persistence layer
  (default `~/.cpm_fm_history.json`) recording one entry per transfer *attempt* with retention pruning
  (FR-140–FR-142, DR-045). Distinct from the raw serial `_rx_buffer`/`_tx_buffer` in `app.py`.
- `gui/` — Qt-only widgets/dialogs:
  - `theme.py` (`apply_theme`, the central `qt-material` setup).
  - `terminal_window.py` (`TerminalWindow`, a non-modal `QMainWindow` serial console).
  - `config_dialogs.py` (`ConfigDialog` base `QDialog` + `SerialConfigDialog`/`GeneralConfigDialog`,
    which build `QFormLayout` forms from declarative field lists).
  - `file_list_widget.py` — the per-pane file list widget (`FileListWidget(QListWidget)`) that adds
    drag-and-drop source/target behaviour; filter/sort is handled in `app.py` + `utils/file_filter.py`.
  - `transfer_dialog.py` — modal per-batch transfer-progress dialog with a Cancel button.
  - `conflict_dialog.py` — destination-exists prompt (Overwrite/Skip/Cancel, apply-to-rest).
  - `filename_validation_dialog.py` — CP/M 8.3 rename/skip/cancel prompt on upload.
  - `transfer_history_dialog.py` — review/filter/export/clear/re-transfer from `TransferHistory`.
  - `file_action_dialog.py`, `about_dialog.py`, `dialog_buttons.py` (shared button helpers),
    `window_state.py` (`WindowState`: QSettings-backed window geometry + last-used config dir/file).

### Key cross-cutting behaviors

- **Threading model:** Serial reads, and both transfer directions, run off the Qt GUI thread (daemon
  threads). Any UI update from those threads must be marshalled onto the GUI thread by **emitting a Qt
  signal** — never touch a widget directly from a worker thread (NFR-004). `MainWindow` declares a set
  of these signals (see the `Signal(...)` declarations at the top of the class). Most just push
  status/progress to the UI; three — `conflict_detected`, `invalid_name_detected`,
  `backup_restore_confirm` — drive a **modal prompt on the GUI thread while the worker thread blocks**
  awaiting the user's decision. Follow this signal pattern for new background work, or Qt will
  crash/misbehave.
- **Remote file listing is capture-based, not request/response:** `_capture_terminal_response`
  sets a `_capture_active` flag, sends the command, waits 1 s for output to begin accumulating in
  `_remote_capture_buffer` via the read callback, then polls every 0.5 s and stops once the buffer
  has not grown within an idle window (max total wait 10 s). `_do_refresh_remote_logic` calls this
  for the `DIR` command and then parses the captured text.
- **Two config JSON formats coexist** and both must keep working:
  - *Flat* (what the dialogs read/write; every file in `examples/`, e.g. `RC2014_Z_Pro.json`):
    `terminal_port`, `transport_port`, `speed`, `data`, `parity`, `stopbits`, `flow`, `msec_char`,
    `msec_line`.
  - *Nested* (legacy/alternative shape still accepted; no example currently shipped):
    `{"serial": {...}, "general": {...}}` with variant key names (`transfer_port`, `data_bits`,
    `stop_bits`, ...).
  `SerialManager.open_port` and `ConfigHandler.validate_serial_settings` defensively normalize both
  (unwrap a `serial` sub-dict, fall back across key-name variants). When touching settings handling,
  preserve compatibility with both shapes.
- The app **starts unconfigured** (`self.settings = {}`); settings come from File > Load or the
  Config dialogs. `eol` setting maps `CR`/`LF`/`CRLF` to terminator chars in `app.py`.
- **Three separate persistence stores, deliberately not merged:** the per-configuration serial/general
  JSON (`ConfigHandler`), the QSettings-backed UI/session state (`WindowState` — window geometry,
  last-used config dir/file), and the transfer-history JSON (`TransferHistory`). Keep them distinct.
- **Whole-drive Backup/Restore** (`app.py:_backup_drive`/`_restore_drive`, FR-150–FR-154, UIR-086–088):
  mirror every file between the remote drive and the host directory. Each refreshes the destination,
  emits `backup_restore_confirm` for a modal "all destination files will be deleted" warning (Cancel is
  the default), then wipes and re-copies via the normal batch transfer path.
- **GUI strings are never hard-coded** — route every user-facing string through `i18n.tr(key)` and add
  the key to **all** `lang/lang_*.txt` files (English is mandatory; missing keys fall back to English).

## Design docs and workflows

`docs/cpm_fm_requirements.md` is the **authoritative requirements specification** going forward — an
ISO/IEC/IEEE 29148 SRS with uniquely identified, traceable requirements (`FR-`/`UIR-`/`DR-`/`CR-`/
`NFR-` etc.). Cite requirement IDs when referencing behavior. `docs/legacy/App_Requirements.md` and
`docs/legacy/App_Design.md` are the original source documents it was consolidated from; they are
**archived** for history but are **superseded** where they conflict (e.g. they call Copy to Remote/Host
empty stubs, but the SRS and code implement working X-Modem transfers — see `FR-080`–`FR-085`,
`CR-010`).
The SRS's §10 **Issue Resolution Log** and §11 **Change History** live in companion files
(`docs/requirements_issue_log.md`, `docs/requirements_change_history.md`) to keep the spec small; the
SRS keeps a one-line stub pointing to each. Both are historical/append-only — you rarely need to read
them, and they are excluded from the generated views.
`Workflows/` holds repo-specific multi-agent workflow definitions (`requirements-check`,
`code-requirements-align`, `defect-investigator`, `test-quality-checker`) for checking code and tests
against the SRS.

**Requirement views (`docs/requirements_views/`) — consult first to save context.** The full SRS is
~37K tokens; you rarely need it whole. Two generated, read-only views (from
`tools/traceability_sync/generate_views.py`, derived from the SRS + code `Satisfies:` tags):
- `requirements_index.md` — terse one-line-per-requirement summary (~13K tokens); use for **broad**
  understanding.
- `code_to_requirements.md` (+ `.json`) — source file → requirement IDs it implements; use for
  **targeted** work (look up the file you're editing, read just those IDs).
The SRS stays the single source of truth and the only requirements file edited by hand. **Never edit
the views** — regenerate them (step 3a).

## Requirement-change workflow (MANDATORY)

Whenever you are asked to **add or change a requirement**, perform all of these steps in order — do
not stop short:

1. **Update the requirements** in `docs/cpm_fm_requirements.md` (add/modify the `FR-`/`UIR-`/`DR-`/
   `CR-`/`NFR-` entry).
2. **Implement the changes.** In every new or changed function, update the docstring with a
   `Satisfies:` tag citing the relevant requirement ID(s).
3. **Update the requirements** with the traceability mapping to the new and changed functions.
3a. **Regenerate the views** — run `python tools/traceability_sync/generate_views.py` and commit
   `docs/requirements_views/` (see "Requirement views" above; never hand-edit them).
4. **Run the unit tests** (`pytest`).
5. **Iterate steps 2–4** until all unit tests pass.
6. **Update the manual test plan** (`docs/manual_test_plan.md`) and increment its test plan version.
7. **Update the manual test scorecard** (`docs/manual_test_scorecard.md`) to match the test plan and
   increment its score version.
7a. **Record the change** — bump `src/version.txt` and the SRS version field (DR-040/DR-041), and add a
   row to **`docs/requirements_change_history.md`** (the §11 companion file — *not* the SRS itself).
   When a requirements review resolves an ambiguity or gap, add the OI entry to
   **`docs/requirements_issue_log.md`** (the §10 companion file).
8. **Provide a summary** of the actions taken.
