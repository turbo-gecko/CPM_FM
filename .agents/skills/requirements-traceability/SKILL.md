---
name: requirements-traceability
description: Trace requirements bidirectionally across specifications, Python implementation, unit tests, HIL tests, and manual tests. Use for alignment audits, Satisfies or Verifies tag work, generated-view maintenance, orphan detection, and coverage-gap analysis.
---

# Requirements Traceability

Treat every mapping as a claim to verify semantically.

## Trace model

- Specification to implementation: `Satisfies:` tags on requirement-bearing code.
- Specification to unit tests: `Verifies:` tags on test functions.
- Specification to HIL: `@pytest.mark.mt(...)` requirement IDs in `integration/`.
- Specification to manual verification: requirement IDs in `docs/manual_test_plan.md`.

The generated views scan the specifications, `src/`, and `tests/`; they do not establish semantic correctness and do not scan `integration/`.

## Procedure

1. Start with `docs/requirements_views/requirements_index.md`.
2. Use `code_to_requirements` and `requirements_to_tests` to identify candidates.
3. Run the traceability tools with the required `.venv` interpreter.
4. Read the exact requirement, implementation, and verifying test before accepting a mapping.
5. Inspect HIL and manual coverage separately when relevant.
6. Classify missing implementation, partial implementation, divergence, orphan behavior, missing test, weak test, and stale tag separately.
7. Regenerate views only after an authorized source/tag change; never hand-edit them.

Use `.agents/workflows/code-requirements-align.md` for a full read-only alignment audit.
