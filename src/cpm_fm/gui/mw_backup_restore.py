from __future__ import annotations

import os
import threading

from PySide6.QtWidgets import QMessageBox

from cpm_fm.gui.mw_base import MainWindowMixinBase
from cpm_fm.terminal.boot_sequence import parse_boot_sequence
from cpm_fm.terminal.cpm_parser import CPMParser
from cpm_fm.utils.i18n import tr


class _BackupRestoreMixin(MainWindowMixinBase):
    """Whole-drive Backup/Restore for :class:`~cpm_fm.app.MainWindow` (mixin).

    The Backup (remote->host) and Restore (host->remote) entry points and their
    worker loops: refresh destination + source listings, confirm the
    destructive operation (FR-152), wipe the destination (FR-153), then mirror
    every file by reusing the batch transfers (FR-154). Includes the host/remote
    listing snapshots and the per-file host-delete / remote-erase helpers. The
    generic Cancel/<accept> confirmation dialog (``_confirm_dialog``) it calls
    stays in :mod:`cpm_fm.app`.
    """

    def do_backup(self):
        """Start a whole-drive Backup (remote→host) on a worker thread.

        FR-080/CR-010: permitted only when both status flags are true. The
        worker refreshes the destination, confirms the destructive operation,
        wipes the host directory, and downloads every remote file.

        Satisfies: FR-150, FR-152, FR-154, CR-010.
        """
        if not (self.serial_mgr.terminal_connected and self.serial_mgr.transport_connected):
            QMessageBox.critical(
                self, tr("dialog.error.title"), tr("error.transport_not_connected")
            )
            return
        threading.Thread(target=self._backup_drive, daemon=True).start()

    def do_restore(self):
        """Start a whole-drive Restore (host→remote) on a worker thread.

        FR-080/CR-010: permitted only when both status flags are true. The
        worker refreshes the destination, confirms the destructive operation,
        wipes the remote drive, and uploads every host file.

        Satisfies: FR-151, FR-152, FR-154, CR-010.
        """
        if not (self.serial_mgr.terminal_connected and self.serial_mgr.transport_connected):
            QMessageBox.critical(
                self, tr("dialog.error.title"), tr("error.transport_not_connected")
            )
            return
        threading.Thread(target=self._restore_drive, daemon=True).start()

    def _backup_drive(self):
        """Worker: mirror the remote drive to the host directory (remote→host).

        FR-150/FR-152: refresh the destination (host) and source (remote)
        listings, then confirm before any deletion. FR-153: on confirmation
        delete every host file. FR-154: download every remote file by reusing
        the Copy to Host batch transfer (its progress dialog, cancel, and
        history recording). The remote listing is captured before the wipe so it
        also serves as the set of files to back up.

        Satisfies: FR-150, FR-152, FR-153, FR-154.
        """
        self.set_status(tr("status.backing_up"))
        # FR-152: refresh the destination (host) pane before prompting, and the
        # source (remote) listing that tells us what to download.
        self.transfer_completed.emit("host")  # refresh Host pane on the GUI thread
        host_files = self._host_dir_files()  # FR-152 destination snapshot to wipe
        names = self._list_remote_file_names()
        if not self._confirm_backup_restore("backup"):
            self.set_status(tr("status.backup_restore_cancelled"))
            return
        # FR-153: empty the destination first, operating on the FR-152 snapshot.
        self._wipe_host_dir(host_files)
        # Refresh the Host pane now the wipe has emptied it, so the deleted
        # files no longer linger in the list while the backup downloads.
        self.transfer_completed.emit("host")
        save_paths = [os.path.join(self.host_dir, name) for name in names]
        if not save_paths:
            # FR-154: nothing to copy; the wipe already emptied the host pane.
            self.set_status(tr("status.nothing_to_transfer"))
            self.transfer_completed.emit("host")
            return
        # FR-154: reuse the batch engine (progress dialog + cancel + history).
        self._transfer_to_host_batch(save_paths)

    def _restore_drive(self):
        """Worker: mirror the host directory to the remote drive (host→remote).

        FR-151/FR-152: snapshot the source (host) files and refresh the
        destination (remote) listing, then confirm before any deletion.
        FR-153: on confirmation delete every remote file. FR-154: upload every
        host file by reusing the Copy to Remote batch transfer (its progress
        dialog, cancel, filename validation, and history recording).

        Satisfies: FR-151, FR-152, FR-153, FR-154.
        """
        self.set_status(tr("status.restoring"))
        host_files = self._host_dir_files()
        # FR-152: refresh the destination (remote) pane before prompting; the
        # returned names are also the set of remote files to delete.
        remote_names = self._list_remote_file_names()
        if not self._confirm_backup_restore("restore"):
            self.set_status(tr("status.backup_restore_cancelled"))
            return
        # FR-153: empty the destination first.
        self._wipe_remote_drive(remote_names)
        filepaths = [os.path.join(self.host_dir, name) for name in host_files]
        if not filepaths:
            # FR-154: nothing to copy; refresh the now-empty remote pane.
            self.set_status(tr("status.nothing_to_transfer"))
            self.transfer_completed.emit("remote")
            return
        # FR-154: reuse the batch engine (progress dialog + cancel + history).
        self._transfer_to_remote_batch(filepaths)

    def _confirm_backup_restore(self, operation: str) -> bool:
        """Raise the destructive-operation confirmation and block until answered.

        Marshals the modal warning onto the GUI thread via
        ``backup_restore_confirm`` (NFR-004) and blocks this worker thread on
        ``_backup_confirm_answered`` until the GUI thread records the user's
        choice. Returns True when the user chose Continue. ``operation`` is
        "backup" or "restore" and selects the destination wording.

        Satisfies: FR-152.
        """
        self._backup_confirm_answered.clear()
        self.backup_restore_confirm.emit(operation)
        self._backup_confirm_answered.wait()
        return self._backup_confirm_result

    def _on_backup_restore_confirm(self, operation: str) -> None:
        """Show the destructive-operation warning and record the user's choice.

        Runs on the GUI thread (queued from the Backup/Restore worker). Presents
        a modal warning with Continue and Cancel (Cancel default and the
        window-manager close equivalent — the safest choice, UIR-088), stores
        the boolean result, and releases the worker by setting
        ``_backup_confirm_answered`` (NFR-004).

        Satisfies: FR-152, UIR-088.
        """
        try:
            title_key = (
                "dialog.backup_restore.backup_title"
                if operation == "backup"
                else "dialog.backup_restore.restore_title"
            )
            msg_key = (
                "dialog.backup_restore.backup"
                if operation == "backup"
                else "dialog.backup_restore.restore"
            )
            # Cancel is the safe default for a destructive operation (UIR-088).
            self._backup_confirm_result = self._confirm_dialog(
                tr(title_key),
                tr(msg_key),
                tr("button.continue"),
                warning=True,
                default_accept=False,
            )
        finally:
            self._backup_confirm_answered.set()

    def _host_dir_files(self) -> list[str]:
        """Return the names of the files (not sub-directories) in the host dir.

        Runs on a worker thread (reads the filesystem only, touches no widget).
        Returns an empty list if the directory cannot be read.

        Satisfies: FR-151, FR-153.
        """
        try:
            return [
                f
                for f in os.listdir(self.host_dir)
                if os.path.isfile(os.path.join(self.host_dir, f))
            ]
        except OSError as e:
            self._debug(f"[backup/restore] host listing failed: {e!r}")
            return []

    def _list_remote_file_names(self) -> list[str]:
        """Refresh the remote listing and return its file names (display order).

        Runs on the Backup/Restore worker thread. Reuses the FR-077–FR-079
        listing/parse mechanism synchronously (``_capture_terminal_response``
        blocks on this thread) and emits ``remote_files_ready`` so the displayed
        Remote Files list reflects the just-read contents (NFR-004, FR-152).
        Returns an empty list if nothing could be captured or parsed.

        Satisfies: FR-150, FR-151, FR-152.
        """
        try:
            cmd = self.settings.get("list_files_cmd", "DIR")
            text = self._capture_terminal_response(cmd)
            files_dict = CPMParser.parse_dir_output(text)
        except Exception as e:  # pragma: no cover - defensive
            self._debug(f"[backup/restore] remote listing failed: {e!r}")
            return []
        self.remote_files_ready.emit(files_dict)
        return list(files_dict.keys())

    def _wipe_host_dir(self, names) -> None:
        """Delete every file in the host directory (Backup destination wipe).

        Runs on the Backup worker thread. Operates on ``names`` — the host
        listing refreshed in FR-152 before the confirmation prompt — rather than
        re-reading the directory, so the wipe acts on exactly the set the user
        was warned about. A file that fails to delete is logged and skipped
        rather than aborting the wipe.

        Satisfies: FR-150, FR-153.
        """
        for name in names:
            self.set_status(tr("status.wiping_destination", name=name))
            try:
                os.remove(os.path.join(self.host_dir, name))
            except OSError as e:
                self._debug(f"[backup] failed to delete {name}: {e!r}")

    def _erase_remote_file(self, name: str) -> None:
        """Delete a single remote file before an Overwrite upload (FR-146).

        Runs on the upload worker thread. Sends the configured delete command
        (``delete_remote_cmd``, default ``ERA $1``, FR-117) on the Terminal Port
        and waits for it to go idle via the capture mechanism, so the receiver
        program is launched against a name that no longer exists. A blank delete
        command is a no-op (the upload then relies on overwrite-by-default).

        Satisfies: FR-146.
        """
        template = self.settings.get("delete_remote_cmd", "ERA $1")
        if not template:
            return
        self._capture_terminal_response(template.replace("$1", name))

    def _wipe_remote_drive(self, names) -> None:
        """Delete every named remote file (Restore destination wipe).

        Runs on the Restore worker thread. When the optional
        ``erase_all_remote_seq`` macro (UIR-107) is configured it is run **once**
        via the shared keystroke-sequence engine to clear the whole drive in a
        single operation (FR-153e) — e.g. a ``SEND ERA *.*`` / ``WAITFOR`` /
        ``SEND Y`` sequence that answers the CP/M ``ALL (Y/N)?`` prompt. When the
        macro is empty or fails to parse, the wipe falls back to sending the
        configured delete command (``delete_remote_cmd``, default ``ERA $1``,
        FR-117) once per file, waiting for each to go idle via the capture
        mechanism; deleting per file avoids the interactive ``ERA *.*``
        confirmation on the CP/M side.

        Satisfies: FR-151, FR-153, FR-153e.
        """
        # FR-153e: a configured erase-all macro clears the drive in one call.
        seq = self.settings.get("erase_all_remote_seq", "")
        if seq.strip():
            try:
                steps = parse_boot_sequence(seq)
            except ValueError as e:
                # Malformed sequence: fall back to the per-file wipe (FR-153e)
                # rather than leaving the drive un-erased.
                self._debug(f"[restore] erase-all sequence parse failed, using per-file: {e!r}")
            else:
                self.set_status(tr("status.wiping_destination", name="*.*"))
                self._execute_sequence(steps)
                return
        # FR-153c/FR-153d: per-file deletion (default when no macro configured).
        template = self.settings.get("delete_remote_cmd", "ERA $1")
        if not template:
            return
        for name in names:
            self.set_status(tr("status.wiping_destination", name=name))
            self._capture_terminal_response(template.replace("$1", name))
