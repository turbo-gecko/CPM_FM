from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from cpm_fm.gui.dialog_buttons import build_button_row
from cpm_fm.utils.i18n import tr

if TYPE_CHECKING:
    from cpm_fm.gui.window_state import WindowState


class ConfigDialog(QDialog):
    """Base class for the modal Configuration Dialogs.

    Builds a two-column form (UIR-021) from a declarative field list. Each
    field is a dict with keys: ``key``, ``label_key`` (an i18n key resolved via
    :func:`tr` at build time — FR-121), ``type`` ("dropdown", "text",
    "directory" or "checkbox"), ``default``, and optionally ``options`` (dropdown),
    ``maxlength`` (text), ``int_range`` (text, an inclusive ``(lo, hi)`` tuple)
    and ``group`` (an i18n key for a titled :class:`QGroupBox` the field is
    placed in). Fields that share a ``group`` value are gathered into one boxed,
    two-column sub-form; fields with no ``group`` render in a plain form. Groups
    and the ungrouped form appear in order of first appearance in the field
    list, so reordering the list reorders the dialog (UIR-041). Option *values*
    and stored keys are technical/semantic and are not translated (CR-015) —
    only the row label and group title are.

    Satisfies: UIR-021, UIR-041, FR-121.
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
        Satisfies: UIR-021, UIR-041, UIR-053, UIR-075.

        Fields are laid out into sections keyed by their optional ``group``: a
        grouped field goes into a titled :class:`QGroupBox`, an ungrouped field
        into a plain form. Sections are emitted in the order their first field
        appears in the list, so the field order alone controls dialog layout.
        """
        layout = QVBoxLayout(self)
        self.entries: dict[str, Any] = {}

        # Map each group key (or None for ungrouped) to its form, recording the
        # order sections are first seen so the layout follows the field list.
        forms: dict[Any, QFormLayout] = {}
        section_order: list[Any] = []
        for field in self.fields:
            group = field.get("group")
            if group not in forms:
                forms[group] = QFormLayout()
                section_order.append(group)
            label, widget = self._build_field(field)
            forms[group].addRow(label, widget)

        for group in section_order:
            if group is None:
                layout.addLayout(forms[group])
            else:
                box = QGroupBox(tr(group))
                box.setLayout(forms[group])
                layout.addWidget(box)

        # UIR-075: Cancel at the far left, the affirmative (Save) button at the
        # far right.
        save_btn = QPushButton(tr("button.save"))
        save_btn.setDefault(True)
        save_btn.clicked.connect(self.save)
        cancel_btn = QPushButton(tr("button.cancel"))
        cancel_btn.clicked.connect(self.reject)
        layout.addLayout(build_button_row(accept_button=save_btn, reject_button=cancel_btn))

    def _build_field(self, field) -> tuple[str, QWidget]:
        """Build the widget for one field and register it in ``self.entries``.

        Returns the resolved row label (translated — FR-121) and the widget to
        place in the form. For a "directory" field the returned widget is the
        path+browse container, while the value-bearing line edit is what gets
        registered in ``self.entries`` for save-time retrieval (UIR-053).

        Satisfies: UIR-021, UIR-053.
        """
        key = field["key"]
        current = str(self.settings.get(key, field["default"]))
        widget: QWidget

        if field["type"] == "dropdown":
            combo = QComboBox()
            combo.addItems([str(o) for o in field["options"]])
            combo.setCurrentText(current)
            self.entries[key] = combo
            widget = combo
        elif field["type"] == "checkbox":
            # Boolean toggle persisted as the string "ON"/"OFF" (consistent with
            # the dropdown-backed OFF/ON settings), so the flat config format and
            # settings.get(...) call sites stay uniform.
            check = QCheckBox()
            check.setChecked(current.upper() == "ON")
            self.entries[key] = check
            widget = check
        elif field["type"] == "directory":
            # Create a horizontal layout for the path and the browse button
            dir_container = QWidget()
            dir_layout = QHBoxLayout(dir_container)
            dir_layout.setContentsMargins(0, 0, 0, 0)
            dir_layout.setSpacing(5)

            line_edit = QLineEdit(current)
            btn_browse = QPushButton("...")
            btn_browse.setFixedWidth(40)

            # `line_edit` is bound as a default argument so each browse handler
            # captures its own field's widget; `checked` absorbs the bool the
            # clicked signal passes.
            def on_browse(checked=False, line_edit=line_edit):
                """
                Satisfies: UIR-053.
                """
                path = QFileDialog.getExistingDirectory(
                    self, tr("dialog.select_directory.title"), line_edit.text()
                )
                if path:
                    line_edit.setText(path)

            btn_browse.clicked.connect(on_browse)
            dir_layout.addWidget(line_edit)
            dir_layout.addWidget(btn_browse)

            widget = dir_container
            # The entry for value retrieval is the line edit, not the container.
            self.entries[key] = line_edit
        else:
            widget = QLineEdit(current)
            if "maxlength" in field:
                widget.setMaxLength(field["maxlength"])
            if "int_range" in field:
                lo, hi = field["int_range"]
                widget.setValidator(QIntValidator(lo, hi, widget))
            self.entries[key] = widget

        return tr(field["label_key"]), widget

    def _value(self, widget) -> str:
        if isinstance(widget, QComboBox):
            return widget.currentText()
        if isinstance(widget, QCheckBox):
            return "ON" if widget.isChecked() else "OFF"
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
                "label_key": "config.serial.terminal_port",
                "type": "dropdown",
                "options": current_ports,
                "default": "COM1",
            },
            {
                "key": "transport_port",
                "label_key": "config.serial.transfer_port",
                "type": "dropdown",
                "options": current_ports,
                "default": "COM1",
            },
            {
                "key": "speed",
                "label_key": "config.serial.speed",
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
                "label_key": "config.serial.data_bits",
                "type": "dropdown",
                "options": ["7", "8"],
                "default": "8",
            },
            {
                "key": "parity",
                "label_key": "config.serial.parity",
                "type": "dropdown",
                "options": ["NONE", "ODD", "EVEN", "MARK", "SPACE"],
                "default": "NONE",
            },
            {
                "key": "stopbits",
                "label_key": "config.serial.stop_bits",
                "type": "dropdown",
                "options": ["1", "2"],
                "default": "1",
            },
            {
                "key": "flow",
                "label_key": "config.serial.flow_control",
                "type": "dropdown",
                "options": ["NONE", "XON/XOFF", "RTS/CTS", "DSR/DTR"],
                "default": "NONE",
            },
            # UIR-030/UIR-031: integer 0..255 inclusive.
            {
                "key": "msec_char",
                "label_key": "config.serial.msec_char",
                "type": "text",
                "default": "0",
                "int_range": (0, 255),
            },
            {
                "key": "msec_line",
                "label_key": "config.serial.msec_line",
                "type": "text",
                "default": "0",
                "int_range": (0, 255),
            },
            # UIR-032/UIR-033: per-port serial read timeouts in milliseconds.
            # The pyserial read timeout for each port; the transport value bounds
            # how long each X-Modem read waits for frame bytes. Default 100 ms.
            {
                "key": "terminal_timeout_ms",
                "label_key": "config.serial.terminal_timeout",
                "type": "text",
                "default": "100",
                "int_range": (10, 5000),
            },
            {
                "key": "transport_timeout_ms",
                "label_key": "config.serial.transport_timeout",
                "type": "text",
                "default": "100",
                "int_range": (10, 5000),
            },
        ]
        super().__init__(
            parent,
            tr("config.serial.title"),
            settings,
            fields,
            callback,
            window_state,
            "serial_config",
        )


