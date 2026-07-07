from __future__ import annotations

import os
import threading

from PySide6.QtWidgets import QMessageBox

from cpm_fm.gui.mw_base import MainWindowMixinBase
from cpm_fm.gui.transfer_history_dialog import TransferHistoryDialog
from cpm_fm.utils.i18n import tr


class _HistoryMixin(MainWindowMixinBase):
    """Transfer-history recording and the history dialog for MainWindow (mixin).

    Records each file's transfer outcome in the persistent history (FR-140/142/
    144), opens the non-modal Transfer History window (FR-143), and re-initiates
    a transfer from a selected history entry by reusing the batch transfers
    (FR-144). The file-size helper used when recording a download lives here too.
    """

    @staticmethod
    def _file_size(path: str) -> int:
        """Return the size of ``path`` in bytes, or 0 if it cannot be read.

        Satisfies: FR-140, FR-142.
        """
        try:
            return os.path.getsize(path)
        except OSError:
            return 0

    def _record_history(
        self,
        filename: str,
        path: str,
        direction: str,
        status: str,
        size: int,
        error: str,
        retry: bool,
    ) -> None:
        """Record one file's transfer outcome in the persistent history.

        Called from the transfer worker threads (FR-142); the underlying store
        is thread-safe so no Qt-signal marshalling is needed here. A history
        write failure must never abort a transfer, so any error is swallowed.

        Satisfies: FR-140, FR-142, FR-144.
        """
        try:
            self.transfer_history.add_entry(
                filename=filename,
                path=path,
                direction=direction,
                status=status,
                size=size,
                error=error,
                retry=retry,
            )
        except Exception as e:  # pragma: no cover - defensive
            self._debug(f"[history] failed to record entry: {e!r}")

    def show_history(self):
        """Open (or re-raise) the non-modal Transfer History window (UIR-082).

        Runs on the GUI thread. The window is reused across invocations: if it is
        already open it is raised and activated rather than opening a second copy
        (mirrors the Manual viewer). Being non-modal (UIR-083) it can be left open
        alongside the other windows and restored on start-up (FR-168). Re-transfer
        records the chosen entry on ``retransfer_entry`` and closes the dialog; the
        ``finished`` handler then starts the transfer, so it (and its own modal
        progress dialog) begins only after this window has closed (FR-144).

        Satisfies: FR-143, FR-144, UIR-082, FR-168.
        """
        existing = self._history_dialog
        if existing is not None and existing.isVisible():
            existing.raise_()
            existing.activateWindow()
            return
        dlg = TransferHistoryDialog(self, self.transfer_history, self.window_state)
        self._history_dialog = dlg
        dlg.finished.connect(self._on_history_finished)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _on_history_finished(self, _result: int) -> None:
        """Start a re-transfer requested from the (now closed) history window.

        Invoked from the dialog's ``finished`` signal so the re-transfer — and its
        own modal progress dialog — starts only after the non-modal history window
        has closed (FR-144).

        Satisfies: FR-144.
        """
        dlg = self._history_dialog
        if dlg is None or dlg.retransfer_entry is None:
            return
        entry = dlg.retransfer_entry
        dlg.retransfer_entry = None
        self._retransfer(entry)

    def _retransfer(self, entry: dict):
        """Re-initiate the transfer described by a history ``entry`` (FR-144).

        Restores the file path and direction from the entry and reuses the
        existing batch transfer flow, recording the new attempt as a re-transfer
        (``retry=True``). A transfer is permitted only when both status flags are
        true (FR-080/CR-010); an upload additionally requires the source host
        file to still exist.

        Satisfies: FR-144, FR-080, CR-010.
        """
        if not (self.serial_mgr.terminal_connected and self.serial_mgr.transport_connected):
            QMessageBox.critical(
                self,  # type: ignore[arg-type]  # mixin is a QMainWindow at runtime
                tr("dialog.error.title"),
                tr("error.transport_not_connected"),
            )
            return
        path = entry.get("path", "")
        direction = entry.get("direction")
        if direction == "remote":
            # Upload: the source host file must still exist to re-send it.
            if not path or not os.path.isfile(path):
                QMessageBox.critical(
                    self,  # type: ignore[arg-type]  # mixin is a QMainWindow at runtime
                    tr("dialog.error.title"),
                    tr("error.retransfer_file_missing", path=path),
                )
                return
            threading.Thread(
                target=self._transfer_to_remote_batch,
                args=([path],),
                kwargs={"retry": True},
                daemon=True,
            ).start()
        elif direction == "host":
            # Download: re-receive into the same host path (its base name is the
            # remote file name PCPUT will be asked for).
            if not path:
                return
            threading.Thread(
                target=self._transfer_to_host_batch,
                args=([path],),
                kwargs={"retry": True},
                daemon=True,
            ).start()
