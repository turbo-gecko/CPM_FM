"""Application visual theme.

Implements the v1.3 Material Design theme (SRS docs/cpm_fm_requirements.md,
UIR-070, UIR-073, CR-013): a single ``qt-material`` stylesheet is applied to the
whole ``QApplication`` at start-up, with the light/dark variant chosen to follow
the host operating system's colour-scheme preference.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

# Material theme variants (qt-material ships these XML palettes).
DARK_THEME = "dark_blue.xml"
LIGHT_THEME = "light_blue.xml"


def prefers_dark(app: QApplication) -> bool:
    """Return True if the OS colour scheme is dark or undetermined.

    UIR-073: follow the OS light/dark preference; default to dark when the
    preference cannot be determined.
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
    """
    from qt_material import apply_stylesheet

    theme = DARK_THEME if prefers_dark(app) else LIGHT_THEME
    apply_stylesheet(app, theme=theme)
    return theme
