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
from cpm_fm.gui.about_dialog import AboutDialog  # noqa: E402
from cpm_fm.gui.terminal_window import TerminalWindow  # noqa: E402
from cpm_fm.gui.window_state import WindowState  # noqa: E402
from cpm_fm.utils import i18n  # noqa: E402
from cpm_fm.utils.config_handler import DEFAULT_SETTINGS  # noqa: E402
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
        assert win.statusBar().currentMessage() == "Terminal port not open - cannot rename"
    finally:
        win.close()


def test_do_remote_file_cmd_refreshes_remote_list(qapp, monkeypatch, state):
    # FR-118: after sending the command the remote list is refreshed.
    win = MainWindow(state)
    try:
        captured = []
        monkeypatch.setattr(win, "_capture_terminal_response", lambda c: captured.append(c) or "")
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


def _arm_transfer_with_xmodem(win, monkeypatch, xmodem_cls):
    # Like _arm_transfer but with a caller-supplied XModem stub (so the test can
    # trigger cancellation from inside send_file/receive_file).
    win.settings = {"xfer_launch_delay": 0}
    win.serial_mgr.terminal_connected = True
    win.serial_mgr.transport_connected = True
    win.serial_mgr.transport_port = _FakeSerial()
    monkeypatch.setattr(win.serial_mgr, "send_data", lambda *a, **k: None)
    monkeypatch.setattr("cpm_fm.app.XModem", xmodem_cls)
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

            def send_file(self, path):
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

            def send_file(self, path):
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
    # (List Files, Receive/Send, Rename, Delete) into a "Remote" group placed
    # first, with Rename/Delete labelled without the "Remote" suffix.
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
        # Its rows hold exactly the five remote command fields, in order.
        form = first.layout()
        labels = [
            form.itemAt(i, QFormLayout.ItemRole.LabelRole).widget().text()
            for i in range(form.rowCount())
        ]
        assert labels == ["List Files", "Receive from Remote", "Send to Remote", "Rename", "Delete"]
        # The non-remote settings remain reachable for saving (e.g. EOL).
        assert "eol" in dlg.entries and "host_directory" in dlg.entries
    finally:
        dlg.deleteLater()


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
        # The window title comes from app.title via the i18n registry.
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
