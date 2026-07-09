"""Headless smoke tests for the PySide6 GUI (v1.3 migration).

These construct the real widgets under an offscreen Qt platform to catch import
errors, signal/slot wiring mistakes, and obvious layout faults without a display.
Run headless via the ``QT_QPA_PLATFORM=offscreen`` environment variable (set in CI).
"""

import os
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from cpm_fm.app import MainWindow  # noqa: E402
from cpm_fm.gui.about_dialog import AboutDialog  # noqa: E402
from cpm_fm.gui.terminal_window import TerminalWindow  # noqa: E402
from cpm_fm.gui.transfer_history_dialog import TransferHistoryDialog  # noqa: E402
from cpm_fm.gui.window_state import WindowState  # noqa: E402
from cpm_fm.utils import i18n  # noqa: E402
from cpm_fm.utils.config_handler import DEFAULT_SETTINGS  # noqa: E402
from cpm_fm.utils.transfer_history import TransferHistory  # noqa: E402
from cpm_fm.version import APP_NAME, REPO_URL, get_version  # noqa: E402


@pytest.fixture(autouse=True)
def _english_language():
    # The translator is a process-wide singleton; force English around every
    # test so a test that switches language cannot break the many tests that
    # assert on English literals (FR-124).
    i18n.set_language(i18n.DEFAULT_LANGUAGE)
    yield
    i18n.set_language(i18n.DEFAULT_LANGUAGE)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def state(tmp_path):
    # Isolated WindowState backed by a temp INI file so tests never read or
    # write the host's real QSettings (registry on Windows).
    settings = QSettings(str(tmp_path / "state.ini"), QSettings.Format.IniFormat)
    return WindowState(settings)


class _FakeSerial:
    """
    Minimal stand-in for a pyserial port used by the transfer workers.
    """

    is_open = False  # so SerialManager.close_ports() skips closing it on teardown

    def reset_input_buffer(self):
        pass


def _fake_xmodem_cls(success=True, calls=None):
    # success may be a single bool applied to every file, or a list/tuple of
    # per-call booleans consumed in order (so a batch test can fail file N).
    # calls, if given, records each transferred path so order/count is assertable.
    seq = iter(success) if isinstance(success, (list, tuple)) else None

    class _FakeXModem:
        def __init__(
            self, ser, monitor=None, progress=None, cancel_check=None, handshake_timeout=None
        ):
            self.progress = progress
            self.no_response = False

        def _report(self):
            # FR-105: exercise the progress hook so the transfer_progress signal
            # path runs during the smoke test.
            if self.progress:
                self.progress(1, 128, 128)

        def _result(self):
            return next(seq) if seq is not None else success

        def send_file(self, path, use_1k=False):
            if calls is not None:
                calls.append(path)
            self._report()
            return self._result()

        def receive_file(self, path, use_1k=False):
            if calls is not None:
                calls.append(path)
            self._report()
            return self._result()

    return _FakeXModem


def _arm_transfer(win, monkeypatch, success=True, calls=None):
    # Put the window in a state where the transfer workers can run without real
    # serial hardware or sleeps: both flags connected, a fake transport port,
    # no launch delay, send_data and XModem stubbed.
    win.settings = {"xfer_launch_delay": 0}
    win.serial_mgr.terminal_connected = True
    win.serial_mgr.transport_connected = True
    win.serial_mgr.transport_port = _FakeSerial()
    # Isolate the transfer history to a temp file so recording during a stubbed
    # transfer never touches the host's real ~/.cpm_fm_history.json (FR-141).
    win.transfer_history = TransferHistory(
        os.path.join(tempfile.mkdtemp(prefix="cpm_fm_hist_"), "history.json")
    )
    monkeypatch.setattr(win.serial_mgr, "send_data", lambda *a, **k: None)
    monkeypatch.setattr("cpm_fm.gui.mw_transfer_batches.XModem", _fake_xmodem_cls(success, calls))
    # Neutralise worker-thread sleeps (launch delay, FR-109 inter-file idle/settle)
    # so batch tests run fast while still exercising the real wait logic.
    monkeypatch.setattr("cpm_fm.gui.mw_transfers.time.sleep", lambda *a, **k: None)


def _fake_action_dialog(value, accepted=True):
    # Stand-in for FileActionDialog: exec() returns Accepted/Rejected without a
    # real modal dialog, and value() returns the supplied (edited) filename.
    from PySide6.QtWidgets import QDialog

    class _Fake:
        def __init__(self, *a, **k):
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted if accepted else QDialog.DialogCode.Rejected

        def value(self):
            return value

    return _Fake


class _RecordingThread:
    # Captures (target, args) and runs nothing, so the worker body can be
    # asserted on without spawning a real thread.
    instances: list = []

    def __init__(self, *a, target=None, args=(), **k):
        self.target = target
        self.args = args
        _RecordingThread.instances.append(self)

    def start(self):
        pass


def test_copy_to_host_refreshes_host_list(qapp, monkeypatch, state):
    # Bug 1: a successful remote->host transfer must refresh the Host Files list.
    win = MainWindow(state)
    try:
        calls = []
        monkeypatch.setattr(win, "refresh_host_files", lambda: calls.append("host"))
        _arm_transfer(win, monkeypatch)
        win._transfer_to_host_batch([os.path.join(win.host_dir, "FOO.TXT")])
        qapp.processEvents()
        assert calls == ["host"]
    finally:
        win.close()


def test_copy_to_remote_refreshes_remote_list(qapp, monkeypatch, state):
    # Bug 2: a successful host->remote transfer must refresh the Remote Files list.
    win = MainWindow(state)
    try:
        calls = []
        monkeypatch.setattr(win, "refresh_remote_files", lambda: calls.append("remote"))
        _arm_transfer(win, monkeypatch)
        win._transfer_to_remote_batch([os.path.join(win.host_dir, "FOO.TXT")])
        qapp.processEvents()
        assert calls == ["remote"]
    finally:
        win.close()


def test_failed_transfer_does_not_refresh(qapp, monkeypatch, state):
    # A failed transfer must not trigger a refresh (no false "it worked" signal).
    win = MainWindow(state)
    try:
        calls = []
        monkeypatch.setattr(win, "refresh_host_files", lambda: calls.append("host"))
        # A failed transfer reports via QMessageBox.critical; stub it so the
        # offscreen test does not block on a modal dialog.
        monkeypatch.setattr("cpm_fm.app.QMessageBox.critical", lambda *a, **k: None)
        _arm_transfer(win, monkeypatch, success=False)
        win._transfer_to_host_batch([os.path.join(win.host_dir, "FOO.TXT")])
        qapp.processEvents()
        assert calls == []
    finally:
        win.close()


def test_progress_dialog_started_and_updates(qapp, state):
    """Verifies: FR-105, UIR-051."""
    # FR-105/UIR-051: batch_started builds the modal dialog; transfer_file_started
    # names the file; transfer_progress updates the blocks/bytes label.
    win = MainWindow(state)
    try:
        win._on_batch_started("remote", 1)
        win._on_transfer_file_started("FOO.TXT", 256, 1)
        dlg = win._transfer_dialog
        assert dlg is not None
        assert dlg.windowTitle() == "Sending File"
        assert "FOO.TXT" in dlg.file_label.text()

        win._on_transfer_progress(2, 256)
        assert dlg.count_label.text() == "Blocks: 2    Bytes: 256"
    finally:
        win.close()


def test_progress_dialog_title_for_receive(qapp, state):
    """Verifies: UIR-051."""
    # UIR-051: the host (receive) direction titles the dialog "Receiving File".
    win = MainWindow(state)
    try:
        win._on_batch_started("host", 1)
        win._on_transfer_file_started("BAR.TXT", 0, 1)
        assert win._transfer_dialog is not None
        assert win._transfer_dialog.windowTitle() == "Receiving File"
    finally:
        win.close()


def test_progress_dialog_closes_on_completion(qapp, monkeypatch, state):
    """Verifies: FR-105."""
    # FR-105: a successful transfer auto-closes the progress dialog.
    win = MainWindow(state)
    try:
        monkeypatch.setattr(win, "refresh_remote_files", lambda: None)
        win._on_batch_started("remote", 1)
        win._on_transfer_file_started("FOO.TXT", 128, 1)
        assert win._transfer_dialog is not None
        win._on_transfer_completed("remote")
        assert win._transfer_dialog is None
    finally:
        win.close()


def test_progress_dialog_closes_on_error(qapp, monkeypatch, state):
    """Verifies: FR-105."""
    # FR-105: a failed transfer auto-closes the progress dialog before the error.
    win = MainWindow(state)
    try:
        monkeypatch.setattr("cpm_fm.app.QMessageBox.critical", lambda *a, **k: None)
        win._on_batch_started("remote", 1)
        win._on_transfer_file_started("FOO.TXT", 128, 1)
        assert win._transfer_dialog is not None
        win._on_error_raised("X-Modem Error", "Transfer failed")
        assert win._transfer_dialog is None
    finally:
        win.close()


def test_transfer_run_leaves_no_progress_dialog(qapp, monkeypatch, state):
    """Verifies: FR-105."""
    # FR-105: end-to-end through a stubbed transfer, the dialog is opened then
    # closed, leaving no leaked dialog once the queued signals are delivered.
    win = MainWindow(state)
    try:
        monkeypatch.setattr(win, "refresh_remote_files", lambda: None)
        _arm_transfer(win, monkeypatch)
        win._transfer_to_remote_batch([os.path.join(win.host_dir, "FOO.TXT")])
        qapp.processEvents()
        assert win._transfer_dialog is None
    finally:
        win.close()


def test_selected_filenames_returns_display_order(qapp, state):
    """Verifies: FR-106, FR-107."""
    # FR-106/FR-107: every selected file is returned in list display order,
    # regardless of the order rows were clicked.
    win = MainWindow(state)
    try:
        win.host_list.clear()
        win.host_list.addItems(["A.TXT", "B.TXT", "C.TXT", "D.TXT"])
        # Select rows 2 then 0 (out of display order) and row 3.
        for row in (2, 0, 3):
            win.host_list.item(row).setSelected(True)
        assert win._selected_filenames(win.host_list) == ["A.TXT", "C.TXT", "D.TXT"]
    finally:
        win.close()


def test_copy_to_remote_transfers_all_selected(qapp, monkeypatch, state):
    """Verifies: FR-106, FR-107, FR-099."""
    # FR-106/FR-107: a multi-file Copy to Remote transfers every selected file
    # sequentially and refreshes the remote list once at the end.
    win = MainWindow(state)
    try:
        refreshes = []
        monkeypatch.setattr(win, "refresh_remote_files", lambda: refreshes.append(1))
        calls = []
        _arm_transfer(win, monkeypatch, calls=calls)
        paths = [os.path.join(win.host_dir, n) for n in ("A.TXT", "B.TXT", "C.TXT")]
        win._transfer_to_remote_batch(paths)
        qapp.processEvents()
        assert [os.path.basename(p) for p in calls] == ["A.TXT", "B.TXT", "C.TXT"]
        assert refreshes == [1]  # FR-099: one refresh for the whole batch.
    finally:
        win.close()


def test_copy_to_host_transfers_all_selected(qapp, monkeypatch, state):
    """Verifies: FR-106, FR-107."""
    # FR-106/FR-107: symmetric multi-file Copy to Host.
    win = MainWindow(state)
    try:
        refreshes = []
        monkeypatch.setattr(win, "refresh_host_files", lambda: refreshes.append(1))
        calls = []
        _arm_transfer(win, monkeypatch, calls=calls)
        paths = [os.path.join(win.host_dir, n) for n in ("A.TXT", "B.TXT")]
        win._transfer_to_host_batch(paths)
        qapp.processEvents()
        assert [os.path.basename(p) for p in calls] == ["A.TXT", "B.TXT"]
        assert refreshes == [1]
    finally:
        win.close()


def test_batch_aborts_on_failure(qapp, monkeypatch, state):
    """Verifies: FR-108, FR-108a, FR-108b."""
    # FR-108: when a file fails mid-batch, the remaining files are skipped, an
    # error names the failed file, and the destination refreshes once because an
    # earlier file succeeded.
    win = MainWindow(state)
    try:
        refreshes = []
        monkeypatch.setattr(win, "refresh_remote_files", lambda: refreshes.append(1))
        errors = []
        monkeypatch.setattr("cpm_fm.app.QMessageBox.critical", lambda *a, **k: errors.append(a[1:]))
        calls = []
        # First file succeeds, second fails -> third is never attempted.
        _arm_transfer(win, monkeypatch, success=[True, False], calls=calls)
        paths = [os.path.join(win.host_dir, n) for n in ("A.TXT", "B.TXT", "C.TXT")]
        win._transfer_to_remote_batch(paths)
        qapp.processEvents()
        assert [os.path.basename(p) for p in calls] == ["A.TXT", "B.TXT"]
        assert refreshes == [1]  # partial success still refreshes (FR-108).
        assert errors == [("X-Modem Error", "Transfer of B.TXT failed; remaining files skipped")]
    finally:
        win.close()


def test_batch_waits_for_prompt_between_files(qapp, monkeypatch, state):
    """Verifies: FR-109."""
    # FR-109: the inter-file prompt wait runs before each file after the first,
    # and never before the first file.
    win = MainWindow(state)
    try:
        monkeypatch.setattr(win, "refresh_remote_files", lambda: None)
        waits = []
        monkeypatch.setattr(win, "_wait_for_terminal_idle", lambda: waits.append(1))
        _arm_transfer(win, monkeypatch)
        paths = [os.path.join(win.host_dir, n) for n in ("A.TXT", "B.TXT", "C.TXT")]
        win._transfer_to_remote_batch(paths)
        qapp.processEvents()
        assert len(waits) == 2  # before files 2 and 3 only
    finally:
        win.close()


def test_remote_batch_settles_after_final_file_before_refresh(qapp, monkeypatch, state):
    """Verifies: FR-109."""
    # FR-109: after the final file of an upload batch the inter-file settle
    # period is waited before the FR-099 completion refresh, so the post-batch
    # Remote-list DIR is not issued while a slow CP/M peer is still returning to
    # its prompt (otherwise the just-uploaded file can be missing from the list).
    win = MainWindow(state)
    try:
        _arm_transfer(win, monkeypatch)
        win.settings = {"xfer_launch_delay": 0, "xfer_interfile_delay": 2}
        events = []
        monkeypatch.setattr(
            win,
            "_cancellable_sleep",
            lambda secs, cancel_event=None: events.append(("sleep", secs)) or False,
        )
        monkeypatch.setattr(win, "refresh_remote_files", lambda: events.append(("refresh", None)))
        win._transfer_to_remote_batch([os.path.join(win.host_dir, "A.TXT")])
        qapp.processEvents()
        # The final-file settle waited exactly the inter-file delay, before refresh.
        assert ("sleep", 2.0) in events
        assert events.index(("sleep", 2.0)) < events.index(("refresh", None))
    finally:
        win.close()


def test_host_batch_settles_after_final_file_before_refresh(qapp, monkeypatch, state):
    """Verifies: FR-109."""
    # FR-109: the download batch applies the same post-final-file settle before
    # signalling completion, keeping the remote quiescent for any command that
    # follows the batch (parity with uploads).
    win = MainWindow(state)
    try:
        _arm_transfer(win, monkeypatch)
        win.settings = {"xfer_launch_delay": 0, "xfer_interfile_delay": 2}
        events = []
        monkeypatch.setattr(
            win,
            "_cancellable_sleep",
            lambda secs, cancel_event=None: events.append(("sleep", secs)) or False,
        )
        monkeypatch.setattr(win, "refresh_host_files", lambda: events.append(("refresh", None)))
        win._transfer_to_host_batch([os.path.join(win.host_dir, "A.TXT")])
        qapp.processEvents()
        assert ("sleep", 2.0) in events
        assert events.index(("sleep", 2.0)) < events.index(("refresh", None))
    finally:
        win.close()


def test_batch_does_not_settle_when_nothing_transferred(qapp, monkeypatch, state):
    """Verifies: FR-109."""
    # FR-109: the post-batch settle is applied only when at least one file was
    # transferred; an all-skipped batch adds no needless delay.
    from cpm_fm.gui.conflict_dialog import SKIP

    win = MainWindow(state)
    try:
        _arm_transfer(win, monkeypatch)
        win.settings = {"xfer_launch_delay": 0, "xfer_interfile_delay": 2}
        delays = []
        monkeypatch.setattr(
            win, "_cancellable_sleep", lambda secs, cancel_event=None: delays.append(secs) or False
        )
        monkeypatch.setattr(win, "refresh_remote_files", lambda: None)
        monkeypatch.setattr(win, "_fresh_remote_names", lambda: set())
        # An invalid CP/M 8.3 name (11-char base) triggers the rename prompt; Skip
        # it so the batch finishes having transferred nothing.
        monkeypatch.setattr(win, "_prompt_invalid_name", lambda name: (SKIP, None))
        win._transfer_to_remote_batch([os.path.join(win.host_dir, "TOOLONGNAME.TXT")])
        qapp.processEvents()
        assert 2.0 not in delays  # no final-file settle when nothing succeeded
    finally:
        win.close()


def test_batch_progress_dialog_shows_file_position(qapp, state):
    """Verifies: FR-105, UIR-051."""
    # FR-105/UIR-051: one dialog serves the batch; transfer_file_started switches
    # it between files on the SAME instance, showing "File i of N".
    win = MainWindow(state)
    try:
        win._on_batch_started("remote", 2)
        dlg = win._transfer_dialog
        assert dlg is not None
        win._on_transfer_file_started("A.TXT", 128, 1)
        assert dlg.batch_label.text() == "File 1 of 2"
        assert "A.TXT" in dlg.file_label.text()
        win._on_transfer_file_started("B.TXT", 128, 2)
        # Same dialog instance, not recreated.
        assert win._transfer_dialog is dlg
        assert dlg.batch_label.text() == "File 2 of 2"
        assert "B.TXT" in dlg.file_label.text()
    finally:
        win.close()


def test_drive_combo_lists_a_to_p(qapp, state):
    """Verifies: UIR-017."""
    # UIR-017: the drive-selection drop-down lists A: through P: (16 drives).
    win = MainWindow(state)
    try:
        items = [win.drive_combo.itemText(i) for i in range(win.drive_combo.count())]
        assert items == [f"{chr(c)}:" for c in range(ord("A"), ord("P") + 1)]
    finally:
        win.close()


def test_change_drive_success_refreshes_remote_list(qapp, monkeypatch, state):
    """Verifies: FR-102."""
    # FR-102: when the "<letter>>" prompt appears, the remote list is populated
    # exactly as Update does. Stub the capture to avoid real serial/sleeps.
    win = MainWindow(state)
    try:
        win.serial_mgr.terminal_connected = True
        monkeypatch.setattr(
            win,
            "_capture_terminal_response",
            lambda cmd, cancellable=False, cancel_event=None: "B:\nB>\n",
        )
        calls = []
        monkeypatch.setattr(win, "_do_refresh_remote_logic", lambda: calls.append("refresh"))
        win._do_change_drive_logic("B")
        assert calls == ["refresh"]
    finally:
        win.close()


def test_change_drive_not_found_clears_list_and_warns(qapp, monkeypatch, state):
    """Verifies: FR-103."""
    # FR-103: no "<letter>>" prompt -> clear the remote list and warn the user.
    win = MainWindow(state)
    try:
        win.remote_list.addItem("STALE.TXT")
        win.serial_mgr.terminal_connected = True
        monkeypatch.setattr(
            win,
            "_capture_terminal_response",
            lambda cmd, cancellable=False, cancel_event=None: "\nnot ready\n",
        )
        warned = []
        monkeypatch.setattr("cpm_fm.app.QMessageBox.warning", lambda *a, **k: warned.append(a[1:]))
        win._do_change_drive_logic("B")
        qapp.processEvents()  # deliver the queued drive_not_found signal
        assert win.remote_list.count() == 0
        assert warned == [("Drive not found", "Drive B: not found")]
    finally:
        win.close()


def test_connect_probes_when_both_ports_connected(qapp, monkeypatch, state):
    """Verifies: FR-041, FR-046."""
    # FR-041/FR-046: when Connect leaves both ports connected, a probe worker is
    # started. Same physical port, so opening the terminal also connects transport.
    win = MainWindow(state)
    try:
        win.settings["terminal_port"] = "COM1"
        win.settings["transport_port"] = "COM1"

        def fake_open(kind, settings):
            win.serial_mgr.terminal_connected = True
            return True

        monkeypatch.setattr(win.serial_mgr, "open_port", fake_open)
        targets = []

        class _RecordingThread:
            def __init__(self, *a, target=None, args=(), **k):
                targets.append(target)

            def start(self):
                pass

        monkeypatch.setattr("cpm_fm.app.threading.Thread", _RecordingThread)
        win.do_connect()
        assert win._do_connect_probe_logic in targets
    finally:
        win.close()


def test_connect_when_terminal_already_open_notifies_and_takes_no_action(qapp, monkeypatch, state):
    """Verifies: FR-030."""
    # FR-030: Connect shall open the Terminal Port only if it is not already
    # open. Defect: pressing Connect while already connected re-attempted the
    # open, which fails (the port is held open) and desyncs the connected
    # flag from the real port state, locking the user out of reconnecting.
    win = MainWindow(state)
    try:
        win.serial_mgr.terminal_connected = True
        win.serial_mgr.transport_connected = True

        opened = []
        monkeypatch.setattr(win.serial_mgr, "open_port", lambda *a, **k: opened.append(a) or True)
        statuses = []
        monkeypatch.setattr(win, "set_status", lambda t: statuses.append(t))
        errors = []
        monkeypatch.setattr(
            "cpm_fm.gui.mw_remote.QMessageBox.critical",
            lambda *a, **k: errors.append(a) or None,
        )

        win.do_connect()

        assert opened == []  # no re-open attempt on either port
        assert errors == []  # not treated as an error
        assert statuses == [i18n.tr("status.terminal_already_open")]
        assert win.serial_mgr.terminal_connected is True
        assert win.serial_mgr.transport_connected is True
    finally:
        win.close()


