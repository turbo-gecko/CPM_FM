"""§11.3 — destination-conflict resolution over real serial (MT-CF*).

Upload a file, then upload it again so the live remote listing reports a
conflict; the worker raises ``conflict_detected`` and we auto-answer
Overwrite / Skip. All writes go to the disposable scratch drive.
"""

from __future__ import annotations

import pytest
from helpers.dialogs import (
    OVERWRITE,
    SKIP,
    answer_conflict,
    answer_file_action,
    silence_message_boxes,
)


def _ensure_absent(gui, monkeypatch, scratch, name):
    gui.set_drive(scratch)
    gui.refresh_remote()
    if name.upper() in {n.upper() for n in gui.remote_names()}:
        answer_file_action(monkeypatch, accepted=True)
        gui.win._remote_delete(name)
        gui.quiesce()


@pytest.fixture
def conflict_spy(gui):
    hits = []
    gui.win.conflict_detected.connect(lambda name, direction: hits.append((name, direction)))
    return hits


@pytest.mark.hil
@pytest.mark.mt("MT-CF01", "FR-145", "FR-146")
def test_overwrite_existing_remote_file(gui, scratch_drive, monkeypatch, conflict_spy, tmp_path):
    """A second upload of the same name prompts, and Overwrite replaces it.

    Verifies: FR-145, FR-146.
    """
    silence_message_boxes(monkeypatch)
    assert gui.connect()[0] == "ok"
    gui.set_drive(scratch_drive)

    name = "CFLICT.TXT"
    (tmp_path / "host" / name).write_bytes(b"first version\r\n")
    _ensure_absent(gui, monkeypatch, scratch_drive, name)

    gui.upload([name])  # first upload — no conflict
    assert name in gui.remote_names()

    answer_conflict(monkeypatch, action=OVERWRITE)
    gui.upload([name])  # second upload — conflict -> Overwrite
    assert conflict_spy, "conflict_detected never fired on the duplicate upload"
    assert name in gui.remote_names()

    answer_file_action(monkeypatch, accepted=True)
    gui.win._remote_delete(name)
    gui.quiesce()


@pytest.mark.hil
@pytest.mark.mt("MT-CF02", "FR-145", "FR-147")
def test_skip_existing_remote_file(gui, scratch_drive, monkeypatch, conflict_spy, tmp_path):
    """Skip on a conflict leaves the existing remote file and records a skip.

    Verifies: FR-145, FR-147.
    """
    silence_message_boxes(monkeypatch)
    assert gui.connect()[0] == "ok"
    gui.set_drive(scratch_drive)

    name = "CFSKIP.TXT"
    (tmp_path / "host" / name).write_bytes(b"keep me\r\n")
    _ensure_absent(gui, monkeypatch, scratch_drive, name)

    gui.upload([name])
    assert name in gui.remote_names()

    answer_conflict(monkeypatch, action=SKIP)
    gui.upload([name])
    assert conflict_spy, "conflict_detected never fired"
    assert name in gui.remote_names()  # still present (skipped, not removed)

    answer_file_action(monkeypatch, accepted=True)
    gui.win._remote_delete(name)
    gui.quiesce()
