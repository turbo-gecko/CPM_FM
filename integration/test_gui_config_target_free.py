"""Target-free real-widget General, Terminal, and Remote Config workflows."""

from __future__ import annotations

import pytest

from cpm_fm.utils import i18n


def _action(win, key: str):
    """Return the translated QAction registered for ``key``."""
    from PySide6.QtGui import QAction

    text = i18n.tr(key)
    return next(action for action in win.findChildren(QAction) if action.text() == text)


def _capture_dialog(monkeypatch, win, action_key: str):
    """Open a config action and return its real dialog without blocking."""
    from PySide6.QtWidgets import QDialog

    captured: dict[str, QDialog] = {}

    def capture(dialog):
        captured["dialog"] = dialog
        return QDialog.Rejected

    monkeypatch.setattr(QDialog, "exec", capture)
    _action(win, action_key).trigger()
    return captured["dialog"]


@pytest.mark.gui_integration
@pytest.mark.mt("MT-G01", "FR-021", "UIR-040", "UIR-041", "UIR-044", "UIR-117")
def test_general_config_action_opens_flat_scrollable_two_column_dialog(gui_no_target, monkeypatch):
    """General Config has the required modal flat form and fixed button row.

    Verifies: FR-021, UIR-040, UIR-041, UIR-044, UIR-117.
    """
    from PySide6.QtWidgets import QFormLayout, QGroupBox, QPushButton, QScrollArea

    dialog = _capture_dialog(monkeypatch, gui_no_target, "menu.config.general")
    scroll = dialog.findChild(QScrollArea)
    assert dialog.windowTitle() == i18n.tr("config.general.title")
    assert dialog.isModal()
    assert dialog.findChildren(QGroupBox) == []
    assert scroll is not None and scroll.widgetResizable()

    form = scroll.widget().layout().itemAt(0).layout()
    assert isinstance(form, QFormLayout)
    assert [
        form.itemAt(row, QFormLayout.ItemRole.LabelRole).widget().text()
        for row in range(form.rowCount())
    ] == [
        i18n.tr("config.general.debug_logging"),
        i18n.tr("config.general.viewer"),
        i18n.tr("config.general.host_directory"),
        i18n.tr("config.general.image_directory"),
    ]
    assert all(
        form.itemAt(row, QFormLayout.ItemRole.FieldRole) is not None
        for row in range(form.rowCount())
    )
    assert dialog.layout().indexOf(scroll) >= 0
    assert [button.text() for button in dialog.findChildren(QPushButton)][-2:] == [
        i18n.tr("button.cancel"),
        i18n.tr("button.save"),
    ]


@pytest.mark.gui_integration
@pytest.mark.mt("MT-G05", "UIR-050")
def test_general_debug_logging_has_exact_options_and_default(gui_no_target, monkeypatch):
    """Debug Logging offers OFF/ON and defaults to OFF.

    Verifies: UIR-050.
    """
    dialog = _capture_dialog(monkeypatch, gui_no_target, "menu.config.general")
    combo = dialog.entries["debug_logging"]
    assert [combo.itemText(index) for index in range(combo.count())] == ["OFF", "ON"]
    assert combo.currentText() == "OFF"


