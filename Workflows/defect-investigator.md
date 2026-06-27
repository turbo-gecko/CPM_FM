---
description: Investigates, reproduces, tests, and fixes a defect — root-causes it, writes a failing Verifies:-tagged test that proves it, plans a minimal upstream fix, then STOPS for explicit user approval before applying the fix and verifying (suite green, views fresh, lint/hooks clean)
---

# Defect Investigator Workflow

This workflow guides a systematic defect investigation: reproduce the defect,
capture it in a failing test, root-cause it, plan a minimal fix, **stop for
explicit user approval**, then apply and verify. It is *test-first* and
*traceability-aware* — every test it adds carries a `Verifies:` tag, and it
leaves the generated views and the lint/format/hook gates clean.

**It never applies the code fix until the user explicitly approves the plan**
(Step 6). The failing test in Steps 3–4 is written first to prove the defect;
the fix that makes it pass waits for approval.

## Document & code layout (read this first)

Know the layout before you start (it mirrors the `code-requirements-align` and
`requirements-check` workflows):

- **`docs/cpm_fm_requirements.md`** — the SRS, source of truth for most
  requirements (`FR-`/`UIR-`/`IFR-`/`DR-`/`STR-` plus the behavioural `CR-010`,
  `CR-011`, `CR-015`, `NFR-002` and the X-Modem `NFR-003a`–`NFR-003q`).
- **`docs/cpm_fm_architecture.md`** — the architecture companion, source of truth
  for the architectural constraints `CR-001`–`CR-009`, `CR-012`–`CR-014` and the
  architectural NFRs `NFR-001`, `NFR-004`, `NFR-005`. A `CR-`/`NFR-` tag in code
  maps here, not in the SRS — read it too when the defect touches a constraint.
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

Traceability tags are the contract: implementation is tagged with a `Satisfies:`
docstring tag on the satisfying class/function; tests are tagged with a
`Verifies:` docstring tag on the test function (e.g.
`"""Verifies: FR-150, FR-152."""`). See `AGENTS.md` for the authoritative map.
The code is `src/`-layout under `src/cpm_fm/`.

## Step 1: Gather Defect Information
- Ask the user for the defect description.
- Ask clarifying questions if needed, such as:
  - What is the expected behavior vs. the actual behavior?
  - Which component or module is affected?
  - How can the defect be reproduced (exact steps, inputs, environment)?
  - Are there any error messages or stack traces?
  - Under what conditions does the defect occur?
- Where possible, identify the requirement ID(s) the defect violates (use
  `requirements_index.md`) — this anchors the test's `Verifies:` tag later.

## Step 2: Analyze Why Tests Missed the Defect (tool-first, then manual)
- **Tool-first pass:** run `python tools/traceability_sync/agent_toolset.py
  --coverage` from the repo root. If the violated requirement is already in the
  **Untested requirements** list, that *mechanically confirms* the coverage gap —
  no test exercised it. Also note any **stale `Verifies:` tags** in the affected
  area.
- **Then reason about what the tool cannot see** (it only knows tag-level
  coverage, not test strength):
  - Search for existing tests on the affected component and read them.
  - Identify whether scenarios were incomplete, or edge/boundary conditions,
    test data, or mock configurations were inadequate.
  - A requirement can be "covered" by a tagged-but-weak test — flag that.
- For a deep, adversarial audit of test *quality* (weak assertions, missing
  boundaries) beyond this defect, hand off to the `test-quality-checker` workflow.

## Step 3: Create or Update Unit Tests (test-first, tagged)
- Identify the test file(s) under `tests/` that should cover the defect scenario,
  following existing patterns and conventions.
- Write new test(s) that specifically trigger the defect, plus edge/boundary
  cases where applicable.
- **Every new or updated test must carry a `Verifies:` docstring tag** citing the
  requirement ID(s) it exercises (e.g. `"""Verifies: NFR-003a, NFR-003b."""`).
  An untagged test silently regresses traceability coverage and will surface as a
  gap in the views.

