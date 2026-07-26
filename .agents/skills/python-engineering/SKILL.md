---
name: python-engineering
description: Design, implement, review, and refactor Python code in this PySide6 application. Use for production-code changes, architecture decisions, type-safety work, error handling, concurrency boundaries, or maintainability reviews under src/.
---

# Python Engineering

Apply the repository rules in `AGENTS.md` before using this skill.

## Design

- Preserve the `gui/`, `terminal/`, and `utils/` boundaries from the architecture document.
- Keep Qt widget access on the GUI thread; marshal worker results through Qt signals.
- Keep `terminal/` and `utils/` free of GUI-toolkit imports.
- Prefer cohesive, testable units and explicit interfaces over broad refactors.
- State meaningful trade-offs and avoid introducing frameworks that the application does not need.

## Implementation

- Follow existing project patterns before introducing a new abstraction.
- Use Python 3.10+ type syntax and descriptive names.
- Validate external inputs at boundaries and handle errors with useful context.
- Avoid bare `except`, hidden global state, and blocking I/O on the GUI thread.
- Update `Satisfies:` docstring tags whenever requirement-bearing behavior changes.

## Verification

- Inspect the targeted requirement IDs through the generated views first.
- Use the `python-testing` skill for test design or test changes.
- Run all Python tools through `.venv/Scripts/python.exe -m <tool>`.
- Follow the relevant workflow under `.agents/workflows/` when the task is a defect, requirement change, or formal audit.
