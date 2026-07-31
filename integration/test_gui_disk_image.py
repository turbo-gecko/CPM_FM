"""§11.6 — disk image: Host-side mount, Copy to Remote over X-Modem (MT-DI04).

After opening a programmatically-generated CP/M disk image, verify that extracted
files in the Host pane can be copied to the remote scratch drive over X-Modem
exactly as if they were ordinary host files. This confirms FR-171 (disk-image
read and extraction) and the established Copy-to-Remote path (FR-106/FR-145).

All writes target the disposable scratch drive and clean up after themselves.
"""

from __future__ import annotations

import os

import pytest
from helpers.dialogs import (
    OVERWRITE,
    answer_conflict,
    answer_file_action,
    answer_invalid_name,
    silence_message_boxes,
)
from helpers.disk_image import create_multi_area_image, create_test_image


@pytest.mark.hil
@pytest.mark.mt("MT-DI04", "FR-171", "FR-106", "FR-145")
def test_disk_image_host_mount_copy_to_remote(gui, scratch_drive, monkeypatch, tmp_path):
    """Disk image extracted files copy to remote via X-Modem.

    Verifies: FR-171, FR-106, FR-145.
    """
    answer_invalid_name(monkeypatch)  # accept suggested 8.3 names
    answer_conflict(monkeypatch, action=OVERWRITE)  # overwrite existing files on remote
    messages = silence_message_boxes(monkeypatch)

    assert gui.connect()[0] == "ok"
    gui.set_drive(scratch_drive)
    gui.quiesce()  # drive change runs on a worker thread; wait for it

    # Create a test disk image with known files in User 0.
    image_path = tmp_path / "test.img"
    create_test_image(image_path)

    # Extract the disk image files to the Host pane's working directory.
    # This simulates what happens when a disk image is opened via File > Open Disk Image…
    workdir = tmp_path / "host_workdir"
    workdir.mkdir()

    from cpm_fm.utils.disk_image import open_image

    img = open_image(image_path)
    assert img is not None, f"Failed to open disk image: {image_path}"

    for entry in img.list_files():
        cpm_name = os.path.basename(entry.name)
        data = img.read_file(entry.name, user=entry.user)
        (workdir / cpm_name).write_bytes(data)

    # Point the Host pane at the extracted files.
    gui.win.host_dir = str(workdir)
    gui.refresh_host()

    # Verify the expected files appear in the Host pane listing.
    host_names = gui.host_names()
    assert len(host_names) > 0, f"Host pane is empty - files not found. Workdir: {workdir}"
    expected_files = ["HELLO.COM", "DATA.TXT", "BINARY.DAT", "LARGE.BIN"]
    for fname in expected_files:
        assert fname in host_names, f"{fname} not found in Host pane after mounting image"

    # Upload all files from the disk image to remote via Copy to Remote.
    # Use 60s quiesce timeout for slow RC2014 targets (same pattern as test_batch_transfer.py).
    gui.upload(expected_files, quiesce_timeout=60)
    critical = [args for kind, args in messages if kind == "critical"]
    assert not critical, f"Copy to Remote reported an error: {critical}"

    # Slow RC2014 targets may need more than the default 15 s quiesce window
    # for a full batch of X-Modem transfers; re-quiesce with a longer timeout
    # so the remote-list refresh that follows the batch also completes.
    gui.quiesce(timeout=60)

    # Verify transferred files appear on the remote side.
    remote_names = set(gui.remote_names())
    for fname in expected_files:
        assert fname in remote_names, f"{fname} not found in remote listing after upload"

    # Clean up: accept the mandatory FR-115 confirmation dialog, then delete
    # every transferred file in one remote multi-file operation.
    transferred = [
        fname
        for fname in expected_files
        if fname.upper() in {name.upper() for name in gui.remote_names()}
    ]
    if transferred:
        answer_file_action(monkeypatch, accepted=True)
        gui.win._remote_delete(transferred)
    gui.quiesce(timeout=30)


"""§11.7 — disk image: Remote-pane mount mutual exclusion with serial session (MT-DI14).

Tests that a Remote-pane disk image mount and a live serial session are mutually
exclusive (FR-176). Opening an image in the Remote pane while connected must fail
with an appropriate error, and disconnecting allows the mount to proceed. After
closing the Remote-mounted image, normal connection is restored.
"""


