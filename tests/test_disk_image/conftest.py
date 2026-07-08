"""Shared fixtures for the disk-image tests: a synthetic CP/M image builder.

The builder is an independent mini-``mkfs`` — it lays out a directory and data
blocks for a chosen :class:`DiskDef` so the reader can be exercised with no
hardware and no cpmtools. It deliberately re-derives the geometry maths so a
reader bug does not hide behind a matching writer bug for the *values* it
asserts (the cpmtools oracle in the Phase 2 harness is the byte-for-byte
cross-check). Multi-extent files are only built for geometries whose directory
entry holds a single 16 KiB extent (``extent_mask == 0``); larger-block
geometries are exercised with single-entry files.
"""

from __future__ import annotations

import math

import pytest

from cpm_fm.utils.disk_image.geometry import DiskDef, build_skew_table

RECORD = 128


def make_image(
    geom: DiskDef,
    files: dict[str, bytes],
    *,
    user: int = 0,
    attrs: dict[str, tuple[bool, bool, bool]] | None = None,
    fill: int = 0xE5,
) -> bytes:
    """Return raw image bytes for ``geom`` containing ``files`` (name -> content).

    ``attrs`` maps a file name to ``(read_only, system, archive)`` flags. The
    layout allocates data blocks sequentially after the directory blocks and
    writes them through the same skew as the reader.
    """
    attrs = attrs or {}
    raw = bytearray([fill]) * geom.total_bytes
    skew = build_skew_table(geom.sectrk, geom.skew)
    track_bytes = geom.sectrk * geom.seclen
    first_data_sec = geom.boottrk * geom.sectrk

    def write_data(pos: int, data: bytes) -> None:
        p, di, end = pos, 0, pos + len(data)
        while p < end:
            sec_index = first_data_sec + p // geom.seclen
            track, logsec = divmod(sec_index, geom.sectrk)
            phys = skew[logsec]
            sec_abs = geom.offset + track * track_bytes + phys * geom.seclen
            within = p % geom.seclen
            take = min(geom.seclen - within, end - p)
            raw[sec_abs + within : sec_abs + within + take] = data[di : di + take]
            p += take
            di += take

    recs_per_block = geom.blocksize // RECORD
    epe = geom.extents_per_entry

    dir_blocks = math.ceil(geom.maxdir * 32 / geom.blocksize)
    next_block = dir_blocks
    directory = bytearray()

    for name, content in files.items():
        base, _, ext = name.partition(".")
        name_bytes = bytearray(base.upper().ljust(8)[:8].encode("ascii"))
        ext_bytes = bytearray(ext.upper().ljust(3)[:3].encode("ascii"))
        ro, sys_, arc = attrs.get(name, (False, False, False))
        if ro:
            ext_bytes[0] |= 0x80
        if sys_:
            ext_bytes[1] |= 0x80
        if arc:
            ext_bytes[2] |= 0x80

        records = math.ceil(len(content) / RECORD)
        total_blocks = math.ceil(len(content) / geom.blocksize)
        block_nums = list(range(next_block, next_block + total_blocks))
        next_block += total_blocks
        for i, bn in enumerate(block_nums):
            write_data(bn * geom.blocksize, content[i * geom.blocksize : (i + 1) * geom.blocksize])

        if records == 0:  # empty file: a single zero-length extent
            directory += _entry(
                user, name_bytes, ext_bytes, ex=0, s2=0, rc=0, al=[], ptrs=geom.ptr16
            )
            continue

        blk = iter(block_nums)
        g = 0
        remaining = records
        while remaining > 0:
            recs_this = min(remaining, epe * 128)
            if g > 0 and epe != 1:
                raise ValueError("multi-entry files require extent_mask == 0 geometry")
            sub = (recs_this - 1) // 128
            rc = recs_this - sub * 128
            e = g * epe + sub
            nblocks = math.ceil(recs_this / recs_per_block)
            al = [next(blk) for _ in range(nblocks)]
            directory += _entry(
                user, name_bytes, ext_bytes, ex=e % 32, s2=e // 32, rc=rc, al=al, ptrs=geom.ptr16
            )
            remaining -= recs_this
            g += 1

    write_data(0, bytes(directory))
    return bytes(raw)


def _entry(user, name_bytes, ext_bytes, *, ex, s2, rc, al, ptrs) -> bytes:
    rec = bytearray(32)
    rec[0] = user
    rec[1:9] = name_bytes
    rec[9:12] = ext_bytes
    rec[12] = ex
    rec[13] = 0
    rec[14] = s2
    rec[15] = rc
    al_bytes = bytearray(16)
    if ptrs:  # 16-bit little-endian
        for i, b in enumerate(al[:8]):
            al_bytes[i * 2] = b & 0xFF
            al_bytes[i * 2 + 1] = (b >> 8) & 0xFF
    else:
        for i, b in enumerate(al[:16]):
            al_bytes[i] = b & 0xFF
    rec[16:32] = al_bytes
    return bytes(rec)


@pytest.fixture
def make_image_fn():
    return make_image
