"""Unit tests for the macro buttons and the Terminal Config dialog (v2.21/v2.25).

Exercise the macro-button feature headlessly under an offscreen Qt platform: the
``macro_<n>_*`` settings defaults, the keystroke-script execution path, and the
:class:`TerminalConfigDialog` — its Terminal tab (Terminal Type / Local Echo /
Autoscroll) and its Macros tab (the ten Macro slots, round-trip, and Test
button). The floating Macro Window and its checkbox were removed in v2.25; macros
are now run from the Terminal Window context-menu Macros submenu (covered in
``test_gui_smoke.py``).

Satisfies: FR-162, FR-021b, FR-021c, UIR-098, UIR-103, UIR-103a, UIR-103d.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication, QTabWidget  # noqa: E402

from cpm_fm.app import MainWindow  # noqa: E402
from cpm_fm.gui.config_dialogs import ConfigDialog, TerminalConfigDialog  # noqa: E402
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
# TerminalConfigDialog — Terminal tab
# --------------------------------------------------------------------------- #


def test_terminal_config_has_terminal_and_macros_tabs(qapp, monkeypatch):
    """Verifies: UIR-103, UIR-103a, UIR-103d."""
    # UIR-103: the dialog is a two-tab layout — a Terminal tab and a Macros tab;
    # the Macros tab holds a nested ten-slot tab widget (UIR-103d/UIR-098).
    monkeypatch.setattr(ConfigDialog, "exec", lambda self: 0)
    dlg = TerminalConfigDialog(None, {}, lambda s: None)
    try:
        tabs = dlg.findChildren(QTabWidget)
        # The outer (2-tab) widget plus the nested macro (10-tab) widget.
        assert len(tabs) == 2
        outer = next(t for t in tabs if t.count() == 2)
        assert [outer.tabText(i) for i in range(2)] == ["Terminal", "Macros"]
        inner = next(t for t in tabs if t.count() == 10)
        assert [inner.tabText(i) for i in range(10)] == [f"Macro {n}" for n in range(1, 11)]
    finally:
        dlg.deleteLater()


def test_terminal_config_terminal_tab_round_trips(qapp, monkeypatch):
    """Verifies: UIR-103a, UIR-034, UIR-103b, UIR-103c."""
    # UIR-103a: the Terminal tab seeds Terminal Type / Local Echo / Autoscroll
    # from settings and returns them on Save (checkboxes as ON/OFF).
    monkeypatch.setattr(ConfigDialog, "exec", lambda self: 0)
    saved: dict = {}
    dlg = TerminalConfigDialog(
        None,
        {"terminal_type": "VT52", "local_echo": "ON", "autoscroll": "OFF"},
        saved.update,
    )
    try:
        assert dlg.entries["terminal_type"].currentText() == "VT52"
        assert dlg.entries["local_echo"].isChecked() is True
        assert dlg.entries["autoscroll"].isChecked() is False
        dlg.entries["terminal_type"].setCurrentText("ADM-3A")
        dlg.entries["autoscroll"].setChecked(True)
        dlg.save()
        assert saved["terminal_type"] == "ADM-3A"
        assert saved["local_echo"] == "ON"
        assert saved["autoscroll"] == "ON"
    finally:
        dlg.deleteLater()


# --------------------------------------------------------------------------- #
# TerminalConfigDialog — Macros tab
# --------------------------------------------------------------------------- #


def test_terminal_config_macros_round_trip_label_and_sequence(qapp, monkeypatch):
    """Verifies: UIR-098, UIR-103d, FR-021b."""
    # UIR-098/FR-021b: the Macros tab seeds each slot from settings and returns
    # all twenty macro keys on Save, preserving the edited label and script.
    monkeypatch.setattr(ConfigDialog, "exec", lambda self: 0)

    saved: dict = {}
    dlg = TerminalConfigDialog(
        None, {"macro_1_label": "Dir", "macro_1_seq": "SEND DIR"}, saved.update
    )
    try:
        assert dlg.entries["macro_1_label"].text() == "Dir"
        assert dlg.entries["macro_1_seq"].toPlainText() == "SEND DIR"
        dlg.entries["macro_2_label"].setText("Reset")
        dlg.entries["macro_2_seq"].setPlainText("SENDRAW 03")
        dlg.save()
        assert saved["macro_1_label"] == "Dir"
        assert saved["macro_2_label"] == "Reset"
        assert saved["macro_2_seq"] == "SENDRAW 03"
        # All ten slots are written back, plus the three terminal settings.
        assert all(f"macro_{i}_label" in saved for i in range(1, 11))
        assert all(f"macro_{i}_seq" in saved for i in range(1, 11))
        assert {"terminal_type", "local_echo", "autoscroll"} <= set(saved)
    finally:
        dlg.deleteLater()


def test_terminal_config_test_button_runs_typed_script(qapp, state, monkeypatch):
    """Verifies: UIR-103d, FR-162."""
    # UIR-103d: the per-slot Test button runs that slot's currently entered script
    # via the owner's macro runner when the Terminal Port is open.
    monkeypatch.setattr(ConfigDialog, "exec", lambda self: 0)
    win = MainWindow(state)
    try:
        win.serial_mgr.terminal_connected = True
        ran: list[str] = []
        monkeypatch.setattr(win, "run_macro_script", ran.append)
        dlg = TerminalConfigDialog(win, {}, lambda s: None)
        try:
            dlg.entries["macro_3_seq"].setPlainText("SEND DIR")
            dlg._run_test(3)
            assert ran == ["SEND DIR"]
        finally:
            dlg.deleteLater()
    finally:
        win.close()


def test_terminal_config_test_button_guards_disconnected(qapp, state, monkeypatch):
    """Verifies: UIR-103d, FR-098."""
    # UIR-103d: with the Terminal Port closed the Test button shows the standard
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
        dlg = TerminalConfigDialog(win, {}, lambda s: None)
        try:
            dlg.entries["macro_1_seq"].setPlainText("SEND DIR")
            dlg._run_test(1)
            assert errors == [("Error", "Terminal port not connected")]
            assert ran == []
        finally:
            dlg.deleteLater()
    finally:
        win.close()


# --------------------------------------------------------------------------- #
# MainWindow wiring — Config > Terminal save
# --------------------------------------------------------------------------- #


def test_menu_terminal_config_saves_subset_and_applies(qapp, state, monkeypatch, tmp_path):
    """Verifies: FR-021c, FR-021b, UIR-034, FR-093."""
    # FR-021c: the Terminal dialog Save writes only the terminal + macro settings
    # to the loaded config file (leaving other settings untouched) and applies
    # them live (engine terminal type, local-echo flag).
    import json

    win = MainWindow(state)
    try:
        cfg = tmp_path / "active.json"
        cfg.write_text(
            json.dumps({"terminal_port": "COM1", "speed": "9600", "eol": "CR"}),
            encoding="utf-8",
        )
        win.window_state.last_config = str(cfg)
        win.settings = dict(DEFAULT_SETTINGS)
        win.settings["terminal_port"] = "COM1"

        captured = {}

        def fake_dialog(parent, settings, callback, window_state):
            captured["callback"] = callback

        monkeypatch.setattr("cpm_fm.gui.mw_config.TerminalConfigDialog", fake_dialog)

        win.menu_terminal_config()
        captured["callback"](
            {
                "terminal_type": "VT52",
                "local_echo": "ON",
                "autoscroll": "OFF",
                "macro_1_label": "Dir",
                "macro_1_seq": "SEND DIR",
            }
        )

        on_disk = json.loads(cfg.read_text(encoding="utf-8"))
        assert on_disk["terminal_type"] == "VT52"
        assert on_disk["local_echo"] == "ON"
        assert on_disk["macro_1_label"] == "Dir"
        # Other settings untouched.
        assert on_disk["terminal_port"] == "COM1"
        assert on_disk["speed"] == "9600"
        # Applied live: engine terminal type and the cached local-echo flag.
        assert win._term_engine.terminal_type == "VT52"
        assert win._local_echo is True
    finally:
        win.close()


class _Noop:
    """A do-nothing stand-in for threading.Thread in guard tests."""

    def start(self):
        pass
