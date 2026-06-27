# AGENTS.md

This file provides guidance to AI agents when working with code in this repository.

## What this is

`cpm-fm` is a **PySide6 (Qt for Python)** desktop app that transfers files between a modern host and
legacy [CP/M](https://en.wikipedia.org/wiki/CP/M) systems over a serial link using X-Modem. Beyond
single/multi-file transfers it offers drag-and-drop, file-conflict resolution, CP/M 8.3 filename
validation, a persistent transfer history, whole-drive backup/restore, and a 12-language UI. The GUI
applies a Material Design theme via the `qt-material` package (set centrally at start-up in
`gui/theme.py`; the light/dark variant follows the host OS — UIR-070/UIR-073). As of v1.3 the UI was
migrated from Tkinter to PySide6; there is no remaining `tkinter` code, and the stray `wxPython` in
`.venv` is unused (ignore it). The current version is in `src/version.txt`.

## Commands

Install (editable, with dev tools): `python -m pip install -e .[dev]`

Run:
- `cpm-fm` — installed GUI launcher (bound to `pythonw.exe`, no console window on Windows)
- `python -m cpm_fm` — equivalent, keeps a console for `print()` debug output (serial errors are
  printed to stdout, not surfaced in the UI)

Test / lint / type-check (CI runs all of these on Python 3.12, see `.github/workflows/ci.yml`):
- `pytest` — full unit suite (`-q` is set in `pyproject.toml`; `testpaths = ["tests"]`, so it never
  descends into `integration/`)
- `pytest tests/test_cpm_parser.py::test_parse_dir_output_extracts_filenames` — single test
- `ruff check src tests` and `ruff format --check src tests` (CI uses `--check`; drop it to apply)
- `mypy src`

Integration (hardware-in-the-loop) suite — **separate, bench-only, not run by CI or the default
`pytest`** because it drives the real app against a real CP/M machine over serial:
- `pytest integration/` — the HIL suite (its own `integration/pytest.ini`); `--target`/`--all-targets`
  select the rig, `--run-destructive` enables the backup/restore (whole-drive-wipe) cases
- `python integration/run.py` — interactive target picker
- See `integration/README.md` for wiring, target setup (`hil_config.json`), and the manual-vs-automated
  split. It is additive test infrastructure and does not itself define requirements.

## Architecture

**Authoritative reference: [`docs/cpm_fm_architecture.md`](docs/cpm_fm_architecture.md)** — the
Software Architecture Description. It holds the full layer/module breakdown, the cross-cutting
behaviours, and the architectural constraints (the `CR-`/`NFR-` requirements). The summary below is
just enough to orient; consult the architecture doc when you need detail.

`src/`-layout package under `src/cpm_fm/`. `app.py:MainWindow` (a `QMainWindow` subclass) is the hub
that owns all components and wires UI events to them; `app.py:main` creates the `QApplication`, applies
the theme, shows the window, and runs `app.exec()` (entry point for both launchers). Three layers are
intentionally decoupled from the GUI so they are unit-testable without a running Qt app — **CR-014
forbids GUI-toolkit imports in `terminal/` and `utils/`**:

- `terminal/` — `serial_manager.py` (`SerialManager`: two `pyserial` ports, terminal + transport, with
  a daemon `_read_loop`), `xmodem.py` (`XModem`: hand-rolled X-Modem, blocking, on worker threads),
  `cpm_parser.py` (`CPMParser.parse_dir_output`: pure `DIR`-output scraper, the most-tested logic).
- `utils/` — `config_handler.py` (JSON settings load/save), `i18n.py` (the `tr(key)` translation
  singleton; strings in `lang/lang_<language>.txt`, English the reference/fallback), `file_filter.py`
  (pure filter/sort), `transfer_history.py` (`TransferHistory`: GUI-free JSON history store).
- `gui/` — Qt-only widgets/dialogs: `theme.py`, `terminal_window.py`, `config_dialogs.py`,
  `file_list_widget.py`, `transfer_dialog.py`, `conflict_dialog.py`, `filename_validation_dialog.py`,
  `transfer_history_dialog.py`, `manual_dialog.py`, `file_action_dialog.py`, `about_dialog.py`,
  `dialog_buttons.py`, `window_state.py`.

**Most safety-critical rule — the threading model (NFR-001/NFR-004):** serial reads and both transfer
directions run off the Qt GUI thread on daemon threads; any UI update from them must be marshalled onto
the GUI thread by **emitting a Qt signal** (never touch a widget directly from a worker thread, or Qt
will crash/misbehave). Three signals — `conflict_detected`, `invalid_name_detected`,
`backup_restore_confirm` — drive a modal prompt on the GUI thread while the worker thread blocks. Other
load-bearing details (capture-based remote listing, the two coexisting config JSON shapes, the three
separate persistence stores, the unconfigured start, never hard-coding GUI strings) are documented in
the architecture doc — read it before changing background work, settings handling, or persistence.

## Design docs and workflows

`docs/cpm_fm_requirements.md` is the **authoritative requirements specification** going forward — an
ISO/IEC/IEEE 29148 SRS with uniquely identified, traceable requirements (`FR-`/`UIR-`/`DR-`/`CR-`/
`NFR-` etc.). Cite requirement IDs when referencing behavior. Its companion
`docs/cpm_fm_architecture.md` is the **authoritative architecture description**: it carries the
architectural design constraints (CR-001–CR-009, CR-012–CR-014) and architectural NFRs (NFR-001,
NFR-004, NFR-005), extracted from the SRS with IDs unchanged. Edit architectural `CR-`/`NFR-`
requirements there; the remaining behavioural constraints (CR-010, CR-011, CR-015, NFR-002) and the
X-Modem protocol requirements (NFR-003a–NFR-003o, SRS §8.1) stay in the SRS. `docs/legacy/App_Requirements.md` and
`docs/legacy/App_Design.md` are the original source documents it was consolidated from; they are
**archived** for history but are **superseded** where they conflict (e.g. they call Copy to Remote/Host
empty stubs, but the SRS and code implement working X-Modem transfers — see `FR-080`–`FR-085`,
`CR-010`).
The SRS's §10 **Issue Resolution Log** and §11 **Change History** live in companion files
(`docs/requirements_issue_log.md`, `docs/requirements_change_history.md`) to keep the spec small; the
SRS keeps a one-line stub pointing to each. Both are historical/append-only — you rarely need to read
them, and they are excluded from the generated views.
`Workflows/` holds repo-specific multi-agent workflow definitions (`requirements-check`,
`code-requirements-align`, `defect-investigator`, `test-quality-checker`) for checking code and tests
against the SRS, plus `context-budget-audit` (run occasionally to confirm docs/source stay optimized
for small-LLM context windows).

**Requirement views (`docs/requirements_views/`) — consult first to save context.** The full SRS is
large; you rarely need it whole. Two generated, read-only views (from
`tools/traceability_sync/generate_views.py`, derived from the SRS **and** the architecture companion
plus code `Satisfies:` tags — the index covers every `FR-`/`UIR-`/`DR-`/`CR-`/`NFR-` requirement from
both files):
- `requirements_index.md` — terse one-line-per-requirement summary (~13K tokens); use for **broad**
  understanding.
- `code_to_requirements.md` (+ `.json`) — source file → requirement IDs it implements (from code
  `Satisfies:` tags); use for **targeted** work (look up the file you're editing, read just those IDs).
- `requirements_to_tests.md` (+ `.json`) — requirement ID → the test(s) that verify it (from test
  `Verifies:` tags), plus an **Untested requirements** list and a **Stale tags** list; use to check
  test coverage of a requirement. (Many `UIR-`/`FR-` GUI requirements are verified by
  `docs/manual_test_plan.md` rather than unit tests — expected, not a gap.)
The SRS (plus `docs/cpm_fm_architecture.md` for `CR-`/`NFR-` architecture) stays the single source of
truth and the only requirements files edited by hand. **Never edit the views** — regenerate them
(step 3a).

## Requirement-change workflow (MANDATORY)

Whenever you are asked to **add or change a requirement**, perform all of these steps in order — do
not stop short:

1. **Update the requirements** in `docs/cpm_fm_requirements.md` (add/modify the `FR-`/`UIR-`/`DR-`/
   `CR-`/`NFR-` entry). Architectural constraints — module structure/toolkit/layering (CR-001–009,
   CR-012–014) and the concurrency/extensibility NFRs (NFR-001, NFR-004, NFR-005) — live in
   `docs/cpm_fm_architecture.md` instead; edit them there.
2. **Implement the changes.** In every new or changed function, update the docstring with a
   `Satisfies:` tag citing the relevant requirement ID(s).
3. **Update the requirements** with the traceability mapping to the new and changed functions.
3a. **Regenerate the views** — run `python tools/traceability_sync/generate_views.py` and commit
   `docs/requirements_views/` (see "Requirement views" above; never hand-edit them). The views derive
   from the specs, code `Satisfies:` tags, **and** test `Verifies:` tags.
4. **Add or update the tests** for the new/changed behaviour, and tag each test function's docstring
   with a `Verifies:` line citing the requirement ID(s) it exercises (the test-suite counterpart of
   `Satisfies:`). Then **run the unit tests** (`pytest`). Check coverage with
   `python tools/traceability_sync/agent_toolset.py --coverage` — it lists requirements with no
   verifying test and any stale `Verifies:` tags.
4a. **Update the integration (HIL) test suite** (`integration/`) when the change touches behaviour it
   exercises — the X-Modem protocol round-trips, the GUI-over-real-serial flows (connect/disconnect,
   listing, drive change, conflict, filename validation, drag-and-drop, transfer history, terminal
   window, remote context-menu actions, backup/restore), or the widget-tree look-and-feel assertions.
   Add or adjust the relevant `integration/test_*.py` case(s), keep each test's
   `@pytest.mark.mt("MT-..", "FR-..")` MT-ID/requirement tags accurate, and update
   `integration/README.md` if the manual-vs-automated split changes. The HIL suite needs a real CP/M
   peer, so it is **not** part of the default `pytest` run or CI — verify it with a bench run
   (`pytest integration/`, plus `--run-destructive` for the backup/restore cases) when hardware is
   available, and record the outcome. If hardware is not at hand, state in the step-8 summary that the
   integration update is written but its bench run is pending. If the change touches no HIL-covered
   behaviour (e.g. a pure architecture `CR-`/`NFR-` constraint with no protocol/GUI effect), state
   explicitly that no integration-suite change was needed — never skip the step silently.
5. **Iterate steps 2–4** until all unit tests pass and the trace is clean (no stale tags;
   `generate_views.py --check` green).
6. **Update the manual test plan** (`docs/manual_test_plan.md`) and increment its test plan version.
7. **Update the manual test scorecard** (`docs/manual_test_scorecard.md`) to match the test plan and
   increment its score version.
7a. **Record the change** — bump `src/version.txt`, the SRS version field (DR-040/DR-041), and the
   `**Version X.Y.Z**` line at the top of the user manual (`src/cpm_fm/docs/cpm_fm_manual.md`) so all
   three stay locked together, and add a row to **`docs/requirements_change_history.md`** (the §11
   companion file — *not* the SRS itself). When a requirements review resolves an ambiguity or gap, add
   the OI entry to **`docs/requirements_issue_log.md`** (the §10 companion file).
7b. **Update the user manual** (`src/cpm_fm/docs/cpm_fm_manual.md`) **when the change alters
   user-visible behaviour** — revise the affected section(s), the Table of Contents, and the
   **Reference: Default Settings** table so the manual matches the new behaviour (this is the end-user
   manual, distinct from the `docs/manual_test_plan.md` updated in step 6). If the change is
   architecture-only (a `CR-`/`NFR-` constraint with no user-visible effect), state explicitly in the
   step-8 summary that no manual content change was needed — never skip the step silently.
8. **Provide a summary** of the actions taken.
