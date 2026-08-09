"""Target-free configuration file lifecycle workflows (MT-L01--MT-L15)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cpm_fm.utils import i18n

_CONFIG_PROCESS_PROBE_PREFIX = "__CPM_FM_CONFIG_PROCESS_PROBE__="


def _run_config_process_probe(
    mode: str, config_path: str, state_path: str, history_path: str
) -> None:
    """Exercise config persistence in a standalone offscreen application process."""
    import json

    from PySide6.QtCore import QSettings
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QApplication

    from cpm_fm.app import MainWindow
    from cpm_fm.gui.window_state import WindowState
    from cpm_fm.utils import i18n
    from cpm_fm.utils.transfer_history import TransferHistory

    i18n.set_language(i18n.DEFAULT_LANGUAGE)
    app = QApplication.instance() or QApplication([])
    settings_store = QSettings(state_path, QSettings.Format.IniFormat)
    state = WindowState(settings_store)
    win = MainWindow(state, TransferHistory(history_path))

    if mode == "load":
        from cpm_fm.gui import mw_config

        mw_config.QFileDialog.getOpenFileName = lambda *args, **kwargs: (
            config_path,
            "JSON files (*.json)",
        )
        load_text = i18n.tr("menu.file.load")
        action = next(action for action in win.findChildren(QAction) if action.text() == load_text)
        action.trigger()
        app.processEvents()
    elif mode != "relaunch":  # pragma: no cover - guarded by the parent tests
        raise ValueError(f"unknown probe mode: {mode}")

    payload = {
        "settings": win.settings,
        "last_config": state.last_config,
        "config_name": win._config_name,
        "title": win.windowTitle(),
        "host_dir": win.host_dir,
        "image_dir": win.image_dir,
        "terminal_type": win._term_engine.terminal_type,
        "local_echo": win._local_echo,
    }
    win.close()
    app.processEvents()
    settings_store.sync()
    print(_CONFIG_PROCESS_PROBE_PREFIX + json.dumps(payload, sort_keys=True))


def _config_process_runner(tmp_path):
    """Return paths and a runner for isolated config-lifecycle processes."""
    import json
    import os
    import subprocess
    import sys

    state_path = tmp_path / "config-state.ini"
    history_path = tmp_path / "config-history.json"
    test_file = Path(__file__).resolve()
    environment = os.environ.copy()
    environment["QT_QPA_PLATFORM"] = "offscreen"

    def run(mode: str, config_path: Path) -> dict[str, object]:
        completed = subprocess.run(
            [
                sys.executable,
                str(test_file),
                "--config-process-probe",
                mode,
                str(config_path),
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
            f"config {mode} process failed\nstdout:\n{completed.stdout}"
            f"\nstderr:\n{completed.stderr}"
        )
        probe_line = next(
            line
            for line in completed.stdout.splitlines()
            if line.startswith(_CONFIG_PROCESS_PROBE_PREFIX)
        )
        return json.loads(probe_line.removeprefix(_CONFIG_PROCESS_PROBE_PREFIX))

    return state_path, run


def _action(win, key: str):
    """Return the translated QAction registered for ``key``."""
    from PySide6.QtGui import QAction

    text = i18n.tr(key)
    return next(action for action in win.findChildren(QAction) if action.text() == text)


def _capture_dialog(monkeypatch, win, action_key: str):
    """Trigger ``action_key`` and return the constructed real modal dialog."""
    from PySide6.QtWidgets import QDialog

    captured = {}

    def capture(dialog):
        captured["dialog"] = dialog
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(QDialog, "exec", capture)
    _action(win, action_key).trigger()
    return captured["dialog"]


def _click_save(dialog) -> None:
    """Click the translated Save button in a captured config dialog."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QPushButton

    button = next(
        child
        for child in dialog.findChildren(QPushButton)
        if child.text() == i18n.tr("button.save")
    )
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)


@pytest.mark.gui_integration
@pytest.mark.mt("MT-L01", "FR-010", "IFR-004")
def test_load_config_action_opens_json_file_dialog(gui_no_target, monkeypatch):
    """Load Config presents a JSON-filtered native file-selection dialog.

    Verifies: FR-010, IFR-004.
    """
    calls: list[tuple[str, str, str]] = []

    def choose(parent, title, directory, file_filter):
        calls.append((title, directory, file_filter))
        return "", file_filter

    monkeypatch.setattr("cpm_fm.gui.mw_config.QFileDialog.getOpenFileName", choose)
    _action(gui_no_target, "menu.file.load").trigger()

    assert calls == [
        (
            i18n.tr("dialog.load_config.title"),
            "",
            i18n.tr("dialog.json_filter"),
        )
    ]
    assert "*.json" in calls[0][2].lower()


