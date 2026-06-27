"""Headless smoke tests for the PySide6 GUI (v1.3 migration).

These construct the real widgets under an offscreen Qt platform to catch import
errors, signal/slot wiring mistakes, and obvious layout faults without a display.
Run headless via the ``QT_QPA_PLATFORM=offscreen`` environment variable (set in CI).
"""

import os
import tempfile

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
        def __init__(self, ser, monitor=None, progress=None, cancel_check=None):
            self.progress = progress

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
    monkeypatch.setattr("cpm_fm.app.time.sleep", lambda *a, **k: None)


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


def test_batch_progress_dialog_shows_file_position(qapp, state):
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
    # UIR-017: the drive-selection drop-down lists A: through P: (16 drives).
    win = MainWindow(state)
    try:
        items = [win.drive_combo.itemText(i) for i in range(win.drive_combo.count())]
        assert items == [f"{chr(c)}:" for c in range(ord("A"), ord("P") + 1)]
    finally:
        win.close()


def test_change_drive_success_refreshes_remote_list(qapp, monkeypatch, state):
    # FR-102: when the "<letter>>" prompt appears, the remote list is populated
    # exactly as Update does. Stub the capture to avoid real serial/sleeps.
    win = MainWindow(state)
    try:
        win.serial_mgr.terminal_connected = True
        monkeypatch.setattr(win, "_capture_terminal_response", lambda cmd, cancellable=False: "B:\nB>\n")
        calls = []
        monkeypatch.setattr(win, "_do_refresh_remote_logic", lambda: calls.append("refresh"))
        win._do_change_drive_logic("B")
        assert calls == ["refresh"]
    finally:
        win.close()


def test_change_drive_not_found_clears_list_and_warns(qapp, monkeypatch, state):
    # FR-103: no "<letter>>" prompt -> clear the remote list and warn the user.
    win = MainWindow(state)
    try:
        win.remote_list.addItem("STALE.TXT")
        win.serial_mgr.terminal_connected = True
        monkeypatch.setattr(win, "_capture_terminal_response", lambda cmd, cancellable=False: "\nnot ready\n")
        warned = []
        monkeypatch.setattr("cpm_fm.app.QMessageBox.warning", lambda *a, **k: warned.append(a[1:]))
        win._do_change_drive_logic("B")
        qapp.processEvents()  # deliver the queued drive_not_found signal
        assert win.remote_list.count() == 0
        assert warned == [("Drive not found", "Drive B: not found")]
    finally:
        win.close()


def test_change_drive_requires_open_terminal(qapp, monkeypatch, state):
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
        monkeypatch.setattr(
            "cpm_fm.app.QMessageBox.critical", lambda *a, **k: errors.append(a[1:])
        )
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
        monkeypatch.setattr(
            "cpm_fm.app.QMessageBox.critical", lambda *a, **k: errors.append(a[1:])
        )
        win.refresh_remote_files()
        qapp.processEvents()
        assert errors == []
    finally:
        win.close()


def test_disconnect_clears_remote_list(qapp, monkeypatch, state):
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


def test_host_update_button_refreshes_host_only(qapp, monkeypatch, state):
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


def test_main_window_constructs(qapp, state):
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


def test_terminal_window_write_and_clear(qapp):
    cleared = []
    term = TerminalWindow(
        None, send_callback=lambda t: None, clear_callback=lambda: cleared.append(1)
    )
    try:
        term.write_text("HELLO")
        assert "HELLO" in term.receive_area.toPlainText()
        term.clear_text()
        assert term.receive_area.toPlainText() == ""
        assert cleared == [1]  # FR-095: Clear invokes the buffer-clear callback.
    finally:
        term.deleteLater()


def test_terminal_write_text_line_endings(qapp):
    # FR-091: CR, LF, and the CRLF pair each produce exactly one new line in the
    # receive area — no blank line between lines. Backspaces erase a character.
    term = TerminalWindow(None, send_callback=lambda t, eol: None)
    try:
        term.write_text("L1\r\nL2\r\nL3")
        assert term.receive_area.toPlainText() == "L1\nL2\nL3"
        assert term.receive_area.document().blockCount() == 3

        term.clear_text()
        term.write_text("A\rB\rC")  # lone CR also a single break
        assert term.receive_area.toPlainText() == "A\nB\nC"

        term.clear_text()
        term.write_text("AB\bC")  # backspace erases the B
        assert term.receive_area.toPlainText() == "AC"
    finally:
        term.deleteLater()


