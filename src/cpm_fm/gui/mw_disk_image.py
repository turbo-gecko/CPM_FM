from __future__ import annotations

import os
import shutil
from typing import TYPE_CHECKING, cast

from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox

from cpm_fm.gui.disk_image_details_dialog import DiskImageDetailsDialog
from cpm_fm.gui.mw_base import MainWindowMixinBase

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget
from cpm_fm.utils.disk_image import (
    detect_diskdef,
    is_ambiguous,
    load_diskdefs,
    open_image,
)
from cpm_fm.utils.i18n import tr
from cpm_fm.utils.temp_cleanup import make_temp_dir


class _DiskImageMixin(MainWindowMixinBase):
    """File > Open Disk Image… / Image Details… handlers for MainWindow (mixin).

    Opens a CP/M raw-sector disk image, auto-detects its geometry, extracts the
    files it contains to a temporary host working directory, and points the Host
    pane at that directory so the entire existing Copy-to-Remote / drag-and-drop /
    conflict / filename-validation / X-Modem path applies unchanged (FR-169–FR-172,
    UIR-108). A read-only details view exposes the CP/M metadata (user number,
    attributes) captured at open time (FR-173, UIR-109). All CP/M-filesystem logic
    lives in the GUI-free :mod:`cpm_fm.utils.disk_image` package (CR-014); this
    mixin holds only UI state and handlers.
    """

    def menu_open_image(self) -> None:
        """Open a CP/M disk image and list its files in the Host pane.

        Auto-detects geometry (FR-170); prompts for a geometry only when detection
        is ambiguous or fails. Extracts each file to a fresh temp working directory
        and repoints the Host pane at it (FR-171). A file that cannot be recognised
        is rejected with an error dialog, leaving the current Host pane unchanged
        (FR-172).

        Satisfies: FR-169, FR-170, FR-171, FR-172, UIR-108.
        """
        widget = cast("QWidget", self)
        start_dir = os.path.dirname(self._image_source) if self._image_source else self.host_dir
        path, _ = QFileDialog.getOpenFileName(
            widget,
            tr("dialog.open_image.title"),
            start_dir,
            tr("dialog.open_image.filter"),
        )
        if not path:
            return

        diskdef = self._resolve_geometry(path)
        if diskdef is False:  # user cancelled the geometry picker
            return

        img = open_image(path, diskdef)
        if img is None:
            QMessageBox.critical(
                widget,
                tr("dialog.error.title"),
                tr("error.disk_image_unreadable", name=os.path.basename(path)),
            )
            return

        try:
            workdir = make_temp_dir("img_")
            failed = self._extract_files(img, workdir)
        except OSError as exc:
            QMessageBox.critical(
                widget,
                tr("dialog.error.title"),
                tr("error.disk_image_extract", error=exc),
            )
            return

        # Capture the CP/M file metadata for the read-only details view before the
        # files become plain host files that no longer carry it (FR-173).
        image_files = img.list_files()

        # Success: swap the temp workdir in as the host directory. Only remove the
        # previous image workdir once the new one is ready (FR-171).
        self._cleanup_image_workdir()
        self._image_workdir = workdir
        self._image_source = path
        self._image_files = image_files
        if self._image_details_action is not None:
            self._image_details_action.setEnabled(True)
        self.host_dir = workdir
        self.refresh_host_files()

        if failed:
            self.set_status(
                tr("status.disk_image_partial", name=os.path.basename(path), count=len(failed))
            )
        else:
            self.set_status(
                tr(
                    "status.disk_image_loaded",
                    name=os.path.basename(path),
                    geometry=img.geom.name,
                )
            )

    def menu_image_details(self) -> None:
        """Show a read-only table of the open image's files and CP/M metadata.

        Presents the name, size, user number and R/S/A attributes captured at open
        time (FR-173). A no-op when no image is currently open (the menu action is
        disabled in that state, UIR-109).

        Satisfies: FR-173, UIR-109.
        """
        if not self._image_files:
            return
        DiskImageDetailsDialog(cast("QWidget", self), self._image_files).exec()

    def _resolve_geometry(self, path: str):
        """Return the geometry to use: ``None`` (auto), a name, or ``False`` if cancelled.

        Detection runs first (FR-170); the user is prompted only when it is
        ambiguous or finds nothing, in which case the picker offers the ranked
        candidates or, failing that, every bundled definition.

        Satisfies: FR-170.
        """
        try:
            defs = load_diskdefs()
            results = detect_diskdef(path, defs)
        except (OSError, ValueError):
            return None
        if not is_ambiguous(results):
            return None  # confident single match → auto

        if results:
            choices = [r.diskdef.name for r in results]
            label = tr("dialog.open_image.pick_ambiguous")
        else:
            choices = defs.names()
            label = tr("dialog.open_image.pick_unknown")
        if not choices:
            return None
        name, ok = QInputDialog.getItem(
            cast("QWidget", self), tr("dialog.open_image.pick_title"), label, choices, 0, False
        )
        if not ok:
            return False
        return name

    def _extract_files(self, img, workdir: str) -> list[str]:
        """Extract every file in ``img`` to ``workdir``; return the names that failed.

        Corruption of an individual file is tolerated (best-effort listing) rather
        than aborting the whole open (FR-172).

        Satisfies: FR-171, FR-172.
        """
        failed: list[str] = []
        for entry in img.list_files():
            safe = os.path.basename(entry.name)
            try:
                data = img.read_file(entry.name)
                with open(os.path.join(workdir, safe), "wb") as fh:
                    fh.write(data)
            except (KeyError, OSError, ValueError):
                failed.append(entry.name)
        return failed

    def _cleanup_image_workdir(self) -> None:
        """Remove the current image working directory, if any (FR-016, FR-019, FR-171).

        Called when opening another image, on File > New, and on application exit.

        Satisfies: FR-171.
        """
        if self._image_workdir and os.path.isdir(self._image_workdir):
            shutil.rmtree(self._image_workdir, ignore_errors=True)
        self._image_workdir = None
        self._image_source = None
        # FR-173/UIR-109: no image open → clear its metadata and disable the
        # Image Details… action.
        self._image_files = []
        if self._image_details_action is not None:
            self._image_details_action.setEnabled(False)
