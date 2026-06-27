"""§11.4 — CP/M 8.3 filename validation on upload (MT-FV*).

A host file whose name is not valid CP/M 8.3 triggers ``invalid_name_detected``
before the upload; the user can Rename (upload under a conforming name) or Skip.
"""

from __future__ import annotations

import pytest
from helpers.dialogs import (
    RENAME,
    SKIP,
    answer_file_action,
    answer_invalid_name,
    silence_message_boxes,
)

from cpm_fm.terminal.cpm_parser import CPMParser

BAD_NAME = "TOOLONGNAME.TXT"  # 11-char base — not valid 8.3


@pytest.fixture
def invalid_spy(gui):
    hits = []
    gui.win.invalid_name_detected.connect(lambda name: hits.append(name))
    return hits


@pytest.mark.hil
@pytest.mark.mt("MT-FV01", "FR-148", "FR-149")
def test_invalid_name_rename_uploads_conforming(
    gui, scratch_drive, monkeypatch, invalid_spy, tmp_path
):
    """An invalid name prompts; Rename uploads under the suggested 8.3 name.

    Verifies: FR-148, FR-149.
    """
    assert not CPMParser.is_valid_8_3(BAD_NAME)
    suggested = CPMParser.suggest_8_3(BAD_NAME)
    silence_message_boxes(monkeypatch)
    assert gui.connect()[0] == "ok"
    gui.set_drive(scratch_drive)

    (tmp_path / "host" / BAD_NAME).write_bytes(b"needs a legal name\r\n")
    # Clean any leftover from a prior run.
    gui.refresh_remote()
    if suggested.upper() in {n.upper() for n in gui.remote_names()}:
        answer_file_action(monkeypatch, accepted=True)
        gui.win._remote_delete(suggested)
        gui.quiesce()

    answer_invalid_name(monkeypatch, action=RENAME)  # accept the 8.3 suggestion
    gui.upload([BAD_NAME])
    assert invalid_spy, "invalid_name_detected never fired"
    assert suggested in gui.remote_names(), f"{suggested} not uploaded after rename"

    answer_file_action(monkeypatch, accepted=True)
    gui.win._remote_delete(suggested)
    gui.quiesce()


@pytest.mark.hil
@pytest.mark.mt("MT-FV02", "FR-148")
def test_invalid_name_skip_does_not_upload(gui, scratch_drive, monkeypatch, invalid_spy, tmp_path):
    """Skipping the name prompt leaves nothing uploaded.

    Verifies: FR-148.
    """
    suggested = CPMParser.suggest_8_3(BAD_NAME)
    silence_message_boxes(monkeypatch)
    assert gui.connect()[0] == "ok"
    gui.set_drive(scratch_drive)

    (tmp_path / "host" / BAD_NAME).write_bytes(b"do not upload\r\n")
    gui.refresh_remote()
    before = set(gui.remote_names())

    answer_invalid_name(monkeypatch, action=SKIP)
    gui.upload([BAD_NAME])
    assert invalid_spy, "invalid_name_detected never fired"
    gui.refresh_remote()
    assert suggested not in gui.remote_names()
    assert set(gui.remote_names()) == before
