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
import parser_docs  # noqa: E402
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
        "def builder():\n"
        '    """Build a thing.\n'
        "\n"
        "    Satisfies: FR-001, NFR-003a,\n"
        "        NFR-003b.\n"
        '    """\n'
        "    return None\n",
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


def test_validate_tables_clean_on_well_formed_table(tmp_path):
    spec = tmp_path / "spec.md"
    spec.write_text(_TABLE, encoding="utf-8")
    assert generate_views.validate_tables(spec) == []


def test_validate_tables_flags_unescaped_pipe_row(tmp_path):
    # The DR-046 failure mode: a literal, unescaped '|' inside a cell makes the
    # row split to one more cell than the 5-column header.
    spec = tmp_path / "spec.md"
    spec.write_text(
        "| ID | Requirement | Priority | Verification | Source |\n"
        "|----|---|---|---|---|\n"
        "| DR-046 | Delimiters are a | b. | Mandatory | T | impl. `x.py:f` |\n",
        encoding="utf-8",
    )
    errors = generate_views.validate_tables(spec)
    assert len(errors) == 1
    assert "expected 5 cells but row has 6" in errors[0]
    assert "DR-046" in errors[0]


def test_validate_tables_accepts_escaped_pipe(tmp_path):
    # The same row with the pipe escaped as ``\|`` stays a single cell — exactly
    # the DR-046 fix — so the validator must not flag it.
    spec = tmp_path / "spec.md"
    spec.write_text(
        "| ID | Requirement | Priority | Verification | Source |\n"
        "|----|---|---|---|---|\n"
        "| DR-046 | Delimiters are a \\| b. | Mandatory | T | impl. `x.py:f` |\n",
        encoding="utf-8",
    )
    assert generate_views.validate_tables(spec) == []


def test_main_exits_nonzero_on_malformed_table(tmp_path, monkeypatch):
    # The --check entry point must surface a malformed row as a non-zero exit,
    # so CI / the pre-commit hook block it instead of silently mis-parsing.
    bad = tmp_path / "bad.md"
    bad.write_text(
        "| ID | Requirement | Priority | Verification | Source |\n"
        "|----|---|---|---|---|\n"
        "| FR-001 | Has an a | b pipe. | Mandatory | T | — |\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(generate_views, "SPEC_FILES", [bad])
    assert generate_views.main(["--check"]) == 3


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
        'def builder():\n    """Build it.\n\n    Satisfies: CR-001.\n    """\n    return None\n',
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


# ---------------------------------------------------------------------------
# parser_docs._merge_source — conservative, never-clobber-curation merging
# ---------------------------------------------------------------------------
def test_merge_source_fills_empty_or_placeholder_cell():
    assert parser_docs._merge_source("—", "impl. `a.py:f`") == "impl. `a.py:f`"
    assert parser_docs._merge_source("", "impl. `a.py:f`") == "impl. `a.py:f`"


def test_merge_source_appends_to_legacy_reference_only_cell():
    # No impl. segment present: append, discarding nothing.
    assert (
        parser_docs._merge_source("App_Design §Purpose", "impl. `a.py:f`")
        == "App_Design §Purpose; impl. `a.py:f`"
    )


def test_merge_source_replaces_plain_citation_list():
    # Trailing impl. text is a bare backticked citation list — safe to rewrite.
    assert (
        parser_docs._merge_source("impl. `old.py:f`, `old2.py:g`", "impl. `new.py:h`")
        == "impl. `new.py:h`"
    )
    # A legacy prefix before the citation list is preserved.
    assert (
        parser_docs._merge_source("App_Design; impl. `old.py:f`", "impl. `new.py:h`")
        == "App_Design; impl. `new.py:h`"
    )


def test_merge_source_refuses_to_clobber_curated_annotation():
    # Each of these carries curated text after the citation; merging must bail
    # out (return None) rather than discard it — the DR-045/047/CR-015 trap.
    parenthetical = "impl. `a.py:f` (default name `X`)"
    tests_citation = "impl. `a.py:f`; tests `test_a.py`"
    cross_ref = "impl. `a.py:f`; FR-121"
    for cell in (parenthetical, tests_citation, cross_ref):
        assert parser_docs._merge_source(cell, "impl. `new.py:h`") is None


# ---------------------------------------------------------------------------
# parser_docs.update_requirements_md — skip-and-report + dry-run
# ---------------------------------------------------------------------------
def _spec_with_source(path, req_id, source_cell):
    path.write_text(
        "# Spec\n\n"
        "| ID | Requirement | Priority | Verification | Source |\n"
        "|----|---|---|---|---|\n"
        f"| {req_id} | A requirement. | Mandatory | T | {source_cell} |\n",
        encoding="utf-8",
    )


def test_update_skips_and_reports_curated_row_preserving_text(tmp_path):
    spec = tmp_path / "spec.md"
    curated = "impl. `old.py:f` (default name `X`); tests `test_old.py`"
    _spec_with_source(spec, "DR-045", curated)
    before = spec.read_text(encoding="utf-8")

    report = parser_docs.update_requirements_md(str(spec), {"DR-045": "impl. `new.py:h`"})

    assert report["applied"] == 0
    assert report["skipped"] == ["DR-045"]
    # The curated cell — and the whole file — is byte-for-byte unchanged.
    assert spec.read_text(encoding="utf-8") == before
    assert "(default name `X`)" in spec.read_text(encoding="utf-8")
    assert "tests `test_old.py`" in spec.read_text(encoding="utf-8")


def test_update_rewrites_plain_citation_row(tmp_path):
    spec = tmp_path / "spec.md"
    _spec_with_source(spec, "FR-001", "impl. `old.py:f`")
    report = parser_docs.update_requirements_md(str(spec), {"FR-001": "impl. `new.py:h`"})
    assert report["applied"] == 1
    assert report["skipped"] == []
    assert "impl. `new.py:h`" in spec.read_text(encoding="utf-8")
    assert "old.py:f" not in spec.read_text(encoding="utf-8")


def test_update_dry_run_writes_nothing_but_returns_diff(tmp_path):
    spec = tmp_path / "spec.md"
    _spec_with_source(spec, "FR-001", "impl. `old.py:f`")
    before = spec.read_text(encoding="utf-8")

    report = parser_docs.update_requirements_md(
        str(spec), {"FR-001": "impl. `new.py:h`"}, dry_run=True
    )

    assert report["applied"] == 1
    # Nothing written; the file is untouched.
    assert spec.read_text(encoding="utf-8") == before
    # The diff previews the rewrite that would have happened.
    assert "new.py:h" in report["diff"]
    assert report["diff"].startswith("---")


def test_apply_updates_dry_run_leaves_docs_untouched(tmp_path):
    code = tmp_path / "src"
    code.mkdir()
    (code / "mod.py").write_text(
        'def builder():\n    """Build it.\n\n    Satisfies: FR-001.\n    """\n    return None\n',
        encoding="utf-8",
    )
    spec = tmp_path / "srs.md"
    _spec_with_source(spec, "FR-001", "—")
    before = spec.read_text(encoding="utf-8")

    agent = agent_toolset.TraceabilityAgent(str(code), [str(spec)])
    report = agent.apply_updates(dry_run=True)

    assert report["applied"] == 1
    assert spec.read_text(encoding="utf-8") == before  # nothing written
    assert any("mod.py:builder" in d for d in report["diffs"].values())
