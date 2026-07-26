---
name: pre-commit-checks
description: Runs and verifies all pre-commit checks (lint, format, requirements traceability, and AI-asset validation) before a commit or push so failures are caught locally first
---

# Pre-Commit Checks Workflow

This workflow runs every linting, formatting, and traceability check that the CI pipeline enforces — *locally* — so a push is never rejected by CI for fixable issues. It is designed to be run before committing or pushing changes.

## What It Checks (mirrors `.pre-commit-config.yaml` and `ci.yml`)

| # | Check | Command | Scope |
|---|-------|---------|-------|
| 1 | Ruff linter | `.venv/Scripts/python.exe -m ruff check src tests` | `src/`, `tests/` |
| 2 | Ruff formatter | `.venv/Scripts/python.exe -m ruff format --check src tests` | `src/`, `tests/` |
| 3 | Requirement views freshness | `.venv/Scripts/python.exe tools/traceability_sync/generate_views.py --check` | Specifications + tags vs. generated views |
| 4 | AI asset validation | `.venv/Scripts/python.exe tools/ai/validate.py` | `.agents/` metadata, skills, placeholders, and links |

## Prerequisites

- Dev dependencies installed once:
  `.venv/Scripts/python.exe -m pip install -e ".[dev]"`
- Pre-commit installed:
  `.venv/Scripts/python.exe -m pip install pre-commit`
- Python 3.12 environment (matches CI)

## Usage

### Run all pre-commit hooks on staged files only:
```bash
.venv/Scripts/python.exe -m pre_commit run
```

### Run all hooks on every file in the repo:
```bash
.venv/Scripts/python.exe -m pre_commit run --all-files
```

### Run a single hook:
```bash
.venv/Scripts/python.exe -m pre_commit run ruff-check --all-files
.venv/Scripts/python.exe -m pre_commit run ruff-format --all-files
.venv/Scripts/python.exe -m pre_commit run requirement-views-fresh --all-files
.venv/Scripts/python.exe -m pre_commit run ai-assets-valid --all-files
```

## Step-by-Step Workflow

### Step 1: Verify Environment is Ready

Confirm the dev tooling is available:

```bash
.venv/Scripts/python.exe -m ruff --version
.venv/Scripts/python.exe tools/traceability_sync/generate_views.py --check
.venv/Scripts/python.exe tools/ai/validate.py
```

The local hooks invoke `.venv/Scripts/python.exe` directly and do not depend on
an activated environment or global `PATH`.

### Step 2: Run All Pre-Commit Checks

Execute the full pre-commit suite:

```bash
.venv/Scripts/python.exe -m pre_commit run --all-files
```

To diagnose a hook independently, run the underlying checks directly:

```bash
.venv/Scripts/python.exe -m ruff check src tests
.venv/Scripts/python.exe -m ruff format --check src tests
.venv/Scripts/python.exe tools/traceability_sync/generate_views.py --check
```

### Step 3: Review Results

Each hook reports its result:

| Result | Meaning |
|--------|---------|
| `PASSED` | No issues found; file is clean |
| `FAILED` | Issue detected; output shows exactly what to fix |

**For `ruff-check` failures:** Read the output. It reports `file:line:code message`. Fix each violation. Apply auto-fixes where safe: `.venv/Scripts/python.exe -m ruff check --fix src tests`.

**For `ruff-format` failures:** The output lists files that need reformatting. Apply formatting: `.venv/Scripts/python.exe -m ruff format src tests`.

**For `requirement-views-fresh` failures:** The requirement views are stale. Regenerate them: `.venv/Scripts/python.exe tools/traceability_sync/generate_views.py`. Review the generated diff to confirm only expected changes (view timestamps/content). Commit them alongside your code changes.

### Step 4: Re-run After Fixes

After applying fixes, re-run **only** the affected hooks to confirm resolution:

```bash
# After ruff-fixing:
.venv/Scripts/python.exe -m pre_commit run ruff-check --all-files
.venv/Scripts/python.exe -m pre_commit run ruff-format --all-files

# After regenerating views:
.venv/Scripts/python.exe -m pre_commit run requirement-views-fresh --all-files
.venv/Scripts/python.exe -m pre_commit run ai-assets-valid --all-files
```

### Step 5: Stage Files and Commit

Once all hooks pass, stage your changes and commit:

```bash
git add <your-changed-files> docs/requirements_views/
git commit -m "Describe your change (refs: FR-XXX)"
```

## Automated Agent Procedure

When an agent is asked to perform pre-commit checks on a codebase or after making changes, follow this procedure:

1. **Confirm tools are installed** (Windows cmd.exe syntax):
   ```cmd
   .venv\Scripts\python.exe -m ruff --version
   .venv\Scripts\python.exe -c "import tools.traceability_sync"
   ```
2. **Run all checks** (direct execution, no PATH dependency — recommended on Windows):
   ```cmd
   rem Lint
   .venv\Scripts\python.exe -m ruff check src tests

   rem Format
   .venv\Scripts\python.exe -m ruff format --check src tests

   rem Traceability views
   .venv\Scripts\python.exe tools/traceability_sync/generate_views.py --check

   rem AI assets
   .venv\Scripts\python.exe tools/ai/validate.py
   ```
3. **For each failing check:**
   a. Fix ruff-lint errors: `.venv\Scripts\python.exe -m ruff check --fix src tests` (report what was auto-fixed, then manually fix any remaining issues).
   b. Reformat: `.venv\Scripts\python.exe -m ruff format src tests`.
   c. Regenerate views: `.venv\Scripts\python.exe tools/traceability_sync/generate_views.py`.
4. **Re-run all checks** to confirm they now pass.
5. **Report summary**: For each check, state PASS/FAIL and list any issues found/resolved. If everything passes, confirm the codebase is ready for commit/push.

## Output Format

Always report results in this structured format:

```
## Pre-Commit Check Results

| Check | Result | Details |
|-------|--------|---------|
| ruff check (src) | PASS/FAIL | 0 issues / [list issues if FAIL] |
| ruff check (tests) | PASS/FAIL | 0 issues / [list issues if FAIL] |
| ruff format (src) | PASS/FAIL | 0 files need formatting / [list files if FAIL] |
| ruff format (tests) | PASS/FAIL | 0 files need formatting / [list files if FAIL] |
| requirement views | PASS/FAIL | In sync / Stale — regenerated |
| AI assets | PASS/FAIL | Valid / [list metadata, placeholder, or link errors] |

### Actions Taken
- Auto-fixed: [count] lint issues via `ruff check --fix`
- Reformatted: [count] files via `ruff format`
- Regenerated: `docs/requirements_views/*`
- AI assets: validated with `tools/ai/validate.py`
```

## Important Notes

- **Never skip pre-commit checks before pushing.** If CI fails due to a pre-commit-checkable issue, the workflow failed — it exists precisely to catch these problems *before* they reach the remote.
- **Commit regenerated views with your code changes.** They are part of the traceability chain and must stay in sync with the commit.
- **The hooks use `local` repos** (see `.pre-commit-config.yaml`) — they run against the project's pinned tool versions, so there is no risk of version drift between local and CI.
- **CI runs these same checks.** If a pre-commit hook fails on CI but passed locally, check for: tool version mismatch, untracked files not covered by the hook's `files:` regex, or stale generated views.
- **Test suite execution (`pytest`)** is *not* part of pre-commit checks in this project — it runs separately in CI as a distinct gate. This workflow focuses on lint, format, traceability-view freshness, and AI-asset validity.

## Integration with Other Workflows

| Workflow | Relationship |
|----------|-------------|
| `requirements-change` | Run these checks after requirement work to verify the resulting tree |
| `test-quality-audit` | Pre-commit ensures style/conventions; this workflow assesses test *quality* beyond coverage |
| `code-requirements-align` | Run code-requirements-align *before* pre-commit if modifying requirements or Satisfies/Verifies tags, since tag changes require view regeneration which is a pre-commit gate |