def test_connect_skips_probe_when_transport_unavailable(qapp, monkeypatch, state):
    """Verifies: FR-046."""
    # FR-046: if the (separate) Transport Port fails to open, no probe runs.
    win = MainWindow(state)
    try:
        win.settings["terminal_port"] = "COM1"
        win.settings["transport_port"] = "COM2"

        def fake_open(kind, settings):
            if kind == "terminal":
                win.serial_mgr.terminal_connected = True
                return True
            return False  # transport fails to open

        monkeypatch.setattr(win.serial_mgr, "open_port", fake_open)
        monkeypatch.setattr("cpm_fm.gui.mw_remote.QMessageBox.critical", lambda *a, **k: None)
        targets = []

        class _RecordingThread:
            def __init__(self, *a, target=None, args=(), **k):
                targets.append(target)

            def start(self):
                pass

        monkeypatch.setattr("cpm_fm.app.threading.Thread", _RecordingThread)
        win.do_connect()
        assert win._do_connect_probe_logic not in targets
    finally:
        win.close()


def test_connect_probe_ok_sets_drive_and_refreshes(qapp, monkeypatch, state):
    """Verifies: FR-042."""
    # FR-042: a returned drive prompt sets the drop-down to that drive and
    # populates the Remote Files list (here the refresh is stubbed/recorded).
    win = MainWindow(state)
    try:
        monkeypatch.setattr(
            win,
            "_capture_terminal_response",
            lambda cmd, cancellable=False, cancel_event=None: "C>\n",
        )
        refreshed = []
        monkeypatch.setattr(win, "refresh_remote_files", lambda: refreshed.append(True))
        win._do_connect_probe_logic()
        qapp.processEvents()  # deliver the queued connect_probe_ok signal
        assert win.drive_combo.currentText() == "C:"
        assert refreshed == [True]
    finally:
        win.close()


def test_connect_probe_retries_then_succeeds(qapp, monkeypatch, state):
    """Verifies: FR-043."""
    # FR-043: no prompt on the first EOL -> send EOL again; the second response
    # carries the prompt, so the probe still succeeds (two capture calls).
    win = MainWindow(state)
    try:
        responses = iter(["not ready\n", "A>\n"])
        calls = []

        def fake_capture(cmd, cancellable=False, cancel_event=None):
            calls.append(cmd)
            return next(responses)

        monkeypatch.setattr(win, "_capture_terminal_response", fake_capture)
        refreshed = []
        monkeypatch.setattr(win, "refresh_remote_files", lambda: refreshed.append(True))
        win._do_connect_probe_logic()
        qapp.processEvents()
        assert len(calls) == 2
        assert win.drive_combo.currentText() == "A:"
        assert refreshed == [True]
    finally:
        win.close()


def test_connect_probe_failure_abort_disconnects(qapp, monkeypatch, state):
    """Verifies: FR-044, FR-045."""
    # FR-044/FR-045: no prompt after the retry -> show the dialog; choosing Abort
    # closes the port(s) via the Disconnect behaviour.
    from cpm_fm.gui.remote_unavailable_dialog import RemoteUnavailableDialog

    win = MainWindow(state)
    try:
        monkeypatch.setattr(
            RemoteUnavailableDialog,
            "exec",
            lambda self: setattr(self, "choice", RemoteUnavailableDialog.ABORT),
        )
        actions = []
        monkeypatch.setattr(win, "do_disconnect", lambda: actions.append("disconnect"))
        monkeypatch.setattr(win, "show_terminal", lambda: actions.append("terminal"))
        win._on_connect_probe_failed()
        assert actions == ["disconnect"]
    finally:
        win.close()


def test_connect_probe_failure_terminal_opens_terminal(qapp, monkeypatch, state):
    """Verifies: FR-045."""
    # FR-045: choosing Terminal opens the Terminal Window and leaves ports open.
    from cpm_fm.gui.remote_unavailable_dialog import RemoteUnavailableDialog

    win = MainWindow(state)
    try:
        monkeypatch.setattr(
            RemoteUnavailableDialog,
            "exec",
            lambda self: setattr(self, "choice", RemoteUnavailableDialog.TERMINAL),
        )
        actions = []
        monkeypatch.setattr(win, "do_disconnect", lambda: actions.append("disconnect"))
        monkeypatch.setattr(win, "show_terminal", lambda: actions.append("terminal"))
        win._on_connect_probe_failed()
        assert actions == ["terminal"]
    finally:
        win.close()


def test_connect_probe_failure_continue_no_action(qapp, monkeypatch, state):
    """Verifies: FR-045."""
    # FR-045: choosing Continue takes no action — ports stay open, no terminal.
    from cpm_fm.gui.remote_unavailable_dialog import RemoteUnavailableDialog

    win = MainWindow(state)
    try:
        monkeypatch.setattr(
            RemoteUnavailableDialog,
            "exec",
            lambda self: setattr(self, "choice", RemoteUnavailableDialog.CONTINUE),
        )
        actions = []
        monkeypatch.setattr(win, "do_disconnect", lambda: actions.append("disconnect"))
        monkeypatch.setattr(win, "show_terminal", lambda: actions.append("terminal"))
        win._on_connect_probe_failed()
        assert actions == []
    finally:
        win.close()


def test_change_drive_requires_open_terminal(qapp, monkeypatch, state):
    """Verifies: FR-104."""
    # FR-104: selecting a drive with the Terminal Port closed clears the list,
    # sets the status, and starts no worker thread.
    win = MainWindow(state)
    try:
        win.remote_list.addItem("STALE.TXT")
        win.serial_mgr.terminal_connected = False
        started = []

        class _RecordingThread:
            def __init__(self, *a, **k):
                started.append(a)

            def start(self):
                pass

        monkeypatch.setattr("cpm_fm.app.threading.Thread", _RecordingThread)
        win.drive_combo.setCurrentIndex(1)  # "B:"
        win.change_drive(1)
        qapp.processEvents()
        assert started == []
        assert win.remote_list.count() == 0
        expected_msg = "Terminal port not connected - cannot read file list"
        assert win.statusBar().currentMessage() == expected_msg
    finally:
        win.close()


def test_update_switches_to_displayed_drive_first(qapp, monkeypatch, state):
    """Verifies: FR-073."""
    # FR-073 (OI-22): the Update button must list the drive shown in the
    # drop-down, not the remote's then-current drive. It runs the drive-change
    # logic for the displayed drive, so the displayed letter is the one sent.
    win = MainWindow(state)
    try:
        win.serial_mgr.terminal_connected = True
        win.drive_combo.setCurrentIndex(2)  # "C:"
        targets = []

        class _RecordingThread:
            def __init__(self, *a, target=None, args=(), **k):
                targets.append((target, args))

            def start(self):
                pass

        monkeypatch.setattr("cpm_fm.app.threading.Thread", _RecordingThread)
        win.refresh_remote_files()
        assert targets == [(win._do_change_drive_logic, ("C",))]
    finally:
        win.close()


def test_update_button_shows_error_dialog_when_disconnected(qapp, monkeypatch, state):
    # Clicking Update with the port closed pops the same critical error dialog
    # as Copy to Host, in addition to setting the status and clearing the list.
    win = MainWindow(state)
    try:
        win.remote_list.addItem("STALE.TXT")
        win.serial_mgr.terminal_connected = False
        errors = []
        monkeypatch.setattr("cpm_fm.app.QMessageBox.critical", lambda *a, **k: errors.append(a[1:]))
        win.do_refresh_remote_files()
        qapp.processEvents()
        assert errors == [("Error", "Terminal port not connected")]
        assert win.remote_list.count() == 0
        expected_msg = "Terminal port not connected - cannot read file list"
        assert win.statusBar().currentMessage() == expected_msg
    finally:
        win.close()


def test_update_auto_refresh_skips_error_dialog_when_disconnected(qapp, monkeypatch, state):
    # The post-transfer auto-refresh path (refresh_remote_files) must not raise
    # the error dialog even when the port has since closed.
    win = MainWindow(state)
    try:
        win.serial_mgr.terminal_connected = False
        errors = []
        monkeypatch.setattr("cpm_fm.app.QMessageBox.critical", lambda *a, **k: errors.append(a[1:]))
        win.refresh_remote_files()
        qapp.processEvents()
        assert errors == []
    finally:
        win.close()


def test_disconnect_clears_remote_list(qapp, monkeypatch, state):
    """Verifies: FR-058."""
    # FR-058: a successful disconnect clears the (now-stale) Remote Files list.
    win = MainWindow(state)
    try:
        win.settings = {"terminal_port": "COM3", "transport_port": "COM3"}
        win.serial_mgr.terminal_connected = True
        win.serial_mgr.transport_connected = True
        monkeypatch.setattr(win.serial_mgr, "close_terminal_port", lambda: True)
        win.remote_list.addItems(["STALE.TXT", "OLD.COM"])
        win.do_disconnect()
        qapp.processEvents()
        assert win.remote_list.count() == 0
    finally:
        win.close()


def test_disconnect_keeps_remote_list_when_close_fails(qapp, monkeypatch, state):
    """Verifies: FR-058, FR-051."""
    # FR-058/FR-051: if the Terminal Port cannot be closed the disconnect is
    # cancelled and the Remote Files list is left untouched.
    win = MainWindow(state)
    try:
        win.settings = {"terminal_port": "COM3", "transport_port": "COM3"}
        win.serial_mgr.terminal_connected = True
        monkeypatch.setattr(win.serial_mgr, "close_terminal_port", lambda: False)
        monkeypatch.setattr("cpm_fm.app.QMessageBox.critical", lambda *a, **k: None)
        win.remote_list.addItems(["STALE.TXT"])
        win.do_disconnect()
        qapp.processEvents()
        assert win.remote_list.count() == 1
    finally:
        win.close()


def test_disconnect_shared_port_also_clears_transport_flag(qapp, monkeypatch, state):
    """Verifies: FR-054."""
    # FR-054: when Transport and Terminal are the same physical port, closing
    # the Terminal Port on disconnect must also clear the Transport flag.
    win = MainWindow(state)
    try:
        win.settings = {"terminal_port": "COM3", "transport_port": "COM3"}
        win.serial_mgr.terminal_connected = True
        win.serial_mgr.transport_connected = True
        monkeypatch.setattr(win.serial_mgr, "close_terminal_port", lambda: True)
        win.do_disconnect()
        qapp.processEvents()
        assert win.serial_mgr.transport_connected is False
    finally:
        win.close()


def test_disconnect_cancels_and_joins_in_flight_probe(qapp, monkeypatch, state):
    """Verifies: FR-050."""
    # FR-050: a Disconnect while the connect probe is still running must set the
    # probe-cancel flag and join the probe worker BEFORE closing the port, so the
    # probe's serial I/O cannot contend with the close (the misconfigured-port
    # hang). A real worker thread that blocks until cancelled proves both the
    # signal and the join actually happen.
    import threading

    win = MainWindow(state)
    try:
        win.settings = {"terminal_port": "COM3", "transport_port": "COM3"}
        win.serial_mgr.terminal_connected = True
        win.serial_mgr.transport_connected = True

        closed_while_alive = []

        def fake_worker():
            # Runs until Disconnect requests cancellation (bounded so the test
            # can never hang even if the flag is never set).
            win._probe_cancel.wait(timeout=5.0)

        win._probe_cancel.clear()
        probe_thread = threading.Thread(target=fake_worker, daemon=True)
        win._probe_thread = probe_thread
        probe_thread.start()

        def fake_close():
            # Captured at close time: the probe must already have stopped, so its
            # serial I/O cannot contend with the close.
            closed_while_alive.append(probe_thread.is_alive())
            return True

        monkeypatch.setattr(win.serial_mgr, "close_terminal_port", fake_close)

        win.do_disconnect()
        qapp.processEvents()

        assert win._probe_cancel.is_set()  # cancellation was requested
        assert win._probe_thread is None  # worker was joined and cleared
        assert closed_while_alive == [False]  # probe had stopped before the close
    finally:
        win._probe_cancel.set()
        win.close()


def test_probe_stops_without_emitting_when_cancelled(qapp, monkeypatch, state):
    """Verifies: FR-050."""
    # FR-050: if a Disconnect cancels the probe, the worker returns without
    # emitting connect_probe_ok/failed, so neither the Remote list is refreshed
    # nor the Remote Filesystem Unavailable dialog is shown.
    win = MainWindow(state)
    try:
        monkeypatch.setattr(win, "_probe_for_drive", lambda: None)
        # Neutralise the failure dialog so an (incorrect) emit could not hang the
        # test, and record any downstream effect of either signal firing.
        shown = []
        monkeypatch.setattr(
            "cpm_fm.gui.mw_remote.RemoteUnavailableDialog.exec",
            lambda self: shown.append(True),
        )
        refreshed = []
        monkeypatch.setattr(win, "refresh_remote_files", lambda: refreshed.append(True))
        win._probe_cancel.set()
        win._do_connect_probe_logic()
        qapp.processEvents()
        assert shown == []  # no Remote Filesystem Unavailable dialog (failed path)
        assert refreshed == []  # no ok-path refresh either
    finally:
        win.close()


def test_disconnect_transport_close_failure_shows_error_dialog(qapp, monkeypatch, state):
    """Verifies: FR-056."""
    # FR-056: when the Transport Port cannot be closed, an error dialog with
    # the exact specified text is shown.
    win = MainWindow(state)
    try:
        win.settings = {"terminal_port": "COM3", "transport_port": "COM4"}
        win.serial_mgr.terminal_connected = True
        win.serial_mgr.transport_connected = True
        monkeypatch.setattr(win.serial_mgr, "close_terminal_port", lambda: True)
        monkeypatch.setattr(win.serial_mgr, "close_transport_port", lambda: False)
        errors = []
        monkeypatch.setattr("cpm_fm.app.QMessageBox.critical", lambda *a, **k: errors.append(a[1:]))
        win.do_disconnect()
        qapp.processEvents()
        assert errors == [("Error", "Transport port is unable to be closed")]
    finally:
        win.close()


def test_host_update_button_refreshes_host_only(qapp, monkeypatch, state):
    """Verifies: FR-063."""
    # FR-063 (OI-14, v2.12): the Host Files group's Update button refreshes the
    # Host list only and must NOT re-populate the Remote list.
    from PySide6.QtWidgets import QPushButton

    win = MainWindow(state)
    try:
        calls = []
        monkeypatch.setattr(win, "refresh_host_files", lambda: calls.append("host"))
        monkeypatch.setattr(win, "refresh_remote_files", lambda: calls.append("remote"))
        update_btn = next(
            b
            for b in win.host_group.findChildren(QPushButton)
            if b.text() == i18n.tr("main.update")
        )
        update_btn.click()
        qapp.processEvents()
        assert calls == ["host"]
    finally:
        win.close()


def test_disconnect_attempts_close_when_flags_false(qapp, monkeypatch, state):
    """Verifies: FR-050, FR-055."""
    # FR-050/FR-055 (OI-24): the close attempts are unconditional. Even when the
    # status flags read disconnected (they may have drifted out of sync with the
    # real port state), pressing Disconnect must still try to close both ports.
    win = MainWindow(state)
    try:
        win.settings = {"terminal_port": "COM3", "transport_port": "COM4"}
        win.serial_mgr.terminal_connected = False
        win.serial_mgr.transport_connected = False
        closed = []
        monkeypatch.setattr(
            win.serial_mgr, "close_terminal_port", lambda: (closed.append("term"), True)[1]
        )
        monkeypatch.setattr(
            win.serial_mgr, "close_transport_port", lambda: (closed.append("trans"), True)[1]
        )
        win.do_disconnect()
        qapp.processEvents()
        assert closed == ["term", "trans"]
    finally:
        win.close()


def test_connect_shared_port_assigns_transport_port(qapp, monkeypatch, state):
    """Verifies: FR-037."""
    # FR-037: when the Transport and Terminal Ports are the same physical port,
    # connecting must point transport_port at the open terminal port object (not
    # leave it None) so transfers have a real port. Regression for the
    # "'NoneType' object has no attribute 'in_waiting'" crash on Copy to Remote.
    win = MainWindow(state)
    try:
        win.settings = {"terminal_port": "COM7", "transport_port": "COM7"}
        fake = _FakeSerial()

        def fake_open(port_type, _settings):
            assert port_type == "terminal"  # the shared case never opens transport
            win.serial_mgr.terminal_port = fake
            win.serial_mgr.terminal_connected = True
            return True

        monkeypatch.setattr(win.serial_mgr, "open_port", fake_open)
        win.do_connect()
        qapp.processEvents()
        assert win.serial_mgr.transport_connected is True
        assert win.serial_mgr.transport_port is fake
    finally:
        win.close()


def test_load_config_clears_remote_list(qapp, state, tmp_path):
    """Verifies: FR-017."""
    # FR-017: loading a configuration file clears the (now-stale) Remote Files list.
    win = MainWindow(state)
    try:
        cfg = tmp_path / "serial.json"
        cfg.write_text('{"terminal_port": "COM3"}')
        win.remote_list.addItems(["STALE.TXT", "OLD.COM"])
        win.load_config(str(cfg))
        qapp.processEvents()
        assert win.remote_list.count() == 0
    finally:
        win.close()


def test_load_config_disconnects_open_ports_before_swap(qapp, monkeypatch, state, tmp_path):
    """Verifies: FR-017a."""
    # FR-017a: loading a config while connected must close the PRIOR config's
    # ports first, and the close must run while self.settings still describes
    # them (do_disconnect reads the port names from settings) — otherwise the
    # old ports stay open while the app "connects" to ports that don't match the
    # newly loaded config.
    win = MainWindow(state)
    try:
        cfg = tmp_path / "new.json"
        cfg.write_text('{"terminal_port": "COM_NEW"}')
        win.settings = {"terminal_port": "COM_OLD"}
        win.serial_mgr.terminal_connected = True

        seen = {}

        def fake_disconnect():
            # The settings visible here must still be the OLD config.
            seen["terminal_port"] = win.settings.get("terminal_port")
            win.serial_mgr.terminal_connected = False

        monkeypatch.setattr(win, "do_disconnect", fake_disconnect)
        monkeypatch.setattr(win, "refresh_host_files", lambda: None)

        win.load_config(str(cfg))
        qapp.processEvents()

        # Disconnect ran before the swap and saw the prior config's port.
        assert seen == {"terminal_port": "COM_OLD"}
        # The new configuration is now loaded.
        assert win.settings.get("terminal_port") == "COM_NEW"
    finally:
        win.close()


def test_load_config_skips_disconnect_when_not_connected(qapp, monkeypatch, state, tmp_path):
    """Verifies: FR-017a."""
    # FR-017a: with nothing open (e.g. the start-up reload of the last-used
    # file, FR-005), the load must NOT trigger a disconnect — no spurious close,
    # status, or indicator churn.
    win = MainWindow(state)
    try:
        cfg = tmp_path / "new.json"
        cfg.write_text('{"terminal_port": "COM_NEW"}')
        win.serial_mgr.terminal_connected = False
        win.serial_mgr.transport_connected = False

        called = []
        monkeypatch.setattr(win, "do_disconnect", lambda: called.append(1))
        monkeypatch.setattr(win, "refresh_host_files", lambda: None)

        win.load_config(str(cfg))
        qapp.processEvents()

        assert called == []
    finally:
        win.close()


def test_main_window_constructs(qapp, state):
    """Verifies: FR-060, FR-070, UIR-014."""
    win = MainWindow(state)
    try:
        # Lists start consistent (FR-060 host populated lazily; FR-070 remote empty).
        assert win.host_list is not None
        assert win.remote_list.count() == 0  # FR-070: remote list empty at startup.
        # set_status truncates to 127 chars (UIR-014) via the queued signal slot.
        win.set_status("x" * 200)
        qapp.processEvents()
        assert len(win.statusBar().currentMessage()) == 127
    finally:
        win.close()


def test_terminal_window_render_and_clear(qapp):
    """Verifies: FR-091, FR-095."""
    # The receive area renders the VT-100 engine's screen; Clear resets the
    # engine (blanking the screen) and invokes the buffer-clear callback.
    from cpm_fm.terminal.vt100_engine import VT100Engine

    engine = VT100Engine()
    cleared = []
    term = TerminalWindow(
        None,
        clear_callback=lambda: cleared.append(1),
        engine=engine,
    )
    try:
        engine.feed(b"HELLO")
        term.render_screen()
        assert engine.display[0].rstrip() == "HELLO"
        term.receive_area._grid.grab()  # offscreen paint must not raise

        term.clear_text()
        assert engine.display[0].rstrip() == ""  # FR-095: screen reset
        assert cleared == [1]  # FR-095: Clear invokes the buffer-clear callback.
    finally:
        term.deleteLater()


