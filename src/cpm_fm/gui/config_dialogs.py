from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from cpm_fm.gui.dialog_buttons import build_button_row

if TYPE_CHECKING:
    from cpm_fm.gui.window_state import WindowState


class ConfigDialog(QDialog):
    """Base class for the modal Configuration Dialogs.

    Builds a two-column form (UIR-021) from a declarative field list. Each
    field is a dict with keys: ``key``, ``label``, ``type`` ("dropdown" or
    "text"), ``default``, and optionally ``options`` (dropdown), ``maxlength``
    (text) and ``int_range`` (text, an inclusive ``(lo, hi)`` tuple).

    Satisfies: UIR-021.
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
        """
        Satisfies: FR-004, UIR-020, UIR-040.
        """
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
        """
        Satisfies: FR-004.

        Save geometry on every close path (Save, Cancel, window close,
        which all funnel through done()) before the modal exec() returns.
        """
        if self._window_state is not None and self._state_key is not None:
            self._window_state.save_geometry(self._state_key, self)
        super().done(result)

    def create_widgets(self):
        """
        Satisfies: UIR-021, UIR-053, UIR-075.
        """
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
            elif field["type"] == "directory":
                # Create a horizontal layout for the path and the browse button
                dir_container = QWidget()
                dir_layout = QHBoxLayout(dir_container)
                dir_layout.setContentsMargins(0, 0, 0, 0)
                dir_layout.setSpacing(5)

                line_edit = QLineEdit(current)
                btn_browse = QPushButton("...")
                btn_browse.setFixedWidth(40)

                # `line_edit` is bound as a default argument so each browse
                # handler captures its own field's widget (the loop rebinds
                # `line_edit` every iteration); `checked` absorbs the bool the
                # clicked signal passes.
                def on_browse(checked=False, line_edit=line_edit):
                    """
                    Satisfies: UIR-053.
                    """
                    path = QFileDialog.getExistingDirectory(
                        self, "Select Directory", line_edit.text()
                    )
                    if path:
                        line_edit.setText(path)

                btn_browse.clicked.connect(on_browse)
                dir_layout.addWidget(line_edit)
                dir_layout.addWidget(btn_browse)

                widget = dir_container
                # We must be able to retrieve the value from the laout
                # Overriding _value to handle the context
                self.entries[key] = line_edit
            else:
                widget = QLineEdit(current)
                if "maxlength" in field:
                    widget.setMaxLength(field["maxlength"])
                if "int_range" in field:
                    lo, hi = field["int_range"]
                    widget.setValidator(QIntValidator(lo, hi, widget))

            if field["type"] != "directory":
                self.entries[key] = widget
                form.addRow(field["label"], widget)
            else:
                # For directory type, widget is the container
                form.addRow(field["label"], dir_container)
                # The entry for value retrieval is the line edit
                self.entries[key] = line_edit

        layout.addLayout(form)

        # UIR-075: Cancel at the far left, the affirmative (Save) button at the
        # far right.
        save_btn = QPushButton("Save")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self.save)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        layout.addLayout(build_button_row(accept_button=save_btn, reject_button=cancel_btn))

    def _value(self, widget) -> str:
        if isinstance(widget, QComboBox):
            return widget.currentText()
        return widget.text()

    def save(self):
        """
        Satisfies: FR-020, FR-021.
        """
        new_settings = {key: self._value(w) for key, w in self.entries.items()}
        self.result_settings = new_settings
        self.callback(new_settings)
        self.accept()


class SerialConfigDialog(ConfigDialog):
    """
    Specialized dialog for Serial Configuration
    (SRS docs/cpm_fm_requirements.md, UIR-020 through UIR-031).

    Satisfies: UIR-020-UIR-031, IFR-002.
    """

    def __init__(self, parent, settings, current_ports, callback, window_state=None):
        """
        Satisfies: UIR-022-UIR-031.

        Define fields based on Requirements.
        """
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

    Satisfies: UIR-040-UIR-057.
    """

    def __init__(self, parent, settings, callback, window_state=None):
        """
        Satisfies: UIR-042, UIR-045, UIR-046, UIR-047, UIR-048, UIR-049,
        UIR-050, UIR-052, UIR-053, UIR-054, UIR-055, UIR-056.

        Command text fields limited to 79 characters.
        """
        fields = [
            {
                "key": "list_files_cmd",
                "label": "List Files",
                "type": "text",
                "default": "DIR",
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
            # UIR-052: seconds to settle, after the terminal output goes idle,
            # between files in a multi-file batch before the next launch command
            # is sent, so its leading characters are not lost while CP/M is
            # returning to the prompt (FR-109). Integer 0..60 inclusive.
            {
                "key": "xfer_interfile_delay",
                "label": "Xfer Inter-file Delay (s)",
                "type": "text",
                "default": "2",
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
            # UIR-054: command used to open a file for viewing/editing (FR-112);
            # $1 is the file path.
            {
                "key": "viewer_cmd",
                "label": "Viewer/Editor",
                "type": "text",
                "default": "notepad $1",
            },
            # UIR-055: remote rename command (FR-117); $1 = original name,
            # $2 = new name (CP/M REN newname=oldname).
            {
                "key": "rename_remote_cmd",
                "label": "Rename Remote",
                "type": "text",
                "default": "REN $2=$1",
                "maxlength": 79,
            },
            # UIR-056: remote delete command (FR-117); $1 = filename.
            {
                "key": "delete_remote_cmd",
                "label": "Delete Remote",
                "type": "text",
                "default": "ERA $1",
                "maxlength": 79,
            },
            {
                "key": "host_directory",
                "label": "Default Host Directory",
                "type": "directory",
                "default": "",
            },
        ]
        super().__init__(
            parent, "General Config", settings, fields, callback, window_state, "general_config"
        )
