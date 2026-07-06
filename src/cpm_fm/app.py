from __future__ import annotations

import os
import shlex
import subprocess
import sys
import threading
from typing import Callable, cast

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QActionGroup, QFontMetrics
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStyle,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from cpm_fm.gui.conflict_dialog import CANCEL
from cpm_fm.gui.dialog_buttons import build_button_row
from cpm_fm.gui.file_list_widget import FileListWidget
from cpm_fm.gui.macro_window import MacroWindow
from cpm_fm.gui.mw_backup_restore import _BackupRestoreMixin
from cpm_fm.gui.mw_config import _ConfigMixin
from cpm_fm.gui.mw_context_menu import _ContextMenuMixin
from cpm_fm.gui.mw_file_panes import _FilePanesMixin
from cpm_fm.gui.mw_history import _HistoryMixin
from cpm_fm.gui.mw_remote import _RemoteMixin
from cpm_fm.gui.mw_transfer_batches import _TransferBatchesMixin
from cpm_fm.gui.mw_transfer_guards import _TransferGuardsMixin
from cpm_fm.gui.mw_transfers import _TransfersMixin
from cpm_fm.gui.terminal_window import TerminalWindow
from cpm_fm.gui.theme import app_icon, apply_theme
from cpm_fm.gui.transfer_dialog import TransferProgressDialog
from cpm_fm.gui.window_state import APP, ORG, WindowState
from cpm_fm.terminal.serial_manager import SerialManager
from cpm_fm.terminal.vt100_engine import VT100Engine
from cpm_fm.utils.config_handler import ConfigHandler
from cpm_fm.utils.i18n import (
    available_languages,
    current_language,
    display_name,
    set_language,
    tr,
)
from cpm_fm.utils.transfer_history import TransferHistory


def build_viewer_args(template: str, path: str) -> list[str]:
    """Build the argument vector for launching the viewer/editor (FR-112).

    Splits the configured ``viewer_cmd`` template into tokens *before*
    substituting, so a file path containing spaces or backslashes is never
    re-parsed by the shell-style splitter. The ``$1`` token is replaced by
    ``path``; if no ``$1`` token is present, ``path`` is appended as the final
    argument. Splitting uses non-POSIX rules on Windows so backslashes in the
    command are preserved.

    Satisfies: FR-112.
    """
    try:
        tokens = shlex.split(template, posix=(os.name != "nt"))
    except ValueError:
        tokens = template.split()

    args: list[str] = []
    substituted = False
    for tok in tokens:
        # Strip surrounding quotes left by a non-POSIX split.
        if len(tok) >= 2 and tok[0] == tok[-1] and tok[0] in ("'", '"'):
            tok = tok[1:-1]
        if tok == "$1":
            args.append(path)
            substituted = True
        else:
            args.append(tok)
    if not substituted:
        args.append(path)
    return args


