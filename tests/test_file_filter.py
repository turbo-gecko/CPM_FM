"""Unit tests for the pure file-list filter/sort helpers (cpm_fm.utils.file_filter).

These exercise the filtering and sorting logic shared by the Host and Remote
file panes without a running Qt application (CR-014): wildcard vs. substring
matching, case sensitivity, name/extension sort keys, direction toggling, sort
stability, and the combined filter-then-sort pipeline.

Satisfies: FR-130, FR-131, FR-132, FR-133.
"""

from __future__ import annotations

from cpm_fm.utils.file_filter import (
    SORT_EXTENSION,
    SORT_NAME,
    filter_and_sort,
    filter_names,
    has_wildcard,
    matches,
    sort_names,
)


def test_empty_pattern_matches_everything():
    """Verifies: FR-131."""
    # FR-131: a blank or whitespace pattern is "no filter".
    assert matches("ANY.TXT", "")
    assert matches("ANY.TXT", "   ")


def test_substring_match_is_case_insensitive_by_default():
    """Verifies: FR-131."""
    # FR-131: a pattern with no wildcard is a case-insensitive substring match.
    assert matches("README.TXT", "read")
    assert matches("README.TXT", "ME.T")
    assert not matches("README.TXT", "xyz")


def test_case_sensitive_substring_match():
    """Verifies: FR-131."""
    # FR-131: case-sensitive mode honours case exactly.
    assert matches("README.TXT", "README", case_sensitive=True)
    assert not matches("README.TXT", "readme", case_sensitive=True)


def test_wildcard_match_is_whole_name_glob():
    """Verifies: FR-131."""
    # FR-131: '*'/'?' switch to a whole-name glob (anchored, unlike substring).
    assert has_wildcard("*.TXT")
    assert matches("ABC.TXT", "*.TXT")
    assert matches("ABC.TXT", "A?C.TXT")
    assert not matches("ABC.TXT", "*.COM")
    # A glob is anchored: "TXT" as a glob fragment would not match the whole name.
    assert not matches("ABC.TXT", "?TXT")


def test_filter_names_preserves_input_order():
    """Verifies: FR-131."""
    # FR-131: filtering keeps the survivors in their original order.
    names = ["B.TXT", "A.TXT", "C.COM"]
    assert filter_names(names, "*.TXT") == ["B.TXT", "A.TXT"]


def test_sort_by_name_ascending_and_descending():
    """Verifies: FR-132."""
    # FR-132: name sort is case-insensitive; direction toggles the order.
    names = ["banana.txt", "Apple.txt", "cherry.txt"]
    assert sort_names(names, key=SORT_NAME) == ["Apple.txt", "banana.txt", "cherry.txt"]
    assert sort_names(names, key=SORT_NAME, descending=True) == [
        "cherry.txt",
        "banana.txt",
        "Apple.txt",
    ]


def test_sort_by_extension_groups_by_ext_then_name():
    """Verifies: FR-132."""
    # FR-132: extension sort groups by extension, with the name as tie-breaker.
    names = ["B.TXT", "A.COM", "C.TXT", "D.COM"]
    assert sort_names(names, key=SORT_EXTENSION) == ["A.COM", "D.COM", "B.TXT", "C.TXT"]


def test_sort_by_extension_handles_extensionless_names():
    """Verifies: FR-132."""
    # FR-132: an extensionless name has an empty extension and sorts first.
    names = ["READ.ME", "LICENSE", "A.TXT"]
    assert sort_names(names, key=SORT_EXTENSION) == ["LICENSE", "READ.ME", "A.TXT"]


def test_unknown_sort_key_falls_back_to_name():
    """Verifies: FR-132."""
    # FR-132: an unrecognised key defaults to name order rather than raising.
    names = ["B.TXT", "A.TXT"]
    assert sort_names(names, key="bogus") == ["A.TXT", "B.TXT"]


def test_filter_and_sort_applies_filter_before_sort():
    """Verifies: FR-133."""
    # FR-133: filter first, then sort the survivors.
    names = ["zeta.txt", "alpha.com", "beta.txt", "gamma.com"]
    assert filter_and_sort(names, "*.txt", key=SORT_NAME) == ["beta.txt", "zeta.txt"]
    assert filter_and_sort(names, "*.com", key=SORT_NAME, descending=True) == [
        "gamma.com",
        "alpha.com",
    ]


def test_filter_and_sort_default_is_name_ascending_no_filter():
    """Verifies: FR-133, FR-078."""
    # FR-133: with no arguments beyond the names, the result is the full list
    # sorted by name ascending (the FR-078 default for the remote list).
    names = ["C.TXT", "a.txt", "B.TXT"]
    assert filter_and_sort(names) == ["a.txt", "B.TXT", "C.TXT"]
