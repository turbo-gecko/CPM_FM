from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from cpm_fm.utils.i18n import tr


class RemoteUnavailableDialog(QDialog):
    """Modal dialog shown when the post-connect probe cannot reach the remote
    file system (FR-044).

    Informs the user that the remote computer's file system cannot be accessed
    and offers three actions whose buttons are laid out in the fixed
    left-to-right order **Abort**, **Continue**, **Terminal** (UIR-092). The
    chosen action is reported via :attr:`choice`, one of :data:`ABORT`,
    :data:`CONTINUE`, :data:`TERMINAL`; closing the dialog (Esc / window close)
    leaves the safe default of :data:`CONTINUE` (take no action).

    Satisfies: FR-044, FR-045, UIR-092.
    """

    ABORT = "abort"
    CONTINUE = "continue"
    TERMINAL = "terminal"

    def __init__(self, parent):
        """
        Satisfies: FR-044, FR-045, UIR-092.
        """
        super().__init__(parent)
        self.setWindowTitle(tr("dialog.remote_unavailable.title"))
        self.setModal(True)
        # Safe default if the dialog is dismissed without a button (Esc / close).
        self.choice = self.CONTINUE

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("dialog.remote_unavailable.body")))

        # UIR-092: exactly three buttons in the fixed left-to-right order
        # Abort, Continue, Terminal. This fixed order is intentional and
        # overrides the two-button house convention (UIR-075), so the row is
        # built explicitly rather than through build_button_row.
        abort_btn = QPushButton(tr("button.abort"))
        continue_btn = QPushButton(tr("button.continue"))
        terminal_btn = QPushButton(tr("button.terminal"))
        abort_btn.clicked.connect(self._choose(self.ABORT))
        continue_btn.clicked.connect(self._choose(self.CONTINUE))
        terminal_btn.clicked.connect(self._choose(self.TERMINAL))
        continue_btn.setDefault(True)

        row = QHBoxLayout()
        row.addWidget(abort_btn)
        row.addStretch()
        row.addWidget(continue_btn)
        row.addWidget(terminal_btn)
        layout.addLayout(row)

    def _choose(self, value: str):
        """Return a click handler that records ``value`` and closes the dialog.

        Satisfies: FR-045.
        """

        def handler():
            self.choice = value
            self.accept()

        return handler
