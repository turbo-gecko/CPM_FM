from __future__ import annotations

import time
from functools import partial
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QTimer
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
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from cpm_fm.gui.dialog_buttons import build_button_row
from cpm_fm.terminal.xmodem import XModem
from cpm_fm.utils.i18n import tr

if TYPE_CHECKING:
    from cpm_fm.gui.window_state import WindowState


class ConfigDialog(QDialog):
    """Base class for the modal Configuration Dialogs.

    Builds a two-column form (UIR-021) from a declarative field list. Each
    field is a dict with keys: ``key``, ``label_key`` (an i18n key resolved via
    :func:`tr` at build time — FR-121), ``type`` ("dropdown", "text",
    "directory", "checkbox", "multiline" or "button"), ``default``, and
    optionally ``options`` (dropdown), ``maxlength`` (text), ``int_range``
    (text, an inclusive ``(lo, hi)`` tuple) and ``group`` (an i18n key for a
    titled :class:`QGroupBox` the field is placed in). A "button" field
    (FR-161) carries no settings value — it uses ``button_key`` (an i18n key
    for the button text) and ``on_click`` (the name of a method on the
    subclass) instead of ``label_key``/``default``, and is never added to
    ``self.entries``, so it is invisible to ``save()``. Fields that share a
    ``group`` value are gathered into one boxed, two-column sub-form; fields
    with no ``group`` render in a plain form. Groups and the ungrouped form
    appear in order of first appearance in the field list, so reordering the
    list reorders the dialog (UIR-041). Option *values* and stored keys are
    technical/semantic and are not translated (CR-015) — only the row label
    and group title are.

    Satisfies: UIR-021, UIR-041, FR-121, FR-161, CR-015.
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
        Satisfies: UIR-021, UIR-041, UIR-053, UIR-075, UIR-117.

        Fields are laid out into sections keyed by their optional ``group``: a
        grouped field goes into a titled :class:`QGroupBox`, an ungrouped field
        into a plain form. Sections are emitted in the order their first field
        appears in the list, so the field order alone controls dialog layout.
        UIR-117: the field sections are placed inside a vertically scrollable
        area so tall dialogs stay fully reachable; the Save/Cancel row (UIR-075)
        sits below it, fixed and outside the scrolled area.
        """
        layout = QVBoxLayout(self)
        self.entries: dict[str, Any] = {}

        # UIR-117: the field sections live in a scrollable content widget.
        content = QWidget()
        content_layout = QVBoxLayout(content)

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
                content_layout.addLayout(forms[group])
            else:
                box = QGroupBox(tr(group))
                box.setLayout(forms[group])
                content_layout.addWidget(box)

        # UIR-117: a vertical scrollbar appears on demand; the content resizes
        # to the viewport width so the two-column form keeps its proportions.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        layout.addWidget(scroll)

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
        registered in ``self.entries`` for save-time retrieval (UIR-053). A
        "button" field (UIR-094/UIR-095) is a bare action trigger — it carries
        no settings value, so it is never added to ``self.entries`` and is
        skipped entirely by ``save()``.

        Satisfies: UIR-021, UIR-053, FR-161.
        """
        key = field["key"]
        current = str(self.settings.get(key, field.get("default", "")))
        widget: QWidget

        if field["type"] == "button":
            # FR-161: a standalone action button (e.g. "Test"), not a
            # settings-bearing field. ``on_click`` names a method on this
            # dialog, resolved here so field definitions stay plain data.
            button = QPushButton(tr(field["button_key"]))
            button.clicked.connect(getattr(self, field["on_click"]))
            return "", button
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
        elif field["type"] == "multiline":
            # UIR-059: a multi-line free-text editor (e.g. the boot-sequence
            # script). Persisted verbatim, newlines included.
            editor = QPlainTextEdit()
            editor.setPlainText(current)
            self.entries[key] = editor
            widget = editor
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
        if isinstance(widget, QPlainTextEdit):
            return widget.toPlainText()
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

    Satisfies: UIR-020-UIR-033, IFR-002.
    """

    def __init__(self, parent, settings, current_ports, callback, window_state=None):
        """
        Satisfies: UIR-022-UIR-033.

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
                # UIR-028: default RTS/CTS since v2.36.1 (was NONE).
                "default": "RTS/CTS",
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


class RemoteConfigDialog(ConfigDialog):
    """Specialized dialog for the Remote Configuration settings.

    Holds the remote-command fields (List Files, Receive/Send from Remote and
    their Test buttons, the XMODEM-1K options, Rename, Delete, Erase All), the
    transfer-timing fields (Xfer Launch Delay, Handshake Timeout, Inter-file
    Delay) and the Boot Sequence editor. All fields are presented **ungrouped**
    in a two-column layout (UIR-116) — the dialog carries no group boxes. Split
    out of the former General Configuration Dialog in v2.36.

    Satisfies: UIR-116, UIR-117, UIR-042, UIR-045, UIR-046, UIR-049, UIR-052,
    UIR-055, UIR-056, UIR-059, UIR-089, UIR-090, UIR-093, UIR-094, UIR-095,
    UIR-107, FR-161, FR-021d.
    """

    def __init__(self, parent, settings, callback, window_state=None):
        """
        Satisfies: UIR-116, UIR-042, UIR-045, UIR-046, UIR-049, UIR-052,
        UIR-055, UIR-056, UIR-059, UIR-089, UIR-090, UIR-093, UIR-094, UIR-095,
        UIR-107.

        Command text fields limited to 79 characters. UIR-116: every field is
        ungrouped (no ``group`` key), so the base dialog renders a single flat
        two-column form in field-list order.
        """
        # FR-161: the Test buttons need the MainWindow's serial_mgr/settings.
        # ``parent`` already *is* the MainWindow at every call site; stored
        # under its own name (rather than read back via self.parent()) so the
        # test handlers below don't depend on Qt's widget-parent bookkeeping.
        # Must be set before super().__init__() — it calls exec() internally,
        # and a button field's on_click is resolved during create_widgets().
        self._main_window = parent
        self._test_timer: QTimer | None = None
        self._test_ser = None
        self._test_shared = False
        self._test_no_response_key = ""
        self._test_deadline = 0.0

        fields = [
            {
                "key": "list_files_cmd",
                "label_key": "config.remote.list_files",
                "type": "text",
                "default": "DIR",
                "maxlength": 79,
            },
            {
                "key": "recv_remote_cmd",
                "label_key": "config.remote.recv_remote",
                "type": "text",
                "default": "PCPUT $1",
                "maxlength": 79,
            },
            # UIR-094: pre-flight test for the Receive from Remote command
            # (FR-161) — not a persisted setting, so it carries no "default"
            # value and is never added to self.entries.
            {
                "key": "_test_recv_remote_cmd",
                "type": "button",
                "button_key": "button.test",
                "on_click": "_test_recv_remote_cmd",
            },
            {
                "key": "send_remote_cmd",
                "label_key": "config.remote.send_remote",
                "type": "text",
                "default": "PCGET $1",
                "maxlength": 79,
            },
            # UIR-095: pre-flight test for the Send to Remote command (FR-161).
            {
                "key": "_test_send_remote_cmd",
                "type": "button",
                "button_key": "button.test",
                "on_click": "_test_send_remote_cmd",
            },
            # XMODEM-1K mode: when checked, host->remote sends use 1024-byte STX
            # frames and the _1k commands below replace the standard send/recv
            # launch commands (a blank _1k field falls back to its standard
            # counterpart). Default unchecked.
            {
                "key": "xmodem_1k",
                "label_key": "config.remote.xmodem_1k",
                "type": "checkbox",
                "default": "OFF",
            },
            {
                "key": "recv_remote_cmd_1k",
                "label_key": "config.remote.recv_remote_1k",
                "type": "text",
                "default": "",
                "maxlength": 79,
            },
            {
                "key": "send_remote_cmd_1k",
                "label_key": "config.remote.send_remote_1k",
                "type": "text",
                "default": "",
                "maxlength": 79,
            },
            # UIR-055: remote rename command (FR-117); $1 = original name,
            # $2 = new name (CP/M REN newname=oldname).
            {
                "key": "rename_remote_cmd",
                "label_key": "config.remote.rename_remote",
                "type": "text",
                "default": "REN $2=$1",
                "maxlength": 79,
            },
            # UIR-056: remote delete command (FR-117); $1 = filename.
            {
                "key": "delete_remote_cmd",
                "label_key": "config.remote.delete_remote",
                "type": "text",
                "default": "ERA $1",
                "maxlength": 79,
            },
            # UIR-107: optional whole-drive erase macro sequence (FR-153e), run
            # once during Restore to clear the remote drive. Multi-line, in the
            # boot-sequence directive language; empty falls back to the per-file
            # ERA loop (FR-153c).
            {
                "key": "erase_all_remote_seq",
                "label_key": "config.remote.erase_all",
                "type": "multiline",
                "default": "",
            },
            # UIR-049: seconds to wait after launching PCPUT/PCGET before the
            # X-Modem handshake starts, so prompts do not overrun the remote
            # UART during its start-up (FR-087). Integer 0..60 inclusive.
            {
                "key": "xfer_launch_delay",
                "label_key": "config.remote.xfer_launch_delay",
                "type": "text",
                "default": "3",
                "int_range": (0, 60),
            },
            # UIR-093: seconds to wait for the remote's first X-Modem response
            # byte before treating the transfer as a misconfigured launch
            # command (FR-159/FR-160). Integer 1..60 inclusive.
            {
                "key": "xfer_handshake_timeout",
                "label_key": "config.remote.xfer_handshake_timeout",
                "type": "text",
                "default": "10",
                "int_range": (1, 60),
            },
            # UIR-052: seconds to settle, after the terminal output goes idle,
            # between files in a multi-file batch before the next launch command
            # is sent, so its leading characters are not lost while CP/M is
            # returning to the prompt (FR-109). Integer 0..60 inclusive.
            {
                "key": "xfer_interfile_delay",
                "label_key": "config.remote.xfer_interfile_delay",
                "type": "text",
                "default": "2",
                "int_range": (0, 60),
            },
            # UIR-059: optional multi-line boot-into-CP/M keystroke sequence
            # (FR-047). Placed last so the tall editor sits at the bottom of the
            # layout. Empty by default — feature disabled.
            {
                "key": "boot_sequence",
                "label_key": "config.remote.boot_sequence",
                "type": "multiline",
                "default": "",
            },
        ]
        super().__init__(
            parent,
            tr("config.remote.title"),
            settings,
            fields,
            callback,
            window_state,
            "remote_config",
        )

    def _test_recv_remote_cmd(self):
        """
        Satisfies: FR-161, UIR-094.

        Pre-flight test for the Receive from Remote field.
        """
        self._start_command_test(
            "recv_remote_cmd", "PCPUT $1", "dialog.test_remote_cmd.no_response_recv"
        )

    def _test_send_remote_cmd(self):
        """
        Satisfies: FR-161, UIR-095.

        Pre-flight test for the Send to Remote field.
        """
        self._start_command_test(
            "send_remote_cmd", "PCGET $1", "dialog.test_remote_cmd.no_response_send"
        )

    def _start_command_test(self, cmd_key: str, default: str, no_response_key: str) -> None:
        """
        Satisfies: FR-161.

        Launches the CP/M side of the command exactly as a real transfer
        would (FR-087), using the field's *currently typed* value (which need
        not yet be saved), then waits up to the handshake timeout (FR-160)
        for any response byte — without ever performing a real transfer.
        Requires an active connection (FR-080/CR-010). Runs entirely on the
        GUI thread via a bounded QTimer poll rather than a worker thread plus
        signal, since the wait is short, cancellable by construction, and this
        avoids the cross-instance signal-connection bookkeeping a repeatedly
        created/destroyed dialog would otherwise need.
        """
        win = self._main_window
        if not (win.serial_mgr.terminal_connected and win.serial_mgr.transport_connected):
            QMessageBox.critical(
                self, tr("dialog.error.title"), tr("error.transport_not_connected")
            )
            return
        if self._test_timer is not None:
            return  # a test is already running
        template = self.entries[cmd_key].text() or default
        if not template.strip():
            return

        ser = win.serial_mgr.transport_port
        self._test_ser = ser
        # FR-037: when the Transport and Terminal Ports are the same physical
        # port, suspend the terminal read loop so it does not steal the
        # response byte this test is waiting for.
        self._test_shared = ser is not None and ser is win.serial_mgr.terminal_port
        self._test_no_response_key = no_response_key
        self._set_test_buttons_enabled(False)
        if self._test_shared:
            win.serial_mgr.pause_terminal_reads()
        if ser:
            ser.reset_input_buffer()
        win.handle_terminal_send(template.replace("$1", "CPMTEST.TXT"))
        QTimer.singleShot(int(win._launch_delay() * 1000), self._test_begin_listen)

    def _test_begin_listen(self) -> None:
        """
        Satisfies: FR-160, FR-161.

        Starts polling for the remote's first response byte once the launch
        delay (FR-089) has elapsed, bounded by the configured handshake
        timeout (FR-160).
        """
        win = self._main_window
        self._test_deadline = time.monotonic() + win._handshake_timeout()
        self._test_timer = QTimer(self)
        self._test_timer.timeout.connect(self._test_poll)
        self._test_timer.start(50)

    def _test_poll(self) -> None:
        """
        Satisfies: FR-161.
        """
        if self._test_ser is not None and self._test_ser.in_waiting > 0:
            self._finish_command_test(True)
            return
        if time.monotonic() >= self._test_deadline:
            self._finish_command_test(False)

    def _finish_command_test(self, got_response: bool) -> None:
        """
        Satisfies: FR-159, FR-161.

        Reports the outcome and cancels (X-Modem CAN, via the same bounded
        abort used by a real transfer) whatever the launched command may
        have started, so it is not left waiting for a real transfer that
        will never come.
        """
        if self._test_timer is not None:
            self._test_timer.stop()
            self._test_timer = None
        if self._test_ser is not None:
            XModem(self._test_ser)._abort()
        if self._test_shared:
            self._main_window.serial_mgr.resume_terminal_reads()
        self._set_test_buttons_enabled(True)
        if got_response:
            QMessageBox.information(
                self, tr("dialog.test_remote_cmd.title"), tr("dialog.test_remote_cmd.success")
            )
        else:
            QMessageBox.warning(
                self, tr("dialog.test_remote_cmd.title"), tr(self._test_no_response_key)
            )

    def _set_test_buttons_enabled(self, enabled: bool) -> None:
        """
        Satisfies: FR-161.

        Disables every button in the dialog (Save, Cancel, both Test buttons,
        the host-directory Browse button) while a test is in flight, so the
        dialog cannot be closed out from under it and a second test cannot
        overlap the first.
        """
        for widget in self.findChildren(QPushButton):
            widget.setEnabled(enabled)


class GeneralConfigDialog(ConfigDialog):
    """Specialized dialog for General Configuration.

    After v2.36 the General dialog holds only the general settings that are not
    remote/transfer- or terminal-specific: Debug Logging, Viewer/Editor, the
    Default Host Directory and the Default Image Directory. The former Remote
    group and the transfer-timing/Boot Sequence fields moved to the Remote
    Configuration Dialog (UIR-116); End of Line and Echo Transfer Data moved to
    the Terminal Config dialog (UIR-103a). All fields are ungrouped (UIR-041).

    Satisfies: UIR-040, UIR-041, UIR-044, UIR-050, UIR-053, UIR-054, UIR-115,
    UIR-117, FR-021, FR-021a.
    """

    def __init__(self, parent, settings, callback, window_state=None):
        """
        Satisfies: UIR-041, UIR-044, UIR-050, UIR-053, UIR-054, UIR-115.

        The fields are ungrouped (no ``group`` key), so the base dialog renders
        a single flat two-column form in field-list order.
        """
        fields = [
            # UIR-050: gate verbose transfer debug output to stdout (FR-088).
            {
                "key": "debug_logging",
                "label_key": "config.general.debug_logging",
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
            # FR-179/UIR-115: the default folder for CP/M disk-image files, browsed
            # by Open/New/Save Image and remembered on Config > Save Config.
            {
                "key": "image_directory",
                "label_key": "config.general.image_directory",
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


class TerminalConfigDialog(ConfigDialog):
    """Configuration dialog for the Terminal Window settings and macro buttons.

    A tabbed dialog (UIR-103) with two tabs:

    * **Terminal** (UIR-103a) — a two-column form holding the Terminal Type
      dropdown (UIR-034), the Local Echo checkbox (UIR-103b/FR-093), and the
      Autoscroll checkbox (UIR-103c/UIR-062).
    * **Macros** (UIR-103d/UIR-098) — ten "Macro <n>" slots as a nested tabbed
      layout, each with a Label field, a multi-line Keystrokes editor (the
      button's boot-sequence-style script, FR-047/FR-162), and a Test button
      that runs the slot's currently entered script on the Terminal Port.

    It reuses :class:`ConfigDialog`'s ``save``/``done``/geometry handling and
    :meth:`ConfigDialog._build_field` for the Terminal-tab fields, but replaces
    the single declarative form with a :class:`QTabWidget`. On Save the inherited
    :meth:`ConfigDialog.save` writes every registered entry — the three terminal
    settings and all twenty ``macro_<n>_*`` keys — back to the settings.

    Satisfies: UIR-103, UIR-103a, UIR-098, UIR-034, UIR-047, UIR-048, UIR-058,
    UIR-117, FR-093, FR-021b, FR-162.
    """

    MACRO_COUNT = 10

    def __init__(self, parent, settings, callback, window_state=None):
        """
        Satisfies: UIR-103, UIR-103a, UIR-034, UIR-047, UIR-048, UIR-058, FR-021b.

        ``parent`` is the MainWindow, stored under ``_main_window`` so the Test
        handlers can reach its serial manager and macro runner (mirrors
        :class:`RemoteConfigDialog`). The Terminal-tab field list is passed to
        the base as ``fields`` so :meth:`ConfigDialog._build_field` can build
        those rows; the macro tabs are built directly in :meth:`create_widgets`.
        Must be set before ``super().__init__``, which builds the widgets and
        enters the modal ``exec()``.
        """
        self._main_window = parent
        # UIR-103a: the Terminal-tab settings, built via the base field
        # machinery so their save/round-trip is shared with the other dialogs.
        terminal_fields = [
            # UIR-034: terminal emulation type applied to the Terminal Window.
            {
                "key": "terminal_type",
                "label_key": "config.terminal.terminal_type",
                "type": "dropdown",
                "options": ["VT100", "VT52", "ADM-3A"],
                "default": "VT100",
            },
            # UIR-103b/FR-093: copy transmitted data to the Receive view.
            {
                "key": "local_echo",
                "label_key": "config.terminal.local_echo",
                "type": "checkbox",
                "default": "OFF",
            },
            # UIR-103c/UIR-062: keep the newest output visible in the Receive view.
            {
                "key": "autoscroll",
                "label_key": "config.terminal.autoscroll",
                "type": "checkbox",
                "default": "ON",
            },
            # UIR-047/UIR-048: end-of-line convention applied to typed/sent lines.
            # Moved from the General Config dialog in v2.36.
            {
                "key": "eol",
                "label_key": "config.terminal.eol",
                "type": "dropdown",
                "options": ["CR", "LF", "CRLF"],
                "default": "CR",
            },
            # UIR-058: gate the X-Modem transfer byte echo to the Terminal
            # Window (FR-086). Default OFF. Moved from the General Config dialog
            # in v2.36.
            {
                "key": "echo_transfer_data",
                "label_key": "config.terminal.echo_transfer",
                "type": "dropdown",
                "options": ["OFF", "ON"],
                "default": "OFF",
            },
        ]
        super().__init__(
            parent,
            tr("config.terminal.title"),
            settings,
            terminal_fields,
            callback,
            window_state,
            "terminal_config",
        )

    def create_widgets(self):
        """Build the Terminal-settings tab and the nested macro-button tabs.

        The **Terminal** tab lays ``self.fields`` (Terminal Type, Local Echo,
        Autoscroll, End of Line, Echo Transfer Data) into a two-column form via
        :meth:`ConfigDialog._build_field`, inside a vertical scroll area
        (UIR-117). The **Macros** tab holds a nested :class:`QTabWidget` of ten
        slots, each a Label field, a Keystrokes editor, and a Test button; the
        Label/Keystrokes widgets are registered in ``self.entries`` under the
        ``macro_<n>_label``/``macro_<n>_seq`` keys so the inherited
        :meth:`ConfigDialog.save` writes all of them (with the terminal settings)
        straight back to the settings.

        Satisfies: UIR-103, UIR-103a, UIR-098, UIR-075, UIR-117, FR-021b.
        """
        outer = QVBoxLayout(self)
        self.entries: dict[str, Any] = {}

        tabs = QTabWidget()

        # UIR-103a: the Terminal-settings tab (Terminal Type / Local Echo /
        # Autoscroll / End of Line / Echo Transfer Data) as a two-column form.
        # UIR-117: the form sits inside a vertical scroll area so every field
        # stays reachable when the tab is shorter than its contents.
        term_page = QWidget()
        term_form = QFormLayout(term_page)
        for field in self.fields:
            label, widget = self._build_field(field)
            term_form.addRow(label, widget)
        term_scroll = QScrollArea()
        term_scroll.setWidgetResizable(True)
        term_scroll.setWidget(term_page)
        tabs.addTab(term_scroll, tr("config.terminal.tab.terminal"))

        # UIR-103d/UIR-098: the Macros tab — a nested tab per macro slot.
        macro_page = QWidget()
        macro_layout = QVBoxLayout(macro_page)
        macro_tabs = QTabWidget()
        for i in range(1, self.MACRO_COUNT + 1):
            page = QWidget()
            form = QFormLayout(page)

            label_edit = QLineEdit(str(self.settings.get(f"macro_{i}_label", "")))
            label_edit.setMaxLength(30)
            self.entries[f"macro_{i}_label"] = label_edit
            form.addRow(tr("config.macros.label"), label_edit)

            seq_edit = QPlainTextEdit(str(self.settings.get(f"macro_{i}_seq", "")))
            self.entries[f"macro_{i}_seq"] = seq_edit
            form.addRow(tr("config.macros.sequence"), seq_edit)

            test_btn = QPushButton(tr("button.test"))
            test_btn.clicked.connect(partial(self._run_test, i))
            form.addRow("", test_btn)

            # UIR-098: one tab per macro slot, labelled "Macro <n>".
            macro_tabs.addTab(page, tr("config.macros.macro", n=i))
        macro_layout.addWidget(macro_tabs)
        tabs.addTab(macro_page, tr("config.terminal.tab.macros"))

        outer.addWidget(tabs)

        # A sensible default size for the tabbed editor when no geometry is
        # saved yet (restore_geometry, run after this, overrides it if present).
        self.resize(460, 380)

        # UIR-075: Cancel far left, Save far right.
        save_btn = QPushButton(tr("button.save"))
        save_btn.setDefault(True)
        save_btn.clicked.connect(self.save)
        cancel_btn = QPushButton(tr("button.cancel"))
        cancel_btn.clicked.connect(self.reject)
        outer.addLayout(build_button_row(accept_button=save_btn, reject_button=cancel_btn))

    def _run_test(self, index: int) -> None:
        """Send macro slot ``index``'s currently entered script to the terminal.

        Runs the (possibly unsaved) script on the Terminal Port via the owner's
        macro runner (FR-162). Permitted only when the Terminal Port is open;
        otherwise the standard not-connected error is shown and nothing is sent.
        An empty script is a no-op.

        Satisfies: UIR-098, FR-162.
        """
        win = self._main_window
        if not win.serial_mgr.terminal_connected:
            QMessageBox.critical(self, tr("dialog.error.title"), tr("error.terminal_not_connected"))
            return
        script = self.entries[f"macro_{index}_seq"].toPlainText()
        if not script.strip():
            return
        win.run_macro_script(script)
