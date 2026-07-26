---
name: context-budget-audit
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

## Budgets

| Artifact | Budget (warn if exceeded) |
|----------|---------------------------|
| `docs/cpm_fm_requirements.md` | ≤ 70K tokens / ≤ 1,200 lines |
| `docs/cpm_fm_architecture.md` | ≤ 6K tokens / ≤ 250 lines |
| `docs/requirements_views/requirements_index.md` | ≤ 30K tokens |
| `docs/requirements_views/code_to_requirements.md` | ≤ 4K tokens |
| `AGENTS.md` | ≤ 5K tokens / ≤ 220 lines |
| `.agents/README.md` | ≤ 1K tokens |
| any single `src/**/*.py` | ≤ 1,200 lines |

Record measured values in each audit report rather than embedding a dated
baseline here. Compare trends with the previous recorded audit when available.

Token estimate used throughout: **bytes ÷ 4** (rough but consistent with how these budgets were set).

## Step 1: Verify the generated views are in sync
- Run `.venv/Scripts/python.exe tools/traceability_sync/generate_views.py --check`.
- **FAIL** if it exits non-zero (the committed views are stale). Remediation: run
  `.venv/Scripts/python.exe tools/traceability_sync/generate_views.py` and commit `docs/requirements_views/`.
- This is the single most important check — stale views silently mislead every agent that trusts them.

## Step 2: Measure document sizes against the budgets
- For each artifact in the Budgets table, measure bytes and lines and compare. Example (cross-platform):
  `.venv/Scripts/python.exe -c "import os; [print(f'{p}: {os.path.getsize(p)//4} tok, {sum(1 for _ in open(p,encoding=\"utf-8\"))} lines') for p in ['docs/cpm_fm_requirements.md','docs/cpm_fm_architecture.md','docs/requirements_views/requirements_index.md','docs/requirements_views/code_to_requirements.md','AGENTS.md','.agents/README.md']]"`
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
- List every `src/**/*.py` over 1,200 lines using a platform-appropriate read-only command.
- **WARN** for any file that exceeds the budget. Remediation: propose a cohesive split
  (see the decomposition plan's mixin approach for the pattern).

## Step 5: Check guidance is present and aligned
- `AGENTS.md` and `.agents/README.md` must agree on the canonical AI-asset
  locations and responsibilities. Skills and workflows must point back to
  `AGENTS.md` rather than copy its repository policy.
- **WARN** if they disagree (e.g. one cites a stale token figure or omits a file the other names).
  Remediation: mirror the change into both. If you edit one, edit the other.
- Confirm the applicable guidance still tells agents to consult the views first,
  never hand-edit generated views, and treat companion files as append-only.

## Step 6: Look for stale or broken file references in the docs
- Grep the docs, `AGENTS.md`, and `.agents/` for paths that no longer exist — especially
  `examples/*.json` filenames, `app.py:<method>` citations whose method has moved, and links to
  renamed/removed files.
- **WARN** per broken reference. Remediation: update to the current path, or remove if obsolete.
- (Prior instance: the test plan and source comments referenced deleted `serial_settings.json` /
  `settings_a.json` examples — fixed 2026-06-27. Watch for the same pattern.)

## Step 7: Spot-check traceability-tag coverage (keeps the views accurate)
- The views are only as good as the code's `Satisfies:` tags. Compare tag count to method count in the
  larger modules and run `.venv/Scripts/python.exe tools/traceability_sync/agent_toolset.py` to confirm
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
