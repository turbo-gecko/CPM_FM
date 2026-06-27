"""§11.2 — transfer history persistence over real serial (MT-TH*).

A live upload records a real entry in the (temp-isolated) transfer-history JSON
store, including the file name, direction, and a success outcome (FR-140/FR-142).
"""

from __future__ import annotations

import json

import pytest
from helpers.dialogs import answer_file_action, silence_message_boxes


@pytest.mark.hil
@pytest.mark.mt("MT-TH01", "FR-140", "FR-142")
def test_upload_records_history_entry(gui, scratch_drive, monkeypatch, tmp_path):
    """A successful upload appends a success record naming the file.

    Verifies: FR-140, FR-142.
    """
    silence_message_boxes(monkeypatch)
    assert gui.connect()[0] == "ok"
    gui.set_drive(scratch_drive)

    name = "HIST.TXT"
    (tmp_path / "host" / name).write_bytes(b"history payload\r\n")
    gui.refresh_remote()
    if name.upper() in {n.upper() for n in gui.remote_names()}:
        answer_file_action(monkeypatch, accepted=True)
        gui.win._remote_delete(name)
        gui.quiesce()

    gui.upload([name])
    assert name in gui.remote_names()

    history_path = tmp_path / "history.json"
    assert history_path.exists(), "history file was never written"
    data = json.loads(history_path.read_text())
    text = json.dumps(data)
    assert name in text, f"{name} not recorded in transfer history"
    assert "success" in text, "no success outcome recorded"

    answer_file_action(monkeypatch, accepted=True)
    gui.win._remote_delete(name)
    gui.quiesce()
