"""Unit tests for the requirements-traceability tooling under
``tools/traceability_sync/``.

That tooling is otherwise guarded only by the CI ``generate_views.py --check``
drift gate. These tests lock down the parsing behaviour that recent changes
introduced and that is easy to break silently:

* ``parser_code`` — capturing a decomposed sub-requirement's lowercase suffix
  (e.g. ``NFR-003a``), and letting a ``Satisfies:`` clause wrap across
  following ID-only lines while never slurping IDs out of surrounding prose;
* numeric range expansion (``DR-001-DR-003``) and explicit-wins-over-range
  de-duplication, which must keep working alongside the suffix support;
* ``generate_views`` — extracting requirement rows (including suffixed IDs)
  from a spec table while ignoring non-requirement rows, and aggregating
  more than one spec file (the SRS + its architecture companion);
* ``agent_toolset`` — accepting either a single spec path or a list, and
  routing each write-back to the file that actually defines the requirement.
"""

import sys
from pathlib import Path

# The tooling lives outside the importable ``cpm_fm`` package and imports its
# siblings by bare name, so its directory must be on sys.path before import.
_TOOLS = Path(__file__).resolve().parents[1] / "tools" / "traceability_sync"
sys.path.insert(0, str(_TOOLS))

import agent_toolset  # noqa: E402
import generate_views  # noqa: E402
from parser_code import RequirementExtractor, scan_codebase  # noqa: E402


# ---------------------------------------------------------------------------
# parser_code._extract_req_ids — the Satisfies-clause parser
# ---------------------------------------------------------------------------
def _extract(docstring):
    """Return the parsed (id, from_range) tuples for a docstring."""
    return RequirementExtractor("x.py")._extract_req_ids(docstring)


def _ids(docstring):
    """Return just the requirement IDs parsed from a docstring."""
    return [req_id for req_id, _ in _extract(docstring)]


def test_captures_lowercase_subrequirement_suffix():
    assert _ids("Satisfies: NFR-003a, NFR-003o.") == ["NFR-003a", "NFR-003o"]


def test_bare_ids_have_no_phantom_suffix():
    assert _ids("Satisfies: FR-001, DR-021.") == ["FR-001", "DR-021"]


def test_single_line_clause_after_prose():
    assert _ids("Summary line.\n\nSatisfies: FR-001, FR-002.") == ["FR-001", "FR-002"]


def test_clause_wraps_onto_id_only_continuation_lines():
    doc = "Satisfies: FR-001, FR-002,\n    FR-003, NFR-003a."
    assert _ids(doc) == ["FR-001", "FR-002", "FR-003", "NFR-003a"]


def test_label_then_ids_on_next_line():
    assert _ids("Satisfies:\n    FR-001, FR-002.") == ["FR-001", "FR-002"]


def test_prose_after_ids_does_not_leak():
    # FR-999 sits in a sentence after the clause and must NOT be collected.
    doc = "Satisfies: FR-001.\nSee FR-999 for the rationale."
    assert _ids(doc) == ["FR-001"]


def test_continuation_stops_at_first_prose_line():
    doc = "Satisfies: FR-001,\n    FR-002.\nNow some prose mentioning FR-999."
    assert _ids(doc) == ["FR-001", "FR-002"]


def test_blank_line_ends_continuation():
    doc = "Satisfies: FR-001,\n    FR-002.\n\n    FR-003."
    assert _ids(doc) == ["FR-001", "FR-002"]


def test_no_satisfies_tag_returns_empty():
    assert _extract("Just a docstring with FR-001 mentioned in prose.") == []


def test_missing_docstring_returns_empty():
    assert _extract(None) == []
    assert _extract("") == []


def test_numeric_range_expands_and_is_flagged():
    result = _extract("Satisfies: DR-001-DR-003.")
    assert result == [("DR-001", True), ("DR-002", True), ("DR-003", True)]


def test_range_then_explicit_single():
    result = _extract("Satisfies: FR-050-FR-052, FR-060.")
    assert result == [
        ("FR-050", True),
        ("FR-051", True),
        ("FR-052", True),
        ("FR-060", False),
    ]


def test_cross_prefix_is_not_treated_as_a_span():
    # "FR-001-DR-003" is two distinct IDs, not a range, so nothing in between.
    assert _ids("Satisfies: FR-001-DR-003.") == ["FR-001", "DR-003"]


def test_explicit_mention_wins_over_range_derived():
    # DR-002 appears both inside the range and explicitly; the explicit mention
    # makes it a genuine (non-range) ID.
    result = dict(_extract("Satisfies: DR-001-DR-003, DR-002."))
    assert result["DR-002"] is False
    assert result["DR-001"] is True and result["DR-003"] is True


# ---------------------------------------------------------------------------
# parser_code.scan_codebase — the AST integration over real files
# ---------------------------------------------------------------------------
def test_scan_codebase_reads_wrapped_suffixed_tags(tmp_path):
    (tmp_path / "mod.py").write_text(
        'def builder():\n'
        '    """Build a thing.\n'
        '\n'
        '    Satisfies: FR-001, NFR-003a,\n'
        '        NFR-003b.\n'
        '    """\n'
        '    return None\n',
        encoding="utf-8",
    )
    elements = scan_codebase(str(tmp_path))
    by_name = {(e.name, e.requirement_id) for e in elements}
    assert ("builder", "FR-001") in by_name
    assert ("builder", "NFR-003a") in by_name
    assert ("builder", "NFR-003b") in by_name
    assert all(e.module == "mod.py" for e in elements)


