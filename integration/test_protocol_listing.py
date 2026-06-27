"""§10 — remote listing tier (MT-R*).

Capture/idle-timeout, drive selection, and DIR-output parsing against the live
peer. Read-only: these tests do not write to the remote.
"""

from __future__ import annotations

import pytest


@pytest.mark.hil
@pytest.mark.mt("MT-R03", "FR-041", "DR-033a")
def test_detect_current_drive(peer):
    """A bare EOL yields a CP/M drive prompt; its letter is detected.

    Verifies: FR-041, DR-033a.
    """
    letter = peer.detect_drive()
    assert letter is not None and "A" <= letter <= "P"
    print(f"[listing] current drive = {letter}:")


@pytest.mark.hil
@pytest.mark.mt("MT-R05", "FR-100", "FR-101", "FR-102")
def test_change_to_scratch_drive(peer, scratch_drive):
    """Selecting the scratch drive returns its drive prompt.

    Verifies: FR-100, FR-101, FR-102.
    """
    assert peer.change_drive(scratch_drive), f"no {scratch_drive}> prompt after select"


@pytest.mark.hil
@pytest.mark.mt("MT-R01", "FR-077", "FR-078", "FR-079")
def test_dir_listing_parses(peer, scratch_drive):
    """A DIR capture on the scratch drive parses into a filename mapping.

    Verifies: FR-077, FR-078, FR-079.
    """
    listing = peer.list(scratch_drive)
    assert isinstance(listing, dict)
    # Every parsed name is a bare 8.3-style token (no drive prefix, no padding).
    for name in listing:
        assert ":" not in name and name == name.strip()
    print(f"[listing] {scratch_drive}: holds {len(listing)} file(s)")
