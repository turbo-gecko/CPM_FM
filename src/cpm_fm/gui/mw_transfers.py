from __future__ import annotations

import os
import threading
import time

from PySide6.QtWidgets import QMessageBox

from cpm_fm.gui.mw_base import MainWindowMixinBase
from cpm_fm.utils.i18n import tr


class _TransfersMixin(MainWindowMixinBase):
    """Shared file-transfer engine for :class:`~cpm_fm.app.MainWindow` (mixin).

    Holds the transfer support layer: file selection, the drag-and-drop entry
    points, the byte/debug echo hooks, the XMODEM-1K toggle, the launch and
    inter-file timing helpers, the cancellable sleep / terminal-idle waits, and
    the cancelled-batch teardown. The batch drivers live in
    :mod:`cpm_fm.gui.mw_transfer_batches` and the conflict / CP/M-name prompts
    in :mod:`cpm_fm.gui.mw_transfer_guards`; all three are combined into
    ``MainWindow`` by inheritance, so every method here runs against the full
    window's state and cross-thread signals (NFR-004).
    """

    def _selected_filenames(self, list_widget) -> list[str]:
        """
        Satisfies: FR-106, FR-107.

        FR-106/FR-107: every selected file, in list display order (top to
        bottom). selectedItems() does not guarantee display order, so iterate
        the rows and keep those that are selected.
        """
        return [
            list_widget.item(row).text()
            for row in range(list_widget.count())
            if list_widget.item(row).isSelected()
        ]

    def _on_files_dropped(self, target_pane, source_pane, payload, external):
        """Start a drag-and-drop file transfer from a pane drop (FR-137, FR-138).

        Runs on the GUI thread (the drop event), then hands the actual transfer
        to the same batch worker threads as the Copy buttons, marshalling UI
        updates back via the existing signals (NFR-004). ``payload`` is a list
        of file names for an internal drag or absolute host paths for an
        external OS drop (``external``). Dropping onto the **Remote** pane sends
        to the remote (Copy to Remote); dropping onto the **Host** pane receives
        from the remote (Copy to Host). A transfer is permitted only when both
        the Terminal and Transport status flags are true (FR-080/CR-010), and is
        confirmed first (FR-137).

        Satisfies: FR-137, FR-138, FR-080, FR-106, FR-107, CR-010.
        """
        if not (self.serial_mgr.terminal_connected and self.serial_mgr.transport_connected):
            QMessageBox.critical(
                self, tr("dialog.error.title"), tr("error.transport_not_connected")
            )
            return
        if not payload:
            return
        if target_pane == "remote":
            if not self._confirm_dnd_transfer("remote", len(payload)):
                return
            # FR-138: external drops already carry absolute paths; an internal
            # drag from the Host pane carries names relative to the host dir.
            filepaths = (
                list(payload)
                if external
                else [os.path.join(self.host_dir, name) for name in payload]
            )
            threading.Thread(
                target=self._transfer_to_remote_batch, args=(filepaths,), daemon=True
            ).start()
        elif target_pane == "host":
            if not self._confirm_dnd_transfer("host", len(payload)):
                return
            save_paths = [os.path.join(self.host_dir, name) for name in payload]
            threading.Thread(
                target=self._transfer_to_host_batch, args=(save_paths,), daemon=True
            ).start()

    def _confirm_dnd_transfer(self, direction: str, count: int) -> bool:
        """Ask the user to confirm a drag-and-drop transfer (FR-137).

        Drag-and-drop is easy to trigger by accident and a serial transfer is
        slow, so each drop is confirmed before it starts. Returns True when the
        user accepts.

        Satisfies: FR-137.
        """
        key = (
            "dialog.dnd_confirm.to_remote"
            if direction == "remote"
            else "dialog.dnd_confirm.to_host"
        )
        # UIR-075: Cancel far left, OK far right (was a Yes/No QMessageBox whose
        # order followed the native platform style).
        return self._confirm_dialog(
            tr("dialog.dnd_confirm.title"),
            tr(key, count=count),
            tr("button.ok"),
        )

    def _on_transfer_bytes(self, direction, data):
        """
        Satisfies: FR-086, FR-088.

        Echo transfer bytes to the Terminal Window as hex tokens of
        the form <HH>, unless the `echo_transfer_data` setting disables it
        (FR-086). Runs on the transfer worker thread; the display write
        is marshalled to the GUI thread via term_write (NFR-004). The slot
        no-ops when the Terminal Window does not exist.
        Direction-tagged, timestamped trace to stdout (visible via
        `python -m cpm_fm`) so transfers can be debugged without conflating
        sent and received bytes, and so prompt/response timing is visible.
        The stdout trace (FR-088) is independent of the Terminal Window echo,
        so it still fires when the echo is turned off.
        """
        if self._debug_enabled():
            print(f"[xfer {direction} {time.time():.2f}] {data.hex(' ')}", flush=True)
        if not self._echo_transfer_enabled():
            return
        hex_text = "".join(f"<{b:02X}>" for b in data)
        # term_write carries bytes (fed to the VT-100 engine); the hex tokens are
        # ASCII, so render as-is on the terminal screen.
        self.term_write.emit(hex_text.encode("ascii"))

    def _echo_transfer_enabled(self) -> bool:
        """
        Satisfies: FR-086.

        The X-Modem transfer byte echo to the Terminal Window is emitted only
        when the `echo_transfer_data` setting holds an affirmative value
        (`ON`/`TRUE`/`1`/`YES`, case-insensitive); the default is off.
        """
        return str(self.settings.get("echo_transfer_data", "OFF")).strip().upper() in (
            "ON",
            "TRUE",
            "1",
            "YES",
        )

    def _on_transfer_progress_cb(self, blocks, bytes_done, total):
        """
        Satisfies: FR-105.

        XModem progress hook. Runs on the transfer worker thread; the
        dialog update is marshalled to the GUI thread via transfer_progress
        (NFR-004). total is unused here (the dialog captured it at start).
        """
        self.transfer_progress.emit(blocks, bytes_done)

    def _xmodem_1k_enabled(self) -> bool:
        """Whether XMODEM-1K mode is selected (the ``xmodem_1k`` setting).

        When enabled, host->remote sends use 1024-byte STX frames and the
        ``_1k`` launch commands replace the standard send/recv commands.

        Satisfies: UIR-089.
        """
        return str(self.settings.get("xmodem_1k", "OFF")).upper() == "ON"

    def _issue_remote_cmd(
        self, cmd_key: str, default: str, filename: str, cmd_key_1k: str | None = None
    ) -> None:
        """
        Satisfies: FR-087, UIR-089, UIR-090.

        Implements recv_remote_cmd / send_remote_cmd (UIR-045/UIR-046): the
        configured command is sent on the Terminal Port to launch the CP/M
        side of the transfer (PCPUT/PCGET), with "$1" replaced by the
        filename. Runs on the transfer worker thread; handle_terminal_send is
        safe to call from there (it marshals its display write via a signal).

        When ``cmd_key_1k`` is given and XMODEM-1K mode is enabled, its non-blank
        template is used instead; a blank ``cmd_key_1k`` template falls back to
        the standard ``cmd_key``/``default``.
        """
        if cmd_key_1k is not None and self._xmodem_1k_enabled():
            template_1k = str(self.settings.get(cmd_key_1k, "")).strip()
            if template_1k:
                self.handle_terminal_send(template_1k.replace("$1", filename))
                return
        template = self.settings.get(cmd_key, default)
        if not template:
            return
        self.handle_terminal_send(template.replace("$1", filename))

    def _launch_delay(self) -> float:
        """
        Satisfies: FR-089.

        Seconds to wait after launching the CP/M side (PCPUT/PCGET) before
        starting the X-Modem handshake. This must exceed the remote program's
        start-up time: while it prints its banner and opens the file it is not
        reading its UART, and any start-character prompts we send during that
        window pile up and overrun its (FIFO-less) UART. Tunable via the
        `xfer_launch_delay` setting; default 3s.
        """
        try:
            return max(0.0, float(self.settings.get("xfer_launch_delay", 3.0)))
        except (TypeError, ValueError):
            return 3.0

    def _handshake_timeout(self) -> float:
        """
        Satisfies: FR-160.

        Seconds to wait for the remote's very first X-Modem response byte
        before treating the transfer as a misconfigured-command failure
        (FR-159), independent of the bounded per-packet retransmission
        timeouts used once the transfer is underway (NFR-003p). Tunable via
        the `xfer_handshake_timeout` setting (UIR-093); default 10s.
        """
        try:
            return max(0.1, float(self.settings.get("xfer_handshake_timeout", 10.0)))
        except (TypeError, ValueError):
            return 10.0

    def _interfile_delay(self) -> float:
        """
        Satisfies: FR-109.

        FR-109: extra settle time after the terminal output goes idle between
        files in a batch, before the next launch command is sent. Tunable via
        the `xfer_interfile_delay` setting (UIR-052); default 2s.
        """
        try:
            return max(0.0, float(self.settings.get("xfer_interfile_delay", 2.0)))
        except (TypeError, ValueError):
            return 2.0

    def _cancellable_sleep(self, seconds: float, cancel_event=None) -> bool:
        """Sleep up to ``seconds``, waking early if a cancellation is requested.
        Returns True if the wait ended because cancellation was requested, False
        if the full interval elapsed.

        The worker-thread launch/settle waits (FR-089/FR-109) and the remote
        listing read (FR-145) are otherwise plain sleeps, so a Cancel pressed
        during one of them would not be observed until the whole delay had
        elapsed (up to ~10s). This sleeps in small steps, polling the
        thread-safe cancel flag between them, so the cancel takes effect
        promptly (FR-120). The interval is counted in steps rather than against
        the wall clock so tests that neutralise ``time.sleep`` still run fast.
        Runs on a worker thread.

        ``cancel_event`` selects which flag to poll; it defaults to the transfer
        cancel flag (FR-120). The connect-probe path passes ``_probe_cancel`` so
        a Disconnect during the probe wakes its capture waits promptly (FR-050).

        Satisfies: FR-120, FR-050.
        """
        event = cancel_event if cancel_event is not None else self._transfer_cancel
        remaining = max(0.0, seconds)
        step = 0.05
        while remaining > 0:
            if event.is_set():
                return True
            time.sleep(min(step, remaining))
            remaining -= step
        return event.is_set()

    def _wait_for_terminal_idle(self) -> None:
        """
        Satisfies: FR-109, FR-120.

        Between files in a batch, wait for the previous CP/M transfer
        program to finish and the CCP command prompt to return before issuing
        the next launch command. Without this, the prior PCPUT/PCGET is still
        closing its file and returning to the CCP — and therefore not yet
        servicing its (FIFO-less) UART — so the leading characters of the next
        command are lost (e.g. "PCPUT X" arriving as "CPUT X"). Mirrors the
        idle-detection of _capture_terminal_response: an initial wait for the
        completion text to start, then wait for the receive buffer to stop
        growing, bounded by a safety maximum, then a final settle. Runs on the
        transfer worker thread; it only reads the plain `_rx_buffer` string.
        Each wait is cancellable so a Cancel between files is observed promptly
        rather than after the full settle (FR-120).
        """
        idle_window = 0.5
        max_wait = 8.0
        if self._cancellable_sleep(1.0):
            return
        waited = 1.0
        while waited < max_wait:
            prev_len = len(self._rx_buffer)
            if self._cancellable_sleep(idle_window):
                return
            waited += idle_window
            if len(self._rx_buffer) == prev_len:
                break
        self._cancellable_sleep(self._interfile_delay())

    def _debug_enabled(self) -> bool:
        """
        Satisfies: FR-088.

        Verbose transfer debug output is emitted to stdout only when
        the `debug_logging` setting holds an affirmative value (default off).
        """
        return str(self.settings.get("debug_logging", "OFF")).strip().upper() in (
            "ON",
            "TRUE",
            "1",
            "YES",
        )

    def _debug(self, msg: str) -> None:
        """
        Satisfies: FR-088.
        """
        if self._debug_enabled():
            print(msg, flush=True)

    def _finish_cancelled_batch(self, direction: str, succeeded: int) -> None:
        """
        Satisfies: FR-120.

        Common end-of-batch handling for a user-cancelled transfer (either
        direction). Runs on the transfer worker thread: report the cancellation
        and hand the dialog teardown / optional refresh to the GUI thread via
        the transfer_cancelled signal (NFR-004).
        """
        self.set_status(tr("status.transfer_cancelled", count=succeeded))
        self.transfer_cancelled.emit(direction, succeeded > 0)
