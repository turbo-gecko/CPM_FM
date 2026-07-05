---
description: Two-way traceability audit between the SRS (and its architecture companion) and the implementation — finds unimplemented requirements, orphan code, divergences, and requirements with no test coverage, using the traceability_sync tools as the mechanical first pass, then reports findings and plans fixes (with explicit user approval before any change)
---

# Code / Requirements Alignment Workflow

This workflow performs a two-way traceability audit between the requirements
specification and the implementation, **and** between the requirements and the
test suite. It surfaces four classes of misalignment, reports them to the user as
a findings table, and produces an implementation plan. **It never modifies code,
specs, or tests automatically — explicit user permission is required before any
change is applied.**

It is *tool-assisted*: the `tools/traceability_sync/` tooling does the mechanical
tag-level trace; the agent does the semantic verification the tools cannot
(reading the code against the "shall" wording, judging partial implementations,
and finding truly untagged orphan behaviour).

## Document & code layout (read this first)

The requirements are split across several files — know the layout before you
start (it mirrors the `requirements-check` workflow):

- **`docs/cpm_fm_requirements.md`** — the SRS, source of truth for most
  requirements (`FR-`/`UIR-`/`IFR-`/`DR-`/`STR-` plus the behavioural `CR-010`,
  `CR-011`, `CR-015`, `NFR-002` and the X-Modem `NFR-003a`–`NFR-003o`).
- **`docs/cpm_fm_architecture.md`** — the architecture companion, source of truth
  for the architectural constraints `CR-001`–`CR-009`, `CR-012`–`CR-014` and the
  architectural NFRs `NFR-001`, `NFR-004`, `NFR-005`. **You must read this file
  too** — a `CR-`/`NFR-` tag in code maps here, not in the SRS, so skipping it
  would mis-report those tags as orphan code.
- **`docs/requirements_views/`** — generated, **read-only** views. Consult these
  *first* to save context instead of loading the whole SRS:
  - `requirements_index.md` — terse one-line-per-requirement summary (both files).
  - `code_to_requirements.md` / `.json` — source file → requirement IDs it
    implements (from code `Satisfies:` tags).
  - `requirements_to_tests.md` / `.json` — requirement → verifying test(s) (from
    test `Verifies:` tags), plus an **Untested requirements** list and a **Stale
    tags** list.
  Never hand-edit the views; regenerate them with
  `python tools/traceability_sync/generate_views.py`.
- `docs/requirements_change_history.md` and `docs/requirements_issue_log.md` are
  the §11/§10 companions (historical; rarely needed for an audit).

The code is `src/`-layout under `src/cpm_fm/`. The hub `app.py:MainWindow` was
decomposed into GUI mixins (`gui/mw_*.py`); the GUI-decoupled layers are
`terminal/` and `utils/` (CR-014 forbids GUI imports there). Implementation
traceability is carried by `Satisfies:` docstring tags on the satisfying
class/function; test traceability is carried by `Verifies:` docstring tags on
the test function. See `AGENTS.md` for the authoritative map.

## Step 1: Inventory the Requirements

- Read the two source-of-truth files (`docs/cpm_fm_requirements.md` **and**
  `docs/cpm_fm_architecture.md`). Use `requirements_index.md` for a fast pass and
  open the full SRS only for exact wording, priority, and verification method of
  the requirements you are auditing.
- Build an inventory of every individually-identifiable requirement: its ID,
  title, priority, the "shall" statement, and its acceptance criteria.
- Treat any traceability aid the documents already provide (the Source column,
  the views) as a **claim to be verified**, not as ground truth.

## Step 2: Run the Tool-Assisted First Pass (mechanical trace)

Run the traceability tooling from the repo root and capture the output — this is
the candidate list you will verify, not the verdict:

- `python tools/traceability_sync/generate_views.py --check` — confirms the views
  are fresh and that every requirements table is structurally valid (exit non-zero
  means stale views or a malformed table row — resolve that first).
- `python tools/traceability_sync/agent_toolset.py` — prints the Traceability
  Update Plan from code `Satisfies:` tags. Map its sections onto the finding
  types, **as leads to verify**:
  - `[POTENTIAL REMOVALS/ORPHANS]` (`to_remove`) → candidate **Unimplemented**:
    a requirement the docs claim but no code `Satisfies:` tag names.
  - `[NEW DISCOVERIES]` (`new_discoveries`) → candidate **Orphan Code**: a
    `Satisfies:` tag citing an ID absent from both spec files.
  - `[MODIFICATIONS]` (`to_update`) → a **stale citation**: code satisfies the
    requirement but the Source cell does not cite it.
