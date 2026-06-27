from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import threading

    from cpm_fm.terminal.serial_manager import SerialManager


class MainWindowMixinBase:
    """Type-only view of the shared :class:`~cpm_fm.app.MainWindow` surface.

    ``MainWindow`` is assembled from several cohesive mixin modules
    (``gui/mw_*.py``) so no single source file is oversized (CR-007). Those
    mixins reach the window's shared state, cross-thread signals (NFR-004), and
    one another's methods through ``self``. Each mixin inherits this class so a
    static type checker can resolve those members; the declarations live under
    ``TYPE_CHECKING`` only, so at runtime this base is empty and contributes no
    behaviour or state (the real attributes are created by ``MainWindow``).

    Satisfies: CR-007, CR-009.
    """

    if TYPE_CHECKING:
        # --- shared instance state (created in MainWindow.__init__) ---
        settings: dict
        serial_mgr: SerialManager
        _rx_buffer: str
        _transfer_cancel: threading.Event
        _conflict_policy: str | None
        _conflict_answered: threading.Event
        _conflict_result: tuple[str, bool]
        _invalid_name_answered: threading.Event
        _invalid_name_result: tuple[str, str]

        # --- cross-thread GUI-marshalling signals (NFR-004) ---
        # Typed ``Any``: a PySide ``Signal`` is a descriptor whose bound
        # ``SignalInstance`` (with ``.emit``) only resolves on a ``QObject``;
        # the mixins are plain classes, so ``Any`` lets them call ``.emit``
        # without re-declaring each signal's argument types here.
        transfer_cancelled: Any
        batch_started: Any
        transfer_file_started: Any
        transfer_completed: Any
        error_raised: Any
        remote_files_ready: Any
        conflict_detected: Any
        invalid_name_detected: Any

        # --- methods that remain on MainWindow / non-transfer sections ---
        def set_status(self, text: str) -> None: ...
        def handle_terminal_send(self, text, append_eol: bool = True) -> None: ...
        def _capture_terminal_response(self, command: str, cancellable: bool = False) -> str: ...
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
        @staticmethod
        def _file_size(path: str) -> int: ...

        # --- transfer methods provided by sibling mixins (cross-mixin calls) ---
        def _debug(self, msg: str) -> None: ...
        def _launch_delay(self) -> float: ...
        def _issue_remote_cmd(
            self,
            cmd_key: str,
            default: str,
            filename: str,
            cmd_key_1k: str | None = None,
        ) -> None: ...
        def _cancellable_sleep(self, seconds: float) -> bool: ...
        def _on_transfer_bytes(self, direction, data) -> None: ...
        def _on_transfer_progress_cb(self, blocks, bytes_done, total) -> None: ...
        def _xmodem_1k_enabled(self) -> bool: ...
        def _wait_for_terminal_idle(self) -> None: ...
        def _finish_cancelled_batch(self, direction: str, succeeded: int) -> None: ...
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
