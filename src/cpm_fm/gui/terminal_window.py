from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QPoint
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QFontDialog,
    QMainWindow,
    QMenu,
    QVBoxLayout,
    QWidget,
)

from cpm_fm.gui.terminal_view import TerminalView
from cpm_fm.terminal.term_translate import TERMINAL_TYPES
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
    (there is no separate transmit field). A status bar below the receive area
    shows the active terminal emulation type (UIR-106).

    Satisfies: UIR-060-UIR-068, UIR-106.
    """

    def __init__(
        self,
        parent,
        key_callback=None,
        clear_callback=None,
        boot_callback=None,
        engine=None,
        font_callback=None,
        paste_callback=None,
        terminal_type_callback=None,
        macros_provider=None,
        run_macro_callback=None,
        boot_enabled_provider=None,
    ):
        """
        Satisfies: UIR-060, UIR-067, UIR-069, FR-091, FR-096, FR-166, UIR-101, UIR-102, UIR-105.

        No Qt parent, so this is an independent non-modal top-level window.
        The owning MainWindow keeps a reference to it.

        ``engine`` is the shared :class:`VT100Engine` the owner feeds received
        bytes into (FR-091); the receive area renders from it. A standalone
        window (no owner) gets its own engine so it is usable on its own.
        ``key_callback`` receives the raw bytes for each keystroke typed into the
        receive area, to be transmitted on the Terminal Port (FR-096).
        ``clear_callback`` is invoked by the context-menu Clear action so the
        owner can clear the receive/transmit data buffers (FR-095).
        ``boot_callback`` runs the configured boot sequence for the context-menu
        "Boot into CP/M" action (FR-049); ``boot_enabled_provider`` returns
        whether that action should be enabled (a boot sequence is configured,
        UIR-105).
        ``font_callback`` receives the :class:`QFont` chosen via the context-menu
        Font action so the owner can persist it (UIR-069).
        ``paste_callback`` receives the clipboard text for the context-menu Paste
        action, to be transmitted on the Terminal Port (FR-166).
        ``terminal_type_callback`` receives the terminal-type value chosen in the
        context menu's Terminal Type submenu, to be applied to the engine and
        settings (UIR-101). ``macros_provider`` returns the list of configured
        ``(label, script)`` macros for the Macros submenu, and
        ``run_macro_callback`` receives the chosen macro's script to run it on the
        Terminal Port (UIR-102/FR-162).

        The Terminal Window carries no on-window controls below the Receive view
        (UIR-064): Clear, Font, Boot and terminal-type/macro actions are all
        reached from the Receive-view context menu (UIR-099); Local Echo and
        Autoscroll are set in the Terminal Config dialog (UIR-103a). Below the
        Receive view sits a status bar showing the active terminal type
        (UIR-106).
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
        # FR-095: invoked by the context-menu Clear action, so the owner can clear
        # the receive/transmit data buffers alongside the display (FR-090/FR-092).
        self.clear_callback = clear_callback
        # FR-049/UIR-105: invoked when the context-menu "Boot into CP/M" action is
        # chosen; boot_enabled_provider reports whether it should be enabled.
        self.boot_callback = boot_callback
        self.boot_enabled_provider = boot_enabled_provider
        # UIR-069: invoked with the QFont chosen via the context-menu Font action
        # so the owner can persist it across sessions.
        self.font_callback = font_callback
        # FR-166: invoked with the clipboard text when the context-menu Paste
        # action is used, so the owner can transmit it on the Terminal Port.
        self.paste_callback = paste_callback
        # UIR-101: invoked with the terminal-type value chosen in the Terminal
        # Type submenu, so the owner can apply and persist it.
        self.terminal_type_callback = terminal_type_callback
        # UIR-102: returns the configured (label, script) macros for the Macros
        # submenu; run_macro_callback runs the chosen macro's script (FR-162).
        self.macros_provider = macros_provider
        self.run_macro_callback = run_macro_callback

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
        # UIR-106: the status text is parameterised by the active terminal type,
        # so it is re-applied here rather than via the plain-key registry.
        self.update_terminal_type_status()

    def update_terminal_type_status(self) -> None:
        """Show the active terminal emulation type in the status bar (UIR-106).

        Reads the current ``terminal_type`` from the engine and renders it in the
        window's status bar (e.g. ``Emulation: VT100``), in the active UI language
        (FR-123). Called when the window is built, after each screen render (so a
        context-menu type change is reflected, UIR-101), on retranslation, and
        when the Terminal settings are applied while the window is open.

        Satisfies: UIR-106, FR-123.
        """
        self.statusBar().showMessage(tr("terminal.status_type", type=self.engine.terminal_type))

    def create_widgets(self):
        """Build the Terminal Window widgets.

        The window holds only the Receive view; below it sits a status bar
        showing the active terminal type (UIR-106) — there are no controls below
        the view (UIR-064). Clear, Font, Boot and the terminal-type/macro actions
        live on the Receive-view context menu (UIR-099); Local Echo and Autoscroll
        are Terminal Config settings (UIR-103a).

        Satisfies: UIR-061, UIR-062, UIR-064, UIR-067, UIR-099, UIR-106, FR-096.
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
        # UIR-099: the Receive view reports a right-click here so this window can
        # build and show the context menu.
        self.receive_area.set_context_menu_callback(self._show_context_menu)
        layout.addWidget(self.receive_area)

        # UIR-106: status bar below the Receive view showing the active terminal
        # emulation type. There is no transmit field — the operator types directly
        # into the receive area and each keystroke is sent live (UIR-067/FR-096).
        self.update_terminal_type_status()

    def clear_text(self):
        """Reset the screen and clear the owner's data buffers (FR-095).

        Resets the VT-100 engine (blanking the screen and scrollback) and
        repaints, then invokes the owner's callback to clear the receive/
        transmit data buffers.

        Satisfies: FR-095, UIR-064.
        """
        self.engine.reset()
        self.receive_area.clear_selection()
        self.receive_area.refresh()
        if self.clear_callback:
            self.clear_callback()

    def render_screen(self):
        """Repaint the receive view from the engine (call after feeding it).

        Also refreshes the status-bar terminal type (UIR-106) so a type change
        made from the context menu (UIR-101) is reflected immediately.

        Satisfies: FR-091, UIR-062, UIR-106.
        """
        self.receive_area.refresh()
        self.update_terminal_type_status()

    def _on_boot(self):
        """Run the configured boot sequence (FR-049).

        Satisfies: FR-049, UIR-105.
        """
        if self.boot_callback:
            self.boot_callback()

    def set_autoscroll(self, enabled: bool):
        """Set whether the Receive view auto-scrolls to the newest output.

        Applied from the ``autoscroll`` setting (UIR-104) when the window opens
        and whenever the Terminal Config is saved (UIR-103a).

        Satisfies: UIR-062, UIR-104.
        """
        self.receive_area.set_autoscroll(enabled)

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

    def _build_context_menu(self) -> QMenu:
        """Build the Receive-view context menu (UIR-099).

        Six items — Copy (FR-165), Paste (FR-166), Clear (FR-095), Font…
        (UIR-069), Reset Size (FR-167), Boot into CP/M (FR-049/UIR-105) —
        followed by the Terminal Type (UIR-101) and Macros (UIR-102) submenus.
        Copy is disabled when nothing is selected; Boot into CP/M is disabled
        unless a boot sequence is configured. Separated from
        :meth:`_show_context_menu` so the menu can be inspected in tests without
        a blocking ``exec``.

        Satisfies: UIR-099, FR-165, FR-166, FR-095, UIR-069, FR-167, FR-049,
        UIR-105, UIR-101, UIR-102.
        """
        menu = QMenu(self)
        act_copy = menu.addAction(tr("terminal.menu.copy"))
        act_copy.setEnabled(self.receive_area.has_selection())
        act_copy.triggered.connect(self.receive_area.copy_selection)
        menu.addAction(tr("terminal.menu.paste"), self._on_paste)
        menu.addSeparator()
        menu.addAction(tr("terminal.menu.clear"), self.clear_text)
        menu.addAction(tr("terminal.menu.font"), self._on_font)
        menu.addAction(tr("terminal.menu.reset_size"), self.reset_size)
        # FR-049/UIR-105: run the configured boot sequence; enabled only when a
        # boot sequence is configured (reported by boot_enabled_provider).
        act_boot = menu.addAction(tr("terminal.menu.boot"), self._on_boot)
        boot_enabled = self.boot_enabled_provider() if self.boot_enabled_provider else False
        act_boot.setEnabled(bool(boot_enabled))
        menu.addSeparator()
        self._add_terminal_type_submenu(menu)
        self._add_macros_submenu(menu)
        return menu

    def _add_terminal_type_submenu(self, menu: QMenu) -> None:
        """Append the Terminal Type submenu (UIR-101).

        Lists the three ``terminal_type`` values as checkable items with the
        engine's active type checked; selecting one hands the value to
        ``terminal_type_callback`` for application and persistence (UIR-034).

        Satisfies: UIR-101.
        """
        # Parent the submenu to ``menu`` so it shares the menu's lifetime.
        sub = QMenu(tr("terminal.menu.terminal_type"), menu)
        menu.addMenu(sub)
        active = self.engine.terminal_type
        for term_type in TERMINAL_TYPES:
            act = sub.addAction(term_type)
            act.setCheckable(True)
            act.setChecked(term_type == active)
            # Bind term_type per-iteration; the callback applies + persists it.
            act.triggered.connect(lambda _checked=False, t=term_type: self._on_terminal_type(t))

    def _add_macros_submenu(self, menu: QMenu) -> None:
        """Append the Macros submenu listing configured macros (UIR-102).

        Each configured ``(label, script)`` becomes an item that runs the script
        on the Terminal Port via ``run_macro_callback`` (FR-162). With no macros
        configured the submenu is disabled.

        Satisfies: UIR-102, FR-162.
        """
        # Parent the submenu to ``menu`` so it shares the menu's lifetime.
        sub = QMenu(tr("terminal.menu.macros_sub"), menu)
        menu.addMenu(sub)
        macros = self.macros_provider() if self.macros_provider else []
        if not macros:
            sub.setEnabled(False)
            return
        for label, script in macros:
            act = sub.addAction(label)
            act.triggered.connect(lambda _checked=False, s=script: self._on_run_macro(s))

    def _on_terminal_type(self, term_type: str) -> None:
        """Apply a terminal type chosen in the submenu (UIR-101).

        Satisfies: UIR-101.
        """
        if self.terminal_type_callback:
            self.terminal_type_callback(term_type)

    def _on_run_macro(self, script: str) -> None:
        """Run a macro chosen in the Macros submenu (UIR-102/FR-162).

        Satisfies: UIR-102, FR-162.
        """
        if self.run_macro_callback:
            self.run_macro_callback(script)

    def _show_context_menu(self, global_pos: QPoint):
        """Show the Receive-view right-click context menu at ``global_pos``.

        Satisfies: UIR-099.
        """
        self._build_context_menu().exec(global_pos)

    def _on_paste(self):
        """Send the clipboard text to the Terminal Port as typed input (FR-166).

        Reads the system clipboard and hands the text to ``paste_callback`` so
        the owner can transmit it (newline-to-EOL conversion and buffering happen
        there); a no-op when the clipboard is empty.

        Satisfies: FR-166.
        """
        text = QApplication.clipboard().text()
        if text and self.paste_callback:
            self.paste_callback(text)

    def reset_size(self):
        """Reset the window so the Receive grid reflows to 80 columns × 24 rows.

        Resizes this window by the delta between the viewport size that holds an
        80×24 grid and its current viewport size; the reflow (FR-091a) then
        settles the emulator to that geometry. Scrollbar visibility depends only
        on the scrollback depth (unchanged by the reset), so the delta is exact.

        Satisfies: FR-167.
        """
        target = self.receive_area.viewport_size_for(80, 24)
        current = self.receive_area.viewport().size()
        dw = target.width() - current.width()
        dh = target.height() - current.height()
        self.resize(self.width() + dw, self.height() + dh)

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
