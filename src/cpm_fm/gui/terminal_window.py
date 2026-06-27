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
        """Satisfies: FR-096.

        Sends the contents of the transmit field. Two behaviours beyond a plain
        text send:

        * An empty field sends a bare end-of-line (the owner appends the
          configured EOL), so the user can transmit a lone <Enter>.
        * Caret notation (``^A``..``^Z``, ``^@``, ``^[``, ``^\\``, ``^]``,
          ``^_``, ``^?``) is interpreted as the corresponding control byte;
          ``^^`` is an escape for a literal caret. When the field resolves to
          control bytes only, no EOL is appended so the control character is
          sent exactly on its own.
        """
        text, is_pure_control = self._parse_send_text(self.tx_entry.text())
        self.send_callback(text, not is_pure_control)
        self.tx_entry.clear()

    @staticmethod
    def _parse_send_text(raw: str) -> tuple[str, bool]:
        """Interpret caret control-character notation in the transmit field.

        Returns ``(text, is_pure_control)`` where ``text`` is the field with
        recognised ``^X`` escapes replaced by their control bytes, and
        ``is_pure_control`` is True when the result is non-empty and contains
        only control characters (so the caller can suppress the trailing EOL).
        """
        out: list[str] = []
        has_printable = False
        has_control = False
        i = 0
        n = len(raw)
        while i < n:
            ch = raw[i]
            if ch == "^" and i + 1 < n:
                nxt = raw[i + 1]
                if nxt == "^":
                    # ^^ is the escape for a literal caret.
                    out.append("^")
                    has_printable = True
                    i += 2
                    continue
                code = ord(nxt.upper())
                if 0x40 <= code <= 0x5F:
                    # ^@ -> 0x00, ^A -> 0x01, ... ^Z -> 0x1A, ^[ -> 0x1B (ESC),
                    # ^\ -> 0x1C, ^] -> 0x1D, ^_ -> 0x1F. (^^ handled above.)
                    out.append(chr(code - 0x40))
                    has_control = True
                    i += 2
                    continue
                if nxt == "?":
                    # ^? -> DEL (0x7F).
                    out.append("\x7f")
                    has_control = True
                    i += 2
                    continue
                # Unrecognised escape: keep the caret as a literal character.
                out.append(ch)
                has_printable = True
                i += 1
                continue
            out.append(ch)
            if ord(ch) < 0x20 or ord(ch) == 0x7F:
                has_control = True
            else:
                has_printable = True
            i += 1
        text = "".join(out)
        is_pure_control = bool(text) and has_control and not has_printable
        return text, is_pure_control

    def write_text(self, text):
        """
        Appends text to the receive area, processing backspaces (\b).

        Satisfies: FR-091, UIR-062.
        """
        cursor = self.receive_area.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        # Insert character by character so backspaces (\b) can erase the
        # preceding character. Line endings are normalised so that CR, LF, and
        # the CRLF pair each produce exactly one new line — inserting '\r' and
        # '\n' separately would otherwise yield a blank line between every line.
        i = 0
        n = len(text)
        while i < n:
            char = text[i]
            if char == "\b":
                cursor.deletePreviousChar()
            elif char == "\r":
                # Collapse a CRLF pair into a single line break.
                if i + 1 < n and text[i + 1] == "\n":
                    i += 1
                cursor.insertText("\n")
            else:
                cursor.insertText(char)
            i += 1

        # Ensure the cursor is updated in the widget
        self.receive_area.setTextCursor(cursor)

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
