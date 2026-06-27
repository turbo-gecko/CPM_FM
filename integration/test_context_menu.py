"""§13 — remote file context-menu actions over real serial (MT-F*).

Remote Rename and Delete issue the configured CP/M commands on the Terminal Port
and refresh the listing (FR-111/FR-114/FR-117/FR-118). All operations target the
disposable scratch drive.
"""

from __future__ import annotations

import pytest
from helpers.dialogs import answer_file_action, silence_message_boxes


def _seed(gui, scratch, monkeypatch, name, tmp_path, data=b"ctx payload\r\n"):
    (tmp_path / "host" / name).write_bytes(data)
    gui.set_drive(scratch)
    gui.refresh_remote()
    if name.upper() in {n.upper() for n in gui.remote_names()}:
        answer_file_action(monkeypatch, accepted=True)
        gui.win._remote_delete(name)
        gui.quiesce()
    gui.upload([name])
    assert name in gui.remote_names()


@pytest.mark.hil
@pytest.mark.mt("MT-F08", "FR-111", "FR-117", "FR-118")
def test_remote_delete_removes_file(gui, scratch_drive, monkeypatch, tmp_path):
    """Remote Delete erases the file and refreshes the listing.

    Verifies: FR-111, FR-117, FR-118.
    """
    silence_message_boxes(monkeypatch)
    assert gui.connect()[0] == "ok"
    name = "CTXDEL.TXT"
    _seed(gui, scratch_drive, monkeypatch, name, tmp_path)

    answer_file_action(monkeypatch, accepted=True)
    gui.win._remote_delete(name)
    gui.quiesce()
    assert name not in gui.remote_names()


@pytest.mark.hil
@pytest.mark.mt("MT-F07", "FR-111", "FR-114", "FR-117")
def test_remote_rename_changes_name(gui, scratch_drive, monkeypatch, tmp_path):
    """Remote Rename renames the file on the remote and refreshes.

    Verifies: FR-111, FR-114, FR-117.
    """
    silence_message_boxes(monkeypatch)
    assert gui.connect()[0] == "ok"
    old, new = "CTXOLD.TXT", "CTXNEW.TXT"
    _seed(gui, scratch_drive, monkeypatch, old, tmp_path)
    # clear any stale destination name
    if new.upper() in {n.upper() for n in gui.remote_names()}:
        answer_file_action(monkeypatch, accepted=True)
        gui.win._remote_delete(new)
        gui.quiesce()

    answer_file_action(monkeypatch, value=new, accepted=True)
    gui.win._remote_rename(old)
    gui.quiesce()

    assert new in gui.remote_names()
    assert old not in gui.remote_names()

    answer_file_action(monkeypatch, accepted=True)
    gui.win._remote_delete(new)
    gui.quiesce()
