"""Target-free real-widget disk-image workflows (MT-DI*).

These tests drive the real ``MainWindow`` and the production CP/M image parser,
extractor, file panes, status bar, menu actions, and details dialog.  Only the
native file/mount choices are made deterministic so the cases run headlessly in
the ``gui_integration`` CI lane.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from helpers.disk_image import create_multi_area_image, create_test_image

from cpm_fm.utils import i18n


def _action(win, key: str):
    """Return the translated QAction registered for ``key``."""
    from PySide6.QtGui import QAction

    text = i18n.tr(key)
    return next(action for action in win.findChildren(QAction) if action.text() == text)


def _choose_host_image(monkeypatch, image_path: Path) -> None:
    """Select ``image_path`` in the native picker and choose a Host mount."""
    monkeypatch.setattr(
        "cpm_fm.gui.mw_disk_image.QFileDialog.getOpenFileName",
        lambda *args, **kwargs: (str(image_path), ""),
    )
    monkeypatch.setattr(
        "cpm_fm.gui.mw_disk_image._DiskImageMixin._prompt_mount_side",
        lambda self: "host",
    )


@pytest.mark.gui_integration
@pytest.mark.mt("MT-DI01", "FR-169", "UIR-108")
def test_open_disk_image_action_lists_real_fixture(gui_no_target, monkeypatch, tmp_path, qapp):
    """Open Disk Image lists extracted files through the real Host pane.

    Verifies: FR-169, UIR-108.
    """
    win = gui_no_target
    image_path = create_test_image(tmp_path / "known.img")
    original_host_dir = tmp_path / "host"
    original_host_dir.mkdir()
    (original_host_dir / "BEFORE.TXT").write_bytes(b"host sentinel")
    win.host_dir = str(original_host_dir)
    win.refresh_host_files()
    _choose_host_image(monkeypatch, image_path)

    open_action = _action(win, "menu.file.open_image")
    assert open_action.isEnabled()
    open_action.trigger()
    qapp.processEvents()

    source_payloads = {
        "BINARY.DAT": bytes(range(256)),
        "DATA.TXT": b"This is a test file for HIL testing.\r\n",
        "HELLO.COM": b"print('Hello from CP/M')",
        "LARGE.BIN": b"X" * 1024,
    }
    assert [win.host_list.item(i).text() for i in range(win.host_list.count())] == [
        f"U0  {name}" for name in sorted(source_payloads)
    ]
    extracted = {name: (Path(win.host_dir) / name).read_bytes() for name in source_payloads}
    assert {name: len(data) for name, data in extracted.items()} == {
        "BINARY.DAT": 256,
        "DATA.TXT": 128,
        "HELLO.COM": 128,
        "LARGE.BIN": 1024,
    }
    for name, payload in source_payloads.items():
        assert extracted[name].startswith(payload)
        assert extracted[name][len(payload) :] == b"\x00" * (len(extracted[name]) - len(payload))
    assert win._image_source == str(image_path)
    assert win._image_pane == "host"
    assert "known.img" in win.host_group.title()
    assert Path(win.host_dir) != original_host_dir
    assert original_host_dir.joinpath("BEFORE.TXT").read_bytes() == b"host sentinel"


@pytest.mark.gui_integration
@pytest.mark.mt("MT-DI02", "FR-170")
def test_unique_image_geometry_is_detected_without_prompt(
    gui_no_target, monkeypatch, tmp_path, qapp
):
    """A uniquely sized real image auto-detects its bundled geometry.

    Verifies: FR-170.
    """
    win = gui_no_target
    image_path = create_test_image(tmp_path / "unique.img", geometry_name="ibm-3740")
    _choose_host_image(monkeypatch, image_path)
    prompts: list[tuple] = []
    monkeypatch.setattr(
        "cpm_fm.gui.mw_disk_image.QInputDialog.getItem",
        lambda *args, **kwargs: prompts.append(args) or ("", False),
    )

    _action(win, "menu.file.open_image").trigger()
    qapp.processEvents()

    assert prompts == []
    assert win._image_geom is not None
    assert win._image_geom.name == "ibm-3740"
    assert win.statusBar().currentMessage() == i18n.tr(
        "status.disk_image_loaded", name="unique.img", geometry="ibm-3740"
    )


@pytest.mark.gui_integration
@pytest.mark.mt("MT-DI03", "FR-170")
def test_unmatched_image_geometry_selection_and_cancel_preserve_current_pane(
    gui_no_target, monkeypatch, tmp_path, qapp
):
    """Unknown-size images offer all formats; Cancel preserves the open image.

    Verifies: FR-170.
    """
    win = gui_no_target
    first_path = create_test_image(tmp_path / "manual-geometry.img")
    first_path.write_bytes(first_path.read_bytes() + b"\x00")
    cancelled_path = create_test_image(tmp_path / "cancelled-geometry.img")
    cancelled_path.write_bytes(cancelled_path.read_bytes() + b"\x00")

    selected_paths = iter((first_path, cancelled_path))
    monkeypatch.setattr(
        "cpm_fm.gui.mw_disk_image.QFileDialog.getOpenFileName",
        lambda *args, **kwargs: (str(next(selected_paths)), ""),
    )
    monkeypatch.setattr(
        "cpm_fm.gui.mw_disk_image._DiskImageMixin._prompt_mount_side",
        lambda self: "host",
    )

    prompts: list[dict[str, object]] = []
    choices = iter((("ibm-3740", True), ("ibm-3740", False)))

    def choose_geometry(parent, title, label, items, current, editable):
        prompts.append(
            {
                "title": title,
                "label": label,
                "items": list(items),
                "current": current,
                "editable": editable,
            }
        )
        return next(choices)

    monkeypatch.setattr(
        "cpm_fm.gui.mw_disk_image.QInputDialog.getItem",
        choose_geometry,
    )

    open_action = _action(win, "menu.file.open_image")
    open_action.trigger()
    qapp.processEvents()

    assert win._image_geom is not None
    assert win._image_geom.name == "ibm-3740"
    assert win._image_source == str(first_path)
    open_workdir = Path(win.host_dir)
    open_names = [win.host_list.item(i).text() for i in range(win.host_list.count())]
    assert open_workdir.is_dir()

    open_action.trigger()
    qapp.processEvents()

    assert len(prompts) == 2
    for prompt in prompts:
        assert prompt["title"] == i18n.tr("dialog.open_image.pick_title")
        assert prompt["label"] == i18n.tr("dialog.open_image.pick_unknown")
        assert "ibm-3740" in prompt["items"]
        assert prompt["current"] == 0
        assert prompt["editable"] is False
    assert win._image_source == str(first_path)
    assert Path(win.host_dir) == open_workdir
    assert open_workdir.is_dir()
    assert [win.host_list.item(i).text() for i in range(win.host_list.count())] == open_names


@pytest.mark.gui_integration
@pytest.mark.mt("MT-DI05", "FR-172")
def test_unreadable_image_error_preserves_current_host_pane(
    gui_no_target, monkeypatch, tmp_path, qapp
):
    """Rejecting a truncated image leaves the current Host pane unchanged.

    Verifies: FR-172.
    """
    win = gui_no_target
    host_dir = tmp_path / "host"
    host_dir.mkdir()
    sentinel = host_dir / "KEEP.TXT"
    sentinel.write_bytes(b"unchanged")
    win.host_dir = str(host_dir)
    win.refresh_host_files()

    bad_path = tmp_path / "truncated.img"
    bad_path.write_bytes(b"not a CP/M disk image")
    _choose_host_image(monkeypatch, bad_path)
    monkeypatch.setattr(
        "cpm_fm.gui.mw_disk_image.QInputDialog.getItem",
        lambda *args, **kwargs: ("ibm-3740", True),
    )
    errors: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "cpm_fm.gui.mw_disk_image.QMessageBox.critical",
        lambda parent, title, message: errors.append((title, message)),
    )

    _action(win, "menu.file.open_image").trigger()
    qapp.processEvents()

    assert errors == [
        (
            i18n.tr("dialog.error.title"),
            i18n.tr("error.disk_image_unreadable", name=bad_path.name),
        )
    ]
    assert win.host_dir == str(host_dir)
    assert [win.host_list.item(i).text() for i in range(win.host_list.count())] == ["KEEP.TXT"]
    assert sentinel.read_bytes() == b"unchanged"
    assert win._image_workdir is None


@pytest.mark.gui_integration
@pytest.mark.mt("MT-DI06", "FR-171")
def test_change_directory_discards_image_workdir_and_repaints_host_pane(
    gui_no_target, monkeypatch, tmp_path, qapp
):
    """Change Directory removes the open image and all stale pane state.

    Verifies: FR-171.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QPushButton

    win = gui_no_target
    image_path = create_test_image(tmp_path / "leave.img")
    destination = tmp_path / "destination"
    destination.mkdir()
    (destination / "AFTER.TXT").write_bytes(b"new directory")
    _choose_host_image(monkeypatch, image_path)
    _action(win, "menu.file.open_image").trigger()
    qapp.processEvents()

    old_workdir = Path(win.host_dir)
    details_action = _action(win, "menu.file.image_details")
    close_action = _action(win, "menu.file.close_image")
    save_action = _action(win, "menu.file.save_image")
    assert old_workdir.is_dir()
    assert details_action.isEnabled()
    assert close_action.isEnabled()
    assert save_action.isEnabled()

    monkeypatch.setattr(
        "cpm_fm.gui.mw_file_panes.QFileDialog.getExistingDirectory",
        lambda *args, **kwargs: str(destination),
    )
    change_directory = next(
        button
        for button in win.findChildren(QPushButton)
        if button.text() == i18n.tr("main.change_directory")
    )
    QTest.mouseClick(change_directory, Qt.MouseButton.LeftButton)
    qapp.processEvents()

    assert old_workdir.exists() is False
    assert win.host_dir == str(destination)
    assert [win.host_list.item(i).text() for i in range(win.host_list.count())] == ["AFTER.TXT"]
    assert destination.name in win.host_group.title()
    assert image_path.name not in win.host_group.title()
    assert win._image_workdir is None
    assert win._image_source is None
    assert win._image_geom is None
    assert win._image_files == []
    assert win._image_stage_map == {}
    assert details_action.isEnabled() is False
    assert close_action.isEnabled() is False
    assert save_action.isEnabled() is False


