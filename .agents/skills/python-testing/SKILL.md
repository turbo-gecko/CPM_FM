---
name: python-testing
description: Design, implement, review, and diagnose Python unit, GUI, integration, and hardware-in-the-loop tests. Use when changing tests, investigating weak assertions or missed defects, verifying requirement coverage, or working in tests/ or integration/.
---

# Python Testing

Apply `AGENTS.md` and select the correct test tier before acting.

## Unit and GUI tests

- Test observable behavior, boundaries, error paths, and state transitions.
- Keep each test focused on one coherent behavior.
- Prefer exact assertions over truthiness, "did not raise", or `mock.called`.
- Mock only external boundaries; do not mock away the behavior under test.
- Control time, randomness, filesystems, serial I/O, and shared state.
- Give every new or changed unit test a `Verifies:` docstring tag.

Use `.agents/workflows/test-case-implementation.md` when implementing multiple test cases and `.agents/workflows/test-quality-audit.md` for a formal audit.

## HIL tests

Read [references/hil-testing.md](references/hil-testing.md) before changing or running `integration/`.

Never claim a HIL pass unless the test ran against the identified physical target. Treat a skip, simulation, or successful command transmission without physical observation as insufficient proof.

## Evidence

- Run the narrowest affected test first.
- Confirm that assertions, rather than setup failures or skips, determine the result.
- Rerun timing-sensitive tests when intermittency is plausible.
- Run broader regression checks in proportion to the change.
- Report exact commands and outcomes; distinguish verified facts from pending bench work.
