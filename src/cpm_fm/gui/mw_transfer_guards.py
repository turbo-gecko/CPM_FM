from __future__ import annotations

import os

from cpm_fm.gui.conflict_dialog import CANCEL, FileConflictDialog
from cpm_fm.gui.filename_validation_dialog import FilenameValidationDialog
from cpm_fm.gui.mw_base import MainWindowMixinBase
from cpm_fm.terminal.cpm_parser import CPMParser


class _TransferGuardsMixin(MainWindowMixinBase):
    """Pre-send guards for :class:`~cpm_fm.app.MainWindow` (mixin).

    Destination-conflict detection/resolution (FR-145-FR-147) and CP/M 8.3
    name validation (FR-148/FR-149): the worker-thread checks and the modal
    GUI-thread dialogs they raise, marshalled via signals (NFR-004). Invoked by
    the batch drivers in :mod:`cpm_fm.gui.mw_transfer_batches`.
    """

    def _fresh_remote_names(self) -> set[str]:
        """Refresh the remote directory listing and return its names, upper-cased.

        Runs on the upload worker thread (FR-145). Reuses the FR-077–FR-079
        listing/parse mechanism synchronously (``_capture_terminal_response``
        blocks on this thread), and also emits ``remote_files_ready`` so the
        displayed Remote Files list reflects the just-read contents (NFR-004).
        Returns an empty set if nothing could be captured/parsed, in which case
        the caller detects no conflicts and uploads proceed as before.

        Satisfies: FR-145.
        """
        try:
            cmd = self.settings.get("list_files_cmd", "DIR")
            # FR-120: cancellable so a Cancel during the pre-upload listing wakes
            # the upload worker promptly; the batch loop then aborts at its top.
            text = self._capture_terminal_response(cmd, cancellable=True)
            files_dict = CPMParser.parse_dir_output(text)
        except Exception as e:  # pragma: no cover - defensive
            self._debug(f"[conflict] remote refresh failed: {e!r}")
            return set()
        # Mirror _do_refresh_remote_logic: update the on-screen list too.
        self.remote_files_ready.emit(files_dict)
        return {name.upper() for name in files_dict}

    @staticmethod
    def _destination_conflict(
        direction: str, path: str, remote_names: set[str], dest_name: str | None = None
    ) -> bool:
        """Whether a file of this name already exists at the destination (FR-145).

        For a download (``host``) the destination is the host filesystem, so the
        check is ``os.path.exists``. For an upload (``remote``) the destination
        is the remote drive, so the destination name (upper-cased — CP/M is
        upper-case 8.3) is checked against ``remote_names`` (the fresh listing).
        ``dest_name`` overrides the name checked for an upload; it is the
        effective remote name, which differs from the host base name when the
        file was renamed to satisfy the CP/M 8.3 convention (FR-149). When
        omitted the host base name is used.

        Satisfies: FR-145, FR-149.
        """
        if direction == "host":
            return os.path.exists(path)
        name = dest_name if dest_name is not None else os.path.basename(path)
        return name.upper() in remote_names

    def _resolve_conflict(self, name: str, direction: str) -> str:
        """Decide how to handle a destination conflict for ``name`` (FR-146/FR-147).

        Returns one of OVERWRITE / SKIP / CANCEL. Honours the batch-wide policy
        (FR-147) without prompting when one is in effect; otherwise raises the
        modal dialog on the GUI thread via ``conflict_detected`` and blocks this
        worker thread until the user answers (NFR-004). When the user ticks
        "apply to all", the chosen Overwrite/Skip becomes the batch policy.

        Satisfies: FR-146, FR-147.
        """
        if self._conflict_policy is not None:
            return self._conflict_policy
        action, apply_to_all = self._prompt_conflict(name, direction)
        if apply_to_all and action != CANCEL:
            self._conflict_policy = action
        return action

    def _prompt_conflict(self, name: str, direction: str) -> tuple[str, bool]:
        """Raise the conflict dialog on the GUI thread and block until answered.

        Marshals the modal dialog onto the GUI thread via ``conflict_detected``
        (NFR-004) and blocks this worker thread on ``_conflict_answered`` until
        the GUI thread records the user's (action, apply_to_all) choice. Split
        from :meth:`_resolve_conflict` so the batch-wide policy logic can be
        tested without the Qt signal/thread round-trip.

        Satisfies: FR-146, FR-147.
        """
        self._conflict_answered.clear()
        self.conflict_detected.emit(name, direction)
        self._conflict_answered.wait()
        return self._conflict_result

    def _on_conflict_detected(self, name: str, direction: str) -> None:
        """Show the modal conflict dialog and record the user's choice (FR-146).

        Runs on the GUI thread (queued from the transfer worker). Stores
        (action, apply_to_all) in ``_conflict_result`` and releases the worker
        by setting ``_conflict_answered`` (NFR-004).

        Satisfies: FR-146, FR-147, UIR-084.
        """
        try:
            dialog = FileConflictDialog(self, name, direction)
            dialog.exec()
            self._conflict_result = (dialog.action, dialog.apply_to_all)
        finally:
            self._conflict_answered.set()

    def _prompt_invalid_name(self, name: str) -> tuple[str, str]:
        """Raise the CP/M 8.3 name-validation dialog and block until answered.

        Marshals the modal dialog onto the GUI thread via
        ``invalid_name_detected`` (NFR-004) and blocks this upload worker thread
        on ``_invalid_name_answered`` until the GUI thread records the user's
        (action, new_name) choice. Split out so the batch loop's handling of the
        result can be tested without the Qt signal/thread round-trip.

        Satisfies: FR-148, FR-149.
        """
        self._invalid_name_answered.clear()
        self.invalid_name_detected.emit(name)
        self._invalid_name_answered.wait()
        return self._invalid_name_result

    def _on_invalid_name_detected(self, name: str) -> None:
        """Show the modal name-validation dialog and record the user's choice.

        Runs on the GUI thread (queued from the upload worker). Pre-fills the
        rename field with a CP/M 8.3-conforming suggestion (FR-149), stores
        (action, new_name) in ``_invalid_name_result``, and releases the worker
        by setting ``_invalid_name_answered`` (NFR-004).

        Satisfies: FR-148, FR-149, UIR-085.
        """
        try:
            suggested = CPMParser.suggest_8_3(name)
            dialog = FilenameValidationDialog(self, name, suggested)
            dialog.exec()
            self._invalid_name_result = (dialog.action, dialog.new_name)
        finally:
            self._invalid_name_answered.set()