def test_parse_send_text_control_characters(qapp):
    # FR-156: caret notation maps to control bytes; ^^ is a literal caret; an
    # unrecognised escape is left literal. is_pure_control is True only when the
    # result is non-empty and contains no printable characters.
    parse = TerminalWindow._parse_send_text
    assert parse("^C") == ("\x03", True)  # Ctrl-C, pure control
    assert parse("^c") == ("\x03", True)  # case-insensitive
    assert parse("^@") == ("\x00", True)  # NUL
    assert parse("^[") == ("\x1b", True)  # ESC
    assert parse("^?") == ("\x7f", True)  # DEL
    assert parse("^^") == ("^", False)  # literal caret (printable)
    assert parse("DIR") == ("DIR", False)  # plain text
    assert parse("AT^C") == ("AT\x03", False)  # mixed -> not pure control
    assert parse("") == ("", False)  # empty -> not pure control
    assert parse("^") == ("^", False)  # trailing lone caret kept literal
    assert parse("^9") == ("^9", False)  # unrecognised escape kept literal


def test_terminal_send_bare_enter_and_control(qapp):
    # FR-155/FR-156: send_text forwards the (parsed) text and an append_eol flag.
    sent = []
    term = TerminalWindow(None, send_callback=lambda t, eol: sent.append((t, eol)))
    try:
        # Empty field -> bare EOL (text empty, append_eol True so the owner adds EOL).
        term.tx_entry.setText("")
        term.send_text()
        assert sent[-1] == ("", True)
        # Pure control -> sent verbatim, no EOL appended.
        term.tx_entry.setText("^C")
        term.send_text()
        assert sent[-1] == ("\x03", False)
        # Plain text -> EOL appended.
        term.tx_entry.setText("DIR")
        term.send_text()
        assert sent[-1] == ("DIR", True)
        assert term.tx_entry.text() == ""  # field cleared after each send
    finally:
        term.deleteLater()


def test_handle_terminal_send_append_eol_flag(qapp, monkeypatch, state):
    # FR-094/FR-156: handle_terminal_send appends the configured EOL by default,
    # but sends the data verbatim when append_eol is False.
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


def test_geometry_and_last_config_persist_across_sessions(qapp, state, tmp_path):
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

        monkeypatch.setattr("cpm_fm.app.QFileDialog.getOpenFileName", fake_open)
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
    # FR-018: with no remembered file, New presents the Save dialog before
    # resetting to the default configuration.
    target = tmp_path / "saved.json"

    win = MainWindow(state)
    try:
        win.window_state.last_config = ""
        win.settings = {"terminal_port": "COM9"}
        monkeypatch.setattr(win, "refresh_host_files", lambda: None)
        monkeypatch.setattr(
            "cpm_fm.app.QFileDialog.getSaveFileName",
            lambda *a, **k: (str(target), "JSON files (*.json)"),
        )

        win.menu_new()

        assert target.exists()
        assert win.settings == DEFAULT_SETTINGS
    finally:
        win.close()
        win.deleteLater()


def test_help_menu_contains_about_action(qapp, state):
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
    # FR-022: selecting Help > About constructs and shows the About dialog.
    win = MainWindow(state)
    try:
        opened = []

        class _FakeAbout:
            def __init__(self, parent=None):
                opened.append(parent)

            def exec(self):
                return 1

        monkeypatch.setattr("cpm_fm.app.AboutDialog", _FakeAbout)
        win.menu_about()
        assert opened == [win]
    finally:
        win.close()
        win.deleteLater()


def test_about_dialog_contents(qapp):
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

        monkeypatch.setattr("cpm_fm.app.ManualDialog", _FakeManual)
        win.menu_manual()
        assert opened == [win]
    finally:
        win.close()
        win.deleteLater()