class GeneralConfigDialog(ConfigDialog):
    """
    Specialized dialog for General Configuration
    (SRS docs/cpm_fm_requirements.md, UIR-040 through UIR-048).

    Satisfies: UIR-040-UIR-058.
    """

    def __init__(self, parent, settings, callback, window_state=None):
        """
        Satisfies: UIR-041, UIR-042, UIR-045, UIR-046, UIR-047, UIR-048,
        UIR-049, UIR-050, UIR-052, UIR-053, UIR-054, UIR-055, UIR-056,
        UIR-058.

        Command text fields limited to 79 characters. UIR-041: the remote
        command fields (List Files, Receive from Remote, Send to Remote, Rename,
        Delete) are gathered into a "Remote" group placed first; the remaining
        general settings follow ungrouped.
        """
        # UIR-041: i18n key for the "Remote" group box title. The five remote
        # command fields below carry this so the base dialog boxes them together
        # and, being first in the list, renders the group before everything else.
        REMOTE = "config.general.remote_group"
        fields = [
            {
                "key": "list_files_cmd",
                "label_key": "config.general.list_files",
                "type": "text",
                "default": "DIR",
                "maxlength": 79,
                "group": REMOTE,
            },
            {
                "key": "recv_remote_cmd",
                "label_key": "config.general.recv_remote",
                "type": "text",
                "default": "PCPUT $1",
                "maxlength": 79,
                "group": REMOTE,
            },
            {
                "key": "send_remote_cmd",
                "label_key": "config.general.send_remote",
                "type": "text",
                "default": "PCGET $1",
                "maxlength": 79,
                "group": REMOTE,
            },
            # XMODEM-1K mode: when checked, host->remote sends use 1024-byte STX
            # frames and the _1k commands below replace the standard send/recv
            # launch commands (a blank _1k field falls back to its standard
            # counterpart). Default unchecked.
            {
                "key": "xmodem_1k",
                "label_key": "config.general.xmodem_1k",
                "type": "checkbox",
                "default": "OFF",
                "group": REMOTE,
            },
            {
                "key": "recv_remote_cmd_1k",
                "label_key": "config.general.recv_remote_1k",
                "type": "text",
                "default": "",
                "maxlength": 79,
                "group": REMOTE,
            },
            {
                "key": "send_remote_cmd_1k",
                "label_key": "config.general.send_remote_1k",
                "type": "text",
                "default": "",
                "maxlength": 79,
                "group": REMOTE,
            },
            # UIR-055: remote rename command (FR-117); $1 = original name,
            # $2 = new name (CP/M REN newname=oldname). Labelled just "Rename"
            # inside the Remote group.
            {
                "key": "rename_remote_cmd",
                "label_key": "config.general.rename_remote",
                "type": "text",
                "default": "REN $2=$1",
                "maxlength": 79,
                "group": REMOTE,
            },
            # UIR-056: remote delete command (FR-117); $1 = filename. Labelled
            # just "Delete" inside the Remote group.
            {
                "key": "delete_remote_cmd",
                "label_key": "config.general.delete_remote",
                "type": "text",
                "default": "ERA $1",
                "maxlength": 79,
                "group": REMOTE,
            },
            # UIR-049: seconds to wait after launching PCPUT/PCGET before the
            # X-Modem handshake starts, so prompts do not overrun the remote
            # UART during its start-up (FR-087). Integer 0..60 inclusive.
            {
                "key": "xfer_launch_delay",
                "label_key": "config.general.xfer_launch_delay",
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
                "label_key": "config.general.xfer_interfile_delay",
                "type": "text",
                "default": "2",
                "int_range": (0, 60),
            },
            {
                "key": "eol",
                "label_key": "config.general.eol",
                "type": "dropdown",
                "options": ["CR", "LF", "CRLF"],
                "default": "CR",
            },
            # UIR-050: gate verbose transfer debug output to stdout (FR-088).
            {
                "key": "debug_logging",
                "label_key": "config.general.debug_logging",
                "type": "dropdown",
                "options": ["OFF", "ON"],
                "default": "OFF",
            },
            # UIR-058: gate the X-Modem transfer byte echo to the Terminal
            # Window (FR-086). Default OFF.
            {
                "key": "echo_transfer_data",
                "label_key": "config.general.echo_transfer",
                "type": "dropdown",
                "options": ["OFF", "ON"],
                "default": "OFF",
            },
            # UIR-054: command used to open a file for viewing/editing (FR-112);
            # $1 is the file path.
            {
                "key": "viewer_cmd",
                "label_key": "config.general.viewer",
                "type": "text",
                "default": "notepad $1",
            },
            {
                "key": "host_directory",
                "label_key": "config.general.host_directory",
                "type": "directory",
                "default": "",
            },
        ]
        super().__init__(
            parent,
            tr("config.general.title"),
            settings,
            fields,
            callback,
            window_state,
            "general_config",
        )
