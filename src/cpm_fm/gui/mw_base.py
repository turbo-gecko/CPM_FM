from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    import threading

    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QComboBox, QLineEdit, QToolButton

    from cpm_fm.gui.file_list_widget import FileListWidget
    from cpm_fm.gui.terminal_window import TerminalWindow
    from cpm_fm.gui.transfer_history_dialog import TransferHistoryDialog
    from cpm_fm.gui.window_state import WindowState
    from cpm_fm.terminal.serial_manager import SerialManager
    from cpm_fm.terminal.vt100_engine import VT100Engine
    from cpm_fm.utils.config_handler import ConfigHandler
    from cpm_fm.utils.disk_image import CpmFileEntry, DiskDef
    from cpm_fm.utils.transfer_history import TransferHistory


class MainWindowMixinBase:
    """Type-only view of the shared :class:`~cpm_fm.app.MainWindow` surface.

    ``MainWindow`` is assembled from several cohesive mixin modules
    (``gui/mw_*.py``) so no single source file is oversized (CR-007). Those
    mixins reach the window's shared state, cross-thread signals (NFR-004), and
    one another's methods through ``self``. Each mixin inherits this class so a
    static type checker can resolve those members; the declarations live under
    ``TYPE_CHECKING`` only, so at runtime this base is empty and contributes no
    behaviour or state (the real attributes are created by ``MainWindow``).
    """

    if TYPE_CHECKING:
        # --- shared instance state (created in MainWindow.__init__) ---
        settings: dict
        serial_mgr: SerialManager
        config_handler: ConfigHandler
        transfer_history: TransferHistory
        window_state: WindowState
        _rx_buffer: str
        _tx_buffer: str
        _local_echo: bool
        _remote_capture_buffer: str
        _capture_active: bool
        _term_engine: VT100Engine
        # The non-modal Terminal Window (UIR-060) and Transfer History window
        # (UIR-083), created on first use; None until then.
        terminal_win: TerminalWindow | None
        _history_dialog: TransferHistoryDialog | None
        _transfer_cancel: threading.Event
        _probe_cancel: threading.Event
        _probe_thread: threading.Thread | None
        _probe_user_area: int | None
        _conflict_policy: str | None
        _conflict_answered: threading.Event
        _conflict_result: tuple[str, bool]
        _invalid_name_answered: threading.Event
        _invalid_name_result: tuple[str, str]
        _backup_confirm_answered: threading.Event
        _backup_confirm_result: bool
        _last_xmodem_no_response: bool
        host_dir: str
        # Disk-image (FR-171): temp workdir of the open image and its source path.
        _image_workdir: str | None
        _image_source: str | None
        # Disk-image write (FR-174): the geometry the image was decoded with, so
        # Save Image… can re-open the source with matching geometry to re-pack.
        _image_geom: DiskDef | None
        # Disk-image details view (FR-173/UIR-109): file metadata captured at open
        # time and the enable-toggled Image Details… menu action.
        _image_files: list[CpmFileEntry]
        # FR-185: staged filename -> (CP/M name, user area) for the open image.
        _image_stage_map: dict[str, tuple[str, int]]
        _image_details_action: QAction | None
        # Disk-image write (FR-174/UIR-110): the enable-toggled Save Image… action.
        _save_image_action: QAction | None
        # Copy-to-image (FR-175): signature of the working dir as opened/last saved
        # (None when no image is open), used to detect unsaved staged changes.
        _image_baseline: set[tuple[str, int, int]] | None
        # Dual-pane mount (FR-176): which pane the open image occupies — "host"
        # (default) or "remote". Meaningful only while an image is open.
        _image_pane: str
        # Close Disk Image (FR-177): the real host directory active immediately
        # before a Host-side image was opened, restored on close (None when none
        # recorded). The Close Disk Image… menu action, enabled only while open.
        _pre_image_host_dir: str | None
        _close_image_action: QAction | None
        # New empty image (FR-178): the New Disk Image… menu action (always
        # available since disk-image writing is no longer opt-in, v2.35).
        _new_image_action: QAction | None
        # FR-179: the folder where disk-image files live (Open/New/Save Image
        # browse root), tracked separately from host_dir.
        image_dir: str

        # --- file-pane widgets and their canonical (unfiltered) name lists ---
        host_list: FileListWidget
        remote_list: FileListWidget
        _host_files: list[str]
        _remote_files: list[str]
        host_filter: QLineEdit
        remote_filter: QLineEdit
        host_sort_combo: QComboBox
        remote_sort_combo: QComboBox
        host_sort_dir_btn: QToolButton
        remote_sort_dir_btn: QToolButton
        # UIR-120: per-pane user-area filter drop-down (hidden until an image is
        # mounted in that pane).
        host_area_filter: QComboBox
        remote_area_filter: QComboBox
        _restoring_filter_sort: bool
        # UIR-017: remote drive-selection drop-down (disabled while a disk image
        # is mounted in the Remote pane, FR-176).
        drive_combo: QComboBox
        # UIR-118: remote user-area (0–15) selection drop-down.
        user_combo: QComboBox
        # FR-184: the tracked, authoritative current remote user area (0–15).
        _remote_user: int
        # FR-182: the area the remote is believed to be in (issue-on-change).
        _applied_user_area: int | None

        # --- cross-thread GUI-marshalling signals (NFR-004) ---
        # Typed ``Any``: a PySide ``Signal`` is a descriptor whose bound
        # ``SignalInstance`` (with ``.emit``) only resolves on a ``QObject``;
        # the mixins are plain classes, so ``Any`` lets them call ``.emit``
        # without re-declaring each signal's argument types here.
        term_write: Any
        transfer_cancelled: Any
        batch_started: Any
        transfer_file_started: Any
        transfer_completed: Any
        error_raised: Any
        remote_files_ready: Any
        conflict_detected: Any
        invalid_name_detected: Any
        backup_restore_confirm: Any
        drive_not_found: Any
        connect_probe_ok: Any
        connect_probe_failed: Any

        # --- methods that remain on MainWindow / non-transfer sections ---
        def set_status(self, text: str) -> None: ...
        def _register_text(self, setter: Callable[[str], None], key: str) -> None: ...
        def handle_terminal_send(self, text, append_eol: bool = True) -> None: ...
        def _capture_terminal_response(
            self, command: str, cancellable: bool = False, cancel_event=None
        ) -> str: ...
        def _confirm_dialog(
            self,
            title: str,
            message: str,
            accept_label: str,
            *,
            warning: bool = False,
            default_accept: bool = True,
        ) -> bool: ...
        def _record_history(
            self,
            filename: str,
            path: str,
            direction: str,
            status: str,
            size: int,
            error: str,
            retry: bool,
        ) -> None: ...
        def _erase_remote_file(self, name: str) -> None: ...
        def _cleanup_image_workdir(self) -> None: ...
        def menu_image_details(self) -> None: ...
        def menu_close_image(self) -> None: ...
        def menu_new_image(self) -> None: ...
        def menu_save_image(self) -> bool: ...
        def _update_save_image_action(self) -> None: ...
        def _maybe_prompt_save_image(self) -> bool: ...
        def _capture_image_baseline(self) -> None: ...
        def _image_is_dirty(self) -> bool: ...
        # Dual-pane mount (FR-176).
        def _remote_is_image(self) -> bool: ...
        # Disk-image user areas (FR-185/FR-188).
        def _host_image_entry(self, staged_name: str) -> tuple[str, int] | None: ...
        def _list_image_remote(self) -> None: ...
        def _copy_host_to_image(self, source_paths: list[str]) -> None: ...
        def _copy_image_to_host(self, names: list[str]) -> None: ...
        def _update_remote_group_title(self) -> None: ...
        def _update_host_group_title(self) -> None: ...
        def refresh_host_files(self) -> None: ...
        def refresh_remote_files(self) -> None: ...
        # Remote user-area selection (FR-181–FR-184).
        def change_user_area(self, index: int) -> None: ...
        def _apply_remote_user_area(self) -> None: ...
        def _apply_transfer_user_area(self, area: int) -> None: ...
        def _apply_remote_view(self) -> None: ...
        @staticmethod
        def _file_size(path: str) -> int: ...

        # --- transfer methods provided by sibling mixins (cross-mixin calls) ---
        def _debug(self, msg: str) -> None: ...
        def _launch_delay(self) -> float: ...
        def _interfile_delay(self) -> float: ...
        def _handshake_timeout(self) -> float: ...
        def _issue_remote_cmd(
            self,
            cmd_key: str,
            default: str,
            filename: str,
            cmd_key_1k: str | None = None,
        ) -> None: ...
        def _cancellable_sleep(self, seconds: float, cancel_event=None) -> bool: ...
        def _on_transfer_bytes(self, direction, data) -> None: ...
        def _on_transfer_progress_cb(self, blocks, bytes_done, total) -> None: ...
        def _xmodem_1k_enabled(self) -> bool: ...
        def _execute_sequence(self, steps) -> None: ...
        def _wait_for_terminal_idle(self) -> None: ...
        def _finish_cancelled_batch(self, direction: str, succeeded: int) -> None: ...
        def _transfer_to_remote_batch(self, filepaths, retry: bool = False) -> None: ...
        def _transfer_to_host_batch(self, save_paths, retry: bool = False) -> None: ...
        def _fresh_remote_names(self) -> set[str]: ...
        def _prompt_invalid_name(self, name: str) -> tuple[str, str]: ...
        @staticmethod
        def _destination_conflict(
            direction: str,
            path: str,
            remote_names: set[str],
            dest_name: str | None = None,
        ) -> bool: ...
        def _resolve_conflict(self, name: str, direction: str) -> str: ...
