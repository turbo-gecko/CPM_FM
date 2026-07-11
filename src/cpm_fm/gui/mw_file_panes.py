from __future__ import annotations

import os

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QListWidgetItem,
    QToolButton,
)

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

        Returns ``(layout, filter_edit, sort_combo, dir_btn, area_combo)``.
        ``pane`` is "host" or "remote" and selects which view-apply slot the
        controls drive. The filter field carries a built-in clear (X) button
        (FR-135) and its input is debounced ~150 ms so a render is not run on
        every keystroke (FR-131). The sort drop-down offers Name/Extension
        (FR-132, userData = the SORT_* key) and the checkable direction button
        toggles ascending/descending. The user-area filter drop-down
        (``area_combo``) is hidden unless a disk image is mounted in this pane
        (UIR-120); it selects one CP/M user area to show, or All.

        Satisfies: FR-130, FR-132, FR-135, FR-189, UIR-079, UIR-080, UIR-120.
        """
        row = QHBoxLayout()

        filter_edit = QLineEdit()
        filter_edit.setClearButtonEnabled(True)  # FR-135: clear (X) button.
        self._register_text(filter_edit.setPlaceholderText, "main.filter_placeholder")
        self._register_text(filter_edit.setToolTip, "main.filter_tooltip")
        row.addWidget(filter_edit, 1)

        # UIR-120: per-pane user-area filter, hidden until an image is mounted
        # here. Populated on demand by _update_area_filter; an area change
        # re-renders immediately (no debounce needed). It is built empty, so
        # without a minimum contents length its size hint would be ~zero and the
        # layout would leave it too narrow to read once populated; reserve room
        # for the widest label (e.g. the "All" text) plus the drop-down arrow.
        area_combo = QComboBox()
        area_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        area_combo.setMinimumContentsLength(6)
        area_combo.setVisible(False)
        self._register_text(area_combo.setToolTip, "main.area_filter_tooltip")
        row.addWidget(area_combo)

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
        # FR-189/UIR-120: an area-filter change re-renders immediately.
        area_combo.currentIndexChanged.connect(apply_fn)

        return row, filter_edit, sort_combo, dir_btn, area_combo

    @staticmethod
    def _update_sort_arrow(button, checked: bool) -> None:
        """Show ``↓`` for descending, ``↑`` for ascending (UIR-080).

        The arrow glyph is a directional indicator, not translatable prose, so
        it is set directly (CR-015).

        Satisfies: UIR-080.
        """
        button.setText("↓" if checked else "↑")

    def _render_file_list(
        self,
        list_widget,
        names,
        filter_edit,
        sort_combo,
        dir_btn,
        area_map=None,
        area_filter=None,
    ) -> None:
        """Filter+sort ``names`` per the pane's controls and show them.

        Applies the shared filter_and_sort logic (FR-133) and flags an active
        (non-empty) filter with a coloured border on the field (UIR-079). Each
        row's real filename is stored in the item's ``UserRole`` so callers read
        it back regardless of the display text; when ``area_map`` is given (an
        image is mounted in this pane, FR-185) the row is prefixed with the CP/M
        user area (``U3  FOO.COM``, UIR-119) while selection/drag/transfer keep
        using the stored filename. When ``area_filter`` is a user area (not
        ``None``) the list is first narrowed to files in that area (FR-189).

        Satisfies: FR-130, FR-131, FR-132, FR-133, FR-189, UIR-079, UIR-119, UIR-120.
        """
        # FR-189: narrow to a single user area before the text filter/sort when
        # the area filter is active (only meaningful with a mounted image).
        if area_map is not None and area_filter is not None:
            names = [n for n in names if area_map.get(n) == area_filter]
        pattern = filter_edit.text()
        key = sort_combo.currentData() or SORT_NAME
        descending = dir_btn.isChecked()
        visible = filter_and_sort(names, pattern, key=key, descending=descending)
        list_widget.clear()
        for name in visible:
            item = QListWidgetItem()
            # The stored filename is authoritative for selection/drag (UIR-119);
            # the display text may carry the area prefix.
            item.setData(Qt.ItemDataRole.UserRole, name)
            if area_map is not None and name in area_map:
                item.setText(f"U{area_map[name]:<2} {name}")
            else:
                item.setText(name)
            list_widget.addItem(item)
        # UIR-079: a coloured border marks an active filter so it is obvious why
        # files may be hidden.
        active = bool(pattern.strip())
        filter_edit.setStyleSheet("QLineEdit { border: 1px solid #4caf50; }" if active else "")

    def _pane_area_map(self, pane: str):
        """Return the staged-name→area map when an image is mounted in ``pane``.

        Drives the user-area column (UIR-119); ``None`` when no image is open or
        the image is mounted in the other pane, so a real host/remote listing
        shows plain filenames.

        Satisfies: UIR-119, FR-185.
        """
        if self._image_workdir is None or self._image_pane != pane:
            return None
        return {staged: area for staged, (_cpm, area) in self._image_stage_map.items()}

    def _area_filter_combo(self, pane: str):
        """Return the user-area filter combo for ``pane`` ("host"/"remote").

        Satisfies: UIR-120.
        """
        return self.host_area_filter if pane == "host" else self.remote_area_filter

    def _update_area_filter(self, pane: str) -> None:
        """Sync the pane's user-area filter combo with the mounted image (FR-189).

        When an image is mounted in ``pane`` the combo is populated with **All**
        (userData ``None``) followed by exactly the user areas present in the
        image (sorted ascending, userData = the ``int`` area) and shown; the
        current selection is preserved when that area is still present, else it
        falls back to All. When no image is mounted here the combo is cleared and
        hidden, so a stale area filter never survives to the next mount. Signals
        are blocked while rebuilding so this does not trigger a render or recurse
        through the ``currentIndexChanged`` slot.

        Satisfies: FR-189, UIR-120.
        """
        combo = self._area_filter_combo(pane)
        area_map = self._pane_area_map(pane)
        combo.blockSignals(True)
        try:
            previous = combo.currentData()
            combo.clear()
            if area_map is None:
                combo.setVisible(False)
                return
            combo.addItem(tr("main.area_filter_all"), None)
            for area in sorted(set(area_map.values())):
                # The area number is a datum, not translatable prose (CR-015).
                combo.addItem(f"U{area}", area)
            idx = combo.findData(previous) if previous is not None else 0
            combo.setCurrentIndex(idx if idx >= 0 else 0)
            combo.setVisible(True)
        finally:
            combo.blockSignals(False)
        # The combo was built empty and hidden; invalidate its geometry so the
        # row re-lays it at its now-populated size hint rather than the stale
        # first-show hint (UIR-120).
        combo.updateGeometry()

    def _apply_host_view(self) -> None:
        """Re-render the Host list from the current filter/sort controls (FR-133).

        Satisfies: FR-133, FR-134, FR-189.
        """
        self._update_area_filter("host")
        self._render_file_list(
            self.host_list,
            self._host_files,
            self.host_filter,
            self.host_sort_combo,
            self.host_sort_dir_btn,
            area_map=self._pane_area_map("host"),
            area_filter=self.host_area_filter.currentData(),
        )
        self._persist_filter_sort()

    def _apply_remote_view(self) -> None:
        """Re-render the Remote list from the current filter/sort controls (FR-133).

        Satisfies: FR-133, FR-134, FR-189.
        """
        self._update_area_filter("remote")
        self._render_file_list(
            self.remote_list,
            self._remote_files,
            self.remote_filter,
            self.remote_sort_combo,
            self.remote_sort_dir_btn,
            area_map=self._pane_area_map("remote"),
            area_filter=self.remote_area_filter.currentData(),
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
        Satisfies: FR-062, FR-171, FR-175, FR-176.
        """
        path = QFileDialog.getExistingDirectory(
            self, tr("dialog.change_directory.title"), self.host_dir
        )
        if path:
            # FR-176: a Remote-mounted image is independent of the host folder, so
            # changing the host directory must not disturb it (v2.35). Only a
            # Host-side image (whose working dir *is* the Host pane) is discarded.
            if self._image_pane == "host" and self._image_workdir is not None:
                # FR-175: discarding the open image may lose unsaved staged
                # changes; offer to save first and abort the change on Cancel.
                if not self._maybe_prompt_save_image():
                    return
                # FR-171: navigating away discards the Host-side image (temp
                # working dir, metadata, Image Details action).
                self._cleanup_image_workdir()
            self.host_dir = path
            self.refresh_host_files()