@pytest.mark.gui_integration
@pytest.mark.mt("MT-G06", "UIR-053")
def test_general_host_directory_browse_populates_selected_path(
    gui_no_target, monkeypatch, tmp_path
):
    """The Host Directory browse button uses the chosen folder.

    Verifies: UIR-053.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QPushButton

    selected = tmp_path / "host-choice"
    selected.mkdir()
    calls: list[tuple[str, str]] = []

    def choose_directory(parent, title, current):
        calls.append((title, current))
        return str(selected)

    monkeypatch.setattr(
        "cpm_fm.gui.config_dialogs.QFileDialog.getExistingDirectory",
        choose_directory,
    )
    dialog = _capture_dialog(monkeypatch, gui_no_target, "menu.config.general")
    edit = dialog.entries["host_directory"]
    browse = next(
        button for button in edit.parentWidget().findChildren(QPushButton) if button.text() == "..."
    )
    QTest.mouseClick(browse, Qt.MouseButton.LeftButton)

    assert calls == [(i18n.tr("dialog.select_directory.title"), "")]
    assert edit.text() == str(selected)


@pytest.mark.gui_integration
@pytest.mark.mt("MT-G07", "UIR-054")
def test_general_viewer_editor_has_documented_default(gui_no_target, monkeypatch):
    """Viewer/Editor defaults to the documented substitution command.

    Verifies: UIR-054.
    """
    dialog = _capture_dialog(monkeypatch, gui_no_target, "menu.config.general")
    assert dialog.entries["viewer_cmd"].text() == "notepad $1"


@pytest.mark.gui_integration
@pytest.mark.mt("MT-G08", "UIR-043")
def test_general_config_has_no_withdrawn_change_disk_field(gui_no_target, monkeypatch):
    """The withdrawn Change Disk setting is absent from the real dialog.

    Verifies: UIR-043.
    """
    dialog = _capture_dialog(monkeypatch, gui_no_target, "menu.config.general")
    assert set(dialog.entries) == {
        "debug_logging",
        "viewer_cmd",
        "host_directory",
        "image_directory",
    }
    assert "change_disk_cmd" not in dialog.entries


@pytest.mark.gui_integration
@pytest.mark.mt("MT-G15", "UIR-115")
def test_general_image_directory_browse_populates_selected_path(
    gui_no_target, monkeypatch, tmp_path
):
    """The Image Directory browse button uses the chosen folder.

    Verifies: UIR-115.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QPushButton

    selected = tmp_path / "image-choice"
    selected.mkdir()
    calls: list[tuple[str, str]] = []

    def choose_directory(parent, title, current):
        calls.append((title, current))
        return str(selected)

    monkeypatch.setattr(
        "cpm_fm.gui.config_dialogs.QFileDialog.getExistingDirectory",
        choose_directory,
    )
    dialog = _capture_dialog(monkeypatch, gui_no_target, "menu.config.general")
    edit = dialog.entries["image_directory"]
    browse = next(
        button for button in edit.parentWidget().findChildren(QPushButton) if button.text() == "..."
    )
    QTest.mouseClick(browse, Qt.MouseButton.LeftButton)

    assert calls == [(i18n.tr("dialog.select_directory.title"), "")]
    assert edit.text() == str(selected)


@pytest.mark.gui_integration
@pytest.mark.mt("MT-G03", "UIR-047", "UIR-048")
def test_terminal_end_of_line_has_exact_options_and_default(gui_no_target, monkeypatch):
    """End of Line offers CR/LF/CRLF and defaults to CR.

    Verifies: UIR-047, UIR-048.
    """
    dialog = _capture_dialog(monkeypatch, gui_no_target, "menu.config.terminal")
    combo = dialog.entries["eol"]
    assert [combo.itemText(index) for index in range(combo.count())] == ["CR", "LF", "CRLF"]
    assert combo.currentText() == "CR"


@pytest.mark.gui_integration
@pytest.mark.mt("MT-G09", "UIR-058")
def test_terminal_transfer_echo_has_exact_options_and_default(gui_no_target, monkeypatch):
    """Echo Transfer Data offers OFF/ON and defaults to OFF.

    Verifies: UIR-058.
    """
    dialog = _capture_dialog(monkeypatch, gui_no_target, "menu.config.terminal")
    combo = dialog.entries["echo_transfer_data"]
    assert [combo.itemText(index) for index in range(combo.count())] == ["OFF", "ON"]
    assert combo.currentText() == "OFF"


