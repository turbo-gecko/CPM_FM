"""Target-free real-widget file-list filter and sort workflows."""

from __future__ import annotations

import pytest


def _visible_names(list_widget) -> list[str]:
    """Return the displayed file names in their current on-screen order."""
    return [list_widget.item(row).text() for row in range(list_widget.count())]


def _action(win, key: str):
    """Return the translated QAction registered for ``key``."""
    from PySide6.QtGui import QAction

    from cpm_fm.utils.i18n import tr

    text = tr(key)
    return next(action for action in win.findChildren(QAction) if action.text() == text)


@pytest.mark.gui_integration
@pytest.mark.mt("MT-FS01", "FR-130", "FR-131", "FR-135", "UIR-079")
def test_host_substring_filter_is_case_insensitive_and_clear_restores_all(
    gui_no_target, tmp_path, qapp
):
    """Typing narrows the Host list and the inline clear restores every file.

    Verifies: FR-130, FR-131, FR-135, UIR-079.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QToolButton

    win = gui_no_target
    for name in ("A.TXT", "b.txt", "C.COM", "D.COM", "LICENSE"):
        (tmp_path / name).write_text(name, encoding="ascii")

    win.host_dir = str(tmp_path)
    win.refresh_host_files()
    win.show()
    qapp.processEvents()

    assert _visible_names(win.host_list) == ["A.TXT", "b.txt", "C.COM", "D.COM", "LICENSE"]

    QTest.keyClicks(win.host_filter, "txt")
    QTest.qWait(200)

    assert win.host_filter.text() == "txt"
    assert _visible_names(win.host_list) == ["A.TXT", "b.txt"]

    clear_button = win.host_filter.findChild(QToolButton)
    assert clear_button is not None
    assert clear_button.isVisible()
    QTest.mouseClick(clear_button, Qt.MouseButton.LeftButton)
    QTest.qWait(200)

    assert win.host_filter.text() == ""
    assert _visible_names(win.host_list) == ["A.TXT", "b.txt", "C.COM", "D.COM", "LICENSE"]


@pytest.mark.gui_integration
@pytest.mark.mt("MT-FS02", "FR-131")
def test_host_wildcards_match_the_complete_filename(gui_no_target, tmp_path, qapp):
    """Glob wildcards are case-insensitive, anchored, and honour ``?`` width.

    Verifies: FR-131.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    win = gui_no_target
    for name in (
        "A.TXT",
        "b.txt",
        "AB.TXT",
        "C.COM",
        "D.COM",
        "e.com",
        "NOTE.COM.BAK",
        "LICENSE",
    ):
        (tmp_path / name).write_text(name, encoding="ascii")

    win.host_dir = str(tmp_path)
    win.refresh_host_files()
    win.show()
    qapp.processEvents()

    QTest.keyClicks(win.host_filter, "*.COM")
    QTest.qWait(200)

    assert win.host_filter.text() == "*.COM"
    assert _visible_names(win.host_list) == ["C.COM", "D.COM", "e.com"]

    QTest.keyClick(
        win.host_filter,
        Qt.Key.Key_A,
        Qt.KeyboardModifier.ControlModifier,
    )
    QTest.keyClicks(win.host_filter, "?.TXT")
    QTest.qWait(200)

    assert win.host_filter.text() == "?.TXT"
    assert _visible_names(win.host_list) == ["A.TXT", "b.txt"]


@pytest.mark.gui_integration
@pytest.mark.mt("MT-FS03", "FR-131")
def test_host_filter_debounces_rapid_typing_to_one_150ms_update(gui_no_target, tmp_path, qapp):
    """Rapid typing restarts one 150 ms timer and renders once after the pause.

    Verifies: FR-131.
    """
    from PySide6.QtCore import QTimer
    from PySide6.QtTest import QSignalSpy, QTest

    win = gui_no_target
    for name in ("A.TXT", "B.COM", "NOTE.TXT", "TXTBOOK.DOC"):
        (tmp_path / name).write_text(name, encoding="ascii")

    win.host_dir = str(tmp_path)
    win.refresh_host_files()
    win.show()
    qapp.processEvents()

    full_list = ["A.TXT", "B.COM", "NOTE.TXT", "TXTBOOK.DOC"]
    assert _visible_names(win.host_list) == full_list

    debounce_timers = [
        timer
        for timer in win.findChildren(QTimer)
        if timer.isSingleShot() and timer.interval() == 150
    ]
    assert len(debounce_timers) == 2
    timer_spies = [(timer, QSignalSpy(timer.timeout)) for timer in debounce_timers]

    QTest.keyClicks(win.host_filter, "txt")

    assert win.host_filter.text() == "txt"
    assert _visible_names(win.host_list) == full_list
    assert sum(spy.count() for _timer, spy in timer_spies) == 0

    active = [(timer, spy) for timer, spy in timer_spies if timer.isActive()]
    assert len(active) == 1
    host_timer, host_spy = active[0]
    assert host_timer.interval() == 150
    assert host_timer.isSingleShot()
    assert host_spy.wait(500)
    qapp.processEvents()

    assert host_spy.count() == 1
    assert sum(spy.count() for _timer, spy in timer_spies) == 1
    assert _visible_names(win.host_list) == ["A.TXT", "NOTE.TXT", "TXTBOOK.DOC"]


