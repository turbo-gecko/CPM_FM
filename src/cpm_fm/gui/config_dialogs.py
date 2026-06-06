from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QVBoxLayout,
)

if TYPE_CHECKING:
    from cpm_fm.gui.window_state import WindowState


class ConfigDialog(QDialog):
    """Base class for the modal Configuration Dialogs.

    Builds a two-column form (UIR-021) from a declarative field list. Each
    field is a dict with keys: ``key``, ``label``, ``type`` ("dropdown" or
    "text"), ``default``, and optionally ``options`` (dropdown), ``maxlength``
    (text) and ``int_range`` (text, an inclusive ``(lo, hi)`` tuple).
    """

    def __init__(
        self,
        parent,
        title: str,
        settings: dict[str, Any],
        fields: list,
        callback,
        window_state: WindowState | None = None,
        state_key: str | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.settings = settings
        self.fields = fields
        self.callback = callback
        self.result_settings: dict[str, Any] | None = None
        # FR-004: optional geometry persistence for this dialog.
        self._window_state = window_state
        self._state_key = state_key

        self.create_widgets()
        if window_state is not None and state_key is not None:
            window_state.restore_geometry(state_key, self)
        # UIR-020/UIR-040: modal dialog.
        self.exec()

    def done(self, result: int) -> None:
        # FR-004: save geometry on every close path (Save, Cancel, window close,
        # which all funnel through done()) before the modal exec() returns.
        if self._window_state is not None and self._state_key is not None:
            self._window_state.save_geometry(self._state_key, self)
        super().done(result)

    def create_widgets(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.entries: dict[str, Any] = {}

        for field in self.fields:
            key = field["key"]
            current = str(self.settings.get(key, field["default"]))

            if field["type"] == "dropdown":
                widget = QComboBox()
                widget.addItems([str(o) for o in field["options"]])
                widget.setCurrentText(current)
            else:
                widget = QLineEdit(current)
                if "maxlength" in field:
                    widget.setMaxLength(field["maxlength"])
                if "int_range" in field:
                    lo, hi = field["int_range"]
                    widget.setValidator(QIntValidator(lo, hi, widget))

            self.entries[key] = widget
            form.addRow(field["label"], widget)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _value(self, widget) -> str:
        if isinstance(widget, QComboBox):
            return widget.currentText()
        return widget.text()

    def save(self):
        new_settings = {key: self._value(w) for key, w in self.entries.items()}
        self.result_settings = new_settings
        self.callback(new_settings)
        self.accept()


class SerialConfigDialog(ConfigDialog):
    """
    Specialized dialog for Serial Configuration
    (SRS docs/cpm_fm_requirements.md, UIR-020 through UIR-031).
    """

    def __init__(self, parent, settings, current_ports, callback, window_state=None):
        # Define fields based on Requirements
        fields = [
            {
                "key": "terminal_port",
                "label": "Terminal Port",
                "type": "dropdown",
                "options": current_ports,
                "default": "COM1",
            },
            {
                "key": "transport_port",
                "label": "Transfer Port",
                "type": "dropdown",
                "options": current_ports,
                "default": "COM1",
            },
            {
                "key": "speed",
                "label": "Speed",
                "type": "dropdown",
                "options": [
                    "300",
                    "1200",
                    "2400",
                    "4800",
                    "9600",
                    "14400",
                    "19200",
                    "38400",
                    "57600",
                    "115200",
                    "230400",
                    "460800",
                    "921600",
                ],
                "default": "115200",
            },
            {
                "key": "data",
                "label": "Data Bits",
                "type": "dropdown",
                "options": ["7", "8"],
                "default": "8",
            },
            {
                "key": "parity",
                "label": "Parity",
                "type": "dropdown",
                "options": ["NONE", "ODD", "EVEN", "MARK", "SPACE"],
                "default": "NONE",
            },
            {
                "key": "stopbits",
                "label": "Stop Bits",
                "type": "dropdown",
                "options": ["1", "2"],
                "default": "1",
            },
            {
                "key": "flow",
                "label": "Flow Control",
                "type": "dropdown",
                "options": ["NONE", "XON/XOFF", "RTS/CTS", "DSR/DTR"],
                "default": "NONE",
            },
            # UIR-030/UIR-031: integer 0..255 inclusive.
            {
                "key": "msec_char",
                "label": "msec/char",
                "type": "text",
                "default": "0",
                "int_range": (0, 255),
            },
            {
                "key": "msec_line",
                "label": "msec/line",
                "type": "text",
                "default": "0",
                "int_range": (0, 255),
            },
        ]
        super().__init__(
            parent, "Serial Config", settings, fields, callback, window_state, "serial_config"
        )


class GeneralConfigDialog(ConfigDialog):
    """
    Specialized dialog for General Configuration
    (SRS docs/cpm_fm_requirements.md, UIR-040 through UIR-048).
    """

    def __init__(self, parent, settings, callback, window_state=None):
        # UIR-042..046: command text fields limited to 79 characters.
        fields = [
            {
                "key": "list_files_cmd",
                "label": "List Files",
                "type": "text",
                "default": "DIR",
                "maxlength": 79,
            },
            {
                "key": "change_disk_cmd",
                "label": "Change Disk",
                "type": "text",
                "default": "",
                "maxlength": 79,
            },
            {
                "key": "recv_remote_cmd",
                "label": "Receive from Remote",
                "type": "text",
                "default": "PCPUT $1",
                "maxlength": 79,
            },
            {
                "key": "send_remote_cmd",
                "label": "Send to Remote",
                "type": "text",
                "default": "PCGET $1",
                "maxlength": 79,
            },
            # UIR-049: seconds to wait after launching PCPUT/PCGET before the
            # X-Modem handshake starts, so prompts do not overrun the remote
            # UART during its start-up (FR-087). Integer 0..60 inclusive.
            {
                "key": "xfer_launch_delay",
                "label": "Xfer Launch Delay (s)",
                "type": "text",
                "default": "3",
                "int_range": (0, 60),
            },
            {
                "key": "eol",
                "label": "End of Line",
                "type": "dropdown",
                "options": ["CR", "LF", "CRLF"],
                "default": "CR",
            },
            # UIR-050: gate verbose transfer debug output to stdout (FR-088).
            {
                "key": "debug_logging",
                "label": "Debug Logging",
                "type": "dropdown",
                "options": ["OFF", "ON"],
                "default": "OFF",
            },
        ]
        super().__init__(
            parent, "General Config", settings, fields, callback, window_state, "general_config"
        )
