"""Target-free GUI connection/error workflows (MT-C02--MT-C04, MT-C10--MT-C15).

These tests drive the real ``MainWindow`` and its connection indicators while
replacing only the operating-system serial boundary.  They provide deterministic
CI evidence for dialog and state transitions; the manual cases retain the real
busy/free-port observations.
"""

from __future__ import annotations

import pytest

from cpm_fm.utils import i18n


@pytest.mark.gui_integration
@pytest.mark.mt("MT-C02", "FR-031", "FR-033")
def test_bad_terminal_port_reports_error_and_stays_disconnected(gui_no_target, monkeypatch):
    """A failed Terminal Port open cancels Connect and keeps its indicator red.

    Verifies: FR-031, FR-033.
    """
    win = gui_no_target
    win.settings["terminal_port"] = "BAD-TERMINAL"
    win.settings["transport_port"] = "UNUSED-TRANSPORT"

    opened: list[str] = []
    monkeypatch.setattr(
        win.serial_mgr,
        "open_port",
        lambda kind, settings: opened.append(kind) or False,
    )
    errors: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "cpm_fm.gui.mw_remote.QMessageBox.critical",
        lambda parent, title, message: errors.append((title, message)),
    )

    win.do_connect()

    assert opened == ["terminal"], "Connect continued after the Terminal Port failed"
    assert errors == [(i18n.tr("dialog.error.title"), i18n.tr("error.terminal_unable_open"))]
    assert win.serial_mgr.terminal_connected is False
    assert win.serial_mgr.transport_connected is False
    assert "#f44336" in win.term_indicator.styleSheet()


@pytest.mark.gui_integration
@pytest.mark.mt("MT-C03", "FR-038", "FR-040", "UIR-074")
def test_distinct_terminal_and_transport_ports_connect_both(gui_no_target, monkeypatch):
    """Distinct available ports are both opened and shown as connected.

    Verifies: FR-038, FR-040, UIR-074.
    """
    win = gui_no_target
    win.settings["terminal_port"] = "FREE-TERMINAL"
    win.settings["transport_port"] = "FREE-TRANSPORT"

    opened: list[str] = []

    def open_port(kind, settings):
        opened.append(kind)
        setattr(win.serial_mgr, f"{kind}_connected", True)
        return True

    monkeypatch.setattr(win.serial_mgr, "open_port", open_port)
    probe_targets = []

    class RecordingThread:
        def __init__(self, *args, target=None, **kwargs):
            probe_targets.append(target)

        def start(self):
            return None

    monkeypatch.setattr("cpm_fm.gui.mw_remote.threading.Thread", RecordingThread)

    win.do_connect()

    assert opened == ["terminal", "transport"]
    assert win.serial_mgr.terminal_connected is True
    assert win.serial_mgr.transport_connected is True
    assert "#4caf50" in win.term_indicator.styleSheet()
    assert "#4caf50" in win.trans_indicator.styleSheet()
    assert probe_targets == [win._do_connect_probe_logic]


@pytest.mark.gui_integration
@pytest.mark.mt("MT-C04", "FR-039", "FR-046")
def test_bad_transport_port_reports_error_and_skips_probe(gui_no_target, monkeypatch):
    """A failed Transport Port open reports the error and prevents probing.

    Verifies: FR-039, FR-046.
    """
    win = gui_no_target
    win.settings["terminal_port"] = "FREE-TERMINAL"
    win.settings["transport_port"] = "BAD-TRANSPORT"

    opened: list[str] = []

    def open_port(kind, settings):
        opened.append(kind)
        if kind == "terminal":
            win.serial_mgr.terminal_connected = True
            return True
        win.serial_mgr.transport_connected = False
        return False

    monkeypatch.setattr(win.serial_mgr, "open_port", open_port)
    errors: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "cpm_fm.gui.mw_remote.QMessageBox.critical",
        lambda parent, title, message: errors.append((title, message)),
    )
    probe_targets = []

    class RecordingThread:
        def __init__(self, *args, target=None, **kwargs):
            probe_targets.append(target)

        def start(self):
            return None

    monkeypatch.setattr("cpm_fm.gui.mw_remote.threading.Thread", RecordingThread)

    win.do_connect()

    assert opened == ["terminal", "transport"]
    assert errors == [(i18n.tr("dialog.error.title"), i18n.tr("error.transport_unable_open"))]
    assert win.serial_mgr.terminal_connected is True
    assert win.serial_mgr.transport_connected is False
    assert "#4caf50" in win.term_indicator.styleSheet()
    assert "#f44336" in win.trans_indicator.styleSheet()
    assert probe_targets == [], "remote probe ran without a connected Transport Port"