# ---------------------------------------------------------------------------
# generate_views — section parsing, helpers, and multi-file aggregation
# ---------------------------------------------------------------------------
_TABLE = (
    "# 7. Design Constraints\n"
    "\n"
    "| ID | Requirement | Priority | Verification | Source |\n"
    "|----|-------------|----------|--------------|--------|\n"
    "| CR-001 | A constraint. | Mandatory | I | App_Design |\n"
    "| NFR-003a | A sub-requirement. | Mandatory | T | impl. `xmodem.py:send_file` |\n"
    "\n"
    "## 9. Traceability\n"
    "\n"
    "| Source section | Requirement IDs |\n"
    "|----------------|-----------------|\n"
    "| App_Design | CR-001, NFR-003a |\n"
)


def test_parse_sections_extracts_ids_including_suffix(tmp_path):
    spec = tmp_path / "spec.md"
    spec.write_text(_TABLE, encoding="utf-8")
    sections = generate_views.parse_sections(spec)
    found = {req_id for _title, rows in sections for (req_id, _d, _s) in rows}
    assert found == {"CR-001", "NFR-003a"}


def test_parse_sections_ignores_non_requirement_rows(tmp_path):
    spec = tmp_path / "spec.md"
    spec.write_text(_TABLE, encoding="utf-8")
    titles = [title for title, _rows in generate_views.parse_sections(spec)]
    # The §9 traceability row's first cell is a source section, not an ID, so
    # that table must not appear as a parsed requirement section.
    assert "9. Traceability" not in titles
    assert "7. Design Constraints" in titles


def test_summarize_keeps_first_sentence_and_caps_words():
    # A lone sentence is returned verbatim (trailing period stripped, no ellipsis).
    assert generate_views.summarize("Persist the window geometry.") == "Persist the window geometry"
    # When more text follows the first sentence, it is cut there and marked with
    # a trailing ellipsis.
    text = "The parser shall do exactly one thing. And then another thing entirely."
    assert generate_views.summarize(text) == "The parser shall do exactly one thing…"


def test_code_impl_extracts_only_the_code_citation():
    assert generate_views.code_impl("App_Design §Purpose; impl. `app.py:main`") == "app.py:main"
    assert generate_views.code_impl("App_Design §Purpose") == "—"


def test_generate_aggregates_multiple_spec_files(tmp_path, monkeypatch):
    srs = tmp_path / "srs.md"
    arch = tmp_path / "arch.md"
    srs.write_text(
        "# SRS\n\n"
        "| ID | Requirement | Priority | Verification | Source |\n"
        "|----|---|---|---|---|\n"
        "| FR-001 | From the SRS. | Mandatory | T | — |\n",
        encoding="utf-8",
    )
    arch.write_text(
        "# Architecture\n\n"
        "| ID | Requirement | Priority | Verification | Source |\n"
        "|----|---|---|---|---|\n"
        "| CR-001 | From the architecture companion. | Mandatory | I | — |\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(generate_views, "SPEC_FILES", [srs, arch])
    index = generate_views.generate()[generate_views.INDEX_MD]
    # Both files' requirements must appear in the single generated index.
    assert "FR-001" in index and "CR-001" in index


# ---------------------------------------------------------------------------
# agent_toolset — input normalisation and per-file write-back routing
# ---------------------------------------------------------------------------
def test_agent_accepts_a_single_path_or_a_list():
    single = agent_toolset.TraceabilityAgent("src", "docs/spec.md")
    assert single.requirements_files == ["docs/spec.md"]
    multi = agent_toolset.TraceabilityAgent("src", ["docs/a.md", "docs/b.md"])
    assert multi.requirements_files == ["docs/a.md", "docs/b.md"]
    assert multi.requirements_file == "docs/a.md"  # first is the default target


def _write_spec(path, req_id, text):
    path.write_text(
        "# Spec\n\n"
        "| ID | Requirement | Priority | Verification | Source |\n"
        "|----|---|---|---|---|\n"
        f"| {req_id} | {text} | Mandatory | T | — |\n",
        encoding="utf-8",
    )


def test_apply_updates_routes_each_change_to_its_owning_file(tmp_path):
    # A code element implements CR-001 (defined only in the architecture file)
    # but neither spec cites it, so the agent must write the new citation back
    # into the architecture file — never into the SRS that defines FR-001.
    code = tmp_path / "src"
    code.mkdir()
    (code / "mod.py").write_text(
        'def builder():\n'
        '    """Build it.\n'
        '\n'
        '    Satisfies: CR-001.\n'
        '    """\n'
        '    return None\n',
        encoding="utf-8",
    )
    srs = tmp_path / "srs.md"
    arch = tmp_path / "arch.md"
    _write_spec(srs, "FR-001", "From the SRS.")
    _write_spec(arch, "CR-001", "From the architecture companion.")

    agent = agent_toolset.TraceabilityAgent(str(code), [str(srs), str(arch)])
    agent.run_sync_analysis()
    assert agent._id_to_file["FR-001"] == str(srs)
    assert agent._id_to_file["CR-001"] == str(arch)

    agent.apply_updates()
    # The CR-001 citation landed in the architecture file; the SRS is untouched.
    assert "impl." in arch.read_text(encoding="utf-8")
    assert "impl." not in srs.read_text(encoding="utf-8")
    assert "builder" in arch.read_text(encoding="utf-8")
