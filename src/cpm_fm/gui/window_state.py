from __future__ import annotations

from PySide6.QtCore import QByteArray, QSettings
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QWidget

from cpm_fm.utils.i18n import DEFAULT_LANGUAGE

# QSettings storage identity. On Windows these map to a registry key under
# HKEY_CURRENT_USER\Software\<ORG>\<APP>; on other platforms to a native config
# file. Kept here (rather than relying on QCoreApplication's org/app names) so
# WindowState works even before those are set and is easy to override in tests.
ORG = "turbo-gecko"
APP = "cpm-fm"


def default_terminal_font() -> QFont:
    """The Terminal Window Receive view's default font (UIR-069).

    A monospaced Courier New — the historic hard-coded terminal font, now the
    fallback when the user has not chosen one.

    Satisfies: UIR-069.
    """
    font = QFont("Courier New")
    font.setStyleHint(QFont.StyleHint.Monospace)
    return font


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

    @property
    def terminal_font(self) -> QFont:
        """The Terminal Window Receive view font (a monospaced Courier New default).

        Like the language and geometry, this is a global UI preference stored in
        QSettings rather than the per-config serial JSON, so the chosen terminal
        font persists across sessions independently of which configuration is
        loaded. The font round-trips through the string form produced by
        ``QFont.toString()``; a missing or unparseable value yields the default.

        Satisfies: UIR-069.
        """
        value = self._settings.value("terminal_font", "")
        if isinstance(value, str) and value:
            font = QFont()
            if font.fromString(value):
                return font
        return default_terminal_font()

    @terminal_font.setter
    def terminal_font(self, font: QFont) -> None:
        """
        Satisfies: UIR-069.
        """
        self._settings.setValue("terminal_font", font.toString())

    # --------------------------------------------------- open-window restoration

    # FR-168: which auxiliary windows were open when the application last closed,
    # so they can be reopened on the next start-up. Like geometry and language,
    # this is UI/session state kept in QSettings (not the per-config serial JSON),
    # stored per window under a distinct ``open/<name>`` key. ``name`` is a stable
    # window identifier such as "terminal" or "history".

    def window_open(self, name: str) -> bool:
        """Whether window ``name`` was recorded open at the last exit.

        QSettings round-trips booleans as the strings "true"/"false" through an
        INI backend, so accept either a real bool or that string form.

        Satisfies: FR-168.
        """
        value = self._settings.value(f"open/{name}", False)
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("1", "true", "yes")

    def set_window_open(self, name: str, is_open: bool) -> None:
        """Record whether window ``name`` is open (persisted for restart restore).

        Satisfies: FR-168.
        """
        self._settings.setValue(f"open/{name}", bool(is_open))

    # ------------------------------------------------- file-list filter / sort

    # FR-134: the last-used filter text and sort settings for each file pane are
    # UI/session preferences (like geometry and language), so they live here in
    # QSettings rather than in the per-config serial JSON. ``pane`` is "host" or
    # "remote"; the values are stored under distinct keys so the two panes are
    # independent.

    def filter_text(self, pane: str) -> str:
        """The persisted filter text for ``pane`` ("" if none).

        Satisfies: FR-134.
        """
        value = self._settings.value(f"filter/{pane}/text", "")
        return value if isinstance(value, str) else ""

    def set_filter_text(self, pane: str, text: str) -> None:
        """
        Satisfies: FR-134.
        """
        self._settings.setValue(f"filter/{pane}/text", text)

    def sort_key(self, pane: str) -> str:
        """The persisted sort key for ``pane`` (defaults to name order).

        Satisfies: FR-134.
        """
        value = self._settings.value(f"filter/{pane}/sort_key", "name")
        return value if isinstance(value, str) and value else "name"

    def set_sort_key(self, pane: str, key: str) -> None:
        """
        Satisfies: FR-134.
        """
        self._settings.setValue(f"filter/{pane}/sort_key", key)

    def sort_descending(self, pane: str) -> bool:
        """Whether ``pane`` sorts descending (defaults to ascending).

        QSettings round-trips booleans as the strings "true"/"false" through an
        INI backend, so accept either a real bool or that string form.

        Satisfies: FR-134.
        """
        value = self._settings.value(f"filter/{pane}/sort_desc", False)
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("1", "true", "yes")

    def set_sort_descending(self, pane: str, descending: bool) -> None:
        """
        Satisfies: FR-134.
        """
        self._settings.setValue(f"filter/{pane}/sort_desc", bool(descending))