- `python tools/traceability_sync/agent_toolset.py --coverage` — prints
  requirement→test coverage from `Verifies:` tags: the **Untested requirements**
  and any **stale `Verifies:` tags** (citing an undefined ID).

**Limits of the tool — what it cannot see (so Steps 3–6 still matter):** it only
sees `Satisfies:`/`Verifies:`-*tagged* elements, and only inside `src/` and
`tests/` — **it never reads `integration/` at all** (see Step 6's HIL bullet).
It cannot judge whether tagged code actually *satisfies* the wording
(divergence), whether an implementation is *partial*, or whether *untagged*
behaviour is a genuine orphan capability. Those require reading the code.

## Step 3: Trace Requirements → Code (find unimplemented / partial)

For every requirement in the inventory (prioritising the tool's `to_remove`
leads, but not limited to them):
- Locate the implementing code via `code_to_requirements.md` and by reading the
  code — never trust the matrix alone.
- Classify each as **Implemented**, **Partially implemented** (some acceptance
  criteria unmet), or **Unimplemented** (no code satisfies it). A `to_remove`
  lead that turns out to be implemented by *untagged* code is a missing
  `Satisfies:` tag, not an unimplemented requirement — note it as such.

## Step 4: Trace Code → Requirements (find orphan code)

- For each meaningful, user-visible/observable behaviour in the source, identify
  which requirement authorises it. Use `code_to_requirements.md` to find files
  with **no** tags — those are where untagged orphan behaviour hides (the tool is
  blind to them).
- Flag **Orphan Code**: a capability the spec does not mention. Internal helpers,
  refactors, and pure infrastructure that merely support a requirement are not
  orphans. The tool's `new_discoveries` (a tag citing an unknown ID) is a
  *different* kind of orphan — a dangling tag — report both.

## Step 5: Verify Correctness (find divergences)

For each requirement that has corresponding code:
- Compare the implementation against the precise "shall" statement **and** each
  acceptance criterion. Flag a **Divergence** when present-but-wrong: wrong
  values, precedence, units, file paths, off-by-one, missing edge-case handling.
- Where practical, confirm by running the relevant tests or tracing concrete
  example inputs from the acceptance criteria through the code.

## Step 6: Trace Requirements → Tests (find coverage gaps)

Using `requirements_to_tests.md` and the `--coverage` output from Step 2:
- For each in-scope requirement, confirm a `Verifies:`-tagged test actually
  exercises it (read the test — a tag is a claim). Flag **Test Coverage** gaps:
  - a requirement with **no** verifying test (and no other planned verification —
    note that many `UIR-`/`FR-` GUI requirements are verified by
    `docs/manual_test_plan.md`, not unit tests; treat those as covered-by-manual,
    not as defects);
  - a **stale `Verifies:` tag** citing an ID no spec defines (fix the tag or the
    spec);
  - a requirement whose test exists but is too weak to catch a realistic fault.
- A requirement may also be covered by the **integration (HIL) suite**
  (`integration/test_*.py`, tagged `@pytest.mark.mt("MT-..", "FR-..")`) rather than
  (or in addition to) a unit test — the protocol round-trips, GUI-over-real-serial
  flows, and widget-tree assertions live there. When judging a coverage gap,
  account for this third tier as well as `tests/` and `docs/manual_test_plan.md`:
  a requirement exercised by an `integration/` case tagged with its ID is
  covered-by-HIL, not an untested defect. The HIL suite is bench-only (a real CP/M
  peer; not in CI or the default `pytest`), so its coverage is established by
  reading the `mt`/`Verifies:` tags, not by the `--coverage` tool.
- **`integration/` is invisible to the mechanical tooling.** `generate_views.py`
  and `agent_toolset.py` only scan `src/` (`Satisfies:`) and `tests/`
  (`Verifies:`) — they never read `integration/`, so a stale or missing
  `@pytest.mark.mt(...)` tag there will never surface as a tool-reported lead,
  no matter how many times Step 2 is re-run. Before finalizing findings, `grep`
  `integration/*.py` for **every** requirement ID touched by a Step 3–5 fix
  (a corrected Source citation, a newly-added `Satisfies:` tag, a reworded
  requirement) — not just the ones already in the untested-requirements list.
  Two things to look for: (a) a citation/wording drift analogous to what was
  just fixed in `src/`/the spec (e.g. an HIL test asserting text the spec no
  longer says); (b) a tagging opportunity — an existing HIL case that already
  exercises the fixed behaviour (e.g. every bench target configured as
  single-shared-port also exercises a same-port requirement on every run) but
  whose `mt`/`Verifies:` tags don't yet cite it. Report both as findings; only
  apply the HIL edit once the user approves it (Step 10), same as any other
  change.
- This workflow checks *coverage/traceability* of tests to requirements. For a
  deep, adversarial audit of test *quality* (weak assertions, missing boundaries),
  defer to the `test-quality-checker` workflow; for chasing a real code fault a
  test uncovers, defer to `defect-investigator`. Note the hand-off rather than
  duplicating those audits here.

## Step 7: Clarify with the User Where Requirements Are Lacking

If, during Steps 3–6, a requirement is **ambiguous, incomplete, contradictory,
or silent** on a behaviour the code clearly needs, do **not** guess. Pause and
ask targeted questions, citing specific IDs and `file:line`, e.g.:
- "Requirement X is silent on <behaviour>; what is the intended behaviour?"
- "The code does A but requirement X implies B — which is correct?"
- "Capability C exists in the code with no requirement — add a requirement, or is
  it out of scope and should be removed?"
- "Test T verifies behaviour the spec does not state (no defined requirement) —
  add the requirement, or drop/retag the test?"

If the requirements document itself needs editing, that is governed by the
`requirements-check` workflow — note it, but do not edit the spec here without
the user's direction.

## Step 8: Report the Findings Table

Present **all** findings as a single table:

| # | Type | Req ID | Location (file:line) | Description | Severity | Suggested Action |
|---|------|--------|----------------------|-------------|----------|------------------|

- **Type** is one of: `Unimplemented`, `Partial`, `Orphan Code`, `Divergence`,
  `Test Coverage`, `Stale Tag` (a `Satisfies:`/`Verifies:` tag citing an unknown
  ID).
- **Req ID** is the requirement ID, or `—` for orphan code.
- **Severity** reflects impact and the requirement's priority (Critical / Major /
  Minor).
