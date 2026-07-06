from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMainWindow, QPushButton, QWidget

from cpm_fm.gui.flow_layout import FlowLayout
from cpm_fm.utils.i18n import tr


class MacroWindow(QMainWindow):
    """Floating, resizable palette of configurable macro buttons.

    A ``Qt.Tool`` window that floats above its parent (the Terminal Window) and
    holds up to ten buttons (UIR-097). Each button, when clicked, hands its
    configured keystroke script to ``click_callback`` for execution on the
    Terminal Port (FR-162). The buttons are laid out with a :class:`FlowLayout`
    so they reflow as the window is resized. Closing the window hides it and
    notifies ``hidden_callback`` so the owner can clear the Terminal Window's
    Macros checkbox (FR-164).

    Satisfies: UIR-097, FR-162, FR-164.
    """

    #: The maximum number of configurable macro slots (UIR-098).
    MACRO_COUNT = 10

    def __init__(
        self,
        parent,
        click_callback: Callable[[str], None] | None = None,
        hidden_callback: Callable[[], None] | None = None,
    ):
        """
        Satisfies: UIR-097, FR-164.

        ``parent`` is the Terminal Window; combined with the ``Qt.Tool`` flag
        this makes the palette float above it without its own taskbar entry.
        ``click_callback`` receives a button's keystroke script when it is
        clicked (FR-162); ``hidden_callback`` is invoked when the window is
        closed via its window control so the owner can sync the checkbox.
        """
        super().__init__(parent)
        # UIR-097: a floating tool palette, not a normal top-level window.
        self.setWindowFlags(Qt.WindowType.Tool)
        # FR-162: invoked with the clicked button's keystroke script.
        self.click_callback = click_callback
        # FR-164: invoked when the user closes the window (it hides rather than
        # destroys), so the owner can clear the Terminal Window's Macros checkbox.
        self.hidden_callback = hidden_callback
        # FR-121/FR-123: retranslation registry (only the title is translated —
        # the button captions are user-supplied labels, not i18n strings).
        self._i18n_registry: list[tuple[Callable[[str], None], str]] = []
        self._register_text(self.setWindowTitle, "macro.title")
        self.resize(320, 200)

        central = QWidget()
        self.setCentralWidget(central)
        # UIR-097: the reflowing button layout.
        self._flow = FlowLayout(central)
        self._buttons: list[QPushButton] = []

    def _register_text(self, setter: Callable[[str], None], key: str) -> None:
        """Set ``setter``'s text from ``key`` now and register it for retranslation.

        Satisfies: FR-121, FR-123.
        """
        self._i18n_registry.append((setter, key))
        setter(tr(key))

    def retranslate_ui(self) -> None:
        """Re-apply the active language to this window (the title).

        Satisfies: FR-123.
        """
        for setter, key in self._i18n_registry:
            setter(tr(key))

    def set_macros(self, macros: list[tuple[str, str]]) -> None:
        """Rebuild the button palette from configured ``(label, script)`` pairs.

        Clears the existing buttons and creates one per entry, in order. Each
        button's ``clicked`` signal hands its script to ``click_callback``
        (FR-162). Only entries the owner has already filtered to non-empty
        label+script are passed in (UIR-097).

        Satisfies: UIR-097, FR-162.
        """
        while self._flow.count():
            item = self._flow.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.deleteLater()
        self._buttons = []
        for label, script in macros:
            button = QPushButton(label)
            # `script` bound as a default argument so each button captures its
            # own script; `checked` absorbs the bool the clicked signal passes.
            button.clicked.connect(lambda checked=False, s=script: self._on_click(s))
            self._flow.addWidget(button)
            self._buttons.append(button)

    def _on_click(self, script: str) -> None:
        """Hand a clicked button's script to the owner for execution (FR-162).

        Satisfies: FR-162.
        """
        if self.click_callback:
            self.click_callback(script)

    def closeEvent(self, event):
        """Hide (not destroy) on close and notify the owner (FR-164).

        Satisfies: FR-164.

        Like the Terminal Window (FR-097), the palette persists in the
        background when closed; the owner reopens it via the Macros checkbox.
        """
        event.ignore()
        self.hide()
        if self.hidden_callback:
            self.hidden_callback()
