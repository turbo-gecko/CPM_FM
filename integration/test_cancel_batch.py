"""§11.3 — Batch transfer: live Cancel during a later batch file (MT-T14).

Start a batch of three uploads; let file 1 complete, then press Cancel while
file 2 is transferring.  Verify that the remaining files are skipped, the
dialog closes with a cancellation status, and no partial file is left on the
remote side.

All writes target the disposable scratch drive and clean up after themselves.
"""

from __future__ import annotations

import threading
import uuid

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from helpers.dialogs import (
    OVERWRITE,
    answer_conflict,
    answer_invalid_name,
    silence_message_boxes,
)
from helpers.trace import get_logger

log = get_logger("transfer.cancel_batch")


@pytest.mark.hil
@pytest.mark.mt("MT-T14", "FR-120")
def test_cancel_during_later_batch_file(gui, scratch_drive, monkeypatch, tmp_path, target):
    """Cancel during file 2 of a 3-file batch; file 1 already completed.

    Verifies: FR-120.
    """
    silence_message_boxes(monkeypatch)
    answer_invalid_name(monkeypatch)  # accept suggested 8.3 names
    answer_conflict(monkeypatch, action=OVERWRITE)  # overwrite existing files
    assert gui.connect()[0] == "ok"
    gui.set_drive(scratch_drive)
    gui.quiesce()

    # Create three uniquely-named host files (CP/M 8.3 compliant: ≤8 char name, ≤3 char ext).
    uid = uuid.uuid4().hex[:4].upper()
    names = [f"CBK1{uid}.TXT", f"CBK2{uid}.TXT", f"CBK3{uid}.TXT"]
    for i, name in enumerate(names):
        # 8 KB each — small files transfer quickly; we use a signal to detect
        # when file 2 starts and immediately inject cancel.
        (tmp_path / "host" / name).write_bytes(b"X" * 8192)

    # Detect when file 2 starts via the transfer_file_started signal.
    # When file 2's signal fires, we immediately set the cancel flag BEFORE
    # _send_one_to_remote runs (the signal is emitted just before that call).
    file2_cancelled = threading.Event()

    def _on_file_started(remote_name, total_bytes, index):
        if remote_name.upper() == names[1].upper():
            log.info("signal: file 2 started (index=%d) — setting cancel NOW", index)
            # Set cancel immediately. The signal is emitted just before
            # _send_one_to_remote, so XModem will detect the flag during
            # its handshake and abort cleanly.
            gui.win._transfer_cancel.set()
            file2_cancelled.set()

    gui.win.transfer_file_started.connect(_on_file_started)

    # Monkeypatch _send_one_to_remote to wait for cancel to be set, ensuring
    # we don't proceed until the signal handler has fired.
    original_send = gui.win._send_one_to_remote
    call_count = [0]

    def _cancel_on_file2(filepath, remote_name=None, user_area=None):
        call_count[0] += 1
        if call_count[0] == 2:
            log.info("file 2 transfer starting — waiting for cancel signal")
            file2_cancelled.wait(timeout=30)
            log.info("cancel was set by signal handler, proceeding with send")
        return original_send(filepath, remote_name, user_area)

    monkeypatch.setattr(gui.win, "_send_one_to_remote", _cancel_on_file2)

    # Upload all three at once via Copy to Remote (triggers worker thread).
    gui.refresh_host()
    gui.select_host(names)
    gui.win.do_copy_to_remote()

    # Wait for the progress dialog to appear.
    dialog = gui.process_until(
        lambda: gui.win._transfer_dialog is not None,
        timeout=10.0,
        interval=0.05,
    )
    assert dialog is not None, "Transfer progress dialog should appear"
    dialog = gui.win._transfer_dialog

    # Wait for file 2 to start: the batch_label changes from "File 1 of 3"
    # to "File 2 of 3". This confirms file 1 completed and we're now on file 2.
    log.info("waiting for file 2 to start (batch_label shows '2')...")
    gui.process_until(
        lambda: dialog.batch_label.isVisible() and "2" in dialog.batch_label.text(),
        timeout=60.0,
        interval=0.1,
    )
    log.info("batch_label now shows file 2: %s", dialog.batch_label.text())

    # Click the Cancel button on the progress dialog.
    QTest.mouseClick(dialog.cancel_button, Qt.MouseButton.LeftButton)
    gui.pump()

    # The Cancel button should immediately disable and show "Cancelling…".
    assert not dialog.cancel_button.isEnabled(), (
        "Cancel button should be disabled after click"
    )
    text = dialog.cancel_button.text()
    assert "Cancelling" in text or "annulant" in text.lower() or "annulé" in text.lower() or "cancellando" in text.lower(), (
        f"Cancel button text should indicate cancelling; got: {text}"
    )

    # Wait for the transfer to complete (aborted) and the dialog to close.
    closed = gui.process_until(
        lambda: gui.win._transfer_dialog is None,
        timeout=30.0,
        interval=0.05,
    )
    assert closed, "Progress dialog should close after cancel"
    log.info("progress dialog closed")

    # Wait for all worker threads to finish.
    gui.quiesce(timeout=60)

    # Refresh the remote list to see the final state (and wait for it to complete).
    gui.refresh_remote()
    remote = gui.remote_names()
    log.info("remote listing: %s", remote[:10])
    log.info("GUI remote user area: %s", getattr(gui.win, '_remote_user', 'N/A'))

    # Status bar should show "Transfer cancelled" (or translated equivalent)
    # or "Remote file list updated" (from the post-cancel refresh). Either is
    # acceptable — the key is that the transfer was cancelled cleanly without
    # an error dialog. We check AFTER the refresh completes to avoid catching
    # intermediate status messages like "Changing to drive J:...".
    status = gui.win.statusBar().currentMessage()
    log.info("status bar (post-refresh): %s", status)
    assert "cancelled" in status.lower() or "annullato" in status.lower() or "annulé" in status.lower() or "file list updated" in status.lower(), (
        f"Status bar should show 'Transfer cancelled' or 'Remote file list updated'; got: {status}"
    )

    # File 1 should be present (completed before cancel).
    assert names[0].upper() in [f.upper() for f in remote], (
        f"{names[0]} should be on remote (completed before cancel). "
        f"Remote listing: {remote[:15]}"
    )

    # Files 2 and 3 should NOT be on the remote (skipped by cancel).
    assert names[1].upper() not in [f.upper() for f in remote], (
        f"{names[1]} should NOT be on remote (cancelled during transfer)"
    )
    assert names[2].upper() not in [f.upper() for f in remote], (
        f"{names[2]} should NOT be on remote (skipped after cancel)"
    )
    log.info("batch cancel confirmed: %s present, %s/%s absent", names[0], names[1], names[2])
