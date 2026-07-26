# Developer Guideline

## Developer Workflow

This section is the single source of truth for building, testing, and — most
importantly — keeping the **requirements, code, tests, and documentation in sync**.
The project is requirements-driven: every behaviour traces to an identified
requirement, and that trace is mechanically enforced (a stale trace fails CI).

### One-time environment setup

```bash
.venv/Scripts/python.exe -m pip install -e .[dev]
.venv/Scripts/python.exe -m pre_commit install
```

The pre-commit hooks ([`.pre-commit-config.yaml`](../.pre-commit-config.yaml)) mirror the
CI lint and trace-freshness gates so drift is caught before a push rather than failing
CI. They reuse the tools installed by `.[dev]`, so the hook versions always match the
project's pins. Run them by hand at any time with:

```bash
.venv/Scripts/python.exe -m pre_commit run --all-files
```

### Build, test, and the quality gate

The inner development loop uses the following quality gates. CI runs all of them on Python 3.12
([`.github/workflows/ci.yml`](../.github/workflows/ci.yml)); the pre-commit hooks run the
lint and trace-freshness checks locally.

```bash
.venv/Scripts/python.exe -m pytest
.venv/Scripts/python.exe -m ruff check src tests
.venv/Scripts/python.exe -m ruff format --check src tests
.venv/Scripts/python.exe -m mypy src
.venv/Scripts/python.exe tools/traceability_sync/generate_views.py --check
.venv/Scripts/python.exe tools/ai/validate.py
```

Useful narrower invocations:

```bash
.venv/Scripts/python.exe -m pytest tests/test_cpm_parser.py
.venv/Scripts/python.exe -m pytest tests/test_cpm_parser.py::test_parse_dir_output_extracts_filenames
.venv/Scripts/python.exe -m ruff format --check src tests
```

