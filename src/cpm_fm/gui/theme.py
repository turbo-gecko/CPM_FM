"""Application visual theme.

Implements the v1.3 Material Design theme (SRS docs/cpm_fm_requirements.md,
UIR-070, UIR-073, CR-013): a single ``qt-material`` stylesheet is applied to the
whole ``QApplication`` at start-up, with the light/dark variant chosen to follow
the host operating system's colour-scheme preference.
"""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

# Material theme variants (qt-material ships these XML palettes).
DARK_THEME = "dark_blue.xml"
LIGHT_THEME = "light_blue.xml"

# DR-044: the runtime window/taskbar icon ships as package data at
# cpm_fm/icons/cpm-fm.png. This module lives at cpm_fm/gui/theme.py, so the
# package root is one directory up. Resolving relative to __file__ keeps the
# lookup working in a source checkout and in a PyInstaller bundle alike (the
# spec bundles the file at the matching cpm_fm/icons destination).
APP_ICON_PATH = Path(__file__).resolve().parent.parent / "icons" / "cpm-fm.png"


def prefers_dark(app: QApplication) -> bool:
    """Return True if the OS colour scheme is dark or undetermined.

    UIR-073: follow the OS light/dark preference; default to dark when the
    preference cannot be determined.

    Satisfies: UIR-073.
    """
    try:
        scheme = app.styleHints().colorScheme()
    except (AttributeError, TypeError):
        # colorScheme() requires Qt 6.5+; treat anything older as "unknown".
        return True
    # Qt.ColorScheme.Light is an explicit light preference; Dark and Unknown
    # both resolve to the dark variant per UIR-073.
    return scheme != Qt.ColorScheme.Light


def apply_theme(app: QApplication) -> str:
    """Apply the Material theme to ``app`` and return the theme name used.

    CR-013: the stylesheet is applied centrally to the QApplication so every
    current and future window inherits it.

    Satisfies: UIR-070, UIR-073, CR-013.
    """
    from qt_material import apply_stylesheet

    theme = DARK_THEME if prefers_dark(app) else LIGHT_THEME
    apply_stylesheet(app, theme=theme)
    return theme


def app_icon() -> QIcon:
    """Return the application icon, or an empty ``QIcon`` if it is missing.

    The icon is set once on the ``QApplication`` (see ``app.py:main``) so every
    current and future window, dialog, and the OS taskbar/dock entry inherit the
    branded icon. The icon file is optional: a missing file yields an empty
    ``QIcon`` (Qt's default icon), exactly as a missing packaging icon does
    (CR-006), so start-up never fails on its absence.

    Satisfies: UIR-078, DR-044.
    """
    if APP_ICON_PATH.is_file():
        return QIcon(str(APP_ICON_PATH))
    return QIcon()
