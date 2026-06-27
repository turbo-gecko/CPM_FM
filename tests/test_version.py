"""Tests for application version sourcing from src/version.txt (DR-040/DR-041)."""

from pathlib import Path

import cpm_fm
from cpm_fm import version as version_module
from cpm_fm.version import _FALLBACK_VERSION, APP_NAME, REPO_URL, get_version

# Repo layout: tests/ is a sibling of src/, so src/version.txt is two levels up.
_VERSION_TXT = Path(__file__).resolve().parent.parent / "src" / "version.txt"


def test_version_file_exists_in_src():
    """DR-040: the version is stored in src/version.txt.

    Verifies: DR-040.
    """
    assert _VERSION_TXT.is_file()


def test_get_version_reads_version_file():
    """DR-040: get_version returns the (stripped) contents of version.txt.

    Verifies: DR-040.
    """
    expected = _VERSION_TXT.read_text(encoding="utf-8").strip()
    assert get_version() == expected
    assert expected  # non-empty


def test_get_version_is_semantic_version_string():
    """DR-040: the file holds a single dotted semantic-version string.

    Verifies: DR-040.
    """
    parts = get_version().split(".")
    assert len(parts) == 3
    assert all(p.isdigit() for p in parts)


def test_package_version_matches_file():
    """DR-041: cpm_fm.__version__ is derived from version.txt.

    Verifies: DR-041.
    """
    assert cpm_fm.__version__ == get_version()


def test_get_version_falls_back_when_file_missing(monkeypatch, tmp_path):
    """DR-041: an unreadable version.txt yields the fallback, not an exception.

    Verifies: DR-041.
    """
    monkeypatch.setattr(version_module, "_VERSION_FILE", tmp_path / "does_not_exist.txt")
    assert get_version() == _FALLBACK_VERSION


def test_identity_constants():
    """UIR-076: the About dialog identity strings.

    Verifies: UIR-076.
    """
    assert APP_NAME == "CP/M File Manager"
    assert REPO_URL == "https://github.com/turbo-gecko/CPM_FM"