def test_terminal_window_renders_engine_screen(qapp):
    """Verifies: FR-091."""
    # Escape sequences drive the on-screen result: cursor addressing overwrites
    # an existing line and the grid paints without error.
    from cpm_fm.terminal.vt100_engine import VT100Engine

    engine = VT100Engine()
    term = TerminalWindow(None, engine=engine)
    try:
        engine.feed(b"L1\r\nL2\r\n\x1b[1;1Hedited")  # home, then overwrite row 0
        term.render_screen()
        assert engine.display[0].rstrip() == "edited"
        assert engine.display[1].rstrip() == "L2"
        term.receive_area._grid.grab()  # offscreen paint must not raise
    finally:
        term.deleteLater()


def test_terminal_window_keystroke_transmits(qapp):
    """Verifies: FR-096, FR-094."""
    # Typing into the receive area encodes the key and hands the bytes to the
    # key callback (there is no transmit field); Enter sends the configured EOL.
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent

    sent = []
    term = TerminalWindow(None, key_callback=sent.append)
    try:
        term.set_eol(b"\r\n")

        def press(key, text):
            term.receive_area.keyPressEvent(
                QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier, text)
            )

        press(Qt.Key.Key_A, "A")
        press(Qt.Key.Key_Return, "\r")
        assert sent == [b"A", b"\r\n"]  # printable key, then the EOL for Enter
    finally:
        term.deleteLater()


def test_font_dialog_lists_survive_app_theme_height(qapp):
    """The font dialog's family/style/size lists stay usable under the app theme.

    The application-wide Material stylesheet (UIR-070) pins every QListView to a
    fixed 36px height, which would collapse QFontDialog's selection lists to a
    single unusable row. Reproduce that rule at the application level and assert
    the dialog built by TerminalWindow restores usably tall lists (the scoped
    ``_FONT_DIALOG_STYLE`` override).

    Verifies: UIR-069.
    """
    from PySide6.QtWidgets import QListView

    app = QApplication.instance()
    saved = app.styleSheet()
    term = TerminalWindow(None)
    dlg = None
    try:
        # Mimic the qt-material rule that collapses list views app-wide.
        app.setStyleSheet("QListView { height: 36px; }")
        dlg = term._build_font_dialog()
        dlg.show()
        qapp.processEvents()
        lists = dlg.findChildren(QListView)
        # The family/style/size lists (3 of them) must be far taller than the
        # collapsed 36px — i.e. the scoped override won over the app sheet.
        tall = [lv for lv in lists if lv.height() > 100]
        assert len(tall) >= 3, f"font-dialog lists collapsed: {[lv.height() for lv in lists]}"
    finally:
        if dlg is not None:
            dlg.deleteLater()
        term.deleteLater()
        app.setStyleSheet(saved)


def test_handle_terminal_key_sends_echoes_and_guards(qapp, state):
    """Verifies: FR-096, FR-092, FR-093, FR-098."""
    win = MainWindow(state)
    try:
        # FR-098: with no open Terminal Port, nothing is sent and the status
        # bar reports it.
        win.serial_mgr.terminal_connected = False
        win.handle_terminal_key(b"A")
        qapp.processEvents()
        assert win.statusBar().currentMessage() == i18n.tr("status.terminal_not_open_send")

        class _Port:
            is_open = True

            def __init__(self):
                self.written = bytearray()

            def write(self, data):
                self.written += data

            def close(self):
                self.is_open = False

        port = _Port()
        win.serial_mgr.terminal_port = port
        win.serial_mgr.terminal_connected = True
        win._tx_buffer = ""
        win._local_echo = False
        emitted = []
        win.term_write.connect(emitted.append)

        # FR-096/FR-092: raw bytes are transmitted and recorded in the tx buffer;
        # FR-093: with echo off, nothing is echoed to the screen.
        win.handle_terminal_key(b"\x03")  # Ctrl-C
        qapp.processEvents()
        assert bytes(port.written) == b"\x03"
        assert win._tx_buffer == "\x03"
        assert emitted == []

        # FR-093: with echo on, the same bytes are emitted to the engine/display.
        win._local_echo = True
        win.handle_terminal_key(b"X")
        qapp.processEvents()
        assert bytes(port.written) == b"\x03X"
        assert emitted == [b"X"]
    finally:
        win.close()


def test_handle_terminal_send_append_eol_flag(qapp, monkeypatch, state):
    """Verifies: FR-094."""
    # FR-094: handle_terminal_send (used by the boot sequence and the capture
    # reads) appends the configured EOL by default, but sends the data verbatim
    # when append_eol is False.
    win = MainWindow(state)
    try:
        win.settings = {"eol": "CR"}
        win.serial_mgr.terminal_connected = True
        sent = []
        monkeypatch.setattr(
            win.serial_mgr, "send_data", lambda port, data: sent.append(data) or True
        )
        win.handle_terminal_send("DIR")
        assert sent[-1] == "DIR\r"  # default: EOL appended
        win.handle_terminal_send("\x03", append_eol=False)
        assert sent[-1] == "\x03"  # bare control byte, no EOL
    finally:
        win.close()


def test_terminal_context_menu_has_six_items_and_copy_state(qapp):
    """The Receive-view context menu offers the six actions; Copy tracks state.

    Verifies: UIR-099, FR-165, UIR-105.
    """
    from PySide6.QtCore import Qt

    from cpm_fm.terminal.vt100_engine import VT100Engine

    engine = VT100Engine(cols=10, rows=3)
    term = TerminalWindow(None, engine=engine)
    try:
        menu = term._build_context_menu()
        # Top-level command actions only (exclude separators and the submenus).
        actions = [a for a in menu.actions() if not a.isSeparator() and a.menu() is None]
        labels = [a.text() for a in actions]
        assert labels == [
            i18n.tr("terminal.menu.copy"),
            i18n.tr("terminal.menu.paste"),
            i18n.tr("terminal.menu.clear"),
            i18n.tr("terminal.menu.font"),
            i18n.tr("terminal.menu.reset_size"),
            i18n.tr("terminal.menu.boot"),
        ]
        # FR-165: Copy disabled with no selection, enabled once text is selected.
        assert actions[0].isEnabled() is False
        engine.feed(b"HELLO")
        term.receive_area.refresh()
        cw = term.receive_area._cell_w
        term.receive_area._mouse_press(0, 0, Qt.MouseButton.LeftButton)
        term.receive_area._mouse_move(5 * cw, 0)
        term.receive_area._mouse_release(5 * cw, 0, Qt.MouseButton.LeftButton)
        assert term._build_context_menu().actions()[0].isEnabled() is True
    finally:
        term.deleteLater()


def test_terminal_context_menu_boot_enabled_reflects_provider(qapp):
    """The Boot into CP/M item is enabled only when a boot sequence is configured.

    Verifies: UIR-105, FR-049.
    """
    from cpm_fm.terminal.vt100_engine import VT100Engine

    configured = {"boot": False}
    term = TerminalWindow(
        None, engine=VT100Engine(), boot_enabled_provider=lambda: configured["boot"]
    )
    try:

        def boot_action():
            menu = term._build_context_menu()
            return next(a for a in menu.actions() if a.text() == i18n.tr("terminal.menu.boot"))

        # UIR-105: disabled with no boot sequence configured.
        assert boot_action().isEnabled() is False
        # ...enabled once one is configured (re-evaluated each time the menu opens).
        configured["boot"] = True
        assert boot_action().isEnabled() is True
    finally:
        term.deleteLater()


def test_terminal_reset_size_reflows_to_80x24(qapp):
    """Reset Size resizes the window so the grid reflows to 80 columns x 24 rows.

    Verifies: FR-167.
    """
    from cpm_fm.terminal.vt100_engine import VT100Engine

    engine = VT100Engine()
    term = TerminalWindow(None, engine=engine)
    try:
        term.show()  # only a visible view reflows (FR-091a)
        term.resize(300, 200)
        qapp.processEvents()
        term.reset_size()
        qapp.processEvents()
        assert (engine.cols, engine.rows) == (80, 24)
    finally:
        term.close()
        term.deleteLater()


def test_terminal_paste_action_reads_clipboard_and_calls_callback(qapp):
    """The Paste action feeds the clipboard text to the paste callback.

    Verifies: FR-166.
    """
    pasted = []
    term = TerminalWindow(None, paste_callback=pasted.append)
    try:
        QApplication.clipboard().setText("DIR\n")
        term._on_paste()
        assert pasted == ["DIR\n"]
    finally:
        term.deleteLater()


def test_handle_terminal_paste_normalises_sends_buffers_echoes(qapp, monkeypatch, state):
    """Paste converts newlines to EOL, transmits, buffers, and echoes.

    Verifies: FR-166, FR-092, FR-093, FR-094, FR-098.
    """
    win = MainWindow(state)
    try:
        win.settings = {"eol": "CR"}
        # FR-098: with the port closed, nothing is sent and the status reports it.
        win.serial_mgr.terminal_connected = False
        win.handle_terminal_paste("A\nB")
        qapp.processEvents()
        assert win.statusBar().currentMessage() == i18n.tr("status.terminal_not_open_send")

        sent = []
        monkeypatch.setattr(
            win.serial_mgr, "send_raw", lambda port, data: sent.append((port, data))
        )
        win.serial_mgr.terminal_connected = True
        win._tx_buffer = ""
        win._local_echo = False
        emitted = []
        win.term_write.connect(emitted.append)

        # FR-094: "\r\n", "\r", and "\n" all normalise to the configured EOL (CR).
        win.handle_terminal_paste("A\r\nB\rC\nD")
        qapp.processEvents()
        assert sent == [("terminal", b"A\rB\rC\rD")]
        assert win._tx_buffer == "A\rB\rC\rD"  # FR-092
        assert emitted == []  # FR-093: echo off => nothing echoed

        # FR-093: with echo on, the transmitted bytes are echoed to the screen.
        win._local_echo = True
        win.handle_terminal_paste("X")
        qapp.processEvents()
        assert emitted == [b"X"]
    finally:
        win.close()


def _submenus(menu):
    """Map submenu title -> QMenu for the submenu actions of ``menu``."""
    return {a.menu().title(): a.menu() for a in menu.actions() if a.menu() is not None}


def test_terminal_context_menu_terminal_type_submenu(qapp):
    """The Terminal Type submenu lists the types, checks the active one, applies.

    Verifies: UIR-101, UIR-099.
    """
    from cpm_fm.terminal.term_translate import TERMINAL_TYPES, VT52
    from cpm_fm.terminal.vt100_engine import VT100Engine

    chosen = []
    engine = VT100Engine()  # default VT100
    term = TerminalWindow(None, engine=engine, terminal_type_callback=chosen.append)
    try:
        menu = term._build_context_menu()  # held so its submenus are not GC'd
        sub = _submenus(menu)[i18n.tr("terminal.menu.terminal_type")]
        acts = sub.actions()
        assert [a.text() for a in acts] == list(TERMINAL_TYPES)
        assert all(a.isCheckable() for a in acts)
        # UIR-101: only the active type (VT100) is checked.
        assert [a.text() for a in acts if a.isChecked()] == ["VT100"]
        # Selecting VT52 hands the value to the callback.
        next(a for a in acts if a.text() == VT52).trigger()
        assert chosen == [VT52]
    finally:
        term.deleteLater()


def test_terminal_window_status_bar_shows_terminal_type(qapp):
    """The status bar shows the active terminal type and refreshes on change.

    Verifies: UIR-106, UIR-064.
    """
    from cpm_fm.terminal.term_translate import VT52
    from cpm_fm.terminal.vt100_engine import VT100Engine

    engine = VT100Engine()  # default VT100
    term = TerminalWindow(None, engine=engine)
    try:
        # UIR-106: built with VT100, the status bar reads the active type.
        assert term.statusBar().currentMessage() == i18n.tr("terminal.status_type", type="VT100")
        # A type change (as a context-menu selection makes, UIR-101) is reflected
        # after the next render.
        engine.set_terminal_type(VT52)
        term.render_screen()
        assert term.statusBar().currentMessage() == i18n.tr("terminal.status_type", type=VT52)
    finally:
        term.deleteLater()


def test_terminal_window_status_bar_follows_language(qapp):
    """The terminal-type status text re-applies the active UI language live.

    Verifies: UIR-106, FR-123.
    """
    from cpm_fm.terminal.vt100_engine import VT100Engine

    term = TerminalWindow(None, engine=VT100Engine())
    try:
        i18n.set_language("french")
        term.retranslate_ui()
        assert term.statusBar().currentMessage() == i18n.tr("terminal.status_type", type="VT100")
        # The French text differs from the English reference (guards against a
        # stale, un-retranslated status bar).
        i18n.set_language("english")
        assert term.statusBar().currentMessage() != i18n.tr("terminal.status_type", type="VT100")
    finally:
        i18n.set_language("english")
        term.deleteLater()


def test_terminal_context_menu_macros_submenu_lists_and_runs(qapp):
    """The Macros submenu lists configured macros and runs the chosen script.

    Verifies: UIR-102, FR-162.
    """
    from cpm_fm.terminal.vt100_engine import VT100Engine

    ran = []
    macros = [("Prompt", "SENDRAW 0D"), ("Dir", "SEND DIR")]
    term = TerminalWindow(
        None,
        engine=VT100Engine(),
        macros_provider=lambda: macros,
        run_macro_callback=ran.append,
    )
    try:
        menu = term._build_context_menu()  # held so its submenus are not GC'd
        sub = _submenus(menu)[i18n.tr("terminal.menu.macros_sub")]
        assert sub.isEnabled()
        assert [a.text() for a in sub.actions()] == ["Prompt", "Dir"]
        sub.actions()[0].trigger()  # FR-162: run the first macro's script
        assert ran == ["SENDRAW 0D"]
    finally:
        term.deleteLater()


def test_terminal_context_menu_macros_submenu_disabled_when_none(qapp):
    """The Macros submenu is present but disabled when no macros are configured.

    Verifies: UIR-102.
    """
    from cpm_fm.terminal.vt100_engine import VT100Engine

    term = TerminalWindow(None, engine=VT100Engine(), macros_provider=lambda: [])
    try:
        menu = term._build_context_menu()  # held so its submenus are not GC'd
        sub = _submenus(menu)[i18n.tr("terminal.menu.macros_sub")]
        assert not sub.isEnabled()
        assert sub.actions() == []
    finally:
        term.deleteLater()


def test_set_terminal_type_from_menu_applies_and_updates_setting(qapp, state):
    """Choosing a terminal type from the menu applies it and updates the setting.

    Verifies: UIR-101, UIR-034.
    """
    from cpm_fm.terminal.term_translate import ADM3A

    win = MainWindow(state)
    try:
        win._set_terminal_type_from_menu(ADM3A)
        assert win.settings["terminal_type"] == ADM3A
        assert win._term_engine.terminal_type == ADM3A
    finally:
        win.close()


def test_configured_macros_filters_incomplete_slots(qapp, state):
    """_configured_macros returns only slots with both label and script set.

    Verifies: UIR-102, FR-162.
    """
    win = MainWindow(state)
    try:
        win.settings["macro_1_label"] = "Prompt"
        win.settings["macro_1_seq"] = "SENDRAW 0D"
        win.settings["macro_2_label"] = "  "  # blank label -> excluded
        win.settings["macro_2_seq"] = "SEND X"
        win.settings["macro_3_label"] = "NoScript"
        win.settings["macro_3_seq"] = "   "  # blank script -> excluded
        assert win._configured_macros() == [("Prompt", "SENDRAW 0D")]
    finally:
        win.close()


def test_apply_terminal_settings_applies_local_echo_and_autoscroll(qapp, state):
    """Local Echo and Autoscroll settings are applied to the running terminal.

    Verifies: UIR-103a, UIR-104, FR-093.
    """
    from cpm_fm.utils.config_handler import DEFAULT_SETTINGS

    win = MainWindow(state)
    try:
        win.settings = dict(DEFAULT_SETTINGS)
        win.settings["local_echo"] = "ON"
        win.settings["autoscroll"] = "OFF"
        win.show_terminal()  # applies the terminal settings on open
        assert win._local_echo is True  # FR-093
        assert win.terminal_win.receive_area._autoscroll is False  # UIR-104
        # A later change re-applied updates both.
        win.settings["local_echo"] = "OFF"
        win.settings["autoscroll"] = "ON"
        win._apply_terminal_settings()
        assert win._local_echo is False
        assert win.terminal_win.receive_area._autoscroll is True
    finally:
        win.close()


def test_apply_terminal_settings_refreshes_status_bar(qapp, state):
    """A Terminal Config save refreshes the open window's terminal-type status.

    Verifies: UIR-106, UIR-034.
    """
    from cpm_fm.terminal.term_translate import ADM3A
    from cpm_fm.utils.config_handler import DEFAULT_SETTINGS

    win = MainWindow(state)
    try:
        win.settings = dict(DEFAULT_SETTINGS)
        win.show_terminal()
        assert win.terminal_win.statusBar().currentMessage() == i18n.tr(
            "terminal.status_type", type="VT100"
        )
        # Changing the setting and re-applying (as a Terminal Config save does)
        # updates the open window's status bar.
        win.settings["terminal_type"] = ADM3A
        win._apply_terminal_settings()
        assert win.terminal_win.statusBar().currentMessage() == i18n.tr(
            "terminal.status_type", type=ADM3A
        )
    finally:
        win.close()


def test_show_history_is_nonmodal_and_reused(qapp, state):
    """The Transfer History window is non-modal and reused across openings.

    Verifies: FR-143, UIR-083.
    """
    win = MainWindow(state)
    try:
        win.show_history()
        first = win._history_dialog
        assert first is not None
        assert first.isVisible() is True
        assert first.isModal() is False  # UIR-083: non-modal
        win.show_history()  # already open -> raised, not duplicated
        assert win._history_dialog is first
    finally:
        win.close()


def test_history_finished_triggers_pending_retransfer(qapp, state, monkeypatch):
    """Closing the history window with a pending entry starts the re-transfer.

    Verifies: FR-144.
    """
    win = MainWindow(state)
    try:
        win.show_history()
        dlg = win._history_dialog
        entry = {"path": "/h/X.TXT", "direction": "remote", "filename": "X.TXT"}
        got = []
        monkeypatch.setattr(win, "_retransfer", got.append)
        # Simulate a Re-transfer click: record the entry, then close the window.
        dlg.retransfer_entry = entry
        dlg.accept()
        qapp.processEvents()
        assert got == [entry]
        # The pending entry is consumed so a plain close does not re-fire it.
        assert dlg.retransfer_entry is None
    finally:
        win.close()


def test_open_windows_restored_on_startup(qapp, state):
    """Windows recorded open at exit are reopened on the next start-up.

    Verifies: FR-168.
    """
    state.set_window_open("terminal", True)
    state.set_window_open("history", True)
    win = MainWindow(state)
    try:
        assert win.terminal_win is not None and win.terminal_win.isVisible()
        assert win._history_dialog is not None and win._history_dialog.isVisible()
    finally:
        win.close()


def test_open_windows_not_restored_when_none_recorded(qapp, state):
    """No auxiliary windows are opened when none were recorded open.

    Verifies: FR-168.
    """
    win = MainWindow(state)
    try:
        assert win.terminal_win is None
        assert win._history_dialog is None
    finally:
        win.close()


def test_closeevent_records_which_windows_were_open(qapp, state):
    """On exit the open state of the Terminal/History windows is persisted.

    Verifies: FR-168.
    """
    win = MainWindow(state)
    win.show_terminal()
    win.show_history()
    win.close()
    assert state.window_open("terminal") is True
    assert state.window_open("history") is True

    # A session with neither open records both as closed. Clear the recorded
    # flags first so the new window does not restore the two windows on start-up.
    state.set_window_open("terminal", False)
    state.set_window_open("history", False)
    win2 = MainWindow(state)
    win2.close()
    assert state.window_open("terminal") is False
    assert state.window_open("history") is False


def test_geometry_and_last_config_persist_across_sessions(qapp, state, tmp_path):
    """Verifies: FR-004, FR-005."""
    # FR-004/FR-005: a session's main-window geometry and last-used config file
    # are saved on close and applied to a fresh session sharing the same store.
    cfg = tmp_path / "serial.json"
    cfg.write_text('{"terminal_port": "COM3", "speed": "9600"}')

    first = MainWindow(state)
    try:
        first.resize(742, 503)
        first.load_config(str(cfg))  # FR-005: records the path as last_config.
        first.close()  # closeEvent saves geometry (FR-004).
    finally:
        first.deleteLater()
    assert state.last_config == str(cfg)

    # A new window built from the same store restores both.
    second = MainWindow(state)
    try:
        assert (second.width(), second.height()) == (742, 503)
        assert second.settings == {"terminal_port": "COM3", "speed": "9600"}
    finally:
        second.close()
        second.deleteLater()


def test_menu_load_remembers_and_reuses_config_folder(qapp, monkeypatch, state, tmp_path):
    """Verifies: FR-006."""
    # FR-006: File > Load defaults to the last-used config folder and records the
    # folder of the chosen file, separately from the Host Files directory.
    cfg = tmp_path / "serial.json"
    cfg.write_text('{"terminal_port": "COM3"}')

    win = MainWindow(state)
    try:
        seen_dirs = []

        def fake_open(parent, caption, directory, filt):
            seen_dirs.append(directory)
            return str(cfg), filt

        monkeypatch.setattr("cpm_fm.gui.mw_config.QFileDialog.getOpenFileName", fake_open)
        win.menu_load()

        # First open started with no remembered folder; the chosen file's folder
        # is now persisted and is independent of the host directory.
        assert seen_dirs == [""]
        assert state.last_config_dir == str(tmp_path)

        win.menu_load()
        assert seen_dirs[-1] == str(tmp_path)
    finally:
        win.close()
        win.deleteLater()