- **Suggested Action** is the one-line fix direction (implement, correct, remove,
  add test, add/fix tag, or "needs clarification — see Step 7").

Follow the table with a short narrative: counts per type, the highest-risk items,
and the current `--coverage` ratio (covered / total, untested count).

## Step 9: Produce an Implementation Plan

For the findings the user confirms are in scope, produce a concrete, ordered plan:
- One plan item per finding (or logical group). State the requirement ID(s)
  addressed, the file(s)/function(s) to change, the nature of the change, and how
  it will be verified (which tests to add/run).
- For any code change that adds or changes a `Satisfies:` tag, a Source citation,
  or a test `Verifies:` tag, the item must include: regenerate the views
  (`python tools/traceability_sync/generate_views.py`) and re-run
  `generate_views.py --check` + `agent_toolset.py --coverage` to confirm the trace
  is clean.
- For any plan item that changes user-visible behaviour, include a step to update
  the end-user manual (`src/cpm_fm/docs/cpm_fm_manual.md`) — affected section(s),
  Table of Contents, and Reference: Default Settings table — and bump its version
  line to match `src/version.txt` (distinct from `docs/manual_test_plan.md`).
- For any plan item that changes behaviour the integration (HIL) suite exercises
  (protocol round-trips, GUI-over-real-serial flows, widget-tree look-and-feel),
  include a step to update the relevant `integration/test_*.py` case(s) with
  accurate `@pytest.mark.mt(...)` tags and to verify them with a bench run
  (`pytest integration/`, plus `--run-destructive` for backup/restore) when
  hardware is available — or to record that the bench run is pending. State when
  no integration change is needed rather than omitting it.
- Route any *spec* edit (new/changed requirement, resolved ambiguity) through the
  `requirements-check` workflow, not this one.
- Sequence by dependency and risk; call out items blocked pending Step 7
  clarifications.

## Step 10: STOP — Request Explicit Permission

- **Do not apply any code, spec, or test changes as part of this workflow.**
- Present the findings table and the implementation plan, then **explicitly ask
  for permission to implement.** For example: "Shall I proceed with implementing
  the plan above? I will not make any changes until you confirm."
- Only after explicit approval may implementation begin. If the user approves only
  part of the plan, implement only the approved items, then run the verification
  in Step 9 (suite green, views fresh, `--check` clean, coverage has no new
  stale tags).

## Notes

- This is an audit-and-plan workflow; correctness depends on reading the actual
  code and tests, never on assuming a matrix/tag is accurate.
- Always cite requirement IDs and `file:line` so every finding is traceable.
- Three-way traceability is the point: requirements without code (Step 3),
  code without requirements (Step 4), and requirements without tests (Step 6) are
  all defects worth reporting.
- The tooling is the fast first pass; the agent's reading of code against the
  "shall" wording is what catches divergences and partials the tooling cannot.
- Never apply changes without explicit user approval (Step 10).
