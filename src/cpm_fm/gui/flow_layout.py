"""A wrapping (flow) layout for the Macro Window's buttons.

Lays child widgets out left-to-right, wrapping to the next row when the current
row is full, so the buttons reflow to more or fewer columns as the containing
window is resized (UIR-097). This is the standard Qt "flow layout" pattern
(adapted from the Qt ``FlowLayout`` example) — Qt ships no built-in wrapping
layout, so a custom :class:`QLayout` that implements ``hasHeightForWidth`` is the
established way to achieve it.

Kept in the ``gui/`` layer as it depends on the Qt toolkit (CR-014).

Satisfies: UIR-097.
"""

from __future__ import annotations

from PySide6.QtCore import QMargins, QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QLayout, QLayoutItem, QWidget


class FlowLayout(QLayout):
    """A layout that arranges its items in rows, wrapping as width allows.

    Satisfies: UIR-097.
    """

    def __init__(self, parent: QWidget | None = None, margin: int = 6, spacing: int = 6):
        """Satisfies: UIR-097."""
        super().__init__(parent)
        self._items: list[QLayoutItem] = []
        self.setContentsMargins(QMargins(margin, margin, margin, margin))
        self.setSpacing(spacing)

    # -- QLayout item bookkeeping -------------------------------------------

    def addItem(self, item: QLayoutItem) -> None:  # noqa: N802 (Qt override)
        """Satisfies: UIR-097."""
        self._items.append(item)

    def count(self) -> int:
        """Satisfies: UIR-097."""
        return len(self._items)

    def itemAt(self, index: int) -> QLayoutItem | None:  # noqa: N802 (Qt override)
        """Satisfies: UIR-097."""
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int) -> QLayoutItem | None:  # noqa: N802 (Qt override)
        """Satisfies: UIR-097."""
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    # -- sizing --------------------------------------------------------------

    def expandingDirections(self) -> Qt.Orientation:  # noqa: N802 (Qt override)
        """Satisfies: UIR-097."""
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:  # noqa: N802 (Qt override)
        """Satisfies: UIR-097."""
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802 (Qt override)
        """Satisfies: UIR-097."""
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802 (Qt override)
        """Satisfies: UIR-097."""
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self) -> QSize:  # noqa: N802 (Qt override)
        """Satisfies: UIR-097."""
        return self.minimumSize()

    def minimumSize(self) -> QSize:  # noqa: N802 (Qt override)
        """Satisfies: UIR-097."""
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(
            margins.left() + margins.right(),
            margins.top() + margins.bottom(),
        )
        return size

    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        """Place the items within ``rect``; return the total height used.

        When ``test_only`` is True the items are not actually moved (used by
        ``heightForWidth`` to compute the height a given width would need).

        Satisfies: UIR-097.
        """
        margins = self.contentsMargins()
        effective = rect.adjusted(
            margins.left(), margins.top(), -margins.right(), -margins.bottom()
        )
        x = effective.x()
        y = effective.y()
        line_height = 0
        spacing = self.spacing()

        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width() + spacing
            if next_x - spacing > effective.right() and line_height > 0:
                # Wrap to the next row.
                x = effective.x()
                y = y + line_height + spacing
                next_x = x + hint.width() + spacing
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x
            line_height = max(line_height, hint.height())

        return y + line_height - rect.y() + margins.bottom()