def test_menu_new_saves_to_current_file_resets_and_closes_ports(qapp, monkeypatch, state, tmp_path):
    """Verifies: FR-018, FR-019."""
    # FR-018/FR-019: New saves the current config to the remembered file, closes
    # any open ports, clears the remote list, and replaces settings with the
    # defaults (forgetting the remembered file path).
    target = tmp_path / "current.json"
    target.write_text("{}")

    win = MainWindow(state)
    try:
        win.window_state.last_config = str(target)
        win.settings = {"terminal_port": "COM9", "speed": "300"}
        win.remote_list.addItems(["STALE.TXT"])
        monkeypatch.setattr(win, "refresh_host_files", lambda: None)
        disconnected = []
        monkeypatch.setattr(win, "do_disconnect", lambda: disconnected.append(1))

        win.menu_new()

        # FR-018: the previous configuration was written to its file.
        assert "COM9" in target.read_text()
        # FR-019: ports closed, remote list cleared, defaults applied, path forgotten.
        assert disconnected == [1]
        assert win.remote_list.count() == 0
        assert win.settings == DEFAULT_SETTINGS
        assert win.window_state.last_config == ""
    finally:
        win.close()
        win.deleteLater()


def test_menu_new_prompts_for_file_when_none_remembered(qapp, monkeypatch, state, tmp_path):
    """Verifies: FR-018."""
    # FR-018: with no remembered file, New presents the Save dialog before
    # resetting to the default configuration.
    target = tmp_path / "saved.json"

    win = MainWindow(state)
    try:
        win.window_state.last_config = ""
        win.settings = {"terminal_port": "COM9"}
        monkeypatch.setattr(win, "refresh_host_files", lambda: None)
        monkeypatch.setattr(
            "cpm_fm.gui.mw_config.QFileDialog.getSaveFileName",
            lambda *a, **k: (str(target), "JSON files (*.json)"),
        )

        win.menu_new()

        assert target.exists()
        assert win.settings == DEFAULT_SETTINGS
    finally:
        win.close()
        win.deleteLater()


def test_help_menu_contains_about_action(qapp, state):
    """Verifies: UIR-004."""
    # UIR-004: the Help menu lists an About action.
    from PySide6.QtWidgets import QMenu

    win = MainWindow(state)
    try:
        help_menus = [m for m in win.menuBar().findChildren(QMenu) if m.title() == "Help"]
        assert help_menus, "Help menu not found on the menu bar"
        labels = [act.text() for act in help_menus[0].actions()]
        assert "About" in labels
    finally:
        win.close()
        win.deleteLater()


def test_menu_about_opens_dialog(qapp, monkeypatch, state):
    """Verifies: FR-022."""
    # FR-022: selecting Help > About constructs and shows the About dialog.
    win = MainWindow(state)
    try:
        opened = []

        class _FakeAbout:
            def __init__(self, parent=None):
                opened.append(parent)

            def exec(self):
                return 1

        monkeypatch.setattr("cpm_fm.gui.mw_config.AboutDialog", _FakeAbout)
        win.menu_about()
        assert opened == [win]
    finally:
        win.close()
        win.deleteLater()


def test_about_dialog_contents(qapp):
    """Verifies: UIR-076."""
    # UIR-076: program name, version string, GitHub link, and an OK button.
    from PySide6.QtWidgets import QLabel, QPushButton

    dlg = AboutDialog()
    try:
        assert dlg.windowTitle() == "About"
        label_text = " ".join(lbl.text() for lbl in dlg.findChildren(QLabel))
        assert APP_NAME in label_text
        assert f"Version {get_version()}" in label_text
        assert REPO_URL in label_text
        # The hyperlink opens externally (host default browser).
        link = next(lbl for lbl in dlg.findChildren(QLabel) if REPO_URL in lbl.text())
        assert link.openExternalLinks()
        buttons = [b.text() for b in dlg.findChildren(QPushButton)]
        assert buttons == ["OK"]
    finally:
        dlg.deleteLater()


def test_help_menu_contains_manual_action(qapp, state):
    """Verifies: UIR-004, FR-023."""
    # UIR-004: the Help menu lists a Manual action (FR-023).
    from PySide6.QtWidgets import QMenu

    win = MainWindow(state)
    try:
        help_menus = [m for m in win.menuBar().findChildren(QMenu) if m.title() == "Help"]
        assert help_menus, "Help menu not found on the menu bar"
        labels = [act.text() for act in help_menus[0].actions()]
        assert "Manual" in labels
    finally:
        win.close()
        win.deleteLater()


def test_menu_manual_opens_dialog(qapp, monkeypatch, state):
    """Verifies: FR-023."""
    # FR-023: selecting Help > Manual constructs and shows the Manual dialog.
    win = MainWindow(state)
    try:
        opened = []

        class _FakeManual:
            def __init__(self, parent=None):
                opened.append(parent)

            def isVisible(self):
                return False

            def show(self):
                pass

        monkeypatch.setattr("cpm_fm.gui.mw_config.ManualDialog", _FakeManual)
        win.menu_manual()
        assert opened == [win]
    finally:
        win.close()
        win.deleteLater()


def test_menu_manual_reuses_open_window(qapp, monkeypatch, state):
    """Verifies: FR-023."""
    # FR-023: a second Help > Manual raises the existing window instead of
    # opening a second copy.
    win = MainWindow(state)
    try:
        constructed = []
        raised = []

        class _FakeManual:
            def __init__(self, parent=None):
                constructed.append(parent)

            def isVisible(self):
                return True

            def show(self):
                pass

            def raise_(self):
                raised.append(True)

            def activateWindow(self):
                pass

        monkeypatch.setattr("cpm_fm.gui.mw_config.ManualDialog", _FakeManual)
        win.menu_manual()  # opens
        win.menu_manual()  # should raise the existing one
        assert len(constructed) == 1
        assert raised == [True]
    finally:
        win.close()
        win.deleteLater()


def test_manual_dialog_contents(qapp):
    """Verifies: UIR-091."""
    # UIR-091: titled "User Manual", renders the manual as HTML, Close button.
    from PySide6.QtWidgets import QPushButton, QTextBrowser

    from cpm_fm.gui.manual_dialog import ManualDialog, load_manual_markdown

    dlg = ManualDialog()
    try:
        assert dlg.windowTitle() == "User Manual"
        assert not dlg.isModal()
        browser = dlg.findChild(QTextBrowser)
        assert browser is not None
        assert browser.openExternalLinks()
        # The manual rendered, so its text is present in the view.
        assert "CP/M File Manager" in browser.toPlainText()
        buttons = [b.text() for b in dlg.findChildren(QPushButton)]
        assert buttons == ["Close"]
    finally:
        dlg.deleteLater()

    # The manual file is bundled and readable from source.
    assert load_manual_markdown() is not None


def test_render_manual_html_anchors_match_toc_links(qapp):
    """Verifies: UIR-091."""
    # UIR-091: the manual is rendered to HTML with GitHub-style heading anchors
    # so its table-of-contents links navigate within the document.
    import re

    from cpm_fm.gui.manual_dialog import load_manual_markdown, render_manual_html

    md = load_manual_markdown()
    assert md is not None
    html = render_manual_html(md)
    assert "<html>" in html
    heading_ids = set(re.findall(r'<h[1-6][^>]*id="([^"]+)"', html))
    toc_links = re.findall(r"\(#([a-z0-9-]+)\)", md)
    assert toc_links, "expected the manual to contain in-document TOC links"
    missing = [link for link in toc_links if link not in heading_ids]
    assert missing == [], f"TOC links without a matching heading anchor: {missing}"


def test_manual_dialog_handles_missing_file(qapp, monkeypatch):
    """Verifies: DR-047."""
    # DR-047: an unreadable manual shows a message rather than crashing.
    from PySide6.QtWidgets import QTextBrowser

    from cpm_fm.gui import manual_dialog

    monkeypatch.setattr(manual_dialog, "load_manual_markdown", lambda: None)
    dlg = manual_dialog.ManualDialog()
    try:
        browser = dlg.findChild(QTextBrowser)
        assert browser is not None
        assert browser.toPlainText().strip() != ""
    finally:
        dlg.deleteLater()


def test_menu_new_aborts_when_save_cancelled(qapp, monkeypatch, state):
    """Verifies: FR-018."""
    # FR-018: cancelling the Save dialog cancels New entirely — the current
    # configuration, ports, and remote list are retained.
    win = MainWindow(state)
    try:
        win.window_state.last_config = ""
        win.settings = {"terminal_port": "COM9"}
        win.remote_list.addItems(["KEEP.TXT"])
        disconnected = []
        monkeypatch.setattr(win, "do_disconnect", lambda: disconnected.append(1))
        monkeypatch.setattr(
            "cpm_fm.gui.mw_config.QFileDialog.getSaveFileName", lambda *a, **k: ("", "")
        )

        win.menu_new()

        assert win.settings == {"terminal_port": "COM9"}
        assert disconnected == []
        assert win.remote_list.count() == 1
    finally:
        win.close()
        win.deleteLater()


def test_menu_save_remembers_config_folder(qapp, monkeypatch, state, tmp_path):
    """Verifies: FR-006."""
    # FR-006: a successful File > Save records its folder for the next dialog.
    target = tmp_path / "out.json"

    win = MainWindow(state)
    try:
        monkeypatch.setattr(
            "cpm_fm.gui.mw_config.QFileDialog.getSaveFileName",
            lambda *a, **k: (str(target), "JSON files (*.json)"),
        )
        win.menu_save()
        assert state.last_config_dir == str(tmp_path)
    finally:
        win.close()
        win.deleteLater()


# --------------------------------------------------------------- file actions


def test_build_viewer_args_substitutes_token():
    """Verifies: FR-112."""
    # FR-112: $1 is replaced by the file path; a path with spaces stays a single
    # argument and is never re-split by the tokeniser.
    from cpm_fm.app import build_viewer_args

    assert build_viewer_args("notepad $1", "C:/dir/F.TXT") == ["notepad", "C:/dir/F.TXT"]
    assert build_viewer_args("notepad $1", "/tmp/a b/F.TXT") == ["notepad", "/tmp/a b/F.TXT"]
    # No $1 token -> the path is appended as the final argument.
    assert build_viewer_args("editor", "F.TXT") == ["editor", "F.TXT"]


def test_lists_have_context_menus(qapp, state):
    """Verifies: UIR-018, UIR-019."""
    # UIR-018/UIR-019: both file lists expose a custom (right-click) context menu.
    from PySide6.QtCore import Qt

    win = MainWindow(state)
    try:
        assert win.host_list.contextMenuPolicy() == Qt.ContextMenuPolicy.CustomContextMenu
        assert win.remote_list.contextMenuPolicy() == Qt.ContextMenuPolicy.CustomContextMenu
    finally:
        win.close()


def test_host_view_launches_viewer(qapp, monkeypatch, state, tmp_path):
    """Verifies: FR-110, FR-112."""
    # FR-110/FR-112: View/Edit launches viewer_cmd with the host file path.
    win = MainWindow(state)
    try:
        win.host_dir = str(tmp_path)
        win.settings = {"viewer_cmd": "myview $1"}
        launched = []
        monkeypatch.setattr(
            "cpm_fm.app.subprocess.Popen", lambda args, *a, **k: launched.append(args)
        )
        win._host_view("F.TXT")
        assert launched == [["myview", os.path.join(str(tmp_path), "F.TXT")]]
    finally:
        win.close()


def test_host_rename_renames_file(qapp, monkeypatch, state, tmp_path):
    """Verifies: FR-114, FR-116, FR-118."""
    # FR-114/FR-116/FR-118: Apply on the rename dialog renames the file and refreshes.
    win = MainWindow(state)
    try:
        win.host_dir = str(tmp_path)
        (tmp_path / "OLD.TXT").write_text("x")
        monkeypatch.setattr(
            "cpm_fm.gui.mw_context_menu.FileActionDialog", _fake_action_dialog("NEW.TXT")
        )
        refreshed = []
        monkeypatch.setattr(win, "refresh_host_files", lambda: refreshed.append(1))
        win._host_rename("OLD.TXT")
        assert (tmp_path / "NEW.TXT").exists()
        assert not (tmp_path / "OLD.TXT").exists()
        assert refreshed == [1]
    finally:
        win.close()


def test_host_rename_cancelled_makes_no_change(qapp, monkeypatch, state, tmp_path):
    """Verifies: FR-114."""
    # FR-114: Cancel leaves the file untouched.
    win = MainWindow(state)
    try:
        win.host_dir = str(tmp_path)
        (tmp_path / "OLD.TXT").write_text("x")
        monkeypatch.setattr(
            "cpm_fm.gui.mw_context_menu.FileActionDialog",
            _fake_action_dialog("NEW.TXT", accepted=False),
        )
        win._host_rename("OLD.TXT")
        assert (tmp_path / "OLD.TXT").exists()
        assert not (tmp_path / "NEW.TXT").exists()
    finally:
        win.close()


def test_host_delete_removes_file(qapp, monkeypatch, state, tmp_path):
    """Verifies: FR-115, FR-116, FR-118."""
    # FR-115/FR-116/FR-118: Apply on the delete dialog removes the file and refreshes.
    win = MainWindow(state)
    try:
        win.host_dir = str(tmp_path)
        (tmp_path / "F.TXT").write_text("x")
        monkeypatch.setattr(
            "cpm_fm.gui.mw_context_menu.FileActionDialog", _fake_action_dialog("F.TXT")
        )
        refreshed = []
        monkeypatch.setattr(win, "refresh_host_files", lambda: refreshed.append(1))
        win._host_delete("F.TXT")
        assert not (tmp_path / "F.TXT").exists()
        assert refreshed == [1]
    finally:
        win.close()


def test_remote_rename_sends_command(qapp, monkeypatch, state):
    """Verifies: FR-117."""
    # FR-117: remote Rename sends rename_remote_cmd with $1=old, $2=new.
    win = MainWindow(state)
    try:
        win.serial_mgr.terminal_connected = True
        win.settings = {"rename_remote_cmd": "REN $2=$1"}
        monkeypatch.setattr(
            "cpm_fm.gui.mw_context_menu.FileActionDialog", _fake_action_dialog("NEW.TXT")
        )
        _RecordingThread.instances = []
        monkeypatch.setattr("cpm_fm.app.threading.Thread", _RecordingThread)
        win._remote_rename("OLD.TXT")
        assert _RecordingThread.instances[0].args == ("REN NEW.TXT=OLD.TXT",)
    finally:
        win.close()


def test_remote_delete_sends_command(qapp, monkeypatch, state):
    """Verifies: FR-117."""
    # FR-117: remote Delete sends delete_remote_cmd with $1=name.
    win = MainWindow(state)
    try:
        win.serial_mgr.terminal_connected = True
        win.settings = {"delete_remote_cmd": "ERA $1"}
        monkeypatch.setattr(
            "cpm_fm.gui.mw_context_menu.FileActionDialog", _fake_action_dialog("F.TXT")
        )
        _RecordingThread.instances = []
        monkeypatch.setattr("cpm_fm.app.threading.Thread", _RecordingThread)
        win._remote_delete("F.TXT")
        assert _RecordingThread.instances[0].args == (["ERA F.TXT"],)
    finally:
        win.close()


def test_host_delete_removes_all_selected_files(qapp, monkeypatch, state, tmp_path):
    """Verifies: FR-110, FR-116."""
    # FR-110/FR-116: Delete from the context menu removes every selected file.
    win = MainWindow(state)
    try:
        win.host_dir = str(tmp_path)
        for fn in ("A.TXT", "B.TXT", "C.TXT"):
            (tmp_path / fn).write_text("x")
        monkeypatch.setattr(
            "cpm_fm.gui.mw_context_menu.FileActionDialog", _fake_action_dialog("A.TXT")
        )
        monkeypatch.setattr(win, "refresh_host_files", lambda: None)
        win._host_delete(["A.TXT", "B.TXT", "C.TXT"])
        assert not (tmp_path / "A.TXT").exists()
        assert not (tmp_path / "B.TXT").exists()
        assert not (tmp_path / "C.TXT").exists()
    finally:
        win.close()


def test_remote_delete_sends_command_per_selected_file(qapp, monkeypatch, state):
    """Verifies: FR-111, FR-117."""
    # FR-111/FR-117: remote Delete sends delete_remote_cmd once per selected file.
    win = MainWindow(state)
    try:
        win.serial_mgr.terminal_connected = True
        win.settings = {"delete_remote_cmd": "ERA $1"}
        monkeypatch.setattr(
            "cpm_fm.gui.mw_context_menu.FileActionDialog", _fake_action_dialog("A.TXT")
        )
        _RecordingThread.instances = []
        monkeypatch.setattr("cpm_fm.app.threading.Thread", _RecordingThread)
        win._remote_delete(["A.TXT", "B.TXT"])
        assert _RecordingThread.instances[0].args == (["ERA A.TXT", "ERA B.TXT"],)
    finally:
        win.close()


def test_context_menu_targets_uses_full_selection_when_clicked_item_selected(qapp, state):
    """Verifies: FR-110."""
    # FR-110: clicking a file that is part of the multi-selection -> Delete
    # targets the whole selection; the single-file name is the clicked item.
    win = MainWindow(state)
    try:
        win.host_list.clear()
        win.host_list.addItems(["A.TXT", "B.TXT", "C.TXT"])
        for row in range(win.host_list.count()):
            win.host_list.item(row).setSelected(True)
        win.host_list.itemAt = lambda pos: win.host_list.item(0)
        name, names = win._context_menu_targets(win.host_list, None)
        assert name == "A.TXT"
        assert names == ["A.TXT", "B.TXT", "C.TXT"]
    finally:
        win.close()


def test_context_menu_targets_uses_clicked_item_when_outside_selection(qapp, state):
    """Verifies: FR-110."""
    # FR-110: clicking a file NOT in the selection -> the action targets that one
    # file alone, not the (unrelated) selection.
    win = MainWindow(state)
    try:
        win.host_list.clear()
        win.host_list.addItems(["A.TXT", "B.TXT", "C.TXT"])
        win.host_list.item(1).setSelected(True)  # B selected
        win.host_list.itemAt = lambda pos: win.host_list.item(0)  # but A clicked
        name, names = win._context_menu_targets(win.host_list, None)
        assert name == "A.TXT"
        assert names == ["A.TXT"]
    finally:
        win.close()


def test_remote_rename_requires_open_terminal(qapp, monkeypatch, state):
    """Verifies: FR-117."""
    # FR-117: with the Terminal Port closed, no command is issued.
    win = MainWindow(state)
    try:
        win.serial_mgr.terminal_connected = False
        _RecordingThread.instances = []
        monkeypatch.setattr("cpm_fm.app.threading.Thread", _RecordingThread)
        win._remote_rename("OLD.TXT")
        assert _RecordingThread.instances == []
        assert win.statusBar().currentMessage() == "Terminal port not connected - cannot rename"
    finally:
        win.close()


def test_do_remote_file_cmd_refreshes_remote_list(qapp, monkeypatch, state):
    """Verifies: FR-118."""
    # FR-118: after sending the command the remote list is refreshed.
    win = MainWindow(state)
    try:
        captured = []
        monkeypatch.setattr(
            win,
            "_capture_terminal_response",
            lambda c, cancellable=False, cancel_event=None: captured.append(c) or "",
        )
        refreshed = []
        monkeypatch.setattr(win, "_do_refresh_remote_logic", lambda: refreshed.append(1))
        win._do_remote_file_cmd("ERA F.TXT")
        assert captured == ["ERA F.TXT"]
        assert refreshed == [1]
    finally:
        win.close()


def test_remote_view_requires_both_flags(qapp, monkeypatch, state):
    """Verifies: FR-113, FR-113b, CR-010."""
    # FR-113/CR-010: remote View needs both status flags; otherwise it errors and
    # starts no download.
    win = MainWindow(state)
    try:
        win.serial_mgr.terminal_connected = True
        win.serial_mgr.transport_connected = False
        errors = []
        monkeypatch.setattr("cpm_fm.app.QMessageBox.critical", lambda *a, **k: errors.append(a[1:]))
        _RecordingThread.instances = []
        monkeypatch.setattr("cpm_fm.app.threading.Thread", _RecordingThread)
        win._remote_view("F.TXT")
        assert _RecordingThread.instances == []
        assert errors == [("Error", "Transport port not connected")]
    finally:
        win.close()


def test_remote_view_downloads_then_opens(qapp, monkeypatch, state):
    """Verifies: FR-113, FR-113a, FR-112."""
    # FR-113/FR-112: a successful download opens the temp file in the viewer.
    win = MainWindow(state)
    try:
        _arm_transfer(win, monkeypatch)
        opened = []
        monkeypatch.setattr(win, "_open_in_viewer", lambda p: opened.append(p))
        win._download_and_view("F.TXT")
        qapp.processEvents()  # deliver the queued view_file_ready signal
        assert len(opened) == 1
        assert os.path.basename(opened[0]) == "F.TXT"
        assert win._transfer_dialog is None  # progress dialog closed
    finally:
        win.close()


def test_host_to_remote_transfers_under_cursor_file(qapp, monkeypatch, state):
    """Verifies: FR-119."""
    # FR-119: To Remote transfers the single host file under the cursor via the
    # Copy to Remote batch worker.
    win = MainWindow(state)
    try:
        win.serial_mgr.terminal_connected = True
        win.serial_mgr.transport_connected = True
        _RecordingThread.instances = []
        monkeypatch.setattr("cpm_fm.app.threading.Thread", _RecordingThread)
        win._host_to_remote("F.TXT")
        t = _RecordingThread.instances[0]
        assert t.target == win._transfer_to_remote_batch
        assert t.args == ([os.path.join(win.host_dir, "F.TXT")],)
    finally:
        win.close()