@pytest.mark.gui_integration
@pytest.mark.mt("MT-C10", "FR-051", "FR-058")
def test_terminal_close_failure_cancels_disconnect_and_keeps_remote_list(
    gui_no_target, monkeypatch
):
    """A Terminal close failure reports the error and preserves connected state.

    Verifies: FR-051, FR-058.
    """
    win = gui_no_target
    win.settings["terminal_port"] = "OPEN-TERMINAL"
    win.settings["transport_port"] = "OPEN-TRANSPORT"
    win.serial_mgr.terminal_connected = True
    win.serial_mgr.transport_connected = True
    win._update_indicators()
    win.remote_list.addItems(["KEEP1.TXT", "KEEP2.COM"])

    close_attempts: list[str] = []

    def close_terminal_port():
        close_attempts.append("terminal")
        return False

    def close_transport_port():
        close_attempts.append("transport")
        return True

    monkeypatch.setattr(win.serial_mgr, "close_terminal_port", close_terminal_port)
    monkeypatch.setattr(win.serial_mgr, "close_transport_port", close_transport_port)
    errors: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "cpm_fm.gui.mw_remote.QMessageBox.critical",
        lambda parent, title, message: errors.append((title, message)),
    )

    win.do_disconnect()

    assert close_attempts == ["terminal"], "Disconnect continued after Terminal close failed"
    assert errors == [(i18n.tr("dialog.error.title"), i18n.tr("error.terminal_unable_close"))]
    assert [win.remote_list.item(i).text() for i in range(win.remote_list.count())] == [
        "KEEP1.TXT",
        "KEEP2.COM",
    ]
    assert win.serial_mgr.terminal_connected is True
    assert win.serial_mgr.transport_connected is True
    assert "#4caf50" in win.term_indicator.styleSheet()
    assert "#4caf50" in win.trans_indicator.styleSheet()


@pytest.mark.gui_integration
@pytest.mark.mt("MT-C12", "FR-041", "FR-043", "FR-044", "UIR-092")
def test_unreachable_remote_retries_then_shows_three_action_dialog(
    gui_no_target, monkeypatch, qapp
):
    """Two failed probes show the real modal Abort/Continue/Terminal dialog.

    Verifies: FR-041, FR-043, FR-044, UIR-092.
    """
    from PySide6.QtWidgets import QLabel, QPushButton

    from cpm_fm.gui.remote_unavailable_dialog import RemoteUnavailableDialog

    win = gui_no_target
    win.settings["boot_sequence"] = ""
    win._probe_cancel.clear()
    captures: list[str] = []

    def capture(command, **kwargs):
        captures.append(command)
        return "remote monitor without a CP/M prompt"

    monkeypatch.setattr(win, "_capture_terminal_response", capture)
    monkeypatch.setattr(
        win,
        "run_boot_sequence",
        lambda: pytest.fail("an empty boot sequence must not run"),
    )
    inspected: list[bool] = []

    def inspect_dialog(dialog):
        assert dialog.isModal() is True
        assert dialog.windowTitle() == i18n.tr("dialog.remote_unavailable.title")
        labels = dialog.findChildren(QLabel)
        assert [label.text() for label in labels] == [i18n.tr("dialog.remote_unavailable.body")]
        buttons = dialog.findChildren(QPushButton)
        assert len(buttons) == 3
        row = dialog.layout().itemAt(1).layout()
        ordered_buttons = [
            row.itemAt(index).widget()
            for index in range(row.count())
            if isinstance(row.itemAt(index).widget(), QPushButton)
        ]
        assert [button.text() for button in ordered_buttons] == [
            i18n.tr("button.abort"),
            i18n.tr("button.continue"),
            i18n.tr("button.terminal"),
        ]
        dialog.choice = RemoteUnavailableDialog.CONTINUE
        inspected.append(True)

    monkeypatch.setattr(RemoteUnavailableDialog, "exec", inspect_dialog)

    win._do_connect_probe_logic()
    qapp.processEvents()

    assert captures == ["", ""], "the failed probe did not perform exactly one retry"
    assert inspected == [True]


