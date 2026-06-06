from __future__ import annotations

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


class TerminalWindow(QMainWindow):
    """
    Non-modal Terminal window (SRS docs/cpm_fm_requirements.md, UIR-060-UIR-067;
    receive/transmit behaviour FR-090-FR-098).
    """

    def __init__(self, parent, send_callback, clear_callback=None):
        # No Qt parent, so this is an independent non-modal top-level window
        # (UIR-060). The owning MainWindow keeps a reference to it.
        super().__init__()
        self.setWindowTitle("Terminal")
        self.resize(600, 400)
        self.send_callback = send_callback
        # Invoked when the Clear button is pressed, so the owner can clear the
        # receive/transmit data buffers alongside the display (FR-090/FR-092).
        self.clear_callback = clear_callback

        self.create_widgets()

    def create_widgets(self):
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
        self.btn_clear = QPushButton("Clear", clicked=self.clear_text)
        ctrl_layout.addWidget(self.btn_clear)
        ctrl_layout.addStretch()

        self.chk_echo = QCheckBox("Local Echo")  # UIR-065: disabled by default.
        self.chk_echo.setChecked(False)
        ctrl_layout.addWidget(self.chk_echo)
        ctrl_layout.addStretch()

        self.chk_scroll = QCheckBox("Autoscroll")  # UIR-066: enabled by default.
        self.chk_scroll.setChecked(True)
        ctrl_layout.addWidget(self.chk_scroll)
        layout.addLayout(ctrl_layout)

        # Transmit Frame: text field (left) + Send button (right) (UIR-067).
        tx_layout = QHBoxLayout()
        self.tx_entry = QLineEdit()
        self.tx_entry.returnPressed.connect(self.send_text)
        tx_layout.addWidget(self.tx_entry)
        self.btn_send = QPushButton("Send", clicked=self.send_text)
        tx_layout.addWidget(self.btn_send)
        layout.addLayout(tx_layout)

    def clear_text(self):
        self.receive_area.clear()
        if self.clear_callback:
            self.clear_callback()

    def send_text(self):
        text = self.tx_entry.text()
        if text:
            self.send_callback(text)
            self.tx_entry.clear()

    def write_text(self, text):
        """Appends text to the receive area."""
        # insertPlainText preserves existing content and does not add newlines.
        cursor = self.receive_area.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text)
        if self.chk_scroll.isChecked():  # UIR-062: autoscroll when enabled.
            self.receive_area.moveCursor(QTextCursor.MoveOperation.End)
            self.receive_area.ensureCursorVisible()

    def closeEvent(self, event):
        # Non-modal window persists in the background when closed by the user;
        # FR-097 reopens/restores the same instance via the Terminal button.
        event.ignore()
        self.hide()
