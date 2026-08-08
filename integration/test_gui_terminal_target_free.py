"""Target-free real-widget Terminal Window workflows."""

from __future__ import annotations

import pytest

_WINDOW_STATE_PROBE_PREFIX = "__CPM_FM_WINDOW_STATE_PROBE__="


def _action(win, key: str):
    """Return the translated QAction registered on the main toolbar for ``key``."""
    from PySide6.QtWidgets import QToolBar

    from cpm_fm.utils.i18n import tr

    text = tr(key)
    toolbar = win.findChild(QToolBar)
    assert toolbar is not None
    return next(action for action in toolbar.actions() if action.text() == text)


def _terminal_config_dialog(monkeypatch, win, qapp):
    """Open Config > Terminal and capture its real modal dialog."""
    from PySide6.QtWidgets import QDialog, QMenu

    from cpm_fm.utils.i18n import tr

    captured: dict[str, QDialog] = {}

    def capture(dialog):
        captured["dialog"] = dialog
        dialog.show()
        qapp.processEvents()
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(QDialog, "exec", capture)
    config_menu = next(
        menu for menu in win.findChildren(QMenu) if menu.title() == tr("menu.config")
    )
    terminal_text = tr("menu.config.terminal")
    next(action for action in config_menu.actions() if action.text() == terminal_text).trigger()
    return captured["dialog"]


def _remote_config_dialog(monkeypatch, win, qapp):
    """Open Config > Remote and capture its real modal dialog."""
    from PySide6.QtWidgets import QDialog, QMenu

    from cpm_fm.utils.i18n import tr

    captured: dict[str, QDialog] = {}

    def capture(dialog):
        captured["dialog"] = dialog
        dialog.show()
        qapp.processEvents()
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(QDialog, "exec", capture)
    config_menu = next(
        menu for menu in win.findChildren(QMenu) if menu.title() == tr("menu.config")
    )
    remote_text = tr("menu.config.remote")
    next(action for action in config_menu.actions() if action.text() == remote_text).trigger()
    return captured["dialog"]


def _terminal_context_menu_opener(monkeypatch, terminal, qapp):
    """Return a callable that opens and captures the real Receive-view menu."""
    from PySide6.QtCore import QPoint, QTimer
    from PySide6.QtGui import QContextMenuEvent

    menus = []
    build_context_menu = terminal._build_context_menu

    def capture_and_auto_close_menu():
        menu = build_context_menu()
        menus.append(menu)
        QTimer.singleShot(0, menu.close)
        return menu

    monkeypatch.setattr(terminal, "_build_context_menu", capture_and_auto_close_menu)

    def open_menu():
        grid = terminal.receive_area.widget()
        local_pos = QPoint(5, 5)
        event = QContextMenuEvent(
            QContextMenuEvent.Reason.Mouse,
            local_pos,
            grid.mapToGlobal(local_pos),
        )
        previous_count = len(menus)
        qapp.sendEvent(grid, event)
        qapp.processEvents()
        assert len(menus) == previous_count + 1
        return menus[-1]

    return open_menu


def _run_window_state_process_probe(mode: str, state_path: str, history_path: str) -> None:
    """Exercise auxiliary-window persistence in a standalone application process."""
    import json

    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    from cpm_fm.app import MainWindow
    from cpm_fm.gui.window_state import WindowState
    from cpm_fm.utils import i18n
    from cpm_fm.utils.transfer_history import TransferHistory

    i18n.set_language(i18n.DEFAULT_LANGUAGE)
    app = QApplication.instance() or QApplication([])
    state = WindowState(QSettings(state_path, QSettings.Format.IniFormat))
    win = MainWindow(state, TransferHistory(history_path))
    win.show()
    app.processEvents()
    payload: dict[str, object]

    if mode == "open":
        _action(win, "toolbar.terminal").trigger()
        _action(win, "toolbar.history").trigger()
        app.processEvents()
        assert win.terminal_win is not None
        assert win._history_dialog is not None
        payload = {
            "terminal_visible_before_exit": win.terminal_win.isVisible(),
            "history_visible_before_exit": win._history_dialog.isVisible(),
        }
        win.close()
        app.processEvents()
        state._settings.sync()
        payload.update(
            terminal_stored_open=state.window_open("terminal"),
            history_stored_open=state.window_open("history"),
        )
    elif mode == "restore_close":
        terminal = win.terminal_win
        history = win._history_dialog
        payload = {
            "terminal_restored": bool(terminal and terminal.isVisible()),
            "history_restored": bool(history and history.isVisible()),
        }
        assert terminal is not None
        assert history is not None
        terminal.close()
        history.close()
        app.processEvents()
        payload.update(
            terminal_visible_after_close=terminal.isVisible(),
            history_visible_after_close=history.isVisible(),
        )
        win.close()
        app.processEvents()
        state._settings.sync()
        payload.update(
            terminal_stored_open=state.window_open("terminal"),
            history_stored_open=state.window_open("history"),
        )
    elif mode == "verify_closed":
        payload = {
            "terminal_created": win.terminal_win is not None,
            "history_created": win._history_dialog is not None,
            "terminal_stored_open": state.window_open("terminal"),
            "history_stored_open": state.window_open("history"),
        }
        win.close()
        app.processEvents()
    else:  # pragma: no cover - guarded by the parent test
        raise ValueError(f"unknown probe mode: {mode}")

    print(_WINDOW_STATE_PROBE_PREFIX + json.dumps(payload, sort_keys=True))


