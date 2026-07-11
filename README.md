# CP/M File Manager (`cpm-fm`)

A cross-platform PySide6 desktop app for transferring files between a modern host and legacy
[CP/M](https://en.wikipedia.org/wiki/CP/M) systems over a serial link, using the X-Modem protocol.
CP/M 2.2 and ZSDOS 1.1 have been confirmed to work with the application.

>## Note (2026-07-09)
>From version 2.36.0, a new major feature change occured involving the addition of being
>able to work with disk images. As part of this effort, there were several UI changes
>from the last major release of 2.27.1. In the package folder there is an archived
>version of the Windows 2.27.1 if people prefer the older app functionality and there
>is a 2.27.1 branch for Linux and Mac users to build their own version from.

## Features

- Browse host and remote (CP/M) file listings side by side, with a draggable splitter.
  Each pane has a wildcard/substring **filter** and a **sort** control (by name or
  extension, ascending or descending); the filter and sort are remembered per pane.
- **CP/M user areas (0–15):** pick a user area next to the drive in the Remote pane;
  listings and transfers are scoped to it. When browsing a **disk image**, each file
  shows its user area and an optional per-area filter narrows the view to one area;
  image files copied to a live machine keep their source area, and saving an image
  preserves every file's area. (Transferring into a *non-zero* area is best-effort —
  your CP/M transfer utility must be reachable from that area, typically a **SYS file
  in user 0**; otherwise the transfer reports a "no response" error naming the area.)
- Transfer single or multiple selected files in both directions over X-Modem, with a
  modal progress dialog (file name, block/byte counts, batch position) and a **Cancel**
  button to abort an in-progress transfer.
- **Drag and drop** to transfer: drag selected files between the panes, or drop files
  from the host OS file manager onto the Remote pane to upload them.
- **File-conflict handling:** when a file already exists at the destination you are
  prompted to Overwrite, Skip, or Cancel, with an option to apply the choice to the
  rest of the batch.
- **CP/M 8.3 filename validation** on upload: a host file whose name CP/M can't store
  prompts you to rename (with a suggested conforming name), skip, or cancel.
- **Transfer history:** every transfer attempt (success, failure, cancelled, or skipped)
  is recorded to a persistent history you can review, filter, export, clear, and
  re-transfer from (**History** toolbar button).
- **Whole-drive Backup and Restore** (toolbar buttons): mirror every file between the
  remote drive and the host directory in one operation. **Backup** copies the whole
  remote drive to the host; **Restore** copies the whole host directory to the remote
  drive. Each first refreshes the destination, then warns that **all** files at the
  destination will be deleted and re-written and asks you to continue or cancel; on
  confirmation it wipes the destination and copies the source across, with the usual
  progress dialog and a Cancel button.
- Manage files on both sides from a right-click context menu: transfer, rename, delete,
  and view/edit (host) or view (remote); transfer and delete act on every selected file.
- **Functional VT-100 terminal:** a built-in, non-modal terminal window that interprets
  the VT-100/ANSI escape sequences CP/M emits (cursor positioning, screen/line erase,
  colour and text attributes, scrolling), so full-screen programs such as editors display
  correctly rather than as raw escape codes. You type directly into the screen — each
  keystroke, including the arrow, function, and Ctrl keys, is sent to CP/M immediately
  (there is no separate Send box). Selectable emulation (**VT100 / VT52 / ADM-3A**), a
  configurable session-remembered **font**, and a right-click menu (Copy, Paste, Clear,
  Font…, Reset Size 24×80, Boot into CP/M, Terminal Type, Macros). The window reopens
  automatically on the next launch if it was open at exit.
- **Configurable keystroke macros:** program up to ten labelled macro buttons (via
  **Config > Terminal**) and run them from the terminal's **Macros** submenu; each uses the
  same scripting directives (`SEND`, `SENDRAW`, `WAIT`, `WAITFOR`) as the boot sequence.
- **Boot into CP/M:** run a configurable boot-sequence script from the terminal to bring
  the remote up into CP/M.
- Separate terminal and transport serial ports (which may be the same physical port).
- Configurable serial parameters, terminal/macro settings, general host settings, and
  CP/M remote commands via the **Serial**, **Terminal**, **General**, and **Remote**
  config dialogs (each with a vertical scrollbar), saved/loaded as JSON.
- Remembers and auto-reloads the last-used configuration on startup, shows its name in
  the title bar, and persists each window's size and position between runs.
- Material Design theme that follows the host OS light/dark mode.
- Multi-language user interface (12 languages, selectable from **Config > Language**):
  English, Spanish, French, German, Italian, Dutch, Polish, Greek, Mandarin, Cantonese,
  Korean — and Pirate.
- **Help > Manual** opens the bundled user manual; **Help > About** shows the version
  and a link to the project repository.

## Requirements

- Python 3.9 or newer. (Continuous integration tests on Python 3.12; that is the
  reference interpreter for development.)
- A serial connection to the CP/M system.
- Runtime dependencies (installed automatically): `PySide6` (Qt GUI), `qt-material`
  (theme), `pyserial` (serial I/O), and `markdown` (renders the bundled user manual).

## Install

```bash
python -m pip install -e .[dev]
```

This installs the package in editable mode together with the development tools
(`pytest`, `ruff`, `mypy`, `pre-commit`, `Pillow`, `pydantic`). For the full
contributor setup — including the pre-commit hooks — see
[Developer Workflow](#developer-workflow).

## Run

```bash
cpm-fm           # via the installed GUI launcher (no console window on Windows)
python -m cpm_fm # equivalent, keeps a console for debugging output
```

The app starts unconfigured (unless it can reload the last-used configuration). Use
**Config > Load Config** to load a settings file — see the samples in [`examples/`](examples/) — or set
parameters via the **Config** menu dialogs and save them with **Config > Save Config**. **Config > New
Config** resets to defaults. The loaded configuration's name is shown in the title bar.

Connect, disconnect, open the terminal, view the transfer history, and run a whole-drive **Backup**
or **Restore** from the toolbar. Right-click a file in either pane for transfer, rename, delete, and
view actions, or drag files between the panes to transfer them.

## Building a standalone package

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

## Documentation

For additional documentation, tips, troubleshooting, and community contributions, visit the
[CPM_FM Wiki](https://github.com/turbo-gecko/CPM_FM/wiki).

## Developer Guide

If you want to fork and/or contribute to the project, see [`docs/dev_guideline.md`](docs/dev_guideline.md) for detailed information on the developer workflow, including setup, testing, building, and the requirement-change workflow.

## License

Apache License 2.0 — see [LICENSE](LICENSE).