@pytest.mark.gui_integration
@pytest.mark.mt("MT-G12", "FR-021c", "UIR-003", "UIR-103", "UIR-103a", "UIR-103d")
def test_terminal_config_menu_and_two_level_tab_structure(gui_no_target, monkeypatch):
    """Config ordering and Terminal/Macros widgets match the real dialog contract.

    Verifies: FR-021c, UIR-003, UIR-103, UIR-103a, UIR-103d.
    """
    from PySide6.QtWidgets import (
        QCheckBox,
        QLineEdit,
        QMenu,
        QPlainTextEdit,
        QPushButton,
        QTabWidget,
    )

    win = gui_no_target
    config_menu = next(
        menu for menu in win.findChildren(QMenu) if menu.title() == i18n.tr("menu.config")
    )
    assert [action.text() for action in config_menu.actions() if not action.isSeparator()] == [
        i18n.tr("menu.file.new"),
        i18n.tr("menu.file.load"),
        i18n.tr("menu.file.save"),
        i18n.tr("menu.config.serial"),
        i18n.tr("menu.config.terminal"),
        i18n.tr("menu.config.general"),
        i18n.tr("menu.config.remote"),
        i18n.tr("menu.config.language"),
    ]

    dialog = _capture_dialog(monkeypatch, win, "menu.config.terminal")
    outer_tabs = dialog.findChild(QTabWidget)
    assert dialog.windowTitle() == i18n.tr("config.terminal.title")
    assert dialog.isModal()
    assert dialog.minimumSize() != dialog.maximumSize()
    assert [outer_tabs.tabText(index) for index in range(outer_tabs.count())] == [
        i18n.tr("config.terminal.tab.terminal"),
        i18n.tr("config.terminal.tab.macros"),
    ]
    terminal_type = dialog.entries["terminal_type"]
    assert [terminal_type.itemText(index) for index in range(terminal_type.count())] == [
        "VT100",
        "VT52",
        "ADM-3A",
    ]
    assert terminal_type.currentText() == "VT100"
    assert isinstance(dialog.entries["local_echo"], QCheckBox)
    assert dialog.entries["local_echo"].isChecked() is False
    assert isinstance(dialog.entries["autoscroll"], QCheckBox)
    assert dialog.entries["autoscroll"].isChecked() is True

    macro_tabs = outer_tabs.widget(1).findChild(QTabWidget)
    assert [macro_tabs.tabText(index) for index in range(macro_tabs.count())] == [
        i18n.tr("config.macros.macro", n=index) for index in range(1, 11)
    ]
    for index in range(macro_tabs.count()):
        page = macro_tabs.widget(index)
        assert len(page.findChildren(QLineEdit)) == 1
        assert len(page.findChildren(QPlainTextEdit)) == 1
        assert [button.text() for button in page.findChildren(QPushButton)] == [
            i18n.tr("button.test")
        ]


@pytest.mark.gui_integration
@pytest.mark.mt("MT-G12a", "FR-021c", "UIR-034", "UIR-103b", "UIR-103c")
def test_terminal_settings_round_trip_subset_and_no_file_warning(
    gui_no_target, monkeypatch, tmp_path
):
    """Terminal settings round-trip, save only their subset, and warn without a file.

    Verifies: FR-021c, UIR-034, UIR-103b, UIR-103c.
    """
    import json

    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QPushButton

    win = gui_no_target
    config_path = tmp_path / "terminal-settings.json"
    original = {
        "terminal_port": "COM1",
        "debug_logging": "ON",
        "list_files_cmd": "LS",
        "terminal_type": "VT100",
        "local_echo": "OFF",
        "autoscroll": "ON",
    }
    config_path.write_text(json.dumps(original), encoding="utf-8")
    win.load_config(str(config_path))
    monkeypatch.setattr(
        "cpm_fm.gui.mw_config.QFileDialog.getSaveFileName",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("Terminal dialog Save must not open a file picker")
        ),
    )

    first = _capture_dialog(monkeypatch, win, "menu.config.terminal")
    first.entries["terminal_type"].setCurrentText("ADM-3A")
    first.entries["local_echo"].setChecked(True)
    first.entries["autoscroll"].setChecked(False)
    save = next(
        button
        for button in first.findChildren(QPushButton)
        if button.text() == i18n.tr("button.save")
    )
    QTest.mouseClick(save, Qt.MouseButton.LeftButton)

    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert {key: saved[key] for key in ("terminal_port", "debug_logging", "list_files_cmd")} == {
        "terminal_port": "COM1",
        "debug_logging": "ON",
        "list_files_cmd": "LS",
    }
    assert {key: saved[key] for key in ("terminal_type", "local_echo", "autoscroll")} == {
        "terminal_type": "ADM-3A",
        "local_echo": "ON",
        "autoscroll": "OFF",
    }
    assert win._term_engine.terminal_type == "ADM-3A"
    assert win._local_echo is True

    reopened = _capture_dialog(monkeypatch, win, "menu.config.terminal")
    assert reopened.entries["terminal_type"].currentText() == "ADM-3A"
    assert reopened.entries["local_echo"].isChecked() is True
    assert reopened.entries["autoscroll"].isChecked() is False

    before_no_file = config_path.read_bytes()
    warnings: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "cpm_fm.gui.mw_config.QMessageBox.warning",
        lambda parent, title, message: warnings.append((title, message)),
    )
    win.window_state.last_config = ""
    no_file = _capture_dialog(monkeypatch, win, "menu.config.terminal")
    no_file.entries["terminal_type"].setCurrentText("VT52")
    no_file_save = next(
        button
        for button in no_file.findChildren(QPushButton)
        if button.text() == i18n.tr("button.save")
    )
    QTest.mouseClick(no_file_save, Qt.MouseButton.LeftButton)

    assert warnings == [(i18n.tr("dialog.warning.title"), i18n.tr("warning.no_config_loaded"))]
    assert win.settings["terminal_type"] == "VT52"
    assert config_path.read_bytes() == before_no_file


