"""Tests for open_image robustness and the auto/explicit geometry paths.

Verifies: FR-169, FR-170, FR-172.
"""

from __future__ import annotations

from cpm_fm.utils.disk_image import load_diskdefs, open_image


def _write(tmp_path, name, data):
    p = tmp_path / name
    p.write_bytes(data)
    return str(p)


def test_open_image_auto_detects_and_lists(tmp_path, make_image_fn):
    """Opening with no geometry auto-detects and lists the files.

    Verifies: FR-169, FR-170.
    """
    geom = load_diskdefs().get("kaypro2")
    raw = make_image_fn(geom, {"README.TXT": bytes([65]) * 256})
    path = _write(tmp_path, "disk.img", raw)

    img = open_image(path)
    assert img is not None
    assert [f.name for f in img.list_files()] == ["README.TXT"]


def test_open_image_forced_geometry(tmp_path, make_image_fn):
    """A forced geometry (by name and by DiskDef) opens the image.

    Verifies: FR-169.
    """
    geom = load_diskdefs().get("ibm-3740")
    raw = make_image_fn(geom, {"X.COM": bytes([1]) * 128})
    path = _write(tmp_path, "disk.img", raw)

    assert open_image(path, "ibm-3740") is not None
    assert open_image(path, geom) is not None


def test_open_image_rejects_bad_input(tmp_path):
    """Zero-byte, garbage, unknown-geometry and missing files return None (no raise).

    Verifies: FR-172.
    """
    assert open_image(_write(tmp_path, "empty.img", b"")) is None
    assert open_image(_write(tmp_path, "garbage.img", bytes([0x37]) * 5000)) is None
    assert open_image(str(tmp_path / "does_not_exist.img")) is None
    # A real image but an unknown forced geometry name.
    assert open_image(_write(tmp_path, "d.img", bytes(256256)), "no-such-def") is None


def test_open_image_rejects_foreign_sized_file(tmp_path):
    """A file the exact size of a known geometry but with a garbage directory is rejected.

    Verifies: FR-172.
    """
    geom = load_diskdefs().get("ibm-3740")
    # Random-looking bytes at the right size: directory region will not validate.
    blob = bytes((i * 251 + 7) & 0xFF for i in range(geom.total_bytes))
    assert open_image(_write(tmp_path, "foreign.img", blob)) is None
