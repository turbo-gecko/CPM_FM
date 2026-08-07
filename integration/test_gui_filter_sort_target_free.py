"""Target-free real-widget file-list filter and sort workflows."""

from __future__ import annotations

import pytest


def _visible_names(list_widget) -> list[str]:
    """Return the displayed file names in their current on-screen order."""
    return [list_widget.item(row).text() for row in range(list_widget.count())]


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