## Step 4: Run New Unit Tests (confirm red)
- Execute the new test(s) with `pytest`.
- Confirm they **fail** — this is the evidence the test detects the defect.
  Document the failure output.
- If a test passes unexpectedly, the test doesn't reproduce the defect — revise
  it before proceeding.

## Step 5: Root-Cause and Draft the Fix Plan
- Analyze the root cause; identify the specific file(s)/function(s) to change.
- Determine the **minimal** fix that addresses the root cause, not the symptom
  (prefer upstream fixes over workarounds).
- Consider side effects and regression risks.
- If the fix touches code with a `Satisfies:` tag — or *should* be tagged but
  isn't — note the tag work the fix will include.
- If, while root-causing, you find the requirement itself is **ambiguous,
  incomplete, contradictory, or silent** on the correct behaviour, do **not**
  guess and do **not** edit the spec here. Pause, cite the specific ID and
  `file:line`, and route the spec change through the `requirements-check`
  workflow.

## Step 6: STOP — Present Findings and Request Explicit Permission
- **Do not apply the code fix yet.**
- Present: the root cause, the failing test (with its red output as proof), the
  affected requirement ID(s), and the concrete fix plan (file(s)/function(s), the
  nature of the change, any tag updates, and how it will be verified).
- **Explicitly ask for permission to implement**, e.g.: "Shall I proceed with the
  fix above? I will not change any code until you confirm."
- Only after explicit approval may implementation begin. If the user approves only
  part of the plan, implement only the approved items.

## Step 7: Implement the Fix
- Apply the approved fix to the identified location(s).
- Use minimal, focused edits; follow existing code style and patterns.
- Add a comment only if the fix is non-obvious.
- Update or add the `Satisfies:` tag on the fixed code if the change creates or
  alters the requirement-bearing behaviour.

## Step 8: Verify the Fix (suite, views, lint/hooks all clean)
- Rerun the new test(s) and confirm they now **pass** (red → green).
- Run the **full** suite (`pytest`) to catch regressions.
- **Regenerate the traceability views**:
  `python tools/traceability_sync/generate_views.py`, then confirm freshness with
  `python tools/traceability_sync/generate_views.py --check` (must exit 0 — CI and
  the pre-commit hook enforce this).
- Re-run `python tools/traceability_sync/agent_toolset.py --coverage` and confirm
  the previously-untested requirement is now covered and there are **no new stale
  tags**.
- **Lint/format clean** (the pre-commit hooks and CI gate on these):
  `ruff check src tests` and `ruff format --check src tests`.
- Document the fix and the coverage improvement (requirement now verified).

## Step 9: Check Requirement Documents (verify alignment; hand off edits)
- Confirm the fix aligns with the stated requirement(s) in
  `docs/cpm_fm_requirements.md` and, for `CR-`/`NFR-` constraints,
  `docs/cpm_fm_architecture.md`.
- Verify the fix doesn't violate any other existing requirement.
- If the defect revealed a **gap or ambiguity** in the requirements, do **not**
  edit the spec in this workflow — note it and route the change through the
  `requirements-check` workflow. For a broader traceability audit (orphan code,
  unimplemented requirements), hand off to `code-requirements-align`.

## Notes
- Test-first is the point: the failing test in Steps 3–4 proves the defect before
  any fix exists; the green test in Step 8 proves the fix.
- Never apply the code fix without explicit user approval (Step 6).
- Every added/changed test carries a `Verifies:` tag; every fixed
  requirement-bearing element carries a `Satisfies:` tag; views are regenerated
  and `--check`-clean before you call the work done.
- Always cite requirement IDs and `file:line` so the investigation is traceable.
- Spec edits go through `requirements-check`; test-quality audits through
  `test-quality-checker`; broad traceability audits through
  `code-requirements-align`.
