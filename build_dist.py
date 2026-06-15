#!/usr/bin/env python3
"""Build a PyInstaller distribution package for cpm-fm.

PyInstaller **cannot cross-compile**: a Windows .exe must be built on Windows, a
Linux binary on Linux, and a macOS .app on macOS. So "build all three" is not
something one machine can do — instead this script builds the package for the OS
it is run on, using the matching spec file. To produce all three, run it once on
each platform (locally or via CI — see the GitHub Actions snippet in the
docstring at the bottom of this file).

Usage::

    python build_dist.py                # build for the current OS
    python build_dist.py --target linux # build for a named target (must match current OS)
    python build_dist.py --no-clean     # keep previous build/ cache
    python build_dist.py --list         # show the spec mapping and exit

Output lands in ``dist/`` (a single executable on Windows/Linux, ``cpm-fm.app``
on macOS).
"""

from __future__ import annotations

import argparse
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Map the running OS (platform.system()) to a friendly target name and its spec.
SPEC_FOR_TARGET = {
    "windows": "pyinstaller_windows.spec",
    "linux": "pyinstaller_linux.spec",
    "macos": "pyinstaller_macos.spec",
}

SYSTEM_TO_TARGET = {
    "Windows": "windows",
    "Linux": "linux",
    "Darwin": "macos",
}


def current_target() -> str | None:
    """Return the build target for the OS we are running on, or None if unknown."""
    return SYSTEM_TO_TARGET.get(platform.system())


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a PyInstaller package for cpm-fm.")
    parser.add_argument(
        "--target",
        choices=sorted(SPEC_FOR_TARGET),
        help="Target platform (defaults to the current OS). Must match the current OS — "
        "PyInstaller cannot cross-compile.",
    )
    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="Do not pass --clean to PyInstaller (reuse the build/ cache).",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Print the target -> spec mapping and exit.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    if args.list:
        print("Target   Spec file                   (build on)")
        print("-------- --------------------------- -------------")
        for target, spec in SPEC_FOR_TARGET.items():
            print(f"{target:<8} {spec:<27} {target}")
        return 0

    detected = current_target()
    target = args.target or detected

    if target is None:
        print(
            f"ERROR: unrecognised OS {platform.system()!r}; pass --target explicitly.",
            file=sys.stderr,
        )
        return 2

    # Guard against the impossible cross-compile request.
    if detected is not None and target != detected:
        print(
            f"ERROR: requested target {target!r} but this is a {detected!r} host. "
            "PyInstaller cannot cross-compile; run this script on a "
            f"{target!r} machine instead.",
            file=sys.stderr,
        )
        return 2

    spec = ROOT / SPEC_FOR_TARGET[target]
    if not spec.is_file():
        print(f"ERROR: spec file not found: {spec}", file=sys.stderr)
        return 2

    # Invoke PyInstaller via the current interpreter so it uses this venv.
    cmd = [sys.executable, "-m", "PyInstaller", str(spec), "--noconfirm"]
    if not args.no_clean:
        cmd.append("--clean")

    print(f"Building {target} package: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(ROOT))
    if result.returncode == 0:
        print(f"\nDone. Artifacts are in {ROOT / 'dist'}.")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))


# ---------------------------------------------------------------------------
# Building all three from one place: use CI. Example GitHub Actions matrix
# (drop into .github/workflows/build.yml):
#
#   jobs:
#     build:
#       strategy:
#         matrix:
#           os: [windows-latest, ubuntu-latest, macos-latest]
#       runs-on: ${{ matrix.os }}
#       steps:
#         - uses: actions/checkout@v4
#         - uses: actions/setup-python@v5
#           with: { python-version: '3.12' }
#         - run: python -m pip install -e .[dev] pyinstaller
#         - run: python build_dist.py
#         - uses: actions/upload-artifact@v4
#           with:
#             name: cpm-fm-${{ matrix.os }}
#             path: dist/
# ---------------------------------------------------------------------------
