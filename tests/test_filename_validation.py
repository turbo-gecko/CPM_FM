"""Tests for host->remote CP/M 8.3 filename validation (FR-148, FR-149).

These cover the pure name-validation/suggestion logic, the rename/skip/cancel
dialog, and the upload batch loop's handling of an invalid name — all without
real serial hardware or worker threads.

Satisfies: FR-148, FR-149, UIR-085.
"""

import os
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from cpm_fm.terminal.cpm_parser import CPMParser  # noqa: E402

pytest.importorskip("PySide6")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from cpm_fm.app import MainWindow  # noqa: E402
from cpm_fm.gui.filename_validation_dialog import (  # noqa: E402
    CANCEL,
    RENAME,
    SKIP,
    FilenameValidationDialog,
)
from cpm_fm.gui.window_state import WindowState  # noqa: E402
from cpm_fm.utils import i18n  # noqa: E402
from cpm_fm.utils.transfer_history import TransferHistory  # noqa: E402

# ----------------------------------------------------- pure validation (FR-148)


@pytest.mark.parametrize(
    "name",
    [
        "FOO.TXT",
        "FOO",  # no extension is valid
        "A.C",
        "ABCDEFGH.TXT",  # 8-char base
        "12345678.123",  # 8.3 maximum
        "readme.txt",  # lower case folds to upper on CP/M
        "FILE-1.BAK",  # hyphen and digit are permitted
    ],
)
def test_is_valid_8_3_accepts_conforming_names(name):
    assert CPMParser.is_valid_8_3(name) is True


@pytest.mark.parametrize(
    "name",
    [
        "",  # empty
        "TOOLONGNAME.TXT",  # base > 8
        "FOO.TEXT",  # extension > 3
        "FOO.BAR.TXT",  # more than one dot
        "FOO.",  # trailing dot / empty extension
        ".TXT",  # empty base
        "FILE NAME.TXT",  # space
        "FOO*.TXT",  # wildcard
        "A:B.TXT",  # reserved delimiter
        "FOO/BAR.TXT",  # path separator
    ],
)
def test_is_valid_8_3_rejects_nonconforming_names(name):
    assert CPMParser.is_valid_8_3(name) is False


@pytest.mark.parametrize(
    "name,expected",
    [
        ("my long file name.text", "MYLONGFI.TEX"),
        ("readme", "README"),
        ("a*b?c.t/t", "ABC.TT"),
        ("....", "FILE"),  # nothing usable -> fallback base, no extension
        ("FOO.TXT", "FOO.TXT"),  # already valid is unchanged
    ],
)
def test_suggest_8_3_produces_valid_suggestion(name, expected):
    suggestion = CPMParser.suggest_8_3(name)
    assert suggestion == expected
    assert CPMParser.is_valid_8_3(suggestion) is True


# ------------------------------------------------------------- fixtures (Qt)


@pytest.fixture(autouse=True)
def _english_language():
    i18n.set_language(i18n.DEFAULT_LANGUAGE)
    yield
    i18n.set_language(i18n.DEFAULT_LANGUAGE)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def state(tmp_path):
    settings = QSettings(str(tmp_path / "state.ini"), QSettings.Format.IniFormat)
    return WindowState(settings)


class _FakeSerial:
    is_open = False

    def reset_input_buffer(self):
        pass


def _fake_xmodem_cls(calls):
    class _FakeXModem:
        def __init__(self, ser, monitor=None, progress=None, cancel_check=None):
            pass

        def send_file(self, path, use_1k=False):
            calls.append(path)
            return True

        def receive_file(self, path, use_1k=False):
            calls.append(path)
            return True

    return _FakeXModem


