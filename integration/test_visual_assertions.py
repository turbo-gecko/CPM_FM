"""§4/§6/§7/§14/§15 — widget-tree & look-and-feel assertions (MT-S/G/I/V).

No peer required (plan §6): these build the real widgets offscreen and assert the
widget tree / stylesheet / structure, not pixels. Runnable any time, off the
bench. True pixel rendering, OS light/dark follow, and taskbar icon stay manual.
"""

from __future__ import annotations

import re

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMenu, QPushButton

from cpm_fm.version import APP_NAME, REPO_URL, get_version

pytestmark = pytest.mark.visual


@pytest.mark.mt("MT-S01", "FR-125", "UIR-078")
def test_window_title_contains_app_name(vwin):
    """Verifies: FR-125."""
    assert APP_NAME in vwin.windowTitle()


@pytest.mark.mt("MT-S03", "FR-070")
def test_remote_list_empty_at_startup(vwin):
    """Verifies: FR-070."""
    assert vwin.remote_list.count() == 0


@pytest.mark.mt("MT-G01", "UIR-004")
def test_menubar_has_file_and_help(vwin):
    """Verifies: UIR-004."""
    titles = [m.title() for m in vwin.menuBar().findChildren(QMenu)]
    assert "File" in titles and "Help" in titles
    help_menu = next(m for m in vwin.menuBar().findChildren(QMenu) if m.title() == "Help")
    labels = [a.text() for a in help_menu.actions()]
    assert "About" in labels and "Manual" in labels


@pytest.mark.mt("MT-G05", "UIR-017")
def test_drive_combo_lists_a_to_p(vwin):
    """Verifies: UIR-017."""
    items = [vwin.drive_combo.itemText(i) for i in range(vwin.drive_combo.count())]
    assert items == [f"{chr(c)}:" for c in range(ord("A"), ord("P") + 1)]


@pytest.mark.mt("MT-G07", "UIR-018", "UIR-019")
def test_lists_have_context_menus(vwin):
    """Verifies: UIR-018, UIR-019."""
    assert vwin.host_list.contextMenuPolicy() == Qt.ContextMenuPolicy.CustomContextMenu
    assert vwin.remote_list.contextMenuPolicy() == Qt.ContextMenuPolicy.CustomContextMenu


@pytest.mark.mt("MT-G03", "UIR-014")
def test_main_panes_have_push_buttons(vwin):
    """The host and remote panes each expose action push buttons.

    Verifies: UIR-014.
    """
    assert vwin.host_group.findChildren(QPushButton)
    remote_group = vwin.remote_list.parentWidget()
    assert remote_group.findChildren(QPushButton)


@pytest.mark.mt("MT-V08", "UIR-070", "UIR-073")
def test_material_theme_applied(vwin, qapp):
    """A Material stylesheet is applied to the application.

    Verifies: UIR-070, UIR-073.
    """
    assert qapp.styleSheet().strip() != ""


@pytest.mark.mt("MT-I03", "UIR-076")
def test_about_dialog_contents(qapp):
    """Verifies: UIR-076."""
    from PySide6.QtWidgets import QLabel, QPushButton

    from cpm_fm.gui.about_dialog import AboutDialog

    dlg = AboutDialog()
    try:
        text = " ".join(lbl.text() for lbl in dlg.findChildren(QLabel))
        assert APP_NAME in text
        assert f"Version {get_version()}" in text
        assert REPO_URL in text
        assert [b.text() for b in dlg.findChildren(QPushButton)] == ["OK"]
    finally:
        dlg.deleteLater()


@pytest.mark.mt("MT-V09", "UIR-091")
def test_manual_dialog_renders(qapp):
    """Verifies: UIR-091."""
    from cpm_fm.gui.manual_dialog import load_manual_markdown, render_manual_html

    md = load_manual_markdown()
    assert md is not None
    html = render_manual_html(md)
    assert "<html>" in html
    # TOC links resolve to heading anchors.
    heading_ids = set(re.findall(r'<h[1-6][^>]*id="([^"]+)"', html))
    toc_links = re.findall(r"\(#([a-z0-9-]+)\)", md)
    assert toc_links and all(link in heading_ids for link in toc_links)
