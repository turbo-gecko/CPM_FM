"""§11.5 — whole-drive Backup / Restore (MT-BR*). DESTRUCTIVE.

Restore WIPES the remote scratch drive then uploads every host file; Backup
wipes the host dir then downloads every remote file. These are double-gated
(``--run-destructive`` + scratch_drive != connect_drive) and always operate on
the operator-nominated disposable scratch drive.
"""

from __future__ import annotations

import pytest
from helpers.dialogs import answer_confirm, answer_file_action, silence_message_boxes

pytestmark = [pytest.mark.hil, pytest.mark.destructive]


def _clear_remote(gui, monkeypatch, name):
    if name.upper() in {n.upper() for n in gui.remote_names()}:
        answer_file_action(monkeypatch, accepted=True)
        gui.win._remote_delete(name)
        gui.quiesce()


@pytest.mark.mt("MT-BR05", "FR-151", "FR-152", "FR-153", "FR-154")
def test_restore_wipes_scratch_then_uploads(gui, scratch_drive, monkeypatch, tmp_path):
    """Restore erases the scratch drive and uploads every host file.

    Verifies: FR-151, FR-152, FR-153, FR-154.
    """
    silence_message_boxes(monkeypatch)
    answer_confirm(monkeypatch, gui.win, accept=True)
    assert gui.connect()[0] == "ok"
    gui.set_drive(scratch_drive)
    assert gui.win.drive_combo.currentText() == f"{scratch_drive}:"  # safety: on scratch

    host = tmp_path / "host"
    payload = {"REST1.TXT": b"restore one\r\n", "REST2.TXT": b"restore two\r\n"}
    for fname, data in payload.items():
        (host / fname).write_bytes(data)

    # Seed a leftover on the scratch drive that Restore must wipe away.
    leftover = "LEFTOVER.TXT"
    (host / leftover).write_bytes(b"should be wiped\r\n")
    gui.upload([leftover])
    assert leftover in gui.remote_names()
    (host / leftover).unlink()  # remove from host so Restore won't re-upload it

    gui.win.do_restore()
    gui.quiesce(timeout=60.0)

    remote = set(gui.remote_names())
    assert remote == set(payload), f"restore mismatch: {remote}"
    assert leftover not in remote, "wipe did not remove the leftover file"

    # cleanup
    for fname in payload:
        _clear_remote(gui, monkeypatch, fname)


@pytest.mark.mt("MT-BR10", "FR-153e", "UIR-107")
def test_restore_erase_all_sequence_wipes_scratch(gui, scratch_drive, monkeypatch, tmp_path):
    """Restore clears the scratch drive with the Erase All macro (run once), then uploads.

    FR-153e: when ``erase_all_remote_seq`` is configured the wipe runs that macro
    once (a single ``ERA *.*``-style command answered by the script) instead of
    one ``ERA`` per file. The observable end state matches MT-BR05: the leftover
    is gone and the drive holds exactly the host payload. The macro is taken from
    the target config when it defines one, else a standard CP/M form that answers
    the ``ALL (Y/N)?`` prompt.

    Verifies: FR-153e, UIR-107.
    """
    silence_message_boxes(monkeypatch)
    answer_confirm(monkeypatch, gui.win, accept=True)
    assert gui.connect()[0] == "ok"
    gui.set_drive(scratch_drive)
    assert gui.win.drive_combo.currentText() == f"{scratch_drive}:"  # safety: on scratch

    # Use the target's configured erase-all macro if present, else a standard
    # CP/M sequence that answers the interactive ALL (Y/N)? prompt.
    if not gui.win.settings.get("erase_all_remote_seq", "").strip():
        gui.win.settings["erase_all_remote_seq"] = "SEND ERA *.*\nWAITFOR (Y/N)\nSEND Y"

    host = tmp_path / "host"
    payload = {"ERA1.TXT": b"erase-all one\r\n", "ERA2.TXT": b"erase-all two\r\n"}
    for fname, data in payload.items():
        (host / fname).write_bytes(data)

    # Seed a leftover on the scratch drive that the erase-all macro must wipe.
    leftover = "LEFTOVER.TXT"
    (host / leftover).write_bytes(b"should be wiped\r\n")
    gui.upload([leftover])
    assert leftover in gui.remote_names()
    (host / leftover).unlink()  # remove from host so Restore won't re-upload it

    gui.win.do_restore()
    gui.quiesce(timeout=60.0)

    remote = set(gui.remote_names())
    assert remote == set(payload), f"erase-all restore mismatch: {remote}"
    assert leftover not in remote, "erase-all macro did not remove the leftover file"

    # cleanup
    for fname in payload:
        _clear_remote(gui, monkeypatch, fname)


@pytest.mark.mt("MT-BR02", "FR-150", "FR-152", "FR-154")
def test_backup_downloads_remote_to_host(gui, scratch_drive, monkeypatch, tmp_path):
    """Backup wipes the host dir then downloads every scratch-drive file.

    Verifies: FR-150, FR-152, FR-154.
    """
    import os

    silence_message_boxes(monkeypatch)
    answer_confirm(monkeypatch, gui.win, accept=True)
    assert gui.connect()[0] == "ok"
    gui.set_drive(scratch_drive)

    host = tmp_path / "host"
    payload = {"BK1.TXT": b"backup one\r\n", "BK2.TXT": b"backup two\r\n"}
    for fname, data in payload.items():
        (host / fname).write_bytes(data)
    # Ensure the scratch drive holds exactly these files.
    for fname in payload:
        _clear_remote(gui, monkeypatch, fname)
        gui.upload([fname])
    assert set(payload).issubset(set(gui.remote_names()))

    # A junk host file that Backup must wipe before downloading.
    (host / "JUNK.TXT").write_bytes(b"delete me\r\n")

    gui.win.do_backup()
    gui.quiesce(timeout=60.0)

    on_host = set(os.listdir(host))
    assert set(payload).issubset(on_host), f"backup did not download all files: {on_host}"
    assert "JUNK.TXT" not in on_host, "backup did not wipe the host dir first"

    for fname in payload:
        _clear_remote(gui, monkeypatch, fname)
