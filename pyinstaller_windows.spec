# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Windows build of cpm-fm.

Produces a single windowed .exe (no console). Build with::

    python build_dist.py            # auto-detects Windows and runs this spec
    # or directly:
    pyinstaller pyinstaller_windows.spec --noconfirm --clean

Shared settings (data-file layout, hidden imports, excludes) live in
``_pyinstaller_common.py`` next to this file.
"""

import os
import sys

# SPECPATH is the directory of this spec; make the shared helper importable.
sys.path.insert(0, SPECPATH)
import _pyinstaller_common as common  # noqa: E402

a = Analysis(
    [common.ENTRY_SCRIPT],
    pathex=common.PATHEX,
    binaries=[],
    datas=common.build_datas(),
    hiddenimports=common.HIDDEN_IMPORTS,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=common.EXCLUDES,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=common.APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # GUI app: no console window
    disable_windowed_traceback=False,
    icon=common.find_icon("ico"),
)
