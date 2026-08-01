"""Target-free whole-drive Backup / Restore workflows (MT-BR*).

These tests drive the real ``MainWindow`` while replacing only external or
potentially destructive boundaries.  They provide deterministic CI evidence;
manual cases retain physical CP/M and operator-observation evidence.
"""

from __future__ import annotations

import threading
import time

import pytest

from cpm_fm.utils import i18n


@pytest.mark.gui_integration
@pytest.mark.mt("MT-BR01", "FR-150", "FR-152", "UIR-088")
def test_backup_refreshes_both_panes_before_real_confirmation(
    gui_no_target, monkeypatch, tmp_path, qapp
):
    """Backup refreshes both panes before showing its safe-default warning.

    Verifies: FR-150, FR-152, UIR-088.
    """
    from PySide6.QtCore import QThread
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QDialog, QLabel, QPushButton

    win = gui_no_target
    win.serial_mgr.terminal_connected = True
    win.serial_mgr.transport_connected = True
    win.settings["list_files_cmd"] = "DIR"

    host_dir = tmp_path / "host"
    host_dir.mkdir()
    host_payload = {
        "HOST1.TXT": b"host one\r\n",
        "HOST2.DAT": b"host two\r\n",
    }
    for name, data in host_payload.items():
        (host_dir / name).write_bytes(data)
    win.host_dir = str(host_dir)
    win.host_list.clear()
    win.host_list.addItem("STALE.HST")
    win.remote_list.clear()
    win.remote_list.addItem("STALE.REM")

    captures: list[str] = []

    def capture(command, **kwargs):
        captures.append(command)
        return "A: REMOTE1 TXT : REMOTE2 COM\r\nA>"

    monkeypatch.setattr(win, "_capture_terminal_response", capture)
    destructive_calls: list[str] = []
    monkeypatch.setattr(
        win,
        "_wipe_host_dir",
        lambda names: destructive_calls.append("wipe"),
    )
    monkeypatch.setattr(
        win,
        "_transfer_to_host_batch",
        lambda paths: destructive_calls.append("transfer"),
    )

    inspection: dict[str, object] = {}

    def inspect_and_cancel(dialog):
        labels = [label.text() for label in dialog.findChildren(QLabel) if label.text()]
        row = dialog.layout().itemAt(dialog.layout().count() - 1).layout()
        buttons = [
            row.itemAt(index).widget()
            for index in range(row.count())
            if isinstance(row.itemAt(index).widget(), QPushButton)
        ]
        inspection.update(
            gui_thread=QThread.currentThread() == qapp.thread(),
            modal=dialog.isModal(),
            title=dialog.windowTitle(),
            labels=labels,
            buttons=[button.text() for button in buttons],
            default_buttons=[button.text() for button in buttons if button.isDefault()],
            host_names=[win.host_list.item(i).text() for i in range(win.host_list.count())],
            remote_names=[win.remote_list.item(i).text() for i in range(win.remote_list.count())],
            host_bytes={name: (host_dir / name).read_bytes() for name in host_payload},
        )
        return int(QDialog.DialogCode.Rejected)

    monkeypatch.setattr("cpm_fm.app.QDialog.exec", inspect_and_cancel)
    statuses: list[str] = []
    win.status_changed.connect(statuses.append)

    backup_action = next(
        action for action in win.findChildren(QAction) if action.text() == i18n.tr("toolbar.backup")
    )
    backup_action.trigger()

    cancelled = i18n.tr("status.backup_restore_cancelled")
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline and cancelled not in statuses:
        qapp.processEvents()
        time.sleep(0.01)
    qapp.processEvents()

    assert captures == ["DIR"]
    assert inspection == {
        "gui_thread": True,
        "modal": True,
        "title": i18n.tr("dialog.backup_restore.backup_title"),
        "labels": [i18n.tr("dialog.backup_restore.backup")],
        "buttons": [i18n.tr("button.cancel"), i18n.tr("button.continue")],
        "default_buttons": [i18n.tr("button.cancel")],
        "host_names": ["HOST1.TXT", "HOST2.DAT"],
        "remote_names": ["REMOTE1.TXT", "REMOTE2.COM"],
        "host_bytes": host_payload,
    }
    assert statuses[-1] == cancelled
    assert destructive_calls == []
    assert {name: (host_dir / name).read_bytes() for name in host_payload} == host_payload


