"""Modal auto-responders + native-dialog monkeypatches (plan §5).

The transfer/backup flows raise modal prompts via signals
(``conflict_detected``, ``invalid_name_detected``, ``backup_restore_confirm``) or
native dialogs (``QFileDialog``, ``QMessageBox``). On a headless bench run these
must answer themselves rather than block. Each installer takes a pytest
``monkeypatch`` so the patch is scoped to the test that requests it.

Constants are re-exported from the app's dialog modules so tests use the same
action vocabulary the production code does.
"""

from __future__ import annotations

from cpm_fm.gui.conflict_dialog import CANCEL, OVERWRITE, SKIP
from cpm_fm.gui.filename_validation_dialog import RENAME

__all__ = [
    "CANCEL",
    "OVERWRITE",
    "SKIP",
    "RENAME",
    "answer_conflict",
    "answer_invalid_name",
    "answer_remote_unavailable",
    "silence_message_boxes",
    "answer_confirm",
    "patch_open_file",
    "patch_save_file",
    "patch_existing_directory",
]


def answer_conflict(monkeypatch, action: str = OVERWRITE, apply_to_all: bool = False) -> None:
    """Make the file-conflict dialog (FR-146/FR-147) answer ``action``."""

    class _Fake:
        def __init__(self, *a, **k):
            self.action = action
            self.apply_to_all = apply_to_all

        def exec(self):
            return 1

    monkeypatch.setattr("cpm_fm.gui.mw_transfer_guards.FileConflictDialog", _Fake)


def answer_invalid_name(monkeypatch, action: str = RENAME, new_name: str | None = None) -> None:
    """Make the CP/M 8.3 name dialog (FR-148/FR-149) answer ``action``.

    With ``RENAME`` and no explicit ``new_name`` the suggested 8.3 name is used.
    """

    class _Fake:
        def __init__(self, parent, name, suggested):
            self.action = action
            self.new_name = suggested if new_name is None else new_name

        def exec(self):
            return 1

    monkeypatch.setattr("cpm_fm.gui.mw_transfer_guards.FilenameValidationDialog", _Fake)


def answer_remote_unavailable(monkeypatch, choice: str) -> None:
    """Force the post-connect "remote unavailable" dialog (FR-044) choice.

    ``choice`` is one of ``RemoteUnavailableDialog.ABORT/CONTINUE/TERMINAL``.
    """
    from cpm_fm.gui.remote_unavailable_dialog import RemoteUnavailableDialog

    monkeypatch.setattr(
        RemoteUnavailableDialog,
        "exec",
        lambda self: setattr(self, "choice", choice),
    )


def silence_message_boxes(monkeypatch) -> list[tuple]:
    """Stub ``QMessageBox`` critical/warning/information so they never block.

    Returns a list that accumulates ``(kind, args)`` so tests can assert which
    message boxes fired.
    """
    fired: list[tuple] = []
    import cpm_fm.app as app_mod

    for kind in ("critical", "warning", "information"):
        monkeypatch.setattr(
            app_mod.QMessageBox,
            kind,
            staticmethod(lambda *a, _k=kind, **k: fired.append((_k, a[1:])) or None),
        )
    return fired


def answer_confirm(monkeypatch, win, accept: bool = True) -> None:
    """Make the window's ``_confirm_dialog`` (DnD/backup warnings) return ``accept``."""
    monkeypatch.setattr(win, "_confirm_dialog", lambda *a, **k: accept)


def answer_file_action(monkeypatch, value: str | None = None, accepted: bool = True) -> None:
    """Make the context-menu ``FileActionDialog`` (rename/delete) auto-answer.

    ``value`` is the (edited) name returned by ``value()`` for a rename;
    ``accepted`` chooses Accept vs Reject. Patches the dialog where the remote
    and host context-menu actions reference it.
    """
    from PySide6.QtWidgets import QDialog

    class _Fake:
        def __init__(self, *a, **k):
            self._value = value if value is not None else (a[2] if len(a) > 2 else "")

        def exec(self):
            return QDialog.DialogCode.Accepted if accepted else QDialog.DialogCode.Rejected

        def value(self):
            return self._value

    monkeypatch.setattr("cpm_fm.gui.mw_context_menu.FileActionDialog", _Fake)


def patch_open_file(monkeypatch, path: str) -> None:
    monkeypatch.setattr(
        "cpm_fm.gui.mw_config.QFileDialog.getOpenFileName",
        lambda *a, **k: (path, "JSON files (*.json)"),
    )


def patch_save_file(monkeypatch, path: str) -> None:
    monkeypatch.setattr(
        "cpm_fm.gui.mw_config.QFileDialog.getSaveFileName",
        lambda *a, **k: (path, "JSON files (*.json)"),
    )


def patch_existing_directory(monkeypatch, path: str) -> None:
    monkeypatch.setattr(
        "cpm_fm.gui.mw_config.QFileDialog.getExistingDirectory",
        lambda *a, **k: path,
    )