@pytest.mark.gui_integration
@pytest.mark.mt("MT-FS04", "FR-132", "UIR-080")
def test_host_sort_controls_apply_name_extension_and_direction(gui_no_target, tmp_path, qapp):
    """The real Host controls apply both sort keys and reverse the order.

    Verifies: FR-132, UIR-080.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from cpm_fm.utils.file_filter import SORT_EXTENSION, SORT_NAME

    win = gui_no_target
    for name in ("zeta.COM", "Alpha.TXT", "beta.COM", "LICENSE", "gamma"):
        (tmp_path / name).write_text(name, encoding="ascii")

    win.host_dir = str(tmp_path)
    win.refresh_host_files()
    win.show()
    qapp.processEvents()

    assert win.host_sort_combo.currentData() == SORT_NAME
    assert win.host_sort_dir_btn.isChecked() is False
    assert win.host_sort_dir_btn.text() == "↑"
    assert _visible_names(win.host_list) == [
        "Alpha.TXT",
        "beta.COM",
        "gamma",
        "LICENSE",
        "zeta.COM",
    ]

    win.host_sort_combo.setFocus()
    QTest.keyClick(win.host_sort_combo, Qt.Key.Key_Down)
    qapp.processEvents()

    extension_ascending = ["gamma", "LICENSE", "beta.COM", "zeta.COM", "Alpha.TXT"]
    assert win.host_sort_combo.currentData() == SORT_EXTENSION
    assert _visible_names(win.host_list) == extension_ascending

    QTest.mouseClick(win.host_sort_dir_btn, Qt.MouseButton.LeftButton)
    qapp.processEvents()

    assert win.host_sort_dir_btn.isChecked() is True
    assert win.host_sort_dir_btn.text() == "↓"
    assert _visible_names(win.host_list) == list(reversed(extension_ascending))

    QTest.mouseClick(win.host_sort_dir_btn, Qt.MouseButton.LeftButton)
    qapp.processEvents()

    assert win.host_sort_dir_btn.isChecked() is False
    assert win.host_sort_dir_btn.text() == "↑"
    assert _visible_names(win.host_list) == extension_ascending


@pytest.mark.gui_integration
@pytest.mark.mt("MT-FS05", "FR-133")
def test_host_filter_and_sort_controls_compose_in_one_view(gui_no_target, tmp_path, qapp):
    """Filtering keeps only matches and sorts that subset with current controls.

    Verifies: FR-133.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from cpm_fm.utils.file_filter import SORT_EXTENSION

    win = gui_no_target
    for name in ("zeta.COM", "Alpha.TXT", "beta.COM", "gamma.com", "LICENSE"):
        (tmp_path / name).write_text(name, encoding="ascii")

    win.host_dir = str(tmp_path)
    win.refresh_host_files()
    win.show()
    qapp.processEvents()

    win.host_sort_combo.setFocus()
    QTest.keyClick(win.host_sort_combo, Qt.Key.Key_Down)
    QTest.mouseClick(win.host_sort_dir_btn, Qt.MouseButton.LeftButton)
    qapp.processEvents()

    assert win.host_sort_combo.currentData() == SORT_EXTENSION
    assert win.host_sort_dir_btn.isChecked() is True
    assert _visible_names(win.host_list) == [
        "Alpha.TXT",
        "zeta.COM",
        "gamma.com",
        "beta.COM",
        "LICENSE",
    ]

    QTest.keyClicks(win.host_filter, "*.COM")
    QTest.qWait(200)

    assert win.host_filter.text() == "*.COM"
    assert win.host_sort_combo.currentData() == SORT_EXTENSION
    assert win.host_sort_dir_btn.isChecked() is True
    assert _visible_names(win.host_list) == ["zeta.COM", "gamma.com", "beta.COM"]


