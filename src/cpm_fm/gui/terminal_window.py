from __future__ import annotations

from typing import Callable

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QFontDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from cpm_fm.gui.terminal_view import TerminalView
from cpm_fm.terminal.vt100_engine import VT100Engine
from cpm_fm.utils.i18n import tr

# UIR-069/UIR-070: the application-wide qt-material stylesheet sets a fixed 36px
# height on every QListView, which collapses QFontDialog's family/style/size
# lists to a single unusable row (the reported "cannot adjust the items"). A
# selector scoped to the dialog restores usable, scrollable lists; it must be a
# descendant selector (``QFontDialog QListView``) — a bare ``QListView`` rule
# loses to the app-wide sheet on specificity — and use ``min-height`` to grow
# past the theme's fixed ``height``.
_FONT_DIALOG_STYLE = "QFontDialog QListView { min-height: 200px; }"


class TerminalWindow(QMainWindow):
    """
    Non-modal Terminal window (SRS docs/cpm_fm_requirements.md, UIR-060-UIR-068).

    Interactive VT-100 terminal: the receive area renders the engine's screen
    and keystrokes typed into it are sent straight to the Terminal Port
    (there is no separate transmit field).

    Satisfies: UIR-060-UIR-068.
    """

    def __init__(
        self,
        parent,
        key_callback=None,
        clear_callback=None,
        boot_callback=None,
        engine=None,
        font_callback=None,
    ):
        """
        Satisfies: UIR-060, UIR-068, UIR-069, FR-091, FR-096.

        No Qt parent, so this is an independent non-modal top-level window.
        The owning MainWindow keeps a reference to it.

        ``engine`` is the shared :class:`VT100Engine` the owner feeds received
        bytes into (FR-091); the receive area renders from it. A standalone
        window (no owner) gets its own engine so it is usable on its own.
        ``key_callback`` receives the raw bytes for each keystroke typed into the
        receive area, to be transmitted on the Terminal Port (FR-096).
        ``font_callback`` receives the :class:`QFont` chosen via the Font button
        so the owner can persist it (UIR-069).
        """
        super().__init__()
        # FR-091: the VT-100 screen model this window renders.
        self.engine = engine if engine is not None else VT100Engine()
        # FR-121/FR-123: maps a widget text-setter to its translation key so the
        # window can be re-translated live when the language changes.
        self._i18n_registry: list[tuple[Callable[[str], None], str]] = []
        self._register_text(self.setWindowTitle, "terminal.title")
        self.resize(600, 400)
        # FR-096: invoked with the bytes for each keystroke typed in the receive
        # area, so the owner can transmit them on the Terminal Port.
        self.key_callback = key_callback
        # Invoked when the Clear button is pressed, so the owner can clear the
        # receive/transmit data buffers alongside the display (FR-090/FR-092).
        self.clear_callback = clear_callback
        # FR-049/UIR-068: invoked when the "Boot into CP/M" button is pressed.
        self.boot_callback = boot_callback
        # UIR-069: invoked with the QFont chosen via the Font button so the owner
        # can persist it across sessions.
        self.font_callback = font_callback

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
        """Build the Terminal Window widgets.

        Satisfies: UIR-061, UIR-062, UIR-064, UIR-065, UIR-066, UIR-067, UIR-069,
        UIR-096, FR-096.
        """
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # Receive Area — a VT-100 character-grid view rendering the engine's
        # screen and scrollback (UIR-061/UIR-062). It is also the keyboard-input
        # surface: keystrokes typed here are encoded to VT-100 byte sequences and
        # sent to the Terminal Port via key_callback (UIR-067/FR-096).
        self.receive_area = TerminalView(self.engine)
        self.receive_area.set_key_callback(self.key_callback)
        layout.addWidget(self.receive_area)

        # Control Frame: Clear (left), Local Echo (centre), Autoscroll (right).
        ctrl_layout = QHBoxLayout()
        self.btn_clear = QPushButton(clicked=self.clear_text)
        self._register_text(self.btn_clear.setText, "terminal.clear")
        ctrl_layout.addWidget(self.btn_clear)

        # UIR-068: "Boot into CP/M" button, to the right of Clear. Disabled until
        # the owner enables it via set_boot_enabled (i.e. when a boot sequence is
        # configured).
        self.btn_boot = QPushButton(clicked=self._on_boot)
        self._register_text(self.btn_boot.setText, "terminal.boot")
        self.btn_boot.setEnabled(False)
        ctrl_layout.addWidget(self.btn_boot)
        ctrl_layout.addStretch()

        # UIR-096: "Macros" checkbox, to the left of Local Echo, that shows/hides
        # the floating Macro Window (FR-164). The owner wires its toggled signal
        # in show_terminal. Unchecked by default.
        self.chk_macros = QCheckBox()
        self._register_text(self.chk_macros.setText, "terminal.macros")
        self.chk_macros.setChecked(False)
        ctrl_layout.addWidget(self.chk_macros)

        self.chk_echo = QCheckBox()  # UIR-065: disabled by default.
        self._register_text(self.chk_echo.setText, "terminal.local_echo")
        self.chk_echo.setChecked(False)
        ctrl_layout.addWidget(self.chk_echo)
        ctrl_layout.addStretch()

        self.chk_scroll = QCheckBox()  # UIR-066: enabled by default.
        self._register_text(self.chk_scroll.setText, "terminal.autoscroll")
        self.chk_scroll.setChecked(True)
        # UIR-062: the checkbox governs the receive view's autoscroll.
        self.chk_scroll.toggled.connect(self.receive_area.set_autoscroll)
        ctrl_layout.addWidget(self.chk_scroll)

        # UIR-069: "Font…" button, right of the Autoscroll checkbox, opens the
        # standard font-selection dialog for the Receive view.
        self.btn_font = QPushButton(clicked=self._on_font)
        self._register_text(self.btn_font.setText, "terminal.font")
        ctrl_layout.addWidget(self.btn_font)
        layout.addLayout(ctrl_layout)

        # UIR-067: input hint. There is no transmit field — the operator types
        # directly into the receive area and each keystroke is sent live.
        self.lbl_hint = QLabel()
        self._register_text(self.lbl_hint.setText, "terminal.input_hint")
        layout.addWidget(self.lbl_hint)

    def clear_text(self):
        """Reset the screen and clear the owner's data buffers (FR-095).

        Resets the VT-100 engine (blanking the screen and scrollback) and
        repaints, then invokes the owner's callback to clear the receive/
        transmit data buffers.

        Satisfies: FR-095, UIR-064.
        """
        self.engine.reset()
        self.receive_area.refresh()
        if self.clear_callback:
            self.clear_callback()

    def render_screen(self):
        """Repaint the receive view from the engine (call after feeding it).

        Satisfies: FR-091, UIR-062.
        """
        self.receive_area.refresh()

    def _on_boot(self):
        """Run the configured boot sequence (FR-049).

        Satisfies: FR-049, UIR-068.
        """
        if self.boot_callback:
            self.boot_callback()

    def set_boot_enabled(self, enabled: bool):
        """Enable/disable the "Boot into CP/M" button (UIR-068).

        Satisfies: UIR-068.
        """
        self.btn_boot.setEnabled(enabled)

    def _build_font_dialog(self) -> QFontDialog:
        """Create the font-selection dialog seeded with the Receive view's font.

        Uses Qt's standard :class:`QFontDialog`, forced non-native so it renders
        and behaves identically on every platform (Windows has no native Qt font
        picker in any case), and carrying a scoped stylesheet that undoes the app
        theme's list-collapsing rule so the family/style/size lists are usable
        (see ``_FONT_DIALOG_STYLE``).

        Satisfies: UIR-069.
        """
        dlg = QFontDialog(self.receive_area.current_font(), self)
        dlg.setOption(QFontDialog.FontDialogOption.DontUseNativeDialog, True)
        dlg.setWindowTitle(tr("terminal.font_dialog_title"))
        dlg.setStyleSheet(_FONT_DIALOG_STYLE)
        return dlg

    def _on_font(self):
        """Open the standard font dialog and apply/persist the chosen font.

        Seeds :class:`QFontDialog` with the Receive view's current font; on OK,
        applies the selection to the view immediately and hands it to
        ``font_callback`` so the owner can persist it (UIR-069).

        Satisfies: UIR-069.
        """
        dlg = self._build_font_dialog()
        if dlg.exec():
            font = dlg.selectedFont()
            self.receive_area.set_font(font)
            if self.font_callback:
                self.font_callback(font)

    def set_terminal_font(self, font: QFont):
        """Apply ``font`` to the Receive view (e.g. the saved font on open).

        Satisfies: UIR-069.
        """
        self.receive_area.set_font(font)

    def set_eol(self, eol: bytes):
        """Set the bytes the Enter key transmits (the configured EOL, FR-094).

        Satisfies: FR-094.
        """
        self.receive_area.set_eol(eol)

    def focus_input(self):
        """Give keyboard focus to the receive area so typing is sent (FR-096).

        Satisfies: FR-096.
        """
        self.receive_area.setFocus()

    def closeEvent(self, event):
        """
        Satisfies: FR-097.

        Non-modal window persists in the background when closed by the user;
        reopens/restores the same instance via the Terminal button.
        """
        event.ignore()
        self.hide()
