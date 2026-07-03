---
description: Session-handoff generator — writes a concise summary of the current conversation to temp/ so a fresh agent can continue the work, linking to existing artifacts instead of duplicating them
---

# Handoff Workflow

This workflow captures the **current conversation** as a handoff document so a new,
context-free agent can pick up the work with minimal re-derivation. It summarises
what happened, what remains, and where to look — **without duplicating content that
already lives in other artifacts** (SRS, architecture doc, commits, plans in
`temp/`, memory, test results). Where such material exists, the handoff **links or
references** it rather than restating it.

## Invocation

Invoke on the conversation you want to hand off. Two optional inputs:

- **Arguments** — if the user passes any arguments, treat them as a **description
  of what the next session should focus on**. Put them verbatim (lightly tidied)
  into the handoff's "Focus for next session" section, and let them shape which
  loose ends you emphasise.
- **Name** — if the user specifies a name for the handoff (e.g. "call it
  `vt100-merge`"), use it for the filename: `temp/<name>.md`. Otherwise use the
  default name below.

## Output location & naming

- Write to the project **`temp/`** folder (gitignored — matches the repo's existing
  `session-summary-*.md` / plan-doc practice).
- **Default filename:** `temp/handoff-<DATE>-<TIME>.md` where `<DATE>` is
  `YYYY-MM-DD` and `<TIME>` is `HHMMSS` (24-hour, local), e.g.
  `temp/handoff-2026-07-04-143205.md`.
- **If the user supplied a name:** `temp/<name>.md` (add the `.md` extension if the
  user omitted it). Do not overwrite an existing file — if it exists, append
  `-<TIME>` to disambiguate.
- Get the real date/time from the system (e.g. `date +%Y-%m-%d-%H%M%S`); never
  guess or hard-code it.

## Core principle: reference, don't duplicate

Before writing any section, ask "is this already recorded somewhere durable?" If so,
**link to it** and summarise in one line — do not copy its content. Typical
artifacts already in this repo to reference rather than restate:

- **Requirements** — cite requirement IDs (`FR-`/`UIR-`/`DR-`/`CR-`/`NFR-`) and
  point to `docs/cpm_fm_requirements.md` / `docs/cpm_fm_architecture.md`; do not
  paraphrase requirement text.
- **Plans / prior summaries** — link the relevant `temp/*.md` (e.g. an approved
  plan) instead of re-explaining the plan.
- **Committed work** — reference commit hashes / branch (`git log --oneline`)
  rather than describing code that is already committed.
- **Views & coverage** — point to `docs/requirements_views/` and the traceability
  tooling instead of listing mappings.
- **Test results** — link `integration/results/.../report.md` rather than pasting
  outcomes.
- **Memory** — if a fact is already in auto-memory, reference it; don't restate.

The handoff's value is the **connective tissue and the not-yet-recorded state**:
what was decided this session, what is half-done, what to do next, and where
everything lives.

## Procedure

1. **Establish the moment.** Get the current date/time (for the filename) and the
   git state — `git rev-parse --abbrev-ref HEAD`, `git status -sb`,
   `git log --oneline -8` — so the handoff records branch, uncommitted work, and
   push/merge status accurately.
2. **Review the conversation** from the start: identify the goal, what was actually
   done, decisions made (and alternatives rejected), and what is still open.
3. **Inventory existing artifacts** touched or relevant (requirements, plans,
   commits, tests, memory). These become links, not prose.
4. **Fold in the arguments**, if any, as the explicit focus for the next session.
5. **Write the document** using the structure below. Keep it tight — a fresh agent
   should be able to read it in a couple of minutes and know exactly where to start.
6. **Report** the file path and a one-line summary back to the user.

## Document structure

```markdown
# Handoff — <short task title> (<DATE> <TIME>)

> Resume protocol: read `AGENTS.md` first (repo rule), then this handoff.

## Focus for next session
<the user's arguments verbatim if provided; otherwise the most important next thread>

## Context in one paragraph
<what this work is and why — 2-4 sentences, no duplication of requirement text>

## Git state
- Branch / push / merge status; uncommitted files (from `git status -sb`)
- Relevant commits: `<hash> <subject>` (reference, don't describe the diff)

## What was done this session
<bullet list of concrete outcomes; link to commits/artifacts rather than restating them>

## Decisions made
<choices locked in and alternatives rejected — the part not recorded elsewhere>

## Open / next steps
<ordered, concrete next actions; the single most important one first>

## References (don't re-read unless needed)
- Requirements: <IDs + file>
- Plans / prior summaries: <temp/*.md links>
- Tests / results: <paths>
- Memory: <relevant memory names>

## Blockers / open questions
<anything preventing progress, or decisions the user still owes>
```

Omit a section only if it is genuinely empty — write "none" rather than deleting
the heading, so the reader knows it was considered.

## Notes

- **Never bypass the `.venv` interpreter rule** if you run any Python tooling while
  gathering state (`.venv/Scripts/python.exe -m ...`).
- The handoff is **generic** — it does not itself follow the requirement-change
  workflow (it changes no requirement, code, or version). It only records state.
- Keep it short. If the handoff starts restating a plan or requirement in full,
  stop and replace that block with a link.
- `temp/` is gitignored by design; the handoff is a working note, not a tracked
  deliverable. If a tracked handoff is ever wanted, the user must say so.

## Integration with other workflows

| Workflow | Relationship |
|----------|-------------|
| `pre-commit-checks` | Run before handing off if the session left committable changes, so the next agent inherits a clean tree |
| `requirements-check` / `code-requirements-align` | If the session changed requirements, reference the resulting SRS/view state rather than re-summarising it in the handoff. This step is optional and user approval must be given before executing these workflows. |
