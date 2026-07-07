import json
import os
from typing import Any

# Default (flat-format) configuration applied by File > New (FR-019). This is
# the single source of truth for the hard-coded defaults that are otherwise
# duplicated across the config dialogs (config_dialogs.py) and the various
# settings.get(key, default) call sites in app.py.
DEFAULT_SETTINGS: dict[str, Any] = {
    "terminal_port": "COM1",
    "transport_port": "COM1",
    "speed": "115200",
    "data": "8",
    "parity": "NONE",
    "stopbits": "1",
    "flow": "NONE",
    # UIR-034: terminal emulation type the Terminal Window interprets received
    # bytes as (VT100 / VT52 / ADM-3A). Drives FR-157/FR-157i/FR-157j rendering
    # and FR-158a/FR-158b cursor-key encoding. Default VT100 (current behaviour).
    "terminal_type": "VT100",
    # UIR-103/FR-093: Local Echo — copy transmitted data to the Terminal Window
    # Receive view. Persisted per-configuration; default OFF. Configured on the
    # Terminal Config dialog's Terminal tab (UIR-103a).
    "local_echo": "OFF",
    # UIR-104/UIR-062: Autoscroll — keep the newest output visible in the Receive
    # view. Persisted per-configuration; default ON. Configured on the Terminal
    # Config dialog's Terminal tab (UIR-103a).
    "autoscroll": "ON",
    "msec_char": "0",
    "msec_line": "0",
    # Per-port serial read timeouts, in milliseconds. Applied as the pyserial
    # read timeout for each port. The transport timeout in particular bounds how
    # long each X-Modem read waits, so it must be long enough for a frame to
    # accumulate at the configured baud rate. Default 100 ms.
    "terminal_timeout_ms": "100",
    "transport_timeout_ms": "100",
    "list_files_cmd": "DIR",
    "recv_remote_cmd": "PCPUT $1",
    "send_remote_cmd": "PCGET $1",
    # XMODEM-1K mode. When `xmodem_1k` is ON, host->remote sends use 1024-byte
    # STX frames instead of 128-byte SOH (the receive side already auto-detects
    # frame size), and the `_1k` launch commands below replace the standard
    # send/recv commands. A blank `_1k` command falls back to its standard
    # counterpart (the 1K framing still applies).
    "xmodem_1k": "OFF",
    "recv_remote_cmd_1k": "",
    "send_remote_cmd_1k": "",
    "xfer_launch_delay": "3",
    "xfer_interfile_delay": "2",
    "eol": "CR",
    "debug_logging": "OFF",
    # FR-086: echo X-Modem transfer bytes to the Terminal Window as <HH> hex
    # tokens. Off by default; set ON to enable the echo.
    "echo_transfer_data": "OFF",
    # FR-112/FR-117: file context-menu action commands. viewer_cmd opens a file
    # in a viewer/editor ($1 = path); rename_remote_cmd / delete_remote_cmd are
    # the CP/M-side commands for remote Rename/Delete ($1 = original name,
    # $2 = new name for rename).
    "viewer_cmd": "notepad $1",
    "rename_remote_cmd": "REN $2=$1",
    "delete_remote_cmd": "ERA $1",
    "host_directory": "",
    # FR-047/UIR-059: optional boot-into-CP/M keystroke sequence. A newline-
    # separated script (SEND/SENDRAW/WAIT/WAITFOR directives) run to drive a
    # remote that does not boot straight into CP/M. Empty disables the feature.
    "boot_sequence": "",
    # FR-162/FR-021b/UIR-097/UIR-098: up to ten configurable macro buttons shown
    # in the floating Macro Window. Each slot pairs a display label
    # (macro_<n>_label) with a keystroke script (macro_<n>_seq) in the same
    # directive language as boot_sequence (SEND/SENDRAW/WAIT/WAITFOR). A slot is
    # shown as a button only when both are non-empty; all default empty. These
    # persist per-configuration alongside the other settings.
    **{f"macro_{i}_label": "" for i in range(1, 11)},
    **{f"macro_{i}_seq": "" for i in range(1, 11)},
}


class ConfigHandler:
    """
    Handles loading and saving of configuration files for the CP/M File Manager.
    Supports both the flat (dialog-written) and the nested (`{"serial": ..., "general": ...}`)
    settings formats.

    Satisfies: IFR-004.
    """

    @staticmethod
    def load_json(filepath: str) -> dict[str, Any]:
        """
        Loads a JSON file and returns its content as a dictionary.

        Satisfies: FR-011, FR-012, IFR-004.
        """
        if not os.path.exists(filepath):
            return {}
        try:
            with open(filepath) as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print(f"Error loading config file {filepath}: {e}")
            return {}

    @staticmethod
    def save_json(filepath: str, data: dict[str, Any]) -> bool:
        """
        Saves a dictionary to a JSON file.

        Satisfies: FR-014, IFR-004.
        """
        try:
            with open(filepath, "w") as f:
                json.dump(data, f, indent=4)
            return True
        except OSError as e:
            print(f"Error saving config file {filepath}: {e}")
            return False
