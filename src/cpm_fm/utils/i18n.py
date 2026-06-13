"""Runtime internationalisation (i18n) for the CP/M File Manager GUI.

All user-facing GUI strings are externalised into per-language files under
``src/cpm_fm/lang/`` named ``lang_<language>.txt`` and resolved at run time via
placeholder keys (FR-121, DR-042). This module is a small process-wide singleton:
the GUI calls :func:`tr` to resolve a key to text in the active language, and
:func:`set_language` to switch language (the GUI then re-translates itself).

The module imports nothing from the GUI toolkit, so it is safe to use from any
layer and unit-testable without a running Qt application (CR-014).

File format (DR-042):
  * UTF-8 text, one ``key = value`` entry per line (split on the first ``=``).
  * Blank lines and lines whose first non-space character is ``#`` are ignored.
  * Values are :meth:`str.format` templates; dynamic strings carry named
    placeholders such as ``{name}``, ``{index}``, ``{count}`` and ``{error}``.

English (``lang_english.txt``) is the complete reference and fallback language
(DR-043, FR-124): a key missing from the active language falls back to English,
and a key missing from English falls back to the key string itself.

Satisfies: FR-121, FR-124, DR-042, DR-043, NFR-005, CR-014.
"""

from __future__ import annotations

from pathlib import Path

# Language files live inside the package: src/cpm_fm/utils/i18n.py -> src/cpm_fm/lang/.
LANG_DIR = Path(__file__).resolve().parent.parent / "lang"

# The default and fallback language (FR-124, DR-043).
DEFAULT_LANGUAGE = "english"

# Cache of parsed language dicts, keyed by language name, so a file is read at
# most once per process. English is loaded lazily on first use as the fallback.
_cache: dict[str, dict[str, str]] = {}
_current_language = DEFAULT_LANGUAGE


def _parse(path: Path) -> dict[str, str]:
    """Parse a ``lang_<language>.txt`` file into a key->template mapping.

    Ignores blank lines and ``#`` comment lines, and splits each remaining line
    on its first ``=`` (so values may themselves contain ``=``). Surrounding
    whitespace around the key and value is stripped. A missing or unreadable
    file yields an empty mapping rather than raising, so a bad language file
    never blocks start-up (it simply falls back to English/keys).

    Satisfies: DR-042.
    """
    result: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return result
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip()
    return result


def _lang_path(language: str) -> Path:
    """
    Satisfies: DR-042.
    """
    return LANG_DIR / f"lang_{language}.txt"


def _load(language: str) -> dict[str, str]:
    """Return the parsed mapping for ``language``, reading and caching it once.

    Satisfies: DR-042.
    """
    if language not in _cache:
        _cache[language] = _parse(_lang_path(language))
    return _cache[language]


def available_languages() -> list[str]:
    """Return the sorted names of the languages discovered in ``LANG_DIR``.

    A language is any ``lang_<name>.txt`` file (FR-122, NFR-005). English is
    always included even if the directory cannot be scanned, so the menu and the
    fallback language are never empty.

    Satisfies: FR-122, NFR-005.
    """
    names = {DEFAULT_LANGUAGE}
    try:
        for path in LANG_DIR.glob("lang_*.txt"):
            names.add(path.stem[len("lang_") :])
    except OSError:
        pass
    return sorted(names)


def display_name(language: str) -> str:
    """Return the menu display form of a language name (capitalised).

    Satisfies: FR-122, UIR-077.
    """
    return language.capitalize()


def current_language() -> str:
    """Return the name of the currently active language.

    Satisfies: FR-123, FR-124.
    """
    return _current_language


def set_language(language: str) -> None:
    """Make ``language`` the active language, loading its file if needed.

    The English fallback is pre-loaded alongside, so :func:`tr` can always fall
    back. Switching to an unknown language is harmless: its mapping is empty, so
    every key falls back to English (then to the key).

    Satisfies: FR-122, FR-123, FR-124, DR-043.
    """
    global _current_language
    _load(DEFAULT_LANGUAGE)
    _load(language)
    _current_language = language


def tr(key: str, **kwargs: object) -> str:
    """Resolve ``key`` to text in the active language and apply placeholders.

    Looks the key up in the active language, then English, then uses the key
    itself (FR-124, DR-043). When keyword arguments are supplied they are
    substituted via :meth:`str.format`; a malformed template (e.g. a missing
    placeholder) degrades to the raw value rather than raising, so a faulty
    translation can never crash the GUI.

    Satisfies: FR-121, FR-124, DR-043.
    """
    active = _load(_current_language)
    value = active.get(key)
    if value is None:
        value = _load(DEFAULT_LANGUAGE).get(key, key)
    if not kwargs:
        return value
    try:
        return value.format(**kwargs)
    except (KeyError, IndexError, ValueError):
        return value
