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
    QRadioButton,
    QStyle,
    QVBoxLayout,
)

from cpm_fm.gui.conflict_dialog import CANCEL, SKIP, FileConflictDialog
from cpm_fm.gui.dialog_buttons import build_button_row
from cpm_fm.gui.disk_image_details_dialog import DiskImageDetailsDialog
from cpm_fm.gui.filename_validation_dialog import FilenameValidationDialog
from cpm_fm.gui.mw_base import MainWindowMixinBase
from cpm_fm.terminal.cpm_parser import CPMParser

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget
from cpm_fm.utils.disk_image import (
    create_image,
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

        Satisfies: FR-169, FR-170, FR-171, FR-172, FR-175, FR-176, FR-177, UIR-108.
        """
        # FR-175: opening another image discards the current working directory;
        # offer to save unsaved staged changes first.
        if not self._maybe_prompt_save_image():
            return
        widget = cast("QWidget", self)
        # FR-176: choose which pane the image mounts into before browsing for it.
        mount = self._prompt_mount_side()
        if mount is None:
            return
        # FR-176: a Remote-pane mount is mutually exclusive with a live serial
        # session — refuse it while the Terminal Port is connected.
        if mount == "remote" and self.serial_mgr.terminal_connected:
            QMessageBox.warning(
                widget,
                tr("dialog.warning.title"),
                tr("error.image_remote_needs_disconnect"),
            )
            return
        # FR-179: browse from the dedicated image directory, not the host folder.
        path, _ = QFileDialog.getOpenFileName(
            widget,
            tr("dialog.open_image.title"),
            self.image_dir,
            tr("dialog.open_image.filter"),
        )
        if not path:
            return
        # FR-179: remember the folder this image came from for next time.
        self.image_dir = os.path.dirname(path)

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
        # FR-185: _extract_files just built the staged-name→area map, but
        # _cleanup_image_workdir() below resets it to {}; keep the new image's map
        # in a local and restore it after cleanup (mirroring image_files), so the
        # area column (UIR-119) and area filter (FR-189) see the real areas.
        stage_map = self._image_stage_map

        # FR-177: remember the real host directory to restore on Close. Read it
        # before _cleanup_image_workdir clears the state: when replacing an already
        # open image, keep the directory recorded for that image (self.host_dir
        # would be its temporary workdir); otherwise it is the current host dir.
        pre_dir = self.host_dir if self._image_workdir is None else self._pre_image_host_dir

        # Success: adopt the new workdir. Only remove the previous image workdir
        # once the new one is ready (FR-171).
        self._cleanup_image_workdir()
        self._image_workdir = workdir
        self._image_source = path
        self._image_geom = img.geom
        self._image_files = image_files
        # FR-185: restore the map cleared by _cleanup_image_workdir() above.
        self._image_stage_map = stage_map
        self._image_pane = mount
        if self._image_details_action is not None:
            self._image_details_action.setEnabled(True)
        if self._close_image_action is not None:
            self._close_image_action.setEnabled(True)
        self._update_save_image_action()
        # FR-176: mount the image into the chosen pane. Host-side repoints the
        # Host pane at the workdir (the established behaviour); Remote-side leaves
        # the Host pane on its real directory and sources the Remote list from the
        # workdir, disabling the (meaningless) drive drop-down.
        if mount == "remote":
            self.drive_combo.setEnabled(False)
            # If the previous mount was Host-side, self.host_dir still points at
            # that image's now-deleted workdir; restore the Host pane to a real
            # directory so it is not left on a stale path (v2.33.1 fix).
            if not os.path.isdir(self.host_dir):
                self.host_dir = pre_dir or self.settings.get("host_directory") or os.getcwd()
                self.refresh_host_files()
            self._list_image_remote()
            self._update_remote_group_title()
        else:
            self._pre_image_host_dir = pre_dir
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

    def menu_close_image(self) -> None:
        """Close the open disk image and restore the Host and Remote panes.

        Prompts to save first when there are unsaved copy-to-image changes and
        writing is enabled (FR-175); Cancel aborts the close and keeps the image
        open. Discarding the working directory (``_cleanup_image_workdir``) resets
        the Remote pane when the image was Remote-mounted (FR-176); a Host-mounted
        image additionally restores the Host pane to the directory that was active
        before the image was opened (falling back to the configured host directory
        or the current working directory). A no-op when no image is open (the menu
        action is disabled in that state, UIR-113).

        Satisfies: FR-177, FR-175, UIR-113.
        """
        if self._image_workdir is None:
            return
        # FR-175: closing discards the working directory; offer to save first.
        if not self._maybe_prompt_save_image():
            return
        # FR-177: capture the restore target before cleanup clears the state.
        was_host = self._image_pane == "host"
        restore_dir = self._pre_image_host_dir or self.settings.get("host_directory") or os.getcwd()
        self._cleanup_image_workdir()
        # FR-177: a Host-side mount had repointed the Host pane at the workdir;
        # restore the previous directory. A Remote-side mount left the Host pane
        # alone, and _cleanup_image_workdir already reset the Remote pane.
        if was_host:
            self.host_dir = restore_dir
            self.refresh_host_files()
        self.set_status(tr("status.disk_image_closed"))

    def menu_new_image(self) -> None:
        """Create a new, empty CP/M disk image and open it (FR-178).

        Prompts for a geometry (there is no file to auto-detect from) and, via the
        mount-side dialog (FR-176), which pane to mount it into, then builds a blank
        image (:func:`~cpm_fm.utils.disk_image.create_image`) with an empty working
        directory. The new image has no source file — it is unnamed until the first
        Save Image… (FR-174) — and the empty working directory is its clean baseline,
        so the FR-175 guard protects files copied in before the first save.

        Satisfies: FR-178, FR-175, FR-176, UIR-114.
        """
        # FR-175: creating a new image discards any open one; offer to save first.
        if not self._maybe_prompt_save_image():
            return
        widget = cast("QWidget", self)
        # FR-176: choose the mount pane, refusing Remote-side while connected.
        mount = self._prompt_mount_side()
        if mount is None:
            return
        if mount == "remote" and self.serial_mgr.terminal_connected:
            QMessageBox.warning(
                widget,
                tr("dialog.warning.title"),
                tr("error.image_remote_needs_disconnect"),
            )
            return
        diskdef = self._prompt_new_geometry()
        if diskdef is None:
            return

        img = create_image(diskdef)
        try:
            workdir = make_temp_dir("img_")
        except OSError as exc:
            QMessageBox.critical(
                widget, tr("dialog.error.title"), tr("error.disk_image_extract", error=exc)
            )
            return

        # FR-178: remember the real host dir to restore on close (Host-side only),
        # read before cleanup clears the state (mirrors menu_open_image).
        pre_dir = self.host_dir if self._image_workdir is None else self._pre_image_host_dir

        self._cleanup_image_workdir()
        self._image_workdir = workdir
        self._image_source = None  # FR-178: unnamed until the first Save Image…
        self._image_geom = img.geom
        self._image_files = []
        self._image_pane = mount
        if self._image_details_action is not None:
            self._image_details_action.setEnabled(True)
        if self._close_image_action is not None:
            self._close_image_action.setEnabled(True)
        self._update_save_image_action()
        if mount == "remote":
            self.drive_combo.setEnabled(False)
            self._list_image_remote()
            self._update_remote_group_title()
        else:
            self._pre_image_host_dir = pre_dir
            self.host_dir = workdir
            self.refresh_host_files()
        # FR-175: the empty working directory is the clean baseline.
        self._capture_image_baseline()
        self.set_status(tr("status.new_image_created", geometry=diskdef.name))

    def _prompt_new_geometry(self):
        """Prompt for a bundled geometry to build a new image with (FR-178).

        Returns the chosen :class:`~cpm_fm.utils.disk_image.DiskDef`, or ``None``
        if the user cancels or no definitions are available.

        Satisfies: FR-178, UIR-114.
        """
        try:
            defs = load_diskdefs()
        except (OSError, ValueError):
            return None
        names = defs.names()
        if not names:
            return None
        name, ok = QInputDialog.getItem(
            cast("QWidget", self),
            tr("dialog.new_image.pick_title"),
            tr("dialog.new_image.pick_label"),
            names,
            0,
            False,
        )
        if not ok:
            return None
        return defs.get(name)

    def _update_save_image_action(self) -> None:
        """Enable Save Image… only while an image is open (UIR-110).

        Disk-image writing is no longer opt-in (v2.35), so the action depends only
        on whether an image is open.

        Satisfies: FR-174, UIR-110.
        """
        if self._save_image_action is not None:
            self._save_image_action.setEnabled(
                self._image_workdir is not None and self._image_geom is not None
            )

    def menu_save_image(self) -> bool:
        """Save the working directory back into the image file (FR-174).

        A plain document-style save (v2.35): an image that already has a file is
        **overwritten in place** (its geometry and boot tracks preserved, DR-050);
        a new, unnamed image (FR-178) is written via a Save-As dialog (browsing the
        image directory, FR-179) and then adopts that path as its file. A capacity
        or filename problem is reported and nothing is written. A no-op when no
        image is open (the action is disabled then, UIR-110). Returns ``True`` only
        when the image was written — the unsaved-changes guard (FR-175) relies on
        this to decide whether a discard may proceed.

        Satisfies: FR-174, FR-175, FR-178, FR-179, UIR-110.
        """
        if not (self._image_workdir and self._image_geom):
            return False
        widget = cast("QWidget", self)

        if self._image_source is not None:
            # Overwrite the current image file in place (KISS — like any Save).
            path = self._image_source
        else:
            # FR-178/FR-179: a new image has no file yet; Save-As from the image dir.
            suggested = os.path.join(self.image_dir, "new_image.img")
            path, _ = QFileDialog.getSaveFileName(
                widget,
                tr("dialog.save_image.title"),
                suggested,
                tr("dialog.save_image.filter"),
            )
            if not path:
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

        # FR-178: a new (source-less) image adopts the written path as its file, so
        # it is now file-backed — the pane title names it and later saves overwrite it.
        if self._image_source is None:
            self._image_source = path
            self._update_host_group_title()
            self._update_remote_group_title()
        # FR-179: remember the folder we saved into.
        self.image_dir = os.path.dirname(path)
        # FR-175: the working directory now matches the saved image → clean again.
        self._capture_image_baseline()
        self.set_status(tr("status.disk_image_saved", name=os.path.basename(path), count=count))
        return True

    def _repack_workdir(self, dest_path: str) -> int:
        """Write the working-directory files into a fresh image at ``dest_path``.

        Re-opens the source image (for its verbatim boot tracks and geometry),
        clears its directory, writes every regular file in the working directory,
        and saves to ``dest_path``. For a source-less new image (FR-178) it builds
        a fresh blank image of the open geometry instead. Each file is written
        under its real CP/M name and back into its source user area (FR-187),
        looked up in ``self._image_stage_map`` (a file with no map entry — e.g.
        one copied in after open — defaults to area 0). Returns the number of
        files written. Raises
        :class:`~cpm_fm.utils.disk_image.filesystem.ImageWriteError` (capacity or
        name) or ``OSError`` (unreadable source / unwritable destination).

        Satisfies: FR-174, FR-178, FR-187, DR-050.
        """
        assert self._image_workdir is not None and self._image_geom is not None
        if self._image_source is None:
            src = create_image(self._image_geom)
        else:
            opened = open_image(self._image_source, self._image_geom)
            if opened is None:
                raise ImageWriteError("source image can no longer be read")
            src = opened
        for entry in list(src.entries):
            src.delete_file(entry.full_name)
        count = 0
        for name in sorted(os.listdir(self._image_workdir)):
            full = os.path.join(self._image_workdir, name)
            if not os.path.isfile(full):
                continue
            # FR-187: restore the file's real CP/M name and source user area.
            cpm_name, area = self._image_stage_map.get(name, (name, 0))
            with open(full, "rb") as fh:
                src.write_file(cpm_name, fh.read(), user=area)
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
        is shown — and ``True`` is returned immediately — when no image is open or
        there are no unsaved changes. This also guards a never-saved new image
        (FR-178), which has no source file yet. Otherwise a Save / Discard / Cancel
        dialog is shown: Save routes through Save Image… (FR-174) and only permits
        the discard if the save completed; a cancelled Save-As keeps the changes
        and aborts the action.

        Satisfies: FR-175.
        """
        if not (self._image_workdir and self._image_geom):
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
        name = (
            os.path.basename(self._image_source) if self._image_source else tr("main.image_unsaved")
        )
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

    # ------------------------------------------------------- dual-pane mount

    def _prompt_mount_side(self) -> str | None:
        """Ask which pane to mount the opening image into; return 'host'/'remote'.

        Returns ``None`` when the user cancels (aborting the open). Host is the
        default. Buttons follow the house order (UIR-075: Cancel far left, OK far
        right).

        Satisfies: FR-176, UIR-112.
        """
        widget = cast("QWidget", self)
        dlg = QDialog(widget)
        dlg.setWindowTitle(tr("dialog.mount_side.title"))
        dlg.setModal(True)
        layout = QVBoxLayout(dlg)
        message = QLabel(tr("dialog.mount_side.message"))
        message.setWordWrap(True)
        layout.addWidget(message)
        host_radio = QRadioButton(tr("dialog.mount_side.host"))
        remote_radio = QRadioButton(tr("dialog.mount_side.remote"))
        host_radio.setChecked(True)  # FR-176: Host-side is the default.
        layout.addWidget(host_radio)
        layout.addWidget(remote_radio)

        ok_btn = QPushButton(tr("button.ok"))
        cancel_btn = QPushButton(tr("button.cancel"))
        ok_btn.clicked.connect(dlg.accept)
        cancel_btn.clicked.connect(dlg.reject)
        ok_btn.setDefault(True)
        layout.addLayout(build_button_row(accept_button=ok_btn, reject_button=cancel_btn))

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None
        return "remote" if remote_radio.isChecked() else "host"

    def _remote_is_image(self) -> bool:
        """True when an open disk image is mounted in the Remote pane (FR-176)."""
        return self._image_workdir is not None and self._image_pane == "remote"

    def _host_image_entry(self, staged_name: str) -> tuple[str, int] | None:
        """Return ``(CP/M name, user area)`` for a staged Host-mounted image file.

        ``None`` when no image is mounted in the Host pane or ``staged_name`` is
        not a staged image file (an ordinary host file). Lets a Copy to Remote
        send each image file under its real CP/M name and into its source user
        area (FR-188).

        Satisfies: FR-185, FR-188.
        """
        if self._image_workdir is None or self._image_pane != "host":
            return None
        return self._image_stage_map.get(staged_name)

    def _list_image_remote(self) -> None:
        """Populate the Remote Files list from the Remote-mounted image workdir.

        The local virtual-device listing: read the working directory (files only)
        straight into the canonical Remote list and render it, with no serial I/O
        (FR-176, revising FR-073/FR-074).

        Satisfies: FR-176.
        """
        if not self._image_workdir:
            return
        try:
            files = [
                f
                for f in os.listdir(self._image_workdir)
                if os.path.isfile(os.path.join(self._image_workdir, f))
            ]
        except OSError:
            files = []
        self._remote_files = files
        self._apply_remote_view()

    def _copy_host_to_image(self, source_paths: list[str]) -> None:
        """Copy selected host files into the Remote-mounted image (local, FR-176).

        A plain filesystem copy of each source into the image working directory,
        applying CP/M 8.3 name validation (FR-148/FR-149) and destination-conflict
        resolution (FR-145–FR-147) — the same dialogs the serial upload uses, but
        built directly here because this runs on the GUI thread. Marks the image
        dirty implicitly (the working-directory signature diverges, FR-175). Each
        copied-in file is recorded in the current user area (FR-186) so it lands
        there on write-back (FR-187).

        Satisfies: FR-176, FR-186.
        """
        if not self._image_workdir:
            return
        widget = cast("QWidget", self)
        workdir = self._image_workdir
        existing = {
            n.upper() for n in os.listdir(workdir) if os.path.isfile(os.path.join(workdir, n))
        }
        policy: str | None = None
        copied = 0
        for src in source_paths:
            dest_name = os.path.basename(src)
            if not CPMParser.is_valid_8_3(dest_name):
                action, new_name = self._prompt_invalid_name_local(dest_name)
                if action == CANCEL:
                    break
                if action == SKIP:
                    continue
                dest_name = new_name
            if dest_name.upper() in existing:
                action, policy = self._resolve_conflict_local(dest_name, "remote", policy)
                if action == CANCEL:
                    break
                if action == SKIP:
                    continue
            dest = os.path.join(workdir, dest_name)
            try:
                shutil.copy2(src, dest)
            except OSError as exc:
                QMessageBox.critical(
                    widget, tr("dialog.error.title"), tr("error.image_copy", error=exc)
                )
                break
            existing.add(dest_name.upper())
            # FR-186: a file copied into a Remote-mounted image lands in the
            # currently selected user area (UIR-118); record it so the area column
            # and write-back (FR-187) reflect it.
            self._image_stage_map[dest_name] = (dest_name, self._remote_user)
            self._record_history(
                dest_name, src, "remote", "success", os.path.getsize(dest), "", False
            )
            copied += 1
        self._list_image_remote()
        self.set_status(tr("status.image_copy_in", count=copied))

    def _copy_image_to_host(self, names: list[str]) -> None:
        """Copy selected image files out to the host directory (local, FR-176).

        A plain filesystem copy of each image file into the current host
        directory, applying destination-conflict resolution (FR-145–FR-147) but
        no 8.3 validation (the out direction produces ordinary host files).

        Satisfies: FR-176.
        """
        if not self._image_workdir:
            return
        widget = cast("QWidget", self)
        workdir = self._image_workdir
        policy: str | None = None
        copied = 0
        for name in names:
            dest = os.path.join(self.host_dir, name)
            if os.path.exists(dest):
                action, policy = self._resolve_conflict_local(name, "host", policy)
                if action == CANCEL:
                    break
                if action == SKIP:
                    continue
            try:
                shutil.copy2(os.path.join(workdir, name), dest)
            except OSError as exc:
                QMessageBox.critical(
                    widget, tr("dialog.error.title"), tr("error.image_copy", error=exc)
                )
                break
            self._record_history(name, dest, "host", "success", os.path.getsize(dest), "", False)
            copied += 1
        self.refresh_host_files()
        self.set_status(tr("status.image_copy_out", count=copied))

    def _prompt_invalid_name_local(self, name: str) -> tuple[str, str]:
        """GUI-thread CP/M 8.3 name-validation prompt for the local copy (FR-176).

        The serial upload path marshals this dialog from a worker thread via a
        signal (`_prompt_invalid_name`); the local host→image copy runs on the GUI
        thread, so it builds the identical dialog directly. Returns
        ``(action, new_name)``.

        Satisfies: FR-176, FR-148, FR-149.
        """
        suggested = CPMParser.suggest_8_3(name)
        dialog = FilenameValidationDialog(cast("QWidget", self), name, suggested)
        dialog.exec()
        return dialog.action, dialog.new_name

    def _resolve_conflict_local(
        self, name: str, direction: str, policy: str | None
    ) -> tuple[str, str | None]:
        """GUI-thread destination-conflict prompt for the local copy (FR-176).

        Returns ``(action, updated_policy)``; a batch-wide Overwrite/Skip policy
        set via the dialog's "apply to all" suppresses further prompts, mirroring
        the serial path's ``_resolve_conflict``.

        Satisfies: FR-176, FR-146, FR-147.
        """
        if policy is not None:
            return policy, policy
        dialog = FileConflictDialog(cast("QWidget", self), name, direction)
        dialog.exec()
        action, apply_to_all = dialog.action, dialog.apply_to_all
        if apply_to_all and action != CANCEL:
            policy = action
        return action, policy

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

        Each file is read from its own user area (FR-185) — so a name present in
        more than one area reads the correct content rather than the first extent
        found — and staged under a host filename that is disambiguated when the
        same name occurs in a second area (``FOO.COM`` then ``FOO~3.COM``), so no
        file is silently overwritten. ``self._image_stage_map`` records each
        staged filename's real CP/M name and source area for the pane's area
        column (UIR-119), area-preserving transfer (FR-188) and write-back
        (FR-187). Corruption of an individual file is tolerated (best-effort
        listing) rather than aborting the whole open (FR-172).

        Satisfies: FR-171, FR-172, FR-185.
        """
        failed: list[str] = []
        self._image_stage_map = {}
        used_names: set[str] = set()
        for entry in img.list_files():
            cpm_name = os.path.basename(entry.name)
            staged = self._unique_staged_name(cpm_name, entry.user, used_names)
            try:
                data = img.read_file(entry.name, user=entry.user)
                with open(os.path.join(workdir, staged), "wb") as fh:
                    fh.write(data)
            except (KeyError, OSError, ValueError):
                failed.append(entry.name)
                continue
            used_names.add(staged.upper())
            self._image_stage_map[staged] = (cpm_name, entry.user)
        return failed

    @staticmethod
    def _unique_staged_name(cpm_name: str, user: int, used: set[str]) -> str:
        """Return a host filename for ``cpm_name`` unique within ``used`` (FR-185).

        The common case (a name in a single user area) stages under the CP/M name
        unchanged. When the same name already occurs in another area the area is
        woven into the base (``FOO.COM`` → ``FOO~3.COM``), and a numeric suffix is
        added if even that collides, so distinct files never overwrite one another
        in the flat working directory.

        Satisfies: FR-185.
        """
        if cpm_name.upper() not in used:
            return cpm_name
        base, dot, ext = cpm_name.partition(".")
        suffix = f"~{user}"
        candidate = f"{base}{suffix}{dot}{ext}"
        n = 1
        while candidate.upper() in used:
            candidate = f"{base}{suffix}_{n}{dot}{ext}"
            n += 1
        return candidate

    def _cleanup_image_workdir(self) -> None:
        """Remove the current image working directory, if any (FR-016, FR-019, FR-171).

        Called when opening another image, on File > New, on Close Disk Image…
        (FR-177), and on application exit.

        Satisfies: FR-171, FR-176, FR-177.
        """
        # FR-176: note a Remote-pane mount before clearing state, so the Remote
        # pane can be reset to a real-device view below.
        was_remote_image = self._image_workdir is not None and self._image_pane == "remote"
        if self._image_workdir and os.path.isdir(self._image_workdir):
            shutil.rmtree(self._image_workdir, ignore_errors=True)
        self._image_workdir = None
        self._image_source = None
        self._image_geom = None
        # FR-175: no image open → no clean baseline to compare against.
        self._image_baseline = None
        # FR-177: no image open → nothing to restore on close.
        self._pre_image_host_dir = None
        # FR-176: no image open → the Remote pane is a real device again. Re-enable
        # the drive drop-down, clear a stale image listing, and restore the title.
        self._image_pane = "host"
        drive_combo = getattr(self, "drive_combo", None)
        if drive_combo is not None:
            drive_combo.setEnabled(True)
        if was_remote_image:
            self._remote_files = []
            self.remote_list.clear()
        self._update_remote_group_title()
        # FR-173/UIR-109: no image open → clear its metadata and disable the
        # Image Details… action. FR-185: drop the staged-name→area map too.
        self._image_files = []
        self._image_stage_map = {}
        if self._image_details_action is not None:
            self._image_details_action.setEnabled(False)
        # UIR-113: no image open → Close Disk Image… is disabled too.
        if self._close_image_action is not None:
            self._close_image_action.setEnabled(False)
        # UIR-110: no image open → Save Image… is disabled too.
        self._update_save_image_action()