def _arm(win, monkeypatch, calls, sent=None):
    win.settings = {"xfer_launch_delay": 0}
    win.serial_mgr.terminal_connected = True
    win.serial_mgr.transport_connected = True
    win.serial_mgr.transport_port = _FakeSerial()
    win.transfer_history = TransferHistory(
        os.path.join(tempfile.mkdtemp(prefix="cpm_fm_hist_"), "history.json")
    )
    if sent is None:
        monkeypatch.setattr(win.serial_mgr, "send_data", lambda *a, **k: None)
    else:
        monkeypatch.setattr(win.serial_mgr, "send_data", lambda *a, **k: sent.append(a))
    monkeypatch.setattr("cpm_fm.gui.mw_transfer_batches.XModem", _fake_xmodem_cls(calls))
    monkeypatch.setattr("cpm_fm.app.time.sleep", lambda *a, **k: None)
    # No remote conflicts unless a test says otherwise.
    monkeypatch.setattr(win, "_fresh_remote_names", lambda: set())
    monkeypatch.setattr(win, "refresh_remote_files", lambda: None)


# --------------------------------------------------- batch integration (FR-149)


def test_remote_batch_skips_invalid_name(qapp, monkeypatch, state, tmp_path):
    # FR-149: Skip leaves the invalid-named file unsent and records "skipped";
    # the conforming file still transfers.
    win = MainWindow(state)
    try:
        calls = []
        _arm(win, monkeypatch, calls)
        monkeypatch.setattr(win, "_prompt_invalid_name", lambda name: (SKIP, ""))
        bad = tmp_path / "bad name.txt"  # space => invalid 8.3
        bad.write_text("x", encoding="utf-8")
        good = tmp_path / "GOOD.TXT"
        good.write_text("y", encoding="utf-8")
        win._transfer_to_remote_batch([str(bad), str(good)])
        qapp.processEvents()
        assert calls == [str(good)]
        statuses = {(e["filename"], e["status"]) for e in win.transfer_history.get_entries()}
        assert ("bad name.txt", "skipped") in statuses
        assert ("GOOD.TXT", "success") in statuses
    finally:
        win.close()


def test_remote_batch_renames_invalid_name(qapp, monkeypatch, state, tmp_path):
    # FR-149: Rename uploads the file under the validated replacement name; the
    # PCGET launch command and the history both carry the new name.
    win = MainWindow(state)
    try:
        calls, sent = [], []
        _arm(win, monkeypatch, calls, sent)
        monkeypatch.setattr(win, "_prompt_invalid_name", lambda name: (RENAME, "RENAMED.TXT"))
        bad = tmp_path / "bad name.txt"
        bad.write_text("x", encoding="utf-8")
        win._transfer_to_remote_batch([str(bad)])
        qapp.processEvents()
        assert calls == [str(bad)]  # the file was still sent
        # The launch command was issued with the renamed (8.3) name.
        assert any("RENAMED.TXT" in args[-1] for args in sent)
        statuses = {(e["filename"], e["status"]) for e in win.transfer_history.get_entries()}
        assert ("RENAMED.TXT", "success") in statuses
    finally:
        win.close()


def test_remote_batch_cancel_on_invalid_name(qapp, monkeypatch, state, tmp_path):
    # FR-149: Cancel at an invalid name aborts the whole batch.
    win = MainWindow(state)
    try:
        calls = []
        _arm(win, monkeypatch, calls)
        cancelled = []
        win.transfer_cancelled.connect(lambda d, ok: cancelled.append((d, ok)))
        monkeypatch.setattr(win, "_prompt_invalid_name", lambda name: (CANCEL, ""))
        bad = tmp_path / "bad name.txt"
        bad.write_text("x", encoding="utf-8")
        good = tmp_path / "GOOD.TXT"
        good.write_text("y", encoding="utf-8")
        win._transfer_to_remote_batch([str(bad), str(good)])
        qapp.processEvents()
        assert calls == []
        assert cancelled == [("remote", False)]
    finally:
        win.close()