class MainWindow(
    QMainWindow,
    _FilePanesMixin,
    _ContextMenuMixin,
    _RemoteMixin,
    _BackupRestoreMixin,
    _TransfersMixin,
    _TransferBatchesMixin,
    _TransferGuardsMixin,
    _ConfigMixin,
    _HistoryMixin,
):
    """Main application window (SRS docs/cpm_fm_requirements.md).

    All GUI updates originating from background threads (serial reads, file
    transfers, the remote-list capture worker) are delivered to the Qt GUI
    thread exclusively via the signals below, which are connected with the
    implicitly-queued cross-thread default (NFR-001, NFR-004). No widget is
    touched directly from a worker thread.

    Satisfies: STR-002.

    Cross-thread GUI marshalling signals.
    """

    status_changed = Signal(str)
    term_write = Signal(bytes)
    remote_files_ready = Signal(dict)
    error_raised = Signal(str, str)
    transfer_completed = Signal(str)
    batch_started = Signal(str, int)
    transfer_file_started = Signal(str, int, int)
    transfer_progress = Signal(int, int)
    drive_not_found = Signal(str)
    connect_probe_ok = Signal(str)
    connect_probe_failed = Signal()
    view_file_ready = Signal(str)
    transfer_cancelled = Signal(str, bool)
    conflict_detected = Signal(str, str)
    invalid_name_detected = Signal(str)
    backup_restore_confirm = Signal(str)

    def __init__(
        self,
        window_state: WindowState | None = None,
        transfer_history: TransferHistory | None = None,
    ):
        """
        Satisfies: FR-003, FR-004, FR-005, FR-070, FR-124, FR-141.
        """
        super().__init__()

        # Core Components
        self.serial_mgr = SerialManager()
        self.config_handler = ConfigHandler()
        # FR-004/FR-005: persisted window geometry and last-used config file.
        # Injectable so tests can isolate the store from the host's real settings.
        self.window_state = window_state if window_state is not None else WindowState()
        # FR-140/FR-141: persistent per-file transfer history. Injectable so tests
        # use an isolated temporary file rather than the host's real history.
        self.transfer_history = (
            transfer_history if transfer_history is not None else TransferHistory()
        )
        self.settings: dict = {}

        # FR-124: activate the persisted GUI language before any widget text is
        # built, so the first paint is already localised. _i18n_registry maps a
        # widget text-setter to its translation key for live re-translation
        # (FR-123); _register_text populates it during setup.
        set_language(self.window_state.language)
        self._i18n_registry: list[tuple[Callable[[str], None], str]] = []

        # FR-125: the base name (no path, no extension) of the loaded config
        # file, shown in the title bar. Empty until a config is loaded.
        self._config_name = ""
        self._update_window_title()
        self.resize(900, 560)

        # UI State
        self.terminal_win: TerminalWindow | None = None
        # UIR-097/FR-164: the floating Macro Window, created on first use when
        # the Terminal Window's Macros checkbox is checked.
        self.macro_win: MacroWindow | None = None
        # FR-105: the modal transfer-progress dialog, live only for the duration
        # of a transfer. Owned and torn down on the GUI thread.
        self._transfer_dialog: TransferProgressDialog | None = None
        # FR-120: set on the GUI thread (Cancel button) and polled by the
        # transfer worker thread to abort the in-progress transfer.
        self._transfer_cancel = threading.Event()
        # FR-146/FR-147: file-conflict resolution. The transfer worker thread
        # emits conflict_detected and blocks on _conflict_answered; the GUI
        # thread shows the dialog (NFR-004) and stores (action, apply_to_all) in
        # _conflict_result before setting the event. _conflict_policy holds a
        # batch-wide Overwrite/Skip decision once the user ticks "apply to all";
        # it is reset at the start of each batch so it never crosses transfers.
        self._conflict_answered = threading.Event()
        self._conflict_result: tuple[str, bool] = (CANCEL, False)
        self._conflict_policy: str | None = None
        # FR-159: whether the most recent XModem handshake got no response at
        # all (a misconfigured launch command), reset per batch.
        self._last_xmodem_no_response = False
        # FR-148/FR-149: CP/M 8.3 name-validation prompt. The upload worker emits
        # invalid_name_detected and blocks on _invalid_name_answered; the GUI
        # thread shows the dialog (NFR-004) and stores (action, new_name) in
        # _invalid_name_result before setting the event.
        self._invalid_name_answered = threading.Event()
        self._invalid_name_result: tuple[str, str] = (CANCEL, "")
        # FR-152: Backup/Restore destructive-operation confirmation. The worker
        # emits backup_restore_confirm and blocks on _backup_confirm_answered;
        # the GUI thread shows the dialog (NFR-004) and stores the boolean
        # (Continue) choice in _backup_confirm_result before setting the event.
        self._backup_confirm_answered = threading.Event()
        self._backup_confirm_result = False
        self.host_dir = os.getcwd()
        # FR-130/FR-133: the canonical, unfiltered file names for each pane. The
        # visible QListWidget rows are derived from these by filter_and_sort, so
        # filtering/sorting can be re-applied without re-reading the source.
        self._host_files: list[str] = []
        self._remote_files: list[str] = []
        # FR-134: guards persistence while restoring saved filter/sort state, so
        # the restore does not immediately re-write what it just read.
        self._restoring_filter_sort = False
        self._remote_capture_buffer = ""
        self._capture_active = False
        # Cached Local Echo state so worker threads read a plain bool rather
        # than touching the checkbox widget (NFR-004).
        self._local_echo = False

        # FR-090/FR-092: receive and transmit data buffers, retained until
        # explicitly cleared via the Terminal Window Clear button (FR-095).
        self._rx_buffer = ""
        self._tx_buffer = ""

        # FR-091: VT-100/ANSI screen model fed the raw received byte stream. The
        # tee in handle_terminal_recv drives it; the Terminal Window renders from
        # it (wired in a later stage). Created up front so bytes are interpreted
        # from the first connect, whether or not the window has been opened.
        self._term_engine = VT100Engine()

        self.setup_menu()
        self.setup_toolbar()
        self.setup_layout()
        self.setup_status_bar()
        self._connect_signals()

        # FR-134: load each pane's saved filter text and sort settings into the
        # newly-built controls before the first list is populated, so the very
        # first render already reflects the restored preferences.
        self._restore_filter_sort()

        # FR-090 / FR-074: capture received data regardless of whether the
        # Terminal Window has been opened (the window may not exist yet).
        self.serial_mgr.on_data_received = self.handle_terminal_recv

        self.refresh_host_files()

        # FR-004: restore the main window's saved size/position (overrides the
        # default resize above when a prior session stored geometry).
        self.window_state.restore_geometry("main", self)

        # FR-005: reload and apply the last-used configuration file. If none is
        # remembered, or it no longer exists, the app starts unconfigured
        # (FR-003) and settings come from File > Load or the config dialogs.
        last = self.window_state.last_config
        if last and os.path.exists(last):
            self.load_config(last)

    # ------------------------------------------------------------------ i18n

    def _register_text(self, setter: Callable[[str], None], key: str) -> None:
        """Set a widget's text from ``key`` now and register it for re-translation.

        ``setter`` is a bound text-setter (e.g. ``action.setText``,
        ``menu.setTitle``, ``button.setText``). The pair is remembered so
        retranslate_ui can re-apply the active language's text when the user
        switches language (FR-123).

        Satisfies: FR-121, FR-123.
        """
        self._i18n_registry.append((setter, key))
        setter(tr(key))

    def retranslate_ui(self) -> None:
        """Re-apply the active language to every persistent UI element (live).

        Re-runs every registered text-setter, refreshes the connection
        indicators (whose text combines a bullet with a translated name), and
        cascades to the Terminal Window if it has been created. On-demand
        dialogs and context menus are not registered here: they read the active
        language via tr() each time they are built, so they are always current.

        Satisfies: FR-123.
        """
        for setter, key in self._i18n_registry:
            setter(tr(key))
        # FR-123: the sort drop-down item *labels* are translated, but their
        # userData (the SORT_* keys) is not; re-apply the labels by row so the
        # current selection and key are preserved across a language switch.
        for combo in (self.host_sort_combo, self.remote_sort_combo):
            combo.setItemText(0, tr("main.sort.name"))
            combo.setItemText(1, tr("main.sort.extension"))
        self._update_indicators()
        # FR-125/FR-126: composite titles (combining translated text with a
        # filename/path) are re-applied here rather than via the registry, like
        # the connection indicators above.
        self._update_window_title()
        self._update_host_group_title()
        if self.terminal_win is not None:
            self.terminal_win.retranslate_ui()
        if self.macro_win is not None:
            self.macro_win.retranslate_ui()

    def _update_window_title(self) -> None:
        """Set the main window title, appending the loaded config's name.

        The title bar shows the application name; when a configuration file is
        loaded it is followed by that file's base name (no directory, no
        extension). Re-resolves the active language each call so it stays
        correct across language switches (FR-123).

        Satisfies: FR-125, UIR-005.
        """
        base = tr("app.title")
        if self._config_name:
            self.setWindowTitle(tr("app.title_with_config", app=base, config=self._config_name))
        else:
            self.setWindowTitle(base)

    def _update_host_group_title(self) -> None:
        """Set the Host Files group title to include the current host directory.

        The directory is appended after the translated "Host Files" label. When
        the directory text is wider than the space available in the group box,
        its leading portion is elided (``…\\tail``) so the trailing, most
        specific part of the path stays visible. Recomputed on resize
        (``resizeEvent``) and on language change (``retranslate_ui``).

        Safe to call before the group box exists (during early construction) —
        it simply does nothing.

        Satisfies: FR-126, UIR-011.
        """
        group = getattr(self, "host_group", None)
        if group is None:
            return
        label = tr("main.host_files")
        metrics = QFontMetrics(group.font())
        # Width consumed by the fixed prefix ("Host Files — ") plus a margin for
        # the group-box frame and title indent, leaving the rest for the path.
        prefix = tr("main.host_files_dir", label=label, dir="")
        avail = group.width() - metrics.horizontalAdvance(prefix) - 24
        elided = metrics.elidedText(self.host_dir, Qt.TextElideMode.ElideLeft, max(0, avail))
        group.setTitle(tr("main.host_files_dir", label=label, dir=elided))

    # ------------------------------------------------------------------ setup

    def _connect_signals(self):
        """
        Satisfies: NFR-004.

        All ``Signal()`` declarations are class-level, so every ``MainWindow``
        instance shares the underlying signal object.  Without this precaution,
        test sessions that create multiple ``MainWindow`` instances accumulate
        orphaned handlers — old ``self`` still receives emits from new ones.
        The _disconnect_signals() helper runs in closeEvent to prevent this leak.
        """
        self.status_changed.connect(self._on_status_changed)
        self.term_write.connect(self._on_term_write)
        self.remote_files_ready.connect(self._update_remote_list_ui)
        self.error_raised.connect(self._on_error_raised)
        self.transfer_completed.connect(self._on_transfer_completed)
        self.batch_started.connect(self._on_batch_started)
        self.transfer_file_started.connect(self._on_transfer_file_started)
        self.transfer_progress.connect(self._on_transfer_progress)
        self.drive_not_found.connect(self._on_drive_not_found)
        self.connect_probe_ok.connect(self._on_connect_probe_ok)
        self.connect_probe_failed.connect(self._on_connect_probe_failed)
        self.view_file_ready.connect(self._on_view_file_ready)
        self.transfer_cancelled.connect(self._on_transfer_cancelled)
        self.conflict_detected.connect(self._on_conflict_detected)
        self.invalid_name_detected.connect(self._on_invalid_name_detected)
        self.backup_restore_confirm.connect(self._on_backup_restore_confirm)

    def _disconnect_signals(self):
        """Remove all handlers connected in ``_connect_signals``.

        This prevents orphaned slots on class-level signals from running when a
        subsequent ``MainWindow`` instance emits those signals (test ordering
        failures, ghost UI updates).  Call this before the window is destroyed
        — currently done from ``closeEvent`` — so that no dead ``self``
        survives on a signal's sender list.

        Satisfies: NFR-004.
        """
        pairs = (
            (self.status_changed, self._on_status_changed),
            (self.term_write, self._on_term_write),
            (self.remote_files_ready, self._update_remote_list_ui),
            (self.error_raised, self._on_error_raised),
            (self.transfer_completed, self._on_transfer_completed),
            (self.batch_started, self._on_batch_started),
            (self.transfer_file_started, self._on_transfer_file_started),
            (self.transfer_progress, self._on_transfer_progress),
            (self.drive_not_found, self._on_drive_not_found),
            (self.connect_probe_ok, self._on_connect_probe_ok),
            (self.connect_probe_failed, self._on_connect_probe_failed),
            (self.view_file_ready, self._on_view_file_ready),
            (self.transfer_cancelled, self._on_transfer_cancelled),
            (self.conflict_detected, self._on_conflict_detected),
            (self.invalid_name_detected, self._on_invalid_name_detected),
            (self.backup_restore_confirm, self._on_backup_restore_confirm),
        )
        for sig, slot in pairs:
            try:
                sig.disconnect(slot)
            except RuntimeError:
                # Slot was never connected to this signal instance (e.g. during
                # early teardown or in tests that skip _connect_signals).
                pass

    def setup_menu(self):
        """
        Satisfies: UIR-001, UIR-002, UIR-003, UIR-004, FR-018, FR-019, FR-022, FR-122.
        """
        menubar = self.menuBar()

        file_menu = menubar.addMenu("")
        self._register_text(file_menu.setTitle, "menu.file")
        self._add_menu_action(file_menu, "menu.file.new", self.menu_new)
        self._add_menu_action(file_menu, "menu.file.load", self.menu_load)
        self._add_menu_action(file_menu, "menu.file.save", self.menu_save)
        file_menu.addSeparator()
        self._add_menu_action(file_menu, "menu.file.exit", self.close)

        config_menu = menubar.addMenu("")
        self._register_text(config_menu.setTitle, "menu.config")
        self._add_menu_action(config_menu, "menu.config.serial", self.menu_serial_config)
        self._add_menu_action(config_menu, "menu.config.general", self.menu_general_config)
        self._add_menu_action(config_menu, "menu.config.macros", self.menu_macro_config)
        self._setup_language_menu(config_menu)

        # UIR-004: Help menu with Manual (FR-023) and About (FR-022) items.
        help_menu = menubar.addMenu("")
        self._register_text(help_menu.setTitle, "menu.help")
        self._add_menu_action(help_menu, "menu.help.manual", self.menu_manual)
        help_menu.addSeparator()
        self._add_menu_action(help_menu, "menu.help.about", self.menu_about)

    def _add_menu_action(self, menu, key: str, handler) -> QAction:
        """Create a menu QAction whose text follows the active language.

        Satisfies: FR-121, FR-123.
        """
        action = QAction("", self)
        action.triggered.connect(handler)
        self._register_text(action.setText, key)
        menu.addAction(action)
        return action

    def _setup_language_menu(self, config_menu) -> None:
        """Build the Config > Language submenu (UIR-077).

        One checkable, mutually-exclusive entry per available language
        (FR-122), displayed by its language name (which is itself not
        translated). The entry for the active language is checked.

        Satisfies: FR-122, UIR-003, UIR-077.
        """
        language_menu = config_menu.addMenu("")
        self._register_text(language_menu.setTitle, "menu.config.language")
        self._language_group = QActionGroup(self)
        self._language_group.setExclusive(True)
        self._language_actions: dict[str, QAction] = {}
        active = current_language()
        for name in available_languages():
            # The language name is the menu label and is deliberately NOT
            # translated (UIR-077); it identifies the language to a speaker of
            # that language.
            action = QAction(display_name(name), self, checkable=True)
            action.setChecked(name == active)
            action.triggered.connect(lambda _checked=False, n=name: self.menu_set_language(n))
            self._language_group.addAction(action)
            language_menu.addAction(action)
            self._language_actions[name] = action

    def menu_set_language(self, name: str) -> None:
        """Switch the active GUI language, persist it, and re-translate live.

        Satisfies: FR-122, FR-123, FR-124.
        """
        set_language(name)
        self.window_state.language = name
        # Keep the checked entry in step (also corrects the state if the change
        # was triggered programmatically rather than by the user).
        action = self._language_actions.get(name)
        if action is not None:
            action.setChecked(True)
        self.retranslate_ui()

    def setup_toolbar(self):
        """
        Satisfies: UIR-013, UIR-015, UIR-016, UIR-071, UIR-082, UIR-086, UIR-087.

        The main-window actions are presented as a top toolbar. All toolbar
        buttons are enabled by default (Connect/Disconnect at startup).
        """
        toolbar = QToolBar("Actions")
        toolbar.setToolButtonStyle(toolbar.toolButtonStyle().ToolButtonTextBesideIcon)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        sp = self.style().standardIcon
        Pix = QStyle.StandardPixmap
        actions = [
            ("toolbar.connect", Pix.SP_DialogApplyButton, self.do_connect),
            ("toolbar.disconnect", Pix.SP_DialogCancelButton, self.do_disconnect),
            ("toolbar.terminal", Pix.SP_ComputerIcon, self.show_terminal),
            # UIR-082: opens the Transfer History dialog (Feature 2).
            ("toolbar.history", Pix.SP_FileDialogDetailedView, self.show_history),
            # UIR-086/UIR-087: whole-drive Backup (remote→host) and Restore
            # (host→remote). The arrows match the panes' left/right layout: the
            # Host pane is on the left and the Remote pane on the right, so
            # Backup points left (remote→host) and Restore points right (host→remote).
            ("toolbar.backup", Pix.SP_ArrowLeft, self.do_backup),
            ("toolbar.restore", Pix.SP_ArrowRight, self.do_restore),
        ]
        for key, pixmap, handler in actions:
            action = QAction(sp(pixmap), "", self, triggered=handler)
            self._register_text(action.setText, key)
            toolbar.addAction(action)

    def setup_layout(self):
        """
        Satisfies: FR-061, FR-070, FR-071, FR-072, UIR-011, UIR-012, UIR-017, UIR-072.

        Host and Remote panes separated by a user-draggable splitter.
        The Host "Change Directory" and both "Update" buttons are enabled at
        startup (FR-061, FR-072); the Remote Files list is empty at startup
        (FR-070); the Remote "Update" button is enabled at startup (FR-071).
        """
        splitter = QSplitter()

        # Left Side: Host Files
        # FR-126: kept as an attribute so the title can be updated to include
        # the current host directory (set via _update_host_group_title).
        host_group = QGroupBox()
        self.host_group = host_group
        self._update_host_group_title()
        host_layout = QVBoxLayout(host_group)

        # UIR-011: a top row with the "Change Directory" and "Update" (refresh
        # the Host Files list only, FR-063) buttons sized equally (stretch
        # factor 1 each).
        host_top = QHBoxLayout()
        change_dir_btn = QPushButton(clicked=self.change_host_dir)
        self._register_text(change_dir_btn.setText, "main.change_directory")
        host_top.addWidget(change_dir_btn, 1)
        refresh_btn = QPushButton(clicked=self.refresh_host_files)
        self._register_text(refresh_btn.setText, "main.update")
        host_top.addWidget(refresh_btn, 1)
        host_layout.addLayout(host_top)

        # UIR-079/UIR-080: filter field + sort controls above the Host list.
        host_fs, self.host_filter, self.host_sort_combo, self.host_sort_dir_btn = (
            self._build_filter_sort_row("host")
        )
        host_layout.addLayout(host_fs)

        # FR-136/FR-137: a drag-and-drop-capable multi-select list (the
        # ExtendedSelection mode is set by FileListWidget). Dropping remote files
        # here downloads them to the host (handled by _on_files_dropped).
        self.host_list = FileListWidget("host", self._on_files_dropped)
        # UIR-018: right-click context menu (View/Edit, Rename, Delete) on host files.
        self.host_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.host_list.customContextMenuRequested.connect(self._host_context_menu)
        host_layout.addWidget(self.host_list)

        # Host buttons row
        host_btns = QHBoxLayout()
        copy_remote_btn = QPushButton(clicked=self.do_copy_to_remote)
        self._register_text(copy_remote_btn.setText, "main.copy_to_remote")
        host_btns.addWidget(copy_remote_btn)
        host_layout.addLayout(host_btns)

        splitter.addWidget(host_group)

        # Right Side: Remote Files
        remote_group = QGroupBox()
        self._register_text(remote_group.setTitle, "main.remote_files")
        remote_layout = QVBoxLayout(remote_group)

        # UIR-012/UIR-017: a drive-selection drop-down (A:–P:) followed by the
        # Update button, sized equally (stretch factor 1 each). `activated` fires
        # only on a user selection, never on programmatic changes, so it cannot
        # trigger a drive change spuriously.
        remote_top = QHBoxLayout()
        self.drive_combo = QComboBox()
        self.drive_combo.addItems([f"{chr(c)}:" for c in range(ord("A"), ord("P") + 1)])
        # Widen the drop-down so the selected drive (e.g. "B:") is never clipped.
        self.drive_combo.setMinimumContentsLength(4)
        self.drive_combo.setMinimumWidth(80)
        self.drive_combo.activated.connect(self.change_drive)
        remote_top.addWidget(self.drive_combo, 1)
        update_btn = QPushButton(clicked=self.do_refresh_remote_files)
        self._register_text(update_btn.setText, "main.update")
        remote_top.addWidget(update_btn, 1)
        remote_layout.addLayout(remote_top)

        # UIR-079/UIR-080: filter field + sort controls above the Remote list.
        remote_fs, self.remote_filter, self.remote_sort_combo, self.remote_sort_dir_btn = (
            self._build_filter_sort_row("remote")
        )
        remote_layout.addLayout(remote_fs)

        # FR-136/FR-137/FR-138: a drag-and-drop-capable multi-select list.
        # Dropping host files (or external OS files) here uploads them to the
        # remote CP/M system (handled by _on_files_dropped).
        self.remote_list = FileListWidget("remote", self._on_files_dropped)
        # UIR-019: right-click context menu (View, Rename, Delete) on remote files.
        self.remote_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.remote_list.customContextMenuRequested.connect(self._remote_context_menu)
        remote_layout.addWidget(self.remote_list)

        # Remote buttons row
        remote_btns = QHBoxLayout()
        copy_host_btn = QPushButton(clicked=self.do_copy_to_host)
        self._register_text(copy_host_btn.setText, "main.copy_to_host")
        remote_btns.addWidget(copy_host_btn)
        remote_layout.addLayout(remote_btns)

        splitter.addWidget(remote_group)

        splitter.setSizes([450, 450])
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.addWidget(splitter)
        self.setCentralWidget(container)

    def setup_status_bar(self):
        """
        Satisfies: UIR-010, UIR-074.

        Single-line status bar; connection indicators.
        """
        self.term_indicator = self._make_indicator("indicator.terminal")
        self.trans_indicator = self._make_indicator("indicator.transport")
        self.statusBar().addPermanentWidget(self.term_indicator)
        self.statusBar().addPermanentWidget(self.trans_indicator)
        self._update_indicators()
        self.set_status(tr("status.ready"))

    @staticmethod
    def _make_indicator(key: str):
        """
        Satisfies: UIR-074, FR-121.

        The translation key (not the display text) is stored on the label, so
        _update_indicators can re-resolve the name in the active language.
        """
        from PySide6.QtWidgets import QLabel

        label = QLabel()
        label.setProperty("indicator_key", key)
        return label

    def _update_indicators(self):
        """
        Satisfies: UIR-074, FR-123.

        Distinct visual state for connected vs not-connected: green (#4caf50)
        when connected, red (#f44336) when not connected. The indicator name is
        resolved from its translation key each call, so it follows the active
        language after a live re-translation.
        """
        for label, connected in (
            (self.term_indicator, self.serial_mgr.terminal_connected),
            (self.trans_indicator, self.serial_mgr.transport_connected),
        ):
            name = tr(label.property("indicator_key"))
            color = "#4caf50" if connected else "#f44336"
            label.setText(f"● {name}")
            label.setStyleSheet(f"color: {color};")

    # ----------------------------------------------------------------- status

    def set_status(self, text: str):
        """
        Satisfies: UIR-014.

        Truncate to 127 characters. Emitting (rather than setting
        directly) makes set_status safe to call from any thread (NFR-004).
        """
        self.status_changed.emit(text[:127])

    def _on_status_changed(self, text: str):
        """
        Satisfies: UIR-010.
        """
        self.statusBar().showMessage(text)

    def _on_term_write(self, data: bytes):
        """
        Satisfies: FR-086, FR-091, FR-093.

        Single GUI-thread sink for all terminal-screen writes: incoming serial
        data, local echo (FR-093), and transfer byte echo (FR-086). Feeds the
        raw bytes into the VT-100 engine here (on the GUI thread, so the engine
        is single-threaded) and repaints the receive view when the Terminal
        Window is open. It never touches the receive/transmit data buffers, so
        local-echo/hex text stays out of them (FR-090).
        """
        self._term_engine.feed(data)
        if self.terminal_win:
            self.terminal_win.render_screen()

    def _on_error_raised(self, title: str, message: str):
        """
        Satisfies: FR-105.

        FR-105: a failed transfer closes the progress dialog before the error
        dialog is shown.
        """
        self._close_transfer_dialog()
        QMessageBox.critical(self, title, message)

    def _on_transfer_completed(self, direction: str):
        """
        Satisfies: FR-099.

        Runs on the GUI thread (queued from the transfer worker). After a
        successful transfer the destination list is otherwise stale until the
        user manually refreshes it, so refresh the affected pane here.
        FR-105: close the progress dialog now the transfer has completed.
        """
        self._close_transfer_dialog()
        if direction == "host":
            self.refresh_host_files()
        elif direction == "remote":
            self.refresh_remote_files()

    def _on_batch_started(self, direction: str, file_count: int):
        """
        Satisfies: FR-105, FR-106.

        Runs on the GUI thread (queued from the transfer
        worker). Build and show the single modal progress dialog that serves
        the whole batch. transfer_file_started then switches it to each file.
        """
        self._close_transfer_dialog()  # defensive: never leak a prior dialog
        # FR-120: the dialog's Cancel button requests cancellation of the batch.
        self._transfer_dialog = TransferProgressDialog(
            self, direction, file_count, cancel_callback=self._request_transfer_cancel
        )
        self._transfer_dialog.show()

    def _on_transfer_file_started(self, filename: str, total_bytes: int, file_index: int):
        """
        Satisfies: FR-105, FR-107.

        Runs on the GUI thread (queued from the transfer
        worker). Switch the existing batch dialog to the file at 1-based
        position file_index. total_bytes is the file size for sends, or 0 for
        receives (length is unknown -> indeterminate).
        """
        if self._transfer_dialog is not None:
            self._transfer_dialog.set_file(filename, total_bytes or None, file_index)

    def _on_transfer_progress(self, blocks: int, bytes_done: int):
        """
        Satisfies: FR-105.

        Runs on the GUI thread (queued per transferred block).
        """
        if self._transfer_dialog is not None:
            self._transfer_dialog.update_progress(blocks, bytes_done)

    def _close_transfer_dialog(self):
        """
        Satisfies: FR-105.

        Tear down the progress dialog on the GUI thread, if present.
        """
        if self._transfer_dialog is not None:
            self._transfer_dialog.close()
            self._transfer_dialog.deleteLater()
            self._transfer_dialog = None

    def _request_transfer_cancel(self):
        """
        Satisfies: FR-120.

        GUI-thread Cancel handler: raise the thread-safe cancel flag the
        transfer worker polls, and reflect the request in the status bar. The
        dialog button is disabled by the dialog itself; the worker tears the
        dialog down once it has aborted (transfer_cancelled).
        """
        self._transfer_cancel.set()
        self.set_status(tr("status.cancelling_transfer"))

    def _on_transfer_cancelled(self, direction: str, any_succeeded: bool):
        """
        Satisfies: FR-120.

        Runs on the GUI thread (queued from the transfer worker). Close the
        progress dialog and, if any file completed before the cancellation,
        refresh the destination list (FR-099).
        """
        self._close_transfer_dialog()
        if any_succeeded:
            if direction == "host":
                self.refresh_host_files()
            elif direction == "remote":
                self.refresh_remote_files()

    # -------------------------------------------------------------- viewer

    def _open_in_viewer(self, path):
        """
        Satisfies: FR-112.

        Open ``path`` in the configured viewer/editor (`viewer_cmd`, $1 = path).
        When `viewer_cmd` is empty, fall back to the host OS default file
        association.
        """
        template = self.settings.get("viewer_cmd", "notepad $1")
        try:
            if template and template.strip():
                subprocess.Popen(build_viewer_args(template, path))
            else:
                self._os_open(path)
        except Exception as e:  # pragma: no cover - depends on host environment
            QMessageBox.critical(
                self, tr("dialog.error.title"), tr("error.unable_open_viewer", error=e)
            )

    @staticmethod
    def _os_open(path):
        """
        Satisfies: FR-112.

        Open a file with the host operating system's default association.
        """
        startfile = getattr(os, "startfile", None)
        if startfile is not None:  # Windows
            startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])

    # ------------------------------------------------------------- dialogs

    def _confirm_dialog(
        self,
        title: str,
        message: str,
        accept_label: str,
        *,
        warning: bool = False,
        default_accept: bool = True,
    ) -> bool:
        """Modal Cancel/<accept> confirmation honouring the house button order.

        A custom QDialog (not QMessageBox) is used so the buttons obey the house
        convention — Cancel at the far left, the affirmative button at the far
        right (UIR-075). QMessageBox orders its buttons by the native platform
        style and would not honour that. Returns True when the user chose the
        affirmative button (False on Cancel or a window-manager close).

        Satisfies: UIR-075.
        """
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.setModal(True)
        dlg_layout = QVBoxLayout(dlg)

        msg_row = QHBoxLayout()
        if warning:
            # Warning icon beside the message text, mirroring QMessageBox.Warning.
            icon_label = QLabel()
            icon = self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxWarning)
            icon_label.setPixmap(icon.pixmap(48, 48))
            icon_label.setAlignment(Qt.AlignmentFlag.AlignTop)
            msg_row.addWidget(icon_label)
        text_label = QLabel(message)
        text_label.setWordWrap(True)
        msg_row.addWidget(text_label, 1)
        dlg_layout.addLayout(msg_row)

        accept_btn = QPushButton(accept_label)
        accept_btn.clicked.connect(dlg.accept)
        cancel_btn = QPushButton(tr("button.cancel"))
        cancel_btn.clicked.connect(dlg.reject)
        (accept_btn if default_accept else cancel_btn).setDefault(True)
        dlg_layout.addLayout(build_button_row(accept_button=accept_btn, reject_button=cancel_btn))

        return dlg.exec() == QDialog.DialogCode.Accepted

    # ------------------------------------------------------------------- exit

    def resizeEvent(self, event):
        """Re-elide the Host Files directory title to the new window width.

        The directory shown in the group title (FR-126) is left-elided to fit
        the available width, so it must be recomputed whenever the window — and
        thus the group box — is resized.

        Satisfies: FR-126.
        """
        super().resizeEvent(event)
        self._update_host_group_title()

    def closeEvent(self, event):
        """
        Satisfies: FR-004, FR-015, FR-016.

        FR-004: persist window geometry on exit. The Terminal Window persists
        in the background when the user closes it (it hides rather than
        destroys), so it still exists here and its current geometry is saved.
        """
        self._disconnect_signals()  # prevent orphaned slot accumulation (NFR-004)
        self.window_state.save_geometry("main", self)
        if self.terminal_win:
            self.window_state.save_geometry("terminal", self.terminal_win)
        # FR-164: persist the Macro Window geometry alongside the Terminal Window.
        if self.macro_win:
            self.window_state.save_geometry("macro", self.macro_win)
        # FR-015: close any open COM ports. FR-016: close all open windows.
        self.serial_mgr.close_ports()
        if self.terminal_win:
            self.terminal_win.close()
        if self.macro_win:
            self.macro_win.close()
        event.accept()


def main() -> None:
    """
    Satisfies: STR-002, CR-002, CR-012, CR-013, UIR-078.
    """
    app = cast(QApplication, QApplication.instance() or QApplication(sys.argv))
    # FR-004/FR-005: identity for QSettings-backed persistence (see WindowState).
    app.setOrganizationName(ORG)
    app.setApplicationName(APP)
    # UIR-078: set the branded application icon once, centrally (like the theme),
    # so every window/dialog and the OS taskbar/dock entry inherit it.
    app.setWindowIcon(app_icon())
    apply_theme(app)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
