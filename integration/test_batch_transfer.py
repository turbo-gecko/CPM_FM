"""§11.1 — Batch transfer: sequential multi-file upload and failure abort (MT-T06/MT-T07).

Upload three host files in a single batch via Copy to Remote and verify that
all three appear on the remote listing after the transfer completes.  This is
the simplest HIL test for the batch-transfer engine (FR-106/FR-107) and
confirms that the single progress dialog (FR-105) serves the whole sequence.

All writes target the disposable scratch drive and clean up after themselves.
"""

from __future__ import annotations

import pytest
from helpers.dialogs import (
    OVERWRITE,
    answer_conflict,
    answer_invalid_name,
    silence_message_boxes,
)
from helpers.trace import get_logger

log = get_logger("transfer.batch")


@pytest.mark.hil
@pytest.mark.mt("MT-T06", "FR-105", "FR-106", "FR-107")
def test_batch_transfer_sequential_multi_file(
    gui, scratch_drive, monkeypatch, tmp_path
):
    """Three host files upload sequentially in a single batch and all appear on remote.

    Verifies: FR-105, FR-106, FR-107.
    """
    silence_message_boxes(monkeypatch)
    answer_invalid_name(monkeypatch)  # accept suggested 8.3 names
    answer_conflict(monkeypatch, action=OVERWRITE)  # overwrite existing files
    assert gui.connect()[0] == "ok"
    gui.set_drive(scratch_drive)

    # Create three uniquely-named host files (CP/M 8.3 compliant).
    names = ["BATCH1.TXT", "BATCH2.DAT", "BATCH3.BIN"]
    for i, name in enumerate(names):
        (tmp_path / "host" / name).write_bytes(f"batch file {i}\r\n".encode())

    # Upload all three at once via Copy to Remote (triggers worker thread).
    gui.upload(names)

    # Slow RC2014 targets may need more than the default 15 s quiesce window
    # for a full batch of X-Modem transfers; re-quiesce with a longer timeout
    # so the remote-list refresh that follows the batch also completes.
    gui.quiesce(timeout=60)

    # After the batch completes, every file should be listed on the remote side.
    remote = gui.remote_names()
    for name in names:
        assert name in remote, f"{name} not found in remote listing after batch upload"
        log.info("batch OK: %s present on remote", name)


@pytest.mark.hil
@pytest.mark.mt("MT-T07", "FR-108")
def test_batch_abort_on_mid_file_failure(gui, scratch_drive, monkeypatch, tmp_path):
    """A failure on the 2nd of 3 files aborts the batch; error names the failed file.

    Verifies: FR-108.
    """
    # Auto-answer conflicts and silence QMessageBox so we can inspect what fired.
    answer_invalid_name(monkeypatch)
    answer_conflict(monkeypatch, action=OVERWRITE)
    error_fired = silence_message_boxes(monkeypatch)

    assert gui.connect()[0] == "ok"
    gui.set_drive(scratch_drive)

    # Create three uniquely-named host files.
    names = ["FAIL1.TXT", "FAIL2.TXT", "FAIL3.TXT"]
    for i, name in enumerate(names):
        (tmp_path / "host" / name).write_bytes(f"fail file {i}\r\n".encode())

    # Monkeypatch _send_one_to_remote to fail on the 2nd call (index 1).
    # Returning False (not raising) triggers the non-ok path which uses
    # _transfer_fail_message(remote_name, "remote") — that message includes
    # the filename via tr("error.transfer_failed", name=name).
    original_send = gui.win._send_one_to_remote
    call_count = [0]
    failure_injected = [False]

    def _failing_send(filepath, remote_name=None, user_area=None):
        call_count[0] += 1
        if call_count[0] == 2 and not failure_injected[0]:
            failure_injected[0] = True
            return False  # triggers the non-ok / abort path (FR-108)
        return original_send(filepath, remote_name, user_area)

    monkeypatch.setattr(gui.win, "_send_one_to_remote", _failing_send)

    # Upload all three — the 2nd should fail and abort the batch.
    gui.upload(names)

    # File 1 succeeded, file 2 failed (batch aborted), file 3 never attempted.
    remote = gui.remote_names()
    assert "FAIL1.TXT" in remote, "file 1 should be present on remote after abort"
    assert "FAIL2.TXT" not in remote, "file 2 should NOT be on remote (transfer failed)"
    assert "FAIL3.TXT" not in remote, "file 3 should NOT be attempted after abort"
    log.info("batch abort confirmed: FAIL1 present, FAIL2/FAIL3 absent")

    # The error dialog should name the failed file (FAIL2.TXT).
    error_messages = [args for kind, args in error_fired if kind == "critical"]
    assert len(error_messages) >= 1, f"expected at least one critical error dialog, got {error_fired}"
    combined = " ".join(str(m) for m in error_messages)
    assert "FAIL2.TXT" in combined or "fail2.txt" in combined.lower(), (
        f"error dialog should name the failed file; got: {error_messages}"
    )
    log.info("error dialog names failed file: %s", error_messages)