def test_host_to_remote_transfers_all_selected_files(qapp, monkeypatch, state):
    """Verifies: FR-119, FR-106, FR-107."""
    # FR-119/FR-106/FR-107: To Remote transfers every selected host file via the
    # Copy to Remote batch worker, in order.
    win = MainWindow(state)
    try:
        win.serial_mgr.terminal_connected = True
        win.serial_mgr.transport_connected = True
        _RecordingThread.instances = []
        monkeypatch.setattr("cpm_fm.app.threading.Thread", _RecordingThread)
        win._host_to_remote(["A.TXT", "B.TXT"])
        t = _RecordingThread.instances[0]
        assert t.target == win._transfer_to_remote_batch
        assert t.args == (
            [os.path.join(win.host_dir, "A.TXT"), os.path.join(win.host_dir, "B.TXT")],
        )
    finally:
        win.close()


def test_remote_to_host_transfers_under_cursor_file(qapp, monkeypatch, state):
    """Verifies: FR-119."""
    # FR-119: To Host transfers the single remote file under the cursor via the
    # Copy to Host batch worker.
    win = MainWindow(state)
    try:
        win.serial_mgr.terminal_connected = True
        win.serial_mgr.transport_connected = True
        _RecordingThread.instances = []
        monkeypatch.setattr("cpm_fm.app.threading.Thread", _RecordingThread)
        win._remote_to_host("F.TXT")
        t = _RecordingThread.instances[0]
        assert t.target == win._transfer_to_host_batch
        assert t.args == ([os.path.join(win.host_dir, "F.TXT")],)
    finally:
        win.close()


def test_remote_to_host_transfers_all_selected_files(qapp, monkeypatch, state):
    """Verifies: FR-119, FR-106, FR-107."""
    # FR-119/FR-106/FR-107: To Host transfers every selected remote file via the
    # Copy to Host batch worker, in order.
    win = MainWindow(state)
    try:
        win.serial_mgr.terminal_connected = True
        win.serial_mgr.transport_connected = True
        _RecordingThread.instances = []
        monkeypatch.setattr("cpm_fm.app.threading.Thread", _RecordingThread)
        win._remote_to_host(["A.TXT", "B.TXT"])
        t = _RecordingThread.instances[0]
        assert t.target == win._transfer_to_host_batch
        assert t.args == (
            [os.path.join(win.host_dir, "A.TXT"), os.path.join(win.host_dir, "B.TXT")],
        )
    finally:
        win.close()


def test_progress_dialog_cancel_button_requests_cancel(qapp):
    """Verifies: FR-120, UIR-051."""
    # FR-120/UIR-051: the Cancel button invokes the callback and then disables
    # itself, showing that cancellation is underway.
    from cpm_fm.gui.transfer_dialog import TransferProgressDialog

    clicked = []
    dlg = TransferProgressDialog(None, "remote", 1, cancel_callback=lambda: clicked.append(1))
    try:
        dlg.cancel_button.click()
        assert clicked == [1]
        assert not dlg.cancel_button.isEnabled()
        assert "ancel" in dlg.cancel_button.text()  # "Cancelling…"
    finally:
        dlg.deleteLater()


def test_request_transfer_cancel_sets_flag(qapp, state):
    """Verifies: FR-120."""
    # FR-120: the GUI cancel handler raises the worker-polled cancel flag.
    win = MainWindow(state)
    try:
        assert not win._transfer_cancel.is_set()
        win._request_transfer_cancel()
        assert win._transfer_cancel.is_set()
    finally:
        win.close()


def test_cancellable_sleep_returns_immediately_when_cancelled(qapp, state):
    """Verifies: FR-120."""
    # FR-120: a worker-thread settle/launch wait wakes at once when a cancel is
    # already pending, rather than blocking for the whole interval. A long
    # interval with real (un-neutralised) time.sleep would hang the test if the
    # cancel were not honoured, so this also pins the early-return.
    win = MainWindow(state)
    try:
        win._transfer_cancel.set()
        assert win._cancellable_sleep(30.0) is True
    finally:
        win.close()


def test_cancellable_sleep_completes_when_not_cancelled(qapp, monkeypatch, state):
    """Verifies: FR-120."""
    # FR-120: with no cancel pending the wait runs its full (step-counted)
    # interval and reports not-cancelled. time.sleep is neutralised so the step
    # loop completes instantly.
    win = MainWindow(state)
    try:
        monkeypatch.setattr("cpm_fm.gui.mw_transfers.time.sleep", lambda *a, **k: None)
        assert win._cancellable_sleep(2.0) is False
    finally:
        win.close()


def test_wait_for_terminal_idle_returns_early_on_cancel(qapp, state):
    """Verifies: FR-120, FR-109."""
    # FR-120: the between-files settle (FR-109) wakes promptly on cancel. A real
    # time.sleep is left in place so the test would hang on the first 1.0s wait
    # if the cancel were ignored.
    win = MainWindow(state)
    try:
        win._transfer_cancel.set()
        win._wait_for_terminal_idle()  # must return without blocking
    finally:
        win.close()


def test_capture_terminal_response_cancellable_bails_early(qapp, monkeypatch, state):
    """Verifies: FR-120, FR-145."""
    # FR-120/FR-145: the pre-upload remote listing returns promptly on cancel
    # (with whatever partial output arrived) instead of sleeping the full idle
    # budget. Real time.sleep is kept so an unhonoured cancel would hang here.
    win = MainWindow(state)
    try:
        monkeypatch.setattr(win, "handle_terminal_send", lambda *a, **k: None)
        win._transfer_cancel.set()
        assert win._capture_terminal_response("DIR", cancellable=True) == ""
        # The non-cancellable form must NOT consult the (possibly stale) flag;
        # neutralise time.sleep so it still completes instantly here.
        monkeypatch.setattr("cpm_fm.gui.mw_transfers.time.sleep", lambda *a, **k: None)
        assert win._capture_terminal_response("DIR") == ""
    finally:
        win.close()


def test_capture_terminal_response_probe_cancel_bails_early(qapp, monkeypatch, state):
    """Verifies: FR-050."""
    # FR-050: the connect probe passes _probe_cancel as the capture's cancel
    # event, so a Disconnect during the probe wakes the capture at once instead
    # of running out the full idle budget. Real time.sleep is kept so an
    # unhonoured cancel would hang here.
    win = MainWindow(state)
    try:
        monkeypatch.setattr(win, "handle_terminal_send", lambda *a, **k: None)
        win._probe_cancel.set()
        assert win._capture_terminal_response("", cancel_event=win._probe_cancel) == ""
    finally:
        win.close()


def _arm_transfer_with_xmodem(win, monkeypatch, xmodem_cls):
    # Like _arm_transfer but with a caller-supplied XModem stub (so the test can
    # trigger cancellation from inside send_file/receive_file).
    win.settings = {"xfer_launch_delay": 0}
    win.serial_mgr.terminal_connected = True
    win.serial_mgr.transport_connected = True
    win.serial_mgr.transport_port = _FakeSerial()
    # Isolate the transfer history to a temp file so recording during a stubbed
    # transfer never touches the host's real ~/.cpm_fm_history.json (FR-141).
    win.transfer_history = TransferHistory(
        os.path.join(tempfile.mkdtemp(prefix="cpm_fm_hist_"), "history.json")
    )
    monkeypatch.setattr(win.serial_mgr, "send_data", lambda *a, **k: None)
    monkeypatch.setattr("cpm_fm.gui.mw_transfer_batches.XModem", xmodem_cls)
    monkeypatch.setattr("cpm_fm.gui.mw_transfers.time.sleep", lambda *a, **k: None)


def test_cancelled_transfer_is_not_reported_as_error(qapp, monkeypatch, state):
    """Verifies: FR-120."""
    # FR-120: cancelling mid-transfer closes the dialog, sets a "cancelled"
    # status, and raises no error dialog; with nothing completed, no refresh.
    win = MainWindow(state)
    try:
        errors = []
        monkeypatch.setattr("cpm_fm.app.QMessageBox.critical", lambda *a, **k: errors.append(a[1:]))
        refreshed = []
        monkeypatch.setattr(win, "refresh_remote_files", lambda: refreshed.append(1))

        class _CancellingXModem:
            def __init__(
                self, ser, monitor=None, progress=None, cancel_check=None, handshake_timeout=None
            ):
                self.no_response = False

            def send_file(self, path, use_1k=False):
                win._transfer_cancel.set()  # user cancels during the transfer
                return False  # X-Modem aborted

        _arm_transfer_with_xmodem(win, monkeypatch, _CancellingXModem)
        win._transfer_to_remote_batch([os.path.join(win.host_dir, "A.TXT")])
        qapp.processEvents()
        assert errors == []  # cancellation is not an error
        assert win._transfer_dialog is None  # dialog torn down
        assert refreshed == []  # nothing completed -> no refresh
        assert "cancelled" in win.statusBar().currentMessage().lower()
    finally:
        win.close()


def test_upload_no_response_reports_misconfigured_command_error(qapp, monkeypatch, state):
    """Verifies: FR-159."""
    # FR-159: a handshake that got no response at all (a misconfigured Send to
    # Remote command) reports a distinct error, not the generic transfer-failed
    # message.
    win = MainWindow(state)
    try:
        errors = []
        monkeypatch.setattr("cpm_fm.app.QMessageBox.critical", lambda *a, **k: errors.append(a[1:]))

        class _NoResponseXModem:
            def __init__(
                self, ser, monitor=None, progress=None, cancel_check=None, handshake_timeout=None
            ):
                self.no_response = True

            def send_file(self, path, use_1k=False):
                return False

        _arm_transfer_with_xmodem(win, monkeypatch, _NoResponseXModem)
        win._transfer_to_remote_batch([os.path.join(win.host_dir, "A.TXT")])
        qapp.processEvents()
        assert errors == [
            (
                i18n.tr("dialog.xmodem_error.title"),
                i18n.tr("error.transfer_no_response_send", name="A.TXT"),
            )
        ]
        entries = win.transfer_history.get_entries()
        assert entries[0]["error"] == i18n.tr("error.transfer_no_response_send", name="A.TXT")
    finally:
        win.close()


def test_download_no_response_reports_misconfigured_command_error(qapp, monkeypatch, state):
    """Verifies: FR-159."""
    # FR-159: same diagnosis on the download side, naming the Receive from
    # Remote command instead.
    win = MainWindow(state)
    try:
        errors = []
        monkeypatch.setattr("cpm_fm.app.QMessageBox.critical", lambda *a, **k: errors.append(a[1:]))

        class _NoResponseXModem:
            def __init__(
                self, ser, monitor=None, progress=None, cancel_check=None, handshake_timeout=None
            ):
                self.no_response = True

            def receive_file(self, path, use_1k=False):
                return False

        _arm_transfer_with_xmodem(win, monkeypatch, _NoResponseXModem)
        win._transfer_to_host_batch([os.path.join(win.host_dir, "B.TXT")])
        qapp.processEvents()
        assert errors == [
            (
                i18n.tr("dialog.xmodem_error.title"),
                i18n.tr("error.transfer_no_response_recv", name="B.TXT"),
            )
        ]
    finally:
        win.close()


def test_cancel_after_partial_batch_refreshes_and_skips_rest(qapp, monkeypatch, state):
    """Verifies: FR-120."""
    # FR-120: when a multi-file batch is cancelled after some files completed,
    # the remaining files are skipped and the destination list refreshes once.
    win = MainWindow(state)
    try:
        monkeypatch.setattr("cpm_fm.app.QMessageBox.critical", lambda *a, **k: None)
        refreshed = []
        monkeypatch.setattr(win, "refresh_remote_files", lambda: refreshed.append(1))
        calls = []

        class _XModem:
            def __init__(
                self, ser, monitor=None, progress=None, cancel_check=None, handshake_timeout=None
            ):
                self.no_response = False

            def send_file(self, path, use_1k=False):
                calls.append(os.path.basename(path))
                if len(calls) == 1:
                    return True  # first file succeeds
                win._transfer_cancel.set()  # cancel during the second file
                return False

        _arm_transfer_with_xmodem(win, monkeypatch, _XModem)
        paths = [os.path.join(win.host_dir, n) for n in ("A.TXT", "B.TXT", "C.TXT")]
        win._transfer_to_remote_batch(paths)
        qapp.processEvents()
        assert calls == ["A.TXT", "B.TXT"]  # C.TXT never attempted
        assert refreshed == [1]  # one refresh because A.TXT completed
    finally:
        win.close()


def test_button_row_both_cancel_left_apply_right(qapp):
    """Verifies: UIR-075."""
    # UIR-075: with both buttons, Cancel is far left and the affirmative far right.
    from PySide6.QtWidgets import QPushButton

    from cpm_fm.gui.dialog_buttons import build_button_row

    apply_btn = QPushButton("Apply")
    cancel_btn = QPushButton("Cancel")
    row = build_button_row(accept_button=apply_btn, reject_button=cancel_btn)
    assert row.itemAt(0).widget() is cancel_btn  # far left
    assert row.itemAt(row.count() - 1).widget() is apply_btn  # far right
    # A flexible stretch separates them.
    assert row.itemAt(1).widget() is None
    assert row.itemAt(1).spacerItem() is not None


def test_button_row_single_button_is_centered(qapp):
    """Verifies: UIR-075."""
    # UIR-075: a lone button is centred between two stretches.
    from PySide6.QtWidgets import QPushButton

    from cpm_fm.gui.dialog_buttons import build_button_row

    only = QPushButton("Close")
    row = build_button_row(accept_button=only)
    assert row.count() == 3
    assert row.itemAt(0).spacerItem() is not None  # leading stretch
    assert row.itemAt(1).widget() is only  # centred button
    assert row.itemAt(2).spacerItem() is not None  # trailing stretch


def test_file_action_dialog_button_layout(qapp):
    """Verifies: UIR-057, UIR-075."""
    # UIR-057/UIR-075: the File Action Dialog places Cancel far left, Apply far
    # right, both connected to reject/accept.
    from PySide6.QtWidgets import QHBoxLayout, QPushButton

    from cpm_fm.gui.file_action_dialog import FileActionDialog

    dlg = FileActionDialog(None, "Rename File", "F.TXT", editable=True)
    try:
        rows = [
            dlg.layout().itemAt(i).layout()
            for i in range(dlg.layout().count())
            if isinstance(dlg.layout().itemAt(i).layout(), QHBoxLayout)
        ]
        assert rows, "expected a horizontal button row"
        row = rows[-1]
        left = row.itemAt(0).widget()
        right = row.itemAt(row.count() - 1).widget()
        assert isinstance(left, QPushButton) and left.text() == "Cancel"
        assert isinstance(right, QPushButton) and right.text() == "Apply"
    finally:
        dlg.deleteLater()


def test_file_action_dialog_multi_file_shows_readonly_list(qapp):
    """Verifies: FR-115."""
    # FR-115: a multi-file Delete shows every selected name in a read-only,
    # non-editable list instead of the single-line field.
    from PySide6.QtWidgets import QPlainTextEdit

    from cpm_fm.gui.file_action_dialog import FileActionDialog

    names = ["A.TXT", "B.TXT", "C.TXT"]
    dlg = FileActionDialog(None, "Delete File", names[0], editable=False, filenames=names)
    try:
        listings = [
            dlg.layout().itemAt(i).widget()
            for i in range(dlg.layout().count())
            if isinstance(dlg.layout().itemAt(i).widget(), QPlainTextEdit)
        ]
        assert listings, "expected a read-only list of filenames"
        listing = listings[0]
        assert listing.isReadOnly()
        assert listing.toPlainText().splitlines() == names
    finally:
        dlg.deleteLater()


def test_general_config_remote_group_first(qapp, monkeypatch):
    """Verifies: UIR-041, UIR-089, UIR-090, UIR-094, UIR-095, UIR-107."""
    # UIR-041: the General Config dialog gathers the remote command fields
    # (List Files, Receive/Send, the XMODEM-1K toggle + 1K commands, Rename,
    # Delete) into a "Remote" group placed first, with Rename/Delete labelled
    # without the "Remote" suffix. UIR-089/UIR-090: the 1K toggle and its two
    # command fields sit directly below Send to Remote. UIR-094/UIR-095: a
    # label-less Test button row sits directly below each of Receive/Send.
    from PySide6.QtWidgets import QFormLayout, QGroupBox

    from cpm_fm.gui.config_dialogs import ConfigDialog, GeneralConfigDialog

    # The base dialog calls exec() in __init__; neutralise it so the modal does
    # not block this headless test.
    monkeypatch.setattr(ConfigDialog, "exec", lambda self: 0)
    dlg = GeneralConfigDialog(None, {}, lambda s: None)
    try:
        layout = dlg.layout()
        # The first laid-out section is the Remote group box.
        first = layout.itemAt(0).widget()
        assert isinstance(first, QGroupBox)
        assert first.title() == "Remote"
        # Its rows hold the remote command fields, in order, with the XMODEM-1K
        # toggle and its 1K command fields directly below Send to Remote. A
        # Test button row has no label item at all (empty label), not an
        # empty-text QLabel.
        form = first.layout()
        labels = []
        for i in range(form.rowCount()):
            item = form.itemAt(i, QFormLayout.ItemRole.LabelRole)
            labels.append(item.widget().text() if item is not None else "")
        assert labels == [
            "List Files",
            "Receive from Remote",
            "",  # UIR-094: Test button for Receive from Remote
            "Send to Remote",
            "",  # UIR-095: Test button for Send to Remote
            "Use XMODEM-1K",
            "Receive from Remote (1K)",
            "Send to Remote (1K)",
            "Rename",
            "Delete",
            "Erase All",  # UIR-107: multi-line erase-all macro, last in the group
        ]
        # The non-remote settings remain reachable for saving (e.g. EOL).
        assert "eol" in dlg.entries and "host_directory" in dlg.entries
    finally:
        dlg.deleteLater()


class _RespondingSerial:
    in_waiting = 1
    is_open = False

    def reset_input_buffer(self):
        pass


class _SilentSerial:
    in_waiting = 0
    is_open = False

    def reset_input_buffer(self):
        pass


def _open_general_config_for_test(win, monkeypatch):
    from cpm_fm.gui.config_dialogs import ConfigDialog, GeneralConfigDialog

    monkeypatch.setattr(ConfigDialog, "exec", lambda self: 0)
    return GeneralConfigDialog(win, win.settings, lambda s: None)


def test_config_test_button_requires_connection(qapp, monkeypatch, state):
    """Verifies: FR-161."""
    # FR-161/FR-080/CR-010: the Test button requires an active connection,
    # exactly like a real transfer, and launches nothing when not connected.
    win = MainWindow(state)
    try:
        win.serial_mgr.terminal_connected = False
        sent = []
        monkeypatch.setattr(win, "handle_terminal_send", lambda text, **k: sent.append(text))
        criticals = []
        monkeypatch.setattr(
            "cpm_fm.gui.config_dialogs.QMessageBox.critical",
            lambda *a, **k: criticals.append(a[1:]),
        )
        dlg = _open_general_config_for_test(win, monkeypatch)
        try:
            dlg._test_send_remote_cmd()
            assert sent == []
            assert criticals == [
                (i18n.tr("dialog.error.title"), i18n.tr("error.transport_not_connected"))
            ]
        finally:
            dlg.deleteLater()
    finally:
        win.close()


def test_config_test_button_reports_success_when_remote_responds(qapp, monkeypatch, state):
    """Verifies: FR-161, FR-160."""
    # FR-161: pressing Test launches the currently-typed command (FR-087
    # style, $1 replaced by a fixed placeholder) and reports success once the
    # remote answers with any byte, without transferring a real file.
    win = MainWindow(state)
    try:
        win.settings["xfer_launch_delay"] = 0
        win.settings["xfer_handshake_timeout"] = 0.05
        win.serial_mgr.terminal_connected = True
        win.serial_mgr.transport_connected = True
        win.serial_mgr.transport_port = _RespondingSerial()
        sent = []
        monkeypatch.setattr(win, "handle_terminal_send", lambda text, **k: sent.append(text))
        infos = []
        monkeypatch.setattr(
            "cpm_fm.gui.config_dialogs.QMessageBox.information",
            lambda *a, **k: infos.append(a[1:]),
        )
        dlg = _open_general_config_for_test(win, monkeypatch)
        try:
            dlg.entries["send_remote_cmd"].setText("PCGET $1")
            dlg._test_send_remote_cmd()
            deadline = time.monotonic() + 2.0
            while not infos and time.monotonic() < deadline:
                qapp.processEvents()
                time.sleep(0.01)
            assert sent == ["PCGET CPMTEST.TXT"]
            assert infos == [
                (
                    i18n.tr("dialog.test_remote_cmd.title"),
                    i18n.tr("dialog.test_remote_cmd.success"),
                )
            ]
        finally:
            dlg.deleteLater()
    finally:
        win.close()