@pytest.mark.gui_integration
@pytest.mark.mt("MT-DI07", "FR-173", "UIR-109")
def test_image_details_action_opens_real_read_only_table(
    gui_no_target, monkeypatch, tmp_path, qapp
):
    """Image Details renders one read-only metadata row per image file.

    Verifies: FR-173, UIR-109.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QAbstractItemView, QDialog, QPushButton, QTableWidget

    win = gui_no_target
    image_path = create_test_image(tmp_path / "details.img")
    _choose_host_image(monkeypatch, image_path)
    _action(win, "menu.file.open_image").trigger()
    qapp.processEvents()

    observed: dict[str, object] = {}

    def inspect_and_close(dialog):
        dialog.show()
        qapp.processEvents()
        table = dialog.findChild(QTableWidget)
        assert table is not None
        observed.update(
            title=dialog.windowTitle(),
            modal=dialog.isModal(),
            headers=[table.horizontalHeaderItem(col).text() for col in range(table.columnCount())],
            rows=[
                [table.item(row, col).text() for col in range(table.columnCount())]
                for row in range(table.rowCount())
            ],
            edit_triggers=table.editTriggers(),
        )
        close_button = next(
            button
            for button in dialog.findChildren(QPushButton)
            if button.text() == i18n.tr("dialog.image_details.close")
        )
        QTest.mouseClick(close_button, Qt.MouseButton.LeftButton)
        return dialog.result()

    monkeypatch.setattr(QDialog, "exec", inspect_and_close)
    _action(win, "menu.file.image_details").trigger()

    assert observed == {
        "title": i18n.tr("dialog.image_details.title"),
        "modal": True,
        "headers": [
            i18n.tr("dialog.image_details.col.name"),
            i18n.tr("dialog.image_details.col.size"),
            i18n.tr("dialog.image_details.col.user"),
            i18n.tr("dialog.image_details.col.attrs"),
        ],
        # CP/M directory sizes are record-granular (128 bytes), and the details
        # dialog preserves directory-entry order rather than the pane's sort.
        "rows": [
            ["HELLO.COM", "128", "0", "-"],
            ["DATA.TXT", "128", "0", "-"],
            ["BINARY.DAT", "256", "0", "-"],
            ["LARGE.BIN", "1024", "0", "-"],
        ],
        "edit_triggers": QAbstractItemView.EditTrigger.NoEditTriggers,
    }


@pytest.mark.gui_integration
@pytest.mark.mt("MT-DI08", "FR-173", "UIR-109")
def test_image_details_action_enabled_only_while_image_is_open(
    gui_no_target, monkeypatch, tmp_path, qapp
):
    """Image Details transitions from disabled to enabled on a real open.

    Verifies: FR-173, UIR-109.
    """
    win = gui_no_target
    details_action = _action(win, "menu.file.image_details")
    assert details_action.isEnabled() is False

    image_path = create_test_image(tmp_path / "enablement.img")
    _choose_host_image(monkeypatch, image_path)
    _action(win, "menu.file.open_image").trigger()
    qapp.processEvents()

    assert details_action.isEnabled() is True
    _action(win, "menu.file.close_image").trigger()
    qapp.processEvents()
    assert details_action.isEnabled() is False


@pytest.mark.gui_integration
@pytest.mark.mt("MT-DI10", "FR-174", "DR-050")
def test_save_image_in_place_reopens_with_exact_working_file_set(
    gui_no_target, monkeypatch, tmp_path, qapp
):
    """Saving a named image in place survives a real close/reopen cycle.

    Verifies: FR-174, DR-050.
    """
    from cpm_fm.utils.disk_image import open_image

    win = gui_no_target
    image_path = create_test_image(tmp_path / "roundtrip.img")
    _choose_host_image(monkeypatch, image_path)
    _action(win, "menu.file.open_image").trigger()
    qapp.processEvents()

    assert win._image_geom is not None
    boot_size = win._image_geom.boottrk * win._image_geom.sectrk * win._image_geom.seclen
    boot_before = image_path.read_bytes()[:boot_size]
    image_before = image_path.read_bytes()
    workdir = Path(win.host_dir)
    (workdir / "DATA.TXT").unlink()
    new_payload = b"saved through the real File menu\r\n"
    (workdir / "NEW.TXT").write_bytes(new_payload)
    assert win._image_is_dirty()

    monkeypatch.setattr(
        "cpm_fm.gui.mw_disk_image.QFileDialog.getSaveFileName",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("a named image must save in place without Save As")
        ),
    )
    _action(win, "menu.file.save_image").trigger()
    qapp.processEvents()

    image_after = image_path.read_bytes()
    assert image_after != image_before
    assert image_after[:boot_size] == boot_before
    assert win._image_is_dirty() is False
    assert win.statusBar().currentMessage() == i18n.tr(
        "status.disk_image_saved", name=image_path.name, count=4
    )

    _action(win, "menu.file.close_image").trigger()
    qapp.processEvents()
    assert workdir.exists() is False
    _action(win, "menu.file.open_image").trigger()
    qapp.processEvents()

    visible_names = [win.host_list.item(i).text() for i in range(win.host_list.count())]
    assert visible_names == [
        "U0  BINARY.DAT",
        "U0  HELLO.COM",
        "U0  LARGE.BIN",
        "U0  NEW.TXT",
    ]
    reopened = open_image(image_path)
    assert reopened is not None
    assert {entry.name for entry in reopened.list_files()} == {
        "BINARY.DAT",
        "HELLO.COM",
        "LARGE.BIN",
        "NEW.TXT",
    }
    new_data = reopened.read_file("NEW.TXT")
    assert new_data.startswith(new_payload)
    assert new_data[len(new_payload) :] == b"\x00" * (len(new_data) - len(new_payload))


@pytest.mark.gui_integration
@pytest.mark.mt("MT-DI10", "FR-174", "DR-050")
@pytest.mark.parametrize("failure", ["invalid-name", "capacity"])
def test_save_image_failure_is_transactional(gui_no_target, monkeypatch, tmp_path, qapp, failure):
    """Invalid names and over-capacity contents leave the image untouched.

    Verifies: FR-174, DR-050.
    """
    win = gui_no_target
    image_path = create_test_image(tmp_path / f"{failure}.img")
    _choose_host_image(monkeypatch, image_path)
    _action(win, "menu.file.open_image").trigger()
    qapp.processEvents()

    before = image_path.read_bytes()
    workdir = Path(win.host_dir)
    if failure == "invalid-name":
        (workdir / "TOO-LONG-NAME.TXT").write_bytes(b"invalid CP/M name")
    else:
        assert win._image_geom is not None
        (workdir / "HUGE.BIN").write_bytes(b"X" * win._image_geom.total_bytes)

    errors: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "cpm_fm.gui.mw_disk_image.QMessageBox.critical",
        lambda parent, title, message: errors.append((title, message)),
    )
    _action(win, "menu.file.save_image").trigger()
    qapp.processEvents()

    assert len(errors) == 1
    assert errors[0][0] == i18n.tr("dialog.error.title")
    assert errors[0][1].startswith(i18n.tr("error.disk_image_write", error="").rstrip())
    assert image_path.read_bytes() == before
    assert win._image_source == str(image_path)
    assert win._image_is_dirty()


@pytest.mark.gui_integration
@pytest.mark.mt("MT-DI12", "FR-175", "UIR-111")
@pytest.mark.parametrize("choice", ["cancel", "discard", "save"])
def test_dirty_image_change_directory_uses_real_unsaved_dialog(
    gui_no_target, monkeypatch, tmp_path, qapp, choice
):
    """The real unsaved dialog routes Cancel, Discard, and Save exactly.

    Verifies: FR-175, UIR-111.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QDialog, QLabel, QPushButton

    from cpm_fm.utils.disk_image import open_image

    win = gui_no_target
    image_path = create_test_image(tmp_path / f"dirty-{choice}.img")
    destination = tmp_path / "destination"
    destination.mkdir()
    (destination / "PLAIN.TXT").write_bytes(b"ordinary host file")
    _choose_host_image(monkeypatch, image_path)
    _action(win, "menu.file.open_image").trigger()
    qapp.processEvents()

    source_before = image_path.read_bytes()
    workdir = Path(win.host_dir)
    staged_payload = f"{choice} staged content\r\n".encode()
    (workdir / "STAGED.TXT").write_bytes(staged_payload)
    assert win._image_is_dirty()
    monkeypatch.setattr(
        "cpm_fm.gui.mw_file_panes.QFileDialog.getExistingDirectory",
        lambda *args, **kwargs: str(destination),
    )

    inspection: dict[str, object] = {}

    def inspect_and_choose(dialog):
        dialog.show()
        qapp.processEvents()
        button_row = dialog.layout().itemAt(dialog.layout().count() - 1).layout()
        buttons = [
            button_row.itemAt(index).widget()
            for index in range(button_row.count())
            if isinstance(button_row.itemAt(index).widget(), QPushButton)
        ]
        inspection.update(
            title=dialog.windowTitle(),
            modal=dialog.isModal(),
            labels=[label.text() for label in dialog.findChildren(QLabel) if label.text()],
            buttons=[button.text() for button in buttons],
            defaults=[button.text() for button in buttons if button.isDefault()],
        )
        selected = next(
            button for button in buttons if button.text() == i18n.tr(f"button.{choice}")
        )
        QTest.mouseClick(selected, Qt.MouseButton.LeftButton)
        return dialog.result()

    monkeypatch.setattr(QDialog, "exec", inspect_and_choose)
    change_directory = next(
        button
        for button in win.findChildren(QPushButton)
        if button.text() == i18n.tr("main.change_directory")
    )
    QTest.mouseClick(change_directory, Qt.MouseButton.LeftButton)
    qapp.processEvents()

    assert inspection == {
        "title": i18n.tr("dialog.image_dirty.title"),
        "modal": True,
        "labels": [i18n.tr("dialog.image_dirty.message", name=image_path.name)],
        "buttons": [
            i18n.tr("button.cancel"),
            i18n.tr("button.discard"),
            i18n.tr("button.save"),
        ],
        "defaults": [i18n.tr("button.save")],
    }

    if choice == "cancel":
        assert win.host_dir == str(workdir)
        assert win._image_source == str(image_path)
        assert workdir.is_dir()
        assert image_path.read_bytes() == source_before
        assert (workdir / "STAGED.TXT").read_bytes() == staged_payload
        win._cleanup_image_workdir()
        return

    assert win.host_dir == str(destination)
    assert win._image_workdir is None
    assert workdir.exists() is False
    assert [win.host_list.item(i).text() for i in range(win.host_list.count())] == ["PLAIN.TXT"]
    if choice == "discard":
        assert image_path.read_bytes() == source_before
        reopened = open_image(image_path)
        assert reopened is not None
        assert "STAGED.TXT" not in {entry.name for entry in reopened.list_files()}
    else:
        assert image_path.read_bytes() != source_before
        reopened = open_image(image_path)
        assert reopened is not None
        saved = reopened.read_file("STAGED.TXT")
        assert saved.startswith(staged_payload)


