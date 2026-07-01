from __future__ import annotations

from dataclasses import dataclass

from pyte import ByteStream, HistoryScreen

# Default terminal geometry and scrollback depth. 80x24 is the classic VT-100
# page; the scrollback depth backs the Terminal Window's history/autoscroll
# (UIR-062/UIR-066). Both are overridable via the constructor so a later
# settings surface can drive them (plan open item, temp/vt100_terminal_plan.md).
DEFAULT_COLS = 80
DEFAULT_ROWS = 24
DEFAULT_HISTORY = 1000


@dataclass(frozen=True)
class Cell:
    """One character cell of the rendered screen, decoupled from ``pyte``.

    The GUI renderer consumes these rather than ``pyte`` internals, so the
    emulator dependency stays confined to this module (keeps CR-014's clean
    layer boundary and makes the engine unit-testable without a GUI).

    ``fg``/``bg`` are ``pyte`` colour names ("default", "red", ... or a hex
    string for indexed/true colour); the renderer maps them to Qt colours.

    Satisfies: FR-091, CR-014.
    """

    char: str
    fg: str = "default"
    bg: str = "default"
    bold: bool = False
    italics: bool = False
    underscore: bool = False
    reverse: bool = False
    strikethrough: bool = False


class VT100Engine:
    """VT-100/ANSI terminal engine: a byte-fed screen model over ``pyte``.

    This is the GUI-free heart of the interactive terminal. Raw bytes from the
    Terminal Port are pushed in via :meth:`feed`; the current screen contents,
    cursor position, and per-cell attributes are read back out for rendering.
    It imports no GUI toolkit, so it lives in ``terminal/`` alongside the other
    protocol logic and is exercised purely from unit tests (CR-014, NFR-001).

    ``pyte``'s :class:`ByteStream` uses an incremental UTF-8 decoder and its
    :class:`Stream` state machine reassembles escape sequences, so bytes and
    even multi-byte / split escape sequences that straddle two :meth:`feed`
    calls are handled correctly — important because the serial read loop
    delivers arbitrarily chunked data (NFR-001).

    Satisfies: FR-091, CR-014.
    """

    def __init__(
        self,
        cols: int = DEFAULT_COLS,
        rows: int = DEFAULT_ROWS,
        history: int = DEFAULT_HISTORY,
        use_utf8: bool = True,
    ) -> None:
        """Create an engine with the given geometry and scrollback depth.

        ``use_utf8`` selects the byte→character decoding: UTF-8 (default, with
        graceful replacement of invalid bytes) or raw 8-bit (each byte maps to
        the code point of the same value, i.e. Latin-1 semantics) for legacy
        8-bit CP/M output. It can also be switched at runtime by the remote via
        the standard ``ESC % G`` / ``ESC % @`` sequences.

        Satisfies: FR-091.
        """
        self._screen = HistoryScreen(cols, rows, history=history)
        self._stream = ByteStream(self._screen)
        self._stream.use_utf8 = use_utf8

    # ------------------------------------------------------------------ input

    def feed(self, data: bytes) -> None:
        """Advance the emulator with raw bytes received from the Terminal Port.

        Satisfies: FR-091.
        """
        self._stream.feed(data)

    def reset(self) -> None:
        """Clear the screen and reset all terminal state to power-on defaults.

        Used by the Terminal Window Clear button (FR-095) and on connect. After
        a reset every line is considered dirty so the renderer repaints in full.

        Satisfies: FR-091, FR-095.
        """
        self._screen.reset()
        self._screen.dirty.update(range(self._screen.lines))

    def resize(self, cols: int, rows: int) -> None:
        """Resize the screen to ``cols`` x ``rows`` character cells.

        Satisfies: FR-091.
        """
        # pyte's resize takes (lines, columns); expose the conventional
        # (cols, rows) order to callers.
        self._screen.resize(rows, cols)

    # ----------------------------------------------------------------- output

    @property
    def cols(self) -> int:
        """Number of character columns.

        Satisfies: FR-091.
        """
        return self._screen.columns

    @property
    def rows(self) -> int:
        """Number of character rows.

        Satisfies: FR-091.
        """
        return self._screen.lines

    @property
    def cursor(self) -> tuple[int, int]:
        """Cursor position as ``(x, y)`` (column, row), both zero-based.

        Satisfies: FR-091.
        """
        return self._screen.cursor.x, self._screen.cursor.y

    @property
    def cursor_hidden(self) -> bool:
        """Whether the cursor is hidden (DECTCEM, ``ESC[?25l``).

        Satisfies: FR-091.
        """
        return self._screen.cursor.hidden

    @property
    def display(self) -> list[str]:
        """The screen as a list of plain-text rows (attributes stripped).

        Convenience for tests and simple text extraction; the renderer uses
        :meth:`line` for attributed cells.

        Satisfies: FR-091.
        """
        return list(self._screen.display)

    def line(self, row: int) -> list[Cell]:
        """Return row ``row`` as a list of attributed :class:`Cell` objects.

        Always returns exactly :attr:`cols` cells; positions the emulator has
        not written are returned as blank default cells.

        Satisfies: FR-091.
        """
        buffer_row = self._screen.buffer[row]
        cells: list[Cell] = []
        for col in range(self._screen.columns):
            ch = buffer_row[col]
            cells.append(
                Cell(
                    char=ch.data,
                    fg=ch.fg,
                    bg=ch.bg,
                    bold=ch.bold,
                    italics=ch.italics,
                    underscore=ch.underscore,
                    reverse=ch.reverse,
                    strikethrough=ch.strikethrough,
                )
            )
        return cells

    # ------------------------------------------------------ dirty-line tracking

    @property
    def dirty(self) -> set[int]:
        """Row indices changed since the last :meth:`clear_dirty` (a copy).

        The renderer repaints only these rows, so fast output does not force a
        full-screen redraw each chunk.

        Satisfies: FR-091.
        """
        return set(self._screen.dirty)

    def clear_dirty(self) -> None:
        """Mark all rows clean; call after the renderer has repainted them.

        Satisfies: FR-091.
        """
        self._screen.dirty.clear()