@pytest.mark.gui_integration
@pytest.mark.mt("MT-C12a", "FR-045")
def test_remote_unavailable_abort_disconnects_and_clears_list(gui_no_target, monkeypatch):
    """Abort closes both ports and clears the stale Remote Files listing.

    Verifies: FR-045.
    """
    from PySide6.QtWidgets import QPushButton

    from cpm_fm.gui.remote_unavailable_dialog import RemoteUnavailableDialog

    class CloseablePort:
        def __init__(self):
            self.is_open = True

        def reset_output_buffer(self):
            return None

        def reset_input_buffer(self):
            return None

        def close(self):
            self.is_open = False

    win = gui_no_target
    win.settings["terminal_port"] = "OPEN-TERMINAL"
    win.settings["transport_port"] = "OPEN-TRANSPORT"
    terminal_port = CloseablePort()
    transport_port = CloseablePort()
    win.serial_mgr.terminal_port = terminal_port
    win.serial_mgr.transport_port = transport_port
    win.serial_mgr.terminal_connected = True
    win.serial_mgr.transport_connected = True
    win.remote_list.addItems(["STALE1.TXT", "STALE2.COM"])

    def choose_abort(dialog):
        buttons = dialog.findChildren(QPushButton)
        abort = next(button for button in buttons if button.text() == i18n.tr("button.abort"))
        abort.click()

    monkeypatch.setattr(RemoteUnavailableDialog, "exec", choose_abort)

    win._on_connect_probe_failed()

    assert terminal_port.is_open is False
    assert transport_port.is_open is False
    assert win.serial_mgr.terminal_connected is False
    assert win.serial_mgr.transport_connected is False
    assert win.remote_list.count() == 0
    assert "#f44336" in win.term_indicator.styleSheet()
    assert "#f44336" in win.trans_indicator.styleSheet()


@pytest.mark.gui_integration
@pytest.mark.mt("MT-C12b", "FR-045")
def test_remote_unavailable_continue_leaves_ports_open_and_takes_no_action(
    gui_no_target, monkeypatch
):
    """Continue closes only the dialog and leaves the connection untouched.

    Verifies: FR-045.
    """
    from PySide6.QtWidgets import QPushButton

    from cpm_fm.gui.remote_unavailable_dialog import RemoteUnavailableDialog

    win = gui_no_target
    win.serial_mgr.terminal_connected = True
    win.serial_mgr.transport_connected = True
    win._update_indicators()
    assert win.remote_list.count() == 0
    actions: list[str] = []
    monkeypatch.setattr(win, "do_disconnect", lambda: actions.append("disconnect"))
    monkeypatch.setattr(win, "show_terminal", lambda: actions.append("terminal"))

    def choose_continue(dialog):
        buttons = dialog.findChildren(QPushButton)
        proceed = next(button for button in buttons if button.text() == i18n.tr("button.continue"))
        proceed.click()

    monkeypatch.setattr(RemoteUnavailableDialog, "exec", choose_continue)

    win._on_connect_probe_failed()

    assert actions == []
    assert win.serial_mgr.terminal_connected is True
    assert win.serial_mgr.transport_connected is True
    assert win.remote_list.count() == 0
    assert "#4caf50" in win.term_indicator.styleSheet()
    assert "#4caf50" in win.trans_indicator.styleSheet()


@pytest.mark.gui_integration
@pytest.mark.mt("MT-C12c", "FR-045", "FR-097")
def test_remote_unavailable_terminal_opens_terminal_and_leaves_ports_open(
    gui_no_target, monkeypatch, qapp
):
    """Terminal opens the real Terminal Window without disconnecting either port.

    Verifies: FR-045, FR-097.
    """
    from PySide6.QtWidgets import QPushButton

    from cpm_fm.gui.remote_unavailable_dialog import RemoteUnavailableDialog

    win = gui_no_target
    win.serial_mgr.terminal_connected = True
    win.serial_mgr.transport_connected = True
    win._update_indicators()
    disconnects: list[bool] = []
    monkeypatch.setattr(win, "do_disconnect", lambda: disconnects.append(True))

    def choose_terminal(dialog):
        buttons = dialog.findChildren(QPushButton)
        terminal = next(button for button in buttons if button.text() == i18n.tr("button.terminal"))
        terminal.click()

    monkeypatch.setattr(RemoteUnavailableDialog, "exec", choose_terminal)

    win._on_connect_probe_failed()
    qapp.processEvents()

    assert disconnects == []
    assert win.terminal_win is not None
    assert win.terminal_win.isVisible() is True
    assert win.serial_mgr.terminal_connected is True
    assert win.serial_mgr.transport_connected is True
    assert "#4caf50" in win.term_indicator.styleSheet()
    assert "#4caf50" in win.trans_indicator.styleSheet()