@pytest.mark.gui_integration
@pytest.mark.mt("MT-L02", "FR-011", "NFR-002")
def test_flat_and_nested_loads_replace_store_and_normalise_serial_keys(
    gui_no_target, monkeypatch, tmp_path
):
    """Both config shapes fully replace settings and feed normalised serial values.

    Verifies: FR-011, NFR-002.
    """
    flat = {
        "terminal_port": "FLAT-TERM",
        "transport_port": "FLAT-XFER",
        "speed": "9600",
        "data": "7",
        "stopbits": "2",
    }
    nested = {
        "serial": {
            "terminal_port": "NESTED-TERM",
            "transfer_port": "NESTED-XFER",
            "speed": "4800",
            "data_bits": "5",
            "stop_bits": "1",
        }
    }
    flat_path = tmp_path / "flat.json"
    nested_path = tmp_path / "nested.json"
    flat_path.write_text(json.dumps(flat), encoding="utf-8")
    nested_path.write_text(json.dumps(nested), encoding="utf-8")
    choices = iter((str(flat_path), str(nested_path)))
    monkeypatch.setattr(
        "cpm_fm.gui.mw_config.QFileDialog.getOpenFileName",
        lambda *args, **kwargs: (next(choices), "JSON files (*.json)"),
    )

    opened: list[dict] = []

    class FakeSerial:
        def __init__(self, **kwargs):
            opened.append(kwargs)
            self.is_open = True

        def close(self):
            self.is_open = False

    monkeypatch.setattr("cpm_fm.terminal.serial_manager.serial.Serial", FakeSerial)

    _action(gui_no_target, "menu.file.load").trigger()
    assert gui_no_target.settings == flat
    assert gui_no_target.serial_mgr.open_port("transport", gui_no_target.settings)
    assert opened[-1]["port"] == "FLAT-XFER"
    assert (opened[-1]["baudrate"], opened[-1]["bytesize"], opened[-1]["stopbits"]) == (
        9600,
        7,
        2,
    )

    _action(gui_no_target, "menu.file.load").trigger()
    assert gui_no_target.settings == nested
    assert "terminal_port" not in gui_no_target.settings
    assert gui_no_target.serial_mgr.open_port("transport", gui_no_target.settings)
    assert opened[-1]["port"] == "NESTED-XFER"
    assert (opened[-1]["baudrate"], opened[-1]["bytesize"], opened[-1]["stopbits"]) == (
        4800,
        5,
        1,
    )


@pytest.mark.gui_integration
@pytest.mark.mt("MT-L03", "FR-012")
def test_unknown_loaded_key_survives_full_save(gui_no_target, monkeypatch, tmp_path):
    """Unknown configuration keys are accepted and preserved verbatim.

    Verifies: FR-012.
    """
    source = tmp_path / "with-extension.json"
    destination = tmp_path / "round-trip.json"
    source.write_text(json.dumps({"terminal_port": "COM7", "foo": 123}), encoding="utf-8")
    monkeypatch.setattr(
        "cpm_fm.gui.mw_config.QFileDialog.getOpenFileName",
        lambda *args, **kwargs: (str(source), "JSON files (*.json)"),
    )
    monkeypatch.setattr(
        "cpm_fm.gui.mw_config.QFileDialog.getSaveFileName",
        lambda *args, **kwargs: (str(destination), "JSON files (*.json)"),
    )

    _action(gui_no_target, "menu.file.load").trigger()
    assert gui_no_target.settings["foo"] == 123
    _action(gui_no_target, "menu.file.save").trigger()

    assert json.loads(destination.read_text(encoding="utf-8"))["foo"] == 123


