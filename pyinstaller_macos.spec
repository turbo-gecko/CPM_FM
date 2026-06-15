# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the macOS build of cpm-fm.

Produces ``dist/cpm-fm.app`` (a windowed .app bundle). Build with::

    python build_dist.py            # auto-detects macOS and runs this spec
    # or directly:
    pyinstaller pyinstaller_macos.spec --noconfirm --clean

Shared settings (data-file layout, hidden imports, excludes) live in
``_pyinstaller_common.py`` next to this file.

Note: PyInstaller does not cross-compile — run this on macOS. The resulting
.app is unsigned; distributing it to other Macs will require codesigning and
notarisation, which are outside the scope of this build.
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
    [],
    exclude_binaries=True,
    name=common.APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # GUI app
    disable_windowed_traceback=False,
    icon=common.find_icon("icns"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=common.APP_NAME,
)

app = BUNDLE(
    coll,
    name=f"{common.APP_NAME}.app",
    icon=common.find_icon("icns"),
    bundle_identifier="com.turbo-gecko.cpm-fm",
    info_plist={
        "NSHighResolutionCapable": True,
        "CFBundleDisplayName": "CP/M File Manager",
    },
)