@pytest.mark.gui_integration
@pytest.mark.mt("MT-DI13", "FR-176", "UIR-112")
def test_remote_mounted_image_uses_real_dialog_copy_buttons_and_save(
    gui_no_target, monkeypatch, tmp_path, qapp
):
    """A Remote mount copies locally in both directions and survives save/reopen.

    Verifies: FR-176, UIR-112.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QDialog, QPushButton, QRadioButton

    win = gui_no_target
    host_dir = tmp_path / "host"
    host_dir.mkdir()
    upload_payload = b"local host to image copy\r\n"
    (host_dir / "UPLOAD.TXT").write_bytes(upload_payload)
    win.host_dir = str(host_dir)
    win.refresh_host_files()
    image_path = create_test_image(tmp_path / "remote.img")
    monkeypatch.setattr(
        "cpm_fm.gui.mw_disk_image.QFileDialog.getOpenFileName",
        lambda *args, **kwargs: (str(image_path), ""),
    )

    mount_dialogs: list[dict[str, object]] = []

    def choose_remote(dialog):
        dialog.show()
        qapp.processEvents()
        radios = dialog.findChildren(QRadioButton)
        buttons = dialog.findChildren(QPushButton)
        host_radio = next(
            radio for radio in radios if radio.text() == i18n.tr("dialog.mount_side.host")
        )
        remote_radio = next(
            radio for radio in radios if radio.text() == i18n.tr("dialog.mount_side.remote")
        )
        mount_dialogs.append(
            {
                "title": dialog.windowTitle(),
                "modal": dialog.isModal(),
                "host_default": host_radio.isChecked(),
                "choices": [radio.text() for radio in radios],
            }
        )
        QTest.mouseClick(remote_radio, Qt.MouseButton.LeftButton)
        ok_button = next(button for button in buttons if button.text() == i18n.tr("button.ok"))
        QTest.mouseClick(ok_button, Qt.MouseButton.LeftButton)
        return dialog.result()

    monkeypatch.setattr(QDialog, "exec", choose_remote)
    monkeypatch.setattr(
        win,
        "_transfer_to_remote_batch",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("Remote-mounted image copy must not use serial upload")
        ),
    )
    monkeypatch.setattr(
        win,
        "_transfer_to_host_batch",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("Remote-mounted image copy must not use serial download")
        ),
    )

    _action(win, "menu.file.open_image").trigger()
    qapp.processEvents()

    assert mount_dialogs == [
        {
            "title": i18n.tr("dialog.mount_side.title"),
            "modal": True,
            "host_default": True,
            "choices": [
                i18n.tr("dialog.mount_side.host"),
                i18n.tr("dialog.mount_side.remote"),
            ],
        }
    ]
    assert win._image_pane == "remote"
    assert win.host_dir == str(host_dir)
    assert win.drive_combo.isEnabled() is False
    assert image_path.name in win.remote_group.title()
    assert [win.host_list.item(i).text() for i in range(win.host_list.count())] == ["UPLOAD.TXT"]
    assert win.remote_list.count() == 4

    win.host_list.item(0).setSelected(True)
    copy_to_remote = next(
        button
        for button in win.findChildren(QPushButton)
        if button.text() == i18n.tr("main.copy_to_remote")
    )
    QTest.mouseClick(copy_to_remote, Qt.MouseButton.LeftButton)
    qapp.processEvents()

    assert win._transfer_dialog is None
    assert win.serial_mgr.terminal_connected is False
    assert win.serial_mgr.transport_connected is False
    assert win._image_workdir is not None
    assert Path(win._image_workdir, "UPLOAD.TXT").read_bytes() == upload_payload
    assert win._image_stage_map["UPLOAD.TXT"] == ("UPLOAD.TXT", 0)
    assert win._image_is_dirty()

    hello_item = next(
        win.remote_list.item(row)
        for row in range(win.remote_list.count())
        if win.remote_list.item(row).data(Qt.ItemDataRole.UserRole) == "HELLO.COM"
    )
    win.remote_list.clearSelection()
    hello_item.setSelected(True)
    copy_to_host = next(
        button
        for button in win.findChildren(QPushButton)
        if button.text() == i18n.tr("main.copy_to_host")
    )
    QTest.mouseClick(copy_to_host, Qt.MouseButton.LeftButton)
    qapp.processEvents()

    copied = host_dir / "HELLO.COM"
    assert copied.read_bytes().startswith(b"print('Hello from CP/M')")
    assert win._transfer_dialog is None

    _action(win, "menu.file.save_image").trigger()
    qapp.processEvents()
    assert win._image_is_dirty() is False
    _action(win, "menu.file.close_image").trigger()
    qapp.processEvents()
    assert win.drive_combo.isEnabled()
    assert win.remote_list.count() == 0

    _action(win, "menu.file.open_image").trigger()
    qapp.processEvents()
    assert len(mount_dialogs) == 2
    remote_names = {
        win.remote_list.item(row).data(Qt.ItemDataRole.UserRole)
        for row in range(win.remote_list.count())
    }
    assert remote_names == {"BINARY.DAT", "DATA.TXT", "HELLO.COM", "LARGE.BIN", "UPLOAD.TXT"}


@pytest.mark.gui_integration
@pytest.mark.mt("MT-DI15", "FR-177", "UIR-113")
@pytest.mark.parametrize("mount", ["host", "remote"])
def test_close_image_restores_selected_pane_state(
    gui_no_target, monkeypatch, tmp_path, qapp, mount
):
    """Close Image restores the prior Host or real Remote pane state.

    Verifies: FR-177, UIR-113.
    """
    win = gui_no_target
    host_dir = tmp_path / "host"
    host_dir.mkdir()
    (host_dir / "HOST.TXT").write_bytes(b"host remains")
    win.host_dir = str(host_dir)
    win.refresh_host_files()
    image_path = create_test_image(tmp_path / f"close-{mount}.img")
    monkeypatch.setattr(
        "cpm_fm.gui.mw_disk_image.QFileDialog.getOpenFileName",
        lambda *args, **kwargs: (str(image_path), ""),
    )
    monkeypatch.setattr(
        "cpm_fm.gui.mw_disk_image._DiskImageMixin._prompt_mount_side",
        lambda self: mount,
    )

    close_action = _action(win, "menu.file.close_image")
    assert close_action.isEnabled() is False
    _action(win, "menu.file.open_image").trigger()
    qapp.processEvents()

    assert win._image_workdir is not None
    workdir = Path(win._image_workdir)
    assert workdir.is_dir()
    assert close_action.isEnabled()
    if mount == "host":
        assert win.host_dir == str(workdir)
    else:
        assert win.host_dir == str(host_dir)
        assert win.remote_list.count() == 4
        assert win.drive_combo.isEnabled() is False

    close_action.trigger()
    qapp.processEvents()

    assert workdir.exists() is False
    assert win._image_workdir is None
    assert close_action.isEnabled() is False
    assert win.host_dir == str(host_dir)
    assert [win.host_list.item(i).text() for i in range(win.host_list.count())] == ["HOST.TXT"]
    if mount == "remote":
        assert win.remote_list.count() == 0
        assert win.drive_combo.isEnabled()
        assert win.remote_group.title() == i18n.tr("main.remote_files")


@pytest.mark.gui_integration
@pytest.mark.mt("MT-DI15", "FR-177", "UIR-113")
def test_close_dirty_image_cancel_keeps_mount_open(gui_no_target, monkeypatch, tmp_path, qapp):
    """Cancel in the real dirty-image dialog aborts Close Disk Image.

    Verifies: FR-177, UIR-113.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QDialog, QPushButton

    win = gui_no_target
    image_path = create_test_image(tmp_path / "dirty-close.img")
    _choose_host_image(monkeypatch, image_path)
    _action(win, "menu.file.open_image").trigger()
    qapp.processEvents()
    workdir = Path(win.host_dir)
    (workdir / "DIRTY.TXT").write_bytes(b"unsaved")
    assert win._image_is_dirty()

    dialogs: list[str] = []

    def cancel_dialog(dialog):
        dialog.show()
        qapp.processEvents()
        dialogs.append(dialog.windowTitle())
        cancel = next(
            button
            for button in dialog.findChildren(QPushButton)
            if button.text() == i18n.tr("button.cancel")
        )
        QTest.mouseClick(cancel, Qt.MouseButton.LeftButton)
        return dialog.result()

    monkeypatch.setattr(QDialog, "exec", cancel_dialog)
    close_action = _action(win, "menu.file.close_image")
    close_action.trigger()
    qapp.processEvents()

    assert dialogs == [i18n.tr("dialog.image_dirty.title")]
    assert win._image_workdir == str(workdir)
    assert win.host_dir == str(workdir)
    assert workdir.is_dir()
    assert (workdir / "DIRTY.TXT").read_bytes() == b"unsaved"
    assert close_action.isEnabled()


