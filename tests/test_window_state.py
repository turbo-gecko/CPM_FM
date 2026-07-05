"""Tests for WindowState UI-preference persistence.

Headless under the offscreen Qt platform, backed by a temporary INI-format
QSettings so the tests never read or write the host's real settings store.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtGui import QFont  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from cpm_fm.gui.window_state import WindowState, default_terminal_font  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def state(tmp_path, qapp):
    settings = QSettings(str(tmp_path / "state.ini"), QSettings.Format.IniFormat)
    return WindowState(settings)


def test_terminal_font_default_when_unset(state):
    """An unset store yields the monospaced Courier New default.

    Verifies: UIR-069.
    """
    font = state.terminal_font
    assert font.family() == "Courier New"
    assert font.styleHint() == QFont.StyleHint.Monospace


def test_terminal_font_roundtrip(state):
    """Setting then reading terminal_font returns an equivalent font.

    Verifies: UIR-069.
    """
    chosen = QFont("Arial", 14)
    chosen.setBold(True)
    state.terminal_font = chosen
    restored = state.terminal_font
    assert restored.family() == "Arial"
    assert restored.pointSize() == 14
    assert restored.bold() is True


def test_terminal_font_persists_across_instances(tmp_path, qapp):
    """The chosen font survives a fresh WindowState over the same store.

    Verifies: UIR-069.
    """
    path = str(tmp_path / "state.ini")
    ws1 = WindowState(QSettings(path, QSettings.Format.IniFormat))
    ws1.terminal_font = QFont("Consolas", 16)

    ws2 = WindowState(QSettings(path, QSettings.Format.IniFormat))
    restored = ws2.terminal_font
    assert restored.family() == "Consolas"
    assert restored.pointSize() == 16


def test_default_terminal_font_is_monospace():
    """The default helper returns a monospaced Courier New.

    Verifies: UIR-069.
    """
    font = default_terminal_font()
    assert font.family() == "Courier New"
    assert font.styleHint() == QFont.StyleHint.Monospace