def test_menu_manual_reuses_open_window(qapp, monkeypatch, state):
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

        monkeypatch.setattr("cpm_fm.app.ManualDialog", _FakeManual)
        win.menu_manual()  # opens
        win.menu_manual()  # should raise the existing one
        assert len(constructed) == 1
        assert raised == [True]
    finally:
        win.close()
        win.deleteLater()


def test_manual_dialog_contents(qapp):
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
    # FR-018: cancelling the Save dialog cancels New entirely — the current
    # configuration, ports, and remote list are retained.
    win = MainWindow(state)
    try:
        win.window_state.last_config = ""
        win.settings = {"terminal_port": "COM9"}
        win.remote_list.addItems(["KEEP.TXT"])
        disconnected = []
        monkeypatch.setattr(win, "do_disconnect", lambda: disconnected.append(1))
        monkeypatch.setattr("cpm_fm.app.QFileDialog.getSaveFileName", lambda *a, **k: ("", ""))

        win.menu_new()

        assert win.settings == {"terminal_port": "COM9"}
        assert disconnected == []
        assert win.remote_list.count() == 1
    finally:
        win.close()
        win.deleteLater()


def test_menu_save_remembers_config_folder(qapp, monkeypatch, state, tmp_path):
    # FR-006: a successful File > Save records its folder for the next dialog.
    target = tmp_path / "out.json"

    win = MainWindow(state)
    try:
        monkeypatch.setattr(
            "cpm_fm.app.QFileDialog.getSaveFileName",
            lambda *a, **k: (str(target), "JSON files (*.json)"),
        )
        win.menu_save()
        assert state.last_config_dir == str(tmp_path)
    finally:
        win.close()
        win.deleteLater()


# --------------------------------------------------------------- file actions


def test_build_viewer_args_substitutes_token():
    # FR-112: $1 is replaced by the file path; a path with spaces stays a single
    # argument and is never re-split by the tokeniser.
    from cpm_fm.app import build_viewer_args

    assert build_viewer_args("notepad $1", "C:/dir/F.TXT") == ["notepad", "C:/dir/F.TXT"]
    assert build_viewer_args("notepad $1", "/tmp/a b/F.TXT") == ["notepad", "/tmp/a b/F.TXT"]
    # No $1 token -> the path is appended as the final argument.
    assert build_viewer_args("editor", "F.TXT") == ["editor", "F.TXT"]


def test_lists_have_context_menus(qapp, state):
    # UIR-018/UIR-019: both file lists expose a custom (right-click) context menu.
    from PySide6.QtCore import Qt

    win = MainWindow(state)
    try:
        assert win.host_list.contextMenuPolicy() == Qt.ContextMenuPolicy.CustomContextMenu
        assert win.remote_list.contextMenuPolicy() == Qt.ContextMenuPolicy.CustomContextMenu
    finally:
        win.close()


def test_host_view_launches_viewer(qapp, monkeypatch, state, tmp_path):
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
    # FR-114/FR-116/FR-118: Apply on the rename dialog renames the file and refreshes.
    win = MainWindow(state)
    try:
        win.host_dir = str(tmp_path)
        (tmp_path / "OLD.TXT").write_text("x")
        monkeypatch.setattr("cpm_fm.app.FileActionDialog", _fake_action_dialog("NEW.TXT"))
        refreshed = []
        monkeypatch.setattr(win, "refresh_host_files", lambda: refreshed.append(1))
        win._host_rename("OLD.TXT")
        assert (tmp_path / "NEW.TXT").exists()
        assert not (tmp_path / "OLD.TXT").exists()
        assert refreshed == [1]
    finally:
        win.close()


def test_host_rename_cancelled_makes_no_change(qapp, monkeypatch, state, tmp_path):
    # FR-114: Cancel leaves the file untouched.
    win = MainWindow(state)
    try:
        win.host_dir = str(tmp_path)
        (tmp_path / "OLD.TXT").write_text("x")
        monkeypatch.setattr(
            "cpm_fm.app.FileActionDialog", _fake_action_dialog("NEW.TXT", accepted=False)
        )
        win._host_rename("OLD.TXT")
        assert (tmp_path / "OLD.TXT").exists()
        assert not (tmp_path / "NEW.TXT").exists()
    finally:
        win.close()