@pytest.mark.gui_integration
@pytest.mark.mt("MT-L04", "FR-017")
def test_load_config_clears_existing_remote_listing(gui_no_target, monkeypatch, tmp_path):
    """Loading any configuration invalidates and clears the Remote pane.

    Verifies: FR-017.
    """
    config = tmp_path / "replacement.json"
    config.write_text(json.dumps({"terminal_port": "COM8"}), encoding="utf-8")
    gui_no_target.remote_list.addItems(["STALE.TXT", "OLD.COM"])
    monkeypatch.setattr(
        "cpm_fm.gui.mw_config.QFileDialog.getOpenFileName",
        lambda *args, **kwargs: (str(config), "JSON files (*.json)"),
    )

    _action(gui_no_target, "menu.file.load").trigger()

    assert gui_no_target.remote_list.count() == 0
    assert gui_no_target.settings == {"terminal_port": "COM8"}


@pytest.mark.gui_integration
@pytest.mark.mt("MT-L05", "FR-013", "FR-014")
def test_save_config_writes_entire_current_settings_store(gui_no_target, monkeypatch, tmp_path):
    """Save Config writes serial, general, remote, and unknown settings together.

    Verifies: FR-013, FR-014.
    """
    destination = tmp_path / "complete.json"
    gui_no_target.settings = {
        "terminal_port": "COM11",
        "speed": "19200",
        "debug_logging": "ON",
        "viewer_cmd": "viewer $1",
        "list_files_cmd": "SD DIR",
        "custom_extension": {"enabled": True},
    }
    gui_no_target.host_dir = str(tmp_path / "host")
    gui_no_target.image_dir = str(tmp_path / "images")
    monkeypatch.setattr(
        "cpm_fm.gui.mw_config.QFileDialog.getSaveFileName",
        lambda *args, **kwargs: (str(destination), "JSON files (*.json)"),
    )

    _action(gui_no_target, "menu.file.save").trigger()

    saved = json.loads(destination.read_text(encoding="utf-8"))
    assert saved == gui_no_target.settings
    assert saved["terminal_port"] == "COM11"
    assert saved["debug_logging"] == "ON"
    assert saved["list_files_cmd"] == "SD DIR"
    assert saved["custom_extension"] == {"enabled": True}
    assert saved["host_directory"] == gui_no_target.host_dir
    assert saved["image_directory"] == gui_no_target.image_dir


@pytest.mark.gui_integration
@pytest.mark.mt("MT-L06", "FR-006", "FR-010", "FR-013")
def test_load_dialog_reuses_last_config_folder_not_host_folder(
    gui_no_target, monkeypatch, tmp_path
):
    """A successful save supplies the next Load dialog's independent folder.

    Verifies: FR-006, FR-010, FR-013.
    """
    config_dir = tmp_path / "configs"
    host_dir = tmp_path / "host"
    config_dir.mkdir()
    host_dir.mkdir()
    destination = config_dir / "remembered.json"
    gui_no_target.host_dir = str(host_dir)
    monkeypatch.setattr(
        "cpm_fm.gui.mw_config.QFileDialog.getSaveFileName",
        lambda *args, **kwargs: (str(destination), "JSON files (*.json)"),
    )
    _action(gui_no_target, "menu.file.save").trigger()

    opened_from: list[str] = []

    def choose(parent, title, directory, file_filter):
        opened_from.append(directory)
        return "", file_filter

    monkeypatch.setattr("cpm_fm.gui.mw_config.QFileDialog.getOpenFileName", choose)
    _action(gui_no_target, "menu.file.load").trigger()

    assert gui_no_target.window_state.last_config_dir == str(config_dir)
    assert opened_from == [str(config_dir)]
    assert opened_from[0] != gui_no_target.host_dir


@pytest.mark.gui_integration
@pytest.mark.mt("MT-L07", "FR-005")
def test_last_loaded_config_is_applied_after_real_process_restart(tmp_path):
    """A second application process automatically applies the remembered config.

    Verifies: FR-005.
    """
    host_dir = tmp_path / "remembered-host"
    image_dir = tmp_path / "remembered-images"
    host_dir.mkdir()
    image_dir.mkdir()
    config_path = tmp_path / "remembered-system.json"
    expected_settings = {
        "terminal_port": "PERSIST-TERM",
        "transport_port": "PERSIST-XFER",
        "speed": "19200",
        "terminal_type": "ADM-3A",
        "local_echo": "ON",
        "autoscroll": "OFF",
        "host_directory": str(host_dir),
        "image_directory": str(image_dir),
        "process_marker": "MT-L07",
    }
    config_path.write_text(json.dumps(expected_settings), encoding="utf-8")
    state_path, run = _config_process_runner(tmp_path)

    loaded = run("load", config_path)
    assert loaded == {
        "settings": expected_settings,
        "last_config": str(config_path),
        "config_name": "remembered-system",
        "title": i18n.tr(
            "app.title_with_config",
            app=i18n.tr("app.title"),
            config="remembered-system",
        ),
        "host_dir": str(host_dir),
        "image_dir": str(image_dir),
        "terminal_type": "ADM-3A",
        "local_echo": True,
    }
    assert state_path.exists()

    assert run("relaunch", config_path) == loaded


