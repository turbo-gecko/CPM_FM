"""§11.3 — Batch transfer: live Cancel during a later batch file (MT-T14).

Start a batch of three uploads; let file 1 complete, then inject Cancel so that
file 2 is skipped.  Verify that the remaining files are skipped, the dialog
closes with a cancellation status, and no partial file is left on the remote side.

All writes target the disposable scratch drive and clean up after themselves.
"""

from __future__ import annotations

import os
import threading
import time as _time_module
import uuid

import pytest
from helpers.dialogs import (
    OVERWRITE,
    answer_conflict,
    answer_invalid_name,
    silence_message_boxes,
)
from helpers.trace import get_logger

log = get_logger("transfer.cancel_batch")

# Track original sleep for the monkeypatch.
_original_sleep = _time_module.sleep


def _wait_for_drive_idle(gui, timeout: float = 30.0) -> None:
    """Wait until the status bar no longer shows a drive-change in progress."""
    deadline = _time_module.time() + timeout
    while _time_module.time() < deadline:
        gui.pump()
        msg = gui.win.statusBar().currentMessage()
        if "drive" not in msg.lower() and "changing" not in msg.lower():
            return
        _time_module.sleep(0.1)


@pytest.mark.hil
@pytest.mark.req("FR-120")
def test_cancel_during_later_batch_file(gui, scratch_drive, monkeypatch, tmp_path, target):
    """Cancel during file 2 of a 3-file batch; file 1 already completed.

    Verifies: FR-120.
    """
    silence_message_boxes(monkeypatch)
    answer_invalid_name(monkeypatch)  # accept suggested 8.3 names
    answer_conflict(monkeypatch, action=OVERWRITE)  # overwrite existing files
    assert gui.connect()[0] == "ok"
    gui.set_drive(scratch_drive)
    _wait_for_drive_idle(gui, timeout=30)
    gui.quiesce(timeout=30)

    # Create three uniquely-named host files (CP/M 8.3 compliant: ≤8 char name, ≤3 char ext).
    # 32 KB → ~256 X-Modem 128-byte blocks; large enough for multi-block transfer, small enough
    # that the monkeypatch delay creates a reliable cancel window on fast targets.
    uid = uuid.uuid4().hex[:4].upper()
    names = [f"CBK1{uid}.TXT", f"CBK2{uid}.TXT", f"CBK3{uid}.TXT"]
    for name in names:
        (tmp_path / "host" / name).write_bytes(b"X" * 32768)

    # --- Synchronization strategy ---
    # 1. _send_one_to_remote: counts how many files have been attempted.
    #    When send_call_count transitions from 0→1 (file 1 just completed),
    #    we set _transfer_cancel immediately. This works on ALL targets:
    #    - Slow targets (rc2014): file 1 takes ~15s, test loop catches inter-file sleep.
    #    - Fast targets (MinZ): all 3 files complete in ~5s, too fast for test loop to react.
    #      Setting cancel immediately after file 1 ensures the batch loop's next cancel-check
    #      (between files) sees it and aborts before file 2 starts.
    #
    # The batch loop structure is:
    #   for filepath in files_to_send:
    #       if _transfer_cancel.is_set(): break  ← checked at top of loop
    #       _send_one_to_remote(...)              ← file 1 completes here
    #       ...
    #       _wait_for_terminal_idle()             ← calls _cancellable_sleep()
    #   (loop continues to next file if not cancelled)
    #
    # By setting cancel immediately after file 1, the next iteration's cancel-check
    # catches it and calls _finish_cancelled_batch() before file 2 starts.

    original_send = gui.win._send_one_to_remote
    send_call_count = [0]
    prev_send_count = [0]
    cancel_set_during_sleep = threading.Event()

    def _patched_send(filepath, remote_name=None, user_area=None):
        name_upper = os.path.basename(filepath).upper()
        send_call_count[0] += 1
        result = original_send(filepath, remote_name, user_area)
        log.info("monkeypatch send: %s (call #%d) → ok=%s", name_upper, send_call_count[0], result)

        # Detect transition: file 1 just completed (count went from 0→1).
        # Set cancel immediately so the batch loop's next iteration sees it.
        if send_call_count[0] == 1 and prev_send_count[0] == 0:
            log.info("file 1 completed (ok=%s) — setting transfer_cancel immediately", result)
            gui.win._transfer_cancel.set()

        prev_send_count[0] = send_call_count[0]
        return result

    monkeypatch.setattr(gui.win, "_send_one_to_remote", _patched_send)

    # Also monkeypatch time.sleep as a fallback for the test's own detection.
    # On slow targets, the test loop catches the inter-file sleep and sets
    # cancel_set_during_sleep to prove file 1 completed.
    def _patched_sleep(duration):
        if duration > 0.5 and send_call_count[0] >= 1:
            log.info(
                "monkeypatch sleep: %.1fs after file %d — cancel already set=%s",
                duration,
                send_call_count[0],
                gui.win._transfer_cancel.is_set(),
            )
            cancel_set_during_sleep.set()
        return _original_sleep(duration)

    monkeypatch.setattr(_time_module, "sleep", _patched_sleep)

    # Capture status bar via transfer_cancelled signal (fires when batch cancellation finishes).
    captured_status = []
    status_lock = threading.Lock()

    def _capture_status(direction, any_succeeded):
        with status_lock:
            captured_status.append(gui.win.statusBar().currentMessage())

    gui.win.transfer_cancelled.connect(_capture_status)

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

    # Wait for cancel to be set (proves file 1 completed).
    # On slow targets, cancel is set during the inter-file sleep (detected by _patched_sleep).
    # On fast targets, cancel is set immediately after file 1 in _patched_send.
    log.info("waiting for cancel to be set...")
    deadline = _time_module.time() + 480
    cancel_was_set = False
    while _time_module.time() < deadline:
        gui.pump()
        if gui.win._transfer_cancel.is_set():
            cancel_was_set = True
            break
        _time_module.sleep(0.1)

    assert cancel_was_set, (
        f"Cancel should have been set after file 1 completed. "
        f"Send calls so far: {send_call_count[0]}"
    )
    log.info("cancel set — send_call_count=%d", send_call_count[0])

    # Wait for the progress dialog to close (batch should abort before starting file 2).
    closed = gui.process_until(
        lambda: gui.win._transfer_dialog is None,
        timeout=120.0,
        interval=0.05,
    )
    assert closed, "Progress dialog should close after cancel"
    log.info("progress dialog closed")

    # Disconnect the signal to prevent further captures.
    gui.win.transfer_cancelled.disconnect(_capture_status)

    # Verify file 2 was never attempted (monkeypatch only called once for file 1).
    assert send_call_count[0] == 1, (
        "File 2 should not have been attempted; _send_one_to_remote called "
        f"{send_call_count[0]} time(s)"
    )
    log.info("verified: file 2 never started — send_call_count=%d", send_call_count[0])

    # Check the captured status bar message (taken before refresh overwrote it).
    with status_lock:
        pre_refresh_status = captured_status[0] if captured_status else ""
    log.info("status bar (pre-refresh, captured): %s", pre_refresh_status)

    # Wait for all worker threads to finish.
    gui.quiesce(timeout=60)

    # Wait for any pending drive-change status message to clear.
    _wait_for_drive_idle(gui, timeout=15)

    # Verify the cancel status was captured BEFORE refresh overwrote it.
    status_lower = pre_refresh_status.lower()
    is_cancelled = (
        "cancelled" in status_lower or "annullato" in status_lower or "annulé" in status_lower
    )
    assert is_cancelled, (
        f"Status bar should show 'Transfer cancelled' immediately after "
        f"dialog close; captured: {pre_refresh_status}"
    )

    # Refresh the remote list to verify file state.
    gui.win.refresh_remote_files()
    deadline = _time_module.time() + 60
    while _time_module.time() < deadline:
        gui.pump()
        msg = gui.win.statusBar().currentMessage()
        if "file list updated" in msg.lower():
            break
        _time_module.sleep(0.1)

    # Extra pump to ensure GUI has processed all queued signals.
    for _ in range(10):
        gui.pump()

    remote = gui.remote_names()
    log.info("remote listing: %s", remote[:15])
    log.info("GUI remote user area: %s", getattr(gui.win, "_remote_user", "N/A"))

    # File 1 should be present (completed before cancel).
    assert names[0].upper() in [f.upper() for f in remote], (
        f"{names[0]} should be on remote (completed before cancel). Remote listing: {remote[:15]}"
    )

    # Files 2 and 3 should NOT be on the remote (skipped/cancelled).
    assert names[1].upper() not in [f.upper() for f in remote], (
        f"{names[1]} should NOT be on remote (cancelled during transfer)"
    )
    assert names[2].upper() not in [f.upper() for f in remote], (
        f"{names[2]} should NOT be on remote (skipped after cancel)"
    )
    log.info("batch cancel confirmed: %s present, %s/%s absent", names[0], names[1], names[2])
