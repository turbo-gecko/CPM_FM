# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`cpm-fm` is a **PySide6 (Qt for Python)** desktop app that transfers files between a modern host and
legacy [CP/M](https://en.wikipedia.org/wiki/CP/M) systems over a serial link using X-Modem. The GUI
applies a Material Design theme via the `qt-material` package (set centrally at start-up in
`gui/theme.py`; the light/dark variant follows the host OS — UIR-070/UIR-073). As of v1.3 the UI was
migrated from Tkinter to PySide6; there is no remaining `tkinter` code, and the stray `wxPython` in
`.venv` is unused (ignore it).

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
- `terminal/xmodem.py` — `XModem` is a hand-rolled X-Modem implementation (128-byte packets,
  **checksum** mode, not CRC). `send_file`/`receive_file` are blocking and run on worker threads.
- `terminal/cpm_parser.py` — `CPMParser.parse_dir_output` is a pure static method that scrapes
  filenames from CP/M 2.2 four-column `DIR` text output. This is the most-tested logic.
- `utils/config_handler.py` — `ConfigHandler` loads/saves settings as JSON.
- `gui/` — `theme.py` (`apply_theme`, the central `qt-material` setup), `terminal_window.py`
  (`TerminalWindow`, a non-modal `QMainWindow` serial console) and `config_dialogs.py` (`ConfigDialog`
  base `QDialog` + `SerialConfigDialog`/`GeneralConfigDialog`, which build `QFormLayout` forms from
  declarative field lists).

### Key cross-cutting behaviors

- **Threading model:** Serial reads, and both transfer directions, run off the Qt GUI thread (daemon
  threads). Any UI update from those threads must be marshalled onto the GUI thread by **emitting a Qt
  signal** (`MainWindow` defines `status_changed`, `term_write`, `remote_files_ready`, `error_raised`;
  cross-thread emits are auto-queued) — never touch a widget directly from a worker thread (NFR-004).
  Follow this signal pattern when adding background work, or Qt will crash/misbehave.
- **Remote file listing is capture-based, not request/response:** `_do_refresh_remote_logic` sets a
  `_capture_active` flag, sends the list command (default `DIR`), `time.sleep(1.5)` to let output
  accumulate in `_remote_capture_buffer` via the read callback, then parses it. There is no end
  marker — the fixed sleep is the synchronization mechanism.
- **Two config JSON formats coexist** and both must keep working:
  - *Flat* (what the dialogs read/write, see `examples/serial_settings.json`): `terminal_port`,
    `transport_port`, `speed`, `data`, `parity`, `stopbits`, `flow`, `msec_char`, `msec_line`.
  - *Nested* (`examples/settings_a.json`): `{"serial": {...}, "general": {...}}` with different key
    names (`transfer_port`, `data_bits`, `stop_bits`, ...).
  `SerialManager.open_port` and `ConfigHandler.validate_serial_settings` defensively normalize both
  (unwrap a `serial` sub-dict, fall back across key-name variants). When touching settings handling,
  preserve compatibility with both shapes.
- The app **starts unconfigured** (`self.settings = {}`); settings come from File > Load or the
  Config dialogs. `eol` setting maps `CR`/`LF`/`CRLF` to terminator chars in `app.py`.

## Design docs and workflows

`docs/cpm_fm_requirements.md` is the **authoritative requirements specification** going forward — an
ISO/IEC/IEEE 29148 SRS with uniquely identified, traceable requirements (`FR-`/`UIR-`/`DR-`/`CR-`/
`NFR-` etc.). Cite requirement IDs when referencing behavior. `docs/legacy/App_Requirements.md` and
`docs/legacy/App_Design.md` are the original source documents it was consolidated from; they are
**archived** for history but are **superseded** where they conflict (e.g. they call Copy to Remote/Host
empty stubs, but the SRS and code implement working X-Modem transfers — see `FR-080`–`FR-085`,
`CR-010`).
`Workflows/` holds repo-specific multi-agent workflow definitions (`requirements-check`,
`code-requirements-align`, `defect-investigator`) for checking code against the SRS.
