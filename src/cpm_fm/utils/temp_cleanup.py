"""Central management of the application's temporary working directories.

The application extracts disk-image contents (FR-171) and downloads remote files
for viewing (FR-113a) into throw-away directories under the OS temp directory.
Every such directory is created with a single shared prefix (:data:`TEMP_PREFIX`)
so the whole set can be found and removed later, including any left behind by a
previous session that ended without a clean exit (a crash or kill bypasses
``closeEvent``). On application start-up and on exit the application sweeps the
temp directory for these directories and removes them (FR-016), so the host is
not left accumulating orphaned ``cpm_fm_*`` folders.

This module is pure host-side filesystem logic and imports nothing from the GUI
toolkit (CR-014), so it is unit-testable without a running Qt application.

Satisfies: FR-016, FR-113a, FR-171, CR-014.
"""

from __future__ import annotations

import glob
import os
import shutil
import tempfile

# Shared prefix for every temporary directory the application creates. The
# disk-image workdir adds its own ``img_`` tag on top of this, so both live under
# the one prefix and are swept together.
TEMP_PREFIX = "cpm_fm_"


def make_temp_dir(tag: str = "") -> str:
    """Create and return a new temporary working directory for the application.

    All directories share :data:`TEMP_PREFIX` so :func:`sweep_temp_dirs` can find
    and remove them later. ``tag`` is an optional extra label folded into the
    prefix (e.g. ``"img_"`` for the disk-image workdir) purely to make the folder
    self-describing on the host; it does not affect the sweep.

    Satisfies: FR-113a, FR-171.
    """
    return tempfile.mkdtemp(prefix=f"{TEMP_PREFIX}{tag}")


def sweep_temp_dirs() -> int:
    """Remove every ``cpm_fm_*`` directory in the OS temp directory; return the count removed.

    Sweeps directories created by :func:`make_temp_dir` in this session as well as
    any historical ones left by a previous session that ended without a clean exit.
    Each directory is removed with ``ignore_errors=True``, so one still held open
    by an external viewer or another running instance is skipped rather than
    aborting the sweep; it is picked up by a later sweep once released. Only
    directories are removed — a stray file sharing the prefix is left untouched.

    Satisfies: FR-016.
    """
    removed = 0
    for path in glob.glob(os.path.join(tempfile.gettempdir(), f"{TEMP_PREFIX}*")):
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
            if not os.path.exists(path):
                removed += 1
    return removed