@pytest.mark.hil
@pytest.mark.mt("MT-DI14", "FR-176")
def test_remote_image_mount_refuses_connect(gui, monkeypatch, tmp_path):
    """Remote-pane disk image mount and live serial session are mutually exclusive.

    Verifies: FR-176.
    """
    answer_invalid_name(monkeypatch)
    answer_conflict(monkeypatch, action=OVERWRITE)

    assert gui.connect()[0] == "ok"

    image_path = tmp_path / "test.img"
    create_test_image(image_path)

    fired: list[tuple] = []
    import cpm_fm.app as app_mod

    for kind in ("critical", "warning", "information"):
        monkeypatch.setattr(
            app_mod.QMessageBox,
            kind,
            staticmethod(lambda *a, _k=kind, **k: fired.append((_k, a[1:])) or None),
        )

    remote_mount_shown = []

    def _prompt_mount_side_fake(self):
        remote_mount_shown.append(True)
        return "remote"

    monkeypatch.setattr(
        "cpm_fm.gui.mw_disk_image._DiskImageMixin._prompt_mount_side",
        _prompt_mount_side_fake,
    )

    gui.win.menu_open_image()

    assert len(remote_mount_shown) == 1, "_prompt_mount_side was not called"
    warning_shown = any(msg[0] == "warning" for msg in fired)
    assert warning_shown, "expected FR-176 warning dialog when mounting Remote while connected"

    assert not gui.win._image_workdir, "image should not be mounted after refused connect"
    assert gui.connected, "connection should remain active"

    gui.disconnect()
    assert not gui.connected

    fired.clear()
    remote_mount_shown.clear()

    from PySide6.QtWidgets import QFileDialog

    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        lambda *a, **k: (str(image_path), "All files (*.img *. IMG)"),
    )

    monkeypatch.setattr(
        "cpm_fm.gui.mw_disk_image._DiskImageMixin._prompt_mount_side",
        _prompt_mount_side_fake,
    )

    gui.win.menu_open_image()

    assert len(remote_mount_shown) == 1, "_prompt_mount_side was not called after disconnect"
    assert gui.win._image_workdir is not None, "image should be mounted in Remote pane"
    assert gui.win._image_pane == "remote", "image should be mounted in remote pane"

    gui.win.menu_close_image()
    gui.quiesce()

    assert gui.win._image_workdir is None, "image should be closed"
    assert not gui.connected

    assert gui.connect()[0] == "ok", "connection should succeed after closing Remote-mounted image"
    gui.disconnect()


"""§11.8 — disk image: Host-side mount, Copy to Remote preserves source user area (MT-DI21a).

Tests that when a Host-mounted multi-area disk image is opened and a file from
user area 3 is copied to the remote via X-Modem, it arrives in area 3 rather than
the default area 0. This verifies FR-188 (transfer matches source area).

All writes target the disposable scratch drive and clean up after themselves.
"""


@pytest.mark.hil
@pytest.mark.mt("MT-DI21a", "FR-188")
def test_disk_image_user_area_transfer_preserves_source(gui, scratch_drive, monkeypatch, tmp_path):
    """Host-mounted multi-area image: Copy to Remote sends file to its source area.

    Creates a disk image with files in user area 3, opens it Host-side, and copies
    one to the remote. Verifies the file arrives in area 3 and not area 0 through
    the GUI's existing serial session.

    Verifies: FR-188.
    """
    answer_invalid_name(monkeypatch)  # accept suggested 8.3 names
    answer_conflict(monkeypatch, action=OVERWRITE)  # overwrite existing files on remote
    messages = silence_message_boxes(monkeypatch)

    assert gui.connect()[0] == "ok"
    gui.set_drive(scratch_drive)
    gui.quiesce()  # drive change runs on a worker thread; wait for it

    # Create a multi-area disk image with a file in user area 3.
    # Using create_multi_area_image() helper to ensure the file exists in area 3.
    image_path = tmp_path / "multi_area.img"
    files_by_area = {
        0: {"HELLO.TXT": b"area0 content"},
        3: {"AREATEST.COM": b"area3 content for MT-DI21a"},
    }
    create_multi_area_image(image_path, files_by_area)

    # Open the image through the real Host-mount path so the staged-file map
    # retains each file's source user area for FR-188.
    from PySide6.QtWidgets import QFileDialog

    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        lambda *a, **k: (str(image_path), "All files (*.img *.dsk *.cpm)"),
    )
    monkeypatch.setattr(
        "cpm_fm.gui.mw_disk_image._DiskImageMixin._prompt_mount_side",
        lambda self: "host",
    )
    gui.win.menu_open_image()

    critical = [args for kind, args in messages if kind == "critical"]
    assert not critical, f"opening the multi-area image reported an error: {critical}"
    assert gui.win._image_pane == "host"
    assert gui.win._host_image_entry("AREATEST.COM") == ("AREATEST.COM", 3)

    # Verify the expected file appears in the Host pane listing.
    host_names = gui.host_names()
    assert "AREATEST.COM" in host_names, "AREATEST.COM not found in Host pane after mounting image"

    # Transfer the area-3 file to remote using Copy to Remote.
    gui.upload(["AREATEST.COM"], quiesce_timeout=60)
    critical = [args for kind, args in messages if kind == "critical"]
    assert not critical, f"Copy to Remote reported an error: {critical}"

    # Verify through the GUI's existing serial session: the file must be in its
    # source area 3 and absent from the default area 0.
    gui.set_user_area(3)
    assert "AREATEST.COM" in {name.upper() for name in gui.remote_names()}

    gui.set_user_area(0)
    assert "AREATEST.COM" not in {name.upper() for name in gui.remote_names()}

    # Clean up in area 3 through the GUI, accepting the mandatory FR-115 dialog.
    gui.set_user_area(3)
    if "AREATEST.COM" in {name.upper() for name in gui.remote_names()}:
        answer_file_action(monkeypatch, accepted=True)
        gui.win._remote_delete("AREATEST.COM")
        gui.quiesce(timeout=30)
    assert "AREATEST.COM" not in {name.upper() for name in gui.remote_names()}

    gui.set_user_area(0)
    gui.win.menu_close_image()
