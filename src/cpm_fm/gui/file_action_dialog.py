from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from cpm_fm.gui.dialog_buttons import build_button_row


class FileActionDialog(QDialog):
    """Modal dialog for the Rename and Delete file actions.

    Presents a single-line filename field pre-populated with the target file's
    name, an Apply button, and a Cancel button (UIR-057). For Rename the field
    is editable (and pre-selected for quick replacement); for Delete it is
    read-only and merely confirms the file to be removed.

    Satisfies: FR-114, FR-115, UIR-057.
    """

    def __init__(
        self,
        parent,
        title: str,
        filename: str,
        editable: bool = True,
        prompt: str | None = None,
    ):
        """
        Satisfies: FR-114, FR-115, UIR-057, UIR-075.
        """
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)

        layout = QVBoxLayout(self)
        if prompt:
            layout.addWidget(QLabel(prompt))

        self.name_edit = QLineEdit(filename)
        self.name_edit.setReadOnly(not editable)
        if editable:
            # Pre-select so the user can immediately type a replacement name.
            self.name_edit.selectAll()
        layout.addWidget(self.name_edit)

        # UIR-057/UIR-075: Apply confirms the action; Cancel makes no change.
        # Cancel sits at the far left, Apply at the far right.
        apply_btn = QPushButton("Apply")
        apply_btn.setDefault(True)
        apply_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        layout.addLayout(build_button_row(accept_button=apply_btn, reject_button=cancel_btn))

    def value(self) -> str:
        """
        The (possibly edited) filename entered by the user.

        Satisfies: FR-114.
        """
        return self.name_edit.text()
