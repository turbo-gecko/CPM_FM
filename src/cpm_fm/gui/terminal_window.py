from __future__ import annotations

from typing import Callable

from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from cpm_fm.utils.i18n import tr


class TerminalWindow(QMainWindow):
    """
    Non-modal Terminal window (SRS docs/cpm_fm_requirements.md, UIR-060-UIR-067;
    receive/transmit behaviour FR-090-FR-098).

    Satisfies: UIR-060-UIR-067.
    """

    def __init__(self, parent, send_callback, clear_callback=None):
        """
        Satisfies: UIR-060.

        No Qt parent, so this is an independent non-modal top-level window.
        The owning MainWindow keeps a reference to it.
        """
        super().__init__()
        # FR-121/FR-123: maps a widget text-setter to its translation key so the
        # window can be re-translated live when the language changes.
        self._i18n_registry: list[tuple[Callable[[str], None], str]] = []
        self._register_text(self.setWindowTitle, "terminal.title")
        self.resize(600, 400)
        self.send_callback = send_callback
        # Invoked when the Clear button is pressed, so the owner can clear the
        # receive/transmit data buffers alongside the display (FR-090/FR-092).
        self.clear_callback = clear_callback

        self.create_widgets()

    def _register_text(self, setter: Callable[[str], None], key: str) -> None:
        """Set ``setter``'s text from ``key`` now and register it for retranslation.

        Satisfies: FR-121, FR-123.
        """
        self._i18n_registry.append((setter, key))
        setter(tr(key))

    def retranslate_ui(self) -> None:
        """Re-apply the active language to this window's widgets (live).

        Satisfies: FR-123.
        """
        for setter, key in self._i18n_registry:
            setter(tr(key))

    def create_widgets(self):
        """Satisfies: UIR-061-UIR-067."""
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # Receive Area — read-only, monospaced (UIR-061/UIR-063).
        self.receive_area = QPlainTextEdit()
        self.receive_area.setReadOnly(True)
        mono = QFont("Courier New")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self.receive_area.setFont(mono)
        layout.addWidget(self.receive_area)

        # Control Frame: Clear (left), Local Echo (centre), Autoscroll (right).
        ctrl_layout = QHBoxLayout()
        self.btn_clear = QPushButton(clicked=self.clear_text)
        self._register_text(self.btn_clear.setText, "terminal.clear")
        ctrl_layout.addWidget(self.btn_clear)
        ctrl_layout.addStretch()

        self.chk_echo = QCheckBox()  # UIR-065: disabled by default.
        self._register_text(self.chk_echo.setText, "terminal.local_echo")
        self.chk_echo.setChecked(False)
        ctrl_layout.addWidget(self.chk_echo)
        ctrl_layout.addStretch()

        self.chk_scroll = QCheckBox()  # UIR-066: enabled by default.
        self._register_text(self.chk_scroll.setText, "terminal.autoscroll")
        self.chk_scroll.setChecked(True)
        ctrl_layout.addWidget(self.chk_scroll)
        layout.addLayout(ctrl_layout)

        # Transmit Frame: text field (left) + Send button (right) (UIR-067).
        tx_layout = QHBoxLayout()
        self.tx_entry = QLineEdit()
        self.tx_entry.returnPressed.connect(self.send_text)
        tx_layout.addWidget(self.tx_entry)
        self.btn_send = QPushButton(clicked=self.send_text)
        self._register_text(self.btn_send.setText, "terminal.send")
        tx_layout.addWidget(self.btn_send)
        layout.addLayout(tx_layout)

    def clear_text(self):
        """Satisfies: FR-095, UIR-064."""
        self.receive_area.clear()
        if self.clear_callback:
            self.clear_callback()

    def send_text(self):
        """Satisfies: FR-096."""
        text = self.tx_entry.text()
        if text:
            self.send_callback(text)
            self.tx_entry.clear()

    def write_text(self, text):
        """
        Appends text to the receive area.

        Satisfies: FR-091, UIR-062.

        insertPlainText preserves existing content and does not add newlines.
        """
        cursor = self.receive_area.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text)
        if self.chk_scroll.isChecked():  # UIR-062: autoscroll when enabled.
            self.receive_area.moveCursor(QTextCursor.MoveOperation.End)
            self.receive_area.ensureCursorVisible()

    def closeEvent(self, event):
        """
        Satisfies: FR-097.

        Non-modal window persists in the background when closed by the user;
        reopens/restores the same instance via the Terminal button.
        """
        event.ignore()
        self.hide()
