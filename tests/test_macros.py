"""Unit tests for the floating Macro Window and its configuration (v2.21).

Exercise the macro-button feature headlessly under an offscreen Qt platform:
the ``macro_<n>_*`` settings defaults, the reflowing :class:`FlowLayout`, the
:class:`MacroWindow` palette (button build/click/close), the "Macros" checkbox
wiring on the Terminal Window, the keystroke-script execution path, and the
:class:`MacroConfigDialog` round-trip and Test button.

Satisfies: FR-162, FR-164, FR-021b, UIR-096, UIR-097, UIR-098.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402

from cpm_fm.app import MainWindow  # noqa: E402
from cpm_fm.gui.config_dialogs import ConfigDialog, MacroConfigDialog  # noqa: E402
from cpm_fm.gui.flow_layout import FlowLayout  # noqa: E402
from cpm_fm.gui.macro_window import MacroWindow  # noqa: E402
from cpm_fm.gui.terminal_window import TerminalWindow  # noqa: E402
from cpm_fm.gui.window_state import WindowState  # noqa: E402
from cpm_fm.utils import i18n  # noqa: E402
from cpm_fm.utils.config_handler import DEFAULT_SETTINGS  # noqa: E402


@pytest.fixture(autouse=True)
def _english_language():
    # The translator is a process-wide singleton; force English so assertions on
    # English literals are stable (FR-124).
    i18n.set_language(i18n.DEFAULT_LANGUAGE)
    yield
    i18n.set_language(i18n.DEFAULT_LANGUAGE)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def state(tmp_path):
    settings = QSettings(str(tmp_path / "state.ini"), QSettings.Format.IniFormat)
    return WindowState(settings)


# --------------------------------------------------------------------------- #
# Settings defaults
# --------------------------------------------------------------------------- #


def test_macro_settings_defaults_present_and_empty():
    """Verifies: FR-162, FR-021b."""
    # FR-162/FR-021b: ten label + ten sequence slots, all default empty.
    for i in range(1, 11):
        assert DEFAULT_SETTINGS[f"macro_{i}_label"] == ""
        assert DEFAULT_SETTINGS[f"macro_{i}_seq"] == ""


# --------------------------------------------------------------------------- #
# FlowLayout
# --------------------------------------------------------------------------- #


def test_flow_layout_holds_and_reports_items(qapp):
    """Verifies: UIR-097."""
    # UIR-097: the flow layout tracks the widgets added to it and reports a
    # height for a given width (the mechanism that lets the buttons reflow).
    from PySide6.QtWidgets import QWidget

    host = QWidget()
    layout = FlowLayout(host)
    for _ in range(3):
        layout.addWidget(QPushButton("x"))
    try:
        assert layout.count() == 3
        assert layout.hasHeightForWidth() is True
        assert layout.heightForWidth(200) > 0
    finally:
        host.deleteLater()


# --------------------------------------------------------------------------- #
# MacroWindow
# --------------------------------------------------------------------------- #


def test_macro_window_builds_buttons_and_click_invokes_callback(qapp):
    """Verifies: UIR-097, FR-162."""
    # UIR-097/FR-162: one button per configured slot, in order; clicking a button
    # hands its keystroke script to the click callback.
    clicked: list[str] = []
    win = MacroWindow(None, click_callback=clicked.append)
    try:
        win.set_macros([("Dir", "SEND DIR"), ("Reset", "SENDRAW 03")])
        assert win._flow.count() == 2
        buttons = win.centralWidget().findChildren(QPushButton)
        assert [b.text() for b in buttons] == ["Dir", "Reset"]
        buttons[1].click()
        assert clicked == ["SENDRAW 03"]
    finally:
        win.deleteLater()


def test_macro_window_rebuild_replaces_buttons(qapp):
    """Verifies: UIR-097."""
    # UIR-097: refreshing the palette clears the previous buttons before adding
    # the new set (so a re-config does not accumulate stale buttons).
    win = MacroWindow(None)
    try:
        win.set_macros([("A", "SEND A"), ("B", "SEND B"), ("C", "SEND C")])
        assert win._flow.count() == 3
        win.set_macros([("A", "SEND A")])
        assert win._flow.count() == 1
    finally:
        win.deleteLater()


def test_macro_window_close_hides_and_notifies(qapp):
    """Verifies: FR-164."""
    # FR-164: closing the palette hides it (it persists) and notifies the owner
    # so the Terminal Window's checkbox can be cleared.
    hidden: list[int] = []
    win = MacroWindow(None, hidden_callback=lambda: hidden.append(1))
    try:
        win.show()
        win.close()
        assert win.isVisible() is False
        assert hidden == [1]
    finally:
        win.deleteLater()


# --------------------------------------------------------------------------- #
# Terminal Window checkbox
# --------------------------------------------------------------------------- #


def test_terminal_window_has_macros_checkbox(qapp):
    """Verifies: UIR-096."""
    # UIR-096: the Terminal Window carries an unchecked "Macros" checkbox.
    term = TerminalWindow(None)
    try:
        assert term.chk_macros.text() == "Macros"
        assert term.chk_macros.isChecked() is False
    finally:
        term.deleteLater()


# --------------------------------------------------------------------------- #
# MainWindow wiring
# --------------------------------------------------------------------------- #


def test_macros_checkbox_toggles_macro_window(qapp, state):
    """Verifies: UIR-096, FR-164."""
    # UIR-096/FR-164: checking the box creates and shows the palette; unchecking
    # it hides the palette.
    win = MainWindow(state)
    try:
        win.settings = dict(DEFAULT_SETTINGS)
        win.settings["macro_1_label"] = "Dir"
        win.settings["macro_1_seq"] = "SEND DIR"
        win.show_terminal()
        assert win.macro_win is None

        win.terminal_win.chk_macros.setChecked(True)
        assert win.macro_win is not None
        assert win.macro_win.isVisible() is True

        win.terminal_win.chk_macros.setChecked(False)
        assert win.macro_win.isVisible() is False
    finally:
        win.close()


def test_refresh_macro_buttons_shows_only_configured_slots(qapp, state):
    """Verifies: UIR-097, FR-021b."""
    # UIR-097: a slot appears only when both its label and its keystroke script
    # are non-empty; label-only, script-only, and blank slots are skipped.
    win = MainWindow(state)
    try:
        win.settings = dict(DEFAULT_SETTINGS)
        win.settings["macro_1_label"] = "Dir"
        win.settings["macro_1_seq"] = "SEND DIR"
        win.settings["macro_2_label"] = "NoScript"  # label only -> skipped
        win.settings["macro_3_seq"] = "SEND X"  # script only -> skipped
        win.show_terminal()
        win._show_macro_window()
        assert win.macro_win._flow.count() == 1
    finally:
        win.close()


def test_macro_window_hidden_clears_checkbox(qapp, state):
    """Verifies: FR-164."""
    # FR-164: when the palette is closed via its window control it clears the
    # Terminal Window's Macros checkbox (kept in sync).
    win = MainWindow(state)
    try:
        win.settings = dict(DEFAULT_SETTINGS)
        win.show_terminal()
        win.terminal_win.chk_macros.setChecked(True)
        assert win.terminal_win.chk_macros.isChecked() is True
        win.macro_win.close()
        assert win.terminal_win.chk_macros.isChecked() is False
    finally:
        win.close()


# --------------------------------------------------------------------------- #
# Script execution
# --------------------------------------------------------------------------- #


def test_run_macro_script_runs_on_worker_thread(qapp, state, monkeypatch):
    """Verifies: FR-162, NFR-004."""
    # FR-162/NFR-004: with the port open, a non-empty script is dispatched to a
    # worker thread targeting _run_sequence_logic with the script.
    import cpm_fm.gui.mw_remote as mw_remote

    win = MainWindow(state)
    try:
        win.serial_mgr.terminal_connected = True
        captured = {}

        class _RecordingThread:
            def __init__(self, *a, target=None, args=(), daemon=None, **k):
                captured["target"] = target
                captured["args"] = args

            def start(self):
                pass

        monkeypatch.setattr(mw_remote.threading, "Thread", _RecordingThread)
        win.run_macro_script("SEND DIR")
        assert captured["target"] == win._run_sequence_logic
        assert captured["args"] == ("SEND DIR",)
    finally:
        win.close()


def test_run_macro_script_guards_when_disconnected(qapp, state, monkeypatch):
    """Verifies: FR-162, FR-098."""
    # FR-098: with the Terminal Port closed the script is not sent and the
    # not-connected status is shown; no worker thread is started.
    import cpm_fm.gui.mw_remote as mw_remote

    win = MainWindow(state)
    try:
        win.serial_mgr.terminal_connected = False
        started = []
        monkeypatch.setattr(
            mw_remote.threading, "Thread", lambda *a, **k: started.append(a) or _Noop()
        )
        win.run_macro_script("SEND DIR")
        assert started == []
        assert win.statusBar().currentMessage() == "Terminal port not connected - cannot send"
    finally:
        win.close()


def test_run_macro_script_empty_is_noop(qapp, state, monkeypatch):
    """Verifies: FR-162."""
    # An empty/whitespace script starts no worker and touches nothing.
    import cpm_fm.gui.mw_remote as mw_remote

    win = MainWindow(state)
    try:
        win.serial_mgr.terminal_connected = True
        started = []
        monkeypatch.setattr(
            mw_remote.threading, "Thread", lambda *a, **k: started.append(a) or _Noop()
        )
        win.run_macro_script("   ")
        assert started == []
    finally:
        win.close()


def test_run_sequence_logic_executes_directives(qapp, state, monkeypatch):
    """Verifies: FR-162."""
    # FR-162: the shared executor drives SEND via handle_terminal_send (EOL added
    # there), SENDRAW as raw control bytes, and WAIT as a sleep, in order.
    import cpm_fm.gui.mw_remote as mw_remote

    win = MainWindow(state)
    try:
        win.serial_mgr.terminal_connected = True
        sent: list[str] = []
        raw: list[tuple] = []
        monkeypatch.setattr(win, "handle_terminal_send", lambda t: sent.append(t))
        monkeypatch.setattr(
            win.serial_mgr, "send_raw", lambda port, data: raw.append((port, data)) or True
        )
        monkeypatch.setattr(mw_remote.time, "sleep", lambda s: None)
        win._run_sequence_logic("SEND DIR\nSENDRAW 03\nWAIT 0.01")
        assert sent == ["DIR"]
        assert raw == [("terminal", b"\x03")]
    finally:
        win.close()


def test_run_sequence_logic_parse_error_sets_status(qapp, state):
    """Verifies: FR-162."""
    # A malformed script runs nothing and reports the failure in the status bar.
    win = MainWindow(state)
    try:
        win.serial_mgr.terminal_connected = True
        win._run_sequence_logic("NOPE bad directive")
        assert win.statusBar().currentMessage() == "Macro failed - check its keystroke sequence"
    finally:
        win.close()


# --------------------------------------------------------------------------- #
# MacroConfigDialog
# --------------------------------------------------------------------------- #


def test_macro_config_round_trips_label_and_sequence(qapp, monkeypatch):
    """Verifies: UIR-098, FR-021b."""
    # UIR-098/FR-021b: the dialog seeds each slot from settings and returns all
    # twenty macro keys on Save, preserving the edited label and script.
    monkeypatch.setattr(ConfigDialog, "exec", lambda self: 0)

    saved: dict = {}
    dlg = MacroConfigDialog(None, {"macro_1_label": "Dir", "macro_1_seq": "SEND DIR"}, saved.update)
    try:
        assert dlg.entries["macro_1_label"].text() == "Dir"
        assert dlg.entries["macro_1_seq"].toPlainText() == "SEND DIR"
        dlg.entries["macro_2_label"].setText("Reset")
        dlg.entries["macro_2_seq"].setPlainText("SENDRAW 03")
        dlg.save()
        assert saved["macro_1_label"] == "Dir"
        assert saved["macro_2_label"] == "Reset"
        assert saved["macro_2_seq"] == "SENDRAW 03"
        # All ten slots are written back.
        assert all(f"macro_{i}_label" in saved for i in range(1, 11))
        assert all(f"macro_{i}_seq" in saved for i in range(1, 11))
    finally:
        dlg.deleteLater()


def test_macro_config_uses_tabbed_layout(qapp, monkeypatch):
    """Verifies: UIR-098."""
    # UIR-098: the ten slots are presented as a tabbed layout, one tab per
    # button, labelled "Button 1" .. "Button 10".
    from PySide6.QtWidgets import QTabWidget

    monkeypatch.setattr(ConfigDialog, "exec", lambda self: 0)
    dlg = MacroConfigDialog(None, {}, lambda s: None)
    try:
        tabs = dlg.findChildren(QTabWidget)
        assert len(tabs) == 1
        tab = tabs[0]
        assert tab.count() == 10
        assert [tab.tabText(i) for i in range(tab.count())] == [f"Button {n}" for n in range(1, 11)]
    finally:
        dlg.deleteLater()


def test_macro_config_test_button_runs_typed_script(qapp, state, monkeypatch):
    """Verifies: UIR-098, FR-162."""
    # UIR-098: the per-slot Test button runs that slot's currently entered script
    # via the owner's macro runner when the Terminal Port is open.
    monkeypatch.setattr(ConfigDialog, "exec", lambda self: 0)
    win = MainWindow(state)
    try:
        win.serial_mgr.terminal_connected = True
        ran: list[str] = []
        monkeypatch.setattr(win, "run_macro_script", ran.append)
        dlg = MacroConfigDialog(win, {}, lambda s: None)
        try:
            dlg.entries["macro_3_seq"].setPlainText("SEND DIR")
            dlg._run_test(3)
            assert ran == ["SEND DIR"]
        finally:
            dlg.deleteLater()
    finally:
        win.close()


def test_macro_config_test_button_guards_disconnected(qapp, state, monkeypatch):
    """Verifies: UIR-098, FR-098."""
    # UIR-098: with the Terminal Port closed the Test button shows the standard
    # not-connected error and sends nothing.
    monkeypatch.setattr(ConfigDialog, "exec", lambda self: 0)
    win = MainWindow(state)
    try:
        win.serial_mgr.terminal_connected = False
        errors = []
        monkeypatch.setattr(
            "cpm_fm.gui.config_dialogs.QMessageBox.critical",
            lambda *a, **k: errors.append(a[1:]),
        )
        ran: list[str] = []
        monkeypatch.setattr(win, "run_macro_script", ran.append)
        dlg = MacroConfigDialog(win, {}, lambda s: None)
        try:
            dlg.entries["macro_1_seq"].setPlainText("SEND DIR")
            dlg._run_test(1)
            assert errors == [("Error", "Terminal port not connected")]
            assert ran == []
        finally:
            dlg.deleteLater()
    finally:
        win.close()


def test_menu_macro_config_saves_subset_and_refreshes(qapp, state, monkeypatch, tmp_path):
    """Verifies: FR-021b."""
    # FR-021b: the Macro dialog Save writes only the macro settings to the loaded
    # config file (leaving other settings untouched) and refreshes the live
    # palette.
    import json

    win = MainWindow(state)
    try:
        cfg = tmp_path / "active.json"
        cfg.write_text(
            json.dumps({"terminal_port": "COM1", "speed": "9600", "eol": "CR"}),
            encoding="utf-8",
        )
        win.window_state.last_config = str(cfg)

        captured = {}

        def fake_dialog(parent, settings, callback, window_state):
            captured["callback"] = callback

        monkeypatch.setattr("cpm_fm.gui.mw_config.MacroConfigDialog", fake_dialog)
        refreshed = []
        monkeypatch.setattr(win, "_refresh_macro_buttons", lambda: refreshed.append(1))

        win.menu_macro_config()
        captured["callback"]({"macro_1_label": "Dir", "macro_1_seq": "SEND DIR"})

        on_disk = json.loads(cfg.read_text(encoding="utf-8"))
        assert on_disk["macro_1_label"] == "Dir"
        assert on_disk["macro_1_seq"] == "SEND DIR"
        # Other settings untouched.
        assert on_disk["terminal_port"] == "COM1"
        assert on_disk["speed"] == "9600"
        # Live palette refreshed.
        assert refreshed == [1]
    finally:
        win.close()


class _Noop:
    """A do-nothing stand-in for threading.Thread in guard tests."""

    def start(self):
        pass
