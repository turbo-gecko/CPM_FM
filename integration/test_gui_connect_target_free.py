"""Target-free GUI connection/error workflows (MT-C02--MT-C04).

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
