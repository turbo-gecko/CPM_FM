"""§10 — remote listing tier (MT-R*).

Capture/idle-timeout, drive selection, and DIR-output parsing against the live
peer. Read-only: these tests do not write to the remote.

The empty-directory (MT-R08) and single-file (MT-R09) edge cases verify the
parser handles degenerate inputs correctly.
"""

from __future__ import annotations

import pytest
from helpers.trace import get_logger

log = get_logger("listing")


@pytest.mark.hil
@pytest.mark.mt("MT-R03", "FR-041", "DR-033a")
def test_detect_current_drive(peer):
    """A bare EOL yields a CP/M drive prompt; its letter is detected.

    Verifies: FR-041, DR-033a.
    """
    letter = peer.detect_drive()
    assert letter is not None and "A" <= letter <= "P"
    log.info("current drive = %s:", letter)


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
    log.info("%s: holds %d file(s)", scratch_drive, len(listing))


@pytest.mark.hil
@pytest.mark.mt("MT-R08", "FR-077")
def test_dir_listing_empty_directory(peer, scratch_drive):
    """An empty directory returns an empty dict (not None or an error).

    Verifies: FR-077.
    """
    peer.wipe_drive(scratch_drive)
    listing = peer.list(scratch_drive)
    assert listing == {}, f"expected empty dict for empty dir, got {listing!r}"
    log.info("%s: empty directory → {} (OK)", scratch_drive)


@pytest.mark.hil
@pytest.mark.mt("MT-R09", "FR-077")
def test_dir_listing_single_file(peer, scratch_drive, tmp_path):
    """A directory with exactly one file returns a mapping with one entry.

    Verifies: FR-077.
    """
    name = "SINGLE.TXT"
    (tmp_path / name).write_bytes(b"one file\r\n")
    peer.erase(name, letter=scratch_drive)
    upload_ok = peer.send_file(str(tmp_path / name), letter=scratch_drive)
    assert upload_ok, f"seed upload of {name} failed"
    listing = peer.list(scratch_drive)
    assert len(listing) == 1, f"expected 1 entry, got {len(listing)}: {listing}"
    assert name.upper() in {n.upper() for n in listing}
    peer.erase(name, letter=scratch_drive)
    log.info("%s: single file → %d entry (OK)", scratch_drive, len(listing))
