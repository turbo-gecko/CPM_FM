"""Tests for transfer file-conflict handling (FR-145, FR-146, FR-147).

These cover destination-conflict detection in both directions, the pre-upload
remote refresh, the batch-wide "apply to all" policy logic, and the batch loops'
handling of Skip/Cancel — all without real serial hardware or worker threads.

Satisfies: FR-145, FR-146, FR-147, UIR-084.
"""

import os
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from cpm_fm.app import MainWindow  # noqa: E402
from cpm_fm.gui.conflict_dialog import CANCEL, OVERWRITE, SKIP, FileConflictDialog  # noqa: E402
from cpm_fm.gui.window_state import WindowState  # noqa: E402
from cpm_fm.utils import i18n  # noqa: E402
from cpm_fm.utils.transfer_history import TransferHistory  # noqa: E402


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


def _arm(win, monkeypatch, calls):
    # Put the window in a state where the batch workers run without hardware.
    win.settings = {"xfer_launch_delay": 0}
    win.serial_mgr.terminal_connected = True
    win.serial_mgr.transport_connected = True
    win.serial_mgr.transport_port = _FakeSerial()
    win.transfer_history = TransferHistory(
        os.path.join(tempfile.mkdtemp(prefix="cpm_fm_hist_"), "history.json")
    )
    monkeypatch.setattr(win.serial_mgr, "send_data", lambda *a, **k: None)
    monkeypatch.setattr("cpm_fm.gui.mw_transfer_batches.XModem", _fake_xmodem_cls(calls))
    monkeypatch.setattr("cpm_fm.gui.mw_transfers.time.sleep", lambda *a, **k: None)


# --------------------------------------------------------- detection (FR-145)


def test_destination_conflict_host_checks_filesystem(tmp_path):
    # FR-145: a download conflict is the existence of the host target path.
    existing = tmp_path / "FOO.TXT"
    existing.write_text("hi", encoding="utf-8")
    assert MainWindow._destination_conflict("host", str(existing), set()) is True
    assert MainWindow._destination_conflict("host", str(tmp_path / "NOPE.TXT"), set()) is False


def test_destination_conflict_remote_checks_listing_case_insensitive():
    # FR-145: an upload conflict checks the base name (upper-cased) against the
    # fresh remote listing.
    names = {"FOO.TXT", "BAR.COM"}
    assert MainWindow._destination_conflict("remote", "/host/foo.txt", names) is True
    assert MainWindow._destination_conflict("remote", "/host/FOO.TXT", names) is True
    assert MainWindow._destination_conflict("remote", "/host/baz.txt", names) is False


def test_fresh_remote_names_uppercases_and_emits(qapp, monkeypatch, state):
    # FR-145: the pre-upload refresh returns upper-cased names and updates the
    # displayed Remote Files list via remote_files_ready.
    win = MainWindow(state)
    try:
        monkeypatch.setattr(win, "_capture_terminal_response", lambda cmd, cancellable=False: "DIR-OUTPUT")
        monkeypatch.setattr(
            "cpm_fm.app.CPMParser.parse_dir_output", lambda text: {"foo.txt": None, "BAR.COM": None}
        )
        names = win._fresh_remote_names()
        assert names == {"FOO.TXT", "BAR.COM"}
        qapp.processEvents()  # let the queued remote_files_ready update the list
        assert set(win._remote_files) == {"foo.txt", "BAR.COM"}
    finally:
        win.close()


def test_fresh_remote_names_empty_on_capture_failure(qapp, monkeypatch, state):
    # FR-145: if the refresh cannot be parsed, no names => no conflicts detected.
    win = MainWindow(state)
    try:
        monkeypatch.setattr(win, "_capture_terminal_response", lambda cmd, cancellable=False: "")
        monkeypatch.setattr("cpm_fm.app.CPMParser.parse_dir_output", lambda text: {})
        assert win._fresh_remote_names() == set()
    finally:
        win.close()


# ------------------------------------------------------------ policy (FR-147)


def test_resolve_conflict_uses_policy_without_prompting(qapp, monkeypatch, state):
    # FR-147: once a batch policy is set, no further prompt is raised.
    win = MainWindow(state)
    try:
        win._conflict_policy = SKIP

        def _boom(name, direction):
            raise AssertionError("_prompt_conflict must not be called when a policy is set")

        monkeypatch.setattr(win, "_prompt_conflict", _boom)
        assert win._resolve_conflict("FOO.TXT", "host") == SKIP
    finally:
        win.close()


