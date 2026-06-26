# Requirements views (GENERATED — do not edit)

These files are **derived views** of the canonical specification
`docs/cpm_fm_requirements.md`, produced so that small / local LLMs (and humans)
can work without loading the full ~40K-token SRS into context.

| File | What it is | Use it for |
|------|------------|------------|
| `requirements_index.md` | Section-grouped, one-line-per-requirement summary (~13K tokens). | **Broad** understanding of what the system requires. |
| `code_to_requirements.md` | Each source file → the requirement IDs it implements (from code `Satisfies:` tags). | **Targeted** work: find the file you're editing, then read just those IDs. |
| `code_to_requirements.json` | The same map, machine-readable. | Tooling / scripts (drift checks, PR-impact lookups). |

## Do not edit these files

They are regenerated from the SRS and the code's `Satisfies:` docstring tags.
Any manual edit will be overwritten. The single source of truth is
`docs/cpm_fm_requirements.md` (plus the `Satisfies:` tags in code).

## Regenerating

```sh
python tools/traceability_sync/generate_views.py
```

Run this after changing the spec or any `Satisfies:` tag (it is step 3a of the
mandatory requirement-change workflow in `AGENTS.md`). To check freshness
without writing (e.g. in CI or a pre-commit hook):

```sh
python tools/traceability_sync/generate_views.py --check   # exit 1 if stale
```
