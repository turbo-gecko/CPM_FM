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
    QFileDialog,
    QGroupBox,
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
    """

    # Cross-thread GUI marshalling signals (NFR-004).
    status_changed = Signal(str)
    term_write = Signal(str)
    remote_files_ready = Signal(dict)
    error_raised = Signal(str, str)
    # Emitted from a transfer worker thread on success so the destination file
    # list is refreshed on the GUI thread ("host" or "remote").
    transfer_completed = Signal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("CP/M File Manager")
        self.resize(900, 560)

        # Core Components
        self.serial_mgr = SerialManager()
        self.config_handler = ConfigHandler()
        self.settings: dict = {}

        # UI State
        self.terminal_win: TerminalWindow | None = None
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

        # Start unconfigured. Load settings via File > Load (see examples/ for sample configs).

    # ------------------------------------------------------------------ setup

    def _connect_signals(self):
        self.status_changed.connect(self._on_status_changed)
        self.term_write.connect(self._on_term_write)
        self.remote_files_ready.connect(self._update_remote_list_ui)
        self.error_raised.connect(self._on_error_raised)
        self.transfer_completed.connect(self._on_transfer_completed)

    def setup_menu(self):
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
            ("Copy to Remote", Pix.SP_ArrowRight, self.do_copy_to_remote),
            ("Copy to Host", Pix.SP_ArrowLeft, self.do_copy_to_host),
            ("Refresh", Pix.SP_BrowserReload, self.refresh_all),
            ("Terminal", Pix.SP_ComputerIcon, self.show_terminal),
        ]
        for text, pixmap, handler in actions:
            action = QAction(sp(pixmap), text, self, triggered=handler)
            toolbar.addAction(action)

    def setup_layout(self):
        # UIR-072: Host and Remote panes separated by a user-draggable splitter.
        splitter = QSplitter()

        # Left Side: Host Files
        host_group = QGroupBox("Host Files")
        host_layout = QVBoxLayout(host_group)
        host_layout.addWidget(QPushButton("Change Directory", clicked=self.change_host_dir))
        self.host_list = QListWidget()
        self.host_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        host_layout.addWidget(self.host_list)
        splitter.addWidget(host_group)

        # Right Side: Remote Files
        remote_group = QGroupBox("Remote Files")
        remote_layout = QVBoxLayout(remote_group)
        remote_layout.addWidget(QPushButton("Update", clicked=self.refresh_remote_files))
        self.remote_list = QListWidget()
        self.remote_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        remote_layout.addWidget(self.remote_list)
        splitter.addWidget(remote_group)

        splitter.setSizes([450, 450])
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.addWidget(splitter)
        self.setCentralWidget(container)

    def setup_status_bar(self):
        # UIR-010/UIR-014: single-line status bar; UIR-074: connection indicators.
        self.term_indicator = self._make_indicator("Terminal")
        self.trans_indicator = self._make_indicator("Transport")
        self.statusBar().addPermanentWidget(self.term_indicator)
        self.statusBar().addPermanentWidget(self.trans_indicator)
        self._update_indicators()
        self.set_status("Ready")

    @staticmethod
    def _make_indicator(name: str):
        from PySide6.QtWidgets import QLabel

        label = QLabel()
        label.setProperty("indicator_name", name)
        return label

    def _update_indicators(self):
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
        # UIR-014: truncate to 127 characters. Emitting (rather than setting
        # directly) makes set_status safe to call from any thread (NFR-004).
        self.status_changed.emit(text[:127])

    def _on_status_changed(self, text: str):
        self.statusBar().showMessage(text)

    def _on_term_write(self, text: str):
        # Single GUI-thread sink for all receive-area writes: incoming serial
        # data, local echo (FR-093), and transfer byte echo (FR-086). It never
        # touches the data buffers, so local-echo/hex text stays out of them.
        if self.terminal_win:
            self.terminal_win.write_text(text)

    def _on_error_raised(self, title: str, message: str):
        QMessageBox.critical(self, title, message)

    def _on_transfer_completed(self, direction: str):
        # Runs on the GUI thread (queued from the transfer worker). After a
        # successful transfer the destination list is otherwise stale until the
        # user manually refreshes it, so refresh the affected pane here.
        if direction == "host":
            self.refresh_host_files()
        elif direction == "remote":
            self.refresh_remote_files()

    # ------------------------------------------------------------- host files

    def refresh_host_files(self):
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
        path = QFileDialog.getExistingDirectory(self, "Change Directory", self.host_dir)
        if path:
            self.host_dir = path
            self.refresh_host_files()

    # -------------------------------------------------------------- terminal

    def show_terminal(self):
        if not self.terminal_win:
            self.terminal_win = TerminalWindow(
                self, self.handle_terminal_send, self.clear_terminal_buffers
            )
            self.terminal_win.chk_echo.toggled.connect(self._set_local_echo)
        else:
            self.terminal_win.showNormal()
        self.terminal_win.show()
        self.terminal_win.raise_()
        self.terminal_win.activateWindow()

    def _set_local_echo(self, enabled: bool):
        self._local_echo = enabled

    def handle_terminal_send(self, text):
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
        # Runs on the serial read daemon thread. Buffer bookkeeping happens here
        # (plain strings, not widgets); the display write is marshalled via the
        # term_write signal (NFR-004).
        # FR-090: store all received data in the receive buffer.
        self._rx_buffer += text
        if self._capture_active:
            self._remote_capture_buffer += text
        self.term_write.emit(text)

    def clear_terminal_buffers(self):
        # FR-090/FR-092: the Clear button is the explicit-clear trigger for
        # both the receive and transmit data buffers.
        self._rx_buffer = ""
        self._tx_buffer = ""

    # ----------------------------------------------------------- connect/disc

    def do_connect(self):
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
        # FR-063: the central Refresh button refreshes both lists; the Update
        # button (Remote Files group) refreshes the remote list only (FR-073).
        self.refresh_host_files()
        self.refresh_remote_files()

    def refresh_remote_files(self):
        if not self.serial_mgr.terminal_connected:
            self.set_status("Terminal port not open - cannot read file list")
            self.remote_list.clear()
            return
        threading.Thread(target=self._do_refresh_remote_logic, daemon=True).start()

    def _do_refresh_remote_logic(self):
        self.set_status("Updating remote file list...")
        self._remote_capture_buffer = ""
        self._capture_active = True
        cmd = self.settings.get("list_files_cmd", "DIR")
        eol = self.settings.get("eol", "CR")
        eol_char = EOL_MAP.get(eol, "\r")
        self.handle_terminal_send(cmd + eol_char)
        # FR-076: wait at least one second for output to start accumulating,
        # then wait for the receive buffer to time out (no new data within the
        # idle window) before processing, bounded by a safety maximum.
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
        files_dict = CPMParser.parse_dir_output(self._remote_capture_buffer)
        self.remote_files_ready.emit(files_dict)

    def _update_remote_list_ui(self, files_dict):
        self.remote_list.clear()
        self.remote_list.addItems(sorted(files_dict.keys()))
        self.set_status("Remote file list updated")

    # -------------------------------------------------------------- transfers

    def _selected_filename(self, list_widget) -> str | None:
        items = list_widget.selectedItems()
        return items[0].text() if items else None

    def do_copy_to_remote(self):
        # FR-080: a transfer is permitted only when both the Terminal and
        # Transport status flags are true.
        if not (self.serial_mgr.terminal_connected and self.serial_mgr.transport_connected):
            QMessageBox.critical(self, "Error", "Transport port not connected")
            return

        filename = self._selected_filename(self.host_list)
        if not filename:
            QMessageBox.warning(self, "Warning", "Please select a file to upload")
            return

        filepath = os.path.join(self.host_dir, filename)
        threading.Thread(target=self._transfer_to_remote, args=(filepath,), daemon=True).start()

    def _on_transfer_bytes(self, direction, data):
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

    def _issue_remote_cmd(self, cmd_key: str, default: str, filename: str) -> None:
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

    def _debug_enabled(self) -> bool:
        # FR-088: verbose transfer debug output is emitted to stdout only when
        # the `debug_logging` setting holds an affirmative value (default off).
        return str(self.settings.get("debug_logging", "OFF")).strip().upper() in (
            "ON",
            "TRUE",
            "1",
            "YES",
        )

    def _debug(self, msg: str) -> None:
        if self._debug_enabled():
            print(msg, flush=True)

    def _transfer_to_remote(self, filepath):
        self.set_status(f"Uploading {os.path.basename(filepath)}...")
        try:
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
            xm = XModem(ser, monitor=self._on_transfer_bytes)
            if xm.send_file(filepath):
                self.set_status(f"Successfully uploaded {os.path.basename(filepath)}")
                # Refresh the Remote Files list so the newly uploaded file shows.
                self.transfer_completed.emit("remote")
            else:
                self.error_raised.emit("X-Modem Error", "Transfer failed")
        except Exception as e:
            self._debug(f"[copy-to-remote] EXCEPTION: {e!r}")
            self.error_raised.emit("Error", str(e))

    def do_copy_to_host(self):
        # FR-080: a transfer is permitted only when both the Terminal and
        # Transport status flags are true.
        if not (self.serial_mgr.terminal_connected and self.serial_mgr.transport_connected):
            QMessageBox.critical(self, "Error", "Transport port not connected")
            return

        filename = self._selected_filename(self.remote_list)
        if not filename:
            QMessageBox.warning(self, "Warning", "Please select a file to download")
            return

        save_path = os.path.join(self.host_dir, filename)
        threading.Thread(target=self._transfer_to_host, args=(save_path,), daemon=True).start()

    def _transfer_to_host(self, save_path):
        self.set_status(f"Downloading {os.path.basename(save_path)}...")
        try:
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
            xm = XModem(ser, monitor=self._on_transfer_bytes)
            if xm.receive_file(save_path):
                self.set_status(f"Successfully downloaded {os.path.basename(save_path)}")
                # Refresh the Host Files list so the newly downloaded file shows.
                self.transfer_completed.emit("host")
            else:
                self.error_raised.emit("X-Modem Error", "Transfer failed")
        except Exception as e:
            self._debug(f"[copy-to-host] EXCEPTION: {e!r}")
            self.error_raised.emit("Error", str(e))

    # ------------------------------------------------------------------ config

    def load_config(self, filename):
        self.settings = self.config_handler.load_json(filename)
        self.set_status(f"Loaded config: {filename}")

    def menu_load(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load Config", "", "JSON files (*.json)")
        if path:
            self.load_config(path)

    def menu_save(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save Config", "", "JSON files (*.json)")
        if path:
            if not path.endswith(".json"):
                path += ".json"
            if self.config_handler.save_json(path, self.settings):
                self.set_status(f"Saved config to {path}")

    def menu_serial_config(self):
        # IFR-003 / UIR-022 / UIR-023: enumerate the host's serial ports.
        ports = [p.device for p in serial.tools.list_ports.comports()]

        def update_settings(new_set):
            self.settings.update(new_set)
            self.set_status("Serial settings updated")

        SerialConfigDialog(self, self.settings, ports, update_settings)

    def menu_general_config(self):
        def update_settings(new_set):
            self.settings.update(new_set)
            self.set_status("General settings updated")

        GeneralConfigDialog(self, self.settings, update_settings)

    # ------------------------------------------------------------------- exit

    def closeEvent(self, event):
        # FR-015: close any open COM ports. FR-016: close all open windows.
        self.serial_mgr.close_ports()
        if self.terminal_win:
            self.terminal_win.close()
        event.accept()


def main() -> None:
    app = cast(QApplication, QApplication.instance() or QApplication(sys.argv))
    apply_theme(app)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