@pytest.mark.gui_integration
@pytest.mark.mt("MT-W02", "UIR-061", "UIR-063", "UIR-064", "UIR-067", "UIR-106")
def test_terminal_toolbar_opens_character_grid_without_transmit_controls(gui_no_target, qapp):
    """The real Terminal action opens only a fixed-pitch grid and status bar.

    Verifies: UIR-061, UIR-063, UIR-064, UIR-067, UIR-106.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import (
        QCheckBox,
        QLabel,
        QLineEdit,
        QPlainTextEdit,
        QPushButton,
        QTextEdit,
    )

    from cpm_fm.gui.terminal_view import TerminalView
    from cpm_fm.utils.i18n import tr

    win = gui_no_target
    win.show()
    qapp.processEvents()
    _action(win, "toolbar.terminal").trigger()
    qapp.processEvents()

    terminal = win.terminal_win
    assert terminal is not None
    assert terminal.isVisible()

    central = terminal.centralWidget()
    layout = central.layout()
    receive = terminal.receive_area
    assert isinstance(receive, TerminalView)
    assert layout.count() == 1
    assert layout.itemAt(0).widget() is receive
    assert not isinstance(receive, (QLineEdit, QPlainTextEdit, QTextEdit))
    assert receive.focusPolicy() == Qt.FocusPolicy.StrongFocus
    assert receive.hasFocus()
    terminal_font = receive.current_font()
    assert terminal_font.family() == "Courier New"
    assert terminal_font.styleHint() == QFont.StyleHint.Monospace

    # Only the character-grid view belongs in the central layout: no legacy
    # transmit editor, Send button, control row, or input-hint label remains.
    forbidden = (QLineEdit, QPlainTextEdit, QTextEdit, QPushButton, QCheckBox, QLabel)
    assert {kind.__name__: central.findChildren(kind) for kind in forbidden} == {
        kind.__name__: [] for kind in forbidden
    }

    status = terminal.statusBar()
    assert status.isVisible()
    assert status.currentMessage() == tr("terminal.status_type", type=terminal.engine.terminal_type)


@pytest.mark.gui_integration
@pytest.mark.mt("MT-W04", "UIR-103b", "FR-093")
def test_terminal_config_local_echo_controls_receive_rendering(gui_no_target, monkeypatch, qapp):
    """Dialog-saved Local Echo renders typed bytes only while enabled.

    Verifies: UIR-103b, FR-093.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QPushButton

    from cpm_fm.utils.i18n import tr

    win = gui_no_target
    sent: list[tuple[str, bytes]] = []
    warnings: list[tuple[str, str]] = []
    monkeypatch.setattr(
        win.serial_mgr,
        "send_raw",
        lambda port, data: sent.append((port, data)) or True,
    )
    monkeypatch.setattr(
        "cpm_fm.gui.mw_config.QMessageBox.warning",
        lambda _parent, title, message: warnings.append((title, message)),
    )

    def save_local_echo(enabled: bool) -> None:
        dialog = _terminal_config_dialog(monkeypatch, win, qapp)
        checkbox = dialog.entries["local_echo"]
        assert checkbox.isChecked() is not enabled
        checkbox.click()
        assert checkbox.isChecked() is enabled
        save = next(
            button
            for button in dialog.findChildren(QPushButton)
            if button.text() == tr("button.save")
        )
        QTest.mouseClick(save, Qt.MouseButton.LeftButton)
        assert win.settings["local_echo"] == ("ON" if enabled else "OFF")

    win.show()
    qapp.processEvents()
    _action(win, "toolbar.terminal").trigger()
    qapp.processEvents()
    terminal = win.terminal_win
    assert terminal is not None
    assert terminal.engine.display[0].rstrip() == ""

    # The production handler rejects typing on a closed port. Mark only the
    # serial-write boundary connected; send_raw above captures every byte.
    win.serial_mgr.terminal_connected = True
    try:
        save_local_echo(True)
        assert win._local_echo is True
        QTest.keyClicks(terminal.receive_area, "A")
        qapp.processEvents()
        assert sent == [("terminal", b"A")]
        assert win._tx_buffer == "A"
        assert terminal.engine.display[0].rstrip() == "A"

        save_local_echo(False)
        assert win._local_echo is False
        QTest.keyClicks(terminal.receive_area, "B")
        qapp.processEvents()
        assert sent == [("terminal", b"A"), ("terminal", b"B")]
        assert win._tx_buffer == "AB"
        assert terminal.engine.display[0].rstrip() == "A"
    finally:
        win.serial_mgr.terminal_connected = False

    expected_warning = (tr("dialog.warning.title"), tr("warning.no_config_loaded"))
    assert warnings == [expected_warning, expected_warning]


