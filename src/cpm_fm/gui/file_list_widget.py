from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QMimeData, Qt
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import QAbstractItemView, QListWidget

# Internal drag MIME type carrying the source pane and the selected file names
# (FR-136). The payload is UTF-8 text of the form "pane\nname1\nname2…", where
# pane is "host" or "remote". A dedicated, application-private type means an
# internal drag is never confused with an external OS file drop (FR-138).
MIME_CPM_FILES = "application/x-cpmfm-file"

# Stylesheet applied to a pane while it is highlighted as a valid drop target
# (FR-139/UIR-081); the green matches the active-filter indicator (UIR-079).
_DROP_ACTIVE_STYLE = "QListWidget { border: 2px solid #4caf50; }"


class FileListWidget(QListWidget):
    """A multi-select file list that is both a drag source and a drop target.

    Drag-and-drop file transfer (Feature 1 of the new-features plan). The widget
    knows only which pane it represents ("host" or "remote") and how to
    recognise an acceptable drop; the transfer *policy* (connection checks,
    confirmation, and which batch worker to run on which thread) is owned by the
    ``MainWindow`` drop handler injected as ``drop_handler``. Keeping the policy
    out of the widget preserves the signal-based cross-thread model (NFR-004):
    drops are observed here on the GUI thread and handed to the MainWindow,
    which spawns the existing transfer worker threads.

    ``drop_handler`` is called as ``drop_handler(target_pane, source_pane,
    payload, external)`` where ``target_pane`` is this widget's pane,
    ``source_pane`` is the originating pane for an internal drag (or ``None``
    for an external OS drop), ``payload`` is the list of file names (internal)
    or absolute host paths (external), and ``external`` flags an OS file drop.

    Satisfies: FR-136, FR-137, FR-138, FR-139, UIR-081.
    """

    def __init__(
        self,
        pane: str,
        drop_handler: Callable[[str, str | None, list[str], bool], None],
    ) -> None:
        """
        Satisfies: FR-136, FR-137, FR-138.
        """
        super().__init__()
        self._pane = pane
        self._drop_handler = drop_handler
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        # FR-136: this list can start a drag; FR-137/FR-138: it can receive drops.
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        # dropEvent is fully overridden, so the default item-move is never used;
        # hide the between-rows insertion indicator that would otherwise show.
        self.setDropIndicatorShown(False)

    # ---------------------------------------------------------- drag source

    def startDrag(self, supportedActions) -> None:  # noqa: N802 (Qt override)
        """Begin an internal drag carrying the selected file names (FR-136).

        Satisfies: FR-136.
        """
        names = [item.text() for item in self.selectedItems()]
        if not names:
            return
        mime = QMimeData()
        mime.setData(MIME_CPM_FILES, "\n".join([self._pane, *names]).encode("utf-8"))
        drag = QDrag(self)
        drag.setMimeData(mime)
        # A transfer copies the file across the link; it never moves the source.
        drag.exec(Qt.DropAction.CopyAction)

    # ---------------------------------------------------------- drop target

    def decode_drop(self, mime: QMimeData) -> tuple[str | None, list[str], bool] | None:
        """Resolve a drop's payload, or ``None`` when this pane must reject it.

        Returns ``(source_pane, names, external)``:
          * an internal drag from the *other* pane -> ``(source, names, False)``;
          * external OS files dropped on the **Remote** pane -> ``(None, paths,
            True)``.
        A same-pane internal drag (dropping a pane's files back onto itself), and
        any external OS drop onto the **Host** pane, are rejected (``None``): the
        Host pane is the local filesystem view, so dropping OS files there is not
        a serial transfer (FR-138).

        Satisfies: FR-137, FR-138.
        """
        if mime.hasFormat(MIME_CPM_FILES):
            raw = bytes(mime.data(MIME_CPM_FILES).data()).decode("utf-8")
            parts = raw.split("\n")
            source, names = parts[0], [p for p in parts[1:] if p]
            # FR-137: a drop onto the originating pane is a no-op.
            if source == self._pane or not names:
                return None
            return source, names, False
        # FR-138: external OS files may be dropped onto the Remote pane only.
        if self._pane == "remote" and mime.hasUrls():
            paths = [u.toLocalFile() for u in mime.urls() if u.isLocalFile()]
            paths = [p for p in paths if p]
            if paths:
                return None, paths, True
        return None

    def dragEnterEvent(self, event) -> None:  # noqa: N802 (Qt override)
        """
        Satisfies: FR-139.
        """
        if self.decode_drop(event.mimeData()) is not None:
            self._set_drop_active(True)
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:  # noqa: N802 (Qt override)
        """
        Satisfies: FR-139.
        """
        if self.decode_drop(event.mimeData()) is not None:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:  # noqa: N802 (Qt override)
        """
        Satisfies: FR-139.
        """
        self._set_drop_active(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802 (Qt override)
        """Hand an accepted drop to the MainWindow drop handler (FR-137, FR-138).

        Satisfies: FR-137, FR-138, FR-139.
        """
        payload = self.decode_drop(event.mimeData())
        self._set_drop_active(False)
        if payload is None:
            event.ignore()
            return
        source, names, external = payload
        event.acceptProposedAction()
        self._drop_handler(self._pane, source, names, external)

    def _set_drop_active(self, active: bool) -> None:
        """Highlight (or un-highlight) the pane as a valid drop zone (FR-139).

        Satisfies: FR-139, UIR-081.
        """
        self.setStyleSheet(_DROP_ACTIVE_STYLE if active else "")