def test_config_test_button_reports_no_response(qapp, monkeypatch, state):
    """Verifies: FR-161, FR-159, FR-160."""
    # FR-159/FR-160: no byte ever arrives within the handshake timeout -> the
    # same no-response diagnosis is reported, naming the Receive from Remote
    # command this time.
    win = MainWindow(state)
    try:
        win.settings["xfer_launch_delay"] = 0
        win.settings["xfer_handshake_timeout"] = 0.05
        win.serial_mgr.terminal_connected = True
        win.serial_mgr.transport_connected = True
        win.serial_mgr.transport_port = _SilentSerial()
        monkeypatch.setattr(win, "handle_terminal_send", lambda text, **k: None)
        warnings = []
        monkeypatch.setattr(
            "cpm_fm.gui.config_dialogs.QMessageBox.warning",
            lambda *a, **k: warnings.append(a[1:]),
        )
        dlg = _open_general_config_for_test(win, monkeypatch)
        try:
            dlg.entries["recv_remote_cmd"].setText("PCPUT $1")
            dlg._test_recv_remote_cmd()
            deadline = time.monotonic() + 2.0
            while not warnings and time.monotonic() < deadline:
                qapp.processEvents()
                time.sleep(0.01)
            assert warnings == [
                (
                    i18n.tr("dialog.test_remote_cmd.title"),
                    i18n.tr("dialog.test_remote_cmd.no_response_recv"),
                )
            ]
        finally:
            dlg.deleteLater()
    finally:
        win.close()


def test_general_config_save_keeps_current_host_dir(qapp, state, monkeypatch):
    # Regression: with a host directory saved in the config and a *different*
    # directory currently selected (e.g. via Change Directory), saving the
    # General Config dialog without touching the host-directory field must not
    # revert the current selection, nor change the stored config value.

    """Verifies: FR-021a."""
    win = MainWindow(state)
    try:
        # refresh_host_files lists the directory off disk; the paths here are
        # synthetic, so neutralise it and just observe that host_dir tracks.
        monkeypatch.setattr(win, "refresh_host_files", lambda: None)
        # No config file is loaded in this fixture, so the dialog Save now takes
        # the "warn and apply to session" path (FR-021a). Neutralise the modal
        # warning so it does not block headless; the host-dir logic under test
        # runs regardless of whether a file was written.
        monkeypatch.setattr("cpm_fm.app.QMessageBox.warning", lambda *a, **k: None)

        win.settings = dict(win.settings)
        win.settings["host_directory"] = "/path/A"
        win.host_dir = "/path/B"  # diverged from config (Change Directory)

        # Capture the callback the dialog would receive without building it.
        captured = {}

        def fake_dialog(parent, settings, callback, window_state):
            captured["callback"] = callback

        monkeypatch.setattr("cpm_fm.gui.mw_config.GeneralConfigDialog", fake_dialog)
        win.menu_general_config()
        callback = captured["callback"]

        # Save with the host-directory field unchanged (it carries the stored
        # config value back) plus an unrelated edit.
        callback({"host_directory": "/path/A", "eol": "LF"})
        assert win.host_dir == "/path/B"  # current selection preserved
        assert win.settings["host_directory"] == "/path/A"  # config preserved
        assert win.settings["eol"] == "LF"  # unrelated edit applied

        # Editing the field to a new value does follow it.
        callback({"host_directory": "/path/C"})
        assert win.host_dir == "/path/C"
        assert win.settings["host_directory"] == "/path/C"
    finally:
        win.close()


def test_serial_config_save_persists_only_serial_to_active_file(qapp, state, monkeypatch, tmp_path):
    """Verifies: FR-020a."""
    # FR-020a: the Serial dialog Save writes only the serial settings to the
    # currently loaded config file, leaves the general settings in that file
    # untouched, and never presents a Save dialog.
    import json

    win = MainWindow(state)
    try:
        cfg = tmp_path / "active.json"
        cfg.write_text(
            json.dumps(
                {
                    "terminal_port": "COM1",
                    "speed": "9600",
                    "eol": "CR",
                    "list_files_cmd": "DIR",
                    "host_directory": "/keep/me",
                }
            ),
            encoding="utf-8",
        )
        win.window_state.last_config = str(cfg)

        captured = {}

        def fake_dialog(parent, settings, current_ports, callback, window_state):
            captured["callback"] = callback

        monkeypatch.setattr("cpm_fm.gui.mw_config.SerialConfigDialog", fake_dialog)

        # FR-020a: no file-select dialog may be shown.
        def _no_dialog(*a, **k):
            raise AssertionError("Save dialog must not be presented")

        monkeypatch.setattr("cpm_fm.gui.mw_config.QFileDialog.getSaveFileName", _no_dialog)

        win.menu_serial_config()
        captured["callback"]({"terminal_port": "COM7", "speed": "115200"})

        on_disk = json.loads(cfg.read_text(encoding="utf-8"))
        # Serial settings persisted...
        assert on_disk["terminal_port"] == "COM7"
        assert on_disk["speed"] == "115200"
        # ...and every other setting in the file left untouched.
        assert on_disk["eol"] == "CR"
        assert on_disk["list_files_cmd"] == "DIR"
        assert on_disk["host_directory"] == "/keep/me"
        # The running session also reflects the change.
        assert win.settings["terminal_port"] == "COM7"
    finally:
        win.close()


def test_general_config_save_persists_general_only(qapp, state, monkeypatch, tmp_path):
    """Verifies: FR-021a."""
    # FR-021a: the General dialog Save writes only the general settings to the
    # currently loaded config file, leaving the serial settings untouched.
    import json

    win = MainWindow(state)
    try:
        monkeypatch.setattr(win, "refresh_host_files", lambda: None)
        cfg = tmp_path / "active.json"
        cfg.write_text(
            json.dumps(
                {
                    "terminal_port": "COM1",
                    "speed": "9600",
                    "eol": "CR",
                    "list_files_cmd": "DIR",
                }
            ),
            encoding="utf-8",
        )
        win.window_state.last_config = str(cfg)

        captured = {}

        def fake_dialog(parent, settings, callback, window_state):
            captured["callback"] = callback

        monkeypatch.setattr("cpm_fm.gui.mw_config.GeneralConfigDialog", fake_dialog)

        def _no_dialog(*a, **k):
            raise AssertionError("Save dialog must not be presented")

        monkeypatch.setattr("cpm_fm.gui.mw_config.QFileDialog.getSaveFileName", _no_dialog)

        win.menu_general_config()
        captured["callback"]({"eol": "LF", "list_files_cmd": "LS"})

        on_disk = json.loads(cfg.read_text(encoding="utf-8"))
        # General settings persisted...
        assert on_disk["eol"] == "LF"
        assert on_disk["list_files_cmd"] == "LS"
        # ...and the serial settings in the file left untouched.
        assert on_disk["terminal_port"] == "COM1"
        assert on_disk["speed"] == "9600"
    finally:
        win.close()


def test_dialog_save_warns_and_writes_nothing_when_no_config_loaded(qapp, state, monkeypatch):
    """Verifies: FR-020a, FR-021a."""
    # FR-020a/FR-021a: with no config file loaded there is nothing to write to;
    # the dialog Save warns, applies the change to the session only, and writes
    # no file (no Save dialog is shown either).
    import cpm_fm.app as app_module

    win = MainWindow(state)
    try:
        win.window_state.last_config = ""  # nothing loaded
        warnings = []
        monkeypatch.setattr(
            "cpm_fm.app.QMessageBox.warning", lambda *a, **k: warnings.append(a[1:])
        )
        saved = []
        monkeypatch.setattr(
            app_module.ConfigHandler, "save_json", lambda self, p, d: saved.append(p) or True
        )

        captured = {}

        def fake_dialog(parent, settings, current_ports, callback, window_state):
            captured["callback"] = callback

        monkeypatch.setattr("cpm_fm.gui.mw_config.SerialConfigDialog", fake_dialog)
        win.menu_serial_config()
        captured["callback"]({"terminal_port": "COM9"})

        assert warnings, "a warning dialog should be shown"
        assert not saved, "no file should be written when no config is loaded"
        # The setting is still applied to the running session.
        assert win.settings["terminal_port"] == "COM9"
    finally:
        win.close()


def test_issue_remote_cmd_uses_1k_command_when_enabled(qapp, state, monkeypatch):
    """Verifies: UIR-089, UIR-090."""
    # UIR-089/UIR-090: with XMODEM-1K on, a non-blank _1k command replaces the
    # standard launch command; a blank _1k command falls back to the standard
    # one; with 1K off the standard command is always used.
    win = MainWindow(state)
    try:
        sent: list[str] = []
        monkeypatch.setattr(win, "handle_terminal_send", sent.append)

        # 1K off -> standard command regardless of any _1k value.
        win.settings = {
            "xmodem_1k": "OFF",
            "send_remote_cmd": "PCGET $1",
            "send_remote_cmd_1k": "PCGET1K $1",
        }
        win._issue_remote_cmd(
            "send_remote_cmd", "PCGET $1", "A.TXT", cmd_key_1k="send_remote_cmd_1k"
        )
        assert sent == ["PCGET A.TXT"]

        # 1K on with a non-blank _1k command -> the 1K command is used.
        sent.clear()
        win.settings["xmodem_1k"] = "ON"
        win._issue_remote_cmd(
            "send_remote_cmd", "PCGET $1", "A.TXT", cmd_key_1k="send_remote_cmd_1k"
        )
        assert sent == ["PCGET1K A.TXT"]

        # 1K on but the _1k command blank -> fall back to the standard command.
        sent.clear()
        win.settings["send_remote_cmd_1k"] = ""
        win._issue_remote_cmd(
            "send_remote_cmd", "PCGET $1", "A.TXT", cmd_key_1k="send_remote_cmd_1k"
        )
        assert sent == ["PCGET A.TXT"]
    finally:
        win.close()


def test_transfer_byte_echo_respects_setting(qapp, state):
    """Verifies: FR-086, UIR-058."""
    # FR-086/UIR-058: the <HH> transfer-byte echo is emitted only when
    # echo_transfer_data is affirmative (default off) and suppressed otherwise.
    win = MainWindow(state)
    try:
        emitted = []
        win.term_write.connect(emitted.append)

        # Default (unset) -> echo off.
        win.settings = {}
        win._on_transfer_bytes("remote", b"\xb5\x06")
        qapp.processEvents()
        assert emitted == []

        # Explicit OFF -> no echo.
        win.settings = {"echo_transfer_data": "OFF"}
        win._on_transfer_bytes("remote", b"\x01\x02\x03")
        qapp.processEvents()
        assert emitted == []

        # ON -> echoed as <HH> tokens.
        win.settings = {"echo_transfer_data": "ON"}
        win._on_transfer_bytes("remote", b"\xb5\x06")
        qapp.processEvents()
        assert emitted == [b"<B5><06>"]
    finally:
        win.close()


def test_handle_terminal_recv_tees_bytes_to_engine_and_buffers(qapp, state):
    """Received bytes feed the VT-100 engine and, decoded, the receive buffer
    and the term_write display signal.

    Verifies: FR-090, FR-091.
    """
    win = MainWindow(state)
    try:
        emitted = []
        win.term_write.connect(emitted.append)
        win.handle_terminal_recv(b"A>\r\n")
        qapp.processEvents()
        # Decoded text reaches the receive buffer; raw bytes go out on term_write.
        assert win._rx_buffer == "A>\r\n"
        assert emitted == [b"A>\r\n"]
        # The GUI-thread sink feeds those bytes to the engine, which renders it.
        assert win._term_engine.display[0].rstrip() == "A>"
    finally:
        win.close()


def test_handle_terminal_recv_capture_buffer_byte_identical(qapp, state):
    """While a capture is active the decoded text is byte-identical to the old
    ASCII/replace behaviour, so DIR/probe/boot parsing is unaffected.

    Verifies: FR-090, FR-091.
    """
    win = MainWindow(state)
    try:
        win._capture_active = True
        win._remote_capture_buffer = ""
        # A non-ASCII byte decodes to U+FFFD, exactly as the read loop's
        # ASCII/replace decode produced before the raw-bytes migration.
        win.handle_terminal_recv(b"DIR\r\n\xb5")
        assert win._remote_capture_buffer == "DIR\r\n�"
    finally:
        win.close()


def test_general_config_has_echo_transfer_field(qapp, monkeypatch):
    """Verifies: UIR-058."""
    # UIR-058: the General Config dialog exposes an "Echo Transfer Data"
    # OFF/ON dropdown persisted as echo_transfer_data, defaulting to OFF.
    from PySide6.QtWidgets import QComboBox

    from cpm_fm.gui.config_dialogs import ConfigDialog, GeneralConfigDialog

    monkeypatch.setattr(ConfigDialog, "exec", lambda self: 0)
    dlg = GeneralConfigDialog(None, {}, lambda s: None)
    try:
        combo = dlg.entries["echo_transfer_data"]
        assert isinstance(combo, QComboBox)
        items = [combo.itemText(i) for i in range(combo.count())]
        assert items == ["OFF", "ON"]
        assert combo.currentText() == "OFF"  # default
    finally:
        dlg.deleteLater()


def test_general_config_xmodem_1k_checkbox_round_trips(qapp, monkeypatch):
    """Verifies: UIR-089, UIR-090."""
    # UIR-089/UIR-090: the dialog exposes a "Use XMODEM-1K" checkbox persisted as
    # xmodem_1k ("OFF"/"ON") plus two blank-by-default 1K command fields. The
    # checkbox reflects the current setting and saves back as "ON"/"OFF".
    from PySide6.QtWidgets import QCheckBox

    from cpm_fm.gui.config_dialogs import ConfigDialog, GeneralConfigDialog

    monkeypatch.setattr(ConfigDialog, "exec", lambda self: 0)

    # Default (no setting): unchecked, blank 1K command fields.
    saved: dict = {}
    dlg = GeneralConfigDialog(None, {}, saved.update)
    try:
        chk = dlg.entries["xmodem_1k"]
        assert isinstance(chk, QCheckBox)
        assert chk.isChecked() is False
        assert dlg.entries["recv_remote_cmd_1k"].text() == ""
        assert dlg.entries["send_remote_cmd_1k"].text() == ""
        chk.setChecked(True)
        dlg.save()
        assert saved["xmodem_1k"] == "ON"
    finally:
        dlg.deleteLater()

    # An existing "ON" setting renders the checkbox checked.
    dlg2 = GeneralConfigDialog(None, {"xmodem_1k": "ON"}, lambda s: None)
    try:
        assert dlg2.entries["xmodem_1k"].isChecked() is True
    finally:
        dlg2.deleteLater()


def test_general_config_boot_sequence_multiline_round_trips(qapp, monkeypatch):
    """Verifies: UIR-059."""
    # UIR-059: the dialog exposes a multi-line "Boot Sequence" editor persisted
    # as boot_sequence (default empty), preserving newlines on save.
    from PySide6.QtWidgets import QPlainTextEdit

    from cpm_fm.gui.config_dialogs import ConfigDialog, GeneralConfigDialog

    monkeypatch.setattr(ConfigDialog, "exec", lambda self: 0)

    saved: dict = {}
    dlg = GeneralConfigDialog(None, {}, saved.update)
    try:
        editor = dlg.entries["boot_sequence"]
        assert isinstance(editor, QPlainTextEdit)
        assert editor.toPlainText() == ""  # default empty
        editor.setPlainText("WAITFOR Boot:\nSEND DDT")
        dlg.save()
        assert saved["boot_sequence"] == "WAITFOR Boot:\nSEND DDT"
    finally:
        dlg.deleteLater()

    # An existing value is rendered verbatim, newlines included.
    dlg2 = GeneralConfigDialog(None, {"boot_sequence": "SEND A\nWAIT 1"}, lambda s: None)
    try:
        assert dlg2.entries["boot_sequence"].toPlainText() == "SEND A\nWAIT 1"
    finally:
        dlg2.deleteLater()


def test_config_menu_has_language_submenu(qapp, state):
    """Verifies: UIR-003, UIR-077."""
    # UIR-003/UIR-077: the Config menu contains a Language submenu listing every
    # shipped language by its (capitalised) name, with the active one checked.
    from PySide6.QtWidgets import QMenu

    win = MainWindow(state)
    try:
        # A "Language" submenu exists somewhere under the menu bar.
        titles = [m.title() for m in win.menuBar().findChildren(QMenu)]
        assert "Language" in titles
        # The per-language actions are keyed by language name and labelled by the
        # capitalised display name.
        labels = {name: act.text() for name, act in win._language_actions.items()}
        assert labels.get("english") == "English"
        assert labels.get("german") == "German"
        assert labels.get("french") == "French"
        # The active language's entry is checked (UIR-077).
        checked = [name for name, act in win._language_actions.items() if act.isChecked()]
        assert checked == ["english"]
    finally:
        win.close()
        win.deleteLater()


def test_language_switch_retranslates_live(qapp, state):
    """Verifies: FR-122, FR-123."""
    # FR-122/FR-123: switching language re-labels the visible UI immediately and
    # persists the choice; switching back restores the English text.
    from PySide6.QtWidgets import QPushButton

    win = MainWindow(state)
    try:
        win.menu_set_language("german")
        qapp.processEvents()
        # A registered widget (the Copy to Remote button) now shows German text.
        buttons = [b.text() for b in win.findChildren(QPushButton)]
        assert "Zum Gerät kopieren" in buttons
        assert win.window_state.language == "german"

        win.menu_set_language("english")
        qapp.processEvents()
        buttons = [b.text() for b in win.findChildren(QPushButton)]
        assert "Copy to Remote" in buttons
        assert win.window_state.language == "english"
    finally:
        win.close()
        win.deleteLater()


def test_persisted_language_applied_on_construction(qapp, state):
    """Verifies: FR-124."""
    # FR-124: a window built from a store that remembers German starts localised.
    state.language = "german"
    win = MainWindow(state)
    try:
        # The window title is rebuilt from app.title (no config loaded -> name only).
        assert win.windowTitle() == "CP/M-Dateimanager"
    finally:
        win.close()
        win.deleteLater()


def test_host_to_remote_requires_both_flags(qapp, monkeypatch, state):
    """Verifies: FR-119, CR-010."""
    # FR-119/CR-010: To Remote needs both status flags; otherwise it errors and
    # starts no transfer.
    win = MainWindow(state)
    try:
        win.serial_mgr.terminal_connected = True
        win.serial_mgr.transport_connected = False
        errors = []
        monkeypatch.setattr("cpm_fm.app.QMessageBox.critical", lambda *a, **k: errors.append(a[1:]))
        _RecordingThread.instances = []
        monkeypatch.setattr("cpm_fm.app.threading.Thread", _RecordingThread)
        win._host_to_remote("F.TXT")
        assert _RecordingThread.instances == []
        assert errors == [("Error", "Transport port not connected")]
    finally:
        win.close()


def _write_config(tmp_path, name="my_settings.json"):
    import json

    path = tmp_path / name
    path.write_text(json.dumps({"speed": 9600}), encoding="utf-8")
    return str(path)


def test_window_title_plain_without_config(qapp, state):
    """Verifies: FR-125, UIR-005."""
    # FR-125/UIR-005: with no config loaded the title is the application name alone.
    win = MainWindow(state)
    try:
        assert win.windowTitle() == "CP/M File Manager"
    finally:
        win.close()
        win.deleteLater()


def test_window_title_includes_loaded_config_basename(qapp, state, tmp_path):
    """Verifies: FR-125."""
    # FR-125: loading a config appends its base name (no path, no extension).
    win = MainWindow(state)
    try:
        win.load_config(_write_config(tmp_path, "my_settings.json"))
        assert win.windowTitle() == "CP/M File Manager — my_settings"
    finally:
        win.close()
        win.deleteLater()


def test_window_title_cleared_by_new(qapp, state, tmp_path, monkeypatch):
    """Verifies: FR-125, FR-019."""
    # FR-125/FR-019: File > New drops the config name from the title bar.
    win = MainWindow(state)
    try:
        win.load_config(_write_config(tmp_path))
        assert "—" in win.windowTitle()
        # New first saves silently to the last-used file (the temp config loaded
        # above), then resets. Stub the port teardown so the test stays headless.
        monkeypatch.setattr(win, "do_disconnect", lambda: None)
        win.menu_new()
        assert win.windowTitle() == "CP/M File Manager"
    finally:
        win.close()
        win.deleteLater()


def test_host_group_title_includes_directory(qapp, state):
    """Verifies: FR-126, UIR-011."""
    # FR-126/UIR-011: the Host Files group title carries the current directory,
    # left-elided so the trailing (most specific) part of the path is visible.
    win = MainWindow(state)
    try:
        win.resize(900, 560)
        win.host_dir = os.path.join("C:", os.sep, "tmp", "cpmwork")
        win.refresh_host_files()
        title = win.host_group.title()
        assert title.startswith("Host Files —")
        assert "cpmwork" in title
    finally:
        win.close()
        win.deleteLater()


# ------------------------------------------------- file-list filter / sort (F3)


def _host_names(win):
    return [win.host_list.item(i).text() for i in range(win.host_list.count())]


def _remote_names(win):
    return [win.remote_list.item(i).text() for i in range(win.remote_list.count())]


def test_filter_sort_controls_present_on_both_panes(qapp, state):
    """Verifies: UIR-079, UIR-080."""
    # UIR-079/UIR-080: each pane has a filter field, a sort drop-down (Name /
    # Extension), and a direction toggle button.
    from PySide6.QtWidgets import QComboBox, QLineEdit, QToolButton

    win = MainWindow(state)
    try:
        assert isinstance(win.host_filter, QLineEdit)
        assert isinstance(win.remote_filter, QLineEdit)
        for combo in (win.host_sort_combo, win.remote_sort_combo):
            assert isinstance(combo, QComboBox)
            assert [combo.itemText(i) for i in range(combo.count())] == ["Name", "Extension"]
            assert [combo.itemData(i) for i in range(combo.count())] == ["name", "extension"]
        assert isinstance(win.host_sort_dir_btn, QToolButton)
        assert win.host_sort_dir_btn.isCheckable()
    finally:
        win.close()
        win.deleteLater()


