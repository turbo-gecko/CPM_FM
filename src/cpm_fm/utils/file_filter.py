"""Pure filtering and sorting helpers for the file-list panes (Feature 3).

The Host Files and Remote Files lists (UIR-011/UIR-012) share a single set of
filter and sort rules so both panes behave identically (FR-133). This module
holds that logic as pure functions operating on plain lists of file-name
strings, so it is unit-testable without a running Qt application and imports
nothing from the GUI toolkit (CR-014).

Filter semantics (FR-131):
  * An empty/whitespace pattern matches everything.
  * A pattern containing a wildcard (``*`` or ``?``) is matched as a glob over
    the whole file name (``fnmatch`` rules: ``*`` = any run, ``?`` = one char).
  * A pattern with no wildcard is matched as a substring ("contains").
  * Matching is case-insensitive by default (CP/M file names are upper-case,
    host names may be either), with an opt-in case-sensitive mode.

Sort semantics (FR-132): by file name or by extension, each ascending or
descending. Sorting is case-insensitive and stable, with the file name as the
tie-breaker so the order is deterministic.

Satisfies: FR-130, FR-131, FR-132, FR-133, CR-014.
"""

from __future__ import annotations

import fnmatch
import os
from collections.abc import Iterable

# Sort-key identifiers, also persisted verbatim (FR-134) and used as the
# sort drop-down option userData in the GUI.
SORT_NAME = "name"
SORT_EXTENSION = "extension"
VALID_SORT_KEYS = (SORT_NAME, SORT_EXTENSION)


def has_wildcard(pattern: str) -> bool:
    """Return True if ``pattern`` contains a glob wildcard (``*`` or ``?``).

    Satisfies: FR-131.
    """
    return "*" in pattern or "?" in pattern


def matches(name: str, pattern: str, *, case_sensitive: bool = False) -> bool:
    """Return True if ``name`` matches ``pattern`` under the FR-131 rules.

    An empty (or whitespace-only) pattern matches every name. A pattern with a
    wildcard is matched as a whole-name glob; otherwise it is a substring match.
    Case-insensitive unless ``case_sensitive`` is set.

    Satisfies: FR-131.
    """
    pattern = pattern.strip()
    if not pattern:
        return True
    hay = name if case_sensitive else name.lower()
    needle = pattern if case_sensitive else pattern.lower()
    if has_wildcard(needle):
        return fnmatch.fnmatchcase(hay, needle)
    return needle in hay


def _extension(name: str) -> str:
    """Return the lower-case extension of ``name`` without its leading dot."""
    return os.path.splitext(name)[1].lstrip(".").lower()


def filter_names(names: Iterable[str], pattern: str, *, case_sensitive: bool = False) -> list[str]:
    """Return the names that match ``pattern`` (FR-131), preserving input order.

    Satisfies: FR-131.
    """
    return [n for n in names if matches(n, pattern, case_sensitive=case_sensitive)]


def sort_names(
    names: Iterable[str], *, key: str = SORT_NAME, descending: bool = False
) -> list[str]:
    """Return ``names`` sorted by ``key`` (FR-132), case-insensitively.

    ``key`` is :data:`SORT_NAME` or :data:`SORT_EXTENSION`; any unrecognised
    value falls back to name order. The file name is always the final
    tie-breaker, so the result is deterministic even when extensions match.

    Satisfies: FR-132.
    """

    def key_func(name: str) -> tuple[str, str]:
        # Extension first when grouping by extension, then the name as the
        # tie-breaker; name order uses the name alone (both fields the name).
        if key == SORT_EXTENSION:
            return (_extension(name), name.lower())
        return (name.lower(), name.lower())

    return sorted(names, key=key_func, reverse=descending)


def filter_and_sort(
    names: Iterable[str],
    pattern: str = "",
    *,
    key: str = SORT_NAME,
    descending: bool = False,
    case_sensitive: bool = False,
) -> list[str]:
    """Filter ``names`` by ``pattern`` then sort the survivors (FR-133).

    The filter is applied first and the sort second, so the displayed order is
    determined only by the files that remain after filtering.

    Satisfies: FR-133.
    """
    filtered = filter_names(names, pattern, case_sensitive=case_sensitive)
    return sort_names(filtered, key=key, descending=descending)
