"""Target-free real-widget Host Rename/Delete workflows."""

from __future__ import annotations

import pytest

from cpm_fm.utils import i18n


@pytest.mark.gui_integration
@pytest.mark.mt("MT-F04", "UIR-057", "FR-114", "FR-116", "FR-118")
def test_host_rename_real_dialog_apply_cancel_and_noop_paths(gui_no_target, monkeypatch, tmp_path):
    """Rename applies one edit while cancel, unchanged, and empty remain no-ops.

    Verifies: UIR-057, FR-114, FR-116, FR-118.
    """
    from PySide6.QtWidgets import QDialog, QLineEdit, QPushButton

    win = gui_no_target
    win.host_dir = str(tmp_path)
    (tmp_path / "OLD.TXT").write_text("payload", encoding="utf-8")
    win.refresh_host_files()
    real_refresh = win.refresh_host_files
    refreshes: list[list[str]] = []

    def record_refresh():
        real_refresh()
        refreshes.append([win.host_list.item(row).text() for row in range(win.host_list.count())])

    monkeypatch.setattr(win, "refresh_host_files", record_refresh)
    responses = iter(
        [
            ("NEW.TXT", "apply"),
            ("IGNORED.TXT", "cancel"),
            ("NEW.TXT", "apply"),
            ("   ", "apply"),
        ]
    )
    observations: list[tuple[str, bool, bool, str]] = []

    def answer(dialog):
        edit = dialog.findChild(QLineEdit)
        value, response = next(responses)
        observations.append(
            (
                dialog.windowTitle(),
                edit.isReadOnly(),
                edit.hasSelectedText(),
                edit.selectedText(),
            )
        )
        edit.setText(value)
        button_key = "button.apply" if response == "apply" else "button.cancel"
        button = next(
            child
            for child in dialog.findChildren(QPushButton)
            if child.text() == i18n.tr(button_key)
        )
        assert button.isEnabled()
        (dialog.accept if response == "apply" else dialog.reject)()
        return dialog.result()

    monkeypatch.setattr(QDialog, "exec", answer)

    win._host_rename("OLD.TXT")
    assert not (tmp_path / "OLD.TXT").exists()
    assert (tmp_path / "NEW.TXT").read_text(encoding="utf-8") == "payload"
    assert refreshes == [["NEW.TXT"]]

    for _ in range(3):
        win._host_rename("NEW.TXT")

    assert (tmp_path / "NEW.TXT").read_text(encoding="utf-8") == "payload"
    assert not (tmp_path / "IGNORED.TXT").exists()
    assert refreshes == [["NEW.TXT"]]
    assert observations == [
        (i18n.tr("dialog.rename_file.title"), False, True, "OLD.TXT"),
        (i18n.tr("dialog.rename_file.title"), False, True, "NEW.TXT"),
        (i18n.tr("dialog.rename_file.title"), False, True, "NEW.TXT"),
        (i18n.tr("dialog.rename_file.title"), False, True, "NEW.TXT"),
    ]


