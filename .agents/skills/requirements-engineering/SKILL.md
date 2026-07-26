---
name: requirements-engineering
description: Analyze, critique, write, and revise software requirements using ISO/IEC/IEEE 29148 principles. Use when a task adds, changes, clarifies, removes, or reviews FR, UIR, IFR, DR, STR, CR, or NFR requirements.
---

# Requirements Engineering

Use this skill with `.agents/workflows/requirements-change.md`; the workflow and `AGENTS.md` contain the repository-specific change sequence.

## Quality criteria

Check each requirement for:

- unique identification and correct category;
- singularity and one necessary concern;
- clear actors, conditions, behavior, limits, and outcomes;
- consistent terminology and absence of conflicts;
- feasibility and stakeholder value;
- objective verification and traceability.

Avoid vague qualifiers, undefined pronouns, bundled obligations, implementation detail without a genuine constraint, and acceptance criteria that merely repeat the requirement.

## Repository classification

- Edit most behavioral requirements in `docs/cpm_fm_requirements.md`.
- Edit architectural `CR-001`–`CR-009`, `CR-012`–`CR-014`, `NFR-001`, `NFR-004`, and `NFR-005` in `docs/cpm_fm_architecture.md`.
- Keep historical change and issue records append-only in their companion files.
- Consult generated views first, but use the authoritative specification for exact wording.

When intent is materially ambiguous, present the competing interpretations and request a stakeholder decision rather than silently choosing one.
