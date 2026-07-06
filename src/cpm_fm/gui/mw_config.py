from __future__ import annotations

import copy
import os

import serial.tools.list_ports
from PySide6.QtWidgets import QFileDialog, QMessageBox

from cpm_fm.gui.about_dialog import AboutDialog
from cpm_fm.gui.config_dialogs import (
    GeneralConfigDialog,
    MacroConfigDialog,
    SerialConfigDialog,
)
from cpm_fm.gui.manual_dialog import ManualDialog
from cpm_fm.gui.mw_base import MainWindowMixinBase
from cpm_fm.utils.config_handler import DEFAULT_SETTINGS
from cpm_fm.utils.i18n import tr


class _ConfigMixin(MainWindowMixinBase):
    """Configuration and menu-action handlers for MainWindow (mixin).

    Loading/saving configuration files (FR-005/FR-006/FR-011-FR-014), File >
    New (FR-018/FR-019), the per-dialog Serial/General config save into the
    active file (FR-020/FR-020a/FR-021/FR-021a), and the Help > Manual / About
    dialog actions (FR-022/FR-023). The dialogs themselves live in their own
    gui/ modules; this mixin wires them to the window's settings and state.
    """

    def load_config(self, filename):
        """
        Satisfies: FR-005, FR-011, FR-012, FR-017, FR-060, FR-125.
        """
        self.settings = self.config_handler.load_json(filename)
        # FR-005: remember this file so it is reloaded on the next startup.
        self.window_state.last_config = filename

        # FR-125: show the loaded config's base name (no path, no extension)
        # in the title bar.
        self._config_name = os.path.splitext(os.path.basename(filename))[0]
        self._update_window_title()

        # Restore host directory if specified in config
        host_dir = self.settings.get("host_directory")
        if host_dir:
            self.host_dir = host_dir
            self.refresh_host_files()

        # UIR-034: apply the loaded terminal emulation type to the engine so
        # received bytes are interpreted (FR-157) and cursor keys encoded
        # (FR-158a/FR-158b) per the configured type from the first connect.
        self._apply_terminal_type()

        # FR-017: the prior remote listing was captured under the previous
        # configuration and is no longer valid — clear it.
        self._clear_remote_files()
        self.set_status(tr("status.loaded_config", filename=filename))

    def _apply_terminal_type(self) -> None:
        """Configure the terminal engine from the current ``terminal_type``.

        Reads the setting (default VT100) and applies it to the shared VT-100
        engine. Called on configuration load and after a Serial Config save so
        the running Terminal Window follows the selected type (UIR-034).

        Satisfies: UIR-034, FR-157.
        """
        self._term_engine.set_terminal_type(self.settings.get("terminal_type", "VT100"))

    def menu_load(self):
        """
        Satisfies: FR-006, FR-010.
        """
        # FR-006: default to the folder used the last time a config was
        # loaded/saved, kept separate from the Host Files directory (FR-060).
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("dialog.load_config.title"),
            self.window_state.last_config_dir,
            tr("dialog.json_filter"),
        )
        if path:
            self.window_state.last_config_dir = os.path.dirname(path)
            self.load_config(path)

    def menu_save(self):
        """
        Satisfies: FR-005, FR-006, FR-013, FR-014.
        """
        # FR-006: default to the last-used config folder (see menu_load).
        path, _ = QFileDialog.getSaveFileName(
            self,
            tr("dialog.save_config.title"),
            self.window_state.last_config_dir,
            tr("dialog.json_filter"),
        )
        if path:
            self._save_to_path(path)

    def _save_to_path(self, path: str) -> bool:
        """
        Write the current settings to ``path`` and update last-used bookkeeping.

        Shared by File > Save (FR-013/FR-014) and File > New (FR-018). Returns
        True on a successful write.

        Satisfies: FR-005, FR-006, FR-014.
        """
        if not path.endswith(".json"):
            path += ".json"

        # Persist the current host directory in the settings before saving
        self.settings["host_directory"] = self.host_dir

        if self.config_handler.save_json(path, self.settings):
            # FR-005: the saved file becomes the last-used config to reload.
            self.window_state.last_config = path
            # FR-006: remember its folder for the next Load/Save dialog.
            self.window_state.last_config_dir = os.path.dirname(path)
            self.set_status(tr("status.saved_config", path=path))
            return True
        return False

    def _save_subset_to_active_config(self, subset: dict, status_key: str) -> bool:
        """Persist only ``subset`` to the currently loaded config file.

        Used by the per-dialog Save buttons (Config > Serial — FR-020a; Config >
        General — FR-021a), each of which must write only its own group of
        settings to the currently active/loaded config file and leave every
        other setting in that file untouched. The on-disk file is read, the
        subset keys overlaid, and the result written back, so keys outside the
        subset keep their stored values (unlike File > Save, which writes the
        full settings store — FR-014).

        When no config file is loaded there is no active file to write to: a
        warning is shown (FR-020a/FR-021a) and the settings remain applied to
        the running session only (the user must use File > Save to persist
        them). Returns True only when a file was written.

        Satisfies: FR-020a, FR-021a.
        """
        path = self.window_state.last_config
        if not path:
            # No active/loaded config file: nothing to write to. Warn and leave
            # the just-updated settings applied to the session only.
            QMessageBox.warning(
                self,  # type: ignore[arg-type]  # mixin is a QMainWindow at runtime
                tr("dialog.warning.title"),
                tr("warning.no_config_loaded"),
            )
            return False
        # Preserve every other setting in the file: read the current on-disk
        # contents, overlay only the subset keys, and write it back.
        on_disk = self.config_handler.load_json(path)
        on_disk.update(subset)
        if self.config_handler.save_json(path, on_disk):
            self.set_status(tr(status_key, path=path))
            return True
        return False

    def menu_new(self):
        """
        Satisfies: FR-018, FR-019.

        FR-018: save the current configuration first (to the last-used file if
        known, otherwise via the Save dialog); abort if the save is cancelled or
        fails so nothing is lost. FR-019: on a successful save, close any open
        ports, clear the Remote Files list, and replace the settings with the
        default configuration.
        """
        # FR-018: save the current configuration. Save silently to the
        # currently-loaded file if there is one, otherwise prompt with the Save
        # dialog. Abort New on cancel/failure.
        if self.window_state.last_config:
            if not self._save_to_path(self.window_state.last_config):
                return
        else:
            path, _ = QFileDialog.getSaveFileName(
                self,
                tr("dialog.save_config.title"),
                self.window_state.last_config_dir,
                tr("dialog.json_filter"),
            )
            if not path or not self._save_to_path(path):
                return

        # FR-019: close any open Terminal/Transport ports (Disconnect behaviour,
        # FR-050-FR-058) and clear the now-stale Remote Files list. do_disconnect
        # reads the port names from the current settings, so it must run before
        # the settings are reset below.
        self.do_disconnect()

        # FR-019: replace the entire settings store with the default
        # configuration (full replace, per FR-011) and forget the remembered
        # configuration file path.
        self.settings = copy.deepcopy(DEFAULT_SETTINGS)
        self.window_state.last_config = ""

        # FR-125: no config file is loaded after New — drop the config name
        # from the title bar.
        self._config_name = ""
        self._update_window_title()

        # FR-019/FR-060: refresh the Host Files list to the default host
        # directory (empty -> current working directory).
        self.host_dir = self.settings.get("host_directory") or os.getcwd()
        self.refresh_host_files()

        # FR-019: ensure the Remote Files list is empty even if no port was open.
        self._clear_remote_files()
        self.set_status(tr("status.new_config_created"))

    def menu_serial_config(self):
        """
        Satisfies: FR-020, IFR-003.

        IFR-003 / UIR-022 / UIR-023: enumerate the host's serial ports.
        """
        ports = [p.device for p in serial.tools.list_ports.comports()]

        def update_settings(new_set):
            self.settings.update(new_set)
            # UIR-034: a change to the terminal type takes effect immediately on
            # the shared engine (and any open Terminal Window).
            self._apply_terminal_type()
            # FR-020a: persist only the serial settings to the active config
            # file, leaving the general settings in that file untouched. If no
            # file is loaded the helper warns and the change stays session-only.
            if not self._save_subset_to_active_config(new_set, "status.serial_settings_saved"):
                self.set_status(tr("status.serial_settings_updated"))

        SerialConfigDialog(self, self.settings, ports, update_settings, self.window_state)

    def menu_general_config(self):
        """
        Satisfies: FR-021.
        """

        def update_settings(new_set):
            # The dialog seeds its host-directory field from the value stored in
            # settings and returns every field on save, so an unchanged field
            # carries the stored value back unchanged. Capture the stored value
            # before updating to tell an actual edit from an untouched field.
            old_host_dir = self.settings.get("host_directory", "")

            self.settings.update(new_set)

            # Only follow a host directory the user actually edited in the
            # dialog. If the field came back unchanged, leave the currently
            # selected directory alone — it may have been changed via Change
            # Directory since the config was loaded, and saving unrelated
            # general settings must not revert it.
            new_host_dir = new_set.get("host_directory", old_host_dir)
            if new_host_dir and new_host_dir != old_host_dir:
                self.host_dir = new_host_dir
                self.refresh_host_files()

            # UIR-068: a change to the boot sequence may enable/disable the
            # Terminal Window's boot button while that window is open.
            self._refresh_boot_button()

            # FR-021a: persist only the general settings to the active config
            # file, leaving the serial settings in that file untouched. If no
            # file is loaded the helper warns and the change stays session-only.
            if not self._save_subset_to_active_config(new_set, "status.general_settings_saved"):
                self.set_status(tr("status.general_settings_updated"))

        GeneralConfigDialog(self, self.settings, update_settings, self.window_state)

    def menu_macro_config(self):
        """
        Satisfies: FR-021b, UIR-098.
        """

        def update_settings(new_set):
            self.settings.update(new_set)
            # UIR-097: reflect the edited macro definitions in the live Macro
            # Window if it is open.
            self._refresh_macro_buttons()
            # FR-021b: persist only the macro settings to the active config file,
            # leaving the serial/general settings untouched. If no file is loaded
            # the helper warns and the change stays session-only.
            if not self._save_subset_to_active_config(new_set, "status.macro_settings_saved"):
                self.set_status(tr("status.macro_settings_updated"))

        MacroConfigDialog(self, self.settings, update_settings, self.window_state)

    def menu_manual(self):
        """Present the non-modal user-manual viewer (Help > Manual).

        The window is reused across invocations: if it is already open it is
        raised and activated rather than opening a second copy.

        Satisfies: FR-023, UIR-091.
        """
        existing = getattr(self, "_manual_dialog", None)
        if existing is not None and existing.isVisible():
            existing.raise_()
            existing.activateWindow()
            return
        dialog = ManualDialog(self)
        self._manual_dialog = dialog
        dialog.show()

    def menu_about(self):
        """
        Satisfies: FR-022, UIR-076.

        Present the modal About dialog (program name, version, GitHub link, OK).
        """
        AboutDialog(self).exec()
