"""§11.1 — drag-and-drop transfers over real serial (MT-D*).

Exercises the drop entry point ``_on_files_dropped`` (the same worker the Copy
buttons use), including the drag-and-drop confirmation (FR-137).
"""

from __future__ import annotations

import pytest
from helpers.dialogs import answer_confirm, answer_file_action, silence_message_boxes


@pytest.mark.hil
@pytest.mark.mt("MT-D01", "FR-137", "FR-138")
def test_internal_drop_host_to_remote_uploads(gui, scratch_drive, monkeypatch, tmp_path):
    """Dropping a host file onto the Remote pane uploads it after confirmation.

    Verifies: FR-137, FR-138.
    """
    silence_message_boxes(monkeypatch)
    assert gui.connect()[0] == "ok"
    gui.set_drive(scratch_drive)
    answer_confirm(monkeypatch, gui.win, accept=True)

    name = "DROP.TXT"
    (tmp_path / "host" / name).write_bytes(b"dropped payload\r\n")
    gui.refresh_host()
    if name.upper() in {n.upper() for n in gui.remote_names()}:
        answer_file_action(monkeypatch, accepted=True)
        gui.win._remote_delete(name)
        gui.quiesce()

    # Internal drag from the Host pane: payload is a list of names, external=False.
    gui.win._on_files_dropped("remote", "host", [name], False)
    gui.quiesce()

    assert name in gui.remote_names()

    answer_file_action(monkeypatch, accepted=True)
    gui.win._remote_delete(name)
    gui.quiesce()


@pytest.mark.hil
@pytest.mark.mt("MT-D05", "FR-137")
def test_drop_cancelled_does_not_transfer(gui, scratch_drive, monkeypatch, tmp_path):
    """Declining the drag-and-drop confirmation transfers nothing.

    Verifies: FR-137.
    """
    silence_message_boxes(monkeypatch)
    assert gui.connect()[0] == "ok"
    gui.set_drive(scratch_drive)
    answer_confirm(monkeypatch, gui.win, accept=False)  # user cancels the drop

    name = "NODROP.TXT"
    (tmp_path / "host" / name).write_bytes(b"should not arrive\r\n")
    gui.refresh_remote()
    before = set(gui.remote_names())

    gui.win._on_files_dropped("remote", "host", [name], False)
    gui.quiesce()

    gui.refresh_remote()
    assert set(gui.remote_names()) == before