def test_host_delete_removes_file(qapp, monkeypatch, state, tmp_path):
    # FR-115/FR-116/FR-118: Apply on the delete dialog removes the file and refreshes.
    win = MainWindow(state)
    try:
        win.host_dir = str(tmp_path)
        (tmp_path / "F.TXT").write_text("x")
        monkeypatch.setattr("cpm_fm.app.FileActionDialog", _fake_action_dialog("F.TXT"))
        refreshed = []
        monkeypatch.setattr(win, "refresh_host_files", lambda: refreshed.append(1))
        win._host_delete("F.TXT")
        assert not (tmp_path / "F.TXT").exists()
        assert refreshed == [1]
    finally:
        win.close()


def test_remote_rename_sends_command(qapp, monkeypatch, state):
    # FR-117: remote Rename sends rename_remote_cmd with $1=old, $2=new.
    win = MainWindow(state)
    try:
        win.serial_mgr.terminal_connected = True
        win.settings = {"rename_remote_cmd": "REN $2=$1"}
        monkeypatch.setattr("cpm_fm.app.FileActionDialog", _fake_action_dialog("NEW.TXT"))
        _RecordingThread.instances = []
        monkeypatch.setattr("cpm_fm.app.threading.Thread", _RecordingThread)
        win._remote_rename("OLD.TXT")
        assert _RecordingThread.instances[0].args == ("REN NEW.TXT=OLD.TXT",)
    finally:
        win.close()


def test_remote_delete_sends_command(qapp, monkeypatch, state):
    # FR-117: remote Delete sends delete_remote_cmd with $1=name.
    win = MainWindow(state)
    try:
        win.serial_mgr.terminal_connected = True
        win.settings = {"delete_remote_cmd": "ERA $1"}
        monkeypatch.setattr("cpm_fm.app.FileActionDialog", _fake_action_dialog("F.TXT"))
        _RecordingThread.instances = []
        monkeypatch.setattr("cpm_fm.app.threading.Thread", _RecordingThread)
        win._remote_delete("F.TXT")
        assert _RecordingThread.instances[0].args == (["ERA F.TXT"],)
    finally:
        win.close()


def test_host_delete_removes_all_selected_files(qapp, monkeypatch, state, tmp_path):
    # FR-110/FR-116: Delete from the context menu removes every selected file.
    win = MainWindow(state)
    try:
        win.host_dir = str(tmp_path)
        for fn in ("A.TXT", "B.TXT", "C.TXT"):
            (tmp_path / fn).write_text("x")
        monkeypatch.setattr("cpm_fm.app.FileActionDialog", _fake_action_dialog("A.TXT"))
        monkeypatch.setattr(win, "refresh_host_files", lambda: None)
        win._host_delete(["A.TXT", "B.TXT", "C.TXT"])
        assert not (tmp_path / "A.TXT").exists()
        assert not (tmp_path / "B.TXT").exists()
        assert not (tmp_path / "C.TXT").exists()
    finally:
        win.close()


def test_remote_delete_sends_command_per_selected_file(qapp, monkeypatch, state):
    # FR-111/FR-117: remote Delete sends delete_remote_cmd once per selected file.
    win = MainWindow(state)
    try:
        win.serial_mgr.terminal_connected = True
        win.settings = {"delete_remote_cmd": "ERA $1"}
        monkeypatch.setattr("cpm_fm.app.FileActionDialog", _fake_action_dialog("A.TXT"))
        _RecordingThread.instances = []
        monkeypatch.setattr("cpm_fm.app.threading.Thread", _RecordingThread)
        win._remote_delete(["A.TXT", "B.TXT"])
        assert _RecordingThread.instances[0].args == (["ERA A.TXT", "ERA B.TXT"],)
    finally:
        win.close()


def test_context_menu_targets_uses_full_selection_when_clicked_item_selected(qapp, state):
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
    # FR-118: after sending the command the remote list is refreshed.
    win = MainWindow(state)
    try:
        captured = []
        monkeypatch.setattr(
            win, "_capture_terminal_response", lambda c, cancellable=False: captured.append(c) or ""
        )
        refreshed = []
        monkeypatch.setattr(win, "_do_refresh_remote_logic", lambda: refreshed.append(1))
        win._do_remote_file_cmd("ERA F.TXT")
        assert captured == ["ERA F.TXT"]
        assert refreshed == [1]
    finally:
        win.close()


