from __future__ import annotations

import threading
import time

from PySide6.QtWidgets import QMessageBox

from cpm_fm.gui.mw_base import MainWindowMixinBase
from cpm_fm.gui.remote_unavailable_dialog import RemoteUnavailableDialog
from cpm_fm.gui.terminal_window import TerminalWindow
from cpm_fm.terminal.boot_sequence import SEND, SENDRAW, WAIT, WAITFOR, parse_boot_sequence
from cpm_fm.terminal.cpm_parser import CPMParser
from cpm_fm.utils.i18n import tr

EOL_MAP = {"CR": "\r", "LF": "\n", "CRLF": "\r\n"}


class _RemoteMixin(MainWindowMixinBase):
    """Terminal, connection, and remote-listing logic for MainWindow (mixin).

    Opening/closing the Terminal Window (FR-097) and the local-echo and
    send/receive buffer handling (FR-090-FR-095); the Connect/Disconnect
    workflow over the Terminal/Transport ports (FR-030-FR-058); and the remote
    directory listing, terminal-response capture, and drive-change logic
    (FR-073-FR-079, FR-100-FR-104). Worker-thread methods marshal UI updates
    back via signals (NFR-004). Shared with the transfer/guard mixins through
    ``handle_terminal_send`` and ``_capture_terminal_response``.
    """

    def show_terminal(self):
        """
        Satisfies: FR-097.
        """
        if not self.terminal_win:
            self.terminal_win = TerminalWindow(
                self,
                self.handle_terminal_key,
                self.clear_terminal_buffers,
                self.do_boot_sequence,
                engine=self._term_engine,
            )
            self.terminal_win.chk_echo.toggled.connect(self._set_local_echo)
            # FR-004: restore the Terminal Window's saved geometry on first open.
            self.window_state.restore_geometry("terminal", self.terminal_win)
        else:
            self.terminal_win.showNormal()
        # UIR-068: the boot button is enabled only when a sequence is configured.
        self._refresh_boot_button()
        # FR-094: the Enter key transmits the configured EOL.
        eol_char = EOL_MAP.get(self.settings.get("eol", "CR"), "\r")
        self.terminal_win.set_eol(eol_char.encode("ascii"))
        self.terminal_win.show()
        self.terminal_win.raise_()
        self.terminal_win.activateWindow()
        # Render whatever the engine already holds (data may have arrived before
        # the window was first opened) and settle autoscroll to the bottom.
        self.terminal_win.render_screen()
        # FR-096: focus the receive area so typing is transmitted immediately.
        self.terminal_win.focus_input()

    def _refresh_boot_button(self):
        """Sync the Terminal Window boot button's enabled state to the config.

        Enabled only when a non-empty boot sequence is configured (UIR-068);
        re-evaluated on open and whenever the configuration changes while the
        window is open.

        Satisfies: UIR-068.
        """
        if self.terminal_win is not None:
            self.terminal_win.set_boot_enabled(self._boot_sequence_configured())

    def _set_local_echo(self, enabled: bool):
        """
        Satisfies: FR-093.
        """
        self._local_echo = enabled

    def handle_terminal_key(self, data: bytes):
        """Transmit raw keystroke bytes typed into the Terminal Window (FR-096).

        Runs on the GUI thread (from the receive area's key handler). Sends the
        already-encoded VT-100 bytes on the Terminal Port, records them in the
        transmit buffer (FR-092), and — when Local Echo is on — echoes them to
        the screen by feeding the same bytes through the engine via term_write
        (FR-093). If the Terminal Port is not open, reports it and sends nothing
        (FR-098).

        Satisfies: FR-096, FR-092, FR-093, FR-098.
        """
        if not self.serial_mgr.terminal_connected:
            self.set_status(tr("status.terminal_not_open_send"))
            return
        self.serial_mgr.send_raw("terminal", data)
        # FR-092: record transmitted data in the transmit buffer (decoded to
        # text, matching the receive-buffer convention).
        self._tx_buffer += data.decode("ascii", errors="replace")
        # FR-093: local echo copies transmitted data to the receive area only.
        if self._local_echo:
            self.term_write.emit(data)

    def handle_terminal_send(self, text, append_eol: bool = True):
        """
        Satisfies: FR-092, FR-093, FR-094, FR-098.

        Sends a line of text on the Terminal Port. Used by the boot-sequence
        ``SEND`` directive and the remote-listing/drive-change capture reads
        (``_capture_terminal_response``); may run on the GUI thread or a worker
        thread. Sends and buffers the data directly; the local-echo display is
        marshalled to the GUI thread via term_write.

        ``append_eol`` is set False by callers that need the text sent on its
        own without a trailing EOL.
        """
        if not self.serial_mgr.terminal_connected:
            self.set_status(tr("status.terminal_not_open_send"))
            return

        eol = self.settings.get("eol", "CR")
        eol_char = EOL_MAP.get(eol, "\r")

        # Prevent double-terminators if already appended (e.g. in _do_refresh_remote_logic)
        if append_eol and not text.endswith(eol_char):
            text += eol_char

        self.serial_mgr.send_data("terminal", text)
        # FR-092: store transmitted data (with EOL) in the transmit buffer.
        self._tx_buffer += text
        # FR-093: local echo copies transmitted data (a byte-for-byte copy,
        # including its EOL) to the receive area only. Encoded the same way
        # send_data transmits it (ASCII/replace) so the echo matches the bytes
        # on the wire, then fed through the engine via term_write (bytes).
        if self._local_echo:
            self.term_write.emit(text.encode("ascii", errors="replace"))

    def handle_terminal_recv(self, data: bytes):
        """
        Satisfies: FR-090, FR-091.

        Runs on the serial read daemon thread. Receives the raw bytes read from
        the Terminal Port and:

        * decodes them to text for the receive buffer and, when a capture is
          active, the remote-capture buffer (FR-090). The decode uses the same
          ASCII/replace rule the read loop used previously, so the DIR-listing,
          drive-probe, and boot-sequence capture logic sees byte-identical text;
          and
        * marshals the raw bytes to the GUI thread via term_write (NFR-004),
          where they are fed into the VT-100 engine and rendered (FR-091).

        Only plain strings/bytes are touched here, never a widget or the engine
        (the engine is fed on the GUI thread, keeping it single-threaded).
        """
        text = data.decode("ascii", errors="replace")
        self._rx_buffer += text
        if self._capture_active:
            self._remote_capture_buffer += text
        self.term_write.emit(data)

    def clear_terminal_buffers(self):
        """
        Satisfies: FR-095.

        FR-090/FR-092: the Clear button is the explicit-clear trigger for
        both the receive and transmit data buffers.
        """
        self._rx_buffer = ""
        self._tx_buffer = ""

    def do_connect(self):
        """
        Satisfies: FR-030, FR-031, FR-032, FR-034, FR-037, FR-038, FR-039,
        FR-040, FR-041, FR-046.
        """
        if self.serial_mgr.open_port("terminal", self.settings):
            self.set_status(tr("status.terminal_port_open"))
            term_port = self.settings.get("terminal_port")
            trans_port = self.settings.get("transport_port")
            if term_port != trans_port:
                if not self.serial_mgr.open_port("transport", self.settings):
                    QMessageBox.critical(
                        self, tr("dialog.error.title"), tr("error.transport_unable_open")
                    )
            else:
                # FR-037: same physical port. Point the Transport Port at the
                # already-open Terminal Port object so transfers have a real
                # port to use (not None) and set the Transport flag.
                self.serial_mgr.transport_port = self.serial_mgr.terminal_port
                self.serial_mgr.transport_connected = True
        else:
            QMessageBox.critical(self, tr("dialog.error.title"), tr("error.terminal_unable_open"))
        self._update_indicators()

        # FR-041/FR-046: only once BOTH ports are confirmed open, probe whether
        # the remote file system is reachable. The probe sends an EOL and waits
        # for a drive prompt, so it runs on a worker thread (NFR-004) and reports
        # back via the connect_probe_ok / connect_probe_failed signals.
        if self.serial_mgr.terminal_connected and self.serial_mgr.transport_connected:
            self.set_status(tr("status.checking_remote_fs"))
            threading.Thread(target=self._do_connect_probe_logic, daemon=True).start()

    def _do_connect_probe_logic(self):
        """
        Satisfies: FR-041, FR-043, FR-044, FR-046, FR-048.

        Runs on a worker thread. Probe for a CP/M drive prompt (FR-041/FR-043).
        If none is found and a boot sequence is configured (FR-047), run the
        sequence and probe once more (FR-048, at most one recovery attempt). On
        success emit connect_probe_ok with the detected drive letter (FR-042);
        otherwise emit connect_probe_failed, which presents the Remote
        Filesystem Unavailable dialog (FR-044). The UI updates run on the GUI
        thread via those signals (NFR-004).
        """
        letter = self._probe_for_drive()
        if letter is None and self._boot_sequence_configured():
            # FR-048: attempt boot-sequence recovery, then re-probe once.
            self.run_boot_sequence()
            letter = self._probe_for_drive()
        if letter is not None:
            self.connect_probe_ok.emit(letter)
        else:
            self.connect_probe_failed.emit()

    def _probe_for_drive(self):
        """Send a bare EOL and look for a CP/M drive prompt, with one retry.

        Returns the detected drive letter (DR-033a) or ``None``. Runs on a
        worker thread; FR-043's single retry is performed here.

        Satisfies: FR-041, FR-043.
        """
        text = self._capture_terminal_response("")
        letter = CPMParser.drive_prompt_letter(text)
        if letter is None:
            text = self._capture_terminal_response("")
            letter = CPMParser.drive_prompt_letter(text)
        return letter

    def _boot_sequence_configured(self) -> bool:
        """True when a non-empty boot sequence (FR-047) is configured.

        Satisfies: FR-047, FR-048.
        """
        return bool(self.settings.get("boot_sequence", "").strip())

    def run_boot_sequence(self) -> bool:
        """Execute the configured boot sequence on the Terminal Port.

        Parses the ``boot_sequence`` setting (FR-047) and runs each directive in
        order: SEND (text + EOL), SENDRAW (raw control bytes), WAIT (sleep), and
        WAITFOR (capture until a string appears or the timeout elapses).
        Synchronous and intended to run on a worker thread (it sleeps and waits
        on serial I/O). Returns True if a non-empty sequence ran to completion,
        False if the sequence was empty or failed to parse.

        Satisfies: FR-047, FR-048, FR-049, NFR-004.
        """
        script = self.settings.get("boot_sequence", "")
        if not script.strip():
            return False
        try:
            steps = parse_boot_sequence(script)
        except ValueError as e:
            print(f"Boot sequence parse error: {e}")
            self.set_status(tr("status.boot_failed"))
            return False
        self.set_status(tr("status.boot_running"))
        for step in steps:
            if step.kind == SEND:
                # handle_terminal_send appends the configured EOL and echoes.
                self.handle_terminal_send(step.text)
            elif step.kind == SENDRAW:
                self.serial_mgr.send_raw("terminal", step.data)
            elif step.kind == WAIT:
                time.sleep(step.seconds)
            elif step.kind == WAITFOR:
                self._wait_for_text(step.text, step.seconds)
        return True

    def _wait_for_text(self, target: str, timeout: float) -> bool:
        """Capture Terminal Port output until ``target`` appears or ``timeout``.

        Reuses the capture buffer fed by ``handle_terminal_recv``. Returns True
        if the text appeared before the timeout. Runs on a worker thread.

        Satisfies: FR-047.
        """
        self._remote_capture_buffer = ""
        self._capture_active = True
        waited = 0.0
        poll = 0.05
        found = False
        while waited < timeout:
            if target in self._remote_capture_buffer:
                found = True
                break
            time.sleep(poll)
            waited += poll
        self._capture_active = False
        return found

    def do_boot_sequence(self):
        """Manually run the boot sequence from the Terminal Window (FR-049).

        Runs the sequence and re-probes on a worker thread (NFR-004). On success
        the drive drop-down and Remote Files list update via connect_probe_ok
        (FR-042); on failure the status bar reports it and no modal dialog is
        shown (the user is already at the Terminal Window).

        Satisfies: FR-049.
        """
        if not self.serial_mgr.terminal_connected:
            self.set_status(tr("status.terminal_not_open_send"))
            return
        threading.Thread(target=self._do_boot_sequence_logic, daemon=True).start()

    def _do_boot_sequence_logic(self):
        """Worker: run the boot sequence then re-probe (FR-049).

        Satisfies: FR-049.
        """
        if not self.run_boot_sequence():
            return
        letter = self._probe_for_drive()
        if letter is not None:
            self.connect_probe_ok.emit(letter)
        else:
            self.set_status(tr("status.boot_failed"))

    def _on_connect_probe_ok(self, drive):
        """
        Satisfies: FR-042.

        Runs on the GUI thread (queued from the probe worker). Point the drive
        drop-down at the detected drive and populate the Remote Files list as
        the Update button would (FR-073). Setting the combo index
        programmatically does not fire its ``activated`` signal, so this does
        not trigger a second drive-change.
        """
        index = ord(drive) - ord("A")
        if 0 <= index < self.drive_combo.count():
            self.drive_combo.setCurrentIndex(index)
        self.refresh_remote_files()

    def _on_connect_probe_failed(self):
        """
        Satisfies: FR-044, FR-045.

        Runs on the GUI thread (queued from the probe worker). Inform the user
        the remote file system is unreachable (UIR-092) and act on their choice:
        Abort closes the port(s) following the Disconnect behaviour
        (FR-050-FR-057) and clears the list; Continue leaves everything open;
        Terminal opens the Terminal Window (FR-097). Both Continue and Terminal
        leave the ports open.
        """
        dialog = RemoteUnavailableDialog(self)
        dialog.exec()
        if dialog.choice == RemoteUnavailableDialog.ABORT:
            self.do_disconnect()
        elif dialog.choice == RemoteUnavailableDialog.TERMINAL:
            self.show_terminal()

    def do_disconnect(self):
        """
        Satisfies: FR-050-FR-058.

        Robustness: the close attempts are unconditional — they do NOT depend
        on the terminal_connected / transport_connected status flags. Those
        flags can drift out of sync with the real port state (e.g. the port is
        still open and communicating but a flag was cleared), and a guarded
        disconnect would then refuse to act, leaving the comms sessions open.
        The underlying close_*_port() methods are safe to call when the port is
        already closed (they no-op and return True), so always attempting the
        close is the correct, defensive behaviour.
        """
        term_port = self.settings.get("terminal_port")
        trans_port = self.settings.get("transport_port")

        # FR-050/FR-051: close the Terminal Port; on failure show an error
        # dialog and cancel the current workflow.
        if not self.serial_mgr.close_terminal_port():
            QMessageBox.critical(self, tr("dialog.error.title"), tr("error.terminal_unable_close"))
            self._update_indicators()
            return
        # FR-052 (flag cleared by close_terminal_port) / FR-053 (status text).
        self.set_status(tr("status.terminal_port_closed"))
        # FR-058: the remote listing was read over the now-closed Terminal
        # Port, so it is stale — clear it.
        self._clear_remote_files()

        if trans_port == term_port:
            # FR-054: same physical port — it was just closed above as the
            # Terminal Port. Clear the Transport flag and drop the shared
            # reference so it cannot point at the now-closed port object.
            self.serial_mgr.transport_port = None
            self.serial_mgr.transport_connected = False
        else:
            # FR-055/FR-056/FR-057: different port — always attempt to close it.
            if not self.serial_mgr.close_transport_port():
                QMessageBox.critical(
                    self, tr("dialog.error.title"), tr("error.transport_unable_close")
                )
                self._update_indicators()
                return

        self._update_indicators()

    def do_refresh_remote_files(self):
        """Handle the Remote Files "Update" button click.

        Mirrors do_copy_to_host: when the port is not open, raise the same
        critical error dialog (in addition to the status-bar message and the
        list being cleared by refresh_remote_files), then delegate. The
        auto-refresh callers (post-transfer) call refresh_remote_files directly
        so they never raise this dialog.
        """
        if not self.serial_mgr.terminal_connected:
            QMessageBox.critical(self, tr("dialog.error.title"), tr("error.terminal_not_connected"))
        self.refresh_remote_files()

    def refresh_remote_files(self):
        """
        Satisfies: FR-073, FR-074.

        FR-073: populate the Remote Files list for the drive currently shown in
        the drive-selection drop-down (UIR-017). Switch to that drive first (as
        if it had just been selected - FR-100-FR-104) before listing, so the
        displayed files always match the drive next to the Update button even
        when the remote's current drive was changed directly in the Terminal
        Window. Runs the drive-change logic on a worker thread.
        """
        if not self.serial_mgr.terminal_connected:
            self.set_status(tr("status.terminal_not_open_list"))
            self._clear_remote_files()
            return
        drive = self.drive_combo.currentText()[0]  # 'A'..'P'
        threading.Thread(target=self._do_change_drive_logic, args=(drive,), daemon=True).start()

    def _capture_terminal_response(self, command: str, cancellable: bool = False) -> str:
        """
        Satisfies: FR-075, FR-076, FR-101, FR-120, FR-145.

        Send `command` (with the configured EOL appended) on the Terminal Port
        and capture the echoed output into the capture buffer until it idles
        out, returning the captured text. Runs on a worker thread.
        FR-076: wait at least one second for output to start accumulating,
        then wait for the receive buffer to time out (no new data within the
        idle window) before processing, bounded by a safety maximum.

        ``cancellable`` is set by transfer callers (the pre-upload remote
        listing, FR-145) so a Cancel during this read wakes the worker promptly
        instead of blocking for the whole idle/settle budget (FR-120); the
        partial capture so far is returned. It is left False for the standalone
        Remote-list refresh / drive-change reads, which are not part of a
        transfer and must not observe a stale transfer-cancel flag.
        """
        self._remote_capture_buffer = ""
        self._capture_active = True
        eol_char = EOL_MAP.get(self.settings.get("eol", "CR"), "\r")
        self.handle_terminal_send(command + eol_char)

        def _settle(secs: float) -> bool:
            # Returns True when the wait should stop early (cancellation).
            if cancellable:
                return self._cancellable_sleep(secs)
            time.sleep(secs)
            return False

        idle_window = 0.5
        max_wait = 10.0
        if not _settle(1.0):
            waited = 1.0
            while waited < max_wait:
                prev_len = len(self._remote_capture_buffer)
                if _settle(idle_window):
                    break
                waited += idle_window
                if len(self._remote_capture_buffer) == prev_len:
                    break
        self._capture_active = False
        return self._remote_capture_buffer

    def _do_refresh_remote_logic(self):
        """
        Satisfies: FR-077, FR-078, FR-079.
        """
        self.set_status(tr("status.updating_remote_list"))
        cmd = self.settings.get("list_files_cmd", "DIR")
        text = self._capture_terminal_response(cmd)
        files_dict = CPMParser.parse_dir_output(text)
        self.remote_files_ready.emit(files_dict)

    def change_drive(self, index):
        """
        Satisfies: FR-100, FR-104.

        FR-100/FR-104: switch the remote drive to the selected letter. Mirror
        FR-074 and refuse when the Terminal Port is closed.
        """
        if not self.serial_mgr.terminal_connected:
            self.set_status(tr("status.terminal_not_open_list"))
            self._clear_remote_files()
            return
        drive = self.drive_combo.itemText(index)[0]  # 'A'..'P'
        threading.Thread(target=self._do_change_drive_logic, args=(drive,), daemon=True).start()

    def _do_change_drive_logic(self, drive):
        """
        Satisfies: FR-100, FR-101, FR-102, FR-103.

        FR-100/FR-101: send "<letter>:" and capture the response. FR-102: if
        the new "<letter>>" drive prompt appears, populate the Remote Files
        list exactly as the Update button would (FR-073). FR-103: otherwise
        clear the list and report "Drive not found". Runs on a worker thread,
        so calling _do_refresh_remote_logic directly is correct (it marshals
        its UI update via the remote_files_ready signal).
        """
        self.set_status(tr("status.changing_drive", drive=drive))
        text = self._capture_terminal_response(f"{drive}:")
        if CPMParser.has_drive_prompt(text, drive):
            self._do_refresh_remote_logic()
        else:
            self.drive_not_found.emit(drive)

    def _on_drive_not_found(self, drive):
        """
        Satisfies: FR-103.

        FR-103: runs on the GUI thread (queued from the drive-change worker).
        """
        self._clear_remote_files()
        QMessageBox.warning(
            self, tr("dialog.drive_not_found.title"), tr("error.drive_not_found_body", drive=drive)
        )

    def _update_remote_list_ui(self, files_dict):
        """
        Satisfies: FR-078, FR-079, FR-133.
        """
        # FR-133: store the parsed names as the canonical list and render them
        # through the active filter/sort controls. With the default settings
        # (no filter, sort by name ascending) this reproduces the FR-078
        # ascending-alphabetical display.
        self._remote_files = list(files_dict.keys())
        self._apply_remote_view()
        self.set_status(tr("status.remote_list_updated"))