Invoke `.venv/Scripts/python.exe` directly rather than relying on activation or
`PATH`. For building a redistributable executable, see
[Building a standalone package](#building-a-standalone-package).

#### Integration (hardware-in-the-loop) suite

The [`integration/`](../integration/) suite drives the **real** app against a **real CP/M
machine** over serial — X-Modem protocol round-trips, the GUI over real serial, and
widget-tree look-and-feel assertions. It is **bench-only**: not run by CI or the default
`pytest` (the root run's `testpaths` is `tests/`), and it needs a configured target
(`integration/hil_config.json`, gitignored). Run it explicitly when hardware is connected:

```bash
.venv/Scripts/python.exe -m pytest integration/
.venv/Scripts/python.exe -m pytest integration/ --run-destructive
.venv/Scripts/python.exe integration/run.py
```

See [`integration/README.md`](../integration/README.md) for wiring, target setup, and the
manual-vs-automated split. It is additive test infrastructure and defines no requirements.

### Keeping requirements, code, tests, and docs in sync

The authoritative documents are:

- [`docs/cpm_fm_requirements.md`](cpm_fm_requirements.md) — the **Software
  Requirements Specification** (ISO/IEC/IEEE 29148), source of truth for most
  requirements (`FR-`/`UIR-`/`DR-`/`STR-` and the behavioural `CR-`/`NFR-` plus the
  X-Modem `NFR-003*`).
- [`docs/cpm_fm_architecture.md`](cpm_fm_architecture.md) — the **Software
  Architecture Description**, source of truth for the architectural constraints
  (`CR-001`–`CR-009`, `CR-012`–`CR-014`) and architectural NFRs (`NFR-001`, `NFR-004`,
  `NFR-005`). Edit these `CR-`/`NFR-` requirements here, not in the SRS.

Traceability is bidirectional and tag-based: each implementing function carries a
`Satisfies:` docstring tag citing requirement IDs, and each test carries a `Verifies:`
tag. The read-only views under [`docs/requirements_views/`](requirements_views/) are
**generated** from the two specs plus those tags by
[`tools/traceability_sync/generate_views.py`](../tools/traceability_sync/generate_views.py)
— never hand-edit them.

**When you add or change a requirement, follow every step in order** (this is the
mandatory workflow; see [`AGENTS.md`](../AGENTS.md) for the agent-facing version):

1. **Edit the spec.** Add/modify the requirement in `docs/cpm_fm_requirements.md` — or,
   for an architectural `CR-`/`NFR-` constraint, in `docs/cpm_fm_architecture.md`.
2. **Implement the change.** In every new/changed function, add or update a `Satisfies:`
   docstring tag citing the requirement ID(s).
3. **Update the spec's traceability** mapping to the new/changed functions, then
   **regenerate the views**: `.venv/Scripts/python.exe tools/traceability_sync/generate_views.py` and
   commit `docs/requirements_views/`.
4. **Add/update tests** for the new behaviour, tagging each test docstring with a
   `Verifies:` line citing the requirement ID(s). Run
   `.venv/Scripts/python.exe -m pytest`, then check coverage:
   `.venv/Scripts/python.exe tools/traceability_sync/agent_toolset.py --coverage` (lists requirements with
   no verifying test and any stale tags).
5. **Update the integration (HIL) suite** ([`integration/`](../integration/)) when the change
   touches behaviour it covers — the X-Modem protocol round-trips, the GUI-over-real-serial
   flows, or the widget-tree look-and-feel. Add/adjust the relevant `integration/test_*.py`
   with accurate `@pytest.mark.mt("MT-..", "FR-..")` tags and verify with a bench run
   (`.venv/Scripts/python.exe -m pytest integration/`; add `--run-destructive` for backup/restore) when hardware is
   available, or note that the bench run is pending. The HIL suite needs a real CP/M peer,
   so it is **not** run by CI or the default `pytest`; state explicitly when no integration
   change is needed rather than skipping it.
6. **Iterate steps 2–4** until the suite is green and the trace is clean
   (`generate_views.py --check` exits 0, no stale tags).
7. **Update the manual test plan** ([`docs/manual_test_plan.md`](manual_test_plan.md))
   and bump its plan version.
8. **Update the manual test scorecard**
   ([`docs/manual_test_scorecard.md`](manual_test_scorecard.md)) to match, bumping
   its score version.
9. **Record the change:** bump [`src/version.txt`](../src/version.txt) and the SRS version
   field (DR-040/DR-041), add a row to
   [`docs/requirements_change_history.md`](requirements_change_history.md), and — if
   a review resolved an ambiguity or gap — an entry in
   [`docs/requirements_issue_log.md`](requirements_issue_log.md).

> The `agent_toolset.py` helper can also rewrite the spec's `Source:` cells to match the
> code's `Satisfies:` tags. It is report-only by default; preview with `--dry-run`, then
> write with `--apply`.

#### Requirement-change workflow

```mermaid
flowchart TD
    A[Requirement added or changed] --> B{Architectural<br/>CR-/NFR- constraint?}
    B -- Yes --> C[Edit docs/cpm_fm_architecture.md]
    B -- No --> D[Edit docs/cpm_fm_requirements.md]
    C --> E[Implement code +<br/>add Satisfies: tags]
    D --> E
    E --> F[Update spec traceability<br/>+ regenerate views]
    F --> G[Add/update tests<br/>+ add Verifies: tags]
    G --> H[pytest + agent_toolset.py --coverage]
    H --> I{Suite green &<br/>trace clean?}
    I -- No --> E
    I -- Yes --> IT[Update integration/ HIL tests<br/>if HIL-covered + bench run<br/>pytest integration/]
    IT --> J[Update manual test plan<br/>+ scorecard]
    J --> K[Bump version + SRS field<br/>+ change history / issue log]
    K --> L[Commit]
```

#### Local quality gate

Run before every push; the pre-commit hooks and CI enforce the same checks.

```mermaid
flowchart LR
    A[Edit] --> B[ruff check src tests]
    B --> C[ruff format --check src tests]
    C --> D[generate_views.py --check]
    D --> E[validate AI assets]
    E --> F[pytest]
    F --> G{All pass?}
    G -- No --> A
    G -- Yes --> H[Commit / push]
```

#### How the traceability views are produced

```mermaid
flowchart LR
    SRS[docs/cpm_fm_requirements.md] --> GEN[generate_views.py]
    ARCH[docs/cpm_fm_architecture.md] --> GEN
    CODE["src/**.py<br/>Satisfies: tags"] --> GEN
    TESTS["tests/**.py<br/>Verifies: tags"] --> GEN
    GEN --> IDX[requirements_index.md]
    GEN --> C2R[code_to_requirements.md / .json]
    GEN --> R2T[requirements_to_tests.md / .json]
```

> **More diagrams:** the X-Modem protocol requirements (`NFR-003*`) are already
> illustrated with sequence diagrams (128-byte and 1K transfers) in
> [`docs/xmodem_specs.md`](xmodem_specs.md), and the runtime layering
> (`gui/` → `terminal/` + `utils/`) — showing the `CR-014` rule that `terminal/` and
> `utils/` import no GUI toolkit, plus the signal-based threading/decoupling model — is
> diagrammed in [`docs/cpm_fm_architecture.md`](cpm_fm_architecture.md) §A2.

## Developer Workflow (AI Assisted)

>## Personal note on the use of AI
>This project has been an exercise in how to incorporate AI into my home project workflow.
>It uses AI to write the Python code and to maintain the documentation, requirements,
>testing etc. My input is in the architecture, the requirements specification and the
>integration/manual testing.
>
>I appreciate and respect that some people have an adverse view of AI. I also respect
>your decision to not use this project based on that viewpoint. There was a time when
>I also felt the same way. I have since come to the conclusion that there are ways in
>which AI can be used that doesn't generate slop and unmaintainable code, and this project
>has helped me determine how to do that.
>
>I have forced the AI to follow strict guidelines on how it produces the code, and to
>keep the requirements and documentation in step with the code base. My belief is that
>the quality of an application is not just in the code, but in having clear, unambiguous
>requirements and architecture. The theory is that the requirements in this project
>are detailed enough for the app to be re-written without AI or using AI to re-write
>the app in a different language entirely.
>
>We the humans, supply the creativity, the decision making, and the soul of an application
>that AI is just not capable of doing. AI is just a tool, no more, no less. It can't
>think, it can't reason like a human, but it is good at performing repetitive,
>boring tasks, and is good at tracking down bugs and issues. It is not perfect, it
>also makes mistakes and does require review of its work.
>
>If you want to learn how to make the AI follow instructions and give repeatable output,
>then this project may help to give you some ideas on how I tackled these issues. There
>are probably better ways of doing this, however this is the way that seems to work for
>me.
>
>Enjoy!

The repository is set up so AI coding assistants can do real work without loading the
whole (large) SRS into context, and so their changes stay traceable. The same build and
test commands from [Developer Workflow](#build-test-and-the-quality-gate) apply — the
assistant runs the same pytest, traceability, Ruff, and mypy commands as a
human would; what differs is the context the tool is given and how the repo workflows are
invoked.

### What the AI reads

- [`AGENTS.md`](../AGENTS.md) — the agent-facing project guide: commands, the architecture
  summary, the threading rules, and the mandatory requirement-change workflow.
- [`.agents/`](../.agents/) — the vendor-neutral catalog of specialized agent
  profiles, open-format Agent Skills, and project workflows.
- [`docs/requirements_views/`](requirements_views/) — the slim, generated views the
  guidance points the AI at: `requirements_index.md` for broad understanding,
  `code_to_requirements.md` to find the IDs a file implements, and
  `requirements_to_tests.md` to check a requirement's test coverage.

> Everything an AI needs lives in `AGENTS.md`, `.agents/`, and the generated
> views. This guide is for humans and is **not** a mandatory context source
> for the AI tools; the AI-facing docs deliberately do not reference it.

### AI development tools

All development assistants use the same repository rules; only their loading mechanisms and tool
vocabulary differ:

| Aspect | Project convention |
|--------|--------------------|
| Authoritative project guide | [`AGENTS.md`](../AGENTS.md) |
| Canonical AI assets | [`.agents/`](../.agents/) contains agents, skills, workflows, and their catalog. |
| Tool-specific adapters | Directories such as [`.codex/`](../.codex/) may provide loading hints only; they never override `AGENTS.md` or `.agents/`. |
| Permissions and tool vocabulary | Supplied by the active development environment rather than defined as project requirements. |

The split is deliberate: agents define who performs work, skills provide
reusable expertise, and workflows define ordered project procedures and gates.
The `context-budget-audit` workflow checks that these layers point to the
authoritative guidance instead of duplicating it.

AI-asset and adapter-only changes are developer tooling changes; they do not
bump the application or SRS version unless application requirements or behavior
also change.

### The repo workflows

[`.agents/workflows/`](../.agents/workflows/) holds eight project workflows:

| Workflow | Use it to… |
|----------|-----------|
| [`requirements-change`](../.agents/workflows/requirements-change.md) | Review or edit requirements; the front door for any specification change. |
| [`code-requirements-align`](../.agents/workflows/code-requirements-align.md) | Audit two-way implementation and verification traceability. |
| [`defect-investigation`](../.agents/workflows/defect-investigation.md) | Reproduce, test, root-cause, fix, and verify a defect. |
| [`test-case-implementation`](../.agents/workflows/test-case-implementation.md) | Implement and prove multiple tests one at a time. |
| [`test-quality-audit`](../.agents/workflows/test-quality-audit.md) | Adversarially audit test quality and missing boundaries. |
| [`context-budget-audit`](../.agents/workflows/context-budget-audit.md) | Check AI-facing context size and stale references. |
| [`pre-commit-checks`](../.agents/workflows/pre-commit-checks.md) | Run the local lint, format, and view-freshness gate. |
| [`handoff`](../.agents/workflows/handoff.md) | Record concise session state for a fresh agent. |

### The AI-assisted loop

```mermaid
flowchart TD
    A[Developer states task] --> B[AI loads AGENTS.md<br/>+ relevant .agents asset]
    B --> C{Task type?}
    C -- Spec change --> D[requirements-change workflow]
    C -- Trace audit --> E[code-requirements-align workflow]
    C -- Defect --> F[defect-investigation workflow]
    C -- Test quality --> G[test-quality-audit workflow]
    D --> H[AI reports findings + plan]
    E --> H
    F --> I[AI implements + runs project quality gates]
    G --> H
    H --> J{Developer approves?}
    J -- No --> A
    J -- Yes --> I
    I --> K[Developer reviews diff]
    K --> L{Quality gate green?}
    L -- No --> I
    L -- Yes --> M[Commit]
```

#### Choosing a workflow

```mermaid
flowchart TD
    Q[What do you need?] --> A{Changing a<br/>requirement?}
    A -- Yes --> R[requirements-change]
    A -- No --> B{Code and spec<br/>out of sync?}
    B -- Yes --> C[code-requirements-align]
    B -- No --> D{Investigating<br/>a bug?}
    D -- Yes --> E[defect-investigation]
    D -- No --> F{Worried about<br/>test quality?}
    F -- Yes --> G[test-quality-audit]
    F -- No --> H{Docs/source<br/>getting bloated?}
    H -- Yes --> I[context-budget-audit]
    H -- No --> J[Use the manual workflow directly]
```

#### A `code-requirements-align` run

```mermaid
sequenceDiagram
    participant Dev as Developer
    participant AI as AI assistant
    participant Tool as traceability_sync
    participant Repo as Code / Spec / Tests
    Dev->>AI: Run code-requirements-align
    AI->>Tool: generate_views.py --check / agent_toolset.py --coverage
    Tool-->>AI: Mechanical tag-level trace
    AI->>Repo: Read code vs "shall" wording (semantic check)
    AI-->>Dev: Findings table + implementation plan
    Dev->>AI: Approve (all or part)
    AI->>Repo: Apply approved changes
    AI->>Tool: Re-run --check + --coverage (verify clean)
    AI-->>Dev: Summary
```

## Building a standalone package

Standalone executables are built with [PyInstaller](https://pyinstaller.org/):

```bash
.venv/Scripts/python.exe -m pip install -e .[build]
.venv/Scripts/python.exe build_dist.py
```

Output lands in `dist/`: a single `cpm-fm.exe` on Windows, a single `cpm-fm`
binary on Linux, and `cpm-fm.app` on macOS.

PyInstaller **cannot cross-compile** — each package must be built on its own OS.
`build_dist.py` auto-selects the matching spec (`pyinstaller_windows.spec`,
`pyinstaller_linux.spec`, `pyinstaller_macos.spec`; shared settings live in
`_pyinstaller_common.py`). To produce all three, run it once on each platform —
the docstring at the bottom of `build_dist.py` includes a ready-to-use GitHub
Actions matrix that does exactly that. Optional app icons: drop
`assets/icon.ico` / `assets/icon.icns` / `assets/icon.png` into the repo.

## Project layout

```
src/cpm_fm/          application package (src-layout)
  app.py             MainWindow + main() entry point
  version.py         version/identity constants (reads src/version.txt)
  gui/               PySide6 dialogs, terminal window, theme, window-state persistence
  terminal/          serial manager, CP/M DIR parser, X-Modem protocol
  utils/             JSON config handling and runtime internationalisation (i18n)
  lang/              per-language UI string files (lang_<language>.txt)
  icons/             runtime window icon
  docs/              bundled user manual (cpm_fm_manual.md), shown by Help > Manual
tests/               pytest suite (each test tagged with Verifies: requirement IDs)
integration/         bench-only hardware-in-the-loop (HIL) suite, separate from tests/;
                     run with `.venv/Scripts/python.exe -m pytest integration/`
  helpers/           peer + GUI drivers, config/settings-copy/integrity/dialogs/results
  test_*.py          protocol, GUI, and visual tiers (tagged with MT-IDs + requirement IDs)
  run.py             interactive target picker
  hil_config.example.json  target-config template (real hil_config.json is gitignored)
  README.md          wiring, target setup, safety, and the manual-vs-automated split
examples/            sample serial/general settings JSON
tools/               developer tooling, incl. traceability_sync/ (view generator,
                     coverage/trace helper)
.agents/             vendor-neutral agents, open-format skills, workflows, and catalog
docs/                requirements (SRS) + architecture description, generated requirement
                     views, manual test plan/scorecard, change history, issue log, and
                     legacy design docs
AGENTS.md            agent-facing project guide
.codex/              optional Codex loading adapter
build_dist.py        PyInstaller driver; pyinstaller_*.spec + _pyinstaller_common.py
```

`docs/cpm_fm_requirements.md` (the SRS) and `docs/cpm_fm_architecture.md` (the
architecture description) are the authoritative, traceable specifications; everything
under `docs/requirements_views/` is generated from them. See
[Developer Workflow](#keeping-requirements-code-tests-and-docs-in-sync) for how they fit
together.
