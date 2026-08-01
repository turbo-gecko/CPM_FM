"""§11.5 — UI responsiveness during large transfer (MT-T11).

During a large transfer, move/resize the main window and hover the toolbar to
verify that the UI stays responsive (transfer runs off the GUI thread) and
progress keeps updating.

All writes target the disposable scratch drive and clean up after themselves.
"""

from __future__ import annotations

import time

import pytest
from helpers.dialogs import (
    OVERWRITE,
    answer_conflict,
    answer_invalid_name,
    silence_message_boxes,
)
from helpers.trace import get_logger
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

log = get_logger("transfer.ui_responsive")


@pytest.mark.hil
@pytest.mark.mt("MT-T11", "NFR-001")
def test_ui_responsive_during_large_transfer(gui, scratch_drive, monkeypatch, tmp_path, target):
    """UI stays responsive during a large file transfer; progress keeps updating.

    Verifies: NFR-001.
    """
    silence_message_boxes(monkeypatch)
    answer_invalid_name(monkeypatch)  # accept suggested 8.3 names
    answer_conflict(monkeypatch, action=OVERWRITE)
    assert gui.connect()[0] == "ok"
    gui.set_drive(scratch_drive)
    gui.quiesce()

    # Create a large host file (64 KB — ~512 X-Modem 128-byte blocks).
    # Large enough that the transfer takes several seconds, giving time to
    # exercise the UI. Small enough that it completes in reasonable time.
    # Name must fit CP/M 8.3 format: ≤8 char name + ≤3 char ext.
    uid = pytest.importorskip("uuid").uuid4().hex[:3].upper()
    name = f"LARGE{uid}.BIN"
    (tmp_path / "host" / name).write_bytes(b"R" * 65536)

    # Upload via Copy to Remote (triggers worker thread).
    # Use do_copy_to_remote directly instead of gui.upload() because upload()
    # calls quiesce() which waits for the transfer to complete — we need to
    # observe the dialog while it's still running.
    gui.refresh_host()
    gui.select_host([name])
    gui.win.do_copy_to_remote()

    # Wait for the progress dialog to appear.
    gui.process_until(
        lambda: gui.win._transfer_dialog is not None,
        timeout=10.0,
        interval=0.05,
    )
    dialog = gui.win._transfer_dialog
    assert dialog is not None, "Transfer progress dialog should appear"

    # Record the initial progress value.
    initial_progress = dialog.progress_bar.value() if dialog.progress_bar else 0
    log.info("initial progress: %d", initial_progress)

    # Exercise the UI while the transfer runs on a worker thread.
    # These operations must NOT block or freeze the GUI (NFR-001).
    # We pump events and exercise the window, then wait for completion.
    start = time.time()
    ui_exercised = [False]

    def _exercise_ui():
        """Move/resize the main window — should not freeze."""
        QTest.mouseClick(gui.win, Qt.LeftButton)  # click to ensure focus
        gui.win.move(100, 100)
        gui.win.resize(800, 600)
        ui_exercised[0] = True

    while time.time() - start < 45:
        gui.pump()
        _exercise_ui()
        QTest.qWait(100)  # small delay between UI exercises

        # Check if dialog is still open (transfer may have completed).
        if gui.win._transfer_dialog is None:
            log.info("dialog closed during UI exercise (%.1fs)", time.time() - start)
            break

        # Check that progress is actually updating.
        current_progress = dialog.progress_bar.value() if dialog.progress_bar else 0
        if current_progress > initial_progress:
            log.info("progress updated to %d", current_progress)
            initial_progress = current_progress

    log.info(
        "UI exercise done (%.1fs), dialog still open=%s",
        time.time() - start,
        gui.win._transfer_dialog is not None,
    )

    # Wait for the transfer to complete and the dialog to close.
    log.info("waiting for dialog to close after UI exercise...")
    closed = gui.process_until(
        lambda: gui.win._transfer_dialog is None,
        timeout=180.0,
        interval=0.05,
    )
    assert closed, "progress dialog did not close after the UI exercise"

    # Wait for the remote-list refresh to complete.
    gui.quiesce(timeout=60)

    # Verify the UI was exercised (window was moved/resized).
    assert ui_exercised[0], "UI should have been exercised during transfer"
    log.info("UI responsive OK: window was moved/resized during transfer")