@pytest.mark.gui_integration
@pytest.mark.mt("MT-DI12", "FR-175", "UIR-111")
def test_clean_image_change_directory_does_not_prompt(gui_no_target, monkeypatch, tmp_path, qapp):
    """Leaving an unchanged image bypasses the unsaved-changes dialog.

    Verifies: FR-175, UIR-111.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QDialog, QPushButton

    win = gui_no_target
    image_path = create_test_image(tmp_path / "clean.img")
    destination = tmp_path / "destination"
    destination.mkdir()
    _choose_host_image(monkeypatch, image_path)
    _action(win, "menu.file.open_image").trigger()
    qapp.processEvents()

    workdir = Path(win.host_dir)
    assert win._image_is_dirty() is False
    monkeypatch.setattr(
        "cpm_fm.gui.mw_file_panes.QFileDialog.getExistingDirectory",
        lambda *args, **kwargs: str(destination),
    )
    monkeypatch.setattr(
        QDialog,
        "exec",
        lambda dialog: (_ for _ in ()).throw(AssertionError("clean image must not prompt")),
    )
    change_directory = next(
        button
        for button in win.findChildren(QPushButton)
        if button.text() == i18n.tr("main.change_directory")
    )
    QTest.mouseClick(change_directory, Qt.MouseButton.LeftButton)
    qapp.processEvents()

    assert win.host_dir == str(destination)
    assert win._image_workdir is None
    assert workdir.exists() is False


@pytest.mark.gui_integration
@pytest.mark.mt("MT-DI16", "FR-178", "UIR-114")
@pytest.mark.parametrize("mount", ["host", "remote"])
def test_new_image_action_creates_empty_selected_pane(
    gui_no_target, monkeypatch, tmp_path, qapp, mount
):
    """New Disk Image creates an unnamed empty image in either pane.

    Verifies: FR-178, UIR-114.
    """
    win = gui_no_target
    host_dir = tmp_path / "host"
    host_dir.mkdir()
    (host_dir / "HOST.TXT").write_bytes(b"ordinary host file")
    win.host_dir = str(host_dir)
    win.refresh_host_files()
    geometry_prompts: list[dict[str, object]] = []
    monkeypatch.setattr(
        "cpm_fm.gui.mw_disk_image._DiskImageMixin._prompt_mount_side",
        lambda self: mount,
    )

    def choose_geometry(parent, title, label, items, current, editable):
        geometry_prompts.append(
            {
                "title": title,
                "label": label,
                "items": list(items),
                "current": current,
                "editable": editable,
            }
        )
        return "ibm-3740", True

    monkeypatch.setattr(
        "cpm_fm.gui.mw_disk_image.QInputDialog.getItem",
        choose_geometry,
    )

    new_action = _action(win, "menu.file.new_image")
    assert new_action.isEnabled()
    new_action.trigger()
    qapp.processEvents()

    assert len(geometry_prompts) == 1
    assert geometry_prompts[0]["title"] == i18n.tr("dialog.new_image.pick_title")
    assert geometry_prompts[0]["label"] == i18n.tr("dialog.new_image.pick_label")
    assert "ibm-3740" in geometry_prompts[0]["items"]
    assert geometry_prompts[0]["current"] == 0
    assert geometry_prompts[0]["editable"] is False
    assert win._image_source is None
    assert win._image_geom is not None
    assert win._image_geom.name == "ibm-3740"
    assert win._image_pane == mount
    assert win._image_is_dirty() is False
    assert _action(win, "menu.file.save_image").isEnabled()
    assert _action(win, "menu.file.close_image").isEnabled()
    if mount == "host":
        assert win.host_list.count() == 0
        assert i18n.tr("main.image_unsaved") in win.host_group.title()
    else:
        assert win.remote_list.count() == 0
        assert win.host_dir == str(host_dir)
        assert [win.host_list.item(i).text() for i in range(win.host_list.count())] == ["HOST.TXT"]
        assert win.drive_combo.isEnabled() is False
        assert i18n.tr("main.image_unsaved") in win.remote_group.title()


@pytest.mark.gui_integration
@pytest.mark.mt("MT-DI16", "FR-178", "UIR-114")
def test_new_remote_image_copy_first_save_as_and_reopen(gui_no_target, monkeypatch, tmp_path, qapp):
    """An unnamed Remote image adopts its first saved path and reopens.

    Verifies: FR-178, UIR-114.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QPushButton

    win = gui_no_target
    host_dir = tmp_path / "host"
    image_dir = tmp_path / "images"
    host_dir.mkdir()
    image_dir.mkdir()
    payload = b"new image payload\r\n"
    (host_dir / "FIRST.TXT").write_bytes(payload)
    win.host_dir = str(host_dir)
    win.image_dir = str(image_dir)
    win.refresh_host_files()
    monkeypatch.setattr(
        "cpm_fm.gui.mw_disk_image._DiskImageMixin._prompt_mount_side",
        lambda self: "remote",
    )
    monkeypatch.setattr(
        "cpm_fm.gui.mw_disk_image.QInputDialog.getItem",
        lambda *args, **kwargs: ("ibm-3740", True),
    )
    _action(win, "menu.file.new_image").trigger()
    qapp.processEvents()

    win.host_list.item(0).setSelected(True)
    copy_to_remote = next(
        button
        for button in win.findChildren(QPushButton)
        if button.text() == i18n.tr("main.copy_to_remote")
    )
    QTest.mouseClick(copy_to_remote, Qt.MouseButton.LeftButton)
    qapp.processEvents()
    assert win._image_is_dirty()
    assert win.remote_list.count() == 1

    saved_path = image_dir / "created.img"
    save_dialogs: list[dict[str, str]] = []

    def choose_save_path(parent, title, suggested, file_filter):
        save_dialogs.append({"title": title, "suggested": suggested, "filter": file_filter})
        return str(saved_path), ""

    monkeypatch.setattr(
        "cpm_fm.gui.mw_disk_image.QFileDialog.getSaveFileName",
        choose_save_path,
    )
    _action(win, "menu.file.save_image").trigger()
    qapp.processEvents()

    assert save_dialogs == [
        {
            "title": i18n.tr("dialog.save_image.title"),
            "suggested": str(image_dir / "new_image.img"),
            "filter": i18n.tr("dialog.save_image.filter"),
        }
    ]
    assert saved_path.is_file()
    assert win._image_source == str(saved_path)
    assert win.image_dir == str(image_dir)
    assert saved_path.name in win.remote_group.title()
    assert i18n.tr("main.image_unsaved") not in win.remote_group.title()
    assert win._image_is_dirty() is False

    _action(win, "menu.file.close_image").trigger()
    monkeypatch.setattr(
        "cpm_fm.gui.mw_disk_image.QFileDialog.getOpenFileName",
        lambda *args, **kwargs: (str(saved_path), ""),
    )
    _action(win, "menu.file.open_image").trigger()
    qapp.processEvents()

    assert win.remote_list.count() == 1
    item = win.remote_list.item(0)
    assert item.data(Qt.ItemDataRole.UserRole) == "FIRST.TXT"
    assert Path(win._image_workdir, "FIRST.TXT").read_bytes().startswith(payload)


