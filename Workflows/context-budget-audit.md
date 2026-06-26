---
description: Periodic audit that the project's docs and source stay optimized for small/local-LLM context windows
---

# Context-Budget Audit Workflow

Run this **occasionally** (e.g. monthly, or before a release) to confirm the project still meets its
goal: documents and source files small enough that a small/local LLM can work across the codebase
without exhausting its context window. It is a read-only health check that ends in a report plus
recommended remediations — it does not change anything itself.

Background: the requirements spec was deliberately slimmed (generated views, extracted historical
back-matter) and guidance was added so agents load slim views instead of the full spec. This audit
catches regression of that work — docs creeping back up, views drifting, oversized source files, or
guidance falling out of alignment.

## Budgets (baseline as of 2026-06-27)

| Artifact | Budget (warn if exceeded) | Baseline |
|----------|---------------------------|----------|
| `docs/cpm_fm_requirements.md` (SRS) | ≤ 40K tokens / ≤ 800 lines | ~37K / 727 |
| `docs/requirements_views/requirements_index.md` | ≤ 16K tokens | ~13K |
| `docs/requirements_views/code_to_requirements.md` | ≤ 4K tokens | ~1K |
| `AGENTS.md` | ≤ 3.5K tokens / ≤ 200 lines | ~2.8K / ~190 |
| `.clinerules/requirements-context.md` | ≤ 1K tokens | ~0.5K |
| any single `src/**/*.py` | ≤ 500 lines | `app.py` is a known 3,041-line outlier (see deferred plan) |

Token estimate used throughout: **bytes ÷ 4** (rough but consistent with how these budgets were set).

## Step 1: Verify the generated views are in sync
- Run `python tools/traceability_sync/generate_views.py --check`.
- **FAIL** if it exits non-zero (the committed views are stale). Remediation: run
  `python tools/traceability_sync/generate_views.py` and commit `docs/requirements_views/`.
- This is the single most important check — stale views silently mislead every agent that trusts them.

## Step 2: Measure document sizes against the budgets
- For each artifact in the Budgets table, measure bytes and lines and compare. Example (cross-platform):
  `python -c "import os; [print(f'{p}: {os.path.getsize(p)//4} tok, {sum(1 for _ in open(p,encoding=\"utf-8\"))} lines') for p in ['docs/cpm_fm_requirements.md','docs/requirements_views/requirements_index.md','docs/requirements_views/code_to_requirements.md','AGENTS.md','.clinerules/requirements-context.md']]"`
- **WARN** for any artifact over budget. Compare against the baseline column: flag anything that has
  grown materially since, not just absolute breaches.
- Remediation if the SRS is over budget: extract the next-heaviest back-matter to a companion file
  (the §10/§11 pattern), tighten verbose requirement prose, or split a section — never delete content.

## Step 3: Confirm historical back-matter has not crept back into the SRS
- The SRS §10 Issue Resolution Log and §11 Change History must remain **stub redirects** to
  `docs/requirements_issue_log.md` and `docs/requirements_change_history.md`.
- Check the §10/§11 sections of the SRS are short stubs (a few lines each), not full tables.
- **WARN** if either section has regained tabular content (someone added history/issues to the SRS
  instead of the companion files). Remediation: move it to the companion file; remind via workflow
  step 7a in `AGENTS.md`.

## Step 4: Scan source files for oversized modules (code-side context cost)
- List every `src/**/*.py` over 500 lines (e.g. `find src -name '*.py' | xargs wc -l | sort -rn`).
- `app.py` is the known outlier with an existing decomposition plan at
  `temp/file-size-optimization-plan.md` — note its current size and whether the plan should be
  scheduled, but do not treat it as a new finding.
- **WARN** for any *new* file that has grown past ~500 lines. Remediation: propose a cohesive split
  (see the decomposition plan's mixin approach for the pattern).

## Step 5: Check guidance is present and aligned
- `AGENTS.md` and `.clinerules/requirements-context.md` must agree on the shared facts (they are
  deliberately kept in lockstep): the three view files, the two companion files, the
  `generate_views.py` regeneration command, and the SRS/index token figures.
- **WARN** if they disagree (e.g. one cites a stale token figure or omits a file the other names).
  Remediation: mirror the change into both. If you edit one, edit the other.
- Confirm both still tell agents to (a) consult the views first, (b) never hand-edit
  `docs/requirements_views/`, and (c) treat the companion files as historical/append-only.

## Step 6: Look for stale or broken file references in the docs
- Grep the docs and `AGENTS.md`/`.clinerules` for paths that no longer exist — especially
  `examples/*.json` filenames, `app.py:<method>` citations whose method has moved, and links to
  renamed/removed files.
- **WARN** per broken reference. Remediation: update to the current path, or remove if obsolete.
- (Prior instance: the test plan and source comments referenced deleted `serial_settings.json` /
  `settings_a.json` examples — fixed 2026-06-27. Watch for the same pattern.)

## Step 7: Spot-check traceability-tag coverage (keeps the views accurate)
- The views are only as good as the code's `Satisfies:` tags. Compare tag count to method count in the
  larger modules (e.g. `app.py`) and run `python tools/traceability_sync/agent_toolset.py` to confirm
  it reports no orphaned or undiscovered requirements.
- **WARN** if coverage has dropped (new methods without `Satisfies:` tags) or the tool reports drift.
  Remediation: add the missing tags, then regenerate the views (Step 1 remediation).

## Step 8: Produce the audit report
- Summarise each step as **PASS / WARN / FAIL** with the measured numbers next to each budget.
- List concrete remediations for every WARN/FAIL, ordered by impact (stale views and an over-budget
  SRS first).
- State the trend vs. the baseline (or the previous audit, if one was recorded): are docs getting
  smaller, holding, or creeping up?
- Do **not** apply fixes as part of this audit — surface them so the maintainer can schedule the work
  (some, like the `app.py` split, are larger efforts with their own plan).
