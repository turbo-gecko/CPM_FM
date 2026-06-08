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


def _fake_xmodem_cls(success):
    class _FakeXModem:
        def __init__(self, ser, monitor=None, progress=None):
            self.progress = progress

        def _report(self):
            # FR-105: exercise the progress hook so the transfer_progress signal
            # path runs during the smoke test.
            if self.progress:
                self.progress(1, 128, 128)

        def send_file(self, path):
            self._report()
            return success

        def receive_file(self, path):
            self._report()
            return success

    return _FakeXModem


def _arm_transfer(win, monkeypatch, success=True):
    # Put the window in a state where the transfer workers can run without real
    # serial hardware or sleeps: both flags connected, a fake transport port,
    # no launch delay, send_data and XModem stubbed.
    win.settings = {"xfer_launch_delay": 0}
    win.serial_mgr.terminal_connected = True
    win.serial_mgr.transport_connected = True
    win.serial_mgr.transport_port = _FakeSerial()
    monkeypatch.setattr(win.serial_mgr, "send_data", lambda *a, **k: None)
    monkeypatch.setattr("cpm_fm.app.XModem", _fake_xmodem_cls(success))


def test_copy_to_host_refreshes_host_list(qapp, monkeypatch, state):
    # Bug 1: a successful remote->host transfer must refresh the Host Files list.
    win = MainWindow(state)
    try:
        calls = []
        monkeypatch.setattr(win, "refresh_host_files", lambda: calls.append("host"))
        _arm_transfer(win, monkeypatch)
        win._transfer_to_host(os.path.join(win.host_dir, "FOO.TXT"))
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
        win._transfer_to_remote(os.path.join(win.host_dir, "FOO.TXT"))
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
        win._transfer_to_host(os.path.join(win.host_dir, "FOO.TXT"))
        qapp.processEvents()
        assert calls == []
    finally:
        win.close()


def test_progress_dialog_started_and_updates(qapp, state):
    # FR-105/UIR-051: transfer_started builds the modal dialog naming the file;
    # transfer_progress updates the blocks/bytes label.
    win = MainWindow(state)
    try:
        win._on_transfer_started("FOO.TXT", 256, "remote")
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
        win._on_transfer_started("BAR.TXT", 0, "host")
        assert win._transfer_dialog is not None
        assert win._transfer_dialog.windowTitle() == "Receiving File"
    finally:
        win.close()


def test_progress_dialog_closes_on_completion(qapp, monkeypatch, state):
    # FR-105: a successful transfer auto-closes the progress dialog.
    win = MainWindow(state)
    try:
        monkeypatch.setattr(win, "refresh_remote_files", lambda: None)
        win._on_transfer_started("FOO.TXT", 128, "remote")
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
        win._on_transfer_started("FOO.TXT", 128, "remote")
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
        win._transfer_to_remote(os.path.join(win.host_dir, "FOO.TXT"))
        qapp.processEvents()
        assert win._transfer_dialog is None
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