@pytest.mark.gui_integration
@pytest.mark.mt("MT-W05", "UIR-103c", "UIR-104", "UIR-062")
def test_terminal_config_autoscroll_follows_bottom_then_preserves_scrollback_position(
    gui_no_target, monkeypatch, qapp
):
    """Autoscroll follows new output when on and stays put when saved off.

    Verifies: UIR-103c, UIR-104, UIR-062.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QPushButton

    from cpm_fm.utils.i18n import tr

    win = gui_no_target
    warnings: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "cpm_fm.gui.mw_config.QMessageBox.warning",
        lambda _parent, title, message: warnings.append((title, message)),
    )

    win.show()
    qapp.processEvents()
    _action(win, "toolbar.terminal").trigger()
    qapp.processEvents()
    terminal = win.terminal_win
    assert terminal is not None
    receive = terminal.receive_area
    scrollbar = receive.verticalScrollBar()

    initial_output = b"".join(f"LINE-{index:03}\r\n".encode() for index in range(80))
    win.handle_terminal_recv(initial_output)
    qapp.processEvents()
    assert terminal.engine.history_len > 0
    assert scrollbar.maximum() > 0
    assert scrollbar.value() == scrollbar.maximum()

    dialog = _terminal_config_dialog(monkeypatch, win, qapp)
    autoscroll = dialog.entries["autoscroll"]
    assert autoscroll.isChecked() is True
    autoscroll.click()
    assert autoscroll.isChecked() is False
    save = next(
        button for button in dialog.findChildren(QPushButton) if button.text() == tr("button.save")
    )
    QTest.mouseClick(save, Qt.MouseButton.LeftButton)
    assert win.settings["autoscroll"] == "OFF"

    scrollback_position = scrollbar.maximum() // 3
    scrollbar.setValue(scrollback_position)
    assert scrollbar.value() == scrollback_position
    prior_maximum = scrollbar.maximum()

    later_output = b"".join(f"LATER-{index:03}\r\n".encode() for index in range(20))
    win.handle_terminal_recv(later_output)
    qapp.processEvents()
    assert win._rx_buffer.endswith(later_output.decode())
    assert scrollbar.maximum() > prior_maximum
    assert scrollbar.value() == scrollback_position

    expected_warning = (tr("dialog.warning.title"), tr("warning.no_config_loaded"))
    assert warnings == [expected_warning]


@pytest.mark.gui_integration
@pytest.mark.mt("MT-W07", "FR-098")
def test_terminal_typing_with_closed_port_reports_status_and_transmits_nothing(
    gui_no_target, monkeypatch, qapp
):
    """Closed-port Receive-view typing reports the exact status and is rejected.

    Verifies: FR-098.
    """
    from PySide6.QtTest import QTest

    from cpm_fm.utils.i18n import tr

    win = gui_no_target
    sent: list[tuple[str, bytes]] = []
    monkeypatch.setattr(
        win.serial_mgr,
        "send_raw",
        lambda port, data: sent.append((port, data)) or True,
    )
    # Even with Local Echo requested, the closed-port guard must reject the key
    # before transmission, buffering, or rendering.
    win.settings["local_echo"] = "ON"

    win.show()
    qapp.processEvents()
    _action(win, "toolbar.terminal").trigger()
    qapp.processEvents()
    terminal = win.terminal_win
    assert terminal is not None
    assert win.serial_mgr.terminal_connected is False
    assert win._local_echo is True
    assert terminal.engine.display[0].rstrip() == ""

    QTest.keyClicks(terminal.receive_area, "X")
    qapp.processEvents()

    assert sent == []
    assert win._tx_buffer == ""
    assert terminal.engine.display[0].rstrip() == ""
    assert win.statusBar().currentMessage() == tr("status.terminal_not_open_send")


@pytest.mark.gui_integration
@pytest.mark.mt("MT-W08", "FR-158")
def test_terminal_receive_view_encodes_control_navigation_and_editing_keys(
    gui_no_target, monkeypatch, qapp
):
    """The real Receive view sends exact CP/M control and VT-100 key bytes.

    Verifies: FR-158.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    win = gui_no_target
    sent: list[tuple[str, bytes]] = []
    monkeypatch.setattr(
        win.serial_mgr,
        "send_raw",
        lambda port, data: sent.append((port, data)) or True,
    )

    win.show()
    qapp.processEvents()
    _action(win, "toolbar.terminal").trigger()
    qapp.processEvents()
    terminal = win.terminal_win
    assert terminal is not None
    receive = terminal.receive_area
    assert receive.hasFocus()
    assert win._local_echo is False
    assert terminal.engine.display[0].rstrip() == ""

    win.serial_mgr.terminal_connected = True
    try:
        QTest.keyClick(
            receive,
            Qt.Key.Key_C,
            Qt.KeyboardModifier.ControlModifier,
        )
        QTest.keyClick(receive, Qt.Key.Key_Up)
        QTest.keyClick(receive, Qt.Key.Key_Down)
        QTest.keyClick(receive, Qt.Key.Key_Right)
        QTest.keyClick(receive, Qt.Key.Key_Left)
        QTest.keyClick(receive, Qt.Key.Key_Backspace)
        QTest.keyClick(receive, Qt.Key.Key_Escape)
        qapp.processEvents()
    finally:
        win.serial_mgr.terminal_connected = False

    expected = [
        ("terminal", b"\x03"),
        ("terminal", b"\x1b[A"),
        ("terminal", b"\x1b[B"),
        ("terminal", b"\x1b[C"),
        ("terminal", b"\x1b[D"),
        ("terminal", b"\x08"),
        ("terminal", b"\x1b"),
    ]
    assert sent == expected
    assert win._tx_buffer == "\x03\x1b[A\x1b[B\x1b[C\x1b[D\x08\x1b"
    assert terminal.engine.display[0].rstrip() == ""


