"""Tests for remote CP/M user-area (0–15) support (FR-181–FR-189, UIR-118, UIR-120).

These cover the user-area command building, the scoped drive-listing ordering
(USER applied before the drive change), the transfer-launch user-area set, the
tracked-area bookkeeping, the connect-time area read-back, the user-area-aware
no-response error (FR-159/FR-183) and the per-pane image user-area filter
(FR-189/UIR-120) — all without real serial hardware or worker threads (the
thread-spawning entry points delegate to the worker logic exercised directly
here).

Satisfies: FR-159, FR-181, FR-182, FR-183, FR-184, FR-189, UIR-118, UIR-120.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QSettings, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from cpm_fm.app import MainWindow  # noqa: E402
from cpm_fm.gui.window_state import WindowState  # noqa: E402
from cpm_fm.utils import i18n  # noqa: E402
from cpm_fm.utils.config_handler import DEFAULT_SETTINGS  # noqa: E402


class _FakeEntry:
    def __init__(self, name, user):
        self.name = name
        self.user = user


class _FakeImage:
    """Minimal image: two files sharing a name across two user areas."""

    def list_files(self):
        return [
            _FakeEntry("ASM.COM", 0),
            _FakeEntry("SHARED.TXT", 0),
            _FakeEntry("SHARED.TXT", 3),  # same name, different area (FR-185)
        ]

    def read_file(self, name, user=None):
        return f"{name}@{user}".encode()


@pytest.fixture(autouse=True)
def _english_language():
    i18n.set_language(i18n.DEFAULT_LANGUAGE)
    yield
    i18n.set_language(i18n.DEFAULT_LANGUAGE)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def state(tmp_path):
    settings = QSettings(str(tmp_path / "state.ini"), QSettings.Format.IniFormat)
    return WindowState(settings)


def test_default_settings_include_user_area_cmd():
    """Verifies: FR-182."""
    # FR-182: the user-area command is configurable, defaulting to "USER $1".
    assert DEFAULT_SETTINGS["user_area_cmd"] == "USER $1"


def test_user_combo_lists_0_to_15(qapp, state):
    """Verifies: UIR-118."""
    win = MainWindow(state)
    try:
        assert win.user_combo.count() == 16
        assert win.user_combo.itemText(0) == "0"
        assert win.user_combo.itemText(15) == "15"
    finally:
        win.close()


def test_apply_remote_user_area_sends_configured_command(qapp, monkeypatch, state):
    """Verifies: FR-182, FR-184."""
    win = MainWindow(state)
    try:
        win.settings = dict(DEFAULT_SETTINGS)
        win._remote_user = 5
        cmds: list[str] = []
        monkeypatch.setattr(
            win, "_capture_terminal_response", lambda cmd, **k: cmds.append(cmd) or ""
        )
        win._apply_remote_user_area()
        # FR-182: "$1" is replaced by the tracked area (FR-184).
        assert cmds == ["USER 5"]
    finally:
        win.close()


def test_apply_remote_user_area_noop_when_command_blank(qapp, monkeypatch, state):
    """Verifies: FR-182."""
    win = MainWindow(state)
    try:
        win.settings = dict(DEFAULT_SETTINGS, user_area_cmd="")
        win._remote_user = 3
        cmds: list[str] = []
        monkeypatch.setattr(
            win, "_capture_terminal_response", lambda cmd, **k: cmds.append(cmd) or ""
        )
        win._apply_remote_user_area()
        # FR-182: a blank command sends nothing (area tracked only).
        assert cmds == []
    finally:
        win.close()


def test_apply_remote_user_area_noop_when_already_in_area(qapp, monkeypatch, state):
    """Verifies: FR-182, FR-184."""
    win = MainWindow(state)
    try:
        win.settings = dict(DEFAULT_SETTINGS)
        # FR-182/FR-184: the remote is already in area 3 -> no USER command,
        # so an unused selection leaves the existing listing flow unchanged.
        win._remote_user = 3
        win._applied_user_area = 3
        cmds: list[str] = []
        monkeypatch.setattr(
            win, "_capture_terminal_response", lambda cmd, **k: cmds.append(cmd) or ""
        )
        win._apply_remote_user_area()
        assert cmds == []
    finally:
        win.close()


def test_change_drive_applies_user_area_before_listing(qapp, monkeypatch, state):
    """Verifies: FR-182, FR-183."""
    win = MainWindow(state)
    try:
        win.settings = dict(DEFAULT_SETTINGS)
        win._remote_user = 4
        calls: list[str] = []
        # A drive prompt is returned so the drive change is treated as successful.
        monkeypatch.setattr(
            win, "_capture_terminal_response", lambda cmd, **k: calls.append(cmd) or "A>"
        )
        monkeypatch.setattr(win, "_do_refresh_remote_logic", lambda: calls.append("LIST"))
        win._do_change_drive_logic("A")
        # FR-182: USER is issued before the drive-change command, then the listing.
        assert calls == ["USER 4", "A:", "LIST"]
    finally:
        win.close()


def test_change_user_area_tracks_selection_when_disconnected(qapp, state):
    """Verifies: FR-181, FR-184."""
    win = MainWindow(state)
    try:
        win.serial_mgr.terminal_connected = False
        win._remote_user = 0
        win.change_user_area(7)
        # FR-184: the selection is recorded even when not connected (authoritative).
        assert win._remote_user == 7
    finally:
        win.close()


def test_apply_transfer_user_area_sets_area_then_settles(qapp, monkeypatch, state):
    """Verifies: FR-183."""
    win = MainWindow(state)
    try:
        win.settings = dict(DEFAULT_SETTINGS)
        sent: list[str] = []
        slept: list[float] = []
        monkeypatch.setattr(win, "handle_terminal_send", lambda text, **k: sent.append(text))
        monkeypatch.setattr(win, "_cancellable_sleep", lambda s, *a, **k: slept.append(s) or False)
        win._apply_transfer_user_area(9)
        # FR-183: USER n is sent on the Terminal Port, then a settle before launch.
        assert sent == ["USER 9"]
        assert slept and slept[0] > 0
    finally:
        win.close()


def test_apply_transfer_user_area_noop_when_command_blank(qapp, monkeypatch, state):
    """Verifies: FR-183."""
    win = MainWindow(state)
    try:
        win.settings = dict(DEFAULT_SETTINGS, user_area_cmd="")
        sent: list[str] = []
        monkeypatch.setattr(win, "handle_terminal_send", lambda text, **k: sent.append(text))
        monkeypatch.setattr(win, "_cancellable_sleep", lambda *a, **k: False)
        win._apply_transfer_user_area(2)
        assert sent == []
    finally:
        win.close()


def test_apply_transfer_user_area_noop_when_already_in_area(qapp, monkeypatch, state):
    """Verifies: FR-183, FR-184."""
    win = MainWindow(state)
    try:
        win.settings = dict(DEFAULT_SETTINGS)
        # FR-183/FR-184: the remote is already in area 0 -> no USER command,
        # so an ordinary area-0 transfer is unchanged from before the feature.
        win._applied_user_area = 0
        sent: list[str] = []
        monkeypatch.setattr(win, "handle_terminal_send", lambda text, **k: sent.append(text))
        monkeypatch.setattr(win, "_cancellable_sleep", lambda *a, **k: False)
        win._apply_transfer_user_area(0)
        assert sent == []
    finally:
        win.close()


def test_connect_probe_reads_back_zcpr_area(qapp, monkeypatch, state):
    """Verifies: FR-184, DR-051."""
    win = MainWindow(state)
    try:
        monkeypatch.setattr(win, "refresh_remote_files", lambda: None)
        # FR-184/DR-051: a ZCPR prompt exposed area 6 during the probe.
        win._probe_user_area = 6
        win._on_connect_probe_ok("A")
        assert win._remote_user == 6
        assert win.user_combo.currentIndex() == 6
        # FR-182: the remote is recorded as already in this area (issue-on-change).
        assert win._applied_user_area == 6
    finally:
        win.close()


def test_connect_probe_defaults_area_to_zero_on_cpm22(qapp, monkeypatch, state):
    """Verifies: FR-184."""
    win = MainWindow(state)
    try:
        monkeypatch.setattr(win, "refresh_remote_files", lambda: None)
        # FR-184: CP/M 2.2 exposes no area (probe read None) -> default to 0.
        win._probe_user_area = None
        win._remote_user = 9  # stale value from a prior session
        win._on_connect_probe_ok("A")
        assert win._remote_user == 0
        assert win.user_combo.currentIndex() == 0
        assert win._applied_user_area == 0
    finally:
        win.close()


# ------------------------------------------------------ disk image (#7 / FR-185+)


def test_extract_preserves_area_and_disambiguates_duplicates(qapp, state, tmp_path):
    """Verifies: FR-185."""
    win = MainWindow(state)
    try:
        workdir = tmp_path / "wd"
        workdir.mkdir()
        failed = win._extract_files(_FakeImage(), str(workdir))
        assert failed == []
        # FR-185: the duplicate name is disambiguated so no file is overwritten.
        staged = set(os.listdir(workdir))
        assert staged == {"ASM.COM", "SHARED.TXT", "SHARED~3.TXT"}
        # FR-185: each staged file records its real CP/M name and source area.
        assert win._image_stage_map["ASM.COM"] == ("ASM.COM", 0)
        assert win._image_stage_map["SHARED.TXT"] == ("SHARED.TXT", 0)
        assert win._image_stage_map["SHARED~3.TXT"] == ("SHARED.TXT", 3)
        # FR-185: each file was read from its own area (correct content).
        assert (workdir / "SHARED.TXT").read_bytes() == b"SHARED.TXT@0"
        assert (workdir / "SHARED~3.TXT").read_bytes() == b"SHARED.TXT@3"
    finally:
        win.close()


def test_pane_area_map_only_for_mounted_pane(qapp, state, tmp_path):
    """Verifies: UIR-119, FR-186."""
    win = MainWindow(state)
    try:
        win._image_workdir = str(tmp_path)
        win._image_stage_map = {"ASM.COM": ("ASM.COM", 0), "SHARED~3.TXT": ("SHARED.TXT", 3)}
        win._image_pane = "host"
        # UIR-119: the map is offered to the pane the image is mounted in only.
        assert win._pane_area_map("host") == {"ASM.COM": 0, "SHARED~3.TXT": 3}
        assert win._pane_area_map("remote") is None
    finally:
        win.close()


def test_render_shows_area_prefix_but_keeps_name(qapp, state):
    """Verifies: UIR-119."""
    win = MainWindow(state)
    try:
        win._render_file_list(
            win.host_list,
            ["ASM.COM", "GAME.COM"],
            win.host_filter,
            win.host_sort_combo,
            win.host_sort_dir_btn,
            area_map={"GAME.COM": 3},
        )
        rows = {
            win.host_list.item(i).data(Qt.ItemDataRole.UserRole): win.host_list.item(i).text()
            for i in range(win.host_list.count())
        }
        # UIR-119: the real filename is stored; the display text carries the area.
        assert rows["GAME.COM"] == "U3  GAME.COM"
        assert rows["ASM.COM"] == "ASM.COM"  # no map entry -> plain name
    finally:
        win.close()


def _arm_host_image(win, tmp_path):
    """Set up a Host-mounted image with two staged files in areas 0 and 3."""
    workdir = tmp_path / "wd"
    workdir.mkdir()
    (workdir / "HELLO.TXT").write_bytes(b"hi")
    (workdir / "GAME.COM").write_bytes(b"game")
    win._image_workdir = str(workdir)
    win._image_pane = "host"
    win.host_dir = str(workdir)
    win._image_stage_map = {"HELLO.TXT": ("HELLO.TXT", 0), "GAME.COM": ("GAME.COM", 3)}
    return workdir


def _run_copy_to_remote(win, monkeypatch, workdir):
    """Drive _transfer_to_remote_batch with I/O neutralised; return per-file (name, area)."""
    captured = []
    monkeypatch.setattr(win, "_fresh_remote_names", lambda: set())
    monkeypatch.setattr(win, "_wait_for_terminal_idle", lambda: None)
    monkeypatch.setattr(win, "_record_history", lambda *a, **k: None)
    monkeypatch.setattr(
        win,
        "_send_one_to_remote",
        lambda fp, rn=None, user_area=None: captured.append((rn, user_area)) or True,
    )
    # Block the batch's Qt signal side effects (progress dialog etc.) without
    # touching the signals themselves, so closeEvent's teardown still works.
    win.blockSignals(True)
    try:
        win._transfer_to_remote_batch([str(workdir / "HELLO.TXT"), str(workdir / "GAME.COM")])
    finally:
        win.blockSignals(False)
    return {rn: ua for (rn, ua) in captured}


def test_image_to_remote_matches_source_area(qapp, monkeypatch, state, tmp_path):
    """Verifies: FR-188."""
    win = MainWindow(state)
    try:
        win.settings = dict(DEFAULT_SETTINGS)  # image_area_mode="match"
        win._remote_user = 9  # selected area — must be ignored in match mode
        workdir = _arm_host_image(win, tmp_path)
        result = _run_copy_to_remote(win, monkeypatch, workdir)
        # FR-188: each image file is sent into its own source area.
        assert result == {"HELLO.TXT": 0, "GAME.COM": 3}
    finally:
        win.close()


def test_image_to_remote_selected_mode_uses_selected_area(qapp, monkeypatch, state, tmp_path):
    """Verifies: FR-188."""
    win = MainWindow(state)
    try:
        win.settings = dict(DEFAULT_SETTINGS, image_area_mode="selected")
        win._remote_user = 7
        workdir = _arm_host_image(win, tmp_path)
        result = _run_copy_to_remote(win, monkeypatch, workdir)
        # FR-188 "selected": every file goes to the selected area (None -> default).
        assert result == {"HELLO.TXT": None, "GAME.COM": None}
    finally:
        win.close()


# ------------------------------------------------ no-response error message (FR-159)


def test_no_response_message_names_user_area_when_nonzero(qapp, state):
    """Verifies: FR-159, FR-183."""
    win = MainWindow(state)
    try:
        win._last_xmodem_no_response = True
        win._applied_user_area = 3
        # FR-159/FR-183: a non-zero applied area upgrades the diagnosis to name
        # the area and the reachability cause, per direction.
        send_msg = win._transfer_fail_message("GO.COM", "remote")
        assert "GO.COM" in send_msg
        assert "user area 3" in send_msg
        assert "Send to Remote" in send_msg
        recv_msg = win._transfer_fail_message("GO.COM", "host")
        assert "user area 3" in recv_msg
        assert "Receive from Remote" in recv_msg
    finally:
        win.close()


def test_no_response_message_area_zero_is_unchanged(qapp, state):
    """Verifies: FR-159."""
    win = MainWindow(state)
    try:
        win._last_xmodem_no_response = True
        win._applied_user_area = 0
        # FR-159: the area-0 (feature-unused) path is byte-for-byte the old message.
        msg = win._transfer_fail_message("GO.COM", "remote")
        assert msg == i18n.tr("error.transfer_no_response_send", name="GO.COM")
        assert "user area" not in msg
    finally:
        win.close()


def test_fail_message_generic_when_not_no_response(qapp, state):
    """Verifies: FR-159."""
    win = MainWindow(state)
    try:
        win._last_xmodem_no_response = False
        win._applied_user_area = 3  # irrelevant: this was not a silent handshake
        msg = win._transfer_fail_message("GO.COM", "remote")
        assert msg == i18n.tr("error.transfer_failed", name="GO.COM")
    finally:
        win.close()


# --------------------------------------------- image user-area filter (FR-189/UIR-120)


def _arm_remote_image_areas(win, tmp_path):
    """Mount a Remote-side image with files in areas 0 and 3 (one dup area)."""
    workdir = tmp_path / "wdr"
    workdir.mkdir()
    win._image_workdir = str(workdir)
    win._image_pane = "remote"
    win._image_stage_map = {
        "A.COM": ("A.COM", 0),
        "B.COM": ("B.COM", 3),
        "C.COM": ("C.COM", 3),
    }
    win._remote_files = ["A.COM", "B.COM", "C.COM"]
    return workdir


def test_area_filter_hidden_without_image(qapp, state):
    """Verifies: UIR-120."""
    win = MainWindow(state)
    try:
        win._update_area_filter("host")
        # UIR-120: with no image mounted the combo is empty and hidden.
        assert win.host_area_filter.isHidden()
        assert win.host_area_filter.count() == 0
    finally:
        win.close()


def test_area_filter_populated_with_present_areas(qapp, state, tmp_path):
    """Verifies: UIR-120, FR-189."""
    win = MainWindow(state)
    try:
        _arm_remote_image_areas(win, tmp_path)
        win._update_area_filter("remote")
        combo = win.remote_area_filter
        assert not combo.isHidden()
        # UIR-120: All (userData None) followed by exactly the present areas,
        # sorted, duplicates collapsed.
        assert [combo.itemData(i) for i in range(combo.count())] == [None, 0, 3]
        assert combo.itemText(0) == i18n.tr("main.area_filter_all")
        assert combo.itemText(2) == "U3"
    finally:
        win.close()


def test_area_filter_narrows_listing_to_selected_area(qapp, state, tmp_path):
    """Verifies: FR-189."""
    win = MainWindow(state)
    try:
        _arm_remote_image_areas(win, tmp_path)
        win._update_area_filter("remote")
        combo = win.remote_area_filter
        combo.setCurrentIndex(combo.findData(3))
        win._apply_remote_view()
        shown = {
            win.remote_list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(win.remote_list.count())
        }
        # FR-189: only the area-3 files remain.
        assert shown == {"B.COM", "C.COM"}
    finally:
        win.close()


def test_area_filter_all_shows_every_area(qapp, state, tmp_path):
    """Verifies: FR-189."""
    win = MainWindow(state)
    try:
        _arm_remote_image_areas(win, tmp_path)
        win._apply_remote_view()  # default selection is All
        shown = {
            win.remote_list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(win.remote_list.count())
        }
        # FR-189: All is the default and lists every area.
        assert shown == {"A.COM", "B.COM", "C.COM"}
    finally:
        win.close()


def test_open_image_preserves_area_map_end_to_end(qapp, monkeypatch, state, tmp_path):
    """Verifies: FR-185, FR-189, UIR-120.

    Regression: ``menu_open_image`` calls ``_cleanup_image_workdir`` (which
    resets ``_image_stage_map``) *after* ``_extract_files`` builds it, so the map
    must be restored for the just-opened image — otherwise the area column and
    the area filter see an empty map (only "All").
    """
    from PySide6.QtWidgets import QFileDialog

    from cpm_fm.gui import mw_disk_image as mod

    class _Geom:
        name = "fake"

    class _Img(_FakeImage):
        geom = _Geom()

    win = MainWindow(state)
    try:
        workdir = tmp_path / "wd"
        workdir.mkdir()
        monkeypatch.setattr(win, "_maybe_prompt_save_image", lambda: True)
        monkeypatch.setattr(win, "_prompt_mount_side", lambda: "remote")
        win.serial_mgr.terminal_connected = False
        monkeypatch.setattr(
            QFileDialog, "getOpenFileName", lambda *a, **k: (str(tmp_path / "disk.img"), "")
        )
        monkeypatch.setattr(win, "_resolve_geometry", lambda p: object())
        monkeypatch.setattr(mod, "open_image", lambda p, d: _Img())
        monkeypatch.setattr(mod, "make_temp_dir", lambda prefix: str(workdir))

        win.menu_open_image()

        # FR-185: the map survived cleanup and reflects the image's real areas.
        assert win._image_stage_map, "stage map was wiped by cleanup"
        areas = sorted({area for (_cpm, area) in win._image_stage_map.values()})
        assert areas == [0, 3]
        # UIR-120/FR-189: the filter combo offers those areas, not just All.
        combo = win.remote_area_filter
        assert [combo.itemData(i) for i in range(combo.count())] == [None, 0, 3]
    finally:
        win.close()