@pytest.mark.gui_integration
@pytest.mark.mt("MT-FS06", "FR-135", "UIR-079")
def test_host_active_filter_border_appears_and_clear_removes_it(gui_no_target, tmp_path, qapp):
    """The real filter field visibly marks active input until inline clear.

    Verifies: FR-135, UIR-079.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QToolButton

    win = gui_no_target
    (tmp_path / "A.TXT").write_text("A.TXT", encoding="ascii")
    win.host_dir = str(tmp_path)
    win.refresh_host_files()
    win.show()
    qapp.processEvents()

    assert win.host_filter.text() == ""
    assert win.host_filter.styleSheet() == ""

    QTest.keyClicks(win.host_filter, "txt")
    QTest.qWait(200)

    active_style = "QLineEdit { border: 1px solid #4caf50; }"
    assert win.host_filter.text() == "txt"
    assert win.host_filter.styleSheet() == active_style

    clear_button = win.host_filter.findChild(QToolButton)
    assert clear_button is not None
    assert clear_button.isVisible()
    QTest.mouseClick(clear_button, Qt.MouseButton.LeftButton)
    QTest.qWait(200)

    assert win.host_filter.text() == ""
    assert win.host_filter.styleSheet() == ""


@pytest.mark.gui_integration
@pytest.mark.mt("MT-FS07", "FR-134")
def test_host_and_remote_filter_sort_state_restore_independently(gui_no_target, tmp_path, qapp):
    """A new real window restores each pane's distinct persisted controls.

    Verifies: FR-134.
    """
    from PySide6.QtCore import QSettings, Qt
    from PySide6.QtTest import QTest

    from cpm_fm.app import MainWindow
    from cpm_fm.gui.window_state import WindowState
    from cpm_fm.utils.file_filter import SORT_EXTENSION, SORT_NAME
    from cpm_fm.utils.transfer_history import TransferHistory

    first = gui_no_target
    first.show()
    qapp.processEvents()

    QTest.keyClicks(first.host_filter, "*.COM")
    first.host_sort_combo.setFocus()
    QTest.keyClick(first.host_sort_combo, Qt.Key.Key_Down)
    QTest.mouseClick(first.host_sort_dir_btn, Qt.MouseButton.LeftButton)
    QTest.keyClicks(first.remote_filter, "TXT")
    QTest.qWait(200)

    assert first.host_filter.text() == "*.COM"
    assert first.host_sort_combo.currentData() == SORT_EXTENSION
    assert first.host_sort_dir_btn.isChecked() is True
    assert first.remote_filter.text() == "TXT"
    assert first.remote_sort_combo.currentData() == SORT_NAME
    assert first.remote_sort_dir_btn.isChecked() is False

    first.close()
    qapp.processEvents()

    state_path = tmp_path / "vstate.ini"
    reopened_state = WindowState(QSettings(str(state_path), QSettings.Format.IniFormat))
    reopened_history = TransferHistory(str(tmp_path / "vhistory.json"))
    second = MainWindow(reopened_state, reopened_history)
    try:
        second.show()
        qapp.processEvents()

        assert second.host_filter.text() == "*.COM"
        assert second.host_sort_combo.currentData() == SORT_EXTENSION
        assert second.host_sort_dir_btn.isChecked() is True
        assert second.host_sort_dir_btn.text() == "↓"
        assert second.remote_filter.text() == "TXT"
        assert second.remote_sort_combo.currentData() == SORT_NAME
        assert second.remote_sort_dir_btn.isChecked() is False
        assert second.remote_sort_dir_btn.text() == "↑"
    finally:
        second.close()
        second.deleteLater()
        qapp.processEvents()


@pytest.mark.gui_integration
@pytest.mark.mt("MT-FS08", "FR-135")
@pytest.mark.parametrize("lifecycle", ("disconnect", "load", "new"))
def test_remote_filter_cannot_resurrect_listing_after_lifecycle_clear(
    gui_no_target, monkeypatch, tmp_path, qapp, lifecycle
):
    """Disconnect/load/new clear visible and canonical Remote list state.

    Verifies: FR-135.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    win = gui_no_target
    win.show()
    qapp.processEvents()
    win._update_remote_list_ui({"A.TXT": 1, "B.COM": 1, "C.TXT": 1})

    QTest.keyClicks(win.remote_filter, "TXT")
    QTest.qWait(200)

    assert win._remote_files == ["A.TXT", "B.COM", "C.TXT"]
    assert _visible_names(win.remote_list) == ["A.TXT", "C.TXT"]

    if lifecycle == "disconnect":
        _action(win, "toolbar.disconnect").trigger()
    elif lifecycle == "load":
        replacement = tmp_path / "replacement.json"
        replacement.write_text("{}", encoding="utf-8")
        monkeypatch.setattr(
            "cpm_fm.gui.mw_config.QFileDialog.getOpenFileName",
            lambda *args, **kwargs: (str(replacement), "JSON files (*.json)"),
        )
        _action(win, "menu.file.load").trigger()
    else:
        active = tmp_path / "active.json"
        active.write_text("{}", encoding="utf-8")
        win.window_state.last_config = str(active)
        _action(win, "menu.file.new").trigger()

    assert _visible_names(win.remote_list) == []

    QTest.keyClick(
        win.remote_filter,
        Qt.Key.Key_A,
        Qt.KeyboardModifier.ControlModifier,
    )
    QTest.keyClicks(win.remote_filter, "COM")
    QTest.qWait(200)

    assert win.remote_filter.text() == "COM"
    assert _visible_names(win.remote_list) == []
    assert win._remote_files == []