def test_remote_view_requires_both_flags(qapp, monkeypatch, state):
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
    # FR-120: the GUI cancel handler raises the worker-polled cancel flag.
    win = MainWindow(state)
    try:
        assert not win._transfer_cancel.is_set()
        win._request_transfer_cancel()
        assert win._transfer_cancel.is_set()
    finally:
        win.close()


def test_cancellable_sleep_returns_immediately_when_cancelled(qapp, state):
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
    # FR-120: with no cancel pending the wait runs its full (step-counted)
    # interval and reports not-cancelled. time.sleep is neutralised so the step
    # loop completes instantly.
    win = MainWindow(state)
    try:
        monkeypatch.setattr("cpm_fm.app.time.sleep", lambda *a, **k: None)
        assert win._cancellable_sleep(2.0) is False
    finally:
        win.close()


def test_wait_for_terminal_idle_returns_early_on_cancel(qapp, state):
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
        monkeypatch.setattr("cpm_fm.app.time.sleep", lambda *a, **k: None)
        assert win._capture_terminal_response("DIR") == ""
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
    monkeypatch.setattr("cpm_fm.app.time.sleep", lambda *a, **k: None)


def test_cancelled_transfer_is_not_reported_as_error(qapp, monkeypatch, state):
    # FR-120: cancelling mid-transfer closes the dialog, sets a "cancelled"
    # status, and raises no error dialog; with nothing completed, no refresh.
    win = MainWindow(state)
    try:
        errors = []
        monkeypatch.setattr("cpm_fm.app.QMessageBox.critical", lambda *a, **k: errors.append(a[1:]))
        refreshed = []
        monkeypatch.setattr(win, "refresh_remote_files", lambda: refreshed.append(1))

        class _CancellingXModem:
            def __init__(self, ser, monitor=None, progress=None, cancel_check=None):
                pass

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


def test_cancel_after_partial_batch_refreshes_and_skips_rest(qapp, monkeypatch, state):
    # FR-120: when a multi-file batch is cancelled after some files completed,
    # the remaining files are skipped and the destination list refreshes once.
    win = MainWindow(state)
    try:
        monkeypatch.setattr("cpm_fm.app.QMessageBox.critical", lambda *a, **k: None)
        refreshed = []
        monkeypatch.setattr(win, "refresh_remote_files", lambda: refreshed.append(1))
        calls = []

        class _XModem:
            def __init__(self, ser, monitor=None, progress=None, cancel_check=None):
                pass

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
    # UIR-041: the General Config dialog gathers the remote command fields
    # (List Files, Receive/Send, the XMODEM-1K toggle + 1K commands, Rename,
    # Delete) into a "Remote" group placed first, with Rename/Delete labelled
    # without the "Remote" suffix. UIR-089/UIR-090: the 1K toggle and its two
    # command fields sit directly below Send to Remote.
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
        # toggle and its 1K command fields directly below Send to Remote.
        form = first.layout()
        labels = [
            form.itemAt(i, QFormLayout.ItemRole.LabelRole).widget().text()
            for i in range(form.rowCount())
        ]
        assert labels == [
            "List Files",
            "Receive from Remote",
            "Send to Remote",
            "Use XMODEM-1K",
            "Receive from Remote (1K)",
            "Send to Remote (1K)",
            "Rename",
            "Delete",
        ]
        # The non-remote settings remain reachable for saving (e.g. EOL).
        assert "eol" in dlg.entries and "host_directory" in dlg.entries
    finally:
        dlg.deleteLater()