@pytest.mark.gui_integration
@pytest.mark.mt("MT-L08", "FR-005", "FR-003")
def test_missing_remembered_config_starts_unconfigured_in_new_process(tmp_path):
    """A deleted remembered config yields a safe unconfigured relaunch.

    Verifies: FR-005, FR-003.
    """
    config_path = tmp_path / "removed-before-relaunch.json"
    config_path.write_text(
        json.dumps(
            {
                "terminal_port": "SHOULD-NOT-RESTORE",
                "terminal_type": "ADM-3A",
                "local_echo": "ON",
                "process_marker": "MT-L08",
            }
        ),
        encoding="utf-8",
    )
    _, run = _config_process_runner(tmp_path)
    loaded = run("load", config_path)
    assert loaded["last_config"] == str(config_path)
    assert loaded["settings"]["process_marker"] == "MT-L08"

    config_path.unlink()
    assert not config_path.exists()

    relaunched = run("relaunch", config_path)
    assert relaunched == {
        "settings": {},
        "last_config": str(config_path),
        "config_name": "",
        "title": i18n.tr("app.title"),
        "host_dir": str(Path.cwd()),
        "image_dir": str(Path.cwd()),
        "terminal_type": "VT100",
        "local_echo": False,
    }


@pytest.mark.gui_integration
@pytest.mark.mt("MT-L09", "FR-018", "FR-019")
def test_new_config_saves_active_file_disconnects_and_resets_application(
    gui_no_target, monkeypatch, tmp_path
):
    """New saves first, disconnects, clears stale state, and forgets the file.

    Verifies: FR-018, FR-019.
    """
    from cpm_fm.utils.config_handler import DEFAULT_SETTINGS

    active = tmp_path / "active.json"
    active.write_text("{}", encoding="utf-8")
    win = gui_no_target
    win.window_state.last_config = str(active)
    win._config_name = "active"
    win._update_window_title()
    win.settings = {
        "terminal_port": "TERM",
        "transport_port": "XFER",
        "speed": "300",
        "marker": "saved-before-reset",
    }
    win.remote_list.addItems(["STALE.TXT"])
    win.serial_mgr.terminal_connected = True
    win.serial_mgr.transport_connected = True
    closed: list[str] = []

    def close_terminal():
        closed.append("terminal")
        win.serial_mgr.terminal_connected = False
        return True

    def close_transport():
        closed.append("transport")
        win.serial_mgr.transport_connected = False
        return True

    monkeypatch.setattr(win.serial_mgr, "close_terminal_port", close_terminal)
    monkeypatch.setattr(win.serial_mgr, "close_transport_port", close_transport)

    _action(win, "menu.file.new").trigger()

    saved = json.loads(active.read_text(encoding="utf-8"))
    assert saved["marker"] == "saved-before-reset"
    assert closed == ["terminal", "transport"]
    assert win.serial_mgr.terminal_connected is False
    assert win.serial_mgr.transport_connected is False
    assert win.remote_list.count() == 0
    assert win.settings == DEFAULT_SETTINGS
    assert win.window_state.last_config == ""
    assert win.host_dir == str(Path.cwd())
    assert win.windowTitle() == i18n.tr("app.title")


