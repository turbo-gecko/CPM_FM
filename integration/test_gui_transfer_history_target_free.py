"""Target-free real-widget Transfer History workflows."""

from __future__ import annotations

import pytest

_PROBE_PREFIX = "__CPM_FM_HISTORY_PROBE__="


def _action(win, key: str):
    """Return the translated QAction registered for ``key``."""
    from PySide6.QtGui import QAction

    from cpm_fm.utils.i18n import tr

    text = tr(key)
    return next(action for action in win.findChildren(QAction) if action.text() == text)


def _select_data(combo, value: str) -> None:
    """Select ``value`` in a real combo box using keyboard interaction."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    index = combo.findData(value)
    assert index >= 0
    combo.setFocus()
    QTest.keyClick(combo, Qt.Key.Key_Home)
    for _ in range(index):
        QTest.keyClick(combo, Qt.Key.Key_Down)
    assert combo.currentData() == value


def _visible_filenames(dialog) -> list[str]:
    """Return the filenames currently rendered in the history table."""
    return [dialog._table.item(row, 1).text() for row in range(dialog._table.rowCount())]


def _run_history_process_probe(mode: str, history_path: str, state_path: str) -> None:
    """Record or render history in a standalone offscreen application process."""
    import json

    from PySide6.QtCore import QSettings, Qt
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QApplication

    from cpm_fm.app import MainWindow
    from cpm_fm.gui.window_state import WindowState
    from cpm_fm.utils import i18n
    from cpm_fm.utils.transfer_history import TransferHistory

    i18n.set_language(i18n.DEFAULT_LANGUAGE)
    app = QApplication.instance() or QApplication([])
    state = WindowState(QSettings(state_path, QSettings.Format.IniFormat))
    history = TransferHistory(history_path)
    win = MainWindow(state, history)
    payload: dict[str, object]

    if mode == "record":
        win._record_history(
            "PERSIST.TXT",
            "C:/HOST/PERSIST.TXT",
            "remote",
            "success",
            321,
            "",
            False,
        )
        payload = {"entries": history.get_entries()}
    elif mode == "read":
        win.show()
        app.processEvents()
        history_text = i18n.tr("toolbar.history")
        action = next(
            action for action in win.findChildren(QAction) if action.text() == history_text
        )
        action.trigger()
        app.processEvents()
        dialog = win._history_dialog
        assert dialog is not None
        row_count = dialog._table.rowCount()
        first_item = dialog._table.item(0, 0)
        payload = {
            "row_count": row_count,
            "filename": dialog._table.item(0, 1).text() if row_count else None,
            "size": dialog._table.item(0, 4).text() if row_count else None,
            "entry": first_item.data(Qt.ItemDataRole.UserRole) if first_item else None,
        }
        dialog.close()
    else:  # pragma: no cover - guarded by the parent test
        raise ValueError(f"unknown probe mode: {mode}")

    win.close()
    app.processEvents()
    print(_PROBE_PREFIX + json.dumps(payload, sort_keys=True))


@pytest.mark.gui_integration
@pytest.mark.mt("MT-TH02", "FR-143", "UIR-083")
def test_history_direction_and_status_filters_compose_and_all_restores_every_row(
    gui_no_target, qapp
):
    """Every direction/status option filters the real dialog, including Skipped.

    Verifies: FR-143, UIR-083.
    """
    win = gui_no_target
    directions = ("remote", "host")
    statuses = ("success", "failure", "cancelled", "skipped")
    expected: dict[tuple[str, str], str] = {}

    for direction in directions:
        for status in statuses:
            filename = f"{direction.upper()}_{status.upper()}.TXT"
            expected[direction, status] = filename
            win.transfer_history.add_entry(
                filename=filename,
                path=f"/history/{filename}",
                direction=direction,
                status=status,
            )

    win.show()
    qapp.processEvents()
    _action(win, "toolbar.history").trigger()
    qapp.processEvents()

    dialog = win._history_dialog
    assert dialog is not None
    assert dialog.isVisible()
    assert dialog._direction_filter.currentData() == ""
    assert dialog._status_filter.currentData() == ""
    all_newest_first = list(reversed(list(expected.values())))
    assert _visible_filenames(dialog) == all_newest_first

    for direction in directions:
        _select_data(dialog._direction_filter, direction)
        assert _visible_filenames(dialog) == [
            expected[direction, status] for status in reversed(statuses)
        ]

    _select_data(dialog._direction_filter, "")
    for status in statuses:
        _select_data(dialog._status_filter, status)
        assert _visible_filenames(dialog) == [
            expected[direction, status] for direction in reversed(directions)
        ]

    _select_data(dialog._direction_filter, "remote")
    _select_data(dialog._status_filter, "skipped")
    assert _visible_filenames(dialog) == [expected["remote", "skipped"]]

    _select_data(dialog._direction_filter, "")
    _select_data(dialog._status_filter, "")
    assert _visible_filenames(dialog) == all_newest_first


@pytest.mark.gui_integration
@pytest.mark.mt("MT-TH03", "FR-143")
def test_history_export_button_writes_exact_json_entries(
    gui_no_target, tmp_path, monkeypatch, qapp
):
    """The real Export action writes every stored field to the chosen JSON file.

    Verifies: FR-143.
    """
    import json

    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QFileDialog

    from cpm_fm.utils.i18n import tr

    win = gui_no_target
    win.transfer_history.add_entry(
        filename="UPLOAD.COM",
        path="C:/HOST/UPLOAD.COM",
        direction="remote",
        status="success",
        size=1024,
        timestamp="2026-08-07T10:00:00",
    )
    win.transfer_history.add_entry(
        filename="FAILED.TXT",
        path="C:/HOST/FAILED.TXT",
        direction="host",
        status="failure",
        size=17,
        error="checksum mismatch",
        retry=True,
        timestamp="2026-08-07T10:01:00",
    )
    expected_entries = win.transfer_history.get_entries()
    chosen_path = tmp_path / "transfer-history"
    picker_call: dict[str, object] = {}

    def choose_export_path(parent, caption, directory, file_filter):
        picker_call.update(
            parent=parent,
            caption=caption,
            directory=directory,
            file_filter=file_filter,
        )
        return str(chosen_path), file_filter

    monkeypatch.setattr(QFileDialog, "getSaveFileName", choose_export_path)

    win.show()
    qapp.processEvents()
    _action(win, "toolbar.history").trigger()
    qapp.processEvents()

    dialog = win._history_dialog
    assert dialog is not None
    assert dialog._export_btn.isEnabled()
    QTest.mouseClick(dialog._export_btn, Qt.MouseButton.LeftButton)

    exported_path = chosen_path.with_suffix(".json")
    assert picker_call == {
        "parent": dialog,
        "caption": tr("history.export.title"),
        "directory": "",
        "file_filter": tr("dialog.json_filter"),
    }
    assert not chosen_path.exists()
    assert exported_path.is_file()
    assert json.loads(exported_path.read_text(encoding="utf-8")) == expected_entries


@pytest.mark.gui_integration
@pytest.mark.mt("MT-TH04", "FR-143")
def test_history_clear_cancel_preserves_then_confirm_empties_table_and_file(
    gui_no_target, tmp_path, monkeypatch, qapp
):
    """No preserves history; Yes clears the real table, store, and JSON file.

    Verifies: FR-143.
    """
    import json

    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QMessageBox

    from cpm_fm.utils.i18n import tr

    win = gui_no_target
    for index, status in enumerate(("success", "skipped")):
        win.transfer_history.add_entry(
            filename=f"FILE{index}.TXT",
            path=f"C:/HOST/FILE{index}.TXT",
            direction="remote",
            status=status,
            size=index + 1,
            timestamp=f"2026-08-07T10:0{index}:00",
        )
    expected_entries = win.transfer_history.get_entries()
    history_path = tmp_path / "vhistory.json"
    confirmation_calls: list[tuple[object, str, str]] = []
    responses = [
        QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.Yes,
    ]

    def answer_confirmation(parent, title, prompt):
        confirmation_calls.append((parent, title, prompt))
        return responses.pop(0)

    monkeypatch.setattr(QMessageBox, "question", answer_confirmation)

    win.show()
    qapp.processEvents()
    _action(win, "toolbar.history").trigger()
    qapp.processEvents()

    dialog = win._history_dialog
    assert dialog is not None
    assert dialog._table.rowCount() == 2
    assert dialog._clear_btn.isEnabled()

    QTest.mouseClick(dialog._clear_btn, Qt.MouseButton.LeftButton)

    assert dialog._table.rowCount() == 2
    assert dialog._clear_btn.isEnabled()
    assert win.transfer_history.get_entries() == expected_entries
    assert json.loads(history_path.read_text(encoding="utf-8")) == expected_entries

    QTest.mouseClick(dialog._clear_btn, Qt.MouseButton.LeftButton)

    expected_confirmation = (
        dialog,
        tr("history.clear_confirm.title"),
        tr("history.clear_confirm.prompt"),
    )
    assert confirmation_calls == [expected_confirmation, expected_confirmation]
    assert responses == []
    assert dialog._table.rowCount() == 0
    assert not dialog._clear_btn.isEnabled()
    assert not dialog._export_btn.isEnabled()
    assert win.transfer_history.get_entries() == []
    assert json.loads(history_path.read_text(encoding="utf-8")) == []


@pytest.mark.gui_integration
@pytest.mark.mt("MT-TH05", "FR-141")
def test_history_entry_survives_real_application_process_restart(tmp_path):
    """A second application process renders history persisted by the first.

    Verifies: FR-141.
    """
    import json
    import os
    import subprocess
    import sys
    from pathlib import Path

    history_path = tmp_path / "process-history.json"
    state_path = tmp_path / "process-state.ini"
    test_file = Path(__file__).resolve()
    environment = os.environ.copy()
    environment["QT_QPA_PLATFORM"] = "offscreen"

    def run_probe(mode: str) -> dict[str, object]:
        completed = subprocess.run(
            [
                sys.executable,
                str(test_file),
                "--history-process-probe",
                mode,
                str(history_path),
                str(state_path),
            ],
            cwd=test_file.parents[1],
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert completed.returncode == 0, (
            f"history {mode} process failed\nstdout:\n{completed.stdout}"
            f"\nstderr:\n{completed.stderr}"
        )
        probe_line = next(
            line for line in completed.stdout.splitlines() if line.startswith(_PROBE_PREFIX)
        )
        return json.loads(probe_line.removeprefix(_PROBE_PREFIX))

    recorded = run_probe("record")
    entries = recorded["entries"]
    assert isinstance(entries, list)
    assert len(entries) == 1
    expected_entry = entries[0]
    assert expected_entry == {
        "timestamp": expected_entry["timestamp"],
        "filename": "PERSIST.TXT",
        "path": "C:/HOST/PERSIST.TXT",
        "direction": "remote",
        "status": "success",
        "size": 321,
        "error": "",
        "retry": False,
    }
    assert json.loads(history_path.read_text(encoding="utf-8")) == [expected_entry]

    reopened = run_probe("read")
    assert reopened == {
        "row_count": 1,
        "filename": "PERSIST.TXT",
        "size": "321",
        "entry": expected_entry,
    }


if __name__ == "__main__":  # pragma: no cover - exercised by MT-TH05 subprocesses
    import sys

    if len(sys.argv) == 5 and sys.argv[1] == "--history-process-probe":
        _run_history_process_probe(sys.argv[2], sys.argv[3], sys.argv[4])
