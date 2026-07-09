from __future__ import annotations

import os
import shutil
from typing import TYPE_CHECKING, cast

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QStyle,
    QVBoxLayout,
)

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

        Satisfies: FR-169, FR-170, FR-171, FR-172, FR-175, UIR-108.
        """
        # FR-175: opening another image discards the current working directory;
        # offer to save unsaved staged changes first.
        if not self._maybe_prompt_save_image():
            return
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
        # FR-175: record the extracted contents as the clean baseline so later
        # copy-to-image edits can be detected as unsaved changes.
        self._capture_image_baseline()

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

    def menu_save_image(self) -> bool:
        """Re-pack the working directory into a new CP/M image via Save As (FR-174).

        Rebuilds the image from the current host working-directory contents using
        the opened image's geometry, preserving its boot tracks (DR-050), and writes
        it to a user-chosen new path. Never overwrites the source image. A capacity
        or filename problem is reported and nothing is written. A no-op when no
        image is open or writing is disabled (the action is disabled in that state,
        UIR-110). Returns ``True`` only when a new image was written — the unsaved-
        changes guard (FR-175) relies on this to decide whether a discard may
        proceed.

        Satisfies: FR-174, FR-175, UIR-110.
        """
        if not (self._image_workdir and self._image_geom and self._image_source):
            return False
        if not self._image_write_enabled():
            return False
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
            return False
        if os.path.abspath(path) == os.path.abspath(self._image_source):
            QMessageBox.warning(
                widget,
                tr("dialog.error.title"),
                tr("error.disk_image_overwrite_source"),
            )
            return False

        try:
            count = self._repack_workdir(path)
        except (ImageWriteError, OSError) as exc:
            QMessageBox.critical(
                widget,
                tr("dialog.error.title"),
                tr("error.disk_image_write", error=exc),
            )
            return False

        # FR-175: the working directory now matches a saved image → clean again.
        self._capture_image_baseline()
        self.set_status(tr("status.disk_image_saved", name=os.path.basename(path), count=count))
        return True

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

    def _workdir_signature(self) -> set[tuple[str, int, int]]:
        """Return a ``(name, size, mtime_ns)`` set describing the working dir.

        Comparing this against the baseline captured at open/save time detects
        copy-to-image edits (added, replaced or removed files) without hooking
        every individual mutation site. Returns an empty set when no image is
        open, so an absent working directory reads as "no changes".

        Satisfies: FR-175.
        """
        sig: set[tuple[str, int, int]] = set()
        if not self._image_workdir:
            return sig
        try:
            with os.scandir(self._image_workdir) as it:
                for entry in it:
                    try:
                        if entry.is_file():
                            st = entry.stat()
                            sig.add((entry.name, st.st_size, st.st_mtime_ns))
                    except OSError:
                        continue
        except OSError:
            return sig
        return sig

    def _capture_image_baseline(self) -> None:
        """Record the current working-directory contents as the clean baseline.

        Called after an image is opened (files just extracted) and after a
        successful Save Image… (working dir now matches a saved image), so a
        subsequent copy-to-image edit registers as an unsaved change (FR-175).

        Satisfies: FR-175.
        """
        self._image_baseline = self._workdir_signature() if self._image_workdir else None

    def _image_is_dirty(self) -> bool:
        """True when the working directory differs from its clean baseline (FR-175)."""
        if self._image_workdir is None or self._image_baseline is None:
            return False
        return self._workdir_signature() != self._image_baseline

    def _maybe_prompt_save_image(self) -> bool:
        """Guard a working-directory discard on unsaved copy-to-image edits.

        Returns ``True`` when the caller may proceed to discard the working
        directory, ``False`` when the user chose to cancel the action. No prompt
        is shown — and ``True`` is returned immediately — when no image is open,
        writing is disabled (nothing is savable), or there are no unsaved changes.
        Otherwise a Save / Discard / Cancel dialog is shown: Save routes through
        Save Image… (FR-174) and only permits the discard if the save completed;
        a cancelled Save-As keeps the changes and aborts the action.

        Satisfies: FR-175.
        """
        if not (self._image_workdir and self._image_geom and self._image_source):
            return True
        if not self._image_write_enabled():
            return True
        if not self._image_is_dirty():
            return True
        choice = self._prompt_save_discard_cancel()
        if choice == "cancel":
            return False
        if choice == "discard":
            return True
        return self.menu_save_image()  # "save": proceed only if the save succeeded

    def _prompt_save_discard_cancel(self) -> str:
        """Show the modal unsaved-changes dialog; return 'save'/'discard'/'cancel'.

        Buttons follow the house order (UIR-075): Cancel far left, the affirmative
        Save far right, with Discard between them. A window-manager close is
        treated as Cancel.

        Satisfies: FR-175, UIR-111.
        """
        widget = cast("QWidget", self)
        name = os.path.basename(self._image_source) if self._image_source else ""
        dlg = QDialog(widget)
        dlg.setWindowTitle(tr("dialog.image_dirty.title"))
        dlg.setModal(True)
        layout = QVBoxLayout(dlg)

        msg_row = QHBoxLayout()
        icon_label = QLabel()
        icon = dlg.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxWarning)
        icon_label.setPixmap(icon.pixmap(48, 48))
        icon_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        msg_row.addWidget(icon_label)
        text = QLabel(tr("dialog.image_dirty.message", name=name))
        text.setWordWrap(True)
        msg_row.addWidget(text, 1)
        layout.addLayout(msg_row)

        result = {"choice": "cancel"}

        def choose(value: str) -> None:
            result["choice"] = value
            dlg.accept()

        save_btn = QPushButton(tr("button.save"))
        discard_btn = QPushButton(tr("button.discard"))
        cancel_btn = QPushButton(tr("button.cancel"))
        save_btn.clicked.connect(lambda: choose("save"))
        discard_btn.clicked.connect(lambda: choose("discard"))
        cancel_btn.clicked.connect(dlg.reject)  # leaves the default "cancel"
        save_btn.setDefault(True)

        btn_row = QHBoxLayout()
        btn_row.addWidget(cancel_btn)
        btn_row.addStretch()
        btn_row.addWidget(discard_btn)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

        dlg.exec()
        return result["choice"]

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
        # FR-175: no image open → no clean baseline to compare against.
        self._image_baseline = None
        # FR-173/UIR-109: no image open → clear its metadata and disable the
        # Image Details… action.
        self._image_files = []
        if self._image_details_action is not None:
            self._image_details_action.setEnabled(False)
        # UIR-110: no image open → Save Image… is disabled too.
        self._update_save_image_action()
