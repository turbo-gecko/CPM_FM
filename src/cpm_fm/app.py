from __future__ import annotations

import copy
import os
import shlex
import subprocess
import sys
import tempfile
import threading
import time
from typing import Callable, cast

import serial.tools.list_ports
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QFontMetrics
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStyle,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from cpm_fm.gui.about_dialog import AboutDialog
from cpm_fm.gui.config_dialogs import GeneralConfigDialog, SerialConfigDialog
from cpm_fm.gui.conflict_dialog import CANCEL, SKIP, FileConflictDialog
from cpm_fm.gui.file_action_dialog import FileActionDialog
from cpm_fm.gui.file_list_widget import FileListWidget
from cpm_fm.gui.filename_validation_dialog import FilenameValidationDialog
from cpm_fm.gui.terminal_window import TerminalWindow
from cpm_fm.gui.theme import app_icon, apply_theme
from cpm_fm.gui.transfer_dialog import TransferProgressDialog
from cpm_fm.gui.transfer_history_dialog import TransferHistoryDialog
from cpm_fm.gui.window_state import APP, ORG, WindowState
from cpm_fm.terminal.cpm_parser import CPMParser
from cpm_fm.terminal.serial_manager import SerialManager
from cpm_fm.terminal.xmodem import XModem
from cpm_fm.utils.config_handler import DEFAULT_SETTINGS, ConfigHandler
from cpm_fm.utils.file_filter import SORT_EXTENSION, SORT_NAME, filter_and_sort
from cpm_fm.utils.i18n import (
    available_languages,
    current_language,
    display_name,
    set_language,
    tr,
)
from cpm_fm.utils.transfer_history import TransferHistory

EOL_MAP = {"CR": "\r", "LF": "\n", "CRLF": "\r\n"}


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


