from __future__ import annotations

import os

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QComboBox, QFileDialog, QHBoxLayout, QLineEdit, QToolButton

from cpm_fm.gui.mw_base import MainWindowMixinBase
from cpm_fm.utils.file_filter import SORT_EXTENSION, SORT_NAME, filter_and_sort
from cpm_fm.utils.i18n import tr


class _FilePanesMixin(MainWindowMixinBase):
    """Host/Remote file-pane controls for :class:`~cpm_fm.app.MainWindow` (mixin).

    The per-pane filter field and sort controls (FR-130-FR-135), the shared
    filter+sort render path, the persisted filter/sort restore (FR-134), and
    the Host Files listing/refresh and change-directory action (FR-060/FR-062).
    The right-click context-menu actions live in
    :mod:`cpm_fm.gui.mw_context_menu`.
    """

    def _build_filter_sort_row(self, pane: str):
        """Build the filter field and sort controls for one file pane.

        Returns ``(layout, filter_edit, sort_combo, dir_btn)``. ``pane`` is
        "host" or "remote" and selects which view-apply slot the controls drive.
        The filter field carries a built-in clear (X) button (FR-135) and its
        input is debounced ~150 ms so a render is not run on every keystroke
        (FR-131). The sort drop-down offers Name/Extension (FR-132, userData =
        the SORT_* key) and the checkable direction button toggles
        ascending/descending.

        Satisfies: FR-130, FR-132, FR-135, UIR-079, UIR-080.
        """
        row = QHBoxLayout()

        filter_edit = QLineEdit()
        filter_edit.setClearButtonEnabled(True)  # FR-135: clear (X) button.
        self._register_text(filter_edit.setPlaceholderText, "main.filter_placeholder")
        self._register_text(filter_edit.setToolTip, "main.filter_tooltip")
        row.addWidget(filter_edit, 1)

        sort_combo = QComboBox()
        sort_combo.addItem(tr("main.sort.name"), SORT_NAME)
        sort_combo.addItem(tr("main.sort.extension"), SORT_EXTENSION)
        self._register_text(sort_combo.setToolTip, "main.sort_by_tooltip")
        row.addWidget(sort_combo)

        dir_btn = QToolButton()
        dir_btn.setCheckable(True)
        dir_btn.setText("↑")  # ascending; flipped to ↓ when checked.
        self._register_text(dir_btn.setToolTip, "main.sort_direction_tooltip")
        row.addWidget(dir_btn)

        apply_fn = self._apply_host_view if pane == "host" else self._apply_remote_view

        # FR-131: debounce filter typing so the list re-renders ~150 ms after the
        # user pauses, not on every character. ``self`` is a QMainWindow at
        # runtime (this mixin is mixed into MainWindow) but is typed as a plain
        # mixin here, so the QObject-parent argument needs a type override.
        timer = QTimer(self)  # type: ignore[arg-type]
        timer.setSingleShot(True)
        timer.setInterval(150)
        timer.timeout.connect(apply_fn)
        filter_edit.textChanged.connect(lambda _text, tm=timer: tm.start())
        # FR-132: a sort change re-renders immediately (no debounce needed).
        sort_combo.currentIndexChanged.connect(apply_fn)
        dir_btn.toggled.connect(lambda checked, b=dir_btn: self._update_sort_arrow(b, checked))
        dir_btn.toggled.connect(apply_fn)

        return row, filter_edit, sort_combo, dir_btn

    @staticmethod
    def _update_sort_arrow(button, checked: bool) -> None:
        """Show ``↓`` for descending, ``↑`` for ascending (UIR-080).

        The arrow glyph is a directional indicator, not translatable prose, so
        it is set directly (CR-015).

        Satisfies: UIR-080.
        """
        button.setText("↓" if checked else "↑")

    def _render_file_list(self, list_widget, names, filter_edit, sort_combo, dir_btn) -> None:
        """Filter+sort ``names`` per the pane's controls and show them.

        Applies the shared filter_and_sort logic (FR-133) and flags an active
        (non-empty) filter with a coloured border on the field (UIR-079).

        Satisfies: FR-130, FR-131, FR-132, FR-133, UIR-079.
        """
        pattern = filter_edit.text()
        key = sort_combo.currentData() or SORT_NAME
        descending = dir_btn.isChecked()
        visible = filter_and_sort(names, pattern, key=key, descending=descending)
        list_widget.clear()
        list_widget.addItems(visible)
        # UIR-079: a coloured border marks an active filter so it is obvious why
        # files may be hidden.
        active = bool(pattern.strip())
        filter_edit.setStyleSheet("QLineEdit { border: 1px solid #4caf50; }" if active else "")

    def _apply_host_view(self) -> None:
        """Re-render the Host list from the current filter/sort controls (FR-133).

        Satisfies: FR-133, FR-134.
        """
        self._render_file_list(
            self.host_list,
            self._host_files,
            self.host_filter,
            self.host_sort_combo,
            self.host_sort_dir_btn,
        )
        self._persist_filter_sort()

    def _apply_remote_view(self) -> None:
        """Re-render the Remote list from the current filter/sort controls (FR-133).

        Satisfies: FR-133, FR-134.
        """
        self._render_file_list(
            self.remote_list,
            self._remote_files,
            self.remote_filter,
            self.remote_sort_combo,
            self.remote_sort_dir_btn,
        )
        self._persist_filter_sort()

    def _clear_remote_files(self) -> None:
        """Empty both the canonical Remote file list and the visible widget.

        Used wherever a stale remote listing must be discarded (load, disconnect,
        drive-not-found, terminal closed, File > New) so the filter/sort source
        does not retain entries that are no longer valid.

        Satisfies: FR-017, FR-058, FR-074, FR-103, FR-104.
        """
        self._remote_files = []
        self.remote_list.clear()

    def _persist_filter_sort(self) -> None:
        """Persist both panes' filter text and sort settings (FR-134).

        A no-op while restoring (so the restore does not overwrite itself).

        Satisfies: FR-134.
        """
        if self._restoring_filter_sort:
            return
        ws = self.window_state
        ws.set_filter_text("host", self.host_filter.text())
        ws.set_sort_key("host", self.host_sort_combo.currentData() or SORT_NAME)
        ws.set_sort_descending("host", self.host_sort_dir_btn.isChecked())
        ws.set_filter_text("remote", self.remote_filter.text())
        ws.set_sort_key("remote", self.remote_sort_combo.currentData() or SORT_NAME)
        ws.set_sort_descending("remote", self.remote_sort_dir_btn.isChecked())

    def _restore_filter_sort(self) -> None:
        """Load each pane's saved filter text and sort settings into its controls.

        Signals are blocked during the restore so it does not trigger a premature
        render or a self-overwriting persist; the first real render happens when
        the lists are next populated.

        Satisfies: FR-134.
        """
        self._restoring_filter_sort = True
        try:
            ws = self.window_state
            panes = (
                ("host", self.host_filter, self.host_sort_combo, self.host_sort_dir_btn),
                ("remote", self.remote_filter, self.remote_sort_combo, self.remote_sort_dir_btn),
            )
            for pane, edit, combo, btn in panes:
                for widget in (edit, combo, btn):
                    widget.blockSignals(True)
                edit.setText(ws.filter_text(pane))
                idx = combo.findData(ws.sort_key(pane))
                combo.setCurrentIndex(idx if idx >= 0 else 0)
                descending = ws.sort_descending(pane)
                btn.setChecked(descending)
                self._update_sort_arrow(btn, descending)
                for widget in (edit, combo, btn):
                    widget.blockSignals(False)
        finally:
            self._restoring_filter_sort = False

    def refresh_host_files(self):
        """
        Satisfies: FR-060, FR-063, FR-126, FR-133.
        """
        # FR-126: the host directory may have changed; reflect it in the group
        # title. This is the single point through which every host-directory
        # change passes.
        self._update_host_group_title()
        try:
            files = [
                f
                for f in os.listdir(self.host_dir)
                if os.path.isfile(os.path.join(self.host_dir, f))
            ]
        except Exception as e:
            self._host_files = []
            self.host_list.clear()
            self.set_status(tr("status.error_reading_host", error=e))
            return
        # FR-133: keep the canonical list and render it through the active
        # filter/sort controls.
        self._host_files = files
        self._apply_host_view()

    def change_host_dir(self):
        """
        Satisfies: FR-062, FR-171.
        """
        path = QFileDialog.getExistingDirectory(
            self, tr("dialog.change_directory.title"), self.host_dir
        )
        if path:
            # FR-171: navigating to another directory discards any open disk
            # image (temp working dir, metadata, Image Details action).
            self._cleanup_image_workdir()
            self.host_dir = path
            self.refresh_host_files()