@pytest.mark.gui_integration
@pytest.mark.mt(
    "MT-W16",
    "UIR-034",
    "UIR-103a",
    "FR-157i",
    "FR-157j",
    "FR-158a",
    "FR-158b",
)
def test_terminal_config_switches_live_emulation_and_arrow_key_encoding(
    gui_no_target, monkeypatch, qapp
):
    """Config saves switch the live engine and its exact cursor-key encoding.

    Verifies: UIR-034, UIR-103a, FR-157i, FR-157j, FR-158a, FR-158b.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QPushButton

    from cpm_fm.utils.i18n import tr

    win = gui_no_target
    sent: list[tuple[str, bytes]] = []
    warnings: list[tuple[str, str]] = []
    monkeypatch.setattr(
        win.serial_mgr,
        "send_raw",
        lambda port, data: sent.append((port, data)) or True,
    )
    monkeypatch.setattr(
        "cpm_fm.gui.mw_config.QMessageBox.warning",
        lambda _parent, title, message: warnings.append((title, message)),
    )

    win.show()
    qapp.processEvents()
    _action(win, "toolbar.terminal").trigger()
    qapp.processEvents()
    terminal = win.terminal_win
    assert terminal is not None
    receive = terminal.receive_area
    assert receive.hasFocus()
    assert terminal.engine.terminal_type == "VT100"

    def save_terminal_type(terminal_type: str) -> None:
        dialog = _terminal_config_dialog(monkeypatch, win, qapp)
        selector = dialog.entries["terminal_type"]
        assert [selector.itemText(index) for index in range(selector.count())] == [
            "VT100",
            "VT52",
            "ADM-3A",
        ]
        selector.setCurrentText(terminal_type)
        assert selector.currentText() == terminal_type
        save = next(
            button
            for button in dialog.findChildren(QPushButton)
            if button.text() == tr("button.save")
        )
        QTest.mouseClick(save, Qt.MouseButton.LeftButton)
        qapp.processEvents()
        assert win.settings["terminal_type"] == terminal_type
        assert terminal.engine.terminal_type == terminal_type
        assert terminal.statusBar().currentMessage() == tr(
            "terminal.status_type", type=terminal_type
        )

    def press_arrows() -> None:
        QTest.keyClick(receive, Qt.Key.Key_Up)
        QTest.keyClick(receive, Qt.Key.Key_Down)
        QTest.keyClick(receive, Qt.Key.Key_Right)
        QTest.keyClick(receive, Qt.Key.Key_Left)
        qapp.processEvents()

    win.serial_mgr.terminal_connected = True
    try:
        save_terminal_type("VT52")
        press_arrows()
        save_terminal_type("ADM-3A")
        press_arrows()
        save_terminal_type("VT100")
        press_arrows()
    finally:
        win.serial_mgr.terminal_connected = False

    expected_bytes = [
        b"\x1bA",
        b"\x1bB",
        b"\x1bC",
        b"\x1bD",
        b"\x0b",
        b"\x0a",
        b"\x0c",
        b"\x08",
        b"\x1b[A",
        b"\x1b[B",
        b"\x1b[C",
        b"\x1b[D",
    ]
    assert sent == [("terminal", data) for data in expected_bytes]
    assert win._tx_buffer == b"".join(expected_bytes).decode("latin-1")
    expected_warning = (tr("dialog.warning.title"), tr("warning.no_config_loaded"))
    assert warnings == [expected_warning, expected_warning, expected_warning]


@pytest.mark.gui_integration
@pytest.mark.mt("MT-W17", "UIR-099", "UIR-100", "FR-165", "FR-166", "FR-094", "FR-098")
def test_terminal_context_menu_selection_copy_paste_and_closed_port(
    gui_no_target, monkeypatch, qapp
):
    """Real selection and menu actions copy and conditionally paste exact text.

    Verifies: UIR-099, UIR-100, FR-165, FR-166, FR-094, FR-098.
    """
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication

    from cpm_fm.utils.i18n import tr

    win = gui_no_target
    sent: list[tuple[str, bytes]] = []
    monkeypatch.setattr(
        win.serial_mgr,
        "send_raw",
        lambda port, data: sent.append((port, data)) or True,
    )

    win.show()
    qapp.processEvents()
    _action(win, "toolbar.terminal").trigger()
    qapp.processEvents()
    terminal = win.terminal_win
    assert terminal is not None
    receive = terminal.receive_area
    grid = receive.widget()
    open_context_menu = _terminal_context_menu_opener(monkeypatch, terminal, qapp)

    command_labels = [
        tr("terminal.menu.copy"),
        tr("terminal.menu.paste"),
        tr("terminal.menu.clear"),
        tr("terminal.menu.font"),
        tr("terminal.menu.reset_size"),
        tr("terminal.menu.boot"),
    ]

    def command_actions(menu):
        actions = {
            action.text(): action
            for action in menu.actions()
            if not action.isSeparator() and action.menu() is None
        }
        assert list(actions) == command_labels
        return actions

    QApplication.clipboard().clear()
    initial_actions = command_actions(open_context_menu())
    assert initial_actions[tr("terminal.menu.copy")].isEnabled() is False

    win.handle_terminal_recv(b"ALPHA   \r\nBETA")
    qapp.processEvents()
    start = QPoint(receive._cell_w // 2, receive._cell_h // 2)
    end = QPoint(4 * receive._cell_w, receive._cell_h + receive._cell_h // 2)
    QTest.mousePress(grid, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(grid, pos=end)
    QTest.mouseRelease(grid, Qt.MouseButton.LeftButton, pos=end)
    qapp.processEvents()
    assert receive.has_selection() is True
    assert receive.selected_text() == "ALPHA\nBETA"

    selected_actions = command_actions(open_context_menu())
    copy_action = selected_actions[tr("terminal.menu.copy")]
    assert copy_action.isEnabled() is True
    copy_action.trigger()
    qapp.processEvents()
    assert QApplication.clipboard().text() == "ALPHA\nBETA"

    paste_text = "DIR\r\nSTAT\nX\rY"
    expected_paste = b"DIR\rSTAT\rX\rY"
    QApplication.clipboard().setText(paste_text)
    win.serial_mgr.terminal_connected = True
    try:
        connected_actions = command_actions(open_context_menu())
        connected_actions[tr("terminal.menu.paste")].trigger()
        qapp.processEvents()
    finally:
        win.serial_mgr.terminal_connected = False

    assert sent == [("terminal", expected_paste)]
    assert win._tx_buffer == expected_paste.decode("ascii")

    QApplication.clipboard().setText("ERA *.*\n")
    closed_actions = command_actions(open_context_menu())
    closed_actions[tr("terminal.menu.paste")].trigger()
    qapp.processEvents()
    assert sent == [("terminal", expected_paste)]
    assert win._tx_buffer == expected_paste.decode("ascii")
    assert win.statusBar().currentMessage() == tr("status.terminal_not_open_send")


@pytest.mark.gui_integration
@pytest.mark.mt("MT-W18", "UIR-099", "FR-095", "FR-167", "FR-091a")
def test_terminal_context_menu_clear_then_reset_size(gui_no_target, monkeypatch, qapp):
    """Real Clear resets terminal state; real Reset Size produces an 80x24 grid.

    Verifies: UIR-099, FR-095, FR-167, FR-091a.
    """
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    from cpm_fm.utils.i18n import tr

    win = gui_no_target
    sent: list[tuple[str, bytes]] = []
    monkeypatch.setattr(
        win.serial_mgr,
        "send_raw",
        lambda port, data: sent.append((port, data)) or True,
    )

    win.show()
    qapp.processEvents()
    _action(win, "toolbar.terminal").trigger()
    qapp.processEvents()
    terminal = win.terminal_win
    assert terminal is not None
    receive = terminal.receive_area
    grid = receive.widget()
    open_context_menu = _terminal_context_menu_opener(monkeypatch, terminal, qapp)

    terminal.resize(520, 340)
    qapp.processEvents()
    assert (terminal.engine.cols, terminal.engine.rows) != (80, 24)

    received = b"".join(f"LINE-{index:02}\r\n".encode() for index in range(40))
    win.handle_terminal_recv(received)
    qapp.processEvents()
    receive.setFocus()
    win.serial_mgr.terminal_connected = True
    try:
        QTest.keyClicks(receive, "Z")
        qapp.processEvents()
    finally:
        win.serial_mgr.terminal_connected = False

    start = QPoint(receive._cell_w // 2, receive._cell_h // 2)
    end = QPoint(4 * receive._cell_w, receive._cell_h // 2)
    QTest.mousePress(grid, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(grid, pos=end)
    QTest.mouseRelease(grid, Qt.MouseButton.LeftButton, pos=end)
    qapp.processEvents()

    assert terminal.engine.history_len > 0
    assert any(line.rstrip() for line in terminal.engine.display)
    assert win._rx_buffer == received.decode("ascii")
    assert win._tx_buffer == "Z"
    assert sent == [("terminal", b"Z")]
    assert receive.has_selection() is True

    clear_menu = open_context_menu()
    clear_action = next(
        action for action in clear_menu.actions() if action.text() == tr("terminal.menu.clear")
    )
    clear_action.trigger()
    qapp.processEvents()

    assert terminal.engine.history_len == 0
    assert all(not line.rstrip() for line in terminal.engine.display)
    assert win._rx_buffer == ""
    assert win._tx_buffer == ""
    assert receive.has_selection() is False

    terminal.resize(430, 260)
    qapp.processEvents()
    before_reset = (terminal.engine.cols, terminal.engine.rows)
    assert before_reset != (80, 24)
    preserved = b"PRESERVE"
    win.handle_terminal_recv(preserved)
    qapp.processEvents()
    assert any("PRESERVE" in line for line in terminal.engine.display)

    reset_menu = open_context_menu()
    reset_action = next(
        action for action in reset_menu.actions() if action.text() == tr("terminal.menu.reset_size")
    )
    reset_action.trigger()
    qapp.processEvents()

    assert (terminal.engine.cols, terminal.engine.rows) == (80, 24)
    assert win._rx_buffer == preserved.decode("ascii")
    assert win._tx_buffer == ""


@pytest.mark.gui_integration
@pytest.mark.mt("MT-W19", "UIR-099", "UIR-101", "UIR-034", "UIR-106", "FR-158", "FR-158b")
def test_terminal_type_context_submenu_switches_checks_status_and_keys(
    gui_no_target, monkeypatch, qapp
):
    """The real type submenu switches live state, check marks, and key bytes.

    Verifies: UIR-099, UIR-101, UIR-034, UIR-106, FR-158, FR-158b.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from cpm_fm.terminal.term_translate import ADM3A, TERMINAL_TYPES, VT100
    from cpm_fm.utils.i18n import tr

    win = gui_no_target
    sent: list[tuple[str, bytes]] = []
    monkeypatch.setattr(
        win.serial_mgr,
        "send_raw",
        lambda port, data: sent.append((port, data)) or True,
    )

    win.show()
    qapp.processEvents()
    _action(win, "toolbar.terminal").trigger()
    qapp.processEvents()
    terminal = win.terminal_win
    assert terminal is not None
    receive = terminal.receive_area
    open_context_menu = _terminal_context_menu_opener(monkeypatch, terminal, qapp)

    def type_actions():
        menu = open_context_menu()
        submenu = next(
            action.menu()
            for action in menu.actions()
            if action.menu() is not None
            and action.menu().title() == tr("terminal.menu.terminal_type")
        )
        assert submenu is not None
        assert submenu.isEnabled() is True
        actions = submenu.actions()
        assert [action.text() for action in actions] == list(TERMINAL_TYPES)
        assert all(action.isCheckable() for action in actions)
        return {action.text(): action for action in actions}

    def assert_checked(actions, expected: str) -> None:
        assert {terminal_type: action.isChecked() for terminal_type, action in actions.items()} == {
            terminal_type: terminal_type == expected for terminal_type in TERMINAL_TYPES
        }

    assert terminal.engine.terminal_type == VT100
    assert win.settings.get("terminal_type", VT100) == VT100
    assert terminal.statusBar().currentMessage() == tr("terminal.status_type", type=VT100)
    initial_actions = type_actions()
    assert_checked(initial_actions, VT100)

    initial_actions[ADM3A].trigger()
    qapp.processEvents()
    assert terminal.engine.terminal_type == ADM3A
    assert win.settings["terminal_type"] == ADM3A
    assert terminal.statusBar().currentMessage() == tr("terminal.status_type", type=ADM3A)

    receive.setFocus()
    win.serial_mgr.terminal_connected = True
    try:
        QTest.keyClick(receive, Qt.Key.Key_Up)
        QTest.keyClick(receive, Qt.Key.Key_Down)
        QTest.keyClick(receive, Qt.Key.Key_Right)
        QTest.keyClick(receive, Qt.Key.Key_Left)
        qapp.processEvents()

        adm_actions = type_actions()
        assert_checked(adm_actions, ADM3A)
        adm_actions[VT100].trigger()
        qapp.processEvents()
        assert terminal.engine.terminal_type == VT100
        assert win.settings["terminal_type"] == VT100
        assert terminal.statusBar().currentMessage() == tr("terminal.status_type", type=VT100)

        QTest.keyClick(receive, Qt.Key.Key_Up)
        qapp.processEvents()
    finally:
        win.serial_mgr.terminal_connected = False

    final_actions = type_actions()
    assert_checked(final_actions, VT100)
    expected_bytes = [b"\x0b", b"\x0a", b"\x0c", b"\x08", b"\x1b[A"]
    assert sent == [("terminal", data) for data in expected_bytes]
    assert win._tx_buffer == b"".join(expected_bytes).decode("ascii")


