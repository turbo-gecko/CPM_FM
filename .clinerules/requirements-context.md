# Requirements context budget — READ BEFORE touching the spec

The full specification `docs/cpm_fm_requirements.md` is ~40K tokens. **Do not
read it whole.** Three slim, generated views in `docs/requirements_views/` exist
so you can work without exhausting the context window. Use them by default.

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

- **Machine lookups (scripts/tooling):**
  Use `docs/requirements_views/code_to_requirements.json`.

## Rules

- `docs/cpm_fm_requirements.md` is the single source of truth and the **only**
  requirements file you edit by hand.
- The files under `docs/requirements_views/` are **generated — never edit them.**
  After changing the spec or any code `Satisfies:` tag, regenerate with:
  `python tools/traceability_sync/generate_views.py`
- Cite requirement IDs (e.g. `FR-080`) when referencing behaviour.
