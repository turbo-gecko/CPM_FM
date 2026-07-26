---
name: test-case-implementation
description: Implements and proves test cases sequentially so each test is independently understood, executed, and shown to verify its intended behavior before moving to the next.
---

# Test Case Implementation Workflow

Required skill: `python-testing`.

For each approved test, complete the following sequence before selecting another:

1. Identify the single behavior, requirement, or failure mode.
2. Inspect the implementation and relevant fixtures.
3. Implement only that test and its minimum support.
4. Run it by node ID or the narrowest selector.
5. Confirm its assertions—not a skip, setup error, or unrelated exception—determine the result.
6. When practical, demonstrate red-before-green or another controlled failure proving fault detection.
7. Rerun if timing, concurrency, or hardware creates intermittent risk.
8. Restore temporary fault injection and record the exact command and outcome.

If execution is impossible, stop that test and report what is proven, what remains unproven, and what dependency or hardware is missing. After all individual cases are proven, run the broader regression and traceability checks required by `AGENTS.md`.