@pytest.mark.gui_integration
@pytest.mark.mt("MT-W20", "UIR-099", "UIR-102", "FR-162")
def test_terminal_macros_context_submenu_filters_dispatches_and_disables(
    gui_no_target, monkeypatch, qapp
):
    """The real Macros submenu lists valid slots and dispatches exact scripts.

    Verifies: UIR-099, UIR-102, FR-162.
    """
    from cpm_fm.gui.mw_remote import MACRO_COUNT
    from cpm_fm.utils.i18n import tr

    win = gui_no_target
    for index in range(1, MACRO_COUNT + 1):
        win.settings[f"macro_{index}_label"] = ""
        win.settings[f"macro_{index}_seq"] = ""

    prompt_script = "SENDRAW 0D"
    list_script = "SEND DIR\nWAIT 1"
    reset_script = "SENDRAW 03"
    win.settings.update(
        {
            "macro_1_label": "  Prompt  ",
            "macro_1_seq": prompt_script,
            "macro_2_label": "",
            "macro_2_seq": "SEND ERA *.*",
            "macro_3_label": "No-op",
            "macro_3_seq": " \n ",
            "macro_4_label": "List",
            "macro_4_seq": list_script,
            f"macro_{MACRO_COUNT}_label": "Reset",
            f"macro_{MACRO_COUNT}_seq": reset_script,
        }
    )

    dispatched: list[str] = []
    monkeypatch.setattr(win, "run_macro_script", dispatched.append)

    win.show()
    qapp.processEvents()
    _action(win, "toolbar.terminal").trigger()
    qapp.processEvents()
    terminal = win.terminal_win
    assert terminal is not None
    open_context_menu = _terminal_context_menu_opener(monkeypatch, terminal, qapp)

    def macros_submenu():
        menu = open_context_menu()
        submenu = next(
            action.menu()
            for action in menu.actions()
            if action.menu() is not None and action.menu().title() == tr("terminal.menu.macros_sub")
        )
        assert submenu is not None
        return submenu

    configured = macros_submenu()
    assert configured.isEnabled() is True
    configured_actions = configured.actions()
    assert [action.text() for action in configured_actions] == ["Prompt", "List", "Reset"]

    configured_actions[1].trigger()
    configured_actions[0].trigger()
    configured_actions[2].trigger()
    qapp.processEvents()
    assert dispatched == [list_script, prompt_script, reset_script]

    for index in range(1, MACRO_COUNT + 1):
        win.settings[f"macro_{index}_label"] = ""
        win.settings[f"macro_{index}_seq"] = ""

    empty = macros_submenu()
    assert empty.isEnabled() is False
    assert empty.actions() == []
    assert dispatched == [list_script, prompt_script, reset_script]