@pytest.mark.gui_integration
@pytest.mark.mt("MT-F05", "UIR-057", "FR-115", "FR-116", "FR-118")
def test_host_single_delete_real_dialog_cancel_then_apply(gui_no_target, monkeypatch, tmp_path):
    """Single-file Delete is read-only, cancel-safe, and refreshes after Apply.

    Verifies: UIR-057, FR-115, FR-116, FR-118.
    """
    from PySide6.QtWidgets import QDialog, QLabel, QLineEdit, QPushButton

    win = gui_no_target
    win.host_dir = str(tmp_path)
    target = tmp_path / "DELETE.ME"
    target.write_text("payload", encoding="utf-8")
    win.refresh_host_files()
    real_refresh = win.refresh_host_files
    refreshes: list[list[str]] = []

    def record_refresh():
        real_refresh()
        refreshes.append([win.host_list.item(row).text() for row in range(win.host_list.count())])

    monkeypatch.setattr(win, "refresh_host_files", record_refresh)
    responses = iter(("cancel", "apply"))
    observations: list[tuple[str, str, bool, str, list[str]]] = []

    def answer(dialog):
        edit = dialog.findChild(QLineEdit)
        response = next(responses)
        observations.append(
            (
                dialog.windowTitle(),
                edit.text(),
                edit.isReadOnly(),
                next(label.text() for label in dialog.findChildren(QLabel)),
                [button.text() for button in dialog.findChildren(QPushButton)],
            )
        )
        (dialog.accept if response == "apply" else dialog.reject)()
        return dialog.result()

    monkeypatch.setattr(QDialog, "exec", answer)

    win._host_delete("DELETE.ME")
    assert target.read_text(encoding="utf-8") == "payload"
    assert refreshes == []

    win._host_delete("DELETE.ME")
    assert not target.exists()
    assert refreshes == [[]]
    expected = (
        i18n.tr("dialog.delete_file.title"),
        "DELETE.ME",
        True,
        i18n.tr("dialog.delete_file.prompt"),
        [i18n.tr("button.cancel"), i18n.tr("button.apply")],
    )
    assert observations == [expected, expected]


@pytest.mark.gui_integration
@pytest.mark.mt("MT-F05a", "FR-110", "FR-115", "FR-116", "FR-118")
def test_host_multi_delete_lists_selection_cancel_then_deletes_once(
    gui_no_target, monkeypatch, tmp_path
):
    """Multi-delete lists every selected name and refreshes once after Apply.

    Verifies: FR-110, FR-115, FR-116, FR-118.
    """
    from PySide6.QtWidgets import QDialog, QLabel, QPlainTextEdit, QPushButton

    win = gui_no_target
    win.host_dir = str(tmp_path)
    selected_names = ["A.TXT", "B.COM", "C.DAT"]
    for name in [*selected_names, "KEEP.TXT"]:
        (tmp_path / name).write_text(name, encoding="utf-8")
    win.refresh_host_files()
    win.host_list.clearSelection()
    for row in range(win.host_list.count()):
        item = win.host_list.item(row)
        item.setSelected(item.text() in selected_names)
    targets = win._selected_filenames(win.host_list)
    assert targets == selected_names

    real_refresh = win.refresh_host_files
    refreshes: list[list[str]] = []

    def record_refresh():
        real_refresh()
        refreshes.append([win.host_list.item(row).text() for row in range(win.host_list.count())])

    monkeypatch.setattr(win, "refresh_host_files", record_refresh)
    responses = iter(("cancel", "apply"))
    observations: list[tuple[str, bool, str, str, list[str]]] = []

    def answer(dialog):
        listing = dialog.findChild(QPlainTextEdit)
        response = next(responses)
        observations.append(
            (
                dialog.windowTitle(),
                listing.isReadOnly(),
                listing.toPlainText(),
                next(label.text() for label in dialog.findChildren(QLabel)),
                [button.text() for button in dialog.findChildren(QPushButton)],
            )
        )
        (dialog.accept if response == "apply" else dialog.reject)()
        return dialog.result()

    monkeypatch.setattr(QDialog, "exec", answer)

    win._host_delete(targets)
    assert all((tmp_path / name).exists() for name in selected_names)
    assert refreshes == []

    win._host_delete(targets)
    assert all(not (tmp_path / name).exists() for name in selected_names)
    assert (tmp_path / "KEEP.TXT").read_text(encoding="utf-8") == "KEEP.TXT"
    assert refreshes == [["KEEP.TXT"]]
    expected = (
        i18n.tr("dialog.delete_file.title"),
        True,
        "\n".join(selected_names),
        i18n.tr("dialog.delete_file.prompt_multi", count=3),
        [i18n.tr("button.cancel"), i18n.tr("button.apply")],
    )
    assert observations == [expected, expected]
