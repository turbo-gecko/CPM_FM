# CP/M File Manager (`cpm-fm`)

A cross-platform PySide6 desktop app for transferring files between a modern host and legacy
[CP/M](https://en.wikipedia.org/wiki/CP/M) systems over a serial link, using the X-Modem protocol.

## Features

- Browse host and remote (CP/M) file listings side by side.
- Copy files to and from the CP/M system over X-Modem.
- Built-in serial terminal with local echo for issuing CP/M commands.
- Separate terminal and transport serial ports.
- Configurable serial parameters and CP/M commands, saved/loaded as JSON.

## Requirements

- Python 3.9+
- PySide6 (for the GUI)
- A serial connection to the CP/M system (`pyserial` is installed automatically).

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

The app starts unconfigured. Use **File > Load** to load a settings file — see the samples in
[`examples/`](examples/) — or set parameters via the **Config** menu and **File > Save** them.

## Test

```bash
pytest
```

## Develop

```bash
ruff check src tests        # lint
ruff format src tests       # format
mypy src                    # type-check
```

## Project layout

```
src/cpm_fm/        application package (src-layout)
  app.py           MainApplication + main() entry point
  gui/             PySide6 dialogs and terminal window
  terminal/        serial manager, CP/M DIR parser, X-Modem protocol
  utils/           JSON config handling
tests/             pytest suite
examples/          sample serial/general settings JSON
docs/              design and requirements documents
```

See [`docs/`](docs/) for the design and requirements documents.

## License

Apache License 2.0 — see [LICENSE](LICENSE).
