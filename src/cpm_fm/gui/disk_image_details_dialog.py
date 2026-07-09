"""Image Details dialog — read-only view of a CP/M disk image's files.

Presents the CP/M-specific metadata (name, size in bytes, user number, and the
read-only/system/archive attribute flags) of the currently open disk image —
metadata the extracted plain host files no longer carry (FR-173, UIR-109). The
dialog is modal and read-only and resolves its text via :func:`tr` at build time
(FR-121). No CP/M-filesystem logic lives here: it only renders the
:class:`~cpm_fm.utils.disk_image.CpmFileEntry` list captured at open time, so the
filesystem logic stays in the GUI-free ``utils/`` layer (CR-014).

Satisfies: FR-173, UIR-109.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHeaderView,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from cpm_fm.gui.dialog_buttons import build_button_row
from cpm_fm.utils.i18n import tr

if TYPE_CHECKING:
    from cpm_fm.utils.disk_image import CpmFileEntry

# UIR-109: the column order of the details table (i18n keys for the headers).
_COLUMN_KEYS = (
    "dialog.image_details.col.name",
    "dialog.image_details.col.size",
    "dialog.image_details.col.user",
    "dialog.image_details.col.attrs",
)


def _attr_text(entry: CpmFileEntry) -> str:
    """Render an entry's read-only/system/archive flags as a compact string (FR-173).

    The CP/M attribute mnemonics R/S/A are not translated; an entry with no flags
    set shows a dash.

    Satisfies: FR-173.
    """
    flags = [
        "R" if entry.read_only else "",
        "S" if entry.system else "",
        "A" if entry.archive else "",
    ]
    return " ".join(f for f in flags if f) or "-"


class DiskImageDetailsDialog(QDialog):
    """Modal, read-only table of the currently open image's files (FR-173, UIR-109).

    Satisfies: FR-173, UIR-109.
    """

    def __init__(self, parent, files: list[CpmFileEntry]) -> None:
        """
        Satisfies: FR-173, UIR-109, FR-121.
        """
        super().__init__(parent)
        self.setWindowTitle(tr("dialog.image_details.title"))
        self.setModal(True)
        self.resize(480, 360)
        self._build_widgets(files)

    def _build_widgets(self, files: list[CpmFileEntry]) -> None:
        """Build the read-only table and a centred Close button.

        Satisfies: FR-173, UIR-109.
        """
        layout = QVBoxLayout(self)

        table = QTableWidget(len(files), len(_COLUMN_KEYS))
        table.setHorizontalHeaderLabels([tr(k) for k in _COLUMN_KEYS])
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.verticalHeader().setVisible(False)
        for row, entry in enumerate(files):
            cells = (entry.name, str(entry.size_bytes), str(entry.user), _attr_text(entry))
            for col, text in enumerate(cells):
                table.setItem(row, col, QTableWidgetItem(text))
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)  # name takes the slack
        layout.addWidget(table)

        close_btn = QPushButton(tr("dialog.image_details.close"))
        close_btn.setDefault(True)
        close_btn.clicked.connect(self.accept)
        layout.addLayout(build_button_row(accept_button=close_btn))
