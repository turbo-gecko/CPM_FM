# Requirements views (GENERATED — do not edit)

These files are **derived views** of the canonical specification
`docs/cpm_fm_requirements.md` and its architecture companion
`docs/cpm_fm_architecture.md` (which holds the `CR-`/`NFR-` architectural
constraints), produced so that small / local LLMs (and humans) can work without
loading the full SRS into context.

| File | What it is | Use it for |
|------|------------|------------|
| `requirements_index.md` | Section-grouped, one-line-per-requirement summary (~13K tokens). | **Broad** understanding of what the system requires. |
| `code_to_requirements.md` | Each source file → the requirement IDs it implements (from code `Satisfies:` tags). | **Targeted** work: find the file you're editing, then read just those IDs. |
| `code_to_requirements.json` | The same map, machine-readable. | Tooling / scripts (drift checks, PR-impact lookups). |
| `requirements_to_tests.md` | Each requirement ID → the test(s) that verify it (from test `Verifies:` tags), plus untested-requirement and stale-tag lists. | Checking which requirements have automated test coverage. |
| `requirements_to_tests.json` | The same coverage map, machine-readable. | Tooling / scripts (coverage gates, untested-requirement reports). |

## Do not edit these files

They are regenerated from the SRS, the architecture companion, the code's
`Satisfies:` docstring tags, and the test suite's `Verifies:` docstring tags. Any
manual edit will be overwritten. The single source of truth is
`docs/cpm_fm_requirements.md` and `docs/cpm_fm_architecture.md` (plus the
`Satisfies:` tags in code and `Verifies:` tags in tests).

## Regenerating

```sh
python tools/traceability_sync/generate_views.py
```

Run this after changing the spec, any code `Satisfies:` tag, or any test
`Verifies:` tag (it is step 3a of the mandatory requirement-change workflow in
`AGENTS.md`). To check freshness without writing (e.g. in CI or a pre-commit
hook):

```sh
python tools/traceability_sync/generate_views.py --check   # exit 1 if stale
```