@pytest.mark.gui_integration
@pytest.mark.mt("MT-BR02", "FR-152")
@pytest.mark.parametrize("dismissal", ["cancel-button", "window-close"])
def test_backup_rejection_preserves_host_and_terminates_worker(
    gui_no_target, monkeypatch, tmp_path, qapp, dismissal
):
    """Cancel and window-close both abort Backup without changing the host.

    Verifies: FR-152.
    """
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QDialog, QPushButton

    win = gui_no_target
    win.serial_mgr.terminal_connected = True
    win.serial_mgr.transport_connected = True
    win.settings["list_files_cmd"] = "DIR"

    host_dir = tmp_path / "host"
    host_dir.mkdir()
    host_payload = {
        "KEEP1.TXT": b"keep one\x00\xff",
        "KEEP2.COM": b"keep two\r\n",
    }
    for name, data in host_payload.items():
        (host_dir / name).write_bytes(data)
    win.host_dir = str(host_dir)

    monkeypatch.setattr(
        win,
        "_capture_terminal_response",
        lambda command, **kwargs: "A: SOURCE TXT\r\nA>",
    )
    destructive_calls: list[str] = []
    monkeypatch.setattr(
        win,
        "_wipe_host_dir",
        lambda names: destructive_calls.append("wipe"),
    )
    monkeypatch.setattr(
        win,
        "_transfer_to_host_batch",
        lambda paths: destructive_calls.append("transfer"),
    )

    dialog_results: list[QDialog.DialogCode] = []

    def reject_dialog(dialog):
        dialog.show()
        qapp.processEvents()
        if dismissal == "cancel-button":
            cancel = next(
                button
                for button in dialog.findChildren(QPushButton)
                if button.text() == i18n.tr("button.cancel")
            )
            cancel.click()
        else:
            dialog.close()
        dialog_results.append(QDialog.DialogCode(dialog.result()))
        return dialog.result()

    monkeypatch.setattr("cpm_fm.app.QDialog.exec", reject_dialog)
    statuses: list[str] = []
    win.status_changed.connect(statuses.append)

    backup_action = next(
        action for action in win.findChildren(QAction) if action.text() == i18n.tr("toolbar.backup")
    )
    backup_action.trigger()

    cancelled = i18n.tr("status.backup_restore_cancelled")
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline and cancelled not in statuses:
        qapp.processEvents()
        time.sleep(0.01)
    qapp.processEvents()

    backup_workers = [
        worker.name for worker in threading.enumerate() if "_backup_drive" in worker.name
    ]
    assert dialog_results == [QDialog.DialogCode.Rejected]
    assert statuses[-1] == cancelled
    assert destructive_calls == []
    assert {name: (host_dir / name).read_bytes() for name in host_payload} == host_payload
    assert sorted(path.name for path in host_dir.iterdir()) == sorted(host_payload)
    assert backup_workers == []