@pytest.mark.gui_integration
@pytest.mark.mt("MT-G13", "FR-021b", "FR-021c", "UIR-098", "UIR-103d")
def test_terminal_macro_labels_and_scripts_save_and_reopen(gui_no_target, monkeypatch, tmp_path):
    """Macro labels and multiline scripts persist verbatim through the real dialog.

    Verifies: FR-021b, FR-021c, UIR-098, UIR-103d.
    """
    import json

    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QPushButton

    win = gui_no_target
    config_path = tmp_path / "macro-settings.json"
    config_path.write_text(json.dumps({"terminal_port": "COM1"}), encoding="utf-8")
    win.load_config(str(config_path))

    dialog = _capture_dialog(monkeypatch, win, "menu.config.terminal")
    expected = {
        "macro_1_label": "Dir",
        "macro_1_seq": "SEND DIR",
        "macro_2_label": "Reset",
        "macro_2_seq": "SENDRAW 03",
    }
    for key, value in expected.items():
        widget = dialog.entries[key]
        if key.endswith("_seq"):
            widget.setPlainText(value)
        else:
            widget.setText(value)
    save = next(
        button
        for button in dialog.findChildren(QPushButton)
        if button.text() == i18n.tr("button.save")
    )
    QTest.mouseClick(save, Qt.MouseButton.LeftButton)

    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert {key: saved[key] for key in expected} == expected
    assert saved["terminal_port"] == "COM1"

    reopened = _capture_dialog(monkeypatch, win, "menu.config.terminal")
    assert reopened.entries["macro_1_label"].text() == "Dir"
    assert reopened.entries["macro_1_seq"].toPlainText() == "SEND DIR"
    assert reopened.entries["macro_2_label"].text() == "Reset"
    assert reopened.entries["macro_2_seq"].toPlainText() == "SENDRAW 03"


@pytest.mark.gui_integration
@pytest.mark.mt("MT-G20", "FR-021d", "UIR-003", "UIR-116", "UIR-117")
def test_remote_config_action_opens_complete_flat_scrollable_dialog(gui_no_target, monkeypatch):
    """Remote Config presents its complete ordered field set without groups.

    Verifies: FR-021d, UIR-003, UIR-116, UIR-117.
    """
    from PySide6.QtWidgets import QGroupBox, QPushButton, QScrollArea

    dialog = _capture_dialog(monkeypatch, gui_no_target, "menu.config.remote")
    scroll = dialog.findChild(QScrollArea)
    assert dialog.windowTitle() == i18n.tr("config.remote.title")
    assert dialog.isModal()
    assert dialog.findChildren(QGroupBox) == []
    assert scroll is not None and scroll.widgetResizable()
    assert list(dialog.entries) == [
        "list_files_cmd",
        "recv_remote_cmd",
        "send_remote_cmd",
        "xmodem_1k",
        "recv_remote_cmd_1k",
        "send_remote_cmd_1k",
        "rename_remote_cmd",
        "delete_remote_cmd",
        "erase_all_remote_seq",
        "xfer_launch_delay",
        "xfer_handshake_timeout",
        "xfer_interfile_delay",
        "boot_sequence",
    ]
    assert [button.text() for button in dialog.findChildren(QPushButton)] == [
        i18n.tr("button.test"),
        i18n.tr("button.test"),
        i18n.tr("button.cancel"),
        i18n.tr("button.save"),
    ]
    assert dialog.layout().indexOf(scroll) >= 0


