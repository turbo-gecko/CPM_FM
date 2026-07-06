"""Unit tests for ConfigHandler JSON load/save (FR-011, FR-012, FR-014, IFR-004).

The config layer had no direct coverage: only DEFAULT_SETTINGS was imported
elsewhere. These pin the documented degrade-to-empty / degrade-to-False error
behaviour and the load<->save round trip, so a regression in either path is
caught rather than silently swallowed (both methods only print on failure).
"""

import json

from cpm_fm.utils.config_handler import DEFAULT_SETTINGS, ConfigHandler


def test_load_json_reads_valid_object(tmp_path):
    """Verifies: FR-011, IFR-004."""
    # FR-011/IFR-004: a well-formed JSON object loads as the matching dict.
    path = tmp_path / "cfg.json"
    path.write_text('{"terminal_port": "COM3", "speed": "9600"}', encoding="utf-8")
    assert ConfigHandler.load_json(str(path)) == {"terminal_port": "COM3", "speed": "9600"}


def test_load_json_missing_file_returns_empty(tmp_path):
    """Verifies: FR-012."""
    # FR-012: a path that does not exist degrades to {} (never raises).
    assert ConfigHandler.load_json(str(tmp_path / "nope.json")) == {}


def test_load_json_malformed_returns_empty(tmp_path):
    """Verifies: FR-012, IFR-004."""
    # FR-012/IFR-004: invalid JSON degrades to {} rather than raising.
    path = tmp_path / "bad.json"
    path.write_text("{ this is : not valid json", encoding="utf-8")
    assert ConfigHandler.load_json(str(path)) == {}


def test_save_json_writes_loadable_file(tmp_path):
    """Verifies: FR-014."""
    # FR-014: a saved file is valid JSON containing exactly the saved mapping.
    path = tmp_path / "out.json"
    data = {"terminal_port": "COM7", "flow": "RTS/CTS", "msec_char": "0"}
    assert ConfigHandler.save_json(str(path), data) is True
    assert json.loads(path.read_text(encoding="utf-8")) == data


def test_save_then_load_round_trips(tmp_path):
    """Verifies: FR-011, FR-014."""
    # FR-011/FR-014: load(save(x)) == x for a representative settings dict.
    path = tmp_path / "round.json"
    data = {"speed": "115200", "data": "8", "parity": "EVEN", "eol": "CRLF"}
    assert ConfigHandler.save_json(str(path), data) is True
    assert ConfigHandler.load_json(str(path)) == data


def test_default_settings_include_xmodem_1k_keys():
    """Verifies: UIR-089, UIR-090."""
    # UIR-089/UIR-090: XMODEM-1K mode is off by default with blank 1K commands.
    assert DEFAULT_SETTINGS["xmodem_1k"] == "OFF"
    assert DEFAULT_SETTINGS["recv_remote_cmd_1k"] == ""
    assert DEFAULT_SETTINGS["send_remote_cmd_1k"] == ""


def test_default_settings_terminal_type_is_vt100():
    """Verifies: UIR-034."""
    # UIR-034: the terminal emulation type defaults to VT100 (current behaviour).
    assert DEFAULT_SETTINGS["terminal_type"] == "VT100"


def test_save_json_to_unwritable_path_returns_false(tmp_path):
    """Verifies: FR-014, IFR-004."""
    # FR-014/IFR-004: an OSError on write (here, a parent directory that does not
    # exist) degrades to False rather than raising.
    path = tmp_path / "no_such_dir" / "out.json"
    assert ConfigHandler.save_json(str(path), {"a": 1}) is False
    assert not path.exists()