@pytest.mark.gui_integration
@pytest.mark.mt("MT-BR04", "FR-151", "FR-152", "UIR-088")
def test_restore_refreshes_remote_before_confirmation_and_cancel_preserves_it(
    gui_no_target, monkeypatch, tmp_path, qapp
):
    """Restore refreshes its destination before a safe-default confirmation.

    Verifies: FR-151, FR-152, UIR-088.
    """
    from PySide6.QtCore import QThread
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QLabel, QPushButton

    win = gui_no_target
    win.serial_mgr.terminal_connected = True
    win.serial_mgr.transport_connected = True
    win.settings["list_files_cmd"] = "DIR"

    host_dir = tmp_path / "host"
    host_dir.mkdir()
    (host_dir / "UPLOAD1.TXT").write_bytes(b"upload one\r\n")
    (host_dir / "UPLOAD2.COM").write_bytes(b"upload two\r\n")
    win.host_dir = str(host_dir)
    win.remote_list.clear()
    win.remote_list.addItem("STALE.REM")

    captures: list[str] = []

    def capture(command, **kwargs):
        captures.append(command)
        return "B: KEEP1 TXT : KEEP2 COM\r\nB>"

    monkeypatch.setattr(win, "_capture_terminal_response", capture)
    destructive_calls: list[str] = []
    monkeypatch.setattr(
        win,
        "_wipe_remote_drive",
        lambda names: destructive_calls.append("wipe"),
    )
    monkeypatch.setattr(
        win,
        "_transfer_to_remote_batch",
        lambda paths: destructive_calls.append("transfer"),
    )

    inspection: dict[str, object] = {}

    def inspect_and_cancel(dialog):
        labels = [label.text() for label in dialog.findChildren(QLabel) if label.text()]
        row = dialog.layout().itemAt(dialog.layout().count() - 1).layout()
        buttons = [
            row.itemAt(index).widget()
            for index in range(row.count())
            if isinstance(row.itemAt(index).widget(), QPushButton)
        ]
        inspection.update(
            gui_thread=QThread.currentThread() == qapp.thread(),
            modal=dialog.isModal(),
            title=dialog.windowTitle(),
            labels=labels,
            buttons=[button.text() for button in buttons],
            default_buttons=[button.text() for button in buttons if button.isDefault()],
            remote_names=[win.remote_list.item(i).text() for i in range(win.remote_list.count())],
        )
        cancel = next(button for button in buttons if button.text() == i18n.tr("button.cancel"))
        cancel.click()
        return dialog.result()

    monkeypatch.setattr("cpm_fm.app.QDialog.exec", inspect_and_cancel)
    statuses: list[str] = []
    win.status_changed.connect(statuses.append)

    restore_action = next(
        action
        for action in win.findChildren(QAction)
        if action.text() == i18n.tr("toolbar.restore")
    )
    restore_action.trigger()

    cancelled = i18n.tr("status.backup_restore_cancelled")
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline and cancelled not in statuses:
        qapp.processEvents()
        time.sleep(0.01)
    qapp.processEvents()

    restore_workers = [
        worker.name for worker in threading.enumerate() if "_restore_drive" in worker.name
    ]
    assert captures == ["DIR"]
    assert inspection == {
        "gui_thread": True,
        "modal": True,
        "title": i18n.tr("dialog.backup_restore.restore_title"),
        "labels": [i18n.tr("dialog.backup_restore.restore")],
        "buttons": [i18n.tr("button.cancel"), i18n.tr("button.continue")],
        "default_buttons": [i18n.tr("button.cancel")],
        "remote_names": ["KEEP1.TXT", "KEEP2.COM"],
    }
    assert statuses[-1] == cancelled
    assert destructive_calls == []
    assert [win.remote_list.item(i).text() for i in range(win.remote_list.count())] == [
        "KEEP1.TXT",
        "KEEP2.COM",
    ]
    assert restore_workers == []