@pytest.mark.gui_integration
@pytest.mark.mt("MT-L10", "FR-018")
def test_new_without_active_file_cancels_or_saves_before_reset(
    gui_no_target, monkeypatch, tmp_path
):
    """New is cancelled with its Save dialog, or saves before resetting.

    Verifies: FR-018.
    """
    from cpm_fm.utils.config_handler import DEFAULT_SETTINGS

    win = gui_no_target
    destination = tmp_path / "new-config-save.json"
    choices = iter((("", ""), (str(destination), "JSON files (*.json)")))
    monkeypatch.setattr(
        "cpm_fm.gui.mw_config.QFileDialog.getSaveFileName",
        lambda *args, **kwargs: next(choices),
    )
    win.settings = {"terminal_port": "KEEP", "marker": "pre-new"}
    win.remote_list.addItem("KEEP.TXT")
    win.serial_mgr.terminal_connected = True
    closed: list[str] = []

    def close_terminal():
        closed.append("terminal")
        win.serial_mgr.terminal_connected = False
        return True

    monkeypatch.setattr(win.serial_mgr, "close_terminal_port", close_terminal)
    monkeypatch.setattr(win.serial_mgr, "close_transport_port", lambda: True)

    _action(win, "menu.file.new").trigger()
    assert win.settings == {"terminal_port": "KEEP", "marker": "pre-new"}
    assert win.remote_list.count() == 1
    assert win.serial_mgr.terminal_connected is True
    assert closed == []
    assert not destination.exists()

    _action(win, "menu.file.new").trigger()
    assert json.loads(destination.read_text(encoding="utf-8"))["marker"] == "pre-new"
    assert closed == ["terminal"]
    assert win.remote_list.count() == 0
    assert win.settings == DEFAULT_SETTINGS


@pytest.mark.gui_integration
@pytest.mark.mt("MT-L11", "FR-125", "UIR-005")
def test_loading_named_config_adds_basename_to_plain_window_title(
    gui_no_target, monkeypatch, tmp_path
):
    """The title changes from the app name to app name plus config basename.

    Verifies: FR-125, UIR-005.
    """
    config = tmp_path / "RC2014_Z_Pro.json"
    config.write_text(json.dumps({"terminal_port": "COM16"}), encoding="utf-8")
    monkeypatch.setattr(
        "cpm_fm.gui.mw_config.QFileDialog.getOpenFileName",
        lambda *args, **kwargs: (str(config), "JSON files (*.json)"),
    )

    assert gui_no_target.windowTitle() == i18n.tr("app.title")
    _action(gui_no_target, "menu.file.load").trigger()

    assert gui_no_target.windowTitle() == i18n.tr(
        "app.title_with_config",
        app=i18n.tr("app.title"),
        config="RC2014_Z_Pro",
    )
    assert str(tmp_path) not in gui_no_target.windowTitle()
    assert ".json" not in gui_no_target.windowTitle()


@pytest.mark.gui_integration
@pytest.mark.mt("MT-L12", "FR-125")
def test_new_config_drops_loaded_name_from_window_title(gui_no_target, monkeypatch, tmp_path):
    """New Config returns a loaded-config title to the plain application name.

    Verifies: FR-125.
    """
    config = tmp_path / "named-system.json"
    config.write_text(json.dumps({"terminal_port": "COM3"}), encoding="utf-8")
    gui_no_target.load_config(str(config))
    assert gui_no_target.windowTitle().endswith(" — named-system")
    monkeypatch.setattr(gui_no_target.serial_mgr, "close_terminal_port", lambda: True)
    monkeypatch.setattr(gui_no_target.serial_mgr, "close_transport_port", lambda: True)

    _action(gui_no_target, "menu.file.new").trigger()

    assert gui_no_target.windowTitle() == i18n.tr("app.title")


@pytest.mark.gui_integration
@pytest.mark.mt("MT-L13", "FR-020a")
def test_serial_dialog_saves_only_serial_group_to_loaded_file(gui_no_target, monkeypatch, tmp_path):
    """Serial Save updates its group in place without a Save As dialog.

    Verifies: FR-020a.
    """
    config = tmp_path / "serial-selective.json"
    original = {
        "terminal_port": "COM1",
        "transport_port": "COM2",
        "speed": "9600",
        "debug_logging": "ON",
        "viewer_cmd": "viewer $1",
        "host_directory": "C:/keep/host",
        "list_files_cmd": "DIR B:",
        "terminal_type": "VT52",
        "unknown": 42,
    }
    config.write_text(json.dumps(original), encoding="utf-8")
    gui_no_target.load_config(str(config))
    monkeypatch.setattr("cpm_fm.gui.mw_config.serial.tools.list_ports.comports", lambda: [])
    monkeypatch.setattr(
        "cpm_fm.gui.mw_config.QFileDialog.getSaveFileName",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("Serial Save must not open Save Config")
        ),
    )

    dialog = _capture_dialog(monkeypatch, gui_no_target, "menu.config.serial")
    dialog.entries["speed"].setCurrentText("115200")
    _click_save(dialog)

    saved = json.loads(config.read_text(encoding="utf-8"))
    assert saved["speed"] == "115200"
    for key in (
        "debug_logging",
        "viewer_cmd",
        "host_directory",
        "list_files_cmd",
        "terminal_type",
        "unknown",
    ):
        assert saved[key] == original[key]
    assert (
        gui_no_target.statusBar().currentMessage()
        == i18n.tr("status.serial_settings_saved", path=str(config))[:127]
    )


