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
from cpm_fm.utils.disk_image.filesystem import ImageWriteError
from cpm_fm.utils.i18n import tr
from cpm_fm.utils.temp_cleanup import make_temp_dir


class _DiskImageMixin(MainWindowMixinBase):
    """File > Open Disk Image… / Image Details… / Save Image… handlers (mixin).

    Opens a CP/M raw-sector disk image, auto-detects its geometry, extracts the
    files it contains to a temporary host working directory, and points the Host
    pane at that directory so the entire existing Copy-to-Remote / drag-and-drop /
    conflict / filename-validation / X-Modem path applies unchanged (FR-169–FR-172,
    UIR-108). A read-only details view exposes the CP/M metadata (user number,
    attributes) captured at open time (FR-173, UIR-109). When the opt-in
    ``image_write_enabled`` setting is on, Save Image… re-packs the working
    directory into a fresh image via Save As, preserving the source's boot tracks
    (FR-174, UIR-110). All CP/M-filesystem logic lives in the GUI-free
    :mod:`cpm_fm.utils.disk_image` package (CR-014); this mixin holds only UI state
    and handlers.
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
        self._image_geom = img.geom
        self._image_files = image_files
        if self._image_details_action is not None:
            self._image_details_action.setEnabled(True)
        self._update_save_image_action()
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

    def _image_write_enabled(self) -> bool:
        """True when the opt-in image_write_enabled setting is on (FR-174, UIR-110)."""
        return str(self.settings.get("image_write_enabled", "OFF")).upper() == "ON"

    def _update_save_image_action(self) -> None:
        """Enable Save Image… only while an image is open and writing is on (UIR-110).

        Satisfies: FR-174, UIR-110.
        """
        if self._save_image_action is not None:
            self._save_image_action.setEnabled(
                self._image_workdir is not None
                and self._image_geom is not None
                and self._image_write_enabled()
            )

    def menu_save_image(self) -> None:
        """Re-pack the working directory into a new CP/M image via Save As (FR-174).

        Rebuilds the image from the current host working-directory contents using
        the opened image's geometry, preserving its boot tracks (DR-050), and writes
        it to a user-chosen new path. Never overwrites the source image. A capacity
        or filename problem is reported and nothing is written. A no-op when no
        image is open or writing is disabled (the action is disabled in that state,
        UIR-110).

        Satisfies: FR-174, UIR-110.
        """
        if not (self._image_workdir and self._image_geom and self._image_source):
            return
        if not self._image_write_enabled():
            return
        widget = cast("QWidget", self)

        suggested = os.path.join(
            os.path.dirname(self._image_source),
            os.path.splitext(os.path.basename(self._image_source))[0] + "_new.img",
        )
        path, _ = QFileDialog.getSaveFileName(
            widget,
            tr("dialog.save_image.title"),
            suggested,
            tr("dialog.save_image.filter"),
        )
        if not path:
            return
        if os.path.abspath(path) == os.path.abspath(self._image_source):
            QMessageBox.warning(
                widget,
                tr("dialog.error.title"),
                tr("error.disk_image_overwrite_source"),
            )
            return

        try:
            count = self._repack_workdir(path)
        except (ImageWriteError, OSError) as exc:
            QMessageBox.critical(
                widget,
                tr("dialog.error.title"),
                tr("error.disk_image_write", error=exc),
            )
            return

        self.set_status(tr("status.disk_image_saved", name=os.path.basename(path), count=count))

    def _repack_workdir(self, dest_path: str) -> int:
        """Write the working-directory files into a fresh image at ``dest_path``.

        Re-opens the source image (for its verbatim boot tracks and geometry),
        clears its directory, writes every regular file in the working directory,
        and saves to ``dest_path``. Returns the number of files written. Raises
        :class:`~cpm_fm.utils.disk_image.filesystem.ImageWriteError` (capacity or
        name) or ``OSError`` (unreadable source / unwritable destination).

        Satisfies: FR-174, DR-050.
        """
        assert self._image_source is not None and self._image_workdir is not None
        src = open_image(self._image_source, self._image_geom)
        if src is None:
            raise ImageWriteError("source image can no longer be read")
        for entry in list(src.entries):
            src.delete_file(entry.full_name)
        count = 0
        for name in sorted(os.listdir(self._image_workdir)):
            full = os.path.join(self._image_workdir, name)
            if not os.path.isfile(full):
                continue
            with open(full, "rb") as fh:
                src.write_file(name, fh.read())
            count += 1
        src.save(dest_path)
        return count

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
        self._image_geom = None
        # FR-173/UIR-109: no image open → clear its metadata and disable the
        # Image Details… action.
        self._image_files = []
        if self._image_details_action is not None:
            self._image_details_action.setEnabled(False)
        # UIR-110: no image open → Save Image… is disabled too.
        self._update_save_image_action()
