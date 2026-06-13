"""Unit tests for the runtime internationalisation module (cpm_fm.utils.i18n).

These exercise the pure-Python translator without a running Qt application
(CR-014): the file-format parser, placeholder substitution, the English->key
fallback chain, language discovery, and cross-language key parity for the
shipped language files.

Satisfies: FR-121, FR-122, FR-124, DR-042, DR-043, NFR-005.
"""

from __future__ import annotations

import pytest

from cpm_fm.utils import i18n


@pytest.fixture(autouse=True)
def _reset_language():
    # The translator is a process-wide singleton; reset to English and clear the
    # cache around every test so state never leaks between tests.
    i18n._cache.clear()
    i18n.set_language(i18n.DEFAULT_LANGUAGE)
    yield
    i18n._cache.clear()
    i18n.set_language(i18n.DEFAULT_LANGUAGE)


def test_parser_ignores_comments_and_blank_lines(tmp_path):
    # DR-042: '#' lines and blank lines are ignored; 'key = value' is parsed.
    f = tmp_path / "lang_test.txt"
    f.write_text(
        "# a comment\n\n   # indented comment\napp.title = Hello\nmenu.file = File\n",
        encoding="utf-8",
    )
    parsed = i18n._parse(f)
    assert parsed == {"app.title": "Hello", "menu.file": "File"}


def test_parser_splits_on_first_equals(tmp_path):
    # DR-042: only the FIRST '=' separates key from value, so values may contain '='.
    f = tmp_path / "lang_test.txt"
    f.write_text("config.json_filter = JSON files (*.json) = ok\n", encoding="utf-8")
    parsed = i18n._parse(f)
    assert parsed["config.json_filter"] == "JSON files (*.json) = ok"


def test_parser_missing_file_returns_empty(tmp_path):
    # DR-042: an unreadable/missing file degrades to an empty mapping, never raises.
    assert i18n._parse(tmp_path / "does_not_exist.txt") == {}


def test_tr_resolves_active_language():
    # FR-121: a known key resolves to the active language's text.
    assert i18n.tr("menu.file") == "File"


def test_tr_substitutes_named_placeholders():
    # DR-042: values are str.format templates filled at run time.
    assert i18n.tr("error.drive_not_found_body", drive="B") == "Drive B: not found"
    assert i18n.tr("transfer.count", blocks=2, bytes_done=256) == "Blocks: 2    Bytes: 256"


def test_tr_unknown_key_falls_back_to_key():
    # FR-124/DR-043: a key absent from every language falls back to the key itself.
    assert i18n.tr("no.such.key.exists") == "no.such.key.exists"


def test_tr_falls_back_to_english_for_missing_translation():
    # FR-124/DR-043: a key present in English but not the active language falls
    # back to the English text. (Add a German-only gap by clearing its entry.)
    i18n.set_language("german")
    i18n._cache["german"].pop("status.ready", None)
    assert i18n.tr("status.ready") == "Ready"


def test_tr_malformed_template_does_not_raise(tmp_path, monkeypatch):
    # A bad translation template degrades to the raw value rather than crashing.
    monkeypatch.setitem(i18n._cache, "english", {"k": "Hi {missing}"})
    monkeypatch.setattr(i18n, "_current_language", "english")
    assert i18n.tr("k", name="x") == "Hi {missing}"


def test_available_languages_discovers_shipped_files():
    # FR-122/NFR-005: discovery finds the shipped language files and always
    # includes English.
    langs = i18n.available_languages()
    assert "english" in langs
    assert "german" in langs
    assert "french" in langs
    assert langs == sorted(langs)


def test_display_name_is_capitalised():
    # FR-122/UIR-077: the menu label is the capitalised language name.
    assert i18n.display_name("english") == "English"
    assert i18n.display_name("german") == "German"


def test_set_and_current_language_round_trip():
    # FR-122/FR-123: switching language is reflected by current_language().
    i18n.set_language("french")
    assert i18n.current_language() == "french"
    assert i18n.tr("menu.file") == "Fichier"


@pytest.mark.parametrize("language", ["german", "french"])
def test_translation_keys_match_english(language):
    # DR-043: each shipped translation must define exactly the same keys as the
    # English reference (no missing keys, no stray extra keys) so nothing silently
    # falls back and no dead entries accumulate.
    english = i18n._parse(i18n._lang_path("english"))
    other = i18n._parse(i18n._lang_path(language))
    assert english, "English reference file should not be empty"
    missing = set(english) - set(other)
    extra = set(other) - set(english)
    assert not missing, f"{language} is missing keys: {sorted(missing)}"
    assert not extra, f"{language} has unexpected extra keys: {sorted(extra)}"
