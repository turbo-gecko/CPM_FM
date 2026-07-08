"""Parser for the cpmtools ``diskdefs`` geometry-definition text format.

Pure text parsing → :class:`~cpm_fm.utils.disk_image.geometry.DiskDef` records
(no image I/O, no GUI imports — CR-014).

Satisfies: DR-048, CR-014.
"""

from __future__ import annotations

from cpm_fm.utils.disk_image.geometry import DiskDef

# cpmtools numeric fields we consume (or tolerate). ``os``/``libdsk:format`` are
# strings; ``offset`` may carry a unit suffix (see _resolve_offset); everything
# else is a plain integer.
_INT_FIELDS = {
    "seclen",
    "tracks",
    "sectrk",
    "blocksize",
    "maxdir",
    "skew",
    "boottrk",
    "logicalextents",
}
_STR_FIELDS = {"os", "libdsk:format"}
_REQUIRED = {"seclen", "tracks", "sectrk", "blocksize", "maxdir"}


class DiskDefError(ValueError):
    """Raised for a malformed ``diskdefs`` stanza (DR-048)."""


def parse_diskdefs(text: str) -> list[DiskDef]:
    """Parse ``diskdefs`` source text into a list of :class:`DiskDef`.

    Grammar (DR-048): a sequence of ``diskdef <name>`` … ``end`` stanzas, one
    ``field value`` per line inside a stanza. Lines beginning with ``#`` and
    blank lines are ignored. A stanza missing a required field, an unterminated
    stanza, or a non-integer numeric field raises :class:`DiskDefError`.

    Satisfies: DR-048.
    """
    defs: list[DiskDef] = []
    name: str | None = None
    ints: dict[str, int] = {}
    strs: dict[str, str] = {}
    offset_raw: str = ""
    skewtab: list[int] = []

    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        head = parts[0].lower()

        if head == "diskdef":
            if name is not None:
                raise DiskDefError(f"line {lineno}: nested 'diskdef' (missing 'end')")
            if len(parts) < 2:
                raise DiskDefError(f"line {lineno}: 'diskdef' needs a name")
            name = parts[1]
            ints, strs, offset_raw, skewtab = {}, {}, "", []
            continue

        if head == "end":
            if name is None:
                raise DiskDefError(f"line {lineno}: 'end' outside a diskdef")
            missing = _REQUIRED - ints.keys()
            if missing:
                raise DiskDefError(f"diskdef '{name}': missing required field(s) {sorted(missing)}")
            defs.append(_build(name, ints, strs, offset_raw, skewtab))
            name = None
            continue

        if name is None:
            raise DiskDefError(f"line {lineno}: field '{head}' outside a diskdef")

        key = parts[0].lower()
        value = " ".join(parts[1:])
        if key == "skewtab":
            skewtab = _parse_int_list(value, name, lineno)
        elif key == "offset":
            offset_raw = value  # resolved to bytes in _build (may carry a unit suffix)
        elif key in _INT_FIELDS:
            ints[key] = _parse_int(value, key, name, lineno)
        elif key in _STR_FIELDS:
            strs[key] = value
        # Unknown fields are tolerated (forward compatibility with cpmtools).

    if name is not None:
        raise DiskDefError(f"diskdef '{name}': missing 'end'")
    return defs


def _build(
    name: str,
    ints: dict[str, int],
    strs: dict[str, str],
    offset_raw: str,
    skewtab: list[int],
) -> DiskDef:
    return DiskDef(
        name=name,
        seclen=ints["seclen"],
        tracks=ints["tracks"],
        sectrk=ints["sectrk"],
        blocksize=ints["blocksize"],
        maxdir=ints["maxdir"],
        skew=ints.get("skew", 0),
        boottrk=ints.get("boottrk", 0),
        os=strs.get("os", "2.2"),
        offset=_resolve_offset(offset_raw, ints["seclen"], ints["sectrk"], name),
        libdsk_format=strs.get("libdsk:format", ""),
        skewtab=tuple(skewtab),
    )


def _resolve_offset(raw: str, seclen: int, sectrk: int, name: str) -> int:
    """Resolve a cpmtools ``offset`` value to bytes (DR-048).

    A bare number is bytes; a trailing unit scales it — ``K``/``M`` for kibi/mebi
    bytes, ``T`` for tracks (``sectrk × seclen``), ``S`` for sectors (``seclen``).
    RomWBW's multi-slice definitions use the ``T`` form (e.g. ``offset 1040T``).
    """
    raw = raw.strip()
    if not raw:
        return 0
    unit = raw[-1].upper()
    if unit.isdigit():
        return int(raw, 0)
    try:
        n = int(raw[:-1].strip(), 0)
    except ValueError as exc:
        raise DiskDefError(f"diskdef '{name}': bad offset value {raw!r}") from exc
    factor = {"T": sectrk * seclen, "S": seclen, "K": 1024, "M": 1024 * 1024}.get(unit)
    if factor is None:
        raise DiskDefError(f"diskdef '{name}': unknown offset unit {unit!r} in {raw!r}")
    return n * factor


def _parse_int(value: str, key: str, name: str, lineno: int) -> int:
    try:
        # tolerate 0x.. and plain decimal
        return int(value, 0)
    except ValueError as exc:
        raise DiskDefError(
            f"diskdef '{name}' line {lineno}: field '{key}' is not an integer: {value!r}"
        ) from exc


def _parse_int_list(value: str, name: str, lineno: int) -> list[int]:
    out: list[int] = []
    for tok in value.replace(",", " ").split():
        try:
            out.append(int(tok, 0))
        except ValueError as exc:
            raise DiskDefError(
                f"diskdef '{name}' line {lineno}: bad skewtab entry {tok!r}"
            ) from exc
    return out
