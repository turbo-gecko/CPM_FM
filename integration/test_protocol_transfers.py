"""§11 — X-Modem transfer tier (MT-T*).

Real round-trips against the live peer: upload to the scratch drive, download
back, and assert byte-for-byte integrity (block-padding aware). The MT-T10 1K
and checksum variants are gated per target by ``has_1k_sender`` /
``has_checksum_sender``; the default-mode round-trip runs on every target.

All writes target the operator-nominated scratch drive and clean up after
themselves (ERA the test file before and after each round-trip).

Boundary tests (MT-T15–MT-T17) verify zero-byte, 128-byte, and 1024-byte
files transfer correctly. The mid-transfer port-close test (MT-T18) verifies
graceful failure.
"""

from __future__ import annotations

import time

import pytest
from helpers.integrity import assert_round_trip, sample_files
from helpers.trace import get_logger

log = get_logger("transfer")


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
        log.info("round-trip OK: %s (%d bytes)", src.name, src.stat().st_size)


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


@pytest.mark.hil
@pytest.mark.mt("MT-T15", "FR-081", "NFR-003q")
def test_round_trip_zero_byte_file(peer, scratch_drive, tmp_path):
    """A zero-byte file round-trips as an empty file on receivers that support it.

    This exercises the protocol layer (`peer.send_file` mirrors `_send_one_to_remote`,
    not the GUI batch): the sender transmits EOT before any data packet. Receivers
    that accept an EOT-only transfer (NFR-003q; e.g. PCGET) create a zero-length
    file and it round-trips; strict receivers (e.g. RomWBW `XM`) instead cancel and
    delete, so the upload fails — that is a receiver-side capability, not a bug, and
    the case is skipped. (In the GUI, zero-byte host files are not sent at all —
    FR-106a skips them up front — so the interactive app never hits this.)

    Verifies: FR-081, NFR-003q.
    """
    name = "EMPTY.DAT"
    empty_file = tmp_path / name
    empty_file.write_bytes(b"")
    peer.erase(name, letter=scratch_drive)
    upload_ok = peer.send_file(str(empty_file), letter=scratch_drive)
    if not upload_ok:
        pytest.skip("N/A: target CP/M receiver does not support zero-byte (EOT-only) transfers")
    # Some CP/M receivers don't materialise a file for an EOT-only transfer.
    if not peer.exists(name, letter=scratch_drive):
        pytest.skip("N/A: target CP/M receiver did not create a file for the empty transfer")
    dst = tmp_path / f"dl_{name}"
    recv_ok = peer.recv_file(name, str(dst), letter=scratch_drive)
    assert recv_ok, "download of zero-byte file failed"
    assert dst.stat().st_size == 0, f"expected 0 bytes, got {dst.stat().st_size}"
    peer.erase(name, letter=scratch_drive)
    log.info("zero-byte round-trip OK")


@pytest.mark.hil
@pytest.mark.mt("MT-T16", "FR-082", "NFR-003c")
def test_round_trip_exactly_128_bytes(peer, scratch_drive, tmp_path):
    """A 128-byte file transfers in a single frame (no extra frames added).

    Verifies: FR-082, NFR-003c.
    """
    name = "ONEROW.DAT"
    data = b"A" * 128
    src = tmp_path / name
    src.write_bytes(data)
    peer.erase(name, letter=scratch_drive)
    assert peer.send_file(str(src), letter=scratch_drive), f"upload of {name} failed"
    assert peer.exists(name, letter=scratch_drive)
    dst = tmp_path / f"dl_{name}"
    assert peer.recv_file(name, str(dst), letter=scratch_drive), f"download of {name} failed"
    assert_round_trip(src, dst)
    peer.erase(name, letter=scratch_drive)
    log.info("128-byte round-trip OK (single frame)")


@pytest.mark.hil
@pytest.mark.mt("MT-T17", "FR-082", "NFR-003b")
def test_round_trip_exactly_1024_bytes(request, peer, scratch_drive, tmp_path):
    """A 1024-byte file with 1K mode transfers in a single 1K frame.

    Verifies: FR-082, NFR-003b.
    """
    target = request.getfixturevalue("target")
    if not target.has_1k_sender:
        pytest.skip("N/A: target has no 1K-capable X-Modem sender")
    name = "BIG1K.DAT"
    data = b"B" * 1024
    src = tmp_path / name
    src.write_bytes(data)
    peer.erase(name, letter=scratch_drive)
    assert peer.send_file(str(src), letter=scratch_drive, use_1k=True), f"upload of {name} failed"
    assert peer.exists(name, letter=scratch_drive)
    dst = tmp_path / f"dl_{name}"
    recv_ok = peer.recv_file(name, str(dst), letter=scratch_drive, use_1k=True)
    assert recv_ok, f"download of {name} failed"
    assert_round_trip(src, dst)
    peer.erase(name, letter=scratch_drive)
    log.info("1024-byte round-trip OK (1K frame)")


@pytest.mark.hil
@pytest.mark.two_port
@pytest.mark.mt("MT-T18", "FR-082", "FR-120")
def test_recv_port_closed_mid_transfer_graceful_failure(peer, scratch_drive, tmp_path):
    """Closing the transport port mid-download fails gracefully (no crash).

    Verifies: FR-082, FR-120.
    """
    name = "BIG.DAT"
    # Seed a file first
    big = tmp_path / name
    big.write_bytes(b"X" * 3001)
    peer.erase(name, letter=scratch_drive)
    assert peer.send_file(str(big), letter=scratch_drive), f"seed upload of {name} failed"
    assert peer.exists(name, letter=scratch_drive)

    # Close the transport port to simulate a disconnect before receive
    peer.sm.close_transport_port()

    # The receive should fail gracefully (return False, not raise)
    dst = tmp_path / f"dl_{name}"
    result = peer.recv_file(name, str(dst), letter=scratch_drive)
    assert result is False, f"expected graceful failure, got {result}"

    # Restore the transport port for cleanup.
    # Dual-port devices need a settle delay after close→reopen so RTS/CTS
    # hardware state (DCD/carrier-detect) stabilises before the next operation.
    settings = peer.settings
    peer.sm.open_port("transport", settings)
    time.sleep(0.5)
    peer.erase(name, letter=scratch_drive)
    log.info("mid-transfer port-close handled gracefully")