@pytest.mark.gui_integration
@pytest.mark.mt("MT-L14", "FR-021a")
def test_general_dialog_saves_only_general_group_to_loaded_file(
    gui_no_target, monkeypatch, tmp_path
):
    """General Save updates its group in place and preserves all serial values.

    Verifies: FR-021a.
    """
    config = tmp_path / "general-selective.json"
    original = {
        "terminal_port": "COM4",
        "transport_port": "COM5",
        "speed": "19200",
        "data": "7",
        "parity": "EVEN",
        "stopbits": "2",
        "flow": "XON/XOFF",
        "debug_logging": "OFF",
        "viewer_cmd": "notepad $1",
        "list_files_cmd": "DIR",
        "unknown": "keep",
    }
    config.write_text(json.dumps(original), encoding="utf-8")
    gui_no_target.load_config(str(config))
    monkeypatch.setattr(
        "cpm_fm.gui.mw_config.QFileDialog.getSaveFileName",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("General Save must not open Save Config")
        ),
    )

    dialog = _capture_dialog(monkeypatch, gui_no_target, "menu.config.general")
    dialog.entries["viewer_cmd"].setText("viewer --readonly $1")
    _click_save(dialog)

    saved = json.loads(config.read_text(encoding="utf-8"))
    assert saved["viewer_cmd"] == "viewer --readonly $1"
    for key in (
        "terminal_port",
        "transport_port",
        "speed",
        "data",
        "parity",
        "stopbits",
        "flow",
        "list_files_cmd",
        "unknown",
    ):
        assert saved[key] == original[key]
    assert (
        gui_no_target.statusBar().currentMessage()
        == i18n.tr("status.general_settings_saved", path=str(config))[:127]
    )


@pytest.mark.gui_integration
@pytest.mark.mt("MT-L15", "FR-020a", "FR-021a")
@pytest.mark.parametrize(
    ("action_key", "setting", "new_value"),
    [
        pytest.param("menu.config.serial", "speed", "57600", id="serial"),
        pytest.param("menu.config.general", "viewer_cmd", "viewer $1", id="general"),
    ],
)
def test_group_save_without_loaded_file_warns_and_is_session_only(
    gui_no_target,
    monkeypatch,
    tmp_path,
    action_key,
    setting,
    new_value,
):
    """Unconfigured group Save warns, writes nothing, and applies for this session.

    Verifies: FR-020a, FR-021a.
    """
    win = gui_no_target
    win.window_state.last_config = ""
    files_before = sorted(
        path.relative_to(tmp_path) for path in tmp_path.rglob("*") if path.is_file()
    )
    warnings: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "cpm_fm.gui.mw_config.QMessageBox.warning",
        lambda parent, title, message: warnings.append((title, message)),
    )
    monkeypatch.setattr(
        "cpm_fm.gui.mw_config.QFileDialog.getSaveFileName",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("A group Save must not open Save Config")
        ),
    )
    monkeypatch.setattr("cpm_fm.gui.mw_config.serial.tools.list_ports.comports", lambda: [])

    dialog = _capture_dialog(monkeypatch, win, action_key)
    entry = dialog.entries[setting]
    if hasattr(entry, "setCurrentText"):
        entry.setCurrentText(new_value)
    else:
        entry.setText(new_value)
    _click_save(dialog)

    assert warnings == [(i18n.tr("dialog.warning.title"), i18n.tr("warning.no_config_loaded"))]
    assert win.settings[setting] == new_value
    assert (
        sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*") if path.is_file())
        == files_before
    )


if __name__ == "__main__":  # pragma: no cover - exercised by MT-L07/L08 subprocesses
    import sys

    if len(sys.argv) == 6 and sys.argv[1] == "--config-process-probe":
        _run_config_process_probe(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5])