@pytest.mark.gui_integration
@pytest.mark.mt("MT-W21", "FR-168")
def test_auxiliary_window_open_state_survives_then_clears_across_processes(tmp_path):
    """Three application processes restore open windows, then persist them closed.

    Verifies: FR-168.
    """
    import json
    import os
    import subprocess
    import sys
    from pathlib import Path

    state_path = tmp_path / "window-state.ini"
    history_path = tmp_path / "window-history.json"
    test_file = Path(__file__).resolve()
    environment = os.environ.copy()
    environment["QT_QPA_PLATFORM"] = "offscreen"

    def run_probe(mode: str) -> dict[str, object]:
        completed = subprocess.run(
            [
                sys.executable,
                str(test_file),
                "--window-state-process-probe",
                mode,
                str(state_path),
                str(history_path),
            ],
            cwd=test_file.parents[1],
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert completed.returncode == 0, (
            f"window-state {mode} process failed\nstdout:\n{completed.stdout}"
            f"\nstderr:\n{completed.stderr}"
        )
        probe_line = next(
            line
            for line in completed.stdout.splitlines()
            if line.startswith(_WINDOW_STATE_PROBE_PREFIX)
        )
        return json.loads(probe_line.removeprefix(_WINDOW_STATE_PROBE_PREFIX))

    assert run_probe("open") == {
        "terminal_visible_before_exit": True,
        "history_visible_before_exit": True,
        "terminal_stored_open": True,
        "history_stored_open": True,
    }
    assert run_probe("restore_close") == {
        "terminal_restored": True,
        "history_restored": True,
        "terminal_visible_after_close": False,
        "history_visible_after_close": False,
        "terminal_stored_open": False,
        "history_stored_open": False,
    }
    assert run_probe("verify_closed") == {
        "terminal_created": False,
        "history_created": False,
        "terminal_stored_open": False,
        "history_stored_open": False,
    }


@pytest.mark.gui_integration
@pytest.mark.mt("MT-W10", "UIR-105")
def test_terminal_boot_context_action_tracks_saved_boot_sequence(gui_no_target, monkeypatch, qapp):
    """Each real context-menu opening reflects the saved Boot Sequence.

    Verifies: UIR-105.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QPushButton

    from cpm_fm.utils.i18n import tr

    win = gui_no_target
    warnings: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "cpm_fm.gui.mw_config.QMessageBox.warning",
        lambda _parent, title, message: warnings.append((title, message)),
    )

    win.show()
    qapp.processEvents()
    _action(win, "toolbar.terminal").trigger()
    qapp.processEvents()
    terminal = win.terminal_win
    assert terminal is not None
    assert win.settings.get("boot_sequence", "") == ""

    def open_boot_action():
        menu = open_context_menu()
        return next(
            action for action in menu.actions() if action.text() == tr("terminal.menu.boot")
        )

    open_context_menu = _terminal_context_menu_opener(monkeypatch, terminal, qapp)

    initial_boot = open_boot_action()
    assert initial_boot.isEnabled() is False

    dialog = _remote_config_dialog(monkeypatch, win, qapp)
    script = "SEND 0\nWAIT 1"
    dialog.entries["boot_sequence"].setPlainText(script)
    save = next(
        button for button in dialog.findChildren(QPushButton) if button.text() == tr("button.save")
    )
    QTest.mouseClick(save, Qt.MouseButton.LeftButton)
    assert win.settings["boot_sequence"] == script

    configured_boot = open_boot_action()
    assert configured_boot.isEnabled() is True
    assert warnings == [(tr("dialog.warning.title"), tr("warning.no_config_loaded"))]


@pytest.mark.gui_integration
@pytest.mark.mt("MT-W12", "FR-091a")
def test_terminal_window_resize_reflows_character_grid(gui_no_target, qapp):
    """Real window resizing reflows the grid and preserves a usable minimum.

    Verifies: FR-091a.
    """
    from cpm_fm.gui.terminal_view import grid_size_for

    win = gui_no_target
    win.show()
    qapp.processEvents()
    _action(win, "toolbar.terminal").trigger()
    qapp.processEvents()
    terminal = win.terminal_win
    assert terminal is not None
    receive = terminal.receive_area

    def resize_and_grid(width: int, height: int) -> tuple[int, int]:
        terminal.showNormal()
        terminal.resize(width, height)
        qapp.processEvents()
        viewport = receive.viewport().size()
        expected = grid_size_for(
            viewport.width(),
            viewport.height(),
            receive._cell_w,
            receive._cell_h,
        )
        actual = (terminal.engine.cols, terminal.engine.rows)
        assert actual == expected
        return actual

    normal = resize_and_grid(520, 340)
    larger = resize_and_grid(760, 560)
    assert larger[0] > normal[0]
    assert larger[1] > normal[1]

    smallest = resize_and_grid(80, 60)
    assert smallest == (20, 5)
    assert smallest[0] < normal[0]
    assert smallest[1] < normal[1]

    terminal.showMaximized()
    qapp.processEvents()
    assert terminal.isMaximized()
    viewport = receive.viewport().size()
    maximised = (terminal.engine.cols, terminal.engine.rows)
    assert maximised == grid_size_for(
        viewport.width(),
        viewport.height(),
        receive._cell_w,
        receive._cell_h,
    )
    assert maximised[0] > smallest[0]
    assert maximised[1] > smallest[1]


@pytest.mark.gui_integration
@pytest.mark.mt("MT-W13", "UIR-069", "UIR-099", "FR-091a")
def test_terminal_font_action_applies_cancels_and_restores_persisted_font(
    gui_no_target, monkeypatch, qapp, tmp_path
):
    """The real Font action applies, reflows, cancels, and restores its choice.

    Verifies: UIR-069, UIR-099, FR-091a.
    """
    from PySide6.QtCore import QSettings
    from PySide6.QtGui import QFont, QFontDatabase
    from PySide6.QtWidgets import QDialog, QFontDialog, QListView

    from cpm_fm.app import MainWindow
    from cpm_fm.gui.terminal_view import grid_size_for
    from cpm_fm.gui.window_state import WindowState
    from cpm_fm.utils.i18n import tr
    from cpm_fm.utils.transfer_history import TransferHistory

    win = gui_no_target
    win.show()
    qapp.processEvents()
    _action(win, "toolbar.terminal").trigger()
    qapp.processEvents()
    terminal = win.terminal_win
    assert terminal is not None
    terminal.resize(620, 420)
    qapp.processEvents()
    receive = terminal.receive_area
    before_font = receive.current_font()
    before_grid = (terminal.engine.cols, terminal.engine.rows)

    # Inspect an unmodified real dialog before isolating its blocking exec().
    # The offscreen plugin does not preserve the visible family selection
    # reliably, so exact on-screen seeding remains retained manual evidence.
    probe = terminal._build_font_dialog()
    try:
        probe.show()
        qapp.processEvents()
        assert probe.windowTitle() == tr("terminal.font_dialog_title")
        assert probe.testOption(QFontDialog.FontDialogOption.DontUseNativeDialog)
        assert "QFontDialog QListView" in probe.styleSheet()
        assert len([view for view in probe.findChildren(QListView) if view.height() > 100]) >= 3
    finally:
        probe.close()
        probe.deleteLater()
        qapp.processEvents()

    alternative_families = [
        family for family in QFontDatabase.families() if family != before_font.family()
    ]
    assert alternative_families
    chosen = QFont(alternative_families[0], 24)
    chosen.setBold(True)
    chosen.setItalic(True)
    rejected = QFont(before_font.family(), 8)

    dialogs: list[QFontDialog] = []

    def resolve_font_dialog(dialog):
        dialogs.append(dialog)
        dialog.show()
        qapp.processEvents()
        if len(dialogs) == 1:
            dialog.setCurrentFont(chosen)
            qapp.processEvents()
            dialog.accept()
            return QDialog.DialogCode.Accepted
        dialog.setCurrentFont(rejected)
        qapp.processEvents()
        dialog.reject()
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(QFontDialog, "exec", resolve_font_dialog)
    open_context_menu = _terminal_context_menu_opener(monkeypatch, terminal, qapp)

    def trigger_font_action():
        menu = open_context_menu()
        font_action = next(
            action for action in menu.actions() if action.text() == tr("terminal.menu.font")
        )
        font_action.trigger()
        qapp.processEvents()

    trigger_font_action()

    assert len(dialogs) == 1

    accepted_font = receive.current_font()
    assert accepted_font.family() == chosen.family()
    assert accepted_font.pointSize() == 24
    assert accepted_font.bold() is True
    assert accepted_font.italic() is True
    accepted_grid = (terminal.engine.cols, terminal.engine.rows)
    viewport = receive.viewport().size()
    assert accepted_grid == grid_size_for(
        viewport.width(),
        viewport.height(),
        receive._cell_w,
        receive._cell_h,
    )
    assert accepted_grid[1] < before_grid[1]
    assert win.window_state.terminal_font.toString() == accepted_font.toString()

    trigger_font_action()

    assert len(dialogs) == 2
    assert receive.current_font().toString() == accepted_font.toString()
    assert (terminal.engine.cols, terminal.engine.rows) == accepted_grid
    assert win.window_state.terminal_font.toString() == accepted_font.toString()

    win.window_state._settings.sync()
    state_path = win.window_state._settings.fileName()
    restored_state = WindowState(QSettings(state_path, QSettings.Format.IniFormat))
    restored = MainWindow(
        restored_state,
        TransferHistory(str(tmp_path / "restored-font-history.json")),
    )
    try:
        restored.show()
        qapp.processEvents()
        _action(restored, "toolbar.terminal").trigger()
        qapp.processEvents()
        assert restored.terminal_win is not None
        restored_font = restored.terminal_win.receive_area.current_font()
        assert restored_font.toString() == accepted_font.toString()
    finally:
        if restored.terminal_win is not None:
            restored.terminal_win.hide()
            restored.terminal_win.deleteLater()
            restored.terminal_win = None
        restored.close()
        restored.deleteLater()
        qapp.processEvents()


if __name__ == "__main__":  # pragma: no cover - exercised by MT-W21 subprocesses
    import sys

    if len(sys.argv) == 5 and sys.argv[1] == "--window-state-process-probe":
        _run_window_state_process_probe(sys.argv[2], sys.argv[3], sys.argv[4])
