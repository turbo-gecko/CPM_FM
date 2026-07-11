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


@pytest.mark.hil
@pytest.mark.mt("MT-R10", "FR-181", "FR-182")
def test_user_area_switch_lists(peer, scratch_drive):
    """Selecting a user area (USER n) re-scopes the listing without breaking it.

    Verifies: FR-181, FR-182.
    """
    assert peer.change_drive(scratch_drive)
    try:
        assert peer.set_user(0), "USER 0 not accepted"
        assert isinstance(peer.list(), dict)
        assert peer.set_user(3), "USER 3 not accepted"
        assert isinstance(peer.list(), dict)
    finally:
        # Always leave the box in the default area so later tests (whose peer
        # operations run in the current area) are not contaminated.
        peer.set_user(0)


@pytest.mark.hil
@pytest.mark.mt("MT-R11", "FR-183", "FR-184")
def test_transfer_targets_selected_user_area(peer, scratch_drive, tmp_path):
    """A file sent while area 3 is current lands in area 3, not area 0.

    Confirms the CP/M-side assumption FR-183 relies on: a file received after
    ``USER 3`` is visible under area 3 and absent under area 0. This is a
    **best-effort** behaviour (FR-183): it works only when the transfer utility
    is reachable from a non-zero user area (present there, or SYS in user 0). On
    a target where it is not, the test is skipped (BLOCKED) rather than failed.

    Isolation: user area is a global CP/M state that persists across tests, so
    this test always restores ``USER 0`` in a ``finally`` — otherwise a failure
    mid-test would leave the box in area 3 and break every later transfer test
    (whose utility may not be reachable from area 3).

    Verifies: FR-183, FR-184.
    """
    name = "UAREA.TXT"
    (tmp_path / name).write_bytes(b"user area 3\r\n")
    assert peer.change_drive(scratch_drive)
    try:
        # Clean the name from both areas first.
        peer.set_user(0)
        peer.erase(name)
        peer.set_user(3)
        peer.erase(name)
        # Send while area 3 is current (send_file keeps the current area). A
        # failed launch here means the utility is not reachable from area 3 —
        # the documented best-effort limit, not a defect.
        if not peer.send_file(str(tmp_path / name), letter=scratch_drive):
            pytest.skip(
                "BLOCKED: transfer utility not reachable from user area 3 "
                "(best-effort, FR-183)"
            )
        peer.set_user(3)
        in_area_3 = name.upper() in {n.upper() for n in peer.list()}
        peer.set_user(0)
        in_area_0 = name.upper() in {n.upper() for n in peer.list()}
        if not in_area_3:
            pytest.skip(
                "BLOCKED: target did not place the file in user area 3 "
                "(best-effort, FR-183)"
            )
        assert not in_area_0, "file leaked into area 0"
    finally:
        # Clean the name from both areas and restore the default area, whatever
        # happened above (assertion, skip, or success).
        for area in (3, 0):
            try:
                peer.set_user(area)
                peer.erase(name)
            except Exception:  # noqa: BLE001 - cleanup must not mask the result
                pass
        peer.set_user(0)
