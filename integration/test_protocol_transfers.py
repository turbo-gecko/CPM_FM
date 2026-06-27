"""§11 — X-Modem transfer tier (MT-T*).

Real round-trips against the live peer: upload to the scratch drive, download
back, and assert byte-for-byte integrity (block-padding aware). The MT-T10 1K
and checksum variants are gated per target by ``has_1k_sender`` /
``has_checksum_sender``; the default-mode round-trip runs on every target.

All writes target the operator-nominated scratch drive and clean up after
themselves (ERA the test file before and after each round-trip).
"""

from __future__ import annotations

import pytest
from helpers.integrity import assert_round_trip, sample_files


@pytest.fixture
def samples(tmp_path):
    return sample_files(tmp_path / "src")


def _round_trip(peer, scratch, src_path, out_dir, use_1k=None):
    name = src_path.name
    peer.erase(name, letter=scratch)  # clean slate (no-op if absent)
    assert peer.send_file(str(src_path), letter=scratch, use_1k=use_1k), f"upload of {name} failed"
    assert peer.exists(name, letter=scratch), f"{name} not listed after upload"
    dst = out_dir / f"dl_{name}"
    assert peer.recv_file(name, str(dst), letter=scratch, use_1k=use_1k), (
        f"download of {name} failed"
    )
    assert_round_trip(src_path, dst)
    peer.erase(name, letter=scratch)


@pytest.mark.hil
@pytest.mark.mt("MT-T03", "FR-081", "FR-082", "FR-083")
def test_round_trip_sample_files(peer, scratch_drive, samples, tmp_path):
    """Every sample file survives an upload→download round-trip byte-for-byte.

    Verifies: FR-081, FR-082, FR-083.
    """
    for src in samples:
        _round_trip(peer, scratch_drive, src, tmp_path)
        print(f"[transfer] round-trip OK: {src.name} ({src.stat().st_size} bytes)")


@pytest.mark.hil
@pytest.mark.mt("MT-T04", "FR-099", "FR-106", "FR-107")
def test_uploaded_file_visible_then_removable(peer, scratch_drive, samples, tmp_path):
    """An uploaded file appears in the listing and can be erased again.

    Verifies: FR-099, FR-106, FR-107.
    """
    src = samples[0]
    name = src.name
    peer.erase(name, letter=scratch_drive)
    assert peer.send_file(str(src), letter=scratch_drive)
    assert peer.exists(name, letter=scratch_drive)
    peer.erase(name, letter=scratch_drive)
    assert not peer.exists(name, letter=scratch_drive)


@pytest.mark.hil
@pytest.mark.mt("MT-T10", "FR-082", "NFR-003b", "NFR-003e")
def test_round_trip_1k(request, peer, scratch_drive, samples, tmp_path):
    """1K (STX/1024-byte) round-trip — gated on the target's 1K sender.

    Verifies: FR-082, NFR-003b, NFR-003e.
    """
    target = request.getfixturevalue("target")
    if not target.has_1k_sender:
        pytest.skip("N/A: target has no 1K-capable X-Modem sender")
    big = next(s for s in samples if s.name == "BIG.DAT")
    _round_trip(peer, scratch_drive, big, tmp_path, use_1k=True)


@pytest.mark.hil
@pytest.mark.mt("MT-T10", "FR-082", "NFR-003d", "NFR-003f")
def test_round_trip_checksum(request, peer, scratch_drive, samples, tmp_path):
    """128-byte checksum round-trip — gated on the target's checksum sender.

    Verifies: FR-082, NFR-003d, NFR-003f.
    """
    target = request.getfixturevalue("target")
    if not target.has_checksum_sender:
        pytest.skip("N/A: target has no checksum-only X-Modem sender")
    src = next(s for s in samples if s.name == "SHORT.TXT")
    _round_trip(peer, scratch_drive, src, tmp_path, use_1k=False)
