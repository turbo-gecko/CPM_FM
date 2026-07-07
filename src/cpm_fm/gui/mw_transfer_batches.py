from __future__ import annotations

import os
import threading

from PySide6.QtWidgets import QMessageBox

from cpm_fm.gui.conflict_dialog import CANCEL, SKIP
from cpm_fm.gui.mw_base import MainWindowMixinBase
from cpm_fm.terminal.cpm_parser import CPMParser
from cpm_fm.terminal.xmodem import XModem
from cpm_fm.utils.i18n import tr


class _TransferBatchesMixin(MainWindowMixinBase):
    """Batch transfer drivers for :class:`~cpm_fm.app.MainWindow` (mixin).

    The Copy-to-Remote / Copy-to-Host entry points and the per-batch worker
    loops that drive each file sequentially over the single Transport Port,
    plus the single-file X-Modem send/receive helpers. Runs on transfer worker
    threads and marshals all UI updates back via signals (NFR-004). The shared
    timing/echo helpers it calls live in :mod:`cpm_fm.gui.mw_transfers`; the
    conflict and CP/M-name prompts in :mod:`cpm_fm.gui.mw_transfer_guards`.
    """

    def do_copy_to_remote(self):
        """
        Satisfies: FR-080, FR-084, FR-106, CR-010.

        FR-080: a transfer is permitted only when both the Terminal and
        Transport status flags are true.
        """
        if not (self.serial_mgr.terminal_connected and self.serial_mgr.transport_connected):
            QMessageBox.critical(
                self, tr("dialog.error.title"), tr("error.transport_not_connected")
            )
            return

        # FR-106: transfer every selected file; warn when none is selected.
        filenames = self._selected_filenames(self.host_list)
        if not filenames:
            QMessageBox.warning(self, tr("dialog.warning.title"), tr("warning.select_upload"))
            return

        filepaths = [os.path.join(self.host_dir, name) for name in filenames]
        threading.Thread(
            target=self._transfer_to_remote_batch, args=(filepaths,), daemon=True
        ).start()

    def _transfer_to_remote_batch(self, filepaths, retry: bool = False):
        """
        Satisfies: FR-099, FR-105, FR-106, FR-107, FR-108, FR-109, FR-142, FR-159.

        Transfer each selected file sequentially over the
        single Transport Port. Runs on a worker thread. One progress
        dialog serves the whole batch. Abort on the first failure, or when the
        user cancels (FR-120). Each file's outcome (success, failure,
        cancellation, or skip) is recorded in the transfer history (FR-142);
        ``retry`` marks the records as a re-transfer (FR-144). Before sending,
        an existing destination file prompts the user to Overwrite/Skip/Cancel
        (FR-145/FR-146/FR-147).
        """
        count = len(filepaths)
        self._transfer_cancel.clear()  # FR-120: start each batch un-cancelled.
        self._conflict_policy = None  # FR-147: no carry-over between batches.
        self._last_xmodem_no_response = False  # FR-159: no carry-over between batches.
        self.batch_started.emit("remote", count)
        # FR-145: refresh the remote listing once so conflict detection checks
        # the live remote contents (empty set => no conflicts detected).
        remote_names = self._fresh_remote_names()
        succeeded = 0
        for index, filepath in enumerate(filepaths, start=1):
            name = os.path.basename(filepath)
            # The name the file will be given on the remote; differs from the
            # host base name when the user renames it to satisfy CP/M 8.3.
            remote_name = name
            # FR-120: stop before starting the next file if cancellation is requested.
            if self._transfer_cancel.is_set():
                self._finish_cancelled_batch("remote", succeeded)
                return
            # FR-148/FR-149: a name that does not meet the CP/M 8.3 convention
            # prompts the user to rename the file, skip it, or cancel the batch.
            if not CPMParser.is_valid_8_3(name):
                action, new_name = self._prompt_invalid_name(name)
                if action == CANCEL:
                    self._finish_cancelled_batch("remote", succeeded)
                    return
                if action == SKIP:
                    self._record_history(name, filepath, "remote", "skipped", 0, "", retry)
                    continue
                # RENAME: upload under the (validated) replacement name. The
                # renamed name is itself subject to conflict detection below.
                remote_name = new_name
            # FR-145/FR-146: prompt when the file already exists on the remote.
            if self._destination_conflict("remote", filepath, remote_names, remote_name):
                action = self._resolve_conflict(remote_name, "remote")
                if action == CANCEL:
                    self._finish_cancelled_batch("remote", succeeded)
                    return
                if action == SKIP:
                    self._record_history(remote_name, filepath, "remote", "skipped", 0, "", retry)
                    continue
                # FR-146 (Overwrite): erase the existing remote file first so the
                # receiver writes to a clean slate. Some CP/M receivers — notably
                # XMODEM-1K variants — prompt or stall on an existing file rather
                # than overwriting silently, which would block the X-Modem
                # handshake and hang the transfer. Deleting first mirrors the
                # per-file ERA the Restore wipe uses (FR-153).
                self._erase_remote_file(remote_name)
            # FR-109: let CP/M return to its prompt before the next command.
            if index > 1:
                self._wait_for_terminal_idle()
            self.set_status(tr("status.uploading", name=remote_name, index=index, count=count))
            try:
                total_bytes = os.path.getsize(filepath)
            except OSError:
                total_bytes = 0
            self.transfer_file_started.emit(remote_name, total_bytes, index)
            try:
                ok = self._send_one_to_remote(filepath, remote_name)
            except Exception as e:
                self._debug(f"[copy-to-remote] EXCEPTION: {e!r}")
                # FR-142: record the failed file with its error message.
                self._record_history(remote_name, filepath, "remote", "failure", 0, str(e), retry)
                if succeeded:
                    self.transfer_completed.emit("remote")
                self.error_raised.emit(tr("dialog.error.title"), str(e))
                return
            if not ok:
                # FR-120: a cancelled transfer is not a failure.
                if self._transfer_cancel.is_set():
                    self._record_history(remote_name, filepath, "remote", "cancelled", 0, "", retry)
                    self._finish_cancelled_batch("remote", succeeded)
                    return
                # FR-159: a handshake that got no response at all points at a
                # misconfigured Send to Remote command, distinct from a
                # generic mid-transfer failure.
                fail_key = (
                    "error.transfer_no_response_send"
                    if self._last_xmodem_no_response
                    else "error.transfer_failed"
                )
                # FR-142: record the failed file.
                self._record_history(
                    remote_name,
                    filepath,
                    "remote",
                    "failure",
                    0,
                    tr(fail_key, name=remote_name),
                    retry,
                )
                # FR-108: abort the batch and refresh if anything got through.
                if succeeded:
                    self.transfer_completed.emit("remote")
                self.error_raised.emit(
                    tr("dialog.xmodem_error.title"), tr(fail_key, name=remote_name)
                )
                return
            # FR-142: record the successful upload with its size.
            self._record_history(remote_name, filepath, "remote", "success", total_bytes, "", retry)
            succeeded += 1
        self.set_status(tr("status.successfully_uploaded", count=succeeded))
        # FR-109: after the final file, wait the inter-file settle period before
        # the FR-099 refresh so the post-batch Remote-list DIR is not issued while
        # a slow CP/M peer is still returning to the prompt (which would list the
        # drive before the just-uploaded file's directory entry is visible).
        if succeeded:
            self._cancellable_sleep(self._interfile_delay())
        # FR-099: refresh the Remote Files list so the uploaded files show.
        self.transfer_completed.emit("remote")

    def _send_one_to_remote(self, filepath, remote_name: str | None = None) -> bool:
        """
        Satisfies: FR-081, FR-082, FR-083, FR-087, FR-149, FR-159, FR-160.

        Launch the CP/M receiver (PCGET) and send one file over X-Modem.
        Returns True on success. Runs on the batch worker thread; it does not
        touch the progress dialog or refresh (the batch driver owns those).
        ``remote_name`` is the name the file is given on the remote (the PCGET
        argument); it defaults to the host base name and differs only when the
        file was renamed to satisfy the CP/M 8.3 convention (FR-149).
        """
        ser = self.serial_mgr.transport_port
        if remote_name is None:
            remote_name = os.path.basename(filepath)
        delay = self._launch_delay()
        self._debug(
            f"[copy-to-remote] start file={remote_name} "
            f"cmd={self.settings.get('send_remote_cmd', 'PCGET $1')!r} "
            f"launch_delay={delay}s transport={ser}"
        )
        # FR-037: when the Transport and Terminal Ports are the same physical
        # port, suspend the terminal read loop for the whole session so it does
        # not steal the start character (C/NAK) and ACKs that X-Modem needs.
        shared = ser is not None and ser is self.serial_mgr.terminal_port
        if shared:
            self.serial_mgr.pause_terminal_reads()
        try:
            # Clear stale bytes, then launch the CP/M receiver (PCGET) on the
            # Terminal Port so its start character lands on a clean transport
            # buffer that send_file does not flush.
            if ser:
                ser.reset_input_buffer()
            self._issue_remote_cmd(
                "send_remote_cmd", "PCGET $1", remote_name, cmd_key_1k="send_remote_cmd_1k"
            )
            self._debug(f"[copy-to-remote] launched PCGET; waiting {delay}s before handshake")
            # FR-120: wake early on cancel; send_file then aborts in its
            # handshake, sending CAN so the launched PCGET aborts too.
            self._cancellable_sleep(delay)
            self._debug("[copy-to-remote] starting X-Modem send")
            xm = XModem(
                ser,
                monitor=self._on_transfer_bytes,
                progress=self._on_transfer_progress_cb,
                cancel_check=self._transfer_cancel.is_set,
                handshake_timeout=self._handshake_timeout(),
            )
            ok = xm.send_file(filepath, use_1k=self._xmodem_1k_enabled())
            self._last_xmodem_no_response = xm.no_response
            return ok
        finally:
            if shared:
                self.serial_mgr.resume_terminal_reads()

    def do_copy_to_host(self):
        """
        Satisfies: FR-080, FR-085, FR-106, CR-010.

        FR-080: a transfer is permitted only when both the Terminal and
        Transport status flags are true.
        """
        if not (self.serial_mgr.terminal_connected and self.serial_mgr.transport_connected):
            QMessageBox.critical(
                self, tr("dialog.error.title"), tr("error.transport_not_connected")
            )
            return

        # FR-106: transfer every selected file; warn when none is selected.
        filenames = self._selected_filenames(self.remote_list)
        if not filenames:
            QMessageBox.warning(self, tr("dialog.warning.title"), tr("warning.select_download"))
            return

        save_paths = [os.path.join(self.host_dir, name) for name in filenames]
        threading.Thread(
            target=self._transfer_to_host_batch, args=(save_paths,), daemon=True
        ).start()

    def _transfer_to_host_batch(self, save_paths, retry: bool = False):
        """
        Satisfies: FR-099, FR-105, FR-106, FR-107, FR-108, FR-109, FR-142, FR-159.

        Receive each selected file sequentially over the single
        Transport Port. Runs on a worker thread. One progress dialog
        serves the whole batch. Abort on the first failure, or when the user
        cancels (FR-120). Each file's outcome (success, failure, cancellation,
        or skip) is recorded in the transfer history (FR-142); ``retry`` marks
        the records as a re-transfer (FR-144). Before receiving, an existing
        host file prompts the user to Overwrite/Skip/Cancel (FR-145/FR-146/FR-147).
        """
        count = len(save_paths)
        self._transfer_cancel.clear()  # FR-120: start each batch un-cancelled.
        self._conflict_policy = None  # FR-147: no carry-over between batches.
        self._last_xmodem_no_response = False  # FR-159: no carry-over between batches.
        self.batch_started.emit("host", count)
        succeeded = 0
        for index, save_path in enumerate(save_paths, start=1):
            name = os.path.basename(save_path)
            # FR-120: stop before starting the next file if cancellation is requested.
            if self._transfer_cancel.is_set():
                self._finish_cancelled_batch("host", succeeded)
                return
            # FR-145/FR-146: prompt when the file already exists on the host.
            if self._destination_conflict("host", save_path, set()):
                action = self._resolve_conflict(name, "host")
                if action == CANCEL:
                    self._finish_cancelled_batch("host", succeeded)
                    return
                if action == SKIP:
                    self._record_history(name, save_path, "host", "skipped", 0, "", retry)
                    continue
            # FR-109: let CP/M return to its prompt before the next command.
            if index > 1:
                self._wait_for_terminal_idle()
            self.set_status(tr("status.downloading", name=name, index=index, count=count))
            # The X-Modem stream carries no length, so total_bytes is 0
            # (indeterminate progress bar).
            self.transfer_file_started.emit(name, 0, index)
            try:
                ok = self._recv_one_to_host(save_path)
            except Exception as e:
                self._debug(f"[copy-to-host] EXCEPTION: {e!r}")
                # FR-142: record the failed file with its error message.
                self._record_history(name, save_path, "host", "failure", 0, str(e), retry)
                if succeeded:
                    self.transfer_completed.emit("host")
                self.error_raised.emit(tr("dialog.error.title"), str(e))
                return
            if not ok:
                # FR-120: a cancelled transfer is not a failure.
                if self._transfer_cancel.is_set():
                    self._record_history(name, save_path, "host", "cancelled", 0, "", retry)
                    self._finish_cancelled_batch("host", succeeded)
                    return
                # FR-159: a handshake that got no response at all points at a
                # misconfigured Receive from Remote command, distinct from a
                # generic mid-transfer failure.
                fail_key = (
                    "error.transfer_no_response_recv"
                    if self._last_xmodem_no_response
                    else "error.transfer_failed"
                )
                # FR-142: record the failed file.
                self._record_history(
                    name,
                    save_path,
                    "host",
                    "failure",
                    0,
                    tr(fail_key, name=name),
                    retry,
                )
                # FR-108: abort the batch and refresh if anything got through.
                if succeeded:
                    self.transfer_completed.emit("host")
                self.error_raised.emit(tr("dialog.xmodem_error.title"), tr(fail_key, name=name))
                return
            # FR-142: record the successful download with the received file size
            # (the X-Modem stream carries no length, so read it from disk).
            self._record_history(
                name, save_path, "host", "success", self._file_size(save_path), "", retry
            )
            succeeded += 1
        self.set_status(tr("status.successfully_downloaded", count=succeeded))
        # FR-109: after the final file, wait the inter-file settle period before
        # signalling completion, so any command that follows the batch is not
        # issued while a slow CP/M peer is still returning to the prompt. The
        # Host-list refresh reads the local filesystem, but the settle keeps the
        # remote quiescent for a subsequent remote command (parity with uploads).
        if succeeded:
            self._cancellable_sleep(self._interfile_delay())
        # FR-099: refresh the Host Files list so the downloaded files show.
        self.transfer_completed.emit("host")

    def _recv_one_to_host(self, save_path) -> bool:
        """
        Satisfies: FR-081, FR-082, FR-083, FR-087, FR-159, FR-160.

        Launch the CP/M sender (PCPUT) and receive one file over X-Modem.
        Returns True on success. Runs on the batch worker thread; it does not
        touch the progress dialog or refresh (the batch driver owns those).
        """
        ser = self.serial_mgr.transport_port
        delay = self._launch_delay()
        self._debug(
            f"[copy-to-host] start file={os.path.basename(save_path)} "
            f"cmd={self.settings.get('recv_remote_cmd', 'PCPUT $1')!r} "
            f"launch_delay={delay}s transport={ser}"
        )
        # FR-037: when the Transport and Terminal Ports are the same physical
        # port, suspend the terminal read loop for the whole session so it does
        # not consume the packets X-Modem is trying to receive.
        shared = ser is not None and ser is self.serial_mgr.terminal_port
        if shared:
            self.serial_mgr.pause_terminal_reads()
        try:
            # Launch the CP/M sender (PCPUT) on the Terminal Port, then receive.
            # receive_file drives the handshake (polls with NAK first, then 'C'
            # per NFR-003f), so it tolerates PCPUT taking several seconds to arm.
            self._issue_remote_cmd(
                "recv_remote_cmd",
                "PCPUT $1",
                os.path.basename(save_path),
                cmd_key_1k="recv_remote_cmd_1k",
            )
            self._debug(f"[copy-to-host] launched PCPUT; waiting {delay}s before handshake")
            # FR-120: wake early on cancel; receive_file then aborts in its
            # handshake, sending CAN so the launched PCPUT aborts too.
            self._cancellable_sleep(delay)
            self._debug("[copy-to-host] starting X-Modem receive")
            xm = XModem(
                ser,
                monitor=self._on_transfer_bytes,
                progress=self._on_transfer_progress_cb,
                cancel_check=self._transfer_cancel.is_set,
                handshake_timeout=self._handshake_timeout(),
            )
            ok = xm.receive_file(save_path, use_1k=self._xmodem_1k_enabled())
            self._last_xmodem_no_response = xm.no_response
            return ok
        finally:
            if shared:
                self.serial_mgr.resume_terminal_reads()
