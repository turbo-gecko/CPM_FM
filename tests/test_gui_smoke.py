"""Headless smoke tests for the PySide6 GUI (v1.3 migration).

These construct the real widgets under an offscreen Qt platform to catch import
errors, signal/slot wiring mistakes, and obvious layout faults without a display.
Run headless via the ``QT_QPA_PLATFORM=offscreen`` environment variable (set in CI).
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from cpm_fm.app import MainWindow  # noqa: E402
from cpm_fm.gui.terminal_window import TerminalWindow  # noqa: E402
from cpm_fm.gui.window_state import WindowState  # noqa: E402


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
    """Minimal stand-in for a pyserial port used by the transfer workers."""

    is_open = False  # so SerialManager.close_ports() skips closing it on teardown

    def reset_input_buffer(self):
        pass


def _fake_xmodem_cls(success=True, calls=None):
    # success may be a single bool applied to every file, or a list/tuple of
    # per-call booleans consumed in order (so a batch test can fail file N).
    # calls, if given, records each transferred path so order/count is assertable.
    seq = iter(success) if isinstance(success, (list, tuple)) else None

    class _FakeXModem:
        def __init__(self, ser, monitor=None, progress=None):
            self.progress = progress

        def _report(self):
            # FR-105: exercise the progress hook so the transfer_progress signal
            # path runs during the smoke test.
            if self.progress:
                self.progress(1, 128, 128)

        def _result(self):
            return next(seq) if seq is not None else success

        def send_file(self, path):
            if calls is not None:
                calls.append(path)
            self._report()
            return self._result()

        def receive_file(self, path):
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
    monkeypatch.setattr(win.serial_mgr, "send_data", lambda *a, **k: None)
    monkeypatch.setattr("cpm_fm.app.XModem", _fake_xmodem_cls(success, calls))
    # Neutralise worker-thread sleeps (launch delay, FR-109 inter-file idle/settle)
    # so batch tests run fast while still exercising the real wait logic.
    monkeypatch.setattr("cpm_fm.app.time.sleep", lambda *a, **k: None)


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
        monkeypatch.setattr(win, "_capture_terminal_response", lambda cmd: "B:\nB>\n")
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
        monkeypatch.setattr(win, "_capture_terminal_response", lambda cmd: "\nnot ready\n")
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
        assert win.statusBar().currentMessage() == "Terminal port not open - cannot read file list"
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
