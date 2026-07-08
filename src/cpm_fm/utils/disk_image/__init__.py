"""Pure-Python CP/M disk-image reader (geometry driven by cpmtools ``diskdefs``).

Public entry points:

* :func:`load_diskdefs` — load the bundled (or a user-supplied) geometry database.
* :func:`detect_diskdef` — rank the geometries that plausibly match an image file.
* :func:`open_image` — open an image (auto-detecting geometry by default) and
  return a :class:`~cpm_fm.utils.disk_image.image.CpmImage`, or ``None`` on any
  unreadable / foreign / too-small input (never raises — FR-172).

No GUI-toolkit imports (CR-014); no third-party dependencies.

Satisfies: FR-169, FR-170, FR-171, FR-172, DR-048, DR-049, CR-014.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from cpm_fm.utils.disk_image.directory import DIR_ENTRY_SIZE, EMPTY_USER, MAX_USER
from cpm_fm.utils.disk_image.diskdefs import DiskDefError, parse_diskdefs
from cpm_fm.utils.disk_image.filesystem import CpmFileEntry
from cpm_fm.utils.disk_image.geometry import DiskDef
from cpm_fm.utils.disk_image.image import CpmImage

__all__ = [
    "CpmFileEntry",
    "CpmImage",
    "DetectResult",
    "DiskDef",
    "DiskDefError",
    "DiskDefs",
    "detect_diskdef",
    "is_ambiguous",
    "load_diskdefs",
    "open_image",
]

_BUNDLED_DISKDEFS = Path(__file__).parent / "data" / "diskdefs"

# Detection tuning (FR-170).
_MIN_SCORE = 0.60  # a candidate below this is treated as "not CP/M"
_AMBIGUOUS_MARGIN = 0.05  # top two within this → the GUI should prompt


class DiskDefs:
    """A loaded geometry database — name-indexed and iterable (DR-048)."""

    def __init__(self, defs: list[DiskDef]):
        self._defs = list(defs)
        self._by_name = {d.name: d for d in self._defs}

    def get(self, name: str) -> DiskDef | None:
        return self._by_name.get(name)

    def names(self) -> list[str]:
        return list(self._by_name)

    def __iter__(self):
        return iter(self._defs)

    def __len__(self) -> int:
        return len(self._defs)


@dataclass
class DetectResult:
    """A ranked geometry candidate for an image (FR-170)."""

    diskdef: DiskDef
    score: float  # directory-validity ratio in 0.0–1.0
    slices: int  # 1 for a single disk; >1 for a multi-slice CF image


def load_diskdefs(path: str | Path | None = None) -> DiskDefs:
    """Load geometry definitions from ``path`` (or the bundled database if ``None``).

    Satisfies: DR-048, FR-170.
    """
    src = Path(path) if path is not None else _BUNDLED_DISKDEFS
    text = src.read_text(encoding="utf-8")
    return DiskDefs(parse_diskdefs(text))


def _score_directory(raw: bytes, geom: DiskDef) -> float:
    """Fraction of the directory region that looks like valid CP/M entries (FR-170).

    Every 32-byte slot counts as valid when it is empty (``0xE5``) or an in-use
    entry with a plausible user number, 7-bit printable name/type bytes and a
    record count ≤ 128. Garbage data scores near zero.

    Satisfies: FR-170.
    """
    try:
        img = CpmImage(raw, geom)
    except ValueError:
        return 0.0
    directory = img._read_directory()  # noqa: SLF001 - same package, detection helper
    slots = len(directory) // DIR_ENTRY_SIZE
    if slots == 0:
        return 0.0
    valid = 0
    for off in range(0, slots * DIR_ENTRY_SIZE, DIR_ENTRY_SIZE):
        rec = directory[off : off + DIR_ENTRY_SIZE]
        user = rec[0]
        if user == EMPTY_USER:
            valid += 1
            continue
        if user > MAX_USER:
            continue
        name_type = rec[1:12]
        if all(0x20 <= (b & 0x7F) <= 0x7E for b in name_type) and rec[15] <= 0x80:
            valid += 1
    return valid / slots


def detect_diskdef(path: str | Path, defs: DiskDefs) -> list[DetectResult]:
    """Rank the geometries in ``defs`` that plausibly describe the image at ``path``.

    A geometry qualifies when the file size equals its ``total_bytes`` (single
    disk) or is an exact multiple ≥ 2 of it (a multi-slice CF image). Each
    qualifier is scored by directory validity (:func:`_score_directory`) on its
    first slice; results at or above the confidence floor are returned best-first.
    An empty list means nothing matched (the GUI should reject or ask — FR-172).

    Satisfies: FR-170.
    """
    try:
        size = os.path.getsize(path)
        raw = Path(path).read_bytes()
    except OSError:
        return []
    if size == 0:
        return []

    exact: list[DetectResult] = []
    multi: list[DetectResult] = []
    for geom in defs:
        tb = geom.total_bytes
        if tb <= 0:
            continue
        if size == tb:
            slices = 1
        elif size % tb == 0 and size // tb >= 2:
            slices = size // tb
        else:
            continue
        score = _score_directory(raw[:tb], geom)
        if score >= _MIN_SCORE:
            (exact if slices == 1 else multi).append(
                DetectResult(diskdef=geom, score=score, slices=slices)
            )

    # A file that is exactly one known disk size *is* that disk; the multi-slice
    # (CF) interpretation is only a fallback used when no single-disk size fits.
    results = exact if exact else multi
    results.sort(key=lambda r: (-r.score, r.slices))
    return results


def is_ambiguous(results: list[DetectResult]) -> bool:
    """True when detection cannot confidently pick one geometry (FR-170).

    Empty results, or two top candidates scoring within :data:`_AMBIGUOUS_MARGIN`,
    mean the GUI should prompt the user to choose.

    Satisfies: FR-170.
    """
    if not results:
        return True
    if len(results) == 1:
        return False
    return (results[0].score - results[1].score) < _AMBIGUOUS_MARGIN


def open_image(path: str | Path, diskdef: str | DiskDef | None = None) -> CpmImage | None:
    """Open a CP/M image, returning a :class:`CpmImage` or ``None`` on bad input.

    ``diskdef=None`` auto-detects geometry (best candidate from
    :func:`detect_diskdef`); a name resolves against the bundled database; a
    :class:`DiskDef` forces that geometry. Any unreadable, too-small, foreign, or
    otherwise unrecognisable input yields ``None`` — this function never raises,
    so the GUI cannot be crashed by a corrupt file (FR-172).

    Satisfies: FR-169, FR-170, FR-172.
    """
    try:
        raw = Path(path).read_bytes()
    except OSError:
        return None
    if not raw:
        return None

    geom: DiskDef | None
    if diskdef is None:
        try:
            candidates = detect_diskdef(path, load_diskdefs())
        except (OSError, DiskDefError):
            return None
        geom = candidates[0].diskdef if candidates else None
    elif isinstance(diskdef, DiskDef):
        geom = diskdef
    else:
        try:
            geom = load_diskdefs().get(diskdef)
        except (OSError, DiskDefError):
            return None
    if geom is None:
        return None

    try:
        return CpmImage(raw[: geom.total_bytes] if geom.total_bytes else raw, geom)
    except (ValueError, IndexError):
        return None
