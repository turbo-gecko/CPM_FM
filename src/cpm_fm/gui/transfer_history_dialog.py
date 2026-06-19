"""Transfer History dialog (Feature 2).

A modal dialog presenting the persisted file-transfer history
(:class:`~cpm_fm.utils.transfer_history.TransferHistory`) in a table, with
filter controls (by direction and status), and actions to re-transfer a
selected entry, export the history, or clear it. Like the other on-demand
dialogs it resolves its text via :func:`tr` at build time (FR-121) and persists
its geometry through the injected :class:`WindowState` (FR-004).

Re-transfer does not start the transfer itself: clicking **Re-transfer** records
the chosen entry on :attr:`retransfer_entry` and accepts (closes) the dialog, so
the owning :class:`MainWindow` can start the transfer — and show its modal
progress dialog — only once this dialog has closed.

Satisfies: FR-143, FR-144, UIR-082, UIR-083.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from cpm_fm.utils.i18n import tr

if TYPE_CHECKING:
    from cpm_fm.gui.window_state import WindowState
    from cpm_fm.utils.transfer_history import TransferHistory

# UIR-083: the column order of the history table. Each tuple is (i18n key for
# the header, entry-field name used to populate the cell).
_COLUMNS = (
    ("history.col.time", "timestamp"),
    ("history.col.file", "filename"),
    ("history.col.direction", "direction"),
    ("history.col.status", "status"),
    ("history.col.size", "size"),
    ("history.col.error", "error"),
)


class TransferHistoryDialog(QDialog):
    """Modal dialog showing and acting on the transfer history (Feature 2).

    Satisfies: FR-143, FR-144, UIR-082, UIR-083.
    """

    def __init__(
        self,
        parent,
        history: TransferHistory,
        window_state: WindowState | None = None,
    ) -> None:
        """
        Satisfies: FR-143, UIR-082, UIR-083, FR-004.
        """
        super().__init__(parent)
        self._history = history
        self._window_state = window_state
        self._state_key = "transfer_history"
        # FR-144: set to the selected entry when Re-transfer is clicked; read by
        # the owner after the dialog closes to start the re-transfer.
        self.retransfer_entry: dict[str, Any] | None = None

        self.setWindowTitle(tr("history.title"))
        self.setModal(True)
        self.resize(720, 420)

        self._build_widgets()
        self._reload()

        if window_state is not None:
            window_state.restore_geometry(self._state_key, self)

    def done(self, result: int) -> None:
        """Persist geometry on every close path before the modal exec returns.

        Satisfies: FR-004.
        """
        if self._window_state is not None:
            self._window_state.save_geometry(self._state_key, self)
        super().done(result)

    # ------------------------------------------------------------------ build

    def _build_widgets(self) -> None:
        """
        Satisfies: UIR-083.
        """
        layout = QVBoxLayout(self)

        # UIR-083: a filter row (direction + status) above the table. The combo
        # *labels* are translated; the underlying filter values are the semantic
        # keys (CR-015), carried as userData.
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel(tr("history.filter.direction")))
        self._direction_filter = QComboBox()
        self._direction_filter.addItem(tr("history.filter.all"), "")
        self._direction_filter.addItem(tr("history.dir.remote"), "remote")
        self._direction_filter.addItem(tr("history.dir.host"), "host")
        self._direction_filter.currentIndexChanged.connect(self._reload)
        filter_row.addWidget(self._direction_filter)
        filter_row.addSpacing(12)
        filter_row.addWidget(QLabel(tr("history.filter.status")))
        self._status_filter = QComboBox()
        self._status_filter.addItem(tr("history.filter.all"), "")
        self._status_filter.addItem(tr("history.status.success"), "success")
        self._status_filter.addItem(tr("history.status.failure"), "failure")
        self._status_filter.addItem(tr("history.status.cancelled"), "cancelled")
        self._status_filter.currentIndexChanged.connect(self._reload)
        filter_row.addWidget(self._status_filter)
        filter_row.addStretch()
        layout.addLayout(filter_row)

        # UIR-083: the history table — read-only, one row per entry, whole-row
        # single selection (a re-transfer acts on one entry).
        self._table = QTableWidget(0, len(_COLUMNS))
        self._table.setHorizontalHeaderLabels([tr(key) for key, _ in _COLUMNS])
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setSortingEnabled(True)
        self._table.verticalHeader().setVisible(False)
        header = self._table.horizontalHeader()
        # The error column takes the slack; the rest size to content.
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(len(_COLUMNS) - 1, QHeaderView.ResizeMode.Stretch)
        self._table.itemSelectionChanged.connect(self._update_buttons)
        layout.addWidget(self._table)

        # UIR-083: action buttons. Re-transfer / Export / Clear on the left;
        # Close on the far right (the dialog-dismiss button).
        btn_row = QHBoxLayout()
        self._retransfer_btn = QPushButton(tr("history.button.retransfer"))
        self._retransfer_btn.clicked.connect(self._on_retransfer)
        btn_row.addWidget(self._retransfer_btn)
        self._export_btn = QPushButton(tr("history.button.export"))
        self._export_btn.clicked.connect(self._on_export)
        btn_row.addWidget(self._export_btn)
        self._clear_btn = QPushButton(tr("history.button.clear"))
        self._clear_btn.clicked.connect(self._on_clear)
        btn_row.addWidget(self._clear_btn)
        btn_row.addStretch()
        close_btn = QPushButton(tr("history.button.close"))
        close_btn.setDefault(True)
        close_btn.clicked.connect(self.reject)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self._update_buttons()

    # ----------------------------------------------------------------- render

    def _reload(self) -> None:
        """Re-populate the table from the history, applying the active filters.

        Entries are shown newest-first. The direction/status filters select the
        rows; both default to "All". Sorting is suspended while filling so the
        inserted rows are not reordered mid-population.

        Satisfies: FR-143.
        """
        want_dir = self._direction_filter.currentData()
        want_status = self._status_filter.currentData()
        entries = [
            e
            for e in reversed(self._history.get_entries())
            if (not want_dir or e.get("direction") == want_dir)
            and (not want_status or e.get("status") == want_status)
        ]

        self._table.setSortingEnabled(False)
        self._table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            for col, (_key, field) in enumerate(_COLUMNS):
                item = QTableWidgetItem(self._cell_text(field, entry))
                # Stash the originating entry on the first cell so a re-transfer
                # can recover the full record (path, direction) for the row.
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, entry)
                self._table.setItem(row, col, item)
        self._table.setSortingEnabled(True)
        self._update_buttons()

    @staticmethod
    def _cell_text(field: str, entry: dict[str, Any]) -> str:
        """Render one entry field as display text (translating coded values).

        Satisfies: FR-143, CR-015.
        """
        value = entry.get(field, "")
        if field == "direction":
            return tr(f"history.dir.{value}") if value in ("remote", "host") else str(value)
        if field == "status":
            text = (
                tr(f"history.status.{value}")
                if value in ("success", "failure", "cancelled")
                else str(value)
            )
            # FR-144: flag re-transfers so a retried attempt is distinguishable.
            if entry.get("retry"):
                text = tr("history.status.retry_suffix", status=text)
            return text
        if field == "size":
            return str(value)
        return str(value)

    def _selected_entry(self) -> dict[str, Any] | None:
        """Return the entry for the currently-selected row, or None.

        Satisfies: FR-144.
        """
        rows = self._table.selectionModel().selectedRows() if self._table.selectionModel() else []
        if not rows:
            return None
        item = self._table.item(rows[0].row(), 0)
        if item is None:
            return None
        entry = item.data(Qt.ItemDataRole.UserRole)
        return entry if isinstance(entry, dict) else None

    def _update_buttons(self) -> None:
        """Enable row-dependent actions only when appropriate.

        Re-transfer needs a selected row; Export and Clear need a non-empty
        history.

        Satisfies: FR-143, FR-144.
        """
        self._retransfer_btn.setEnabled(self._selected_entry() is not None)
        has_rows = self._table.rowCount() > 0
        self._export_btn.setEnabled(has_rows)
        self._clear_btn.setEnabled(has_rows)

    # ---------------------------------------------------------------- actions

    def _on_retransfer(self) -> None:
        """Record the selected entry for the owner and close the dialog.

        Satisfies: FR-144.
        """
        entry = self._selected_entry()
        if entry is None:
            return
        self.retransfer_entry = entry
        self.accept()

    def _on_export(self) -> None:
        """Export the history to a user-chosen JSON file.

        Satisfies: FR-143.
        """
        path, _ = QFileDialog.getSaveFileName(
            self, tr("history.export.title"), "", tr("dialog.json_filter")
        )
        if not path:
            return
        if not path.endswith(".json"):
            path += ".json"
        if not self._history.export_history(path):
            QMessageBox.critical(
                self, tr("dialog.error.title"), tr("error.history_export_failed", path=path)
            )

    def _on_clear(self) -> None:
        """Clear the whole history after a confirmation.

        Satisfies: FR-143.
        """
        reply = QMessageBox.question(
            self, tr("history.clear_confirm.title"), tr("history.clear_confirm.prompt")
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._history.clear_history()
            self._reload()
