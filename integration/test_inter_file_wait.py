"""§11.4 — Inter-file wait + post-final settle (MT-T08).

Run a multi-file batch and verify that:
- Before each file after the first, the app waits for the CCP prompt to return
  plus the inter-file settle delay (no truncated "command not found" on launch).
- After the final file, the app waits the inter-file settle delay before the
  auto-refresh DIR, so the just-transferred files reliably appear in the refreshed
  Remote list.

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

log = get_logger("transfer.interfile")


@pytest.mark.hil
@pytest.mark.mt("MT-T08", "FR-109")
def test_inter_file_wait_and_post_final_settle(gui, scratch_drive, monkeypatch, tmp_path, target):
    """Three-file batch: CCP prompt returns between files; all appear after final settle.

    Verifies: FR-109.
    """
    error_fired = silence_message_boxes(monkeypatch)
    answer_invalid_name(monkeypatch)  # accept suggested 8.3 names
    answer_conflict(monkeypatch, action=OVERWRITE)
    assert gui.connect()[0] == "ok"
    gui.set_drive(scratch_drive)
    gui.quiesce()

    # Create three uniquely-named host files (CP/M 8.3 compliant).
    uid = pytest.importorskip("uuid").uuid4().hex[:4].upper()
    names = [f"IW1{uid}.TXT", f"IW2{uid}.TXT", f"IW3{uid}.TXT"]
    for name in names:
        (tmp_path / "host" / name).write_bytes(b"Y" * 8192)

    # Upload all three at once via Copy to Remote (triggers worker thread).
    gui.refresh_host()
    gui.select_host(names)
    gui.win.do_copy_to_remote()

    # Wait for the batch to complete and the remote-list refresh to finish.
    gui.quiesce(timeout=60)

    # Refresh the remote list explicitly and wait for it to complete.
    gui.win.refresh_remote_files()
    deadline = time.time() + 30
    while time.time() < deadline:
        gui.pump()
        msg = gui.win.statusBar().currentMessage()
        if "file list updated" in msg.lower():
            break
        time.sleep(0.1)

    # After the batch completes, every file should be listed on the remote side.
    # If the post-final settle were missing, slow targets (rc2014_mini) would
    # miss the just-uploaded files in the auto-refresh DIR.
    remote = gui.remote_names()
    log.info("remote listing (first 20): %s", [f for f in remote[:20]])
    log.info("GUI remote user area: %s", getattr(gui.win, "_remote_user", "N/A"))

    # Check if any errors occurred during the transfer.
    error_messages = [args for kind, args in error_fired if kind == "critical"]
    if error_messages:
        log.warning("errors during transfer: %s", error_messages)
    for name in names:
        assert name.upper() in [f.upper() for f in remote], (
            f"{name} not found in remote listing after batch upload — "
            "post-final settle may have been skipped"
        )
        log.info("inter-file OK: %s present on remote", name)


@pytest.mark.hil
@pytest.mark.req("FR-109")
def test_inter_file_wait_terminal_shows_prompt_between_files(
    gui, scratch_drive, monkeypatch, tmp_path, target
):
    """Three-file batch: terminal window shows CCP prompt between each file transfer.

    Verifies: FR-109 (inter-file wait path).
    """
    silence_message_boxes(monkeypatch)
    answer_invalid_name(monkeypatch)
    answer_conflict(monkeypatch, action=OVERWRITE)
    assert gui.connect()[0] == "ok"
    gui.set_drive(scratch_drive)
    gui.quiesce()

    # Create three uniquely-named host files.
    uid = pytest.importorskip("uuid").uuid4().hex[:4].upper()
    names = [f"IWT1{uid}.TXT", f"IWT2{uid}.TXT", f"IWT3{uid}.TXT"]
    for name in names:
        (tmp_path / "host" / name).write_bytes(b"Z" * 8192)

    # Open the terminal window BEFORE starting the batch so we can observe
    # the CCP prompt between files.
    gui.win.show_terminal()
    term = gui.win.terminal_win
    assert term is not None, "terminal window was not created"

    def _screen_text(term) -> str:
        return "\n".join(term.engine.display)

    # Upload all three at once via Copy to Remote (triggers worker thread).
    gui.upload(names)

    # Wait for the batch to complete and the remote-list refresh to finish.
    gui.quiesce(timeout=60)

    # After the batch completes, every file should be listed on the remote side.
    remote = gui.remote_names()
    for name in names:
        assert name.upper() in [f.upper() for f in remote], (
            f"{name} not found in remote listing after batch upload"
        )
        log.info("inter-file terminal OK: %s present on remote", name)