def test_general_config_save_keeps_current_host_dir(qapp, state, monkeypatch):
    # Regression: with a host directory saved in the config and a *different*
    # directory currently selected (e.g. via Change Directory), saving the
    # General Config dialog without touching the host-directory field must not
    # revert the current selection, nor change the stored config value.
    import cpm_fm.app as app_module

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

        monkeypatch.setattr(app_module, "GeneralConfigDialog", fake_dialog)
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
    # FR-020a: the Serial dialog Save writes only the serial settings to the
    # currently loaded config file, leaves the general settings in that file
    # untouched, and never presents a Save dialog.
    import json

    import cpm_fm.app as app_module

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

        monkeypatch.setattr(app_module, "SerialConfigDialog", fake_dialog)
        # FR-020a: no file-select dialog may be shown.
        def _no_dialog(*a, **k):
            raise AssertionError("Save dialog must not be presented")

        monkeypatch.setattr("cpm_fm.app.QFileDialog.getSaveFileName", _no_dialog)

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
    # FR-021a: the General dialog Save writes only the general settings to the
    # currently loaded config file, leaving the serial settings untouched.
    import json

    import cpm_fm.app as app_module

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

        monkeypatch.setattr(app_module, "GeneralConfigDialog", fake_dialog)

        def _no_dialog(*a, **k):
            raise AssertionError("Save dialog must not be presented")

        monkeypatch.setattr("cpm_fm.app.QFileDialog.getSaveFileName", _no_dialog)

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

        monkeypatch.setattr(app_module, "SerialConfigDialog", fake_dialog)
        win.menu_serial_config()
        captured["callback"]({"terminal_port": "COM9"})

        assert warnings, "a warning dialog should be shown"
        assert not saved, "no file should be written when no config is loaded"
        # The setting is still applied to the running session.
        assert win.settings["terminal_port"] == "COM9"
    finally:
        win.close()


def test_issue_remote_cmd_uses_1k_command_when_enabled(qapp, state, monkeypatch):
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
        assert emitted == ["<B5><06>"]
    finally:
        win.close()


def test_general_config_has_echo_transfer_field(qapp, monkeypatch):
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


def test_config_menu_has_language_submenu(qapp, state):
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
    # FR-125/UIR-005: with no config loaded the title is the application name alone.
    win = MainWindow(state)
    try:
        assert win.windowTitle() == "CP/M File Manager"
    finally:
        win.close()
        win.deleteLater()


def test_window_title_includes_loaded_config_basename(qapp, state, tmp_path):
    # FR-125: loading a config appends its base name (no path, no extension).
    win = MainWindow(state)
    try:
        win.load_config(_write_config(tmp_path, "my_settings.json"))
        assert win.windowTitle() == "CP/M File Manager — my_settings"
    finally:
        win.close()
        win.deleteLater()


def test_window_title_cleared_by_new(qapp, state, tmp_path, monkeypatch):
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
    # FR-137: dropping a pane's own files back onto itself is a no-op (rejected).
    win = MainWindow(state)
    try:
        assert win.host_list.decode_drop(_cpm_mime("host", ["A.TXT"])) is None
        assert win.remote_list.decode_drop(_cpm_mime("remote", ["A.TXT"])) is None
    finally:
        win.close()
        win.deleteLater()


def test_decode_drop_external_files_remote_only(qapp, state, tmp_path):
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
    # UIR-078/DR-044: the runtime icon ships as package data and app_icon()
    # returns a real (non-null) QIcon loaded from it.
    from cpm_fm.gui.theme import APP_ICON_PATH, app_icon

    assert APP_ICON_PATH.is_file(), f"missing runtime icon at {APP_ICON_PATH}"
    icon = app_icon()
    assert not icon.isNull()
    assert icon.availableSizes(), "icon has no rendered sizes"


def test_app_icon_missing_falls_back_to_empty(qapp, monkeypatch):
    # UIR-078: a missing icon resource yields an empty QIcon rather than raising,
    # so start-up survives its absence (consistent with the optional CR-006 icons).
    from pathlib import Path

    from cpm_fm.gui import theme

    monkeypatch.setattr(theme, "APP_ICON_PATH", Path("does-not-exist.png"))
    icon = theme.app_icon()
    assert icon.isNull()


# --------------------------------------------------------- transfer history (Feature 2)


def test_successful_transfer_records_history(qapp, monkeypatch, state):
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
    # FR-142: a user-cancelled file is recorded with "cancelled" status.
    win = MainWindow(state)
    try:
        monkeypatch.setattr(win, "refresh_remote_files", lambda: None)

        class _CancellingXModem:
            def __init__(self, ser, monitor=None, progress=None, cancel_check=None):
                pass

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
