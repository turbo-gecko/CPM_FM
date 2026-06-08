from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QProgressBar,
    QVBoxLayout,
)


class TransferProgressDialog(QDialog):
    """
    Modal progress dialog shown during an X-Modem file transfer (SRS
    docs/cpm_fm_requirements.md, FR-105, UIR-051).

    Displays the filename and a running blocks/bytes count that the owner
    updates after each transferred block (via :meth:`update_progress`). When the
    file size is known (host-to-remote sends) a determinate progress bar is
    shown; for receives, where X-Modem carries no length, the bar is left
    indeterminate. The owning MainWindow closes the dialog when the transfer
    completes (success or failure) — it does not close itself.
    """

    def __init__(self, parent, direction: str, filename: str, total_bytes: int | None):
        super().__init__(parent)
        self._total_bytes = total_bytes if total_bytes and total_bytes > 0 else None

        verb = "Sending" if direction == "remote" else "Receiving"
        self.setWindowTitle(f"{verb} File")
        self.setModal(True)
        # No close button / context-help: the transfer owns this dialog's
        # lifetime and closes it automatically (FR-105).
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)

        layout = QVBoxLayout(self)

        self.file_label = QLabel(f"{verb}: {filename}")
        layout.addWidget(self.file_label)

        self.count_label = QLabel("Blocks: 0    Bytes: 0")
        layout.addWidget(self.count_label)

        self.progress_bar = QProgressBar()
        if self._total_bytes is not None:
            self.progress_bar.setRange(0, self._total_bytes)
            self.progress_bar.setValue(0)
        else:
            # Unknown total — indeterminate "busy" bar (UIR-051).
            self.progress_bar.setRange(0, 0)
        layout.addWidget(self.progress_bar)

        self.resize(360, 120)

    def update_progress(self, blocks: int, bytes_done: int) -> None:
        """Refresh the blocks/bytes display after a transferred block (FR-105)."""
        self.count_label.setText(f"Blocks: {blocks}    Bytes: {bytes_done}")
        if self._total_bytes is not None:
            self.progress_bar.setValue(min(bytes_done, self._total_bytes))
