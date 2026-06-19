from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from cpm_fm.terminal.cpm_parser import CPMParser
from cpm_fm.utils.i18n import tr

# Actions returned by FilenameValidationDialog (FR-149). The SKIP/CANCEL string
# values match those of gui.conflict_dialog so the transfer batch loop and the
# transfer history treat a skip/cancel identically regardless of which prompt
# produced it.
RENAME = "rename"
SKIP = "skip"
CANCEL = "cancel"


class FilenameValidationDialog(QDialog):
    """
    Modal dialog shown before a host→remote upload when the file's name does not
    meet the CP/M 8.3 naming convention (SRS docs/cpm_fm_requirements.md,
    UIR-085).

    It names the offending file, explains the convention, and offers an editable
    field (pre-filled with a conforming suggestion) plus three buttons —
    **Rename**, **Skip**, and **Cancel**. Rename is accepted only once the
    entered name is itself a valid CP/M 8.3 name (:meth:`CPMParser.is_valid_8_3`);
    until then an inline error is shown and the dialog stays open. After
    :meth:`exec` returns, the caller reads :attr:`action` (one of
    RENAME/SKIP/CANCEL) and, for RENAME, :attr:`new_name`. There is no window
    manual-close control; closing via the window manager is treated as Cancel.

    Satisfies: FR-148, FR-149, UIR-085.
    """

    def __init__(self, parent, filename: str, suggested: str):
        """
        Satisfies: FR-148, FR-149, UIR-085.
        """
        super().__init__(parent)
        self.action: str = CANCEL
        self.new_name: str = ""

        self.setWindowTitle(tr("dialog.invalid_name.title"))
        self.setModal(True)
        # A deliberate three-way choice; a window-manager close is Cancel.
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)

        layout = QVBoxLayout(self)

        message = QLabel(tr("dialog.invalid_name.message", name=filename))
        message.setWordWrap(True)
        layout.addWidget(message)

        self._name_edit = QLineEdit(suggested)
        self._name_edit.selectAll()
        layout.addWidget(self._name_edit)

        # Inline validation feedback, shown only when a Rename attempt is still
        # not a valid CP/M 8.3 name.
        self._error = QLabel("")
        self._error.setWordWrap(True)
        self._error.setStyleSheet("color: #f44336;")
        layout.addWidget(self._error)

        # Button row: Cancel far left, then Skip and Rename to the right (Rename
        # is the affirmative action, placed last).
        self._rename_btn = QPushButton(tr("dialog.invalid_name.rename"))
        self._skip_btn = QPushButton(tr("dialog.invalid_name.skip"))
        self._cancel_btn = QPushButton(tr("dialog.invalid_name.cancel"))
        self._rename_btn.clicked.connect(self._on_rename)
        self._skip_btn.clicked.connect(lambda: self._choose(SKIP))
        self._cancel_btn.clicked.connect(lambda: self._choose(CANCEL))
        self._rename_btn.setDefault(True)

        row = QHBoxLayout()
        row.addWidget(self._cancel_btn)
        row.addStretch()
        row.addWidget(self._skip_btn)
        row.addWidget(self._rename_btn)
        layout.addLayout(row)

        self.resize(420, 180)

    def _on_rename(self) -> None:
        """Validate the entered name and accept it, or show an inline error.

        Satisfies: FR-149.
        """
        candidate = self._name_edit.text().strip()
        if not CPMParser.is_valid_8_3(candidate):
            self._error.setText(tr("dialog.invalid_name.still_invalid"))
            return
        self.action = RENAME
        self.new_name = candidate
        self.accept()

    def _choose(self, action: str) -> None:
        """Record a Skip/Cancel choice and close.

        Satisfies: FR-149.
        """
        self.action = action
        self.accept()

    def reject(self) -> None:
        """Treat a window-manager close (Esc / close box) as Cancel (UIR-085).

        Satisfies: FR-149, UIR-085.
        """
        self.action = CANCEL
        super().reject()