@pytest.mark.gui_integration
@pytest.mark.mt("MT-DI17", "FR-176", "FR-179")
def test_image_directory_persists_and_remote_mount_survives_host_directory_change(
    gui_no_target, monkeypatch, tmp_path, qapp
):
    """Image browsing persists independently and a Remote mount survives Host navigation.

    Verifies: FR-176, FR-179.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QPushButton

    win = gui_no_target
    initial_host = tmp_path / "host-initial"
    next_host = tmp_path / "host-next"
    image_dir = tmp_path / "images"
    wrong_dir = tmp_path / "wrong"
    for directory in (initial_host, next_host, image_dir, wrong_dir):
        directory.mkdir()
    (initial_host / "INITIAL.TXT").write_bytes(b"initial")
    (next_host / "NEXT.TXT").write_bytes(b"next")
    image_path = create_test_image(image_dir / "persisted.img")
    win.host_dir = str(initial_host)
    win.image_dir = str(image_dir)
    win.settings["host_directory"] = str(initial_host)
    win.settings["image_directory"] = str(image_dir)
    win.refresh_host_files()

    config_path = tmp_path / "image-directory.json"
    monkeypatch.setattr(
        "cpm_fm.gui.mw_config.QFileDialog.getSaveFileName",
        lambda *args, **kwargs: (str(config_path), ""),
    )
    _action(win, "menu.file.save").trigger()
    qapp.processEvents()
    assert config_path.is_file()

    win.host_dir = str(wrong_dir)
    win.image_dir = str(wrong_dir)
    monkeypatch.setattr(
        "cpm_fm.gui.mw_config.QFileDialog.getOpenFileName",
        lambda *args, **kwargs: (str(config_path), ""),
    )
    _action(win, "menu.file.load").trigger()
    qapp.processEvents()
    assert win.host_dir == str(initial_host)
    assert win.image_dir == str(image_dir)

    open_dialogs: list[str] = []

    def choose_image(parent, title, directory, file_filter):
        open_dialogs.append(directory)
        return str(image_path), ""

    monkeypatch.setattr(
        "cpm_fm.gui.mw_disk_image.QFileDialog.getOpenFileName",
        choose_image,
    )
    monkeypatch.setattr(
        "cpm_fm.gui.mw_disk_image._DiskImageMixin._prompt_mount_side",
        lambda self: "remote",
    )
    _action(win, "menu.file.open_image").trigger()
    qapp.processEvents()

    assert open_dialogs == [str(image_dir)]
    assert win._image_workdir is not None
    image_workdir = win._image_workdir
    remote_names = [
        win.remote_list.item(row).data(Qt.ItemDataRole.UserRole)
        for row in range(win.remote_list.count())
    ]
    monkeypatch.setattr(
        "cpm_fm.gui.mw_file_panes.QFileDialog.getExistingDirectory",
        lambda *args, **kwargs: str(next_host),
    )
    change_directory = next(
        button
        for button in win.findChildren(QPushButton)
        if button.text() == i18n.tr("main.change_directory")
    )
    QTest.mouseClick(change_directory, Qt.MouseButton.LeftButton)
    qapp.processEvents()

    assert win.host_dir == str(next_host)
    assert [win.host_list.item(i).text() for i in range(win.host_list.count())] == ["NEXT.TXT"]
    assert win.image_dir == str(image_dir)
    assert win._image_workdir == image_workdir
    assert win._image_pane == "remote"
    assert win.drive_combo.isEnabled() is False
    assert [
        win.remote_list.item(row).data(Qt.ItemDataRole.UserRole)
        for row in range(win.remote_list.count())
    ] == remote_names


@pytest.mark.gui_integration
@pytest.mark.mt("MT-DI18", "FR-174")
def test_config_labels_and_named_versus_new_image_save_behavior(
    gui_no_target, monkeypatch, tmp_path, qapp
):
    """Config labels are current; only a new image asks for its first save path.

    Verifies: FR-174.
    """
    from PySide6.QtWidgets import QMenu

    win = gui_no_target
    config_menu = next(
        menu for menu in win.findChildren(QMenu) if menu.title() == i18n.tr("menu.config")
    )
    assert [action.text() for action in config_menu.actions() if not action.isSeparator()][:3] == [
        i18n.tr("menu.file.new"),
        i18n.tr("menu.file.load"),
        i18n.tr("menu.file.save"),
    ]
    assert "image_write_enabled" not in win.settings

    named_path = create_test_image(tmp_path / "named.img")
    _choose_host_image(monkeypatch, named_path)
    _action(win, "menu.file.open_image").trigger()
    qapp.processEvents()
    named_before = named_path.read_bytes()
    Path(win.host_dir, "NAMED.TXT").write_bytes(b"named image edit")

    save_dialogs: list[str] = []

    def unexpected_save_as(*args, **kwargs):
        save_dialogs.append("named")
        raise AssertionError("a named image must save in place")

    monkeypatch.setattr(
        "cpm_fm.gui.mw_disk_image.QFileDialog.getSaveFileName",
        unexpected_save_as,
    )
    _action(win, "menu.file.save_image").trigger()
    qapp.processEvents()
    assert save_dialogs == []
    assert named_path.read_bytes() != named_before

    _action(win, "menu.file.close_image").trigger()
    monkeypatch.setattr(
        "cpm_fm.gui.mw_disk_image._DiskImageMixin._prompt_mount_side",
        lambda self: "remote",
    )
    monkeypatch.setattr(
        "cpm_fm.gui.mw_disk_image.QInputDialog.getItem",
        lambda *args, **kwargs: ("ibm-3740", True),
    )
    _action(win, "menu.file.new_image").trigger()
    qapp.processEvents()
    assert win._image_workdir is not None
    Path(win._image_workdir, "NEW.TXT").write_bytes(b"new image edit")

    new_path = tmp_path / "new-once.img"
    calls: list[str] = []

    def first_save_as(parent, title, suggested, file_filter):
        calls.append(suggested)
        return str(new_path), ""

    monkeypatch.setattr(
        "cpm_fm.gui.mw_disk_image.QFileDialog.getSaveFileName",
        first_save_as,
    )
    save_action = _action(win, "menu.file.save_image")
    save_action.trigger()
    qapp.processEvents()
    assert calls == [str(Path(win.image_dir) / "new_image.img")]
    assert win._image_source == str(new_path)
    assert new_path.is_file()

    Path(win._image_workdir, "SECOND.TXT").write_bytes(b"second save")
    save_action.trigger()
    qapp.processEvents()
    assert calls == [str(Path(win.image_dir) / "new_image.img")]


@pytest.mark.gui_integration
@pytest.mark.mt("MT-DI19", "FR-180")
def test_remote_image_backup_and_restore_are_confirmed_local_mirrors(
    gui_no_target, monkeypatch, tmp_path, qapp
):
    """Remote-image Backup and Restore mirror temporary folders without serial I/O.

    Verifies: FR-180.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QDialog, QLabel, QPushButton

    win = gui_no_target
    host_dir = tmp_path / "host"
    host_dir.mkdir()
    (host_dir / "OLD1.TXT").write_bytes(b"delete me one")
    (host_dir / "OLD2.COM").write_bytes(b"delete me two")
    win.host_dir = str(host_dir)
    win.refresh_host_files()
    image_path = create_test_image(tmp_path / "mirror.img")
    monkeypatch.setattr(
        "cpm_fm.gui.mw_disk_image.QFileDialog.getOpenFileName",
        lambda *args, **kwargs: (str(image_path), ""),
    )
    monkeypatch.setattr(
        "cpm_fm.gui.mw_disk_image._DiskImageMixin._prompt_mount_side",
        lambda self: "remote",
    )
    monkeypatch.setattr(
        win,
        "_transfer_to_remote_batch",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("Remote-image Restore must not use serial")
        ),
    )
    monkeypatch.setattr(
        win,
        "_transfer_to_host_batch",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("Remote-image Backup must not use serial")
        ),
    )
    _action(win, "menu.file.open_image").trigger()
    qapp.processEvents()

    confirmations: list[dict[str, object]] = []

    def accept_confirmation(dialog):
        dialog.show()
        qapp.processEvents()
        button_row = dialog.layout().itemAt(dialog.layout().count() - 1).layout()
        buttons = [
            button_row.itemAt(index).widget()
            for index in range(button_row.count())
            if isinstance(button_row.itemAt(index).widget(), QPushButton)
        ]
        confirmations.append(
            {
                "title": dialog.windowTitle(),
                "labels": [label.text() for label in dialog.findChildren(QLabel) if label.text()],
                "buttons": [button.text() for button in buttons],
                "defaults": [button.text() for button in buttons if button.isDefault()],
            }
        )
        proceed = next(button for button in buttons if button.text() == i18n.tr("button.continue"))
        QTest.mouseClick(proceed, Qt.MouseButton.LeftButton)
        return dialog.result()

    monkeypatch.setattr(QDialog, "exec", accept_confirmation)
    _action(win, "toolbar.backup").trigger()
    qapp.processEvents()

    assert sorted(path.name for path in host_dir.iterdir()) == [
        "BINARY.DAT",
        "DATA.TXT",
        "HELLO.COM",
        "LARGE.BIN",
    ]
    assert (host_dir / "HELLO.COM").read_bytes().startswith(b"print('Hello from CP/M')")
    assert win._transfer_dialog is None
    assert win.serial_mgr.terminal_connected is False
    assert win.serial_mgr.transport_connected is False

    for path in list(host_dir.iterdir()):
        path.unlink()
    restore_payloads = {
        "RESTORE1.TXT": b"restore one\r\n",
        "RESTORE2.COM": b"restore two\r\n",
    }
    for name, payload in restore_payloads.items():
        (host_dir / name).write_bytes(payload)
    win.refresh_host_files()
    _action(win, "toolbar.restore").trigger()
    qapp.processEvents()

    assert len(confirmations) == 2
    assert confirmations[0] == {
        "title": i18n.tr("dialog.backup_restore.backup_title"),
        "labels": [i18n.tr("dialog.backup_restore.backup")],
        "buttons": [i18n.tr("button.cancel"), i18n.tr("button.continue")],
        "defaults": [i18n.tr("button.cancel")],
    }
    assert confirmations[1] == {
        "title": i18n.tr("dialog.backup_restore.restore_title"),
        "labels": [i18n.tr("dialog.backup_restore.restore")],
        "buttons": [i18n.tr("button.cancel"), i18n.tr("button.continue")],
        "defaults": [i18n.tr("button.cancel")],
    }
    assert win._image_workdir is not None
    assert sorted(path.name for path in Path(win._image_workdir).iterdir()) == sorted(
        restore_payloads
    )
    assert {
        name: Path(win._image_workdir, name).read_bytes() for name in restore_payloads
    } == restore_payloads
    remote_names = {
        win.remote_list.item(row).data(Qt.ItemDataRole.UserRole)
        for row in range(win.remote_list.count())
    }
    assert remote_names == set(restore_payloads)
    assert win._image_is_dirty()
    assert win._transfer_dialog is None