@pytest.mark.gui_integration
@pytest.mark.mt("MT-FS09", "FR-123", "UIR-080")
def test_language_action_translates_filter_sort_without_changing_keys(
    gui_no_target, tmp_path, qapp
):
    """Translated controls retain semantic keys and continue sorting correctly.

    Verifies: FR-123, UIR-080.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from cpm_fm.utils import i18n
    from cpm_fm.utils.file_filter import SORT_EXTENSION, SORT_NAME

    win = gui_no_target
    for name in ("zeta.COM", "Alpha.TXT", "beta.COM", "LICENSE"):
        (tmp_path / name).write_text(name, encoding="ascii")
    win.host_dir = str(tmp_path)
    win.refresh_host_files()
    win.show()
    qapp.processEvents()

    win.host_sort_combo.setFocus()
    QTest.keyClick(win.host_sort_combo, Qt.Key.Key_Down)
    QTest.mouseClick(win.host_sort_dir_btn, Qt.MouseButton.LeftButton)
    qapp.processEvents()

    extension_descending = ["Alpha.TXT", "zeta.COM", "beta.COM", "LICENSE"]
    assert win.host_sort_combo.currentData() == SORT_EXTENSION
    assert _visible_names(win.host_list) == extension_descending

    english_text = (
        win.host_filter.placeholderText(),
        win.host_filter.toolTip(),
        win.host_sort_combo.itemText(0),
        win.host_sort_combo.itemText(1),
    )
    language = "spanish"
    assert language in i18n.available_languages()
    win._language_actions[language].trigger()
    qapp.processEvents()

    expected_text = (
        i18n.tr("main.filter_placeholder"),
        i18n.tr("main.filter_tooltip"),
        i18n.tr("main.sort.name"),
        i18n.tr("main.sort.extension"),
    )
    assert i18n.current_language() == language
    assert win._language_actions[language].isChecked()
    assert expected_text != english_text
    for filter_edit, sort_combo in (
        (win.host_filter, win.host_sort_combo),
        (win.remote_filter, win.remote_sort_combo),
    ):
        assert (
            filter_edit.placeholderText(),
            filter_edit.toolTip(),
            sort_combo.itemText(0),
            sort_combo.itemText(1),
        ) == expected_text
        assert [sort_combo.itemData(index) for index in range(sort_combo.count())] == [
            SORT_NAME,
            SORT_EXTENSION,
        ]

    assert win.host_sort_combo.currentData() == SORT_EXTENSION
    assert win.host_sort_dir_btn.isChecked() is True
    assert _visible_names(win.host_list) == extension_descending

    win.host_sort_combo.setFocus()
    QTest.keyClick(win.host_sort_combo, Qt.Key.Key_Up)
    qapp.processEvents()

    assert win.host_sort_combo.currentData() == SORT_NAME
    assert _visible_names(win.host_list) == ["zeta.COM", "LICENSE", "beta.COM", "Alpha.TXT"]
