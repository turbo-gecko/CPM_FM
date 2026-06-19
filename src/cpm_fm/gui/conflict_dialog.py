from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from cpm_fm.utils.i18n import tr

# Conflict-resolution actions returned by FileConflictDialog (FR-146/FR-147).
OVERWRITE = "overwrite"
SKIP = "skip"
CANCEL = "cancel"


class FileConflictDialog(QDialog):
    """
    Modal dialog shown when a file being transferred already exists at the
    destination (SRS docs/cpm_fm_requirements.md, UIR-084).

    It names the conflicting file and offers the standard operating-system
    file-copy choices — Overwrite, Skip, or Cancel — plus an "apply to all
    remaining conflicts" checkbox (FR-147) so the chosen Overwrite/Skip action
    can be remembered for the rest of the batch. After :meth:`exec` returns, the
    caller reads :attr:`action` (one of OVERWRITE/SKIP/CANCEL) and
    :attr:`apply_to_all`. There is no window close control; closing via the
    window manager is treated as Cancel — the safest default.

    Satisfies: FR-146, FR-147, UIR-084.
    """

    def __init__(self, parent, filename: str, direction: str):
        """
        Satisfies: FR-146, FR-147, UIR-084.

        ``direction`` is "remote" (host→remote upload) or "host" (remote→host
        download); it selects the destination wording in the message.
        """
        super().__init__(parent)
        self.action: str = CANCEL
        self.apply_to_all: bool = False

        self.setWindowTitle(tr("dialog.conflict.title"))
        self.setModal(True)
        # The dialog owns a deliberate three-way choice; no manual-close control,
        # and a window-manager close is equivalent to Cancel (UIR-084).
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)

        layout = QVBoxLayout(self)

        dest_key = (
            "dialog.conflict.dest.remote" if direction == "remote" else "dialog.conflict.dest.host"
        )
        message = QLabel(tr("dialog.conflict.message", name=filename, dest=tr(dest_key)))
        message.setWordWrap(True)
        layout.addWidget(message)

        self._apply_all_check = QCheckBox(tr("dialog.conflict.apply_all"))
        layout.addWidget(self._apply_all_check)

        # Button row: Cancel far left, then Skip and Overwrite to the right
        # (Overwrite is the affirmative action, placed last).
        self._overwrite_btn = QPushButton(tr("dialog.conflict.overwrite"))
        self._skip_btn = QPushButton(tr("dialog.conflict.skip"))
        self._cancel_btn = QPushButton(tr("dialog.conflict.cancel"))
        self._overwrite_btn.clicked.connect(lambda: self._choose(OVERWRITE))
        self._skip_btn.clicked.connect(lambda: self._choose(SKIP))
        self._cancel_btn.clicked.connect(lambda: self._choose(CANCEL))
        self._overwrite_btn.setDefault(True)

        row = QHBoxLayout()
        row.addWidget(self._cancel_btn)
        row.addStretch()
        row.addWidget(self._skip_btn)
        row.addWidget(self._overwrite_btn)
        layout.addLayout(row)

        self.resize(380, 150)

    def _choose(self, action: str) -> None:
        """Record the chosen action and whether to apply it to all, then close.

        Satisfies: FR-146, FR-147.
        """
        self.action = action
        # Cancel ends the batch outright, so the "apply to all" flag is moot.
        self.apply_to_all = action != CANCEL and self._apply_all_check.isChecked()
        self.accept()

    def reject(self) -> None:
        """Treat a window-manager close (Esc / close box) as Cancel (UIR-084).

        Satisfies: FR-146, UIR-084.
        """
        self.action = CANCEL
        self.apply_to_all = False
        super().reject()
