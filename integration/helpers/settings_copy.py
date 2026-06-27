"""Settings-file immutability + working-copy methodology (plan §2.1).

The rule "the app settings file is not changed during testing" is enforced
mechanically: every test works on a *fresh copy* of the original file, and the
copy fixture asserts at teardown that the original's SHA-256 is unchanged. A
mismatch fails the test and signals a leak of mutation back to the source file.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path


def file_sha256(path: str | Path) -> str:
    """Return the SHA-256 hex digest of a file's contents."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def make_working_copy(src: str | Path, dst_dir: str | Path) -> Path:
    """Copy ``src`` into ``dst_dir`` and return the working-copy path.

    Metadata is preserved (``copy2``) so the copy is byte-identical, but the
    harness only ever mutates this copy — never ``src``.
    """
    src = Path(src)
    dst = Path(dst_dir) / src.name
    shutil.copy2(src, dst)
    return dst
