---
description: Compares requirements to the codebase to find orphan code, unimplemented requirements, and incorrect implementations, then reports findings and plans fixes (with explicit user approval before any change)
---

# Code / Requirements Alignment Workflow

This workflow performs a two-way traceability audit between the requirements
specification and the implementation. It surfaces three classes of misalignment,
reports them to the user as a findings table, and produces an implementation plan.
**It never modifies code automatically — explicit user permission is required
before any change is applied.**

## Step 1: Locate and Read the Requirements

- Find the requirements specification (e.g. `docs/*requirements*.md`, a
  `REQUIREMENTS` file, or whatever the project uses). If more than one candidate
  exists, ask the user which document is the source of truth.
- Read the **entire** requirements document.
- Build an inventory of every individually-identifiable requirement:
  - Capture its ID (e.g. `FUN-01`, `SYS-03`, `NFR-02`), title, priority, the
    "shall" statement, and its acceptance criteria.
  - Note any explicit traceability aids the document already provides (for
    example an implementation/traceability matrix mapping each ID to a
    file/class/method). Treat such a matrix as a **claim to be verified**, not
    as ground truth.

## Step 2: Build a Map of the Codebase

- Survey the source tree to understand its structure (modules, classes, key
  functions, entry points, configuration, persistence, UI).
- For each meaningful unit of behavior, note what it does and where it lives
  (`file:line`, class, function).
- Pay attention to behavior that has user-visible or externally-observable
  effect — those are the units most likely to map to a requirement.

## Step 3: Trace Requirements → Code (find unimplemented requirements)

For every requirement in the Step 1 inventory:
- Locate the code that implements it. Verify by reading the code, not by
  trusting the document's matrix.
- Classify each requirement as:
  - **Implemented** — code exists and satisfies the "shall" statement and its
    acceptance criteria.
  - **Partially implemented** — some but not all of the behavior/acceptance
    criteria are met.
  - **Unimplemented** — no code satisfies the requirement.

## Step 4: Trace Code → Requirements (find orphan code)

For every meaningful behavior found in Step 2:
- Identify which requirement (if any) authorizes it.
- Flag **orphan code**: behavior with user-visible/observable effect that maps
  to no requirement. (Internal helpers, refactors, and pure infrastructure that
  merely support a requirement are not orphans — only flag behavior that
  represents a *capability* the spec does not mention.)

## Step 5: Verify Correctness (find incorrect implementations)

For each requirement that has corresponding code:
- Compare the implementation against the precise wording of the "shall"
  statement **and** each acceptance criterion.
- Flag a **divergence** when the code is present but behaves differently from
  what the requirement specifies — wrong values, wrong precedence, wrong units,
  missing edge-case handling, wrong file paths, off-by-one, etc.
- Where practical, confirm the divergence by running the relevant tests or by
  tracing concrete example inputs from the acceptance criteria through the code.

## Step 6: Clarify with the User Where Requirements Are Lacking

If, during Steps 3–5, a requirement is **ambiguous, incomplete, contradictory,
or silent** on a behavior the code clearly needs, do **not** guess. Pause and
ask the user targeted clarifying questions, for example:
- "Requirement X is silent on <behavior>; what is the intended behavior?"
- "The code does A but requirement X implies B — which is correct?"
- "Capability C exists in the code but has no requirement — should I add a
  requirement for it, or is it out of scope and should be removed?"

Reference specific requirement IDs and `file:line` locations in every question.
Continue questioning until the intended behavior for each finding is unambiguous.
(If the requirements document itself needs editing, that is governed by the
`requirements-check` workflow — note it, but do not edit the spec here without
the user's direction.)

## Step 7: Report the Findings Table

Present **all** findings to the user as a single table. Use these columns:

| # | Type | Req ID | Location (file:line) | Description | Severity | Suggested Action |
|---|------|--------|----------------------|-------------|----------|------------------|

- **Type** is one of: `Unimplemented`, `Partial`, `Orphan Code`, `Divergence`.
- **Req ID** is the requirement ID, or `—` for orphan code.
- **Severity** reflects impact and the requirement's priority (e.g.
  Critical / Major / Minor).
- **Suggested Action** is a one-line summary of the fix direction (implement,
  correct, remove, or "needs clarification — see Step 6").

Follow the table with a short narrative summary: counts per type and the
highest-risk items.

## Step 8: Produce an Implementation Plan

For the findings the user has confirmed are in scope, produce a concrete,
ordered plan:
- One plan item per finding (or per logical group of findings).
- For each item state: the requirement ID(s) addressed, the file(s)/function(s)
  to change, the nature of the change, and how it will be verified (which tests
  to add or run).
- Sequence the items by dependency and risk.
- Call out any item that is blocked pending the clarifications from Step 6.

## Step 9: STOP — Request Explicit Permission

- **Do not apply any code changes as part of this workflow.**
- Present the findings table and the implementation plan, then **explicitly ask
  the user for permission to implement the changes.** For example:
  "Shall I proceed with implementing the plan above? I will not make any code
  changes until you confirm."
- Only after the user explicitly grants permission may implementation begin.
  If the user approves only part of the plan, implement only the approved items.

## Notes

- This is an audit-and-plan workflow; correctness depends on reading the actual
  code, never on assuming the traceability matrix is accurate.
- Always cite requirement IDs and `file:line` locations so every finding is
  traceable.
- Two-way traceability is the point: requirements without code (Step 3) **and**
  code without requirements (Step 4) are both defects worth reporting.
- Never apply changes without explicit user approval (Step 9).