def test_host_filter_hides_nonmatching_files(qapp, state):
    """Verifies: FR-130, FR-131."""
    # FR-130/FR-131: a filter restricts the host list to matching names.
    win = MainWindow(state)
    try:
        win._host_files = ["A.TXT", "B.COM", "C.TXT", "D.COM"]
        win.host_filter.setText("*.TXT")
        win._apply_host_view()
        assert _host_names(win) == ["A.TXT", "C.TXT"]
        # Clearing the filter restores the full list.
        win.host_filter.setText("")
        win._apply_host_view()
        assert _host_names(win) == ["A.TXT", "B.COM", "C.TXT", "D.COM"]
    finally:
        win.close()
        win.deleteLater()


def test_host_sort_by_extension_and_direction(qapp, state):
    """Verifies: FR-132."""
    # FR-132: the sort drop-down and direction button reorder the host list.
    from cpm_fm.utils.file_filter import SORT_EXTENSION

    win = MainWindow(state)
    try:
        win._host_files = ["B.TXT", "A.COM", "C.TXT", "D.COM"]
        win.host_sort_combo.setCurrentIndex(win.host_sort_combo.findData(SORT_EXTENSION))
        win._apply_host_view()
        assert _host_names(win) == ["A.COM", "D.COM", "B.TXT", "C.TXT"]
        # Toggling descending reverses within the extension grouping.
        win.host_sort_dir_btn.setChecked(True)
        win._apply_host_view()
        assert _host_names(win) == ["C.TXT", "B.TXT", "D.COM", "A.COM"]
        assert win.host_sort_dir_btn.text() == "↓"
    finally:
        win.close()
        win.deleteLater()


def test_active_filter_sets_visual_indicator(qapp, state):
    """Verifies: UIR-079."""
    # UIR-079: an active (non-empty) filter flags the field with a styled border.
    win = MainWindow(state)
    try:
        win._host_files = ["A.TXT"]
        win.host_filter.setText("A")
        win._apply_host_view()
        assert "border" in win.host_filter.styleSheet()
        win.host_filter.setText("")
        win._apply_host_view()
        assert win.host_filter.styleSheet() == ""
    finally:
        win.close()
        win.deleteLater()


def test_remote_list_applies_filter_and_sort(qapp, state):
    """Verifies: FR-133."""
    # FR-133: the remote listing is rendered through the pane's filter/sort.
    win = MainWindow(state)
    try:
        win.remote_filter.setText("*.COM")
        win._update_remote_list_ui({"B.TXT": True, "A.COM": True, "C.COM": True})
        assert _remote_names(win) == ["A.COM", "C.COM"]
    finally:
        win.close()
        win.deleteLater()


def test_default_remote_list_is_name_ascending(qapp, state):
    """Verifies: FR-078, FR-133."""
    # FR-078/FR-133: with default controls the remote list is name-ascending,
    # preserving the long-standing default display.
    win = MainWindow(state)
    try:
        win._update_remote_list_ui({"C.TXT": True, "A.TXT": True, "B.TXT": True})
        assert _remote_names(win) == ["A.TXT", "B.TXT", "C.TXT"]
    finally:
        win.close()
        win.deleteLater()


def test_clear_remote_files_empties_canonical_and_widget(qapp, state):
    """Verifies: FR-058, FR-103."""
    # FR-058/FR-103: clearing the remote list drops both the widget rows and the
    # canonical source, so a later filter change cannot resurrect stale entries.
    win = MainWindow(state)
    try:
        win._update_remote_list_ui({"A.TXT": True})
        assert win._remote_files
        win._clear_remote_files()
        assert win._remote_files == []
        assert win.remote_list.count() == 0
        # A filter change now renders nothing rather than the old entries.
        win.remote_filter.setText("A")
        win._apply_remote_view()
        assert win.remote_list.count() == 0
    finally:
        win.close()
        win.deleteLater()


def test_filter_sort_settings_persist_across_sessions(qapp, state):
    """Verifies: FR-134."""
    # FR-134: a pane's filter text and sort settings are saved and restored in a
    # later session sharing the same store.
    from cpm_fm.utils.file_filter import SORT_EXTENSION

    first = MainWindow(state)
    try:
        first.host_filter.setText("*.TXT")
        first.host_sort_combo.setCurrentIndex(first.host_sort_combo.findData(SORT_EXTENSION))
        first.host_sort_dir_btn.setChecked(True)
        first._apply_host_view()  # persists via _persist_filter_sort
    finally:
        first.close()
        first.deleteLater()

    second = MainWindow(state)
    try:
        assert second.host_filter.text() == "*.TXT"
        assert second.host_sort_combo.currentData() == SORT_EXTENSION
        assert second.host_sort_dir_btn.isChecked() is True
        assert second.host_sort_dir_btn.text() == "↓"
    finally:
        second.close()
        second.deleteLater()


def test_sort_combo_labels_retranslate_live(qapp, state):
    """Verifies: FR-123."""
    # FR-123: switching language re-labels the sort drop-down items while keeping
    # their userData (sort keys) intact.
    win = MainWindow(state)
    try:
        win.menu_set_language("german")
        qapp.processEvents()
        labels = [win.host_sort_combo.itemText(i) for i in range(win.host_sort_combo.count())]
        assert labels == ["Name", "Erweiterung"]
        assert [win.host_sort_combo.itemData(i) for i in range(2)] == ["name", "extension"]
    finally:
        win.close()
        win.deleteLater()


# ----------------------------------------------- drag-and-drop transfer (F1)


def _cpm_mime(pane, names):
    # Build the internal drag payload a FileListWidget produces (FR-136).
    from PySide6.QtCore import QMimeData

    from cpm_fm.gui.file_list_widget import MIME_CPM_FILES

    mime = QMimeData()
    mime.setData(MIME_CPM_FILES, "\n".join([pane, *names]).encode("utf-8"))
    return mime


def _url_mime(paths):
    # Build an external OS file-manager drag payload (file URLs) (FR-138).
    from PySide6.QtCore import QMimeData, QUrl

    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(p) for p in paths])
    return mime


def test_file_lists_are_drag_drop_capable(qapp, state):
    """Verifies: FR-136, FR-137, UIR-081."""
    # FR-136/FR-137/UIR-081: both panes are drag-enabled, accept drops, and are
    # FileListWidget instances tagged with their pane.
    from cpm_fm.gui.file_list_widget import FileListWidget

    win = MainWindow(state)
    try:
        for lst, pane in ((win.host_list, "host"), (win.remote_list, "remote")):
            assert isinstance(lst, FileListWidget)
            assert lst._pane == pane
            assert lst.dragEnabled()
            assert lst.acceptDrops()
    finally:
        win.close()
        win.deleteLater()


def test_decode_drop_internal_cross_pane(qapp, state):
    """Verifies: FR-137."""
    # FR-137: a pane accepts an internal drag from the OTHER pane and reports the
    # source pane, names, and external=False.
    win = MainWindow(state)
    try:
        assert win.remote_list.decode_drop(_cpm_mime("host", ["A.TXT", "B.TXT"])) == (
            "host",
            ["A.TXT", "B.TXT"],
            False,
        )
        assert win.host_list.decode_drop(_cpm_mime("remote", ["X.COM"])) == (
            "remote",
            ["X.COM"],
            False,
        )
    finally:
        win.close()
        win.deleteLater()


def test_decode_drop_same_pane_rejected(qapp, state):
    """Verifies: FR-137."""
    # FR-137: dropping a pane's own files back onto itself is a no-op (rejected).
    win = MainWindow(state)
    try:
        assert win.host_list.decode_drop(_cpm_mime("host", ["A.TXT"])) is None
        assert win.remote_list.decode_drop(_cpm_mime("remote", ["A.TXT"])) is None
    finally:
        win.close()
        win.deleteLater()


def test_decode_drop_external_files_remote_only(qapp, state, tmp_path):
    """Verifies: FR-138."""
    # FR-138: external OS file drops are accepted on the Remote pane (as absolute
    # paths, external=True) but rejected on the Host pane.
    f = tmp_path / "EXT.TXT"
    f.write_text("x")
    win = MainWindow(state)
    try:
        source, paths, external = win.remote_list.decode_drop(_url_mime([str(f)]))
        # QUrl.toLocalFile normalises to forward slashes on Windows; compare by
        # normalised path so the test is separator-agnostic.
        assert source is None and external is True
        assert [os.path.normpath(p) for p in paths] == [os.path.normpath(str(f))]
        assert win.host_list.decode_drop(_url_mime([str(f)])) is None
    finally:
        win.close()
        win.deleteLater()


def test_drop_host_to_remote_starts_copy_to_remote(qapp, monkeypatch, state):
    """Verifies: FR-137, FR-137e."""
    # FR-137: dropping host files onto the Remote pane (confirmed) starts the
    # Copy to Remote batch worker with host-dir-joined paths.
    win = MainWindow(state)
    try:
        win.serial_mgr.terminal_connected = True
        win.serial_mgr.transport_connected = True
        monkeypatch.setattr(win, "_confirm_dnd_transfer", lambda *a, **k: True)
        _RecordingThread.instances = []
        monkeypatch.setattr("cpm_fm.app.threading.Thread", _RecordingThread)
        win._on_files_dropped("remote", "host", ["A.TXT", "B.TXT"], False)
        t = _RecordingThread.instances[0]
        assert t.target == win._transfer_to_remote_batch
        assert t.args == (
            [os.path.join(win.host_dir, "A.TXT"), os.path.join(win.host_dir, "B.TXT")],
        )
    finally:
        win.close()
        win.deleteLater()


def test_drop_remote_to_host_starts_copy_to_host(qapp, monkeypatch, state):
    """Verifies: FR-137, FR-137e."""
    # FR-137: dropping remote files onto the Host pane (confirmed) starts the
    # Copy to Host batch worker.
    win = MainWindow(state)
    try:
        win.serial_mgr.terminal_connected = True
        win.serial_mgr.transport_connected = True
        monkeypatch.setattr(win, "_confirm_dnd_transfer", lambda *a, **k: True)
        _RecordingThread.instances = []
        monkeypatch.setattr("cpm_fm.app.threading.Thread", _RecordingThread)
        win._on_files_dropped("host", "remote", ["F.TXT"], False)
        t = _RecordingThread.instances[0]
        assert t.target == win._transfer_to_host_batch
        assert t.args == ([os.path.join(win.host_dir, "F.TXT")],)
    finally:
        win.close()
        win.deleteLater()


def test_drop_external_files_use_absolute_paths(qapp, monkeypatch, state):
    """Verifies: FR-138."""
    # FR-138: an external OS drop onto the Remote pane transfers the dropped
    # absolute paths verbatim (not re-joined under the host directory).
    win = MainWindow(state)
    try:
        win.serial_mgr.terminal_connected = True
        win.serial_mgr.transport_connected = True
        monkeypatch.setattr(win, "_confirm_dnd_transfer", lambda *a, **k: True)
        _RecordingThread.instances = []
        monkeypatch.setattr("cpm_fm.app.threading.Thread", _RecordingThread)
        abs_paths = [os.path.join("C:", os.sep, "ext", "A.TXT")]
        win._on_files_dropped("remote", None, abs_paths, True)
        t = _RecordingThread.instances[0]
        assert t.target == win._transfer_to_remote_batch
        assert t.args == (abs_paths,)
    finally:
        win.close()
        win.deleteLater()


def test_drop_requires_both_flags(qapp, monkeypatch, state):
    """Verifies: FR-137, FR-137c, CR-010."""
    # FR-137/CR-010: a drop with the transport disconnected errors and starts no
    # transfer (and never even prompts for confirmation).
    win = MainWindow(state)
    try:
        win.serial_mgr.terminal_connected = True
        win.serial_mgr.transport_connected = False
        errors = []
        monkeypatch.setattr("cpm_fm.app.QMessageBox.critical", lambda *a, **k: errors.append(a[1:]))
        _RecordingThread.instances = []
        monkeypatch.setattr("cpm_fm.app.threading.Thread", _RecordingThread)
        win._on_files_dropped("remote", "host", ["A.TXT"], False)
        assert _RecordingThread.instances == []
        assert errors == [("Error", "Transport port not connected")]
    finally:
        win.close()
        win.deleteLater()


def test_drop_cancelled_confirmation_starts_no_transfer(qapp, monkeypatch, state):
    """Verifies: FR-137."""
    # FR-137: declining the confirmation dialog starts no transfer.
    win = MainWindow(state)
    try:
        win.serial_mgr.terminal_connected = True
        win.serial_mgr.transport_connected = True
        monkeypatch.setattr(win, "_confirm_dnd_transfer", lambda *a, **k: False)
        _RecordingThread.instances = []
        monkeypatch.setattr("cpm_fm.app.threading.Thread", _RecordingThread)
        win._on_files_dropped("remote", "host", ["A.TXT"], False)
        assert _RecordingThread.instances == []
    finally:
        win.close()
        win.deleteLater()


def test_dnd_confirm_dialog_button_order_and_labels(qapp, monkeypatch, state):
    """Verifies: UIR-075."""
    # UIR-075: the drag-and-drop transfer confirmation puts Cancel at the far
    # left and OK at the far right (was a Yes/No QMessageBox ordered by the
    # native platform style).
    from PySide6.QtWidgets import QDialog, QPushButton

    class _StubDialog(QDialog):
        last = None

        def exec(self):
            type(self).last = self
            return QDialog.DialogCode.Rejected.value

    win = MainWindow(state)
    try:
        monkeypatch.setattr("cpm_fm.app.QDialog", _StubDialog)
        assert win._confirm_dnd_transfer("remote", 2) is False  # Rejected
        dlg = _StubDialog.last
        assert dlg is not None
        row = dlg.layout().itemAt(dlg.layout().count() - 1).layout()
        buttons = [
            row.itemAt(i).widget()
            for i in range(row.count())
            if isinstance(row.itemAt(i).widget(), QPushButton)
        ]
        assert buttons[0].text() == i18n.tr("button.cancel")
        assert buttons[-1].text() == i18n.tr("button.ok")
    finally:
        win.close()


def test_app_icon_resource_present_and_loadable(qapp):
    """Verifies: UIR-078, DR-044."""
    # UIR-078/DR-044: the runtime icon ships as package data and app_icon()
    # returns a real (non-null) QIcon loaded from it.
    from cpm_fm.gui.theme import APP_ICON_PATH, app_icon

    assert APP_ICON_PATH.is_file(), f"missing runtime icon at {APP_ICON_PATH}"
    icon = app_icon()
    assert not icon.isNull()
    assert icon.availableSizes(), "icon has no rendered sizes"


def test_app_icon_missing_falls_back_to_empty(qapp, monkeypatch):
    """Verifies: UIR-078, CR-006."""
    # UIR-078: a missing icon resource yields an empty QIcon rather than raising,
    # so start-up survives its absence (consistent with the optional CR-006 icons).
    from pathlib import Path

    from cpm_fm.gui import theme

    monkeypatch.setattr(theme, "APP_ICON_PATH", Path("does-not-exist.png"))
    icon = theme.app_icon()
    assert icon.isNull()


# --------------------------------------------------------- transfer history (Feature 2)


def test_successful_transfer_records_history(qapp, monkeypatch, state):
    """Verifies: FR-142."""
    # FR-142: a successful upload records one "success" history entry with the
    # file's name, path, direction, and size.
    win = MainWindow(state)
    try:
        monkeypatch.setattr(win, "refresh_remote_files", lambda: None)
        _arm_transfer(win, monkeypatch)
        path = os.path.join(win.host_dir, "FOO.TXT")
        monkeypatch.setattr("cpm_fm.app.os.path.getsize", lambda p: 321)
        win._transfer_to_remote_batch([path])
        qapp.processEvents()
        entries = win.transfer_history.get_entries()
        assert len(entries) == 1
        e = entries[0]
        assert e["filename"] == "FOO.TXT"
        assert e["path"] == path
        assert e["direction"] == "remote"
        assert e["status"] == "success"
        assert e["size"] == 321
        assert e["retry"] is False
    finally:
        win.close()


def test_failed_transfer_records_failure_history(qapp, monkeypatch, state):
    """Verifies: FR-142."""
    # FR-142: a failed transfer records a "failure" entry with an error message.
    win = MainWindow(state)
    try:
        monkeypatch.setattr("cpm_fm.app.QMessageBox.critical", lambda *a, **k: None)
        _arm_transfer(win, monkeypatch, success=False)
        win._transfer_to_host_batch([os.path.join(win.host_dir, "BAR.TXT")])
        qapp.processEvents()
        entries = win.transfer_history.get_entries()
        assert len(entries) == 1
        assert entries[0]["status"] == "failure"
        assert entries[0]["direction"] == "host"
        assert entries[0]["error"]  # non-empty error message
    finally:
        win.close()


def test_cancelled_transfer_records_cancelled_history(qapp, monkeypatch, state):
    """Verifies: FR-142."""
    # FR-142: a user-cancelled file is recorded with "cancelled" status.
    win = MainWindow(state)
    try:
        monkeypatch.setattr(win, "refresh_remote_files", lambda: None)

        class _CancellingXModem:
            def __init__(
                self, ser, monitor=None, progress=None, cancel_check=None, handshake_timeout=None
            ):
                self.no_response = False

            def send_file(self, path, use_1k=False):
                win._transfer_cancel.set()
                return False

        _arm_transfer_with_xmodem(win, monkeypatch, _CancellingXModem)
        win.transfer_history = TransferHistory(
            os.path.join(tempfile.mkdtemp(prefix="cpm_fm_hist_"), "history.json")
        )
        win._transfer_to_remote_batch([os.path.join(win.host_dir, "A.TXT")])
        qapp.processEvents()
        entries = win.transfer_history.get_entries()
        assert len(entries) == 1
        assert entries[0]["status"] == "cancelled"
    finally:
        win.close()


def test_retransfer_reuses_batch_with_retry_flag(qapp, monkeypatch, state):
    """Verifies: FR-144."""
    # FR-144: re-transfer of a "remote" entry re-runs the remote batch worker
    # with retry=True for the recorded host path (which must exist).
    win = MainWindow(state)
    try:
        win.serial_mgr.terminal_connected = True
        win.serial_mgr.transport_connected = True
        path = os.path.join(win.host_dir, "EXISTS.TXT")
        monkeypatch.setattr("cpm_fm.app.os.path.isfile", lambda p: p == path)
        _RecordingThread.instances = []
        monkeypatch.setattr("cpm_fm.app.threading.Thread", _RecordingThread)
        win._retransfer({"path": path, "direction": "remote", "filename": "EXISTS.TXT"})
        assert len(_RecordingThread.instances) == 1
        t = _RecordingThread.instances[0]
        assert t.target == win._transfer_to_remote_batch
        assert t.args == ([path],)
    finally:
        win.close()


def test_retransfer_missing_file_reports_and_starts_nothing(qapp, monkeypatch, state):
    """Verifies: FR-144."""
    # FR-144: re-transfer of an upload whose source file is gone reports an error
    # and starts no transfer.
    win = MainWindow(state)
    try:
        win.serial_mgr.terminal_connected = True
        win.serial_mgr.transport_connected = True
        errors = []
        monkeypatch.setattr("cpm_fm.app.QMessageBox.critical", lambda *a, **k: errors.append(a[1:]))
        monkeypatch.setattr("cpm_fm.app.os.path.isfile", lambda p: False)
        _RecordingThread.instances = []
        monkeypatch.setattr("cpm_fm.app.threading.Thread", _RecordingThread)
        win._retransfer({"path": "/gone/X.TXT", "direction": "remote", "filename": "X.TXT"})
        assert errors  # an error was reported
        assert _RecordingThread.instances == []  # no transfer started
    finally:
        win.close()


def test_retransfer_blocked_when_not_connected(qapp, monkeypatch, state):
    """Verifies: FR-144, FR-080."""
    # FR-144/FR-080: re-transfer requires both connection flags.
    win = MainWindow(state)
    try:
        errors = []
        monkeypatch.setattr("cpm_fm.app.QMessageBox.critical", lambda *a, **k: errors.append(a[1:]))
        _RecordingThread.instances = []
        monkeypatch.setattr("cpm_fm.app.threading.Thread", _RecordingThread)
        win._retransfer({"path": "/h/X.TXT", "direction": "remote", "filename": "X.TXT"})
        assert errors
        assert _RecordingThread.instances == []
    finally:
        win.close()


def test_history_toolbar_action_present(qapp, state):
    """Verifies: UIR-082."""
    # UIR-082: a History action is present on the toolbar.
    win = MainWindow(state)
    try:
        from PySide6.QtWidgets import QToolBar

        texts = []
        for tb in win.findChildren(QToolBar):
            texts += [a.text() for a in tb.actions()]
        assert "History" in texts
    finally:
        win.close()


def test_history_dialog_lists_filters_and_clears(qapp, state, tmp_path):
    """Verifies: FR-143."""
    # FR-143: the dialog lists entries (newest first), filters by direction, and
    # clears the history after confirmation.
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QMessageBox

    history = TransferHistory(str(tmp_path / "h.json"))
    history.add_entry(filename="UP.TXT", path="/h/UP.TXT", direction="remote", status="success")
    history.add_entry(filename="DOWN.TXT", path="/h/DOWN.TXT", direction="host", status="failure")
    settings = QSettings(str(tmp_path / "state.ini"), QSettings.Format.IniFormat)
    ws = WindowState(settings)

    dlg = TransferHistoryDialog(None, history, ws)
    try:
        # Newest-first: DOWN.TXT (added last) is row 0.
        assert dlg._table.rowCount() == 2
        assert dlg._table.item(0, 1).text() == "DOWN.TXT"

        # Filter to remote only -> just UP.TXT remains.
        idx = dlg._direction_filter.findData("remote")
        dlg._direction_filter.setCurrentIndex(idx)
        assert dlg._table.rowCount() == 1
        assert dlg._table.item(0, 1).text() == "UP.TXT"

        # Clear (confirmation stubbed to Yes) empties the history and the table.
        import cpm_fm.gui.transfer_history_dialog as thd

        thd.QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
        dlg._on_clear()
        assert dlg._table.rowCount() == 0
        assert history.get_entries() == []
    finally:
        dlg.deleteLater()


