from __future__ import annotations

from PySide6.QtCore import QByteArray, QSettings
from PySide6.QtWidgets import QWidget

# QSettings storage identity. On Windows these map to a registry key under
# HKEY_CURRENT_USER\Software\<ORG>\<APP>; on other platforms to a native config
# file. Kept here (rather than relying on QCoreApplication's org/app names) so
# WindowState works even before those are set and is easy to override in tests.
ORG = "turbo-gecko"
APP = "cpm-fm"


class WindowState:
    """Persists window/dialog geometry and the last-used config file (FR-004/FR-005).

    Window geometry is stored as the opaque blob produced by
    ``QWidget.saveGeometry`` (which captures size, position and maximised/normal
    state) and restored with ``QWidget.restoreGeometry``. This is UI/session
    state, deliberately kept separate from the user's serial-configuration JSON
    files handled by :class:`~cpm_fm.utils.config_handler.ConfigHandler`.

    A :class:`QSettings` instance may be injected (tests pass an isolated,
    temporary store so they do not touch the host's real settings).

    Satisfies: FR-004, FR-005.
    """

    def __init__(self, settings: QSettings | None = None) -> None:
        """Satisfies: FR-004, FR-005."""
        self._settings = settings if settings is not None else QSettings(ORG, APP)

    def save_geometry(self, name: str, widget: QWidget) -> None:
        """Satisfies: FR-004."""
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
        """Satisfies: FR-005."""
        self._settings.setValue("last_config", path)
