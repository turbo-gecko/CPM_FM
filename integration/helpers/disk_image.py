"""CP/M disk-image creation helpers for hardware-in-the-loop (HIL) integration tests.

Provides reusable functions to generate minimal CP/M images programmatically,
supporting single-area and multi-area test scenarios.

The disk_image API from cpm_fm.utils.disk_image is used to create, populate,
and save images without committing any .dsk files to the repository.

Satisfies: FR-170, FR-171.
"""

from __future__ import annotations

from pathlib import Path

from cpm_fm.utils.disk_image import create_image, load_diskdefs


def create_test_image(path: str | Path, geometry_name: str = "ibm-3740") -> Path:
    """Create a minimal CP/M disk image with test files in user area 0.

    The generated image contains several small test files suitable for
    transfer testing (Copy to Remote, drag-and-drop, conflict resolution).

    Args:
        path: Destination file path for the created image.
        geometry_name: Name of the geometry from the bundled database
            (default "ibm-3740" - 8-inch double-density).

    Returns:
        The Path to the created disk image.

    Example:
        >>> img_path = create_test_image("/tmp/test.img")
        >>> assert img_path.exists()

    Satisfies: FR-170, FR-171.
    """
    geom = load_diskdefs().get(geometry_name)
    if geom is None:
        raise ValueError(f"unknown geometry: {geometry_name}")

    img = create_image(geom)

    test_files = {
        "HELLO.COM": b"print('Hello from CP/M')",
        "DATA.TXT": b"This is a test file for HIL testing.\r\n",
        "BINARY.DAT": bytes(range(256)),
        "LARGE.BIN": (b"X" * 1024),
    }

    for name, content in test_files.items():
        img.write_file(name, content, user=0)

    img.save(path)
    return Path(path)


def create_multi_area_image(
    path: str | Path, files_by_area: dict[int, dict[str, bytes]], geometry_name: str = "ibm-3740"
) -> Path:
    """Create a CP/M disk image with files in multiple user areas.

    This helper is designed for MT-DI21a (multi-area image testing) where
    the same filename exists in different user areas to verify area isolation.

    Args:
        path: Destination file path for the created image.
        files_by_area: Mapping of user area numbers to dicts of filename→content.
            Example: {0: {"FOO.COM": b"area0"}, 3: {"FOO.COM": b"area3"}}
    geometry_name: Name of the geometry from the bundled database
        (default "ibm-3740" - 8-inch double-density).

    Returns:
        The Path to the created disk image.

    Example:
        >>> areas = {
        ...     0: {"TEST.TXT": b"user 0 content"},
        ...     3: {"TEST.TXT": b"user 3 content", "OTHER.DAT": b"data"},
        ... }
        >>> img_path = create_multi_area_image("/tmp/multi.img", areas)

    Satisfies: FR-170, FR-171.
    """
    geom = load_diskdefs().get(geometry_name)
    if geom is None:
        raise ValueError(f"unknown geometry: {geometry_name}")

    img = create_image(geom)

    for area, files in files_by_area.items():
        for name, content in files.items():
            img.write_file(name, content, user=area)

    img.save(path)
    return Path(path)
