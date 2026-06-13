"""Application version and identity constants.

The version number is held in a plain-text file ``version.txt`` in the ``src/``
folder (a sibling of the ``cpm_fm`` package) so it can be kept in lock-step with
the SRS version without editing source. ``get_version`` reads that file; the
package ``__version__`` is derived from it. This module imports nothing from the
GUI layers, so it is safe to use from anywhere (CR-014).

Satisfies: DR-040, DR-041.
"""

from __future__ import annotations

from pathlib import Path

# UIR-076 / FR-022: identity strings shown in the About dialog.
APP_NAME = "CP/M File Manager"
REPO_URL = "https://github.com/turbo-gecko/CPM_FM"

# DR-041: sentinel used when version.txt cannot be read, so the application
# still starts and the About dialog still renders.
_FALLBACK_VERSION = "0.0.0"

# version.txt lives in src/, one level above this package directory
# (src/cpm_fm/version.py -> src/version.txt).
_VERSION_FILE = Path(__file__).resolve().parent.parent / "version.txt"


def get_version() -> str:
    """Return the application version string read from ``src/version.txt``.

    Reads the single semantic-version string from the file, ignoring
    surrounding whitespace. If the file is missing or unreadable, returns the
    fallback sentinel rather than raising, so start-up is never blocked
    (DR-041).

    Satisfies: DR-040, DR-041.
    """
    try:
        text = _VERSION_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return _FALLBACK_VERSION
    return text or _FALLBACK_VERSION