@pytest.mark.gui_integration
@pytest.mark.mt("MT-BR06", "FR-154", "FR-120")
def test_restore_progress_cancel_stops_remaining_batch_without_error(
    gui_no_target, monkeypatch, tmp_path, qapp
):
    """Cancelling Restore's real progress dialog stops the remaining uploads.

    Verifies: FR-154, FR-120.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QAction
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QPushButton

    win = gui_no_target
    win.serial_mgr.terminal_connected = True
    win.serial_mgr.transport_connected = True
    win.settings["list_files_cmd"] = "DIR"

    host_dir = tmp_path / "host"
    host_dir.mkdir()
    source_names = ["ONE.TXT", "TWO.TXT", "THREE.TXT"]
    for index, name in enumerate(source_names, start=1):
        (host_dir / name).write_bytes(bytes([index]) * 256)
    win.host_dir = str(host_dir)

    monkeypatch.setattr(
        win,
        "_capture_terminal_response",
        lambda command, **kwargs: "B: OLD1 TXT : OLD2 COM\r\nB>",
    )
    events: list[str] = []
    wiped_names: list[str] = []

    def record_wipe(names):
        events.append("wipe")
        wiped_names.extend(names)

    monkeypatch.setattr(win, "_wipe_remote_drive", record_wipe)
    monkeypatch.setattr(win, "_fresh_remote_names", lambda: set())

    send_started = threading.Event()
    send_attempts: list[str] = []

    def cancellable_send(filepath, remote_name, user_area=None):
        events.append(f"send:{remote_name}")
        send_attempts.append(remote_name)
        send_started.set()
        if not win._transfer_cancel.wait(timeout=5.0):
            raise TimeoutError("Cancel was not delivered to the active Restore transfer")
        return False

    monkeypatch.setattr(win, "_send_one_to_remote", cancellable_send)

    def accept_restore(dialog):
        proceed = next(
            button
            for button in dialog.findChildren(QPushButton)
            if button.text() == i18n.tr("button.continue")
        )
        proceed.click()
        return dialog.result()

    monkeypatch.setattr("cpm_fm.app.QDialog.exec", accept_restore)
    message_boxes: list[tuple[str, str, str]] = []
    for kind in ("critical", "warning", "information"):
        monkeypatch.setattr(
            f"cpm_fm.app.QMessageBox.{kind}",
            lambda parent, title, message, _kind=kind: message_boxes.append(
                (_kind, title, message)
            ),
        )
    statuses: list[str] = []
    win.status_changed.connect(statuses.append)

    restore_action = next(
        action
        for action in win.findChildren(QAction)
        if action.text() == i18n.tr("toolbar.restore")
    )
    restore_action.trigger()

    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        qapp.processEvents()
        if win._transfer_dialog is not None and send_started.is_set():
            break
        time.sleep(0.01)
    dialog = win._transfer_dialog
    assert dialog is not None, "Restore did not create its batch progress dialog"
    assert send_started.is_set(), "Restore did not enter its first file transfer"
    assert dialog._file_count == 3
    assert dialog.batch_label.text() == i18n.tr("transfer.batch_position", index=1, count=3)

    QTest.mouseClick(dialog.cancel_button, Qt.MouseButton.LeftButton)
    assert dialog.cancel_button.isEnabled() is False
    assert dialog.cancel_button.text() == i18n.tr("button.cancelling")

    cancelled = i18n.tr("status.transfer_cancelled", count=0)
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        qapp.processEvents()
        if win._transfer_dialog is None and cancelled in statuses:
            break
        time.sleep(0.01)
    qapp.processEvents()

    active_workers = [
        worker.name
        for worker in threading.enumerate()
        if "_restore_drive" in worker.name or "_transfer_to_remote_batch" in worker.name
    ]
    assert wiped_names == ["OLD1.TXT", "OLD2.COM"]
    assert events[0] == "wipe"
    assert len(send_attempts) == 1
    assert send_attempts[0] in source_names
    assert events == ["wipe", f"send:{send_attempts[0]}"]
    assert statuses[-1] == cancelled
    assert win._transfer_dialog is None
    assert message_boxes == []
    assert active_workers == []


@pytest.mark.gui_integration
@pytest.mark.mt("MT-BR07", "FR-151", "FR-148", "FR-149")
@pytest.mark.parametrize("choice", ["rename", "skip", "cancel"])
def test_restore_invalid_filename_uses_real_validation_actions(
    gui_no_target, monkeypatch, tmp_path, qapp, choice
):
    """Restore routes an invalid host name through Rename, Skip, and Cancel.

    Verifies: FR-151, FR-148, FR-149.
    """
    from PySide6.QtCore import Qt, QThread
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QLabel, QLineEdit, QPushButton

    from cpm_fm.gui.filename_validation_dialog import FilenameValidationDialog
    from cpm_fm.terminal.cpm_parser import CPMParser

    win = gui_no_target
    win.serial_mgr.terminal_connected = True
    win.serial_mgr.transport_connected = True
    win.settings["list_files_cmd"] = "DIR"

    host_dir = tmp_path / "host"
    host_dir.mkdir()
    invalid_name = "bad name.txt"
    valid_name = "GOOD.TXT"
    (host_dir / invalid_name).write_bytes(b"invalid source name\r\n")
    (host_dir / valid_name).write_bytes(b"valid source name\r\n")
    win.host_dir = str(host_dir)
    monkeypatch.setattr(win, "_host_dir_files", lambda: [invalid_name, valid_name])

    monkeypatch.setattr(
        win,
        "_capture_terminal_response",
        lambda command, **kwargs: "B: OLD TXT\r\nB>",
    )
    wiped_names: list[str] = []
    monkeypatch.setattr(win, "_wipe_remote_drive", lambda names: wiped_names.extend(names))
    monkeypatch.setattr(win, "_fresh_remote_names", lambda: set())
    monkeypatch.setattr(win, "_wait_for_terminal_idle", lambda: None)
    monkeypatch.setattr(win, "refresh_remote_files", lambda: None)

    send_attempts: list[tuple[str, str]] = []

    def successful_send(filepath, remote_name, user_area=None):
        send_attempts.append((filepath, remote_name))
        return True

    monkeypatch.setattr(win, "_send_one_to_remote", successful_send)

    validation_inspections: list[dict[str, object]] = []

    def answer_dialog(dialog):
        if not isinstance(dialog, FilenameValidationDialog):
            proceed = next(
                button
                for button in dialog.findChildren(QPushButton)
                if button.text() == i18n.tr("button.continue")
            )
            proceed.click()
            return dialog.result()

        row = dialog.layout().itemAt(dialog.layout().count() - 1).layout()
        buttons = [
            row.itemAt(index).widget()
            for index in range(row.count())
            if isinstance(row.itemAt(index).widget(), QPushButton)
        ]
        name_edit = dialog.findChild(QLineEdit)
        labels = [label.text() for label in dialog.findChildren(QLabel) if label.text()]
        validation_inspections.append(
            {
                "gui_thread": QThread.currentThread() == qapp.thread(),
                "modal": dialog.isModal(),
                "title": dialog.windowTitle(),
                "labels": labels,
                "suggestion": name_edit.text(),
                "buttons": [button.text() for button in buttons],
                "close_button": bool(dialog.windowFlags() & Qt.WindowType.WindowCloseButtonHint),
            }
        )
        if choice == "rename":
            name_edit.setText("RENAMED.TXT")
            button_text = i18n.tr("dialog.invalid_name.rename")
        else:
            button_text = i18n.tr(f"dialog.invalid_name.{choice}")
        next(button for button in buttons if button.text() == button_text).click()
        return dialog.result()

    monkeypatch.setattr("cpm_fm.app.QDialog.exec", answer_dialog)
    message_boxes: list[tuple[str, str, str]] = []
    for kind in ("critical", "warning", "information"):
        monkeypatch.setattr(
            f"cpm_fm.app.QMessageBox.{kind}",
            lambda parent, title, message, _kind=kind: message_boxes.append(
                (_kind, title, message)
            ),
        )
    statuses: list[str] = []
    win.status_changed.connect(statuses.append)

    restore_action = next(
        action
        for action in win.findChildren(QAction)
        if action.text() == i18n.tr("toolbar.restore")
    )
    restore_action.trigger()

    expected_count = 0 if choice == "cancel" else (2 if choice == "rename" else 1)
    final_status = (
        i18n.tr("status.transfer_cancelled", count=0)
        if choice == "cancel"
        else i18n.tr("status.successfully_uploaded", count=expected_count)
    )
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        qapp.processEvents()
        if win._transfer_dialog is None and final_status in statuses:
            break
        time.sleep(0.01)
    qapp.processEvents()

    active_workers = [
        worker.name
        for worker in threading.enumerate()
        if "_restore_drive" in worker.name or "_transfer_to_remote_batch" in worker.name
    ]
    suggestion = CPMParser.suggest_8_3(invalid_name)
    assert validation_inspections == [
        {
            "gui_thread": True,
            "modal": True,
            "title": i18n.tr("dialog.invalid_name.title"),
            "labels": [i18n.tr("dialog.invalid_name.message", name=invalid_name)],
            "suggestion": suggestion,
            "buttons": [
                i18n.tr("dialog.invalid_name.cancel"),
                i18n.tr("dialog.invalid_name.skip"),
                i18n.tr("dialog.invalid_name.rename"),
            ],
            "close_button": False,
        }
    ]
    assert CPMParser.is_valid_8_3(suggestion) is True
    assert wiped_names == ["OLD.TXT"]
    expected_remote_names = {
        "rename": ["RENAMED.TXT", valid_name],
        "skip": [valid_name],
        "cancel": [],
    }[choice]
    assert [remote_name for _, remote_name in send_attempts] == expected_remote_names

    history = [(entry["filename"], entry["status"]) for entry in win.transfer_history.get_entries()]
    expected_history = {
        "rename": [("RENAMED.TXT", "success"), (valid_name, "success")],
        "skip": [(invalid_name, "skipped"), (valid_name, "success")],
        "cancel": [],
    }[choice]
    assert history == expected_history
    assert statuses[-1] == final_status
    assert win._transfer_dialog is None
    assert message_boxes == []
    assert active_workers == []


@pytest.mark.gui_integration
@pytest.mark.mt("MT-BR08", "FR-080", "CR-010")
@pytest.mark.parametrize("action", ["do_backup", "do_restore"])
@pytest.mark.parametrize(
    ("terminal_connected", "transport_connected"),
    [(False, True), (True, False)],
    ids=["terminal-disconnected", "transport-disconnected"],
)
def test_disconnected_port_blocks_backup_and_restore_before_any_action(
    gui_no_target,
    monkeypatch,
    tmp_path,
    action,
    terminal_connected,
    transport_connected,
):
    """Either disconnected port blocks Backup/Restore before work begins.

    Verifies: FR-080, CR-010.
    """
    win = gui_no_target
    win.serial_mgr.terminal_connected = terminal_connected
    win.serial_mgr.transport_connected = transport_connected

    host_dir = tmp_path / "host"
    host_dir.mkdir()
    sentinel = host_dir / "KEEP.TXT"
    sentinel.write_bytes(b"must remain unchanged\r\n")
    win.host_dir = str(host_dir)
    win.remote_list.addItems(["KEEP.COM"])

    errors: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "cpm_fm.gui.mw_backup_restore.QMessageBox.critical",
        lambda parent, title, message: errors.append((title, message)),
    )

    class UnexpectedWorker:
        def __init__(self, *args, **kwargs):
            pytest.fail(f"{action} started a worker while a port was disconnected")

    monkeypatch.setattr("cpm_fm.gui.mw_backup_restore.threading.Thread", UnexpectedWorker)

    getattr(win, action)()

    assert errors == [(i18n.tr("dialog.error.title"), i18n.tr("error.transport_not_connected"))]
    assert sentinel.read_bytes() == b"must remain unchanged\r\n"
    assert [win.remote_list.item(i).text() for i in range(win.remote_list.count())] == ["KEEP.COM"]
