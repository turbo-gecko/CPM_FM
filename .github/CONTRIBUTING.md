# Contributing to CP/M File Manager (`cpm-fm`)

First off — thank you for taking the time to contribute! `cpm-fm` is a
cross-platform [PySide6](https://doc.qt.io/qtforpython/) desktop app for
transferring files between a modern host and legacy
[CP/M](https://en.wikipedia.org/wiki/CP/M) systems over a serial link using the
X-Modem protocol. Contributions of all kinds are welcome: bug reports, feature
ideas, documentation fixes, translations, and code.

This project is released under the [Apache License 2.0](../LICENSE). By
contributing, you agree that your contributions will be licensed under the same
license.

Please also read and follow our [Code of Conduct](CODE_OF_CONDUCT.md).

## Table of contents

- [Ways to contribute](#ways-to-contribute)
- [Reporting bugs](#reporting-bugs)
- [Suggesting features](#suggesting-features)
- [Development setup](#development-setup)
- [Project layout](#project-layout)
- [The requirement-change workflow (important)](#the-requirement-change-workflow-important)
- [Coding standards](#coding-standards)
- [Testing](#testing)
- [Commit messages and pull requests](#commit-messages-and-pull-requests)
- [Versioning](#versioning)
- [Translations](#translations)
- [Security issues](#security-issues)

## Ways to contribute

- **Report a bug** or **request a feature** through our
  [issue templates](https://github.com/turbo-gecko/CPM_FM/issues/new/choose).
- **Improve documentation** — the README, the in-app user manual
  (`src/cpm_fm/docs/cpm_fm_manual.md`), or these community docs.
- **Add or improve a translation** — the UI ships in 12 languages (see
  [Translations](#translations)).
- **Fix a bug or build a feature** — see the workflow below before you start.

If you are unsure whether an idea fits the project, open an issue to discuss it
first. For general questions, please use
[GitHub Discussions](https://github.com/turbo-gecko/CPM_FM/discussions) rather
than the issue tracker.

## Reporting bugs

Use the **Bug report** or **Hardware / serial report** issue template. A good
report includes:

- The `cpm-fm` version (Help → About, or `src/version.txt`) and your OS.
- Clear steps to reproduce, what you expected, and what actually happened.
- For serial/transfer problems: the serial adapter, baud rate, cable, and the
  target CP/M system (the **Hardware / serial report** template prompts for
  these). Console output helps — launch with
  `.venv/Scripts/python.exe -m cpm_fm` to keep a console where serial errors are
  printed.

Please search existing issues first to avoid duplicates.

## Suggesting features

Use the **Feature request** template. Because this project maintains a formal
requirements specification (see below), new features become new or changed
requirements — describe the *behaviour* and *why* it matters, and a maintainer
will help map it into the spec.

## Development setup

The project's Python interpreter lives in **`.venv/`**.

> **MANDATORY: use the `.venv` interpreter for every Python command.** Run
> `python`, `pip`, `pytest`, `mypy`, and `ruff` as
> `.venv/Scripts/python.exe -m <tool> …` — never the bare command. This keeps
> everyone on the same interpreter and matches CI.

Install in editable mode with the dev tools:

```bash
.venv/Scripts/python.exe -m pip install -e .[dev]
```

Run the app:

- `cpm-fm` — installed GUI launcher (no console window on Windows), or
- `.venv/Scripts/python.exe -m cpm_fm` — keeps a console for `print()`/serial
  debug output.

Requires **Python 3.9+** (CI runs on 3.12).

## Project layout

`src/`-layout package under `src/cpm_fm/`. Three layers are intentionally
decoupled from the GUI so they are unit-testable without a running Qt app:

- `terminal/` — serial management, hand-rolled X-Modem, and the `DIR`-output
  parser.
- `utils/` — config handling, i18n, file filtering, transfer history,
  disk-image support.
- `gui/` — Qt-only widgets and dialogs.

`app.py:MainWindow` is the hub that owns the components and wires UI events.

**Read [`AGENTS.md`](../AGENTS.md) and
[`docs/cpm_fm_architecture.md`](../docs/cpm_fm_architecture.md) before making
non-trivial changes.** Two rules are load-bearing:

- **No GUI-toolkit imports in `terminal/` or `utils/`** (constraint CR-014).
- **The threading model (NFR-001/NFR-004):** serial reads and both transfer
  directions run off the Qt GUI thread on daemon threads. Any UI update from a
  worker thread **must** be marshalled onto the GUI thread by emitting a Qt
  signal — never touch a widget directly from a worker thread.

## The requirement-change workflow (important)

`cpm-fm` is developed against an ISO/IEC/IEEE 29148 **Software Requirements
Specification** (`docs/cpm_fm_requirements.md`) with uniquely identified,
traceable requirements (`FR-`/`UIR-`/`DR-`/`CR-`/`NFR-`). If your change
**adds or changes a requirement** (most features and behavioural fixes do),
please follow this workflow — it keeps the spec, code, tests, and docs in sync:

1. **Update the requirements** in `docs/cpm_fm_requirements.md`
   (architectural `CR-`/`NFR-` constraints live in
   `docs/cpm_fm_architecture.md`).
2. **Implement the change**, tagging each new/changed function's docstring with
   a `Satisfies:` line citing the requirement ID(s).
3. **Add the traceability mapping**, then **regenerate the requirement views**:
   `.venv/Scripts/python.exe tools/traceability_sync/generate_views.py`
   (never hand-edit `docs/requirements_views/`).
4. **Add or update tests**, tagging each test's docstring with a `Verifies:`
   line citing the requirement ID(s), and run the suite (see
   [Testing](#testing)). Check coverage with
   `.venv/Scripts/python.exe tools/traceability_sync/agent_toolset.py --coverage`.
5. **Iterate** until tests pass and the trace is clean
   (`generate_views.py --check` is green — CI enforces this).
6. **Update the manual test plan** (`docs/manual_test_plan.md`) and its version.
7. **Update the manual test scorecard** (`docs/manual_test_scorecard.md`).
8. **Record the change**: bump `src/version.txt`, the SRS version field, and the
   user manual version so all three match; add a row to
   `docs/requirements_change_history.md`. Update the user manual
   (`src/cpm_fm/docs/cpm_fm_manual.md`) when user-visible behaviour changes.

For small, non-behavioural changes (typos, refactors, comments) you don't need
the full workflow — but do run the linters and tests. If in doubt, ask in the
issue or PR.

## Coding standards

- **Formatting & linting:** [`ruff`](https://docs.astral.sh/ruff/) (line length
  100). Format with `.venv/Scripts/python.exe -m ruff format src tests` and lint
  with `.venv/Scripts/python.exe -m ruff check src tests`. CI runs both in
  `--check` mode.
- **Types:** [`mypy`](https://mypy-lang.org/) —
  `.venv/Scripts/python.exe -m mypy src`.
- **Pre-commit:** a `.pre-commit-config.yaml` is provided. Install the hooks
  with `.venv/Scripts/python.exe -m pre_commit install` so formatting, lint, and
  the view-sync check run automatically.
- **No hard-coded UI strings** — user-facing text goes through the `tr(key)`
  translation layer (`utils/i18n.py`) with entries in `lang/lang_<language>.txt`.
- Match the style, naming, and comment density of the surrounding code.

## Testing

- **Unit suite:** `.venv/Scripts/python.exe -m pytest` (config in
  `pyproject.toml`; `testpaths = ["tests"]`). This is what CI runs and what your
  PR must pass.
- **Single test:**
  `.venv/Scripts/python.exe -m pytest tests/test_cpm_parser.py::test_parse_dir_output_extracts_filenames`.
- **Integration (hardware-in-the-loop) suite:** `integration/` drives the real
  app against a real CP/M machine over serial. It is **bench-only** — not run by
  CI or the default `pytest`. If your change touches protocol or GUI-over-serial
  behaviour, update the relevant `integration/test_*.py` cases and their
  `@pytest.mark.mt(...)` tags. Run it on hardware when you can
  (`.venv/Scripts/python.exe -m pytest integration/`, add `--run-destructive`
  for backup/restore cases); if you can't, say so in the PR. See
  `integration/README.md`.

Please add tests for new behaviour and keep the existing suite green.

## Commit messages and pull requests

- Branch off `main`; keep each PR focused on a single change.
- Write clear commit messages: a concise summary line, then a body explaining
  *what* and *why* when it isn't obvious.
- Reference the issue you're addressing (e.g. `Fixes #123`) and relevant
  requirement IDs (e.g. `FR-170`) where applicable.
- Fill out the [pull request template](PULL_REQUEST_TEMPLATE.md), including the
  checklist.
- Ensure `ruff`, `mypy`, `pytest`, and `generate_views.py --check` all pass
  locally before requesting review — CI runs the same checks.

## Versioning

The project uses **semantic versioning** (`MAJOR.MINOR.PATCH`):

- **PATCH** (third digit) — a bug fix or minor correction (e.g. `2.36.0` →
  `2.36.1`). Recorded only in `docs/requirements_change_history.md`.
- **MINOR** (second digit, resets PATCH to 0) — a genuinely new feature or
  substantive requirement addition.
- **MAJOR** (first digit) — a breaking or architectural change.

Keep `src/version.txt`, the SRS version field, and the user-manual version line
locked together.

## Translations

The UI ships in 12 languages. Strings live in
`src/cpm_fm/lang/lang_<language>.txt`, with **English as the reference and
fallback**. To add or fix a translation, copy the English file's keys and
translate the values — don't remove or rename keys. New user-facing strings must
be added to the English file (and ideally the others) rather than hard-coded.

## Security issues

**Do not report security vulnerabilities through public GitHub issues.** See our
[Security Policy](SECURITY.md) for how to report privately.

---

Thanks again for contributing! If anything here is unclear, open a
[discussion](https://github.com/turbo-gecko/CPM_FM/discussions) or ask in your
issue/PR.
