from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from cpm_fm.gui.dialog_buttons import build_button_row


class TransferProgressDialog(QDialog):
    """
    Modal progress dialog shown during an X-Modem file transfer (SRS
    docs/cpm_fm_requirements.md).

    A single dialog serves a whole transfer batch: it is created
    when the batch begins, switched to each file via :meth:`set_file`, and shows
    the batch position ("File i of N") when more than one file is transferred.
    For each file it displays the filename and a running blocks/bytes count that
    the owner updates after each transferred block (via :meth:`update_progress`).
    When the file size is known (host-to-remote sends) a determinate progress bar
    is shown; for receives, where X-Modem carries no length, the bar is left
    indeterminate. The owning MainWindow closes the dialog when the batch
    completes (success, failure, or cancellation) — it does not close itself.

    A centred Cancel button (FR-120) requests cancellation of the transfer via
    the supplied ``cancel_callback``; once pressed it disables itself and shows
    "Cancelling…" until the owner tears the dialog down.

    Satisfies: FR-105, FR-120, UIR-051.
    """

    def __init__(
        self,
        parent,
        direction: str,
        file_count: int,
        cancel_callback: Callable[[], None] | None = None,
    ):
        """
        Satisfies: FR-105, FR-120, UIR-051.
        """
        super().__init__(parent)
        self._file_count = max(1, file_count)
        self._total_bytes: int | None = None
        self._cancel_callback = cancel_callback

        verb = "Sending" if direction == "remote" else "Receiving"
        self.setWindowTitle(f"{verb} File")
        self.setModal(True)
        # No close button / context-help: the transfer owns this dialog's
        # lifetime and closes it automatically (FR-105).
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        self._verb = verb

        layout = QVBoxLayout(self)

        # UIR-051: batch-position label, shown only for multi-file batches.
        self.batch_label = QLabel("")
        self.batch_label.setVisible(self._file_count > 1)
        layout.addWidget(self.batch_label)

        self.file_label = QLabel(f"{verb}:")
        layout.addWidget(self.file_label)

        self.count_label = QLabel("Blocks: 0    Bytes: 0")
        layout.addWidget(self.count_label)

        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)

        # FR-120/UIR-051: centred Cancel button to request cancellation.
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self._on_cancel_clicked)
        layout.addLayout(build_button_row(reject_button=self.cancel_button))

        self.resize(360, 160)

    def _on_cancel_clicked(self) -> None:
        """Request cancellation and show that it is in progress.

        Satisfies: FR-120, UIR-051.
        """
        self.mark_cancelling()
        if self._cancel_callback is not None:
            self._cancel_callback()

    def mark_cancelling(self) -> None:
        """Disable the Cancel button and indicate cancellation is underway.

        Satisfies: FR-120, UIR-051.
        """
        self.cancel_button.setEnabled(False)
        self.cancel_button.setText("Cancelling…")

    def set_file(self, filename: str, total_bytes: int | None, index: int) -> None:
        """Switch the dialog to the file at 1-based position `index`.

        Updates the batch-position and filename labels, resets the blocks/bytes
        count, and reconfigures the progress bar: determinate against the file
        size when known (sends), indeterminate when not (receives).

        Satisfies: FR-105, FR-107, UIR-051.
        """
        self._total_bytes = total_bytes if total_bytes and total_bytes > 0 else None
        if self._file_count > 1:
            self.batch_label.setText(f"File {index} of {self._file_count}")
        self.file_label.setText(f"{self._verb}: {filename}")
        self.count_label.setText("Blocks: 0    Bytes: 0")
        if self._total_bytes is not None:
            self.progress_bar.setRange(0, self._total_bytes)
            self.progress_bar.setValue(0)
        else:
            # Unknown total — indeterminate "busy" bar (UIR-051).
            self.progress_bar.setRange(0, 0)

    def update_progress(self, blocks: int, bytes_done: int) -> None:
        """Refresh the blocks/bytes display after a transferred block.

        Satisfies: FR-105.
        """
        self.count_label.setText(f"Blocks: {blocks}    Bytes: {bytes_done}")
        if self._total_bytes is not None:
            self.progress_bar.setValue(min(bytes_done, self._total_bytes))
