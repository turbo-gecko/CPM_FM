from __future__ import annotations

import re
from pathlib import Path

import markdown
from PySide6.QtWidgets import (
    QDialog,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
)

from cpm_fm.gui.dialog_buttons import build_button_row
from cpm_fm.utils.i18n import tr

# The user manual ships as Markdown inside the package so the same
# ``__file__``-relative lookup works both from source and from a frozen
# (PyInstaller) bundle, where the file is placed at ``cpm_fm/docs`` to match
# (gui/manual_dialog.py -> cpm_fm/docs/cpm_fm_manual.md).
MANUAL_PATH = Path(__file__).resolve().parent.parent / "docs" / "cpm_fm_manual.md"

# Markdown extensions used to render the manual to HTML. ``toc`` gives every
# heading an ``id`` anchor so the manual's table-of-contents links navigate
# within the document; ``tables``/``fenced_code`` render those constructs;
# ``attr_list``/``sane_lists`` improve list and attribute fidelity.
_MD_EXTENSIONS = ["toc", "tables", "fenced_code", "attr_list", "sane_lists"]

# Light styling applied to the rendered HTML. Qt's rich-text engine supports
# only a subset of CSS, so this is deliberately conservative (table borders are
# set via tag attributes in :func:`render_manual_html`, not CSS).
_MANUAL_CSS = (
    "code, pre { font-family: 'Courier New', monospace; }"
    "th, td { padding: 3px 6px; }"
    "th { background-color: #eeeeee; }"
)


def _github_slugify(value: str, separator: str) -> str:
    """Slugify a heading the way GitHub does, for TOC-anchor compatibility.

    The manual's table-of-contents links use GitHub-style anchors (lower-cased,
    punctuation stripped, spaces turned into hyphens **without** collapsing
    runs — so an em-dash surrounded by spaces yields a double hyphen). Python-
    Markdown's default slugify collapses those runs, which would break such a
    link, so we reproduce GitHub's rule here.
    """
    value = value.strip().lower()
    value = re.sub(r"[^\w\s-]", "", value)
    return re.sub(r"\s", separator, value)


def load_manual_markdown() -> str | None:
    """Return the manual's Markdown text, or ``None`` if it cannot be read.

    A missing or unreadable file is reported to the user by the dialog rather
    than raising, so opening the manual can never crash the GUI.

    Satisfies: FR-023, DR-047.
    """
    try:
        return MANUAL_PATH.read_text(encoding="utf-8")
    except OSError:
        return None


def render_manual_html(markdown_text: str) -> str:
    """Render the manual Markdown to a self-contained HTML document.

    Headings receive GitHub-style ``id`` anchors so the table-of-contents links
    navigate within the document, and tables are given border attributes (Qt's
    rich-text engine renders borders from tag attributes rather than CSS).

    Satisfies: FR-023, UIR-091.
    """
    body = markdown.markdown(
        markdown_text,
        extensions=_MD_EXTENSIONS,
        extension_configs={"toc": {"slugify": _github_slugify}},
    )
    body = body.replace("<table>", '<table border="1" cellpadding="4" cellspacing="0">')
    return f"<html><head><style>{_MANUAL_CSS}</style></head><body>{body}</body></html>"


class ManualDialog(QDialog):
    """Non-modal viewer for the bundled user manual (Help > Manual).

    Renders the Markdown manual to HTML and shows it in a scrollable, resizable
    read-only ``QTextBrowser``. In-document links (the table of contents)
    navigate within the manual; external ``http(s)`` links open in the host's
    default browser. A single Close button (centred per UIR-075) dismisses the
    window.

    Satisfies: FR-023, UIR-091.
    """

    def __init__(self, parent=None):
        """
        Satisfies: FR-023, UIR-091, UIR-075.
        """
        super().__init__(parent)
        self.setWindowTitle(tr("manual.title"))
        # A reference document the user reads alongside the app, so non-modal.
        self.setModal(False)
        self.resize(800, 600)

        layout = QVBoxLayout(self)

        browser = QTextBrowser(self)
        # Internal anchors navigate within the document; http(s) links open in
        # the host's default browser rather than inside the viewer.
        browser.setOpenExternalLinks(True)
        markdown_text = load_manual_markdown()
        if markdown_text is None:
            browser.setPlainText(tr("manual.load_error", path=str(MANUAL_PATH)))
        else:
            browser.setHtml(render_manual_html(markdown_text))
        layout.addWidget(browser)

        # UIR-075: a single Close button, centred, dismisses the window.
        close_btn = QPushButton(tr("button.close"))
        close_btn.setDefault(True)
        close_btn.clicked.connect(self.accept)
        layout.addLayout(build_button_row(accept_button=close_btn))
