"""Tests for the whole-drive Backup and Restore feature (FR-150–FR-154).

These cover the worker orchestration (refresh → confirm → wipe → transfer
ordering, and the cancel/empty short-circuits), the destination-wipe helpers,
the connection guard, and the GUI-thread confirmation slot — all without real
serial hardware or worker threads.

Satisfies: FR-150, FR-151, FR-152, FR-153, FR-154, UIR-086, UIR-087, UIR-088.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from cpm_fm.app import MainWindow  # noqa: E402
from cpm_fm.gui.window_state import WindowState  # noqa: E402
from cpm_fm.utils import i18n  # noqa: E402


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


def _arm(win, monkeypatch, tmp_path):
    """Mark both ports connected and isolate the window from real I/O."""
    win.settings = {"delete_remote_cmd": "ERA $1", "list_files_cmd": "DIR"}
    win.serial_mgr.terminal_connected = True
    win.serial_mgr.transport_connected = True
    win.host_dir = str(tmp_path)
    monkeypatch.setattr(win, "refresh_host_files", lambda: None)
    monkeypatch.setattr(win, "refresh_remote_files", lambda: None)


# ------------------------------------------------------ orchestration (FR-150)


def test_backup_order_refresh_confirm_wipe_transfer(qapp, monkeypatch, state, tmp_path):
    # FR-150/FR-152/FR-153/FR-154: the destination is refreshed and confirmed
    # before the wipe, and the wipe happens before the transfer.
    win = MainWindow(state)
    try:
        _arm(win, monkeypatch, tmp_path)
        order = []
        sent_paths = []
        monkeypatch.setattr(
            win, "_list_remote_file_names", lambda: order.append("refresh") or ["A.TXT", "B.TXT"]
        )
        monkeypatch.setattr(
            win, "_confirm_backup_restore", lambda op: order.append("confirm") or True
        )
        monkeypatch.setattr(win, "_wipe_host_dir", lambda names: order.append("wipe"))
        monkeypatch.setattr(
            win,
            "_transfer_to_host_batch",
            lambda paths: (order.append("transfer"), sent_paths.extend(paths)),
        )
        win._backup_drive()
        assert order == ["refresh", "confirm", "wipe", "transfer"]
        assert sent_paths == [
            os.path.join(str(tmp_path), "A.TXT"),
            os.path.join(str(tmp_path), "B.TXT"),
        ]
    finally:
        win.close()


def test_backup_cancel_stops_before_wipe(qapp, monkeypatch, state, tmp_path):
    # FR-152: Cancel aborts before any deletion or transfer.
    win = MainWindow(state)
    try:
        _arm(win, monkeypatch, tmp_path)
        order = []
        monkeypatch.setattr(win, "_list_remote_file_names", lambda: ["A.TXT"])
        monkeypatch.setattr(win, "_confirm_backup_restore", lambda op: False)
        monkeypatch.setattr(win, "_wipe_host_dir", lambda names: order.append("wipe"))
        monkeypatch.setattr(win, "_transfer_to_host_batch", lambda paths: order.append("transfer"))
        win._backup_drive()
        assert order == []
    finally:
        win.close()


def test_backup_empty_source_wipes_but_skips_transfer(qapp, monkeypatch, state, tmp_path):
    # FR-154: an empty source still wipes the destination but transfers nothing.
    win = MainWindow(state)
    try:
        _arm(win, monkeypatch, tmp_path)
        order = []
        monkeypatch.setattr(win, "_list_remote_file_names", lambda: [])
        monkeypatch.setattr(win, "_confirm_backup_restore", lambda op: True)
        monkeypatch.setattr(win, "_wipe_host_dir", lambda names: order.append("wipe"))
        monkeypatch.setattr(win, "_transfer_to_host_batch", lambda paths: order.append("transfer"))
        win._backup_drive()
        assert order == ["wipe"]
    finally:
        win.close()


# ------------------------------------------------------ orchestration (FR-151)


def test_restore_order_refresh_confirm_wipe_transfer(qapp, monkeypatch, state, tmp_path):
    # FR-151/FR-152/FR-153/FR-154: refresh + confirm before wipe; wipe before transfer.
    win = MainWindow(state)
    try:
        _arm(win, monkeypatch, tmp_path)
        order = []
        wiped = []
        sent_paths = []
        monkeypatch.setattr(win, "_host_dir_files", lambda: ["X.TXT"])
        monkeypatch.setattr(
            win, "_list_remote_file_names", lambda: order.append("refresh") or ["OLD.TXT"]
        )
        monkeypatch.setattr(
            win, "_confirm_backup_restore", lambda op: order.append("confirm") or True
        )
        monkeypatch.setattr(
            win, "_wipe_remote_drive", lambda names: (order.append("wipe"), wiped.extend(names))
        )
        monkeypatch.setattr(
            win,
            "_transfer_to_remote_batch",
            lambda paths: (order.append("transfer"), sent_paths.extend(paths)),
        )
        win._restore_drive()
        assert order == ["refresh", "confirm", "wipe", "transfer"]
        assert wiped == ["OLD.TXT"]
        assert sent_paths == [os.path.join(str(tmp_path), "X.TXT")]
    finally:
        win.close()


def test_restore_cancel_stops_before_wipe(qapp, monkeypatch, state, tmp_path):
    # FR-152: Cancel aborts before any deletion or transfer.
    win = MainWindow(state)
    try:
        _arm(win, monkeypatch, tmp_path)
        order = []
        monkeypatch.setattr(win, "_host_dir_files", lambda: ["X.TXT"])
        monkeypatch.setattr(win, "_list_remote_file_names", lambda: ["OLD.TXT"])
        monkeypatch.setattr(win, "_confirm_backup_restore", lambda op: False)
        monkeypatch.setattr(win, "_wipe_remote_drive", lambda names: order.append("wipe"))
        monkeypatch.setattr(
            win, "_transfer_to_remote_batch", lambda paths: order.append("transfer")
        )
        win._restore_drive()
        assert order == []
    finally:
        win.close()


# ------------------------------------------------------------- wipe helpers


def test_wipe_host_dir_removes_all_files(qapp, monkeypatch, state, tmp_path):
    # FR-153: every regular file in the host directory is deleted.
    win = MainWindow(state)
    try:
        _arm(win, monkeypatch, tmp_path)
        for name in ("A.TXT", "B.DAT", "C"):
            (tmp_path / name).write_text("x", encoding="utf-8")
        win._wipe_host_dir(win._host_dir_files())
        assert os.listdir(str(tmp_path)) == []
    finally:
        win.close()


def test_wipe_host_dir_preserves_subdirectories(qapp, monkeypatch, state, tmp_path):
    # FR-153: subdirectories within the host directory are NOT removed.
    win = MainWindow(state)
    try:
        _arm(win, monkeypatch, tmp_path)
        (tmp_path / "FILE.TXT").write_text("x", encoding="utf-8")
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "nested.txt").write_text("y", encoding="utf-8")
        win._wipe_host_dir(win._host_dir_files())
        remaining = os.listdir(str(tmp_path))
        assert "FILE.TXT" not in remaining
        assert "subdir" in remaining
    finally:
        win.close()


def test_wipe_remote_drive_issues_delete_per_file(qapp, monkeypatch, state, tmp_path):
    # FR-153: one configured delete command is sent per remote file.
    win = MainWindow(state)
    try:
        _arm(win, monkeypatch, tmp_path)
        cmds = []
        monkeypatch.setattr(win, "_capture_terminal_response", lambda cmd: cmds.append(cmd) or "")
        win._wipe_remote_drive(["A.TXT", "B.COM"])
        assert cmds == ["ERA A.TXT", "ERA B.COM"]
    finally:
        win.close()


# ------------------------------------------------------- connection guard


def test_do_backup_requires_connection(qapp, monkeypatch, state, tmp_path):
    # FR-080/CR-010: with no connection, no worker thread is started.
    win = MainWindow(state)
    try:
        win.serial_mgr.terminal_connected = False
        win.serial_mgr.transport_connected = False
        started = []
        monkeypatch.setattr("cpm_fm.app.QMessageBox.critical", lambda *a, **k: None)
        monkeypatch.setattr(
            "cpm_fm.app.threading.Thread",
            lambda *a, **k: started.append((a, k)),
        )
        win.do_backup()
        win.do_restore()
        assert started == []
    finally:
        win.close()


# ------------------------------------------------------ confirmation slot (UIR-088)


class _FakeBox:
    Icon = QMessageBox.Icon
    ButtonRole = QMessageBox.ButtonRole
    # The test sets which button the user "clicks": "continue", "cancel", or
    # "close" (window-manager close, which returns no clicked button).
    choice = "continue"

    def __init__(self, parent):
        self._buttons = []
        self._clicked = None

    def setIcon(self, icon):
        pass

    def setWindowTitle(self, title):
        pass

    def setText(self, text):
        pass

    def addButton(self, text, role):
        btn = object()
        self._buttons.append((role, btn))
        return btn

    def setDefaultButton(self, btn):
        pass

    def exec(self):
        if _FakeBox.choice == "continue":
            self._clicked = self._buttons[0][1]
        elif _FakeBox.choice == "cancel":
            self._clicked = self._buttons[1][1]
        else:  # window-manager close
            self._clicked = None
        return 0

    def clickedButton(self):
        return self._clicked


@pytest.mark.parametrize(
    "choice,expected",
    [("continue", True), ("cancel", False), ("close", False)],
)
def test_on_backup_restore_confirm_records_choice(qapp, monkeypatch, state, choice, expected):
    # FR-152/UIR-088: Continue => True; Cancel and a window-manager close => False.
    # The worker is released by the answered event in every case.
    win = MainWindow(state)
    try:
        _FakeBox.choice = choice
        monkeypatch.setattr("cpm_fm.app.QMessageBox", _FakeBox)
        win._backup_confirm_answered.clear()
        win._on_backup_restore_confirm("backup")
        assert win._backup_confirm_result is expected
        assert win._backup_confirm_answered.is_set()
    finally:
        win.close()