def test_resolve_conflict_apply_to_all_sets_policy(qapp, monkeypatch, state):
    # FR-147: resolving with "apply to all" ticked remembers the action and
    # applies it to subsequent conflicts without prompting again.
    win = MainWindow(state)
    try:
        prompts = []

        def _prompt(name, direction):
            prompts.append(name)
            return (SKIP, True)

        monkeypatch.setattr(win, "_prompt_conflict", _prompt)
        assert win._resolve_conflict("A.TXT", "host") == SKIP
        assert win._resolve_conflict("B.TXT", "host") == SKIP
        assert prompts == ["A.TXT"]  # only the first conflict prompted
        assert win._conflict_policy == SKIP
    finally:
        win.close()


def test_resolve_conflict_without_apply_to_all_prompts_each_time(qapp, monkeypatch, state):
    # FR-146/FR-147: without the checkbox, every conflict prompts and no policy
    # is remembered.
    win = MainWindow(state)
    try:
        prompts = []

        def _prompt(name, direction):
            prompts.append(name)
            return (OVERWRITE, False)

        monkeypatch.setattr(win, "_prompt_conflict", _prompt)
        assert win._resolve_conflict("A.TXT", "host") == OVERWRITE
        assert win._resolve_conflict("B.TXT", "host") == OVERWRITE
        assert prompts == ["A.TXT", "B.TXT"]
        assert win._conflict_policy is None
    finally:
        win.close()


def test_resolve_conflict_cancel_never_becomes_policy(qapp, monkeypatch, state):
    # FR-147: Cancel ends the batch and is never remembered as a policy.
    win = MainWindow(state)
    try:
        monkeypatch.setattr(win, "_prompt_conflict", lambda name, direction: (CANCEL, True))
        assert win._resolve_conflict("A.TXT", "host") == CANCEL
        assert win._conflict_policy is None
    finally:
        win.close()


def test_on_conflict_detected_records_choice_and_releases_worker(qapp, monkeypatch, state):
    # FR-146/UIR-084: the GUI slot shows the dialog, stores the choice, and sets
    # the event the worker thread blocks on.
    win = MainWindow(state)
    try:

        class _FakeDialog:
            def __init__(self, parent, name, direction):
                self.action = SKIP
                self.apply_to_all = True

            def exec(self):
                return 1

        monkeypatch.setattr("cpm_fm.gui.mw_transfer_guards.FileConflictDialog", _FakeDialog)
        win._conflict_answered.clear()
        win._on_conflict_detected("FOO.TXT", "host")
        assert win._conflict_result == (SKIP, True)
        assert win._conflict_answered.is_set()
    finally:
        win.close()


# -------------------------------------------------- batch integration (FR-146)


def test_host_batch_skips_existing_file(qapp, monkeypatch, state, tmp_path):
    # FR-146: a Skip leaves the existing file untouched (no receive) and records
    # a "skipped" history entry, while a non-conflicting file still transfers.
    win = MainWindow(state)
    try:
        calls = []
        _arm(win, monkeypatch, calls)
        monkeypatch.setattr(win, "refresh_host_files", lambda: None)
        monkeypatch.setattr(win, "_prompt_conflict", lambda name, direction: (SKIP, False))
        existing = tmp_path / "FOO.TXT"
        existing.write_text("x", encoding="utf-8")
        fresh = tmp_path / "BAR.TXT"  # does not exist => no conflict
        win._transfer_to_host_batch([str(existing), str(fresh)])
        qapp.processEvents()
        assert calls == [str(fresh)]  # only the non-conflicting file received
        statuses = {(e["filename"], e["status"]) for e in win.transfer_history.get_entries()}
        assert ("FOO.TXT", "skipped") in statuses
        assert ("BAR.TXT", "success") in statuses
    finally:
        win.close()