def test_history_dialog_retransfer_sets_entry_and_accepts(qapp, state, tmp_path):
    """Verifies: FR-144."""
    # FR-144: clicking Re-transfer records the selected entry and closes (accepts).
    history = TransferHistory(str(tmp_path / "h.json"))
    history.add_entry(filename="UP.TXT", path="/h/UP.TXT", direction="remote", status="success")
    dlg = TransferHistoryDialog(None, history, None)
    try:
        dlg._table.selectRow(0)
        dlg._on_retransfer()
        assert dlg.retransfer_entry is not None
        assert dlg.retransfer_entry["filename"] == "UP.TXT"
        assert dlg.result() == dlg.DialogCode.Accepted
    finally:
        dlg.deleteLater()


# --- Boot-into-CP/M sequence (FR-047/FR-048/FR-049, UIR-068) -------------------


def test_run_boot_sequence_executes_directives(qapp, monkeypatch, state):
    """Verifies: FR-047."""
    # FR-047: SEND goes out via handle_terminal_send (EOL appended there),
    # SENDRAW writes raw control bytes, WAIT sleeps; order is preserved.
    import cpm_fm.gui.mw_remote as mw_remote

    win = MainWindow(state)
    try:
        win.serial_mgr.terminal_connected = True
        win.settings["boot_sequence"] = "SEND DDT\nSENDRAW 03\nWAIT 0.01"
        sent: list[str] = []
        raw: list[tuple] = []
        monkeypatch.setattr(win, "handle_terminal_send", lambda t: sent.append(t))
        monkeypatch.setattr(
            win.serial_mgr, "send_raw", lambda port, data: raw.append((port, data)) or True
        )
        monkeypatch.setattr(mw_remote.time, "sleep", lambda s: None)
        assert win.run_boot_sequence() is True
        assert sent == ["DDT"]
        assert raw == [("terminal", b"\x03")]
    finally:
        win.close()


def test_run_boot_sequence_empty_returns_false(qapp, state):
    """Verifies: FR-047."""
    # An empty sequence disables the feature: run_boot_sequence is a no-op.
    win = MainWindow(state)
    try:
        win.settings["boot_sequence"] = ""
        assert win.run_boot_sequence() is False
    finally:
        win.close()


def test_boot_auto_recovery_runs_sequence_then_reprobes(qapp, monkeypatch, state):
    """Verifies: FR-048."""
    # FR-048: the first probe finds no prompt, so with a sequence configured the
    # boot runs and the re-probe (now seeing a prompt) sets the drive.
    win = MainWindow(state)
    try:
        win.settings["boot_sequence"] = "SEND \\r"
        booted = {"done": False}

        def fake_run():
            booted["done"] = True
            return True

        monkeypatch.setattr(win, "run_boot_sequence", fake_run)

        def fake_capture(cmd, cancellable=False, cancel_event=None):
            return "A>\n" if booted["done"] else "junk\n"

        monkeypatch.setattr(win, "_capture_terminal_response", fake_capture)
        refreshed: list = []
        monkeypatch.setattr(win, "refresh_remote_files", lambda: refreshed.append(True))
        win._do_connect_probe_logic()
        qapp.processEvents()  # deliver the queued connect_probe_ok signal
        assert booted["done"] is True
        assert win.drive_combo.currentText() == "A:"
        assert refreshed == [True]
    finally:
        win.close()


def test_boot_no_recovery_when_sequence_empty(qapp, monkeypatch, state):
    """Verifies: FR-044, FR-048."""
    # FR-048/FR-044: with no sequence configured, a failed probe goes straight
    # to the Remote Filesystem Unavailable dialog — no boot is attempted.
    from cpm_fm.gui.remote_unavailable_dialog import RemoteUnavailableDialog

    win = MainWindow(state)
    try:
        win.settings["boot_sequence"] = ""
        boot_calls: list = []
        monkeypatch.setattr(win, "run_boot_sequence", lambda: boot_calls.append(True) or True)
        monkeypatch.setattr(
            win,
            "_capture_terminal_response",
            lambda cmd, cancellable=False, cancel_event=None: "junk\n",
        )
        shown: list = []
        monkeypatch.setattr(
            RemoteUnavailableDialog,
            "exec",
            lambda self: (
                shown.append(True) or setattr(self, "choice", RemoteUnavailableDialog.CONTINUE)
            ),
        )
        win._do_connect_probe_logic()
        qapp.processEvents()
        assert boot_calls == []
        assert shown == [True]
    finally:
        win.close()


def test_boot_menu_item_reflects_config(qapp, state):
    """Verifies: UIR-105, FR-049."""
    # UIR-105: the Terminal Window context-menu "Boot into CP/M" item is enabled
    # only when a non-empty boot sequence is configured, re-evaluated each time
    # the menu opens (the owner provides the state via boot_enabled_provider).
    win = MainWindow(state)
    try:

        def boot_enabled():
            menu = win.terminal_win._build_context_menu()
            act = next(a for a in menu.actions() if a.text() == i18n.tr("terminal.menu.boot"))
            return act.isEnabled()

        win.settings["boot_sequence"] = ""
        win.show_terminal()
        assert boot_enabled() is False
        win.settings["boot_sequence"] = "SEND \\r"
        assert boot_enabled() is True
        win.settings["boot_sequence"] = "   "  # whitespace only counts as empty
        assert boot_enabled() is False
    finally:
        win.close()


def test_manual_boot_success_reprobes_and_sets_drive(qapp, monkeypatch, state):
    """Verifies: FR-049."""
    # FR-049: a manual boot that reaches CP/M updates the drive drop-down and
    # refreshes the remote list via the connect_probe_ok path.
    win = MainWindow(state)
    try:
        monkeypatch.setattr(win, "run_boot_sequence", lambda: True)
        monkeypatch.setattr(win, "_probe_for_drive", lambda: "B")
        refreshed: list = []
        monkeypatch.setattr(win, "refresh_remote_files", lambda: refreshed.append(True))
        win._do_boot_sequence_logic()
        qapp.processEvents()
        assert win.drive_combo.currentText() == "B:"
        assert refreshed == [True]
    finally:
        win.close()


def test_manual_boot_failure_sets_status_without_dialog(qapp, monkeypatch, state):
    """Verifies: FR-049."""
    # FR-049: a manual boot that still fails reports in the status bar and does
    # NOT raise the modal Remote Filesystem Unavailable dialog.
    win = MainWindow(state)
    try:
        monkeypatch.setattr(win, "run_boot_sequence", lambda: True)
        monkeypatch.setattr(win, "_probe_for_drive", lambda: None)
        statuses: list = []
        monkeypatch.setattr(win, "set_status", lambda t: statuses.append(t))
        win._do_boot_sequence_logic()
        qapp.processEvents()
        assert "Boot sequence did not reach CP/M" in statuses
    finally:
        win.close()


# --- Disk image support (FR-169–FR-173, UIR-108, UIR-109) --------------------


class _FakeGeom:
    name = "ibm-3740"


class _FakeEntry:
    """Stand-in CpmFileEntry: name plus the metadata the details view shows."""

    def __init__(self, name, size_bytes=128, user=0, read_only=False, system=False, archive=False):
        self.name = name
        self.size_bytes = size_bytes
        self.user = user
        self.read_only = read_only
        self.system = system
        self.archive = archive


class _FakeImage:
    """Stand-in CpmImage: two files with deterministic content."""

    geom = _FakeGeom()

    def list_files(self):
        return [
            _FakeEntry("HELLO.TXT", size_bytes=384, user=0, archive=True),
            _FakeEntry("GAME.COM", size_bytes=128, user=3, read_only=True, system=True),
        ]

    def read_file(self, name):
        return b"content-of-" + name.encode()


def test_open_disk_image_extracts_and_lists(qapp, monkeypatch, state, tmp_path):
    """Verifies: FR-169, FR-171, UIR-108."""
    # FR-169/FR-171: opening an image extracts its files to a temp working dir and
    # points the Host pane at them (auto-detected geometry, no picker).
    win = MainWindow(state)
    try:
        img_path = str(tmp_path / "disk.img")
        monkeypatch.setattr(
            "cpm_fm.gui.mw_disk_image.QFileDialog.getOpenFileName",
            lambda *a, **k: (img_path, ""),
        )
        monkeypatch.setattr("cpm_fm.gui.mw_disk_image.is_ambiguous", lambda r: False)
        monkeypatch.setattr("cpm_fm.gui.mw_disk_image.detect_diskdef", lambda p, d: [])
        monkeypatch.setattr("cpm_fm.gui.mw_disk_image.open_image", lambda p, dd=None: _FakeImage())

        win.menu_open_image()
        qapp.processEvents()

        assert win._image_workdir is not None
        assert win.host_dir == win._image_workdir
        assert set(win._host_files) == {"HELLO.TXT", "GAME.COM"}
        extracted = os.path.join(win._image_workdir, "HELLO.TXT")
        with open(extracted, "rb") as fh:
            assert fh.read() == b"content-of-HELLO.TXT"
    finally:
        win.close()


def test_open_disk_image_rejects_bad_file(qapp, monkeypatch, state, tmp_path):
    """Verifies: FR-172."""
    # FR-172: an unreadable/foreign image is rejected with an error dialog and the
    # Host pane is left unchanged (no temp workdir).
    win = MainWindow(state)
    try:
        before_dir = win.host_dir
        monkeypatch.setattr(
            "cpm_fm.gui.mw_disk_image.QFileDialog.getOpenFileName",
            lambda *a, **k: (str(tmp_path / "junk.img"), ""),
        )
        monkeypatch.setattr("cpm_fm.gui.mw_disk_image.is_ambiguous", lambda r: False)
        monkeypatch.setattr("cpm_fm.gui.mw_disk_image.detect_diskdef", lambda p, d: [])
        monkeypatch.setattr("cpm_fm.gui.mw_disk_image.open_image", lambda p, dd=None: None)
        errors = []
        monkeypatch.setattr(
            "cpm_fm.gui.mw_disk_image.QMessageBox.critical",
            lambda *a, **k: errors.append(a[1:]),
        )

        win.menu_open_image()
        qapp.processEvents()

        assert len(errors) == 1
        assert win._image_workdir is None
        assert win.host_dir == before_dir
    finally:
        win.close()


def test_open_disk_image_cleanup_on_close(qapp, monkeypatch, state, tmp_path):
    """Verifies: FR-171."""
    # FR-171: the temp working directory is removed when the window closes.
    win = MainWindow(state)
    monkeypatch.setattr(
        "cpm_fm.gui.mw_disk_image.QFileDialog.getOpenFileName",
        lambda *a, **k: (str(tmp_path / "disk.img"), ""),
    )
    monkeypatch.setattr("cpm_fm.gui.mw_disk_image.is_ambiguous", lambda r: False)
    monkeypatch.setattr("cpm_fm.gui.mw_disk_image.detect_diskdef", lambda p, d: [])
    monkeypatch.setattr("cpm_fm.gui.mw_disk_image.open_image", lambda p, dd=None: _FakeImage())

    win.menu_open_image()
    qapp.processEvents()
    workdir = win._image_workdir
    assert workdir and os.path.isdir(workdir)

    win.close()
    assert not os.path.isdir(workdir)


def test_image_details_dialog_lists_metadata(qapp):
    """Verifies: FR-173, UIR-109."""
    # FR-173: the details dialog renders name/size/user/attributes for each file.
    from PySide6.QtWidgets import QTableWidget

    from cpm_fm.gui.disk_image_details_dialog import DiskImageDetailsDialog

    files = [
        _FakeEntry("HELLO.TXT", size_bytes=384, user=0, archive=True),
        _FakeEntry("GAME.COM", size_bytes=128, user=3, read_only=True, system=True),
    ]
    dlg = DiskImageDetailsDialog(None, files)
    try:
        table = dlg.findChild(QTableWidget)
        assert table.rowCount() == 2
        assert table.item(0, 0).text() == "HELLO.TXT"
        assert table.item(0, 1).text() == "384"
        assert table.item(0, 2).text() == "0"
        assert table.item(0, 3).text() == "A"
        assert table.item(1, 2).text() == "3"
        assert table.item(1, 3).text() == "R S"  # read-only + system
    finally:
        dlg.close()


def test_image_details_action_enabled_only_when_image_open(qapp, monkeypatch, state, tmp_path):
    """Verifies: FR-173, UIR-109."""
    # UIR-109: the Image Details… action is disabled until an image is open and is
    # re-disabled (and its metadata cleared) when the image is closed.
    win = MainWindow(state)
    try:
        assert win._image_details_action is not None
        assert not win._image_details_action.isEnabled()

        monkeypatch.setattr(
            "cpm_fm.gui.mw_disk_image.QFileDialog.getOpenFileName",
            lambda *a, **k: (str(tmp_path / "disk.img"), ""),
        )
        monkeypatch.setattr("cpm_fm.gui.mw_disk_image.is_ambiguous", lambda r: False)
        monkeypatch.setattr("cpm_fm.gui.mw_disk_image.detect_diskdef", lambda p, d: [])
        monkeypatch.setattr("cpm_fm.gui.mw_disk_image.open_image", lambda p, dd=None: _FakeImage())

        win.menu_open_image()
        qapp.processEvents()
        assert win._image_details_action.isEnabled()
        assert [e.name for e in win._image_files] == ["HELLO.TXT", "GAME.COM"]

        win._cleanup_image_workdir()
        assert not win._image_details_action.isEnabled()
        assert win._image_files == []
    finally:
        win.close()


def test_image_details_noop_when_no_image(qapp, monkeypatch, state):
    """Verifies: FR-173, UIR-109."""
    # UIR-109: invoking the handler with no image open must not build a dialog.
    win = MainWindow(state)
    try:
        built = []
        monkeypatch.setattr(
            "cpm_fm.gui.mw_disk_image.DiskImageDetailsDialog",
            lambda *a, **k: built.append(1),
        )
        win.menu_image_details()
        assert built == []
    finally:
        win.close()


def _open_fake_image(win, qapp, monkeypatch, tmp_path):
    """Open a fake disk image in ``win`` and return its temp working directory."""
    monkeypatch.setattr(
        "cpm_fm.gui.mw_disk_image.QFileDialog.getOpenFileName",
        lambda *a, **k: (str(tmp_path / "disk.img"), ""),
    )
    monkeypatch.setattr("cpm_fm.gui.mw_disk_image.is_ambiguous", lambda r: False)
    monkeypatch.setattr("cpm_fm.gui.mw_disk_image.detect_diskdef", lambda p, d: [])
    monkeypatch.setattr("cpm_fm.gui.mw_disk_image.open_image", lambda p, dd=None: _FakeImage())
    win.menu_open_image()
    qapp.processEvents()
    return win._image_workdir


def test_load_config_discards_open_image(qapp, monkeypatch, state, tmp_path):
    """Verifies: FR-171."""
    # FR-171: loading a configuration discards any open disk image — the temp
    # working directory is removed and the Image Details view is no longer
    # available — rather than leaving stale image contents viewable.
    import json

    win = MainWindow(state)
    try:
        workdir = _open_fake_image(win, qapp, monkeypatch, tmp_path)
        assert workdir and os.path.isdir(workdir)
        assert win._image_details_action.isEnabled()

        cfg_dir = tmp_path / "cfgdir"
        cfg_dir.mkdir()
        cfg = tmp_path / "s.json"
        cfg.write_text(json.dumps({"host_directory": str(cfg_dir)}))
        win.load_config(str(cfg))
        qapp.processEvents()

        assert win._image_workdir is None
        assert win._image_files == []
        assert not win._image_details_action.isEnabled()
        assert not os.path.isdir(workdir)  # temp dir removed, no leak
        assert win.host_dir == str(cfg_dir)
    finally:
        win.close()


def test_change_dir_discards_open_image(qapp, monkeypatch, state, tmp_path):
    """Verifies: FR-171."""
    # FR-171: Change Directory to another folder discards the open image too.
    win = MainWindow(state)
    try:
        workdir = _open_fake_image(win, qapp, monkeypatch, tmp_path)
        assert workdir and os.path.isdir(workdir)

        newdir = tmp_path / "plain"
        newdir.mkdir()
        monkeypatch.setattr(
            "cpm_fm.gui.mw_file_panes.QFileDialog.getExistingDirectory",
            lambda *a, **k: str(newdir),
        )
        win.change_host_dir()
        qapp.processEvents()

        assert win._image_workdir is None
        assert win._image_files == []
        assert not win._image_details_action.isEnabled()
        assert not os.path.isdir(workdir)
        assert win.host_dir == str(newdir)
    finally:
        win.close()


def test_save_image_action_gated_by_setting(qapp, monkeypatch, state, tmp_path):
    """Verifies: FR-174, UIR-110."""
    # UIR-110: Save Image… is enabled only while an image is open AND the opt-in
    # image_write_enabled setting is on; it re-disables when either goes away.
    win = MainWindow(state)
    try:
        assert win._save_image_action is not None
        assert not win._save_image_action.isEnabled()  # no image, writing off

        _open_fake_image(win, qapp, monkeypatch, tmp_path)
        # Image open but writing still off (default) → still disabled.
        assert not win._save_image_action.isEnabled()

        win.settings["image_write_enabled"] = "ON"
        win._update_save_image_action()
        assert win._save_image_action.isEnabled()

        win._cleanup_image_workdir()  # closing the image re-disables it
        assert not win._save_image_action.isEnabled()
    finally:
        win.close()


def test_save_image_noop_when_writing_disabled(qapp, monkeypatch, state, tmp_path):
    """Verifies: FR-174, UIR-110."""
    # UIR-110: with writing off, invoking the handler must not even open the
    # Save-As dialog.
    win = MainWindow(state)
    try:
        _open_fake_image(win, qapp, monkeypatch, tmp_path)
        called = []
        monkeypatch.setattr(
            "cpm_fm.gui.mw_disk_image.QFileDialog.getSaveFileName",
            lambda *a, **k: called.append(1) or ("", ""),
        )
        win.menu_save_image()
        assert called == []
    finally:
        win.close()


def test_save_image_writes_new_image(qapp, monkeypatch, state, tmp_path):
    """Verifies: FR-174, DR-050, UIR-110."""
    # FR-174: with writing enabled, Save Image re-packs the working directory into
    # a fresh image at the chosen path; re-opening it lists those files.
    from cpm_fm.utils.disk_image import load_diskdefs
    from cpm_fm.utils.disk_image.image import CpmImage

    win = MainWindow(state)
    try:
        geom = load_diskdefs().get("ibm-3740")
        src = tmp_path / "src.img"
        src.write_bytes(bytes([0xE5]) * geom.total_bytes)
        workdir = tmp_path / "wd"
        workdir.mkdir()
        (workdir / "A.TXT").write_bytes(b"a" * 128)
        (workdir / "B.TXT").write_bytes(b"b" * 256)

        win._image_source = str(src)
        win._image_geom = geom
        win._image_workdir = str(workdir)
        win.settings["image_write_enabled"] = "ON"
        win._update_save_image_action()

        dest = tmp_path / "out.img"
        monkeypatch.setattr(
            "cpm_fm.gui.mw_disk_image.QFileDialog.getSaveFileName",
            lambda *a, **k: (str(dest), ""),
        )
        win.menu_save_image()
        qapp.processEvents()

        assert dest.exists()
        reopened = CpmImage(bytearray(dest.read_bytes()), geom)
        assert {f.name for f in reopened.list_files()} == {"A.TXT", "B.TXT"}
        assert reopened.read_file("A.TXT") == b"a" * 128
        assert reopened.read_file("B.TXT") == b"b" * 256
    finally:
        win.close()


def test_save_image_refuses_source_overwrite(qapp, monkeypatch, state, tmp_path):
    """Verifies: FR-174."""
    # FR-174: Save Image never writes over the source image — choosing the source
    # path is refused with a warning and nothing is written.
    from cpm_fm.utils.disk_image import load_diskdefs

    win = MainWindow(state)
    try:
        geom = load_diskdefs().get("ibm-3740")
        src = tmp_path / "src.img"
        original = bytes([0xE5]) * geom.total_bytes
        src.write_bytes(original)
        workdir = tmp_path / "wd"
        workdir.mkdir()
        (workdir / "A.TXT").write_bytes(b"a" * 128)

        win._image_source = str(src)
        win._image_geom = geom
        win._image_workdir = str(workdir)
        win.settings["image_write_enabled"] = "ON"
        win._update_save_image_action()

        monkeypatch.setattr(
            "cpm_fm.gui.mw_disk_image.QFileDialog.getSaveFileName",
            lambda *a, **k: (str(src), ""),  # user picks the source path
        )
        warnings = []
        monkeypatch.setattr(
            "cpm_fm.gui.mw_disk_image.QMessageBox.warning",
            lambda *a, **k: warnings.append(a[1:]),
        )
        win.menu_save_image()
        assert warnings  # refused with a warning
        assert src.read_bytes() == original  # source untouched
    finally:
        win.close()
