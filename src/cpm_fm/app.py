from __future__ import annotations

import os
import sys
import threading
import time
from typing import cast

import serial.tools.list_ports
from PySide6.QtCore import Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStyle,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from cpm_fm.gui.config_dialogs import GeneralConfigDialog, SerialConfigDialog
from cpm_fm.gui.terminal_window import TerminalWindow
from cpm_fm.gui.theme import apply_theme
from cpm_fm.gui.transfer_dialog import TransferProgressDialog
from cpm_fm.gui.window_state import APP, ORG, WindowState
from cpm_fm.terminal.cpm_parser import CPMParser
from cpm_fm.terminal.serial_manager import SerialManager
from cpm_fm.terminal.xmodem import XModem
from cpm_fm.utils.config_handler import ConfigHandler

EOL_MAP = {"CR": "\r", "LF": "\n", "CRLF": "\r\n"}


class MainWindow(QMainWindow):
    """Main application window (SRS docs/cpm_fm_requirements.md).

    All GUI updates originating from background threads (serial reads, file
    transfers, the remote-list capture worker) are delivered to the Qt GUI
    thread exclusively via the signals below, which are connected with the
    implicitly-queued cross-thread default (NFR-001, NFR-004). No widget is
    touched directly from a worker thread.

    Satisfies: STR-002, NFR-004.
    """

    # Cross-thread GUI marshalling signals (NFR-004).
    status_changed = Signal(str)
    term_write = Signal(str)
    remote_files_ready = Signal(dict)
    error_raised = Signal(str, str)
    # Emitted from a transfer worker thread on success so the destination file
    # list is refreshed on the GUI thread ("host" or "remote").
    transfer_completed = Signal(str)
    # FR-105/FR-106: emitted from the transfer worker thread to drive the single
    # modal transfer-progress dialog on the GUI thread (NFR-004). batch_started
    # carries (direction, file_count) and builds the dialog once for the whole
    # batch; transfer_file_started carries (filename, total_bytes, file_index)
    # and switches the dialog to the next file; transfer_progress carries
    # (blocks, bytes_done) and fires once per transferred block.
    batch_started = Signal(str, int)
    transfer_file_started = Signal(str, int, int)
    transfer_progress = Signal(int, int)
    # FR-103: emitted (with the selected drive letter) from the drive-change
    # worker thread when the drive's prompt does not appear, so the "Drive not
    # found" dialog and the list-clear run on the GUI thread (NFR-004).
    drive_not_found = Signal(str)

    def __init__(self, window_state: WindowState | None = None):
        """Satisfies: FR-003, FR-004, FR-005."""
        super().__init__()
        self.setWindowTitle("CP/M File Manager")
        self.resize(900, 560)

        # Core Components
        self.serial_mgr = SerialManager()
        self.config_handler = ConfigHandler()
        # FR-004/FR-005: persisted window geometry and last-used config file.
        # Injectable so tests can isolate the store from the host's real settings.
        self.window_state = window_state if window_state is not None else WindowState()
        self.settings: dict = {}

        # UI State
        self.terminal_win: TerminalWindow | None = None
        # FR-105: the modal transfer-progress dialog, live only for the duration
        # of a transfer. Owned and torn down on the GUI thread.
        self._transfer_dialog: TransferProgressDialog | None = None
        self.host_dir = os.getcwd()
        self._remote_capture_buffer = ""
        self._capture_active = False
        # Cached Local Echo state so worker threads read a plain bool rather
        # than touching the checkbox widget (NFR-004).
        self._local_echo = False

        # FR-090/FR-092: receive and transmit data buffers, retained until
        # explicitly cleared via the Terminal Window Clear button (FR-095).
        self._rx_buffer = ""
        self._tx_buffer = ""

        self.setup_menu()
        self.setup_toolbar()
        self.setup_layout()
        self.setup_status_bar()
        self._connect_signals()

        # FR-090 / FR-074: capture received data regardless of whether the
        # Terminal Window has been opened (the window may not exist yet).
        self.serial_mgr.on_data_received = self.handle_terminal_recv

        self.refresh_host_files()

        # FR-004: restore the main window's saved size/position (overrides the
        # default resize above when a prior session stored geometry).
        self.window_state.restore_geometry("main", self)

        # FR-005: reload and apply the last-used configuration file. If none is
        # remembered, or it no longer exists, the app starts unconfigured
        # (FR-003) and settings come from File > Load or the config dialogs.
        last = self.window_state.last_config
        if last and os.path.exists(last):
            self.load_config(last)

    # ------------------------------------------------------------------ setup

    def _connect_signals(self):
        """Satisfies: NFR-004."""
        self.status_changed.connect(self._on_status_changed)
        self.term_write.connect(self._on_term_write)
        self.remote_files_ready.connect(self._update_remote_list_ui)
        self.error_raised.connect(self._on_error_raised)
        self.transfer_completed.connect(self._on_transfer_completed)
        self.batch_started.connect(self._on_batch_started)
        self.transfer_file_started.connect(self._on_transfer_file_started)
        self.transfer_progress.connect(self._on_transfer_progress)
        self.drive_not_found.connect(self._on_drive_not_found)

    def setup_menu(self):
        """Satisfies: UIR-001, UIR-002, UIR-003."""
        menubar = self.menuBar()

        file_menu = menubar.addMenu("File")
        file_menu.addAction(QAction("Load", self, triggered=self.menu_load))
        file_menu.addAction(QAction("Save", self, triggered=self.menu_save))
        file_menu.addSeparator()
        file_menu.addAction(QAction("Exit", self, triggered=self.close))

        config_menu = menubar.addMenu("Config")
        config_menu.addAction(QAction("Serial", self, triggered=self.menu_serial_config))
        config_menu.addAction(QAction("General", self, triggered=self.menu_general_config))

    def setup_toolbar(self):
        """Satisfies: UIR-013, UIR-071."""
        # UIR-013/UIR-071: the main-window actions are presented as a top toolbar.
        toolbar = QToolBar("Actions")
        toolbar.setToolButtonStyle(toolbar.toolButtonStyle().ToolButtonTextBesideIcon)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        sp = self.style().standardIcon
        Pix = QStyle.StandardPixmap
        actions = [
            ("Connect", Pix.SP_DialogApplyButton, self.do_connect),
            ("Disconnect", Pix.SP_DialogCancelButton, self.do_disconnect),
            ("Terminal", Pix.SP_ComputerIcon, self.show_terminal),
        ]
        for text, pixmap, handler in actions:
            action = QAction(sp(pixmap), text, self, triggered=handler)
            toolbar.addAction(action)

    def setup_layout(self):
        """Satisfies: UIR-011, UIR-012, UIR-017, UIR-072."""
        # UIR-072: Host and Remote panes separated by a user-draggable splitter.
        splitter = QSplitter()

        # Left Side: Host Files
        host_group = QGroupBox("Host Files")
        host_layout = QVBoxLayout(host_group)
        host_layout.addWidget(QPushButton("Change Directory", clicked=self.change_host_dir))
        self.host_list = QListWidget()
        self.host_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        host_layout.addWidget(self.host_list)

        # Host buttons row
        host_btns = QHBoxLayout()
        host_btns.addWidget(QPushButton("Refresh Host", clicked=self.refresh_all))
        host_btns.addWidget(QPushButton("Copy to Remote", clicked=self.do_copy_to_remote))
        host_layout.addLayout(host_btns)

        splitter.addWidget(host_group)

        # Right Side: Remote Files
        remote_group = QGroupBox("Remote Files")
        remote_layout = QVBoxLayout(remote_group)

        # UIR-012/UIR-017: a drive-selection drop-down (A:–P:) followed by the
        # Update button. `activated` fires only on a user selection, never on
        # programmatic changes, so it cannot trigger a drive change spuriously.
        remote_top = QHBoxLayout()
        self.drive_combo = QComboBox()
        self.drive_combo.addItems([f"{chr(c)}:" for c in range(ord("A"), ord("P") + 1)])
        # Widen the drop-down so the selected drive (e.g. "B:") is never clipped.
        self.drive_combo.setMinimumContentsLength(4)
        self.drive_combo.setMinimumWidth(80)
        self.drive_combo.activated.connect(self.change_drive)
        remote_top.addWidget(self.drive_combo)
        remote_top.addWidget(QPushButton("Update", clicked=self.refresh_remote_files))
        remote_top.addStretch()
        remote_layout.addLayout(remote_top)

        self.remote_list = QListWidget()
        self.remote_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        remote_layout.addWidget(self.remote_list)

        # Remote buttons row
        remote_btns = QHBoxLayout()
        remote_btns.addWidget(QPushButton("Copy to Host", clicked=self.do_copy_to_host))
        remote_layout.addLayout(remote_btns)

        splitter.addWidget(remote_group)

        splitter.setSizes([450, 450])
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.addWidget(splitter)
        self.setCentralWidget(container)

    def setup_status_bar(self):
        """Satisfies: UIR-010, UIR-074."""
        # UIR-010/UIR-014: single-line status bar; UIR-074: connection indicators.
        self.term_indicator = self._make_indicator("Terminal")
        self.trans_indicator = self._make_indicator("Transport")
        self.statusBar().addPermanentWidget(self.term_indicator)
        self.statusBar().addPermanentWidget(self.trans_indicator)
        self._update_indicators()
        self.set_status("Ready")

    @staticmethod
    def _make_indicator(name: str):
        """Satisfies: UIR-074."""
        from PySide6.QtWidgets import QLabel

        label = QLabel()
        label.setProperty("indicator_name", name)
        return label

    def _update_indicators(self):
        """Satisfies: UIR-074."""
        # UIR-074: distinct visual state for connected vs not-connected.
        for label, connected in (
            (self.term_indicator, self.serial_mgr.terminal_connected),
            (self.trans_indicator, self.serial_mgr.transport_connected),
        ):
            name = label.property("indicator_name")
            color = "#4caf50" if connected else "#9e9e9e"
            label.setText(f"● {name}")
            label.setStyleSheet(f"color: {color};")

    # ----------------------------------------------------------------- status

    def set_status(self, text: str):
        """Satisfies: UIR-014."""
        # UIR-014: truncate to 127 characters. Emitting (rather than setting
        # directly) makes set_status safe to call from any thread (NFR-004).
        self.status_changed.emit(text[:127])

    def _on_status_changed(self, text: str):
        """Satisfies: UIR-010."""
        self.statusBar().showMessage(text)

    def _on_term_write(self, text: str):
        """Satisfies: FR-086, FR-091, FR-093."""
        # Single GUI-thread sink for all receive-area writes: incoming serial
        # data, local echo (FR-093), and transfer byte echo (FR-086). It never
        # touches the data buffers, so local-echo/hex text stays out of them.
        if self.terminal_win:
            self.terminal_win.write_text(text)

    def _on_error_raised(self, title: str, message: str):
        """Satisfies: FR-105."""
        # FR-105: a failed transfer closes the progress dialog before the error
        # dialog is shown.
        self._close_transfer_dialog()
        QMessageBox.critical(self, title, message)

    def _on_transfer_completed(self, direction: str):
        """Satisfies: FR-099."""
        # Runs on the GUI thread (queued from the transfer worker). After a
        # successful transfer the destination list is otherwise stale until the
        # user manually refreshes it, so refresh the affected pane here.
        # FR-105: close the progress dialog now the transfer has completed.
        self._close_transfer_dialog()
        if direction == "host":
            self.refresh_host_files()
        elif direction == "remote":
            self.refresh_remote_files()

    def _on_batch_started(self, direction: str, file_count: int):
        """Satisfies: FR-105, FR-106."""
        # FR-105/FR-106: runs on the GUI thread (queued from the transfer
        # worker). Build and show the single modal progress dialog that serves
        # the whole batch. transfer_file_started then switches it to each file.
        self._close_transfer_dialog()  # defensive: never leak a prior dialog
        self._transfer_dialog = TransferProgressDialog(self, direction, file_count)
        self._transfer_dialog.show()

    def _on_transfer_file_started(self, filename: str, total_bytes: int, file_index: int):
        """Satisfies: FR-105, FR-107."""
        # FR-105/FR-107: runs on the GUI thread (queued from the transfer
        # worker). Switch the existing batch dialog to the file at 1-based
        # position file_index. total_bytes is the file size for sends, or 0 for
        # receives (length is unknown -> indeterminate).
        if self._transfer_dialog is not None:
            self._transfer_dialog.set_file(filename, total_bytes or None, file_index)

    def _on_transfer_progress(self, blocks: int, bytes_done: int):
        """Satisfies: FR-105."""
        # FR-105: runs on the GUI thread (queued per transferred block).
        if self._transfer_dialog is not None:
            self._transfer_dialog.update_progress(blocks, bytes_done)

    def _close_transfer_dialog(self):
        """Satisfies: FR-105."""
        # FR-105: tear down the progress dialog on the GUI thread, if present.
        if self._transfer_dialog is not None:
            self._transfer_dialog.close()
            self._transfer_dialog.deleteLater()
            self._transfer_dialog = None

    # ------------------------------------------------------------- host files

    def refresh_host_files(self):
        """Satisfies: FR-060."""
        self.host_list.clear()
        try:
            files = [
                f
                for f in os.listdir(self.host_dir)
                if os.path.isfile(os.path.join(self.host_dir, f))
            ]
            self.host_list.addItems(files)
        except Exception as e:
            self.set_status(f"Error reading host files: {e}")

    def change_host_dir(self):
        """Satisfies: FR-062."""
        path = QFileDialog.getExistingDirectory(self, "Change Directory", self.host_dir)
        if path:
            self.host_dir = path
            self.refresh_host_files()

    # -------------------------------------------------------------- terminal

    def show_terminal(self):
        """Satisfies: FR-097."""
        if not self.terminal_win:
            self.terminal_win = TerminalWindow(
                self, self.handle_terminal_send, self.clear_terminal_buffers
            )
            self.terminal_win.chk_echo.toggled.connect(self._set_local_echo)
            # FR-004: restore the Terminal Window's saved geometry on first open.
            self.window_state.restore_geometry("terminal", self.terminal_win)
        else:
            self.terminal_win.showNormal()
        self.terminal_win.show()
        self.terminal_win.raise_()
        self.terminal_win.activateWindow()

    def _set_local_echo(self, enabled: bool):
        """Satisfies: FR-093."""
        self._local_echo = enabled

    def handle_terminal_send(self, text):
        """Satisfies: FR-092, FR-093, FR-094, FR-098."""
        # May be called from the GUI thread (Send button) or a worker thread
        # (the remote-list refresh). Sends data and buffers it directly; the
        # local-echo display is marshalled to the GUI thread via term_write.
        if not self.serial_mgr.terminal_connected:
            self.set_status("Terminal port not open - cannot send")
            return

        eol = self.settings.get("eol", "CR")
        eol_char = EOL_MAP.get(eol, "\r")

        # Prevent double-terminators if already appended (e.g. in _do_refresh_remote_logic)
        if not text.endswith(eol_char):
            text += eol_char

        self.serial_mgr.send_data("terminal", text)
        # FR-092: store transmitted data (with EOL) in the transmit buffer.
        self._tx_buffer += text
        # FR-093: local echo copies transmitted data to the receive area only.
        if self._local_echo:
            self.term_write.emit(f"\n{text}")

    def handle_terminal_recv(self, text):
        """Satisfies: FR-090, FR-091."""
        # Runs on the serial read daemon thread. Buffer bookkeeping happens here
        # (plain strings, not widgets); the display write is marshalled via the
        # term_write signal (NFR-004).
        # FR-090: store all received data in the receive buffer.
        self._rx_buffer += text
        if self._capture_active:
            self._remote_capture_buffer += text
        self.term_write.emit(text)

    def clear_terminal_buffers(self):
        """Satisfies: FR-095."""
        # FR-090/FR-092: the Clear button is the explicit-clear trigger for
        # both the receive and transmit data buffers.
        self._rx_buffer = ""
        self._tx_buffer = ""

    # ----------------------------------------------------------- connect/disc

    def do_connect(self):
        """Satisfies: FR-030, FR-031, FR-032, FR-034, FR-037, FR-038, FR-039, FR-040."""
        if self.serial_mgr.open_port("terminal", self.settings):
            self.set_status("Terminal port open")
            term_port = self.settings.get("terminal_port")
            trans_port = self.settings.get("transport_port")
            if term_port != trans_port:
                if not self.serial_mgr.open_port("transport", self.settings):
                    QMessageBox.critical(self, "Error", "Transport port is unable to be opened")
            else:
                self.serial_mgr.transport_connected = True
        else:
            QMessageBox.critical(self, "Error", "Terminal port is unable to be opened")
        self._update_indicators()

    def do_disconnect(self):
        """Satisfies: FR-050-FR-058."""
        term_port = self.settings.get("terminal_port")
        trans_port = self.settings.get("transport_port")

        # FR-050/FR-051: close the Terminal Port if open; on failure show an
        # error dialog and cancel the current workflow.
        if self.serial_mgr.terminal_connected:
            if not self.serial_mgr.close_terminal_port():
                QMessageBox.critical(self, "Error", "Terminal port is unable to be closed")
                self._update_indicators()
                return
            # FR-052 (flag cleared by close_terminal_port) / FR-053 (status text).
            self.set_status("Terminal port closed")
            # FR-058: the remote listing was read over the now-closed Terminal
            # Port, so it is stale — clear it.
            self.remote_list.clear()

        # FR-054: same physical port — clear the Transport flag, no separate close.
        if trans_port == term_port:
            self.serial_mgr.transport_connected = False
        # FR-055/FR-056/FR-057: different port — close it if open.
        elif self.serial_mgr.transport_connected:
            if not self.serial_mgr.close_transport_port():
                QMessageBox.critical(self, "Error", "Transport port is unable to be closed")
                self._update_indicators()
                return

        self._update_indicators()

    # ----------------------------------------------------------- remote files

    def refresh_all(self):
        """Satisfies: FR-063."""
        # FR-063: the central Refresh button refreshes both lists; the Update
        # button (Remote Files group) refreshes the remote list only (FR-073).
        self.refresh_host_files()
        self.refresh_remote_files()

    def refresh_remote_files(self):
        """Satisfies: FR-073, FR-074."""
        if not self.serial_mgr.terminal_connected:
            self.set_status("Terminal port not open - cannot read file list")
            self.remote_list.clear()
            return
        threading.Thread(target=self._do_refresh_remote_logic, daemon=True).start()

    def _capture_terminal_response(self, command: str) -> str:
        """Satisfies: FR-075, FR-076, FR-101."""
        # Send `command` (with the configured EOL appended) on the Terminal Port
        # and capture the echoed output into the capture buffer until it idles
        # out, returning the captured text. Runs on a worker thread.
        # FR-076: wait at least one second for output to start accumulating,
        # then wait for the receive buffer to time out (no new data within the
        # idle window) before processing, bounded by a safety maximum.
        self._remote_capture_buffer = ""
        self._capture_active = True
        eol_char = EOL_MAP.get(self.settings.get("eol", "CR"), "\r")
        self.handle_terminal_send(command + eol_char)
        time.sleep(1.0)
        idle_window = 0.5
        max_wait = 10.0
        waited = 1.0
        while waited < max_wait:
            prev_len = len(self._remote_capture_buffer)
            time.sleep(idle_window)
            waited += idle_window
            if len(self._remote_capture_buffer) == prev_len:
                break
        self._capture_active = False
        return self._remote_capture_buffer

    def _do_refresh_remote_logic(self):
        """Satisfies: FR-077, FR-078, FR-079."""
        self.set_status("Updating remote file list...")
        cmd = self.settings.get("list_files_cmd", "DIR")
        text = self._capture_terminal_response(cmd)
        files_dict = CPMParser.parse_dir_output(text)
        self.remote_files_ready.emit(files_dict)

    def change_drive(self, index):
        """Satisfies: FR-100, FR-104."""
        # FR-100/FR-104: switch the remote drive to the selected letter. Mirror
        # FR-074 and refuse when the Terminal Port is closed.
        if not self.serial_mgr.terminal_connected:
            self.set_status("Terminal port not open - cannot read file list")
            self.remote_list.clear()
            return
        drive = self.drive_combo.itemText(index)[0]  # 'A'..'P'
        threading.Thread(target=self._do_change_drive_logic, args=(drive,), daemon=True).start()

    def _do_change_drive_logic(self, drive):
        """Satisfies: FR-100, FR-101, FR-102, FR-103."""
        # FR-100/FR-101: send "<letter>:" and capture the response. FR-102: if
        # the new "<letter>>" drive prompt appears, populate the Remote Files
        # list exactly as the Update button would (FR-073). FR-103: otherwise
        # clear the list and report "Drive not found". Runs on a worker thread,
        # so calling _do_refresh_remote_logic directly is correct (it marshals
        # its UI update via the remote_files_ready signal).
        self.set_status(f"Changing to drive {drive}:...")
        text = self._capture_terminal_response(f"{drive}:")
        if CPMParser.has_drive_prompt(text, drive):
            self._do_refresh_remote_logic()
        else:
            self.drive_not_found.emit(drive)

    def _on_drive_not_found(self, drive):
        """Satisfies: FR-103."""
        # FR-103: runs on the GUI thread (queued from the drive-change worker).
        self.remote_list.clear()
        QMessageBox.warning(self, "Drive not found", f"Drive {drive}: not found")

    def _update_remote_list_ui(self, files_dict):
        """Satisfies: FR-078, FR-079."""
        self.remote_list.clear()
        self.remote_list.addItems(sorted(files_dict.keys()))
        self.set_status("Remote file list updated")

    # -------------------------------------------------------------- transfers

    def _selected_filenames(self, list_widget) -> list[str]:
        """Satisfies: FR-106, FR-107."""
        # FR-106/FR-107: every selected file, in list display order (top to
        # bottom). selectedItems() does not guarantee display order, so iterate
        # the rows and keep those that are selected.
        return [
            list_widget.item(row).text()
            for row in range(list_widget.count())
            if list_widget.item(row).isSelected()
        ]

    def do_copy_to_remote(self):
        """Satisfies: FR-080, FR-084, FR-106, CR-010."""
        # FR-080: a transfer is permitted only when both the Terminal and
        # Transport status flags are true.
        if not (self.serial_mgr.terminal_connected and self.serial_mgr.transport_connected):
            QMessageBox.critical(self, "Error", "Transport port not connected")
            return

        # FR-106: transfer every selected file; warn when none is selected.
        filenames = self._selected_filenames(self.host_list)
        if not filenames:
            QMessageBox.warning(self, "Warning", "Please select one or more files to upload")
            return

        filepaths = [os.path.join(self.host_dir, name) for name in filenames]
        threading.Thread(
            target=self._transfer_to_remote_batch, args=(filepaths,), daemon=True
        ).start()

    def _on_transfer_bytes(self, direction, data):
        """Satisfies: FR-086, FR-088."""
        # FR-086: echo transfer bytes to the Terminal Window as hex tokens of
        # the form <HH>. Runs on the transfer worker thread; the display write
        # is marshalled to the GUI thread via term_write (NFR-004). The slot
        # no-ops when the Terminal Window does not exist.
        # Direction-tagged, timestamped trace to stdout (visible via
        # `python -m cpm_fm`) so transfers can be debugged without conflating
        # sent and received bytes, and so prompt/response timing is visible.
        # Gated by the debug_logging setting (FR-088).
        if self._debug_enabled():
            print(f"[xfer {direction} {time.time():.2f}] {data.hex(' ')}", flush=True)
        hex_text = "".join(f"<{b:02X}>" for b in data)
        self.term_write.emit(hex_text)

    def _on_transfer_progress_cb(self, blocks, bytes_done, total):
        """Satisfies: FR-105."""
        # FR-105: XModem progress hook. Runs on the transfer worker thread; the
        # dialog update is marshalled to the GUI thread via transfer_progress
        # (NFR-004). total is unused here (the dialog captured it at start).
        self.transfer_progress.emit(blocks, bytes_done)

    def _issue_remote_cmd(self, cmd_key: str, default: str, filename: str) -> None:
        """Satisfies: FR-087."""
        # Implements recv_remote_cmd / send_remote_cmd (UIR-045/UIR-046): the
        # configured command is sent on the Terminal Port to launch the CP/M
        # side of the transfer (PCPUT/PCGET), with "$1" replaced by the
        # filename. Runs on the transfer worker thread; handle_terminal_send is
        # safe to call from there (it marshals its display write via a signal).
        template = self.settings.get(cmd_key, default)
        if not template:
            return
        self.handle_terminal_send(template.replace("$1", filename))

    def _launch_delay(self) -> float:
        """Satisfies: FR-089."""
        # Seconds to wait after launching the CP/M side (PCPUT/PCGET) before
        # starting the X-Modem handshake. This must exceed the remote program's
        # start-up time: while it prints its banner and opens the file it is not
        # reading its UART, and any start-character prompts we send during that
        # window pile up and overrun its (FIFO-less) UART. Tunable via the
        # `xfer_launch_delay` setting; default 3s.
        try:
            return max(0.0, float(self.settings.get("xfer_launch_delay", 3.0)))
        except (TypeError, ValueError):
            return 3.0

    def _interfile_delay(self) -> float:
        """Satisfies: FR-109."""
        # FR-109: extra settle time after the terminal output goes idle between
        # files in a batch, before the next launch command is sent. Tunable via
        # the `xfer_interfile_delay` setting (UIR-052); default 2s.
        try:
            return max(0.0, float(self.settings.get("xfer_interfile_delay", 2.0)))
        except (TypeError, ValueError):
            return 2.0

    def _wait_for_terminal_idle(self) -> None:
        """Satisfies: FR-109."""
        # FR-109: between files in a batch, wait for the previous CP/M transfer
        # program to finish and the CCP command prompt to return before issuing
        # the next launch command. Without this, the prior PCPUT/PCGET is still
        # closing its file and returning to the CCP — and therefore not yet
        # servicing its (FIFO-less) UART — so the leading characters of the next
        # command are lost (e.g. "PCPUT X" arriving as "CPUT X"). Mirrors the
        # idle-detection of _capture_terminal_response: an initial wait for the
        # completion text to start, then wait for the receive buffer to stop
        # growing, bounded by a safety maximum, then a final settle. Runs on the
        # transfer worker thread; it only reads the plain `_rx_buffer` string.
        idle_window = 0.5
        max_wait = 8.0
        time.sleep(1.0)
        waited = 1.0
        while waited < max_wait:
            prev_len = len(self._rx_buffer)
            time.sleep(idle_window)
            waited += idle_window
            if len(self._rx_buffer) == prev_len:
                break
        time.sleep(self._interfile_delay())

    def _debug_enabled(self) -> bool:
        """Satisfies: FR-088."""
        # FR-088: verbose transfer debug output is emitted to stdout only when
        # the `debug_logging` setting holds an affirmative value (default off).
        return str(self.settings.get("debug_logging", "OFF")).strip().upper() in (
            "ON",
            "TRUE",
            "1",
            "YES",
        )

    def _debug(self, msg: str) -> None:
        """Satisfies: FR-088."""
        if self._debug_enabled():
            print(msg, flush=True)

    def _transfer_to_remote_batch(self, filepaths):
        """Satisfies: FR-099, FR-105, FR-106, FR-107, FR-108, FR-109."""
        # FR-106/FR-107: transfer each selected file sequentially over the
        # single Transport Port. Runs on a worker thread. FR-105: one progress
        # dialog serves the whole batch. FR-108: abort on the first failure.
        count = len(filepaths)
        self.batch_started.emit("remote", count)
        succeeded = 0
        for index, filepath in enumerate(filepaths, start=1):
            name = os.path.basename(filepath)
            # FR-109: let CP/M return to its prompt before the next command.
            if index > 1:
                self._wait_for_terminal_idle()
            self.set_status(f"Uploading {name} ({index}/{count})...")
            try:
                total_bytes = os.path.getsize(filepath)
            except OSError:
                total_bytes = 0
            self.transfer_file_started.emit(name, total_bytes, index)
            try:
                ok = self._send_one_to_remote(filepath)
            except Exception as e:
                self._debug(f"[copy-to-remote] EXCEPTION: {e!r}")
                if succeeded:
                    self.transfer_completed.emit("remote")
                self.error_raised.emit("Error", str(e))
                return
            if not ok:
                # FR-108: abort the batch and refresh if anything got through.
                if succeeded:
                    self.transfer_completed.emit("remote")
                self.error_raised.emit(
                    "X-Modem Error", f"Transfer of {name} failed; remaining files skipped"
                )
                return
            succeeded += 1
        self.set_status(f"Successfully uploaded {succeeded} file(s)")
        # FR-099: refresh the Remote Files list so the uploaded files show.
        self.transfer_completed.emit("remote")

    def _send_one_to_remote(self, filepath) -> bool:
        """Satisfies: FR-081, FR-082, FR-083, FR-087."""
        # Launch the CP/M receiver (PCGET) and send one file over X-Modem.
        # Returns True on success. Runs on the batch worker thread; it does not
        # touch the progress dialog or refresh (the batch driver owns those).
        ser = self.serial_mgr.transport_port
        delay = self._launch_delay()
        self._debug(
            f"[copy-to-remote] start file={os.path.basename(filepath)} "
            f"cmd={self.settings.get('send_remote_cmd', 'PCGET $1')!r} "
            f"launch_delay={delay}s transport={ser}"
        )
        # Clear stale bytes, then launch the CP/M receiver (PCGET) on the
        # Terminal Port so its start character lands on a clean transport
        # buffer that send_file does not flush.
        if ser:
            ser.reset_input_buffer()
        self._issue_remote_cmd("send_remote_cmd", "PCGET $1", os.path.basename(filepath))
        self._debug(f"[copy-to-remote] launched PCGET; waiting {delay}s before handshake")
        time.sleep(delay)
        self._debug("[copy-to-remote] starting X-Modem send")
        xm = XModem(
            ser,
            monitor=self._on_transfer_bytes,
            progress=self._on_transfer_progress_cb,
        )
        return xm.send_file(filepath)

    def do_copy_to_host(self):
        """Satisfies: FR-080, FR-085, FR-106, CR-010."""
        # FR-080: a transfer is permitted only when both the Terminal and
        # Transport status flags are true.
        if not (self.serial_mgr.terminal_connected and self.serial_mgr.transport_connected):
            QMessageBox.critical(self, "Error", "Transport port not connected")
            return

        # FR-106: transfer every selected file; warn when none is selected.
        filenames = self._selected_filenames(self.remote_list)
        if not filenames:
            QMessageBox.warning(self, "Warning", "Please select one or more files to download")
            return

        save_paths = [os.path.join(self.host_dir, name) for name in filenames]
        threading.Thread(
            target=self._transfer_to_host_batch, args=(save_paths,), daemon=True
        ).start()

    def _transfer_to_host_batch(self, save_paths):
        """Satisfies: FR-099, FR-105, FR-106, FR-107, FR-108, FR-109."""
        # FR-106/FR-107: receive each selected file sequentially over the single
        # Transport Port. Runs on a worker thread. FR-105: one progress dialog
        # serves the whole batch. FR-108: abort on the first failure.
        count = len(save_paths)
        self.batch_started.emit("host", count)
        succeeded = 0
        for index, save_path in enumerate(save_paths, start=1):
            name = os.path.basename(save_path)
            # FR-109: let CP/M return to its prompt before the next command.
            if index > 1:
                self._wait_for_terminal_idle()
            self.set_status(f"Downloading {name} ({index}/{count})...")
            # The X-Modem stream carries no length, so total_bytes is 0
            # (indeterminate progress bar).
            self.transfer_file_started.emit(name, 0, index)
            try:
                ok = self._recv_one_to_host(save_path)
            except Exception as e:
                self._debug(f"[copy-to-host] EXCEPTION: {e!r}")
                if succeeded:
                    self.transfer_completed.emit("host")
                self.error_raised.emit("Error", str(e))
                return
            if not ok:
                # FR-108: abort the batch and refresh if anything got through.
                if succeeded:
                    self.transfer_completed.emit("host")
                self.error_raised.emit(
                    "X-Modem Error", f"Transfer of {name} failed; remaining files skipped"
                )
                return
            succeeded += 1
        self.set_status(f"Successfully downloaded {succeeded} file(s)")
        # FR-099: refresh the Host Files list so the downloaded files show.
        self.transfer_completed.emit("host")

    def _recv_one_to_host(self, save_path) -> bool:
        """Satisfies: FR-081, FR-082, FR-083, FR-087."""
        # Launch the CP/M sender (PCPUT) and receive one file over X-Modem.
        # Returns True on success. Runs on the batch worker thread; it does not
        # touch the progress dialog or refresh (the batch driver owns those).
        ser = self.serial_mgr.transport_port
        delay = self._launch_delay()
        self._debug(
            f"[copy-to-host] start file={os.path.basename(save_path)} "
            f"cmd={self.settings.get('recv_remote_cmd', 'PCPUT $1')!r} "
            f"launch_delay={delay}s transport={ser}"
        )
        # Launch the CP/M sender (PCPUT) on the Terminal Port, then receive.
        # receive_file drives the handshake (polls with 'C'), so it tolerates
        # PCPUT taking several seconds to arm.
        self._issue_remote_cmd("recv_remote_cmd", "PCPUT $1", os.path.basename(save_path))
        self._debug(f"[copy-to-host] launched PCPUT; waiting {delay}s before handshake")
        time.sleep(delay)
        self._debug("[copy-to-host] starting X-Modem receive")
        xm = XModem(
            ser,
            monitor=self._on_transfer_bytes,
            progress=self._on_transfer_progress_cb,
        )
        return xm.receive_file(save_path)

    # ------------------------------------------------------------------ config

    def load_config(self, filename):
        """Satisfies: FR-005, FR-011, FR-012, FR-017, FR-060."""
        self.settings = self.config_handler.load_json(filename)
        # FR-005: remember this file so it is reloaded on the next startup.
        self.window_state.last_config = filename

        # Restore host directory if specified in config
        host_dir = self.settings.get("host_directory")
        if host_dir:
            self.host_dir = host_dir
            self.refresh_host_files()

        # FR-017: the prior remote listing was captured under the previous
        # configuration and is no longer valid — clear it.
        self.remote_list.clear()
        self.set_status(f"Loaded config: {filename}")

    def menu_load(self):
        """Satisfies: FR-010."""
        path, _ = QFileDialog.getOpenFileName(self, "Load Config", "", "JSON files (*.json)")
        if path:
            self.load_config(path)

    def menu_save(self):
        """Satisfies: FR-005, FR-013, FR-014."""
        path, _ = QFileDialog.getSaveFileName(self, "Save Config", "", "JSON files (*.json)")
        if path:
            if not path.endswith(".json"):
                path += ".json"

            # Persist the current host directory in the settings before saving
            self.settings["host_directory"] = self.host_dir

            if self.config_handler.save_json(path, self.settings):
                # FR-005: the saved file becomes the last-used config to reload.
                self.window_state.last_config = path
                self.set_status(f"Saved config to {path}")

    def menu_serial_config(self):
        """Satisfies: FR-020, IFR-003."""
        # IFR-003 / UIR-022 / UIR-023: enumerate the host's serial ports.
        ports = [p.device for p in serial.tools.list_ports.comports()]

        def update_settings(new_set):
            self.settings.update(new_set)
            self.set_status("Serial settings updated")

        SerialConfigDialog(self, self.settings, ports, update_settings, self.window_state)

    def menu_general_config(self):
        """Satisfies: FR-021."""

        def update_settings(new_set):
            self.settings.update(new_set)

            # If the default host directory was changed, apply it immediately
            if "host_directory" in new_set:
                path = new_set["host_directory"]
                if path:
                    self.host_dir = path
                    self.refresh_host_files()

            self.set_status("General settings updated")

        GeneralConfigDialog(self, self.settings, update_settings, self.window_state)

    # ------------------------------------------------------------------- exit

    def closeEvent(self, event):
        """Satisfies: FR-004, FR-015, FR-016."""
        # FR-004: persist window geometry on exit. The Terminal Window persists
        # in the background when the user closes it (it hides rather than
        # destroys), so it still exists here and its current geometry is saved.
        self.window_state.save_geometry("main", self)
        if self.terminal_win:
            self.window_state.save_geometry("terminal", self.terminal_win)
        # FR-015: close any open COM ports. FR-016: close all open windows.
        self.serial_mgr.close_ports()
        if self.terminal_win:
            self.terminal_win.close()
        event.accept()


def main() -> None:
    """Satisfies: STR-002, CR-002, CR-013."""
    app = cast(QApplication, QApplication.instance() or QApplication(sys.argv))
    # FR-004/FR-005: identity for QSettings-backed persistence (see WindowState).
    app.setOrganizationName(ORG)
    app.setApplicationName(APP)
    apply_theme(app)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