def test_remote_batch_skips_existing_file(qapp, monkeypatch, state, tmp_path):
    # FR-145/FR-146: an upload conflict is detected against the fresh remote
    # listing; Skip records "skipped" and does not send the file.
    win = MainWindow(state)
    try:
        calls = []
        _arm(win, monkeypatch, calls)
        monkeypatch.setattr(win, "refresh_remote_files", lambda: None)
        monkeypatch.setattr(win, "_fresh_remote_names", lambda: {"FOO.TXT"})
        monkeypatch.setattr(win, "_prompt_conflict", lambda name, direction: (SKIP, False))
        foo = tmp_path / "FOO.TXT"
        foo.write_text("x", encoding="utf-8")
        bar = tmp_path / "BAR.TXT"
        bar.write_text("y", encoding="utf-8")
        win._transfer_to_remote_batch([str(foo), str(bar)])
        qapp.processEvents()
        assert calls == [str(bar)]  # FOO.TXT skipped, BAR.TXT sent
        statuses = {(e["filename"], e["status"]) for e in win.transfer_history.get_entries()}
        assert ("FOO.TXT", "skipped") in statuses
        assert ("BAR.TXT", "success") in statuses
    finally:
        win.close()


def test_remote_batch_overwrite_erases_then_sends(qapp, monkeypatch, state, tmp_path):
    # FR-146: choosing Overwrite on an upload conflict erases the existing remote
    # file first (so a receiver that won't silently overwrite cannot stall the
    # handshake) and then sends the file.
    win = MainWindow(state)
    try:
        calls = []
        _arm(win, monkeypatch, calls)
        monkeypatch.setattr(win, "refresh_remote_files", lambda: None)
        monkeypatch.setattr(win, "_fresh_remote_names", lambda: {"FOO.TXT"})
        erased = []
        monkeypatch.setattr(win, "_erase_remote_file", lambda name: erased.append(name))
        monkeypatch.setattr(win, "_prompt_conflict", lambda name, direction: (OVERWRITE, False))
        foo = tmp_path / "FOO.TXT"
        foo.write_text("x", encoding="utf-8")
        win._transfer_to_remote_batch([str(foo)])
        qapp.processEvents()
        assert erased == ["FOO.TXT"]  # erased before the send
        assert calls == [str(foo)]  # then sent
        statuses = {(e["filename"], e["status"]) for e in win.transfer_history.get_entries()}
        assert ("FOO.TXT", "success") in statuses
    finally:
        win.close()


def test_batch_cancel_aborts_whole_transfer(qapp, monkeypatch, state, tmp_path):
    # FR-146: Cancel at a conflict aborts the batch — no file is transferred.
    win = MainWindow(state)
    try:
        calls = []
        _arm(win, monkeypatch, calls)
        monkeypatch.setattr(win, "refresh_host_files", lambda: None)
        cancelled = []
        win.transfer_cancelled.connect(lambda d, ok: cancelled.append((d, ok)))
        monkeypatch.setattr(win, "_prompt_conflict", lambda name, direction: (CANCEL, False))
        existing = tmp_path / "FOO.TXT"
        existing.write_text("x", encoding="utf-8")
        fresh = tmp_path / "BAR.TXT"
        win._transfer_to_host_batch([str(existing), str(fresh)])
        qapp.processEvents()
        assert calls == []  # nothing transferred
        assert cancelled == [("host", False)]
    finally:
        win.close()


def test_apply_to_all_skip_prompts_once_for_many_conflicts(qapp, monkeypatch, state, tmp_path):
    # FR-147: with "apply to all" the user is prompted only once even though
    # several files conflict.
    win = MainWindow(state)
    try:
        calls = []
        _arm(win, monkeypatch, calls)
        monkeypatch.setattr(win, "refresh_host_files", lambda: None)
        prompts = []

        def _prompt(name, direction):
            prompts.append(name)
            return (SKIP, True)

        monkeypatch.setattr(win, "_prompt_conflict", _prompt)
        paths = []
        for n in ("A.TXT", "B.TXT", "C.TXT"):
            p = tmp_path / n
            p.write_text("x", encoding="utf-8")
            paths.append(str(p))
        win._transfer_to_host_batch(paths)
        qapp.processEvents()
        assert len(prompts) == 1  # prompted once, policy applied to the rest
        assert calls == []  # all three skipped
        skipped = [e for e in win.transfer_history.get_entries() if e["status"] == "skipped"]
        assert len(skipped) == 3
    finally:
        win.close()


def test_conflict_dialog_cancel_on_window_close(qapp, state):
    # UIR-084: closing the dialog via the window manager is equivalent to Cancel.
    win = MainWindow(state)
    try:
        dialog = FileConflictDialog(win, "FOO.TXT", "host")
        dialog.reject()
        assert dialog.action == CANCEL
        assert dialog.apply_to_all is False
    finally:
        win.close()
