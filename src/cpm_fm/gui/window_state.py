from __future__ import annotations

from PySide6.QtCore import QByteArray, QSettings
from PySide6.QtWidgets import QWidget

from cpm_fm.utils.i18n import DEFAULT_LANGUAGE

# QSettings storage identity. On Windows these map to a registry key under
# HKEY_CURRENT_USER\Software\<ORG>\<APP>; on other platforms to a native config
# file. Kept here (rather than relying on QCoreApplication's org/app names) so
# WindowState works even before those are set and is easy to override in tests.
ORG = "turbo-gecko"
APP = "cpm-fm"


class WindowState:
    """Persists window/dialog geometry and the last-used config file/folder.

    Window geometry is stored as the opaque blob produced by
    ``QWidget.saveGeometry`` (which captures size, position and maximised/normal
    state) and restored with ``QWidget.restoreGeometry``. This is UI/session
    state, deliberately kept separate from the user's serial-configuration JSON
    files handled by :class:`~cpm_fm.utils.config_handler.ConfigHandler`.

    The folder of the most recently loaded/saved config file (``last_config_dir``)
    is also persisted here, so the Load/Save dialogs reopen where the user last
    worked with configuration files. It is deliberately distinct from the Host
    Files directory (FR-060), which is stored per-config in the JSON itself.

    A :class:`QSettings` instance may be injected (tests pass an isolated,
    temporary store so they do not touch the host's real settings).

    Satisfies: FR-004, FR-005, FR-006.
    """

    def __init__(self, settings: QSettings | None = None) -> None:
        """
        Satisfies: FR-004, FR-005.
        """
        self._settings = settings if settings is not None else QSettings(ORG, APP)

    def save_geometry(self, name: str, widget: QWidget) -> None:
        """
        Satisfies: FR-004.
        """
        self._settings.setValue(f"geometry/{name}", widget.saveGeometry())

    def restore_geometry(self, name: str, widget: QWidget) -> bool:
        """Restore ``widget``'s saved geometry; return True if any was applied.

        Satisfies: FR-004.
        """
        value = self._settings.value(f"geometry/{name}")
        if isinstance(value, QByteArray) and not value.isEmpty():
            return widget.restoreGeometry(value)
        return False

    @property
    def last_config(self) -> str:
        """Path of the most recently loaded/saved config file ("" if none).

        Satisfies: FR-005.
        """
        value = self._settings.value("last_config", "")
        return value if isinstance(value, str) else ""

    @last_config.setter
    def last_config(self, path: str) -> None:
        """
        Satisfies: FR-005.
        """
        self._settings.setValue("last_config", path)

    @property
    def last_config_dir(self) -> str:
        """Folder the Load/Save config dialogs should default to ("" if none).

        Distinct from the Host Files directory (FR-060); see the class docstring.

        Satisfies: FR-006.
        """
        value = self._settings.value("last_config_dir", "")
        return value if isinstance(value, str) else ""

    @last_config_dir.setter
    def last_config_dir(self, path: str) -> None:
        """
        Satisfies: FR-006.
        """
        self._settings.setValue("last_config_dir", path)

    @property
    def language(self) -> str:
        """The active GUI language name, defaulting to English ("english").

        This is a global UI preference (like geometry and the last-used config
        file), deliberately kept in QSettings rather than the per-config serial
        JSON, so it persists independently of which configuration is loaded.

        Satisfies: FR-124.
        """
        value = self._settings.value("language", DEFAULT_LANGUAGE)
        return value if isinstance(value, str) and value else DEFAULT_LANGUAGE

    @language.setter
    def language(self, name: str) -> None:
        """
        Satisfies: FR-122, FR-124.
        """
        self._settings.setValue("language", name)
