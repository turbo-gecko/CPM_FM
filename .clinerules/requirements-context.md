# Requirements context budget — READ BEFORE touching the spec

The full specification `docs/cpm_fm_requirements.md` (plus its architecture
companion `docs/cpm_fm_architecture.md`) is large. **Do not read it whole.**
Several slim, generated views in `docs/requirements_views/` exist so you can work
without exhausting the context window. Use them by default. The views already
fold in both files, so the index covers every requirement including the `CR-`/
`NFR-` architectural constraints.

## Which view to use

- **Targeted work (editing or understanding a specific file/feature):**
  1. `search_codebase` (or grep) the file path in
     `docs/requirements_views/code_to_requirements.md` — it maps each source
     file to the requirement IDs it implements.
  2. `read_files` only those IDs in `docs/requirements_views/requirements_index.md`.
  3. Open the full spec **only** for the exact wording / priority / verification
     of one specific requirement — read just that section, never the whole file.

- **Broad understanding (what does the system require overall?):**
  Read `docs/requirements_views/requirements_index.md` (~13K tokens). It is a
  section-grouped, one-line-per-requirement summary. This alone is usually enough.

- **Test coverage of a requirement (which test verifies it?):**
  Use `docs/requirements_views/requirements_to_tests.md` — it maps each
  requirement ID to the test(s) carrying a `Verifies:` tag for it, and lists
  untested requirements and stale tags. (`python
  tools/traceability_sync/agent_toolset.py --coverage` prints the same untested /
  stale summary on demand.)

- **Machine lookups (scripts/tooling):**
  Use `docs/requirements_views/code_to_requirements.json` or
  `requirements_to_tests.json`.

## Rules

- `docs/cpm_fm_requirements.md` is the single source of truth for requirements and the
  only file you hand-edit to add or change a requirement — **except** the `CR-`/`NFR-`
  architectural constraints (module structure, toolkit, layering, threading model), which
  live in and are hand-edited in `docs/cpm_fm_architecture.md`. That doc also carries the
  authoritative architecture narrative (layers, cross-cutting behaviours).
- The Issue Resolution Log and Change History are companion files
  (`docs/requirements_issue_log.md`, `docs/requirements_change_history.md`) — historical and
  append-only. Don't load them for implementation work; append to them only as part of the
  requirement-change workflow (see `AGENTS.md`).
- The files under `docs/requirements_views/` are **generated — never edit them.**
  After changing the spec, any code `Satisfies:` tag, or any test `Verifies:` tag,
  regenerate with:
  `python tools/traceability_sync/generate_views.py`
- Tag tests the way you tag code: a test function's docstring carries a
  `Verifies:` line citing the requirement ID(s) it exercises, mirroring code
  `Satisfies:` tags.
- Cite requirement IDs (e.g. `FR-080`) when referencing behaviour.
