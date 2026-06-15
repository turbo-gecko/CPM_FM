# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Linux build of cpm-fm.

Produces a single self-contained executable. Build with::

    python build_dist.py            # auto-detects Linux and runs this spec
    # or directly:
    pyinstaller pyinstaller_linux.spec --noconfirm --clean

Shared settings (data-file layout, hidden imports, excludes) live in
``_pyinstaller_common.py`` next to this file.

Note: PyInstaller does not cross-compile — run this on Linux (the glibc of the
build host sets the minimum supported glibc of the result).
"""

import os
import sys

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
    console=False,  # GUI app
    disable_windowed_traceback=False,
    icon=common.find_icon("png"),
)
