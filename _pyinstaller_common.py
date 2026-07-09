"""Shared configuration for the per-platform PyInstaller spec files.

This module is imported by ``pyinstaller_windows.spec``, ``pyinstaller_linux.spec``
and ``pyinstaller_macos.spec`` so the parts that MUST stay identical across
platforms — above all the bundled data-file layout — live in exactly one place.

Why the data-file layout matters
--------------------------------
The app resolves two sets of runtime data files relative to ``__file__``:

* ``cpm_fm/version.py`` reads ``version.txt`` from ``parent.parent`` of the
  package module, i.e. the directory *above* ``cpm_fm`` (see DR-040).
* ``cpm_fm/utils/i18n.py`` reads ``lang_<language>.txt`` from
  ``<package>/lang`` (see DR-042).

PyInstaller sets each frozen module's ``__file__`` to a path under the bundle
root (``sys._MEIPASS`` for one-file builds), so those same relative lookups keep
working *only if* the data files are placed at matching locations inside the
bundle:

* ``version.txt`` -> bundle root (``.``)
* ``lang_*.txt``  -> ``cpm_fm/lang``
* ``cpm_fm_manual.md`` -> ``cpm_fm/docs`` (see DR-047, manual_dialog.py)

The ``DATAS`` list below encodes exactly that. Do not change the destinations
without also changing the ``Path(__file__)`` logic in ``version.py`` / ``i18n.py``.
"""

from __future__ import annotations

import os

from PyInstaller.utils.hooks import collect_data_files

# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------

#: Name of the produced executable / app bundle.
APP_NAME = "cpm-fm"

#: Repo root = the directory containing this file (and the .spec files).
ROOT = os.path.dirname(os.path.abspath(__file__))

#: Entry-point script. ``__main__.py`` is run as ``__main__`` by PyInstaller, so
#: its ``if __name__ == "__main__": main()`` guard fires exactly as it does for
#: ``python -m cpm_fm``.
ENTRY_SCRIPT = os.path.join(ROOT, "src", "cpm_fm", "__main__.py")

#: ``src`` must be on the import path so the ``cpm_fm`` package is found.
PATHEX = [os.path.join(ROOT, "src")]


# ---------------------------------------------------------------------------
# Data files
# ---------------------------------------------------------------------------

def build_datas() -> list[tuple[str, str]]:
    """Return the ``(source, dest_dir)`` tuples to bundle.

    Keep the destinations in sync with the ``Path(__file__)``-relative loaders
    described in this module's docstring (DR-040, DR-042).
    """
    datas: list[tuple[str, str]] = []

    # version.txt -> bundle root, matching version.py's parent.parent lookup.
    datas.append((os.path.join(ROOT, "src", "version.txt"), "."))

    # Per-language string files -> cpm_fm/lang, matching i18n.py's LANG_DIR.
    lang_dir = os.path.join(ROOT, "src", "cpm_fm", "lang")
    for name in sorted(os.listdir(lang_dir)):
        if name.startswith("lang_") and name.endswith(".txt"):
            datas.append((os.path.join(lang_dir, name), os.path.join("cpm_fm", "lang")))

    # Sample settings files — handy since the app starts unconfigured.
    examples_dir = os.path.join(ROOT, "examples")
    if os.path.isdir(examples_dir):
        for name in sorted(os.listdir(examples_dir)):
            if name.endswith(".json"):
                datas.append((os.path.join(examples_dir, name), "examples"))

    # DR-044/UIR-078: runtime window icon -> cpm_fm/icons, matching theme.py's
    # __file__-relative lookup (APP_ICON_PATH).
    runtime_icon = os.path.join(ROOT, "src", "cpm_fm", "icons", "cpm-fm.png")
    if os.path.isfile(runtime_icon):
        datas.append((runtime_icon, os.path.join("cpm_fm", "icons")))

    # DR-047/FR-023: bundled user manual -> cpm_fm/docs, matching
    # manual_dialog.py's __file__-relative lookup (MANUAL_PATH).
    manual = os.path.join(ROOT, "src", "cpm_fm", "docs", "cpm_fm_manual.md")
    if os.path.isfile(manual):
        datas.append((manual, os.path.join("cpm_fm", "docs")))

    # DR-048: bundled CP/M disk-image geometry database -> cpm_fm/utils/disk_image/data,
    # matching disk_image/__init__.py's __file__-relative lookup (_BUNDLED_DISKDEFS).
    diskdefs = os.path.join(ROOT, "src", "cpm_fm", "utils", "disk_image", "data", "diskdefs")
    if os.path.isfile(diskdefs):
        datas.append((diskdefs, os.path.join("cpm_fm", "utils", "disk_image", "data")))

    # qt-material ships its own QSS templates / icon resources that are loaded at
    # runtime; PyInstaller's static analysis won't find them, so collect them.
    datas += collect_data_files("qt_material")

    return datas


# ---------------------------------------------------------------------------
# Imports the static analyser may miss / modules we can safely drop
# ---------------------------------------------------------------------------

#: ``serial.tools.list_ports`` is imported normally in app.py, but list it
#: explicitly so a future refactor to a lazy import can't silently break the build.
#: Python-Markdown loads its extensions by dotted path at run time (see
#: ``manual_dialog._MD_EXTENSIONS``), so the static analyser won't see them;
#: list them here so the manual (UIR-091) renders in a frozen build.
HIDDEN_IMPORTS = [
    "serial.tools.list_ports",
    "markdown.extensions.toc",
    "markdown.extensions.tables",
    "markdown.extensions.fenced_code",
    "markdown.extensions.attr_list",
    "markdown.extensions.sane_lists",
]

#: Large optional libraries the app never uses. ``wx`` is present but unused in
#: the dev venv (see CLAUDE.md); ``tkinter`` was fully removed at the v1.3 Qt
#: migration. Excluding these keeps the bundle small.
EXCLUDES = [
    "tkinter",
    "_tkinter",
    "wx",
    "matplotlib",
    "numpy",
    "pandas",
    "scipy",
    "PIL",
    "pytest",
    "pydoc",
]


def find_icon(extension: str) -> str | None:
    """Return ``assets/icon.<extension>`` if it exists, else ``None``.

    Icons are optional: drop ``assets/icon.ico`` (Windows), ``assets/icon.icns``
    (macOS) or ``assets/icon.png`` (Linux) into the repo to brand the build;
    without them PyInstaller uses its default icon.
    """
    candidate = os.path.join(ROOT, "assets", f"icon.{extension}")
    return candidate if os.path.isfile(candidate) else None
