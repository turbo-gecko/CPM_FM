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