@pytest.mark.gui_integration
@pytest.mark.mt("MT-G02", "UIR-042", "UIR-045", "UIR-046")
def test_remote_primary_commands_have_defaults_and_length_limits(gui_no_target, monkeypatch):
    """List/receive/send commands expose exact defaults and 79-character limits.

    Verifies: UIR-042, UIR-045, UIR-046.
    """
    dialog = _capture_dialog(monkeypatch, gui_no_target, "menu.config.remote")
    expected = {
        "list_files_cmd": "DIR",
        "recv_remote_cmd": "PCPUT $1",
        "send_remote_cmd": "PCGET $1",
    }
    for key, default in expected.items():
        edit = dialog.entries[key]
        assert edit.text() == default
        assert edit.maxLength() == 79


@pytest.mark.gui_integration
@pytest.mark.mt("MT-G21", "UIR-055", "UIR-056")
def test_remote_rename_delete_labels_defaults_and_limits(gui_no_target, monkeypatch):
    """Rename/Delete use concise labels, exact commands, and 79-character limits.

    Verifies: UIR-055, UIR-056.
    """
    from PySide6.QtWidgets import QLabel

    dialog = _capture_dialog(monkeypatch, gui_no_target, "menu.config.remote")
    expected = {
        "rename_remote_cmd": (i18n.tr("config.remote.rename_remote"), "REN $2=$1"),
        "delete_remote_cmd": (i18n.tr("config.remote.delete_remote"), "ERA $1"),
    }
    labels = [label.text() for label in dialog.findChildren(QLabel)]
    for key, (label, default) in expected.items():
        edit = dialog.entries[key]
        assert labels.count(label) == 1
        assert edit.text() == default
        assert edit.maxLength() == 79


@pytest.mark.gui_integration
@pytest.mark.mt("MT-G22", "UIR-089", "UIR-090")
def test_remote_xmodem_1k_defaults_and_saved_toggle_round_trip(
    gui_no_target, monkeypatch, tmp_path
):
    """XMODEM-1K starts off with blank commands and persists when enabled.

    Verifies: UIR-089, UIR-090.
    """
    import json

    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QPushButton

    win = gui_no_target
    config_path = tmp_path / "xmodem-1k.json"
    config_path.write_text(json.dumps({"unrelated": "keep"}), encoding="utf-8")
    win.load_config(str(config_path))

    dialog = _capture_dialog(monkeypatch, win, "menu.config.remote")
    toggle = dialog.entries["xmodem_1k"]
    assert toggle.isChecked() is False
    for key in ("recv_remote_cmd_1k", "send_remote_cmd_1k"):
        edit = dialog.entries[key]
        assert edit.text() == ""
        assert edit.maxLength() == 79
    toggle.setChecked(True)
    save = next(
        button
        for button in dialog.findChildren(QPushButton)
        if button.text() == i18n.tr("button.save")
    )
    QTest.mouseClick(save, Qt.MouseButton.LeftButton)

    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["xmodem_1k"] == "ON"
    assert saved["unrelated"] == "keep"
    reopened = _capture_dialog(monkeypatch, win, "menu.config.remote")
    assert reopened.entries["xmodem_1k"].isChecked() is True


@pytest.mark.gui_integration
@pytest.mark.mt("MT-G04", "UIR-049", "UIR-052", "UIR-093")
def test_remote_transfer_timing_fields_enforce_documented_ranges(gui_no_target, monkeypatch):
    """Transfer timing fields expose exact defaults and bounded integer input.

    Verifies: UIR-049, UIR-052, UIR-093.
    """
    from PySide6.QtTest import QTest

    dialog = _capture_dialog(monkeypatch, gui_no_target, "menu.config.remote")
    expected = {
        "xfer_launch_delay": (0, 60, "3"),
        "xfer_handshake_timeout": (1, 60, "10"),
        "xfer_interfile_delay": (0, 60, "2"),
    }
    for key, (minimum, maximum, default) in expected.items():
        edit = dialog.entries[key]
        validator = edit.validator()
        assert edit.text() == default
        assert validator.bottom() == minimum
        assert validator.top() == maximum
        edit.clear()
        QTest.keyClicks(edit, str(minimum))
        assert edit.text() == str(minimum)
        edit.clear()
        QTest.keyClicks(edit, str(maximum))
        assert edit.text() == str(maximum)
        edit.clear()
        QTest.keyClicks(edit, str(maximum + 1))
        assert edit.text() != str(maximum + 1)