@pytest.mark.gui_integration
@pytest.mark.mt("MT-DI20", "FR-185", "FR-186", "UIR-119")
def test_multi_area_image_disambiguates_names_and_details(
    gui_no_target, monkeypatch, tmp_path, qapp
):
    """Multi-area rows, staged names, contents, and details retain user identity.

    Verifies: FR-185, FR-186, UIR-119.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QAbstractItemView, QDialog, QPushButton, QTableWidget

    win = gui_no_target
    payloads = {
        0: {"SHARED.TXT": b"area zero payload", "ZERO.COM": b"zero payload"},
        3: {"SHARED.TXT": b"area three payload", "THREE.COM": b"three payload"},
    }
    image_path = create_multi_area_image(tmp_path / "multi-area.img", payloads)
    _choose_host_image(monkeypatch, image_path)
    _action(win, "menu.file.open_image").trigger()
    qapp.processEvents()

    displayed = {
        win.host_list.item(row).data(Qt.ItemDataRole.UserRole): win.host_list.item(row).text()
        for row in range(win.host_list.count())
    }
    assert displayed == {
        "SHARED.TXT": "U0  SHARED.TXT",
        "SHARED~3.TXT": "U3  SHARED~3.TXT",
        "THREE.COM": "U3  THREE.COM",
        "ZERO.COM": "U0  ZERO.COM",
    }
    assert win._image_stage_map == {
        "SHARED.TXT": ("SHARED.TXT", 0),
        "SHARED~3.TXT": ("SHARED.TXT", 3),
        "THREE.COM": ("THREE.COM", 3),
        "ZERO.COM": ("ZERO.COM", 0),
    }
    workdir = Path(win.host_dir)
    staged_payloads = {
        "SHARED.TXT": payloads[0]["SHARED.TXT"],
        "SHARED~3.TXT": payloads[3]["SHARED.TXT"],
        "THREE.COM": payloads[3]["THREE.COM"],
        "ZERO.COM": payloads[0]["ZERO.COM"],
    }
    for staged_name, payload in staged_payloads.items():
        data = (workdir / staged_name).read_bytes()
        assert data.startswith(payload)
        assert data[len(payload) :] == b"\x00" * (len(data) - len(payload))

    observed: dict[str, object] = {}

    def inspect_and_close(dialog):
        dialog.show()
        qapp.processEvents()
        table = dialog.findChild(QTableWidget)
        assert table is not None
        observed["entries"] = {
            (table.item(row, 0).text(), table.item(row, 2).text())
            for row in range(table.rowCount())
        }
        observed["edit_triggers"] = table.editTriggers()
        close_button = next(
            button
            for button in dialog.findChildren(QPushButton)
            if button.text() == i18n.tr("dialog.image_details.close")
        )
        QTest.mouseClick(close_button, Qt.MouseButton.LeftButton)
        return dialog.result()

    monkeypatch.setattr(QDialog, "exec", inspect_and_close)
    _action(win, "menu.file.image_details").trigger()

    assert observed == {
        "entries": {
            ("SHARED.TXT", "0"),
            ("SHARED.TXT", "3"),
            ("THREE.COM", "3"),
            ("ZERO.COM", "0"),
        },
        "edit_triggers": QAbstractItemView.EditTrigger.NoEditTriggers,
    }


@pytest.mark.gui_integration
@pytest.mark.mt("MT-DI21", "FR-187")
def test_multi_area_save_reopen_preserves_areas_and_content(
    gui_no_target, monkeypatch, tmp_path, qapp
):
    """Saving and reopening preserves duplicate names in their user areas.

    Verifies: FR-187.
    """
    from cpm_fm.utils.disk_image import open_image

    win = gui_no_target
    payloads = {
        0: {"SHARED.TXT": b"saved area zero"},
        3: {"SHARED.TXT": b"saved area three", "THREE.COM": b"saved unique file"},
    }
    image_path = create_multi_area_image(tmp_path / "multi-area-save.img", payloads)
    _choose_host_image(monkeypatch, image_path)
    _action(win, "menu.file.open_image").trigger()
    qapp.processEvents()

    _action(win, "menu.file.save_image").trigger()
    qapp.processEvents()
    _action(win, "menu.file.close_image").trigger()
    qapp.processEvents()
    _action(win, "menu.file.open_image").trigger()
    qapp.processEvents()

    assert win._image_stage_map == {
        "SHARED.TXT": ("SHARED.TXT", 0),
        "SHARED~3.TXT": ("SHARED.TXT", 3),
        "THREE.COM": ("THREE.COM", 3),
    }
    reopened = open_image(image_path)
    assert reopened is not None
    assert {(entry.name, entry.user) for entry in reopened.list_files()} == {
        ("SHARED.TXT", 0),
        ("SHARED.TXT", 3),
        ("THREE.COM", 3),
    }
    for area, files in payloads.items():
        for name, payload in files.items():
            data = reopened.read_file(name, user=area)
            assert data.startswith(payload)
            assert data[len(payload) :] == b"\x00" * (len(data) - len(payload))


@pytest.mark.gui_integration
@pytest.mark.mt("MT-DI22", "FR-189", "UIR-120")
@pytest.mark.parametrize("mount", ["host", "remote"])
def test_image_area_filter_scopes_combines_and_resets(
    gui_no_target, monkeypatch, tmp_path, qapp, mount
):
    """The mounted pane's area filter composes with filtering and resets on close.

    Verifies: FR-189, UIR-120.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    win = gui_no_target
    payloads = {
        0: {"HOME.COM": b"home", "ROOT.SYS": b"root"},
        3: {
            "GAME.COM": b"game",
            "README.TXT": b"readme",
            "THIRD.BIN": b"third",
        },
        7: {"SEVEN.DAT": b"seven"},
    }
    image_path = create_multi_area_image(tmp_path / f"area-filter-{mount}.img", payloads)
    monkeypatch.setattr(
        "cpm_fm.gui.mw_disk_image.QFileDialog.getOpenFileName",
        lambda *args, **kwargs: (str(image_path), ""),
    )
    monkeypatch.setattr(
        "cpm_fm.gui.mw_disk_image._DiskImageMixin._prompt_mount_side",
        lambda self: mount,
    )
    _action(win, "menu.file.open_image").trigger()
    qapp.processEvents()

    combo = win.host_area_filter if mount == "host" else win.remote_area_filter
    other_combo = win.remote_area_filter if mount == "host" else win.host_area_filter
    list_widget = win.host_list if mount == "host" else win.remote_list
    filter_edit = win.host_filter if mount == "host" else win.remote_filter
    sort_dir = win.host_sort_dir_btn if mount == "host" else win.remote_sort_dir_btn

    def visible_names() -> list[str]:
        return [
            list_widget.item(row).data(Qt.ItemDataRole.UserRole)
            for row in range(list_widget.count())
        ]

    assert not combo.isHidden()
    assert [combo.itemData(index) for index in range(combo.count())] == [None, 0, 3, 7]
    assert [combo.itemText(index) for index in range(combo.count())] == [
        i18n.tr("main.area_filter_all"),
        "U0",
        "U3",
        "U7",
    ]
    assert combo.currentData() is None
    assert other_combo.isHidden()
    assert other_combo.count() == 0
    assert set(visible_names()) == {
        "GAME.COM",
        "HOME.COM",
        "README.TXT",
        "ROOT.SYS",
        "SEVEN.DAT",
        "THIRD.BIN",
    }

    combo.setCurrentIndex(combo.findData(3))
    qapp.processEvents()
    assert visible_names() == ["GAME.COM", "README.TXT", "THIRD.BIN"]

    filter_edit.setText("m")
    sort_dir.setChecked(True)
    QTest.qWait(200)
    qapp.processEvents()
    assert visible_names() == ["README.TXT", "GAME.COM"]

    workdir = Path(win._image_workdir)
    staged_before = {path.name: path.read_bytes() for path in workdir.iterdir()}
    stage_map_before = dict(win._image_stage_map)
    combo.setCurrentIndex(combo.findData(None))
    qapp.processEvents()
    assert visible_names() == ["README.TXT", "HOME.COM", "GAME.COM"]
    assert {path.name: path.read_bytes() for path in workdir.iterdir()} == staged_before
    assert win._image_stage_map == stage_map_before
    assert win._transfer_dialog is None
    assert win.serial_mgr.terminal_connected is False
    assert win.serial_mgr.transport_connected is False

    filter_edit.clear()
    sort_dir.setChecked(False)
    QTest.qWait(200)
    _action(win, "menu.file.close_image").trigger()
    qapp.processEvents()

    assert combo.isHidden()
    assert combo.count() == 0
    assert combo.currentData() is None
    assert workdir.exists() is False
