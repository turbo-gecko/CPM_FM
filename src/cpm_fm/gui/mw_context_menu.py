from __future__ import annotations

import os
import threading

from PySide6.QtWidgets import QDialog, QMenu, QMessageBox

from cpm_fm.gui.file_action_dialog import FileActionDialog
from cpm_fm.gui.mw_base import MainWindowMixinBase
from cpm_fm.utils.i18n import tr
from cpm_fm.utils.temp_cleanup import make_temp_dir


class _ContextMenuMixin(MainWindowMixinBase):
    """Right-click file actions for :class:`~cpm_fm.app.MainWindow` (mixin).

    The Host/Remote context menus (FR-110/FR-111) and the actions they invoke:
    To Remote / To Host (reusing the batch transfers), View/Edit, Rename, and
    Delete for both panes (FR-114-FR-119), plus the remote-view download worker
    (FR-113) and the remote file-management command workers (FR-117/FR-118).
    The viewer launcher (``_open_in_viewer``/``_os_open``) and
    ``build_viewer_args`` remain in :mod:`cpm_fm.app`.
    """

    def _context_menu_targets(self, list_widget, pos):
        """
        Resolve the file under the cursor and the set of files an action applies
        to for a right-click context menu (FR-110, FR-111).

        Returns ``(name, names)`` where ``name`` is the single file under the
        cursor (the target of the single-file actions) and ``names`` is the list
        of files Delete applies to: the current selection when the clicked file
        is part of it, otherwise just the clicked file. Returns ``(None, [])``
        when the click was not over an item.

        Satisfies: FR-110, FR-111.
        """
        item = list_widget.itemAt(pos)
        if item is None:
            return None, []
        name = item.text()
        names = self._selected_filenames(list_widget)
        if name not in names:
            names = [name]
        return name, names

    def _host_context_menu(self, pos):
        """
        Satisfies: FR-110, FR-119, UIR-018.

        Right-click menu for the Host Files list: To Remote, View/Edit, Rename,
        Delete. To Remote and Delete act on every selected file; View/Edit and
        Rename act on the file under the cursor and are disabled when more than
        one file is selected.
        """
        name, names = self._context_menu_targets(self.host_list, pos)
        if name is None:
            return
        single = len(names) == 1
        menu = QMenu(self)
        menu.addAction(tr("ctxmenu.to_remote"), lambda names=names: self._host_to_remote(names))
        menu.addSeparator()
        menu.addAction(tr("ctxmenu.view_edit"), lambda: self._host_view(name)).setEnabled(single)
        menu.addAction(tr("ctxmenu.rename"), lambda: self._host_rename(name)).setEnabled(single)
        menu.addAction(tr("ctxmenu.delete"), lambda names=names: self._host_delete(names))
        menu.exec(self.host_list.mapToGlobal(pos))

    def _remote_context_menu(self, pos):
        """
        Satisfies: FR-111, FR-119, UIR-019.

        Right-click menu for the Remote Files list: To Host, View, Rename,
        Delete. To Host and Delete act on every selected file; View and Rename
        act on the file under the cursor and are disabled when more than one
        file is selected.
        """
        name, names = self._context_menu_targets(self.remote_list, pos)
        if name is None:
            return
        single = len(names) == 1
        menu = QMenu(self)
        menu.addAction(tr("ctxmenu.to_host"), lambda names=names: self._remote_to_host(names))
        menu.addSeparator()
        menu.addAction(tr("ctxmenu.view"), lambda: self._remote_view(name)).setEnabled(single)
        menu.addAction(tr("ctxmenu.rename"), lambda: self._remote_rename(name)).setEnabled(single)
        menu.addAction(tr("ctxmenu.delete"), lambda names=names: self._remote_delete(names))
        menu.exec(self.remote_list.mapToGlobal(pos))

    def _host_to_remote(self, names):
        """
        Satisfies: FR-119, FR-080, FR-106, FR-107, CR-010.

        Copy every selected host file to the remote, reusing the Copy to Remote
        batch transfer (FR-099/FR-105, sequential per FR-106/FR-107). Accepts a
        single filename or a list of filenames.
        """
        names = [names] if isinstance(names, str) else list(names)
        if not (self.serial_mgr.terminal_connected and self.serial_mgr.transport_connected):
            QMessageBox.critical(
                self, tr("dialog.error.title"), tr("error.transport_not_connected")
            )
            return
        if not names:
            return
        filepaths = [os.path.join(self.host_dir, name) for name in names]
        threading.Thread(
            target=self._transfer_to_remote_batch, args=(filepaths,), daemon=True
        ).start()

    def _remote_to_host(self, names):
        """
        Satisfies: FR-119, FR-080, FR-106, FR-107, CR-010.

        Copy every selected remote file to the host, reusing the Copy to Host
        batch transfer (FR-099/FR-105, sequential per FR-106/FR-107). Accepts a
        single filename or a list of filenames.
        """
        names = [names] if isinstance(names, str) else list(names)
        if not (self.serial_mgr.terminal_connected and self.serial_mgr.transport_connected):
            QMessageBox.critical(
                self, tr("dialog.error.title"), tr("error.transport_not_connected")
            )
            return
        if not names:
            return
        save_paths = [os.path.join(self.host_dir, name) for name in names]
        threading.Thread(
            target=self._transfer_to_host_batch, args=(save_paths,), daemon=True
        ).start()

    def _host_view(self, name):
        """
        Satisfies: FR-110, FR-112.
        """
        self._open_in_viewer(os.path.join(self.host_dir, name))

    def _host_rename(self, name):
        """
        Satisfies: FR-110, FR-114, FR-116, FR-118.
        """
        dlg = FileActionDialog(self, tr("dialog.rename_file.title"), name, editable=True)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        new_name = dlg.value().strip()
        if not new_name or new_name == name:
            return
        try:
            os.rename(os.path.join(self.host_dir, name), os.path.join(self.host_dir, new_name))
        except OSError as e:
            QMessageBox.critical(self, tr("dialog.error.title"), tr("error.rename_failed", error=e))
            return
        self.refresh_host_files()

    def _host_delete(self, names):
        """
        Delete every selected host file (FR-110), confirming all of them in one
        modal dialog (FR-115) and refreshing the Host Files list afterwards.
        Files that delete successfully stay deleted even if a later file fails;
        any failures are reported together (FR-116).

        Accepts either a single filename or a list of filenames.

        Satisfies: FR-110, FR-115, FR-116, FR-118.
        """
        names = [names] if isinstance(names, str) else list(names)
        if not names:
            return
        single = len(names) == 1
        prompt = (
            tr("dialog.delete_file.prompt")
            if single
            else tr("dialog.delete_file.prompt_multi", count=len(names))
        )
        dlg = FileActionDialog(
            self,
            tr("dialog.delete_file.title"),
            names[0],
            editable=False,
            prompt=prompt,
            filenames=names,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        errors = []
        for name in names:
            try:
                os.remove(os.path.join(self.host_dir, name))
            except OSError as e:
                errors.append(str(e))
        self.refresh_host_files()
        if errors:
            QMessageBox.critical(
                self, tr("dialog.error.title"), tr("error.delete_failed", error="\n".join(errors))
            )

    def _remote_view(self, name):
        """
        Satisfies: FR-111, FR-113.

        Download the remote file to a temporary folder over X-Modem, then open
        it in the viewer (FR-112). Permitted only when both status flags are
        connected (FR-080/CR-010). Runs the download on a worker thread.
        """
        if not (self.serial_mgr.terminal_connected and self.serial_mgr.transport_connected):
            QMessageBox.critical(
                self, tr("dialog.error.title"), tr("error.transport_not_connected")
            )
            return
        threading.Thread(target=self._download_and_view, args=(name,), daemon=True).start()

    def _download_and_view(self, name):
        """
        Satisfies: FR-113.

        Worker thread: receive ``name`` into a temp folder via the Copy to Host
        transfer process, then request the viewer on the GUI thread via the
        view_file_ready signal (NFR-004). The progress dialog (FR-105) is driven
        by the same batch signals as a normal transfer.
        """
        save_path = os.path.join(make_temp_dir(), name)
        self._transfer_cancel.clear()  # FR-120: start un-cancelled.
        self.batch_started.emit("host", 1)
        self.set_status(tr("status.downloading_for_viewing", name=name))
        self.transfer_file_started.emit(name, 0, 1)
        try:
            ok = self._recv_one_to_host(save_path)
        except Exception as e:
            self._debug(f"[remote-view] EXCEPTION: {e!r}")
            self.error_raised.emit(tr("dialog.error.title"), str(e))
            return
        if not ok:
            # FR-120: a cancelled download just closes the dialog (no viewer).
            if self._transfer_cancel.is_set():
                self._finish_cancelled_batch("host", 0)
                return
            self.error_raised.emit(
                tr("dialog.xmodem_error.title"), tr("error.download_failed", name=name)
            )
            return
        self.view_file_ready.emit(save_path)

    def _on_view_file_ready(self, path):
        """
        Satisfies: FR-112, FR-113.

        Runs on the GUI thread (queued from the remote-view worker). Close the
        progress dialog and open the downloaded file in the viewer.
        """
        self._close_transfer_dialog()
        self.set_status(tr("status.opening_viewer"))
        self._open_in_viewer(path)

    def _remote_rename(self, name):
        """
        Satisfies: FR-111, FR-114, FR-117, FR-118.
        """
        if not self.serial_mgr.terminal_connected:
            self.set_status(tr("status.terminal_not_open_rename"))
            return
        dlg = FileActionDialog(self, tr("dialog.rename_remote.title"), name, editable=True)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        new_name = dlg.value().strip()
        if not new_name or new_name == name:
            return
        template = self.settings.get("rename_remote_cmd", "REN $2=$1")
        if not template:
            return
        cmd = template.replace("$2", new_name).replace("$1", name)
        threading.Thread(target=self._do_remote_file_cmd, args=(cmd,), daemon=True).start()

    def _remote_delete(self, names):
        """
        Delete every selected remote file (FR-111) by sending the configured
        delete command once per file on the Terminal Port, confirming all of
        them in one modal dialog (FR-115). Accepts a single filename or a list.

        Satisfies: FR-111, FR-115, FR-117, FR-118.
        """
        names = [names] if isinstance(names, str) else list(names)
        if not self.serial_mgr.terminal_connected:
            self.set_status(tr("status.terminal_not_open_delete"))
            return
        if not names:
            return
        single = len(names) == 1
        prompt = (
            tr("dialog.delete_remote.prompt")
            if single
            else tr("dialog.delete_remote.prompt_multi", count=len(names))
        )
        dlg = FileActionDialog(
            self,
            tr("dialog.delete_remote.title"),
            names[0],
            editable=False,
            prompt=prompt,
            filenames=names,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        template = self.settings.get("delete_remote_cmd", "ERA $1")
        if not template:
            return
        cmds = [template.replace("$1", name) for name in names]
        threading.Thread(target=self._do_remote_file_cmds, args=(cmds,), daemon=True).start()

    def _do_remote_file_cmd(self, cmd):
        """
        Satisfies: FR-117, FR-118.

        Worker thread: send a single remote file-management command (Rename).
        Delegates to _do_remote_file_cmds, which sends the command, waits for the
        output to go idle, and refreshes the Remote Files list.
        """
        self._do_remote_file_cmds([cmd])

    def _do_remote_file_cmds(self, cmds):
        """
        Satisfies: FR-117, FR-118.

        Worker thread: send one or more remote file-management commands on the
        Terminal Port in order, waiting for each command's output to go idle
        (reusing the capture mechanism), then refresh the Remote Files list once
        (FR-074-FR-079). _do_refresh_remote_logic marshals its UI update via the
        remote_files_ready signal (NFR-004).
        """
        for cmd in cmds:
            self.set_status(tr("status.executing", cmd=cmd))
            self._capture_terminal_response(cmd)
        self._do_refresh_remote_logic()