@pytest.mark.gui_integration
@pytest.mark.mt("MT-C13", "DR-033", "FR-042")
def test_zcpr_prompt_selects_drive_and_refreshes_without_unavailable_dialog(
    gui_no_target, monkeypatch, qapp
):
    """A ZCPR user-area prompt succeeds on the first probe and refreshes its drive.

    Verifies: DR-033, FR-042.
    """
    from cpm_fm.gui.remote_unavailable_dialog import RemoteUnavailableDialog

    win = gui_no_target
    win.settings["boot_sequence"] = ""
    win._probe_cancel.clear()
    captures: list[str] = []

    def capture(command, **kwargs):
        captures.append(command)
        return "monitor output\r\nB7>\r\n"

    monkeypatch.setattr(win, "_capture_terminal_response", capture)
    refreshes: list[bool] = []
    monkeypatch.setattr(win, "refresh_remote_files", lambda: refreshes.append(True))
    monkeypatch.setattr(
        RemoteUnavailableDialog,
        "exec",
        lambda dialog: pytest.fail("a valid ZCPR prompt opened the unavailable dialog"),
    )

    win._do_connect_probe_logic()
    qapp.processEvents()

    assert captures == [""], "a recognized ZCPR prompt unexpectedly triggered a retry"
    assert win.drive_combo.currentText() == "B:"
    assert refreshes == [True]


@pytest.mark.gui_integration
@pytest.mark.mt("MT-C14", "FR-047", "FR-048")
def test_boot_sequence_recovers_failed_probe_then_selects_drive(gui_no_target, monkeypatch, qapp):
    """A configured boot script runs once and the post-boot probe reaches CP/M.

    Verifies: FR-047, FR-048.
    """
    from cpm_fm.gui.remote_unavailable_dialog import RemoteUnavailableDialog

    win = gui_no_target
    win.settings["boot_sequence"] = "SEND CPM"
    win._probe_cancel.clear()
    responses = iter(["monitor prompt", "still in monitor", "C>"])
    captures: list[str] = []

    def capture(command, **kwargs):
        captures.append(command)
        return next(responses)

    monkeypatch.setattr(win, "_capture_terminal_response", capture)
    sent: list[str] = []
    monkeypatch.setattr(win, "handle_terminal_send", lambda text: sent.append(text))
    refreshes: list[bool] = []
    monkeypatch.setattr(win, "refresh_remote_files", lambda: refreshes.append(True))
    monkeypatch.setattr(
        RemoteUnavailableDialog,
        "exec",
        lambda dialog: pytest.fail("successful boot recovery opened the unavailable dialog"),
    )

    win._do_connect_probe_logic()
    qapp.processEvents()

    assert captures == ["", "", ""]
    assert sent == ["CPM"], "the configured boot sequence did not run exactly once"
    assert win.drive_combo.currentText() == "C:"
    assert refreshes == [True]


@pytest.mark.gui_integration
@pytest.mark.mt("MT-C15", "FR-044", "FR-048")
def test_empty_boot_sequence_skips_recovery_and_shows_unavailable_dialog(
    gui_no_target, monkeypatch, qapp
):
    """Whitespace-only boot configuration goes directly from retry to dialog.

    Verifies: FR-044, FR-048.
    """
    from cpm_fm.gui.remote_unavailable_dialog import RemoteUnavailableDialog

    win = gui_no_target
    win.settings["boot_sequence"] = "   \n\t"
    win.serial_mgr.terminal_connected = True
    win.serial_mgr.transport_connected = True
    win._probe_cancel.clear()
    events: list[str] = []

    def capture(command, **kwargs):
        events.append("capture")
        return "remote remains unreachable"

    monkeypatch.setattr(win, "_capture_terminal_response", capture)
    boot_calls: list[bool] = []
    monkeypatch.setattr(win, "run_boot_sequence", lambda: boot_calls.append(True) or True)
    actions: list[str] = []
    monkeypatch.setattr(win, "do_disconnect", lambda: actions.append("disconnect"))
    monkeypatch.setattr(win, "show_terminal", lambda: actions.append("terminal"))

    def record_dialog(dialog):
        assert dialog.choice == RemoteUnavailableDialog.CONTINUE
        events.append("dialog")

    monkeypatch.setattr(RemoteUnavailableDialog, "exec", record_dialog)

    win._do_connect_probe_logic()
    qapp.processEvents()

    assert events == ["capture", "capture", "dialog"]
    assert boot_calls == []
    assert actions == []
    assert win.serial_mgr.terminal_connected is True
    assert win.serial_mgr.transport_connected is True
    assert win.remote_list.count() == 0
