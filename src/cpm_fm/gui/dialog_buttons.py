from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QPushButton


def build_button_row(
    accept_button: QPushButton | None = None,
    reject_button: QPushButton | None = None,
) -> QHBoxLayout:
    """Lay out a dialog's confirm/cancel buttons per the house convention.

    When both buttons are present, the Cancel (reject) button is placed at the
    far left and the affirmative (accept) button at the far right, with a
    flexible stretch between them. When only one button is present, it is
    horizontally centred.

    Callers create and connect the QPushButtons themselves; this helper only
    arranges them. Returns the populated QHBoxLayout to add to the dialog.

    Satisfies: UIR-075.
    """
    row = QHBoxLayout()
    if accept_button is not None and reject_button is not None:
        # Cancel far left, Apply/Save far right.
        row.addWidget(reject_button)
        row.addStretch()
        row.addWidget(accept_button)
    else:
        # A single button is centred between two stretches.
        only = accept_button if accept_button is not None else reject_button
        row.addStretch()
        if only is not None:
            row.addWidget(only)
        row.addStretch()
    return row