def test_remote_batch_valid_name_never_prompts(qapp, monkeypatch, state, tmp_path):
    # FR-148: a conforming name is uploaded without raising the validation prompt.
    win = MainWindow(state)
    try:
        calls = []
        _arm(win, monkeypatch, calls)

        def _boom(name):
            raise AssertionError("valid names must not be prompted")

        monkeypatch.setattr(win, "_prompt_invalid_name", _boom)
        good = tmp_path / "GOOD.TXT"
        good.write_text("y", encoding="utf-8")
        win._transfer_to_remote_batch([str(good)])
        qapp.processEvents()
        assert calls == [str(good)]
    finally:
        win.close()


def test_renamed_name_then_subject_to_conflict(qapp, monkeypatch, state, tmp_path):
    # FR-145/FR-149: the renamed name is conflict-checked against the remote.
    win = MainWindow(state)
    try:
        calls = []
        _arm(win, monkeypatch, calls)
        monkeypatch.setattr(win, "_fresh_remote_names", lambda: {"RENAMED.TXT"})
        monkeypatch.setattr(win, "_prompt_invalid_name", lambda name: (RENAME, "RENAMED.TXT"))
        monkeypatch.setattr(win, "_prompt_conflict", lambda name, direction: (SKIP, False))
        bad = tmp_path / "bad name.txt"
        bad.write_text("x", encoding="utf-8")
        win._transfer_to_remote_batch([str(bad)])
        qapp.processEvents()
        assert calls == []  # renamed onto an existing remote file, then skipped
        statuses = {(e["filename"], e["status"]) for e in win.transfer_history.get_entries()}
        assert ("RENAMED.TXT", "skipped") in statuses
    finally:
        win.close()


# ------------------------------------------------------------- dialog (UIR-085)


def test_dialog_rename_with_valid_name_accepts(qapp, state):
    win = MainWindow(state)
    try:
        dialog = FilenameValidationDialog(win, "bad name.txt", "BADNAME.TXT")
        dialog._name_edit.setText("NEWNAME.TXT")
        dialog._on_rename()
        assert dialog.action == RENAME
        assert dialog.new_name == "NEWNAME.TXT"
    finally:
        win.close()


def test_dialog_rename_with_invalid_name_stays_open(qapp, state):
    # FR-149: an invalid replacement is rejected inline (dialog not accepted).
    win = MainWindow(state)
    try:
        dialog = FilenameValidationDialog(win, "bad name.txt", "BADNAME.TXT")
        dialog._name_edit.setText("still bad.text")
        dialog._on_rename()
        assert dialog.action == CANCEL  # unchanged from the default
        assert dialog._error.text() != ""
    finally:
        win.close()


def test_dialog_skip_and_cancel(qapp, state):
    win = MainWindow(state)
    try:
        d1 = FilenameValidationDialog(win, "bad name.txt", "BADNAME.TXT")
        d1._choose(SKIP)
        assert d1.action == SKIP
        d2 = FilenameValidationDialog(win, "bad name.txt", "BADNAME.TXT")
        d2.reject()
        assert d2.action == CANCEL
    finally:
        win.close()


def test_on_invalid_name_detected_records_choice_and_releases_worker(qapp, monkeypatch, state):
    # FR-149/UIR-085: the GUI slot shows the dialog, stores the choice, and sets
    # the event the worker thread blocks on.
    win = MainWindow(state)
    try:

        class _FakeDialog:
            def __init__(self, parent, name, suggested):
                self.action = RENAME
                self.new_name = "RENAMED.TXT"

            def exec(self):
                return 1

        monkeypatch.setattr("cpm_fm.gui.mw_transfer_guards.FilenameValidationDialog", _FakeDialog)
        win._invalid_name_answered.clear()
        win._on_invalid_name_detected("bad name.txt")
        assert win._invalid_name_result == (RENAME, "RENAMED.TXT")
        assert win._invalid_name_answered.is_set()
    finally:
        win.close()