@pytest.mark.gui_integration
@pytest.mark.mt("MT-G10", "UIR-059")
def test_remote_boot_sequence_multiline_text_saves_and_reopens(
    gui_no_target, monkeypatch, tmp_path
):
    """Boot Sequence is last, multiline, empty by default, and persists verbatim.

    Verifies: UIR-059.
    """
    import json

    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QPlainTextEdit, QPushButton

    win = gui_no_target
    config_path = tmp_path / "boot-sequence.json"
    config_path.write_text(json.dumps({"unrelated": "keep"}), encoding="utf-8")
    win.load_config(str(config_path))

    dialog = _capture_dialog(monkeypatch, win, "menu.config.remote")
    editor = dialog.entries["boot_sequence"]
    script = "WAITFOR Boot:\nSEND \nWAIT 1"
    assert list(dialog.entries)[-1] == "boot_sequence"
    assert isinstance(editor, QPlainTextEdit)
    assert editor.toPlainText() == ""
    editor.setPlainText(script)
    save = next(
        button
        for button in dialog.findChildren(QPushButton)
        if button.text() == i18n.tr("button.save")
    )
    QTest.mouseClick(save, Qt.MouseButton.LeftButton)

    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["boot_sequence"] == script
    assert saved["unrelated"] == "keep"
    reopened = _capture_dialog(monkeypatch, win, "menu.config.remote")
    assert reopened.entries["boot_sequence"].toPlainText() == script


@pytest.mark.gui_integration
@pytest.mark.mt("MT-G23", "FR-021d")
def test_remote_save_writes_subset_and_warns_without_active_file(
    gui_no_target, monkeypatch, tmp_path
):
    """Remote Save preserves other groups and becomes session-only without a file.

    Verifies: FR-021d.
    """
    import json

    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QPushButton

    win = gui_no_target
    config_path = tmp_path / "remote-subset.json"
    original = {
        "terminal_port": "COM1",
        "debug_logging": "ON",
        "terminal_type": "VT52",
        "list_files_cmd": "DIR",
    }
    config_path.write_text(json.dumps(original), encoding="utf-8")
    win.load_config(str(config_path))
    monkeypatch.setattr(
        "cpm_fm.gui.mw_config.QFileDialog.getSaveFileName",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("Remote dialog Save must not open a file picker")
        ),
    )

    dialog = _capture_dialog(monkeypatch, win, "menu.config.remote")
    dialog.entries["list_files_cmd"].setText("DIR B:")
    save = next(
        button
        for button in dialog.findChildren(QPushButton)
        if button.text() == i18n.tr("button.save")
    )
    QTest.mouseClick(save, Qt.MouseButton.LeftButton)

    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["list_files_cmd"] == "DIR B:"
    assert {key: saved[key] for key in ("terminal_port", "debug_logging", "terminal_type")} == {
        "terminal_port": "COM1",
        "debug_logging": "ON",
        "terminal_type": "VT52",
    }

    before_no_file = config_path.read_bytes()
    warnings: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "cpm_fm.gui.mw_config.QMessageBox.warning",
        lambda parent, title, message: warnings.append((title, message)),
    )
    win.window_state.last_config = ""
    no_file = _capture_dialog(monkeypatch, win, "menu.config.remote")
    no_file.entries["list_files_cmd"].setText("DIR C:")
    no_file_save = next(
        button
        for button in no_file.findChildren(QPushButton)
        if button.text() == i18n.tr("button.save")
    )
    QTest.mouseClick(no_file_save, Qt.MouseButton.LeftButton)

    assert warnings == [(i18n.tr("dialog.warning.title"), i18n.tr("warning.no_config_loaded"))]
    assert win.settings["list_files_cmd"] == "DIR C:"
    assert config_path.read_bytes() == before_no_file