class MainWindow(QMainWindow):
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
    term_write = Signal(str)
    remote_files_ready = Signal(dict)
    error_raised = Signal(str, str)
    # Emitted from a transfer worker thread on success so the destination file
    # list is refreshed on the GUI thread ("host" or "remote").
    transfer_completed = Signal(str)
    # FR-105/FR-106: emitted from the transfer worker thread to drive the single
    # modal transfer-progress dialog on the GUI thread (NFR-004). batch_started
    # carries (direction, file_count) and builds the dialog once for the whole
    # batch; transfer_file_started carries (filename, total_bytes, file_index)
    # and switches the dialog to the next file; transfer_progress carries
    # (blocks, bytes_done) and fires once per transferred block.
    batch_started = Signal(str, int)
    transfer_file_started = Signal(str, int, int)
    transfer_progress = Signal(int, int)
    # FR-103: emitted (with the selected drive letter) from the drive-change
    # worker thread when the drive's prompt does not appear, so the "Drive not
    # found" dialog and the list-clear run on the GUI thread (NFR-004).
    drive_not_found = Signal(str)
    # FR-113: emitted (with the downloaded temp-file path) from the remote-view
    # worker thread once the file has been received, so the viewer is launched
    # on the GUI thread (NFR-004).
    view_file_ready = Signal(str)
    # FR-120: emitted from a transfer worker thread when the batch is cancelled,
    # carrying (direction, any_succeeded), so the dialog teardown and any
    # destination-list refresh run on the GUI thread (NFR-004).
    transfer_cancelled = Signal(str, bool)
    # FR-146: emitted from a transfer worker thread when a destination file
    # already exists, carrying (filename, direction), so the modal conflict
    # dialog runs on the GUI thread (NFR-004). The worker blocks on
    # _conflict_answered until the GUI thread records the user's choice.
    conflict_detected = Signal(str, str)
    # FR-148/FR-149: emitted from the upload worker thread when a file's name
    # does not meet the CP/M 8.3 convention, carrying (filename), so the modal
    # rename/skip/cancel dialog runs on the GUI thread (NFR-004). The worker
    # blocks on _invalid_name_answered until the GUI thread records the choice.
    invalid_name_detected = Signal(str)
    # FR-152: emitted from a Backup/Restore worker thread, carrying the
    # operation ("backup" or "restore"), so the destructive-operation
    # confirmation dialog runs on the GUI thread (NFR-004). The worker blocks on
    # _backup_confirm_answered until the GUI thread records the user's choice.
    backup_restore_confirm = Signal(str)

    def __init__(
        self,
        window_state: WindowState | None = None,
        transfer_history: TransferHistory | None = None,
    ):
        """
        Satisfies: FR-003, FR-004, FR-005, FR-124, FR-141.
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
        self.view_file_ready.connect(self._on_view_file_ready)
        self.transfer_cancelled.connect(self._on_transfer_cancelled)
        self.conflict_detected.connect(self._on_conflict_detected)
        self.invalid_name_detected.connect(self._on_invalid_name_detected)
        self.backup_restore_confirm.connect(self._on_backup_restore_confirm)

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
        self._setup_language_menu(config_menu)

        # UIR-004: Help menu with an About item (FR-022).
        help_menu = menubar.addMenu("")
        self._register_text(help_menu.setTitle, "menu.help")
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
        Satisfies: UIR-013, UIR-071, UIR-082, UIR-086, UIR-087.

        The main-window actions are presented as a top toolbar.
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
        Satisfies: UIR-011, UIR-012, UIR-017, UIR-072.

        Host and Remote panes separated by a user-draggable splitter.
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
        # both lists, FR-063) buttons sized equally (stretch factor 1 each).
        host_top = QHBoxLayout()
        change_dir_btn = QPushButton(clicked=self.change_host_dir)
        self._register_text(change_dir_btn.setText, "main.change_directory")
        host_top.addWidget(change_dir_btn, 1)
        refresh_btn = QPushButton(clicked=self.refresh_all)
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
        update_btn = QPushButton(clicked=self.refresh_remote_files)
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

    # ------------------------------------------------- file-list filter / sort

    def _build_filter_sort_row(self, pane: str):
        """Build the filter field and sort controls for one file pane.

        Returns ``(layout, filter_edit, sort_combo, dir_btn)``. ``pane`` is
        "host" or "remote" and selects which view-apply slot the controls drive.
        The filter field carries a built-in clear (X) button (FR-135) and its
        input is debounced ~150 ms so a render is not run on every keystroke
        (FR-131). The sort drop-down offers Name/Extension (FR-132, userData =
        the SORT_* key) and the checkable direction button toggles
        ascending/descending.

        Satisfies: FR-130, FR-132, FR-135, UIR-079, UIR-080.
        """
        row = QHBoxLayout()

        filter_edit = QLineEdit()
        filter_edit.setClearButtonEnabled(True)  # FR-135: clear (X) button.
        self._register_text(filter_edit.setPlaceholderText, "main.filter_placeholder")
        self._register_text(filter_edit.setToolTip, "main.filter_tooltip")
        row.addWidget(filter_edit, 1)

        sort_combo = QComboBox()
        sort_combo.addItem(tr("main.sort.name"), SORT_NAME)
        sort_combo.addItem(tr("main.sort.extension"), SORT_EXTENSION)
        self._register_text(sort_combo.setToolTip, "main.sort_by_tooltip")
        row.addWidget(sort_combo)

        dir_btn = QToolButton()
        dir_btn.setCheckable(True)
        dir_btn.setText("↑")  # ascending; flipped to ↓ when checked.
        self._register_text(dir_btn.setToolTip, "main.sort_direction_tooltip")
        row.addWidget(dir_btn)

        apply_fn = self._apply_host_view if pane == "host" else self._apply_remote_view

        # FR-131: debounce filter typing so the list re-renders ~150 ms after the
        # user pauses, not on every character.
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.setInterval(150)
        timer.timeout.connect(apply_fn)
        filter_edit.textChanged.connect(lambda _text, tm=timer: tm.start())
        # FR-132: a sort change re-renders immediately (no debounce needed).
        sort_combo.currentIndexChanged.connect(apply_fn)
        dir_btn.toggled.connect(lambda checked, b=dir_btn: self._update_sort_arrow(b, checked))
        dir_btn.toggled.connect(apply_fn)

        return row, filter_edit, sort_combo, dir_btn

    @staticmethod
    def _update_sort_arrow(button, checked: bool) -> None:
        """Show ``↓`` for descending, ``↑`` for ascending (UIR-080).

        The arrow glyph is a directional indicator, not translatable prose, so
        it is set directly (CR-015).

        Satisfies: UIR-080.
        """
        button.setText("↓" if checked else "↑")

    def _render_file_list(self, list_widget, names, filter_edit, sort_combo, dir_btn) -> None:
        """Filter+sort ``names`` per the pane's controls and show them.

        Applies the shared filter_and_sort logic (FR-133) and flags an active
        (non-empty) filter with a coloured border on the field (UIR-079).

        Satisfies: FR-130, FR-131, FR-132, FR-133, UIR-079.
        """
        pattern = filter_edit.text()
        key = sort_combo.currentData() or SORT_NAME
        descending = dir_btn.isChecked()
        visible = filter_and_sort(names, pattern, key=key, descending=descending)
        list_widget.clear()
        list_widget.addItems(visible)
        # UIR-079: a coloured border marks an active filter so it is obvious why
        # files may be hidden.
        active = bool(pattern.strip())
        filter_edit.setStyleSheet("QLineEdit { border: 1px solid #4caf50; }" if active else "")

    def _apply_host_view(self) -> None:
        """Re-render the Host list from the current filter/sort controls (FR-133).

        Satisfies: FR-133, FR-134.
        """
        self._render_file_list(
            self.host_list,
            self._host_files,
            self.host_filter,
            self.host_sort_combo,
            self.host_sort_dir_btn,
        )
        self._persist_filter_sort()

    def _apply_remote_view(self) -> None:
        """Re-render the Remote list from the current filter/sort controls (FR-133).

        Satisfies: FR-133, FR-134.
        """
        self._render_file_list(
            self.remote_list,
            self._remote_files,
            self.remote_filter,
            self.remote_sort_combo,
            self.remote_sort_dir_btn,
        )
        self._persist_filter_sort()

    def _clear_remote_files(self) -> None:
        """Empty both the canonical Remote file list and the visible widget.

        Used wherever a stale remote listing must be discarded (load, disconnect,
        drive-not-found, terminal closed, File > New) so the filter/sort source
        does not retain entries that are no longer valid.

        Satisfies: FR-017, FR-058, FR-074, FR-103, FR-104.
        """
        self._remote_files = []
        self.remote_list.clear()

    def _persist_filter_sort(self) -> None:
        """Persist both panes' filter text and sort settings (FR-134).

        A no-op while restoring (so the restore does not overwrite itself).

        Satisfies: FR-134.
        """
        if self._restoring_filter_sort:
            return
        ws = self.window_state
        ws.set_filter_text("host", self.host_filter.text())
        ws.set_sort_key("host", self.host_sort_combo.currentData() or SORT_NAME)
        ws.set_sort_descending("host", self.host_sort_dir_btn.isChecked())
        ws.set_filter_text("remote", self.remote_filter.text())
        ws.set_sort_key("remote", self.remote_sort_combo.currentData() or SORT_NAME)
        ws.set_sort_descending("remote", self.remote_sort_dir_btn.isChecked())

    def _restore_filter_sort(self) -> None:
        """Load each pane's saved filter text and sort settings into its controls.

        Signals are blocked during the restore so it does not trigger a premature
        render or a self-overwriting persist; the first real render happens when
        the lists are next populated.

        Satisfies: FR-134.
        """
        self._restoring_filter_sort = True
        try:
            ws = self.window_state
            panes = (
                ("host", self.host_filter, self.host_sort_combo, self.host_sort_dir_btn),
                ("remote", self.remote_filter, self.remote_sort_combo, self.remote_sort_dir_btn),
            )
            for pane, edit, combo, btn in panes:
                for widget in (edit, combo, btn):
                    widget.blockSignals(True)
                edit.setText(ws.filter_text(pane))
                idx = combo.findData(ws.sort_key(pane))
                combo.setCurrentIndex(idx if idx >= 0 else 0)
                descending = ws.sort_descending(pane)
                btn.setChecked(descending)
                self._update_sort_arrow(btn, descending)
                for widget in (edit, combo, btn):
                    widget.blockSignals(False)
        finally:
            self._restoring_filter_sort = False

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

    def _on_term_write(self, text: str):
        """
        Satisfies: FR-086, FR-091, FR-093.

        Single GUI-thread sink for all receive-area writes: incoming serial
        data, local echo (FR-093), and transfer byte echo (FR-086). It never
        touches the data buffers, so local-echo/hex text stays out of them.
        """
        if self.terminal_win:
            self.terminal_win.write_text(text)

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

    # ------------------------------------------------------------- host files

    def refresh_host_files(self):
        """
        Satisfies: FR-060, FR-126, FR-133.
        """
        # FR-126: the host directory may have changed; reflect it in the group
        # title. This is the single point through which every host-directory
        # change passes.
        self._update_host_group_title()
        try:
            files = [
                f
                for f in os.listdir(self.host_dir)
                if os.path.isfile(os.path.join(self.host_dir, f))
            ]
        except Exception as e:
            self._host_files = []
            self.host_list.clear()
            self.set_status(tr("status.error_reading_host", error=e))
            return
        # FR-133: keep the canonical list and render it through the active
        # filter/sort controls.
        self._host_files = files
        self._apply_host_view()

    def change_host_dir(self):
        """
        Satisfies: FR-062.
        """
        path = QFileDialog.getExistingDirectory(
            self, tr("dialog.change_directory.title"), self.host_dir
        )
        if path:
            self.host_dir = path
            self.refresh_host_files()

    # ------------------------------------------------ file context-menu actions

    def _context_menu_targets(self, list_widget, pos):
        """
        Resolve the file under the cursor and the set of files an action applies
        to for a right-click context menu (FR-110, FR-111).

        Returns ``(name, names)`` where ``name`` is the single file under the
        cursor (the target of the single-file actions) and ``names`` is the list
        of files Delete applies to: the current selection when the clicked file
        is part of it, otherwise just the clicked file. Returns ``(None, [])``
        when the click was not over an item.

        Satisfies: FR-110, FR-111.
        """
        item = list_widget.itemAt(pos)
        if item is None:
            return None, []
        name = item.text()
        names = self._selected_filenames(list_widget)
        if name not in names:
            names = [name]
        return name, names

    def _host_context_menu(self, pos):
        """
        Satisfies: FR-110, FR-119, UIR-018.

        Right-click menu for the Host Files list: To Remote, View/Edit, Rename,
        Delete. To Remote and Delete act on every selected file; View/Edit and
        Rename act on the file under the cursor and are disabled when more than
        one file is selected.
        """
        name, names = self._context_menu_targets(self.host_list, pos)
        if name is None:
            return
        single = len(names) == 1
        menu = QMenu(self)
        menu.addAction(tr("ctxmenu.to_remote"), lambda names=names: self._host_to_remote(names))
        menu.addSeparator()
        menu.addAction(tr("ctxmenu.view_edit"), lambda: self._host_view(name)).setEnabled(single)
        menu.addAction(tr("ctxmenu.rename"), lambda: self._host_rename(name)).setEnabled(single)
        menu.addAction(tr("ctxmenu.delete"), lambda names=names: self._host_delete(names))
        menu.exec(self.host_list.mapToGlobal(pos))

    def _remote_context_menu(self, pos):
        """
        Satisfies: FR-111, FR-119, UIR-019.

        Right-click menu for the Remote Files list: To Host, View, Rename,
        Delete. To Host and Delete act on every selected file; View and Rename
        act on the file under the cursor and are disabled when more than one
        file is selected.
        """
        name, names = self._context_menu_targets(self.remote_list, pos)
        if name is None:
            return
        single = len(names) == 1
        menu = QMenu(self)
        menu.addAction(tr("ctxmenu.to_host"), lambda names=names: self._remote_to_host(names))
        menu.addSeparator()
        menu.addAction(tr("ctxmenu.view"), lambda: self._remote_view(name)).setEnabled(single)
        menu.addAction(tr("ctxmenu.rename"), lambda: self._remote_rename(name)).setEnabled(single)
        menu.addAction(tr("ctxmenu.delete"), lambda names=names: self._remote_delete(names))
        menu.exec(self.remote_list.mapToGlobal(pos))

    def _host_to_remote(self, names):
        """
        Satisfies: FR-119, FR-080, FR-106, FR-107, CR-010.

        Copy every selected host file to the remote, reusing the Copy to Remote
        batch transfer (FR-099/FR-105, sequential per FR-106/FR-107). Accepts a
        single filename or a list of filenames.
        """
        names = [names] if isinstance(names, str) else list(names)
        if not (self.serial_mgr.terminal_connected and self.serial_mgr.transport_connected):
            QMessageBox.critical(
                self, tr("dialog.error.title"), tr("error.transport_not_connected")
            )
            return
        if not names:
            return
        filepaths = [os.path.join(self.host_dir, name) for name in names]
        threading.Thread(
            target=self._transfer_to_remote_batch, args=(filepaths,), daemon=True
        ).start()

    def _remote_to_host(self, names):
        """
        Satisfies: FR-119, FR-080, FR-106, FR-107, CR-010.

        Copy every selected remote file to the host, reusing the Copy to Host
        batch transfer (FR-099/FR-105, sequential per FR-106/FR-107). Accepts a
        single filename or a list of filenames.
        """
        names = [names] if isinstance(names, str) else list(names)
        if not (self.serial_mgr.terminal_connected and self.serial_mgr.transport_connected):
            QMessageBox.critical(
                self, tr("dialog.error.title"), tr("error.transport_not_connected")
            )
            return
        if not names:
            return
        save_paths = [os.path.join(self.host_dir, name) for name in names]
        threading.Thread(
            target=self._transfer_to_host_batch, args=(save_paths,), daemon=True
        ).start()

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

    def _host_view(self, name):
        """
        Satisfies: FR-110, FR-112.
        """
        self._open_in_viewer(os.path.join(self.host_dir, name))

    def _host_rename(self, name):
        """
        Satisfies: FR-110, FR-114, FR-116, FR-118.
        """
        dlg = FileActionDialog(self, tr("dialog.rename_file.title"), name, editable=True)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        new_name = dlg.value().strip()
        if not new_name or new_name == name:
            return
        try:
            os.rename(os.path.join(self.host_dir, name), os.path.join(self.host_dir, new_name))
        except OSError as e:
            QMessageBox.critical(self, tr("dialog.error.title"), tr("error.rename_failed", error=e))
            return
        self.refresh_host_files()

    def _host_delete(self, names):
        """
        Delete every selected host file (FR-110), confirming all of them in one
        modal dialog (FR-115) and refreshing the Host Files list afterwards.
        Files that delete successfully stay deleted even if a later file fails;
        any failures are reported together (FR-116).

        Accepts either a single filename or a list of filenames.

        Satisfies: FR-110, FR-115, FR-116, FR-118.
        """
        names = [names] if isinstance(names, str) else list(names)
        if not names:
            return
        single = len(names) == 1
        prompt = (
            tr("dialog.delete_file.prompt")
            if single
            else tr("dialog.delete_file.prompt_multi", count=len(names))
        )
        dlg = FileActionDialog(
            self,
            tr("dialog.delete_file.title"),
            names[0],
            editable=False,
            prompt=prompt,
            filenames=names,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        errors = []
        for name in names:
            try:
                os.remove(os.path.join(self.host_dir, name))
            except OSError as e:
                errors.append(str(e))
        self.refresh_host_files()
        if errors:
            QMessageBox.critical(
                self, tr("dialog.error.title"), tr("error.delete_failed", error="\n".join(errors))
            )

    def _remote_view(self, name):
        """
        Satisfies: FR-111, FR-113.

        Download the remote file to a temporary folder over X-Modem, then open
        it in the viewer (FR-112). Permitted only when both status flags are
        connected (FR-080/CR-010). Runs the download on a worker thread.
        """
        if not (self.serial_mgr.terminal_connected and self.serial_mgr.transport_connected):
            QMessageBox.critical(
                self, tr("dialog.error.title"), tr("error.transport_not_connected")
            )
            return
        threading.Thread(target=self._download_and_view, args=(name,), daemon=True).start()

    def _download_and_view(self, name):
        """
        Satisfies: FR-113.

        Worker thread: receive ``name`` into a temp folder via the Copy to Host
        transfer process, then request the viewer on the GUI thread via the
        view_file_ready signal (NFR-004). The progress dialog (FR-105) is driven
        by the same batch signals as a normal transfer.
        """
        save_path = os.path.join(tempfile.mkdtemp(prefix="cpm_fm_"), name)
        self._transfer_cancel.clear()  # FR-120: start un-cancelled.
        self.batch_started.emit("host", 1)
        self.set_status(tr("status.downloading_for_viewing", name=name))
        self.transfer_file_started.emit(name, 0, 1)
        try:
            ok = self._recv_one_to_host(save_path)
        except Exception as e:
            self._debug(f"[remote-view] EXCEPTION: {e!r}")
            self.error_raised.emit(tr("dialog.error.title"), str(e))
            return
        if not ok:
            # FR-120: a cancelled download just closes the dialog (no viewer).
            if self._transfer_cancel.is_set():
                self._finish_cancelled_batch("host", 0)
                return
            self.error_raised.emit(
                tr("dialog.xmodem_error.title"), tr("error.download_failed", name=name)
            )
            return
        self.view_file_ready.emit(save_path)

    def _on_view_file_ready(self, path):
        """
        Satisfies: FR-112, FR-113.

        Runs on the GUI thread (queued from the remote-view worker). Close the
        progress dialog and open the downloaded file in the viewer.
        """
        self._close_transfer_dialog()
        self.set_status(tr("status.opening_viewer"))
        self._open_in_viewer(path)

    def _remote_rename(self, name):
        """
        Satisfies: FR-111, FR-114, FR-117, FR-118.
        """
        if not self.serial_mgr.terminal_connected:
            self.set_status(tr("status.terminal_not_open_rename"))
            return
        dlg = FileActionDialog(self, tr("dialog.rename_remote.title"), name, editable=True)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        new_name = dlg.value().strip()
        if not new_name or new_name == name:
            return
        template = self.settings.get("rename_remote_cmd", "REN $2=$1")
        if not template:
            return
        cmd = template.replace("$2", new_name).replace("$1", name)
        threading.Thread(target=self._do_remote_file_cmd, args=(cmd,), daemon=True).start()

    def _remote_delete(self, names):
        """
        Delete every selected remote file (FR-111) by sending the configured
        delete command once per file on the Terminal Port, confirming all of
        them in one modal dialog (FR-115). Accepts a single filename or a list.

        Satisfies: FR-111, FR-115, FR-117, FR-118.
        """
        names = [names] if isinstance(names, str) else list(names)
        if not self.serial_mgr.terminal_connected:
            self.set_status(tr("status.terminal_not_open_delete"))
            return
        if not names:
            return
        single = len(names) == 1
        prompt = (
            tr("dialog.delete_remote.prompt")
            if single
            else tr("dialog.delete_remote.prompt_multi", count=len(names))
        )
        dlg = FileActionDialog(
            self,
            tr("dialog.delete_remote.title"),
            names[0],
            editable=False,
            prompt=prompt,
            filenames=names,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        template = self.settings.get("delete_remote_cmd", "ERA $1")
        if not template:
            return
        cmds = [template.replace("$1", name) for name in names]
        threading.Thread(target=self._do_remote_file_cmds, args=(cmds,), daemon=True).start()

    def _do_remote_file_cmd(self, cmd):
        """
        Satisfies: FR-117, FR-118.

        Worker thread: send a single remote file-management command (Rename).
        Delegates to _do_remote_file_cmds, which sends the command, waits for the
        output to go idle, and refreshes the Remote Files list.
        """
        self._do_remote_file_cmds([cmd])

    def _do_remote_file_cmds(self, cmds):
        """
        Satisfies: FR-117, FR-118.

        Worker thread: send one or more remote file-management commands on the
        Terminal Port in order, waiting for each command's output to go idle
        (reusing the capture mechanism), then refresh the Remote Files list once
        (FR-074-FR-079). _do_refresh_remote_logic marshals its UI update via the
        remote_files_ready signal (NFR-004).
        """
        for cmd in cmds:
            self.set_status(tr("status.executing", cmd=cmd))
            self._capture_terminal_response(cmd)
        self._do_refresh_remote_logic()

    # -------------------------------------------------------------- terminal

    def show_terminal(self):
        """
        Satisfies: FR-097.
        """
        if not self.terminal_win:
            self.terminal_win = TerminalWindow(
                self, self.handle_terminal_send, self.clear_terminal_buffers
            )
            self.terminal_win.chk_echo.toggled.connect(self._set_local_echo)
            # FR-004: restore the Terminal Window's saved geometry on first open.
            self.window_state.restore_geometry("terminal", self.terminal_win)
        else:
            self.terminal_win.showNormal()
        self.terminal_win.show()
        self.terminal_win.raise_()
        self.terminal_win.activateWindow()

    def _set_local_echo(self, enabled: bool):
        """
        Satisfies: FR-093.
        """
        self._local_echo = enabled

    def handle_terminal_send(self, text):
        """
        Satisfies: FR-092, FR-093, FR-094, FR-098.

        May be called from the GUI thread (Send button) or a worker thread
        (the remote-list refresh). Sends data and buffers it directly; the
        local-echo display is marshalled to the GUI thread via term_write.
        """
        if not self.serial_mgr.terminal_connected:
            self.set_status(tr("status.terminal_not_open_send"))
            return

        eol = self.settings.get("eol", "CR")
        eol_char = EOL_MAP.get(eol, "\r")

        # Prevent double-terminators if already appended (e.g. in _do_refresh_remote_logic)
        if not text.endswith(eol_char):
            text += eol_char

        self.serial_mgr.send_data("terminal", text)
        # FR-092: store transmitted data (with EOL) in the transmit buffer.
        self._tx_buffer += text
        # FR-093: local echo copies transmitted data (a byte-for-byte copy,
        # including its EOL) to the receive area only.
        if self._local_echo:
            self.term_write.emit(text)

    def handle_terminal_recv(self, text):
        """
        Satisfies: FR-090, FR-091.

        Runs on the serial read daemon thread. Buffer bookkeeping happens here
        (plain strings, not widgets); the display write is marshalled via the
        term_write signal (NFR-004).
        FR-090: store all received data in the receive buffer.
        """
        self._rx_buffer += text
        if self._capture_active:
            self._remote_capture_buffer += text
        self.term_write.emit(text)

    def clear_terminal_buffers(self):
        """
        Satisfies: FR-095.

        FR-090/FR-092: the Clear button is the explicit-clear trigger for
        both the receive and transmit data buffers.
        """
        self._rx_buffer = ""
        self._tx_buffer = ""

    # ----------------------------------------------------------- connect/disc

    def do_connect(self):
        """
        Satisfies: FR-030, FR-031, FR-032, FR-034, FR-037, FR-038, FR-039, FR-040.
        """
        if self.serial_mgr.open_port("terminal", self.settings):
            self.set_status(tr("status.terminal_port_open"))
            term_port = self.settings.get("terminal_port")
            trans_port = self.settings.get("transport_port")
            if term_port != trans_port:
                if not self.serial_mgr.open_port("transport", self.settings):
                    QMessageBox.critical(
                        self, tr("dialog.error.title"), tr("error.transport_unable_open")
                    )
            else:
                # FR-037: same physical port. Point the Transport Port at the
                # already-open Terminal Port object so transfers have a real
                # port to use (not None) and set the Transport flag.
                self.serial_mgr.transport_port = self.serial_mgr.terminal_port
                self.serial_mgr.transport_connected = True
        else:
            QMessageBox.critical(self, tr("dialog.error.title"), tr("error.terminal_unable_open"))
        self._update_indicators()

    def do_disconnect(self):
        """
        Satisfies: FR-050-FR-058.
        """
        term_port = self.settings.get("terminal_port")
        trans_port = self.settings.get("transport_port")

        # FR-050/FR-051: close the Terminal Port if open; on failure show an
        # error dialog and cancel the current workflow.
        if self.serial_mgr.terminal_connected:
            if not self.serial_mgr.close_terminal_port():
                QMessageBox.critical(
                    self, tr("dialog.error.title"), tr("error.terminal_unable_close")
                )
                self._update_indicators()
                return
            # FR-052 (flag cleared by close_terminal_port) / FR-053 (status text).
            self.set_status(tr("status.terminal_port_closed"))
            # FR-058: the remote listing was read over the now-closed Terminal
            # Port, so it is stale — clear it.
            self._clear_remote_files()

        # FR-054: same physical port — clear the Transport flag, no separate
        # close. Also drop the shared reference so it cannot point at the
        # now-closed Terminal Port object.
        if trans_port == term_port:
            self.serial_mgr.transport_port = None
            self.serial_mgr.transport_connected = False
        # FR-055/FR-056/FR-057: different port — close it if open.
        elif self.serial_mgr.transport_connected:
            if not self.serial_mgr.close_transport_port():
                QMessageBox.critical(
                    self, tr("dialog.error.title"), tr("error.transport_unable_close")
                )
                self._update_indicators()
                return

        self._update_indicators()

    # ----------------------------------------------------------- remote files

    def refresh_all(self):
        """
        Satisfies: FR-063.

        FR-063: the central Refresh button refreshes both lists; the Update
        button (Remote Files group) refreshes the remote list only (FR-073).
        """
        self.refresh_host_files()
        self.refresh_remote_files()

    def refresh_remote_files(self):
        """
        Satisfies: FR-073, FR-074.

        FR-073: populate the Remote Files list for the drive currently shown in
        the drive-selection drop-down (UIR-017). Switch to that drive first (as
        if it had just been selected - FR-100-FR-104) before listing, so the
        displayed files always match the drive next to the Update button even
        when the remote's current drive was changed directly in the Terminal
        Window. Runs the drive-change logic on a worker thread.
        """
        if not self.serial_mgr.terminal_connected:
            self.set_status(tr("status.terminal_not_open_list"))
            self._clear_remote_files()
            return
        drive = self.drive_combo.currentText()[0]  # 'A'..'P'
        threading.Thread(target=self._do_change_drive_logic, args=(drive,), daemon=True).start()

    def _capture_terminal_response(self, command: str) -> str:
        """
        Satisfies: FR-075, FR-076, FR-101.

        Send `command` (with the configured EOL appended) on the Terminal Port
        and capture the echoed output into the capture buffer until it idles
        out, returning the captured text. Runs on a worker thread.
        FR-076: wait at least one second for output to start accumulating,
        then wait for the receive buffer to time out (no new data within the
        idle window) before processing, bounded by a safety maximum.
        """
        self._remote_capture_buffer = ""
        self._capture_active = True
        eol_char = EOL_MAP.get(self.settings.get("eol", "CR"), "\r")
        self.handle_terminal_send(command + eol_char)
        time.sleep(1.0)
        idle_window = 0.5
        max_wait = 10.0
        waited = 1.0
        while waited < max_wait:
            prev_len = len(self._remote_capture_buffer)
            time.sleep(idle_window)
            waited += idle_window
            if len(self._remote_capture_buffer) == prev_len:
                break
        self._capture_active = False
        return self._remote_capture_buffer

    def _do_refresh_remote_logic(self):
        """
        Satisfies: FR-077, FR-078, FR-079.
        """
        self.set_status(tr("status.updating_remote_list"))
        cmd = self.settings.get("list_files_cmd", "DIR")
        text = self._capture_terminal_response(cmd)
        files_dict = CPMParser.parse_dir_output(text)
        self.remote_files_ready.emit(files_dict)

    def change_drive(self, index):
        """
        Satisfies: FR-100, FR-104.

        FR-100/FR-104: switch the remote drive to the selected letter. Mirror
        FR-074 and refuse when the Terminal Port is closed.
        """
        if not self.serial_mgr.terminal_connected:
            self.set_status(tr("status.terminal_not_open_list"))
            self._clear_remote_files()
            return
        drive = self.drive_combo.itemText(index)[0]  # 'A'..'P'
        threading.Thread(target=self._do_change_drive_logic, args=(drive,), daemon=True).start()

    def _do_change_drive_logic(self, drive):
        """
        Satisfies: FR-100, FR-101, FR-102, FR-103.

        FR-100/FR-101: send "<letter>:" and capture the response. FR-102: if
        the new "<letter>>" drive prompt appears, populate the Remote Files
        list exactly as the Update button would (FR-073). FR-103: otherwise
        clear the list and report "Drive not found". Runs on a worker thread,
        so calling _do_refresh_remote_logic directly is correct (it marshals
        its UI update via the remote_files_ready signal).
        """
        self.set_status(tr("status.changing_drive", drive=drive))
        text = self._capture_terminal_response(f"{drive}:")
        if CPMParser.has_drive_prompt(text, drive):
            self._do_refresh_remote_logic()
        else:
            self.drive_not_found.emit(drive)

    def _on_drive_not_found(self, drive):
        """
        Satisfies: FR-103.

        FR-103: runs on the GUI thread (queued from the drive-change worker).
        """
        self._clear_remote_files()
        QMessageBox.warning(
            self, tr("dialog.drive_not_found.title"), tr("error.drive_not_found_body", drive=drive)
        )

    def _update_remote_list_ui(self, files_dict):
        """
        Satisfies: FR-078, FR-079, FR-133.
        """
        # FR-133: store the parsed names as the canonical list and render them
        # through the active filter/sort controls. With the default settings
        # (no filter, sort by name ascending) this reproduces the FR-078
        # ascending-alphabetical display.
        self._remote_files = list(files_dict.keys())
        self._apply_remote_view()
        self.set_status(tr("status.remote_list_updated"))

    # -------------------------------------------------------------- transfers

    def _selected_filenames(self, list_widget) -> list[str]:
        """
        Satisfies: FR-106, FR-107.

        FR-106/FR-107: every selected file, in list display order (top to
        bottom). selectedItems() does not guarantee display order, so iterate
        the rows and keep those that are selected.
        """
        return [
            list_widget.item(row).text()
            for row in range(list_widget.count())
            if list_widget.item(row).isSelected()
        ]

    def _on_files_dropped(self, target_pane, source_pane, payload, external):
        """Start a drag-and-drop file transfer from a pane drop (FR-137, FR-138).

        Runs on the GUI thread (the drop event), then hands the actual transfer
        to the same batch worker threads as the Copy buttons, marshalling UI
        updates back via the existing signals (NFR-004). ``payload`` is a list
        of file names for an internal drag or absolute host paths for an
        external OS drop (``external``). Dropping onto the **Remote** pane sends
        to the remote (Copy to Remote); dropping onto the **Host** pane receives
        from the remote (Copy to Host). A transfer is permitted only when both
        the Terminal and Transport status flags are true (FR-080/CR-010), and is
        confirmed first (FR-137).

        Satisfies: FR-137, FR-138, FR-080, FR-106, FR-107, CR-010.
        """
        if not (self.serial_mgr.terminal_connected and self.serial_mgr.transport_connected):
            QMessageBox.critical(
                self, tr("dialog.error.title"), tr("error.transport_not_connected")
            )
            return
        if not payload:
            return
        if target_pane == "remote":
            if not self._confirm_dnd_transfer("remote", len(payload)):
                return
            # FR-138: external drops already carry absolute paths; an internal
            # drag from the Host pane carries names relative to the host dir.
            filepaths = (
                list(payload)
                if external
                else [os.path.join(self.host_dir, name) for name in payload]
            )
            threading.Thread(
                target=self._transfer_to_remote_batch, args=(filepaths,), daemon=True
            ).start()
        elif target_pane == "host":
            if not self._confirm_dnd_transfer("host", len(payload)):
                return
            save_paths = [os.path.join(self.host_dir, name) for name in payload]
            threading.Thread(
                target=self._transfer_to_host_batch, args=(save_paths,), daemon=True
            ).start()

    def _confirm_dnd_transfer(self, direction: str, count: int) -> bool:
        """Ask the user to confirm a drag-and-drop transfer (FR-137).

        Drag-and-drop is easy to trigger by accident and a serial transfer is
        slow, so each drop is confirmed before it starts. Returns True when the
        user accepts.

        Satisfies: FR-137.
        """
        key = (
            "dialog.dnd_confirm.to_remote"
            if direction == "remote"
            else "dialog.dnd_confirm.to_host"
        )
        reply = QMessageBox.question(self, tr("dialog.dnd_confirm.title"), tr(key, count=count))
        return reply == QMessageBox.StandardButton.Yes

    def do_copy_to_remote(self):
        """
        Satisfies: FR-080, FR-084, FR-106, CR-010.

        FR-080: a transfer is permitted only when both the Terminal and
        Transport status flags are true.
        """
        if not (self.serial_mgr.terminal_connected and self.serial_mgr.transport_connected):
            QMessageBox.critical(
                self, tr("dialog.error.title"), tr("error.transport_not_connected")
            )
            return

        # FR-106: transfer every selected file; warn when none is selected.
        filenames = self._selected_filenames(self.host_list)
        if not filenames:
            QMessageBox.warning(self, tr("dialog.warning.title"), tr("warning.select_upload"))
            return

        filepaths = [os.path.join(self.host_dir, name) for name in filenames]
        threading.Thread(
            target=self._transfer_to_remote_batch, args=(filepaths,), daemon=True
        ).start()

    def _on_transfer_bytes(self, direction, data):
        """
        Satisfies: FR-086, FR-088.

        Echo transfer bytes to the Terminal Window as hex tokens of
        the form <HH>, unless the `echo_transfer_data` setting disables it
        (FR-086). Runs on the transfer worker thread; the display write
        is marshalled to the GUI thread via term_write (NFR-004). The slot
        no-ops when the Terminal Window does not exist.
        Direction-tagged, timestamped trace to stdout (visible via
        `python -m cpm_fm`) so transfers can be debugged without conflating
        sent and received bytes, and so prompt/response timing is visible.
        The stdout trace (FR-088) is independent of the Terminal Window echo,
        so it still fires when the echo is turned off.
        """
        if self._debug_enabled():
            print(f"[xfer {direction} {time.time():.2f}] {data.hex(' ')}", flush=True)
        if not self._echo_transfer_enabled():
            return
        hex_text = "".join(f"<{b:02X}>" for b in data)
        self.term_write.emit(hex_text)

    def _echo_transfer_enabled(self) -> bool:
        """
        Satisfies: FR-086.

        The X-Modem transfer byte echo to the Terminal Window is emitted only
        when the `echo_transfer_data` setting holds an affirmative value
        (`ON`/`TRUE`/`1`/`YES`, case-insensitive); the default is off.
        """
        return str(self.settings.get("echo_transfer_data", "OFF")).strip().upper() in (
            "ON",
            "TRUE",
            "1",
            "YES",
        )

    def _on_transfer_progress_cb(self, blocks, bytes_done, total):
        """
        Satisfies: FR-105.

        XModem progress hook. Runs on the transfer worker thread; the
        dialog update is marshalled to the GUI thread via transfer_progress
        (NFR-004). total is unused here (the dialog captured it at start).
        """
        self.transfer_progress.emit(blocks, bytes_done)

    def _issue_remote_cmd(self, cmd_key: str, default: str, filename: str) -> None:
        """
        Satisfies: FR-087.

        Implements recv_remote_cmd / send_remote_cmd (UIR-045/UIR-046): the
        configured command is sent on the Terminal Port to launch the CP/M
        side of the transfer (PCPUT/PCGET), with "$1" replaced by the
        filename. Runs on the transfer worker thread; handle_terminal_send is
        safe to call from there (it marshals its display write via a signal).
        """
        template = self.settings.get(cmd_key, default)
        if not template:
            return
        self.handle_terminal_send(template.replace("$1", filename))

    def _launch_delay(self) -> float:
        """
        Satisfies: FR-089.

        Seconds to wait after launching the CP/M side (PCPUT/PCGET) before
        starting the X-Modem handshake. This must exceed the remote program's
        start-up time: while it prints its banner and opens the file it is not
        reading its UART, and any start-character prompts we send during that
        window pile up and overrun its (FIFO-less) UART. Tunable via the
        `xfer_launch_delay` setting; default 3s.
        """
        try:
            return max(0.0, float(self.settings.get("xfer_launch_delay", 3.0)))
        except (TypeError, ValueError):
            return 3.0

    def _interfile_delay(self) -> float:
        """
        Satisfies: FR-109.

        FR-109: extra settle time after the terminal output goes idle between
        files in a batch, before the next launch command is sent. Tunable via
        the `xfer_interfile_delay` setting (UIR-052); default 2s.
        """
        try:
            return max(0.0, float(self.settings.get("xfer_interfile_delay", 2.0)))
        except (TypeError, ValueError):
            return 2.0

    def _wait_for_terminal_idle(self) -> None:
        """
        Satisfies: FR-109.

        Between files in a batch, wait for the previous CP/M transfer
        program to finish and the CCP command prompt to return before issuing
        the next launch command. Without this, the prior PCPUT/PCGET is still
        closing its file and returning to the CCP — and therefore not yet
        servicing its (FIFO-less) UART — so the leading characters of the next
        command are lost (e.g. "PCPUT X" arriving as "CPUT X"). Mirrors the
        idle-detection of _capture_terminal_response: an initial wait for the
        completion text to start, then wait for the receive buffer to stop
        growing, bounded by a safety maximum, then a final settle. Runs on the
        transfer worker thread; it only reads the plain `_rx_buffer` string.
        """
        idle_window = 0.5
        max_wait = 8.0
        time.sleep(1.0)
        waited = 1.0
        while waited < max_wait:
            prev_len = len(self._rx_buffer)
            time.sleep(idle_window)
            waited += idle_window
            if len(self._rx_buffer) == prev_len:
                break
        time.sleep(self._interfile_delay())

    def _debug_enabled(self) -> bool:
        """
        Satisfies: FR-088.

        Verbose transfer debug output is emitted to stdout only when
        the `debug_logging` setting holds an affirmative value (default off).
        """
        return str(self.settings.get("debug_logging", "OFF")).strip().upper() in (
            "ON",
            "TRUE",
            "1",
            "YES",
        )

    def _debug(self, msg: str) -> None:
        """
        Satisfies: FR-088.
        """
        if self._debug_enabled():
            print(msg, flush=True)

    def _transfer_to_remote_batch(self, filepaths, retry: bool = False):
        """
        Satisfies: FR-099, FR-105, FR-106, FR-107, FR-108, FR-109, FR-142.

        Transfer each selected file sequentially over the
        single Transport Port. Runs on a worker thread. One progress
        dialog serves the whole batch. Abort on the first failure, or when the
        user cancels (FR-120). Each file's outcome (success, failure,
        cancellation, or skip) is recorded in the transfer history (FR-142);
        ``retry`` marks the records as a re-transfer (FR-144). Before sending,
        an existing destination file prompts the user to Overwrite/Skip/Cancel
        (FR-145/FR-146/FR-147).
        """
        count = len(filepaths)
        self._transfer_cancel.clear()  # FR-120: start each batch un-cancelled.
        self._conflict_policy = None  # FR-147: no carry-over between batches.
        self.batch_started.emit("remote", count)
        # FR-145: refresh the remote listing once so conflict detection checks
        # the live remote contents (empty set => no conflicts detected).
        remote_names = self._fresh_remote_names()
        succeeded = 0
        for index, filepath in enumerate(filepaths, start=1):
            name = os.path.basename(filepath)
            # The name the file will be given on the remote; differs from the
            # host base name when the user renames it to satisfy CP/M 8.3.
            remote_name = name
            # FR-120: stop before starting the next file if cancellation is requested.
            if self._transfer_cancel.is_set():
                self._finish_cancelled_batch("remote", succeeded)
                return
            # FR-148/FR-149: a name that does not meet the CP/M 8.3 convention
            # prompts the user to rename the file, skip it, or cancel the batch.
            if not CPMParser.is_valid_8_3(name):
                action, new_name = self._prompt_invalid_name(name)
                if action == CANCEL:
                    self._finish_cancelled_batch("remote", succeeded)
                    return
                if action == SKIP:
                    self._record_history(name, filepath, "remote", "skipped", 0, "", retry)
                    continue
                # RENAME: upload under the (validated) replacement name. The
                # renamed name is itself subject to conflict detection below.
                remote_name = new_name
            # FR-145/FR-146: prompt when the file already exists on the remote.
            if self._destination_conflict("remote", filepath, remote_names, remote_name):
                action = self._resolve_conflict(remote_name, "remote")
                if action == CANCEL:
                    self._finish_cancelled_batch("remote", succeeded)
                    return
                if action == SKIP:
                    self._record_history(remote_name, filepath, "remote", "skipped", 0, "", retry)
                    continue
            # FR-109: let CP/M return to its prompt before the next command.
            if index > 1:
                self._wait_for_terminal_idle()
            self.set_status(tr("status.uploading", name=remote_name, index=index, count=count))
            try:
                total_bytes = os.path.getsize(filepath)
            except OSError:
                total_bytes = 0
            self.transfer_file_started.emit(remote_name, total_bytes, index)
            try:
                ok = self._send_one_to_remote(filepath, remote_name)
            except Exception as e:
                self._debug(f"[copy-to-remote] EXCEPTION: {e!r}")
                # FR-142: record the failed file with its error message.
                self._record_history(remote_name, filepath, "remote", "failure", 0, str(e), retry)
                if succeeded:
                    self.transfer_completed.emit("remote")
                self.error_raised.emit(tr("dialog.error.title"), str(e))
                return
            if not ok:
                # FR-120: a cancelled transfer is not a failure.
                if self._transfer_cancel.is_set():
                    self._record_history(remote_name, filepath, "remote", "cancelled", 0, "", retry)
                    self._finish_cancelled_batch("remote", succeeded)
                    return
                # FR-142: record the failed file.
                self._record_history(
                    remote_name,
                    filepath,
                    "remote",
                    "failure",
                    0,
                    tr("error.transfer_failed", name=remote_name),
                    retry,
                )
                # FR-108: abort the batch and refresh if anything got through.
                if succeeded:
                    self.transfer_completed.emit("remote")
                self.error_raised.emit(
                    tr("dialog.xmodem_error.title"), tr("error.transfer_failed", name=remote_name)
                )
                return
            # FR-142: record the successful upload with its size.
            self._record_history(remote_name, filepath, "remote", "success", total_bytes, "", retry)
            succeeded += 1
        self.set_status(tr("status.successfully_uploaded", count=succeeded))
        # FR-099: refresh the Remote Files list so the uploaded files show.
        self.transfer_completed.emit("remote")

    def _finish_cancelled_batch(self, direction: str, succeeded: int) -> None:
        """
        Satisfies: FR-120.

        Common end-of-batch handling for a user-cancelled transfer (either
        direction). Runs on the transfer worker thread: report the cancellation
        and hand the dialog teardown / optional refresh to the GUI thread via
        the transfer_cancelled signal (NFR-004).
        """
        self.set_status(tr("status.transfer_cancelled", count=succeeded))
        self.transfer_cancelled.emit(direction, succeeded > 0)

    # ----------------------------------------------------- conflict resolution

    def _fresh_remote_names(self) -> set[str]:
        """Refresh the remote directory listing and return its names, upper-cased.

        Runs on the upload worker thread (FR-145). Reuses the FR-077–FR-079
        listing/parse mechanism synchronously (``_capture_terminal_response``
        blocks on this thread), and also emits ``remote_files_ready`` so the
        displayed Remote Files list reflects the just-read contents (NFR-004).
        Returns an empty set if nothing could be captured/parsed, in which case
        the caller detects no conflicts and uploads proceed as before.

        Satisfies: FR-145.
        """
        try:
            cmd = self.settings.get("list_files_cmd", "DIR")
            text = self._capture_terminal_response(cmd)
            files_dict = CPMParser.parse_dir_output(text)
        except Exception as e:  # pragma: no cover - defensive
            self._debug(f"[conflict] remote refresh failed: {e!r}")
            return set()
        # Mirror _do_refresh_remote_logic: update the on-screen list too.
        self.remote_files_ready.emit(files_dict)
        return {name.upper() for name in files_dict}

    @staticmethod
    def _destination_conflict(
        direction: str, path: str, remote_names: set[str], dest_name: str | None = None
    ) -> bool:
        """Whether a file of this name already exists at the destination (FR-145).

        For a download (``host``) the destination is the host filesystem, so the
        check is ``os.path.exists``. For an upload (``remote``) the destination
        is the remote drive, so the destination name (upper-cased — CP/M is
        upper-case 8.3) is checked against ``remote_names`` (the fresh listing).
        ``dest_name`` overrides the name checked for an upload; it is the
        effective remote name, which differs from the host base name when the
        file was renamed to satisfy the CP/M 8.3 convention (FR-149). When
        omitted the host base name is used.

        Satisfies: FR-145, FR-149.
        """
        if direction == "host":
            return os.path.exists(path)
        name = dest_name if dest_name is not None else os.path.basename(path)
        return name.upper() in remote_names

    def _resolve_conflict(self, name: str, direction: str) -> str:
        """Decide how to handle a destination conflict for ``name`` (FR-146/FR-147).

        Returns one of OVERWRITE / SKIP / CANCEL. Honours the batch-wide policy
        (FR-147) without prompting when one is in effect; otherwise raises the
        modal dialog on the GUI thread via ``conflict_detected`` and blocks this
        worker thread until the user answers (NFR-004). When the user ticks
        "apply to all", the chosen Overwrite/Skip becomes the batch policy.

        Satisfies: FR-146, FR-147.
        """
        if self._conflict_policy is not None:
            return self._conflict_policy
        action, apply_to_all = self._prompt_conflict(name, direction)
        if apply_to_all and action != CANCEL:
            self._conflict_policy = action
        return action

    def _prompt_conflict(self, name: str, direction: str) -> tuple[str, bool]:
        """Raise the conflict dialog on the GUI thread and block until answered.

        Marshals the modal dialog onto the GUI thread via ``conflict_detected``
        (NFR-004) and blocks this worker thread on ``_conflict_answered`` until
        the GUI thread records the user's (action, apply_to_all) choice. Split
        from :meth:`_resolve_conflict` so the batch-wide policy logic can be
        tested without the Qt signal/thread round-trip.

        Satisfies: FR-146, FR-147.
        """
        self._conflict_answered.clear()
        self.conflict_detected.emit(name, direction)
        self._conflict_answered.wait()
        return self._conflict_result

    def _on_conflict_detected(self, name: str, direction: str) -> None:
        """Show the modal conflict dialog and record the user's choice (FR-146).

        Runs on the GUI thread (queued from the transfer worker). Stores
        (action, apply_to_all) in ``_conflict_result`` and releases the worker
        by setting ``_conflict_answered`` (NFR-004).

        Satisfies: FR-146, FR-147, UIR-084.
        """
        try:
            dialog = FileConflictDialog(self, name, direction)
            dialog.exec()
            self._conflict_result = (dialog.action, dialog.apply_to_all)
        finally:
            self._conflict_answered.set()

    # ------------------------------------------------- CP/M name validation

    def _prompt_invalid_name(self, name: str) -> tuple[str, str]:
        """Raise the CP/M 8.3 name-validation dialog and block until answered.

        Marshals the modal dialog onto the GUI thread via
        ``invalid_name_detected`` (NFR-004) and blocks this upload worker thread
        on ``_invalid_name_answered`` until the GUI thread records the user's
        (action, new_name) choice. Split out so the batch loop's handling of the
        result can be tested without the Qt signal/thread round-trip.

        Satisfies: FR-148, FR-149.
        """
        self._invalid_name_answered.clear()
        self.invalid_name_detected.emit(name)
        self._invalid_name_answered.wait()
        return self._invalid_name_result

    def _on_invalid_name_detected(self, name: str) -> None:
        """Show the modal name-validation dialog and record the user's choice.

        Runs on the GUI thread (queued from the upload worker). Pre-fills the
        rename field with a CP/M 8.3-conforming suggestion (FR-149), stores
        (action, new_name) in ``_invalid_name_result``, and releases the worker
        by setting ``_invalid_name_answered`` (NFR-004).

        Satisfies: FR-148, FR-149, UIR-085.
        """
        try:
            suggested = CPMParser.suggest_8_3(name)
            dialog = FilenameValidationDialog(self, name, suggested)
            dialog.exec()
            self._invalid_name_result = (dialog.action, dialog.new_name)
        finally:
            self._invalid_name_answered.set()

    def _send_one_to_remote(self, filepath, remote_name: str | None = None) -> bool:
        """
        Satisfies: FR-081, FR-082, FR-083, FR-087, FR-149.

        Launch the CP/M receiver (PCGET) and send one file over X-Modem.
        Returns True on success. Runs on the batch worker thread; it does not
        touch the progress dialog or refresh (the batch driver owns those).
        ``remote_name`` is the name the file is given on the remote (the PCGET
        argument); it defaults to the host base name and differs only when the
        file was renamed to satisfy the CP/M 8.3 convention (FR-149).
        """
        ser = self.serial_mgr.transport_port
        if remote_name is None:
            remote_name = os.path.basename(filepath)
        delay = self._launch_delay()
        self._debug(
            f"[copy-to-remote] start file={remote_name} "
            f"cmd={self.settings.get('send_remote_cmd', 'PCGET $1')!r} "
            f"launch_delay={delay}s transport={ser}"
        )
        # FR-037: when the Transport and Terminal Ports are the same physical
        # port, suspend the terminal read loop for the whole session so it does
        # not steal the start character (C/NAK) and ACKs that X-Modem needs.
        shared = ser is not None and ser is self.serial_mgr.terminal_port
        if shared:
            self.serial_mgr.pause_terminal_reads()
        try:
            # Clear stale bytes, then launch the CP/M receiver (PCGET) on the
            # Terminal Port so its start character lands on a clean transport
            # buffer that send_file does not flush.
            if ser:
                ser.reset_input_buffer()
            self._issue_remote_cmd("send_remote_cmd", "PCGET $1", remote_name)
            self._debug(f"[copy-to-remote] launched PCGET; waiting {delay}s before handshake")
            time.sleep(delay)
            self._debug("[copy-to-remote] starting X-Modem send")
            xm = XModem(
                ser,
                monitor=self._on_transfer_bytes,
                progress=self._on_transfer_progress_cb,
                cancel_check=self._transfer_cancel.is_set,
            )
            return xm.send_file(filepath)
        finally:
            if shared:
                self.serial_mgr.resume_terminal_reads()

    def do_copy_to_host(self):
        """
        Satisfies: FR-080, FR-085, FR-106, CR-010.

        FR-080: a transfer is permitted only when both the Terminal and
        Transport status flags are true.
        """
        if not (self.serial_mgr.terminal_connected and self.serial_mgr.transport_connected):
            QMessageBox.critical(
                self, tr("dialog.error.title"), tr("error.transport_not_connected")
            )
            return

        # FR-106: transfer every selected file; warn when none is selected.
        filenames = self._selected_filenames(self.remote_list)
        if not filenames:
            QMessageBox.warning(self, tr("dialog.warning.title"), tr("warning.select_download"))
            return

        save_paths = [os.path.join(self.host_dir, name) for name in filenames]
        threading.Thread(
            target=self._transfer_to_host_batch, args=(save_paths,), daemon=True
        ).start()

    def _transfer_to_host_batch(self, save_paths, retry: bool = False):
        """
        Satisfies: FR-099, FR-105, FR-106, FR-107, FR-108, FR-109, FR-142.

        Receive each selected file sequentially over the single
        Transport Port. Runs on a worker thread. One progress dialog
        serves the whole batch. Abort on the first failure, or when the user
        cancels (FR-120). Each file's outcome (success, failure, cancellation,
        or skip) is recorded in the transfer history (FR-142); ``retry`` marks
        the records as a re-transfer (FR-144). Before receiving, an existing
        host file prompts the user to Overwrite/Skip/Cancel (FR-145/FR-146/FR-147).
        """
        count = len(save_paths)
        self._transfer_cancel.clear()  # FR-120: start each batch un-cancelled.
        self._conflict_policy = None  # FR-147: no carry-over between batches.
        self.batch_started.emit("host", count)
        succeeded = 0
        for index, save_path in enumerate(save_paths, start=1):
            name = os.path.basename(save_path)
            # FR-120: stop before starting the next file if cancellation is requested.
            if self._transfer_cancel.is_set():
                self._finish_cancelled_batch("host", succeeded)
                return
            # FR-145/FR-146: prompt when the file already exists on the host.
            if self._destination_conflict("host", save_path, set()):
                action = self._resolve_conflict(name, "host")
                if action == CANCEL:
                    self._finish_cancelled_batch("host", succeeded)
                    return
                if action == SKIP:
                    self._record_history(name, save_path, "host", "skipped", 0, "", retry)
                    continue
            # FR-109: let CP/M return to its prompt before the next command.
            if index > 1:
                self._wait_for_terminal_idle()
            self.set_status(tr("status.downloading", name=name, index=index, count=count))
            # The X-Modem stream carries no length, so total_bytes is 0
            # (indeterminate progress bar).
            self.transfer_file_started.emit(name, 0, index)
            try:
                ok = self._recv_one_to_host(save_path)
            except Exception as e:
                self._debug(f"[copy-to-host] EXCEPTION: {e!r}")
                # FR-142: record the failed file with its error message.
                self._record_history(name, save_path, "host", "failure", 0, str(e), retry)
                if succeeded:
                    self.transfer_completed.emit("host")
                self.error_raised.emit(tr("dialog.error.title"), str(e))
                return
            if not ok:
                # FR-120: a cancelled transfer is not a failure.
                if self._transfer_cancel.is_set():
                    self._record_history(name, save_path, "host", "cancelled", 0, "", retry)
                    self._finish_cancelled_batch("host", succeeded)
                    return
                # FR-142: record the failed file.
                self._record_history(
                    name,
                    save_path,
                    "host",
                    "failure",
                    0,
                    tr("error.transfer_failed", name=name),
                    retry,
                )
                # FR-108: abort the batch and refresh if anything got through.
                if succeeded:
                    self.transfer_completed.emit("host")
                self.error_raised.emit(
                    tr("dialog.xmodem_error.title"), tr("error.transfer_failed", name=name)
                )
                return
            # FR-142: record the successful download with the received file size
            # (the X-Modem stream carries no length, so read it from disk).
            self._record_history(
                name, save_path, "host", "success", self._file_size(save_path), "", retry
            )
            succeeded += 1
        self.set_status(tr("status.successfully_downloaded", count=succeeded))
        # FR-099: refresh the Host Files list so the downloaded files show.
        self.transfer_completed.emit("host")

    def _recv_one_to_host(self, save_path) -> bool:
        """
        Satisfies: FR-081, FR-082, FR-083, FR-087.

        Launch the CP/M sender (PCPUT) and receive one file over X-Modem.
        Returns True on success. Runs on the batch worker thread; it does not
        touch the progress dialog or refresh (the batch driver owns those).
        """
        ser = self.serial_mgr.transport_port
        delay = self._launch_delay()
        self._debug(
            f"[copy-to-host] start file={os.path.basename(save_path)} "
            f"cmd={self.settings.get('recv_remote_cmd', 'PCPUT $1')!r} "
            f"launch_delay={delay}s transport={ser}"
        )
        # FR-037: when the Transport and Terminal Ports are the same physical
        # port, suspend the terminal read loop for the whole session so it does
        # not consume the packets X-Modem is trying to receive.
        shared = ser is not None and ser is self.serial_mgr.terminal_port
        if shared:
            self.serial_mgr.pause_terminal_reads()
        try:
            # Launch the CP/M sender (PCPUT) on the Terminal Port, then receive.
            # receive_file drives the handshake (polls with NAK first, then 'C'
            # per NFR-003), so it tolerates PCPUT taking several seconds to arm.
            self._issue_remote_cmd("recv_remote_cmd", "PCPUT $1", os.path.basename(save_path))
            self._debug(f"[copy-to-host] launched PCPUT; waiting {delay}s before handshake")
            time.sleep(delay)
            self._debug("[copy-to-host] starting X-Modem receive")
            xm = XModem(
                ser,
                monitor=self._on_transfer_bytes,
                progress=self._on_transfer_progress_cb,
                cancel_check=self._transfer_cancel.is_set,
            )
            return xm.receive_file(save_path)
        finally:
            if shared:
                self.serial_mgr.resume_terminal_reads()

    # ------------------------------------------------------- transfer history

    @staticmethod
    def _file_size(path: str) -> int:
        """Return the size of ``path`` in bytes, or 0 if it cannot be read.

        Satisfies: FR-140, FR-142.
        """
        try:
            return os.path.getsize(path)
        except OSError:
            return 0

    def _record_history(
        self,
        filename: str,
        path: str,
        direction: str,
        status: str,
        size: int,
        error: str,
        retry: bool,
    ) -> None:
        """Record one file's transfer outcome in the persistent history.

        Called from the transfer worker threads (FR-142); the underlying store
        is thread-safe so no Qt-signal marshalling is needed here. A history
        write failure must never abort a transfer, so any error is swallowed.

        Satisfies: FR-140, FR-142, FR-144.
        """
        try:
            self.transfer_history.add_entry(
                filename=filename,
                path=path,
                direction=direction,
                status=status,
                size=size,
                error=error,
                retry=retry,
            )
        except Exception as e:  # pragma: no cover - defensive
            self._debug(f"[history] failed to record entry: {e!r}")

    def show_history(self):
        """Open the modal Transfer History dialog and act on a re-transfer.

        Runs on the GUI thread. The dialog records the chosen entry on
        ``retransfer_entry`` and closes itself when Re-transfer is clicked, so
        the transfer (and its own modal progress dialog) starts only after this
        dialog has closed (FR-144).

        Satisfies: FR-143, FR-144, UIR-082.
        """
        dlg = TransferHistoryDialog(self, self.transfer_history, self.window_state)
        dlg.exec()
        if dlg.retransfer_entry is not None:
            self._retransfer(dlg.retransfer_entry)

    def _retransfer(self, entry: dict):
        """Re-initiate the transfer described by a history ``entry`` (FR-144).

        Restores the file path and direction from the entry and reuses the
        existing batch transfer flow, recording the new attempt as a re-transfer
        (``retry=True``). A transfer is permitted only when both status flags are
        true (FR-080/CR-010); an upload additionally requires the source host
        file to still exist.

        Satisfies: FR-144, FR-080, CR-010.
        """
        if not (self.serial_mgr.terminal_connected and self.serial_mgr.transport_connected):
            QMessageBox.critical(
                self, tr("dialog.error.title"), tr("error.transport_not_connected")
            )
            return
        path = entry.get("path", "")
        direction = entry.get("direction")
        if direction == "remote":
            # Upload: the source host file must still exist to re-send it.
            if not path or not os.path.isfile(path):
                QMessageBox.critical(
                    self, tr("dialog.error.title"), tr("error.retransfer_file_missing", path=path)
                )
                return
            threading.Thread(
                target=self._transfer_to_remote_batch,
                args=([path],),
                kwargs={"retry": True},
                daemon=True,
            ).start()
        elif direction == "host":
            # Download: re-receive into the same host path (its base name is the
            # remote file name PCPUT will be asked for).
            if not path:
                return
            threading.Thread(
                target=self._transfer_to_host_batch,
                args=([path],),
                kwargs={"retry": True},
                daemon=True,
            ).start()

    # ------------------------------------------------------- backup / restore

    def do_backup(self):
        """Start a whole-drive Backup (remote→host) on a worker thread.

        FR-080/CR-010: permitted only when both status flags are true. The
        worker refreshes the destination, confirms the destructive operation,
        wipes the host directory, and downloads every remote file.

        Satisfies: FR-150, FR-152, FR-154, CR-010.
        """
        if not (self.serial_mgr.terminal_connected and self.serial_mgr.transport_connected):
            QMessageBox.critical(
                self, tr("dialog.error.title"), tr("error.transport_not_connected")
            )
            return
        threading.Thread(target=self._backup_drive, daemon=True).start()

    def do_restore(self):
        """Start a whole-drive Restore (host→remote) on a worker thread.

        FR-080/CR-010: permitted only when both status flags are true. The
        worker refreshes the destination, confirms the destructive operation,
        wipes the remote drive, and uploads every host file.

        Satisfies: FR-151, FR-152, FR-154, CR-010.
        """
        if not (self.serial_mgr.terminal_connected and self.serial_mgr.transport_connected):
            QMessageBox.critical(
                self, tr("dialog.error.title"), tr("error.transport_not_connected")
            )
            return
        threading.Thread(target=self._restore_drive, daemon=True).start()

    def _backup_drive(self):
        """Worker: mirror the remote drive to the host directory (remote→host).

        FR-150/FR-152: refresh the destination (host) and source (remote)
        listings, then confirm before any deletion. FR-153: on confirmation
        delete every host file. FR-154: download every remote file by reusing
        the Copy to Host batch transfer (its progress dialog, cancel, and
        history recording). The remote listing is captured before the wipe so it
        also serves as the set of files to back up.

        Satisfies: FR-150, FR-152, FR-153, FR-154.
        """
        self.set_status(tr("status.backing_up"))
        # FR-152: refresh the destination (host) pane before prompting, and the
        # source (remote) listing that tells us what to download.
        self.transfer_completed.emit("host")  # refresh Host pane on the GUI thread
        host_files = self._host_dir_files()  # FR-152 destination snapshot to wipe
        names = self._list_remote_file_names()
        if not self._confirm_backup_restore("backup"):
            self.set_status(tr("status.backup_restore_cancelled"))
            return
        # FR-153: empty the destination first, operating on the FR-152 snapshot.
        self._wipe_host_dir(host_files)
        save_paths = [os.path.join(self.host_dir, name) for name in names]
        if not save_paths:
            # FR-154: nothing to copy; the wipe already emptied the host pane.
            self.set_status(tr("status.nothing_to_transfer"))
            self.transfer_completed.emit("host")
            return
        # FR-154: reuse the batch engine (progress dialog + cancel + history).
        self._transfer_to_host_batch(save_paths)

    def _restore_drive(self):
        """Worker: mirror the host directory to the remote drive (host→remote).

        FR-151/FR-152: snapshot the source (host) files and refresh the
        destination (remote) listing, then confirm before any deletion.
        FR-153: on confirmation delete every remote file. FR-154: upload every
        host file by reusing the Copy to Remote batch transfer (its progress
        dialog, cancel, filename validation, and history recording).

        Satisfies: FR-151, FR-152, FR-153, FR-154.
        """
        self.set_status(tr("status.restoring"))
        host_files = self._host_dir_files()
        # FR-152: refresh the destination (remote) pane before prompting; the
        # returned names are also the set of remote files to delete.
        remote_names = self._list_remote_file_names()
        if not self._confirm_backup_restore("restore"):
            self.set_status(tr("status.backup_restore_cancelled"))
            return
        # FR-153: empty the destination first.
        self._wipe_remote_drive(remote_names)
        filepaths = [os.path.join(self.host_dir, name) for name in host_files]
        if not filepaths:
            # FR-154: nothing to copy; refresh the now-empty remote pane.
            self.set_status(tr("status.nothing_to_transfer"))
            self.transfer_completed.emit("remote")
            return
        # FR-154: reuse the batch engine (progress dialog + cancel + history).
        self._transfer_to_remote_batch(filepaths)

    def _confirm_backup_restore(self, operation: str) -> bool:
        """Raise the destructive-operation confirmation and block until answered.

        Marshals the modal warning onto the GUI thread via
        ``backup_restore_confirm`` (NFR-004) and blocks this worker thread on
        ``_backup_confirm_answered`` until the GUI thread records the user's
        choice. Returns True when the user chose Continue. ``operation`` is
        "backup" or "restore" and selects the destination wording.

        Satisfies: FR-152.
        """
        self._backup_confirm_answered.clear()
        self.backup_restore_confirm.emit(operation)
        self._backup_confirm_answered.wait()
        return self._backup_confirm_result

    def _on_backup_restore_confirm(self, operation: str) -> None:
        """Show the destructive-operation warning and record the user's choice.

        Runs on the GUI thread (queued from the Backup/Restore worker). Presents
        a modal warning with Continue and Cancel (Cancel default and the
        window-manager close equivalent — the safest choice, UIR-088), stores
        the boolean result, and releases the worker by setting
        ``_backup_confirm_answered`` (NFR-004).

        Satisfies: FR-152, UIR-088.
        """
        try:
            title_key = (
                "dialog.backup_restore.backup_title"
                if operation == "backup"
                else "dialog.backup_restore.restore_title"
            )
            msg_key = (
                "dialog.backup_restore.backup"
                if operation == "backup"
                else "dialog.backup_restore.restore"
            )
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Warning)
            box.setWindowTitle(tr(title_key))
            box.setText(tr(msg_key))
            continue_btn = box.addButton(tr("button.continue"), QMessageBox.ButtonRole.AcceptRole)
            cancel_btn = box.addButton(tr("button.cancel"), QMessageBox.ButtonRole.RejectRole)
            box.setDefaultButton(cancel_btn)
            box.exec()
            self._backup_confirm_result = box.clickedButton() is continue_btn
        finally:
            self._backup_confirm_answered.set()

    def _host_dir_files(self) -> list[str]:
        """Return the names of the files (not sub-directories) in the host dir.

        Runs on a worker thread (reads the filesystem only, touches no widget).
        Returns an empty list if the directory cannot be read.

        Satisfies: FR-151, FR-153.
        """
        try:
            return [
                f
                for f in os.listdir(self.host_dir)
                if os.path.isfile(os.path.join(self.host_dir, f))
            ]
        except OSError as e:
            self._debug(f"[backup/restore] host listing failed: {e!r}")
            return []

    def _list_remote_file_names(self) -> list[str]:
        """Refresh the remote listing and return its file names (display order).

        Runs on the Backup/Restore worker thread. Reuses the FR-077–FR-079
        listing/parse mechanism synchronously (``_capture_terminal_response``
        blocks on this thread) and emits ``remote_files_ready`` so the displayed
        Remote Files list reflects the just-read contents (NFR-004, FR-152).
        Returns an empty list if nothing could be captured or parsed.

        Satisfies: FR-150, FR-151, FR-152.
        """
        try:
            cmd = self.settings.get("list_files_cmd", "DIR")
            text = self._capture_terminal_response(cmd)
            files_dict = CPMParser.parse_dir_output(text)
        except Exception as e:  # pragma: no cover - defensive
            self._debug(f"[backup/restore] remote listing failed: {e!r}")
            return []
        self.remote_files_ready.emit(files_dict)
        return list(files_dict.keys())

    def _wipe_host_dir(self, names) -> None:
        """Delete every file in the host directory (Backup destination wipe).

        Runs on the Backup worker thread. Operates on ``names`` — the host
        listing refreshed in FR-152 before the confirmation prompt — rather than
        re-reading the directory, so the wipe acts on exactly the set the user
        was warned about. A file that fails to delete is logged and skipped
        rather than aborting the wipe.

        Satisfies: FR-150, FR-153.
        """
        for name in names:
            self.set_status(tr("status.wiping_destination", name=name))
            try:
                os.remove(os.path.join(self.host_dir, name))
            except OSError as e:
                self._debug(f"[backup] failed to delete {name}: {e!r}")

    def _wipe_remote_drive(self, names) -> None:
        """Delete every named remote file (Restore destination wipe).

        Runs on the Restore worker thread. Sends the configured delete command
        (``delete_remote_cmd``, default ``ERA $1``, FR-117) once per file on the
        Terminal Port, waiting for each to go idle via the capture mechanism.
        Deleting per file avoids the interactive ``ERA *.*`` confirmation on the
        CP/M side.

        Satisfies: FR-151, FR-153.
        """
        template = self.settings.get("delete_remote_cmd", "ERA $1")
        if not template:
            return
        for name in names:
            self.set_status(tr("status.wiping_destination", name=name))
            self._capture_terminal_response(template.replace("$1", name))

    # ------------------------------------------------------------------ config

    def load_config(self, filename):
        """
        Satisfies: FR-005, FR-011, FR-012, FR-017, FR-060, FR-125.
        """
        self.settings = self.config_handler.load_json(filename)
        # FR-005: remember this file so it is reloaded on the next startup.
        self.window_state.last_config = filename

        # FR-125: show the loaded config's base name (no path, no extension)
        # in the title bar.
        self._config_name = os.path.splitext(os.path.basename(filename))[0]
        self._update_window_title()

        # Restore host directory if specified in config
        host_dir = self.settings.get("host_directory")
        if host_dir:
            self.host_dir = host_dir
            self.refresh_host_files()

        # FR-017: the prior remote listing was captured under the previous
        # configuration and is no longer valid — clear it.
        self._clear_remote_files()
        self.set_status(tr("status.loaded_config", filename=filename))

    def menu_load(self):
        """
        Satisfies: FR-006, FR-010.
        """
        # FR-006: default to the folder used the last time a config was
        # loaded/saved, kept separate from the Host Files directory (FR-060).
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("dialog.load_config.title"),
            self.window_state.last_config_dir,
            tr("dialog.json_filter"),
        )
        if path:
            self.window_state.last_config_dir = os.path.dirname(path)
            self.load_config(path)

    def menu_save(self):
        """
        Satisfies: FR-005, FR-006, FR-013, FR-014.
        """
        # FR-006: default to the last-used config folder (see menu_load).
        path, _ = QFileDialog.getSaveFileName(
            self,
            tr("dialog.save_config.title"),
            self.window_state.last_config_dir,
            tr("dialog.json_filter"),
        )
        if path:
            self._save_to_path(path)

    def _save_to_path(self, path: str) -> bool:
        """
        Write the current settings to ``path`` and update last-used bookkeeping.

        Shared by File > Save (FR-013/FR-014) and File > New (FR-018). Returns
        True on a successful write.

        Satisfies: FR-005, FR-006, FR-014.
        """
        if not path.endswith(".json"):
            path += ".json"

        # Persist the current host directory in the settings before saving
        self.settings["host_directory"] = self.host_dir

        if self.config_handler.save_json(path, self.settings):
            # FR-005: the saved file becomes the last-used config to reload.
            self.window_state.last_config = path
            # FR-006: remember its folder for the next Load/Save dialog.
            self.window_state.last_config_dir = os.path.dirname(path)
            self.set_status(tr("status.saved_config", path=path))
            return True
        return False

    def menu_new(self):
        """
        Satisfies: FR-018, FR-019.

        FR-018: save the current configuration first (to the last-used file if
        known, otherwise via the Save dialog); abort if the save is cancelled or
        fails so nothing is lost. FR-019: on a successful save, close any open
        ports, clear the Remote Files list, and replace the settings with the
        default configuration.
        """
        # FR-018: save the current configuration. Save silently to the
        # currently-loaded file if there is one, otherwise prompt with the Save
        # dialog. Abort New on cancel/failure.
        if self.window_state.last_config:
            if not self._save_to_path(self.window_state.last_config):
                return
        else:
            path, _ = QFileDialog.getSaveFileName(
                self,
                tr("dialog.save_config.title"),
                self.window_state.last_config_dir,
                tr("dialog.json_filter"),
            )
            if not path or not self._save_to_path(path):
                return

        # FR-019: close any open Terminal/Transport ports (Disconnect behaviour,
        # FR-050-FR-058) and clear the now-stale Remote Files list. do_disconnect
        # reads the port names from the current settings, so it must run before
        # the settings are reset below.
        self.do_disconnect()

        # FR-019: replace the entire settings store with the default
        # configuration (full replace, per FR-011) and forget the remembered
        # configuration file path.
        self.settings = copy.deepcopy(DEFAULT_SETTINGS)
        self.window_state.last_config = ""

        # FR-125: no config file is loaded after New — drop the config name
        # from the title bar.
        self._config_name = ""
        self._update_window_title()

        # FR-019/FR-060: refresh the Host Files list to the default host
        # directory (empty -> current working directory).
        self.host_dir = self.settings.get("host_directory") or os.getcwd()
        self.refresh_host_files()

        # FR-019: ensure the Remote Files list is empty even if no port was open.
        self._clear_remote_files()
        self.set_status(tr("status.new_config_created"))

    def menu_serial_config(self):
        """
        Satisfies: FR-020, IFR-003.

        IFR-003 / UIR-022 / UIR-023: enumerate the host's serial ports.
        """
        ports = [p.device for p in serial.tools.list_ports.comports()]

        def update_settings(new_set):
            self.settings.update(new_set)
            self.set_status(tr("status.serial_settings_updated"))

        SerialConfigDialog(self, self.settings, ports, update_settings, self.window_state)

    def menu_general_config(self):
        """
        Satisfies: FR-021.
        """

        def update_settings(new_set):
            # The dialog seeds its host-directory field from the value stored in
            # settings and returns every field on save, so an unchanged field
            # carries the stored value back unchanged. Capture the stored value
            # before updating to tell an actual edit from an untouched field.
            old_host_dir = self.settings.get("host_directory", "")

            self.settings.update(new_set)

            # Only follow a host directory the user actually edited in the
            # dialog. If the field came back unchanged, leave the currently
            # selected directory alone — it may have been changed via Change
            # Directory since the config was loaded, and saving unrelated
            # general settings must not revert it.
            new_host_dir = new_set.get("host_directory", old_host_dir)
            if new_host_dir and new_host_dir != old_host_dir:
                self.host_dir = new_host_dir
                self.refresh_host_files()

            self.set_status(tr("status.general_settings_updated"))

        GeneralConfigDialog(self, self.settings, update_settings, self.window_state)

    def menu_about(self):
        """
        Satisfies: FR-022, UIR-076.

        Present the modal About dialog (program name, version, GitHub link, OK).
        """
        AboutDialog(self).exec()

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
        self.window_state.save_geometry("main", self)
        if self.terminal_win:
            self.window_state.save_geometry("terminal", self.terminal_win)
        # FR-015: close any open COM ports. FR-016: close all open windows.
        self.serial_mgr.close_ports()
        if self.terminal_win:
            self.terminal_win.close()
        event.accept()


def main() -> None:
    """
    Satisfies: STR-002, CR-002, CR-013, UIR-078.
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
