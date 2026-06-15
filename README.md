# CP/M File Manager (`cpm-fm`)

A cross-platform PySide6 desktop app for transferring files between a modern host and legacy
[CP/M](https://en.wikipedia.org/wiki/CP/M) systems over a serial link, using the X-Modem protocol.

## Features

- Browse host and remote (CP/M) file listings side by side, with a draggable splitter.
- Transfer single or multiple files in both directions over X-Modem.
- Manage files on both sides from a right-click context menu: rename, delete, and
  view/edit (host) or view (remote).
- Built-in non-modal serial terminal for issuing CP/M commands.
- Separate terminal and transport serial ports (which may be the same physical port).
- Configurable serial parameters and CP/M commands via Serial and General config
  dialogs, saved/loaded as JSON.
- Remembers and auto-reloads the last-used configuration on startup, and persists each
  window's size and position between runs.
- Material Design theme that follows the host OS light/dark mode.
- Multi-language user interface (12 languages, selectable from **Config > Language**):
  English, Spanish, French, German, Italian, Dutch, Polish, Greek, Mandarin, Cantonese,
  Korean — and Pirate.

## Requirements

- Python 3.9+
- A serial connection to the CP/M system.
- Dependencies (installed automatically): `PySide6` (Qt GUI), `qt-material` (theme),
  and `pyserial` (serial I/O).

## Install

```bash
python -m pip install -e .[dev]
```

This installs the package in editable mode along with the development tools (pytest, ruff, mypy).

## Run

```bash
cpm-fm           # via the installed GUI launcher (no console window on Windows)
python -m cpm_fm # equivalent, keeps a console for debugging output
```

The app starts unconfigured (unless it can reload the last-used configuration). Use
**File > Load** to load a settings file — see the samples in [`examples/`](examples/) — or set
parameters via the **Config** menu and **File > Save** them. **File > New** resets to defaults.
The loaded configuration's name is shown in the title bar.

Connect, disconnect, and open the terminal from the toolbar. Right-click a file in either pane
for transfer, rename, delete, and view actions.

## Test

```bash
pytest
```

## Build a standalone package

Standalone executables are built with [PyInstaller](https://pyinstaller.org/):

```bash
python -m pip install -e .[build]   # adds PyInstaller
python build_dist.py                # builds for the current OS
```

Output lands in `dist/`: a single `cpm-fm.exe` on Windows, a single `cpm-fm`
binary on Linux, and `cpm-fm.app` on macOS.

PyInstaller **cannot cross-compile** — each package must be built on its own OS.
`build_dist.py` auto-selects the matching spec (`pyinstaller_windows.spec`,
`pyinstaller_linux.spec`, `pyinstaller_macos.spec`; shared settings live in
`_pyinstaller_common.py`). To produce all three, run it once on each platform —
the docstring at the bottom of `build_dist.py` includes a ready-to-use GitHub
Actions matrix that does exactly that. Optional app icons: drop
`assets/icon.ico` / `assets/icon.icns` / `assets/icon.png` into the repo.

## Develop

```bash
ruff check src tests        # lint
ruff format src tests       # format
mypy src                    # type-check
```

## Project layout

```
src/cpm_fm/        application package (src-layout)
  app.py           MainWindow + main() entry point
  version.py       version/identity constants (reads src/version.txt)
  gui/             PySide6 dialogs, terminal window, theme, window-state persistence
  terminal/        serial manager, CP/M DIR parser, X-Modem protocol
  utils/           JSON config handling and runtime internationalisation (i18n)
  lang/            per-language UI string files (lang_<language>.txt)
tests/             pytest suite
examples/          sample serial/general settings JSON
docs/              requirements (SRS), manual test plan/scorecard, legacy design docs
```

`docs/cpm_fm_requirements.md` is the authoritative, traceable Software Requirements
Specification (ISO/IEC/IEEE 29148). See [`docs/`](docs/) for it and the manual test plan.

## License

Apache License 2.0 — see [LICENSE](LICENSE).
