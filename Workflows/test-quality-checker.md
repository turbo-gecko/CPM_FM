---
description: Aggressively audits the quality of the unit test suite against unit-testing best practices (Pylons / Tres Seaver guidelines), assuming the code is faulty, then reports weaknesses and proposes high-value tests that test to 'not fail' and exercise boundary conditions
---

# Test Quality Checker Workflow

This workflow audits the **quality** of the existing unit tests — not merely
their existence or their line coverage. Its job is to find faults: in the code
under test, and in the tests themselves. It is deliberately adversarial.

## Guiding Principles (non-negotiable)

1. **Tests exist to find faults, as well as to determine correctness.** A suite
   that only confirms the happy path is doing half its job. Treat the absence of
   fault-finding tests as a defect in the suite.
2. **Quality over quantity.** One focused test that pins down a contract is worth
   more than ten that re-assert the same happy path or chase a coverage number.
   High line coverage is *not* evidence of a good suite.
3. **Tests must test to 'not fail'.** A passing test must pass because the code is
   correct, not because the test is too weak to detect a fault. Assert on real,
   specific values and side effects — never on truthiness, "did not raise", or a
   `mock.called` that any wrong implementation would also satisfy.
4. **Tests must exercise boundary conditions and edge cases.** Empty, zero, one,
   many, max, off-by-one, negative, null/None, malformed, oversized, duplicate,
   out-of-order, and error/exception paths — these are where faults hide.
5. **Be aggressive. Assume the code is faulty and it is your job to find every
   issue.** Do not give the code the benefit of the doubt. Start from "this is
   broken — prove me wrong."

## Best Practices This Workflow Enforces (Pylons / Tres Seaver)

Judge every existing and proposed test against these rules:

- **Test Just One Thing.** Each test method exercises one set of preconditions for
  one function/method. Canonical form: *set up preconditions → call the unit under
  test exactly once → assert the return value and/or side effects → do nothing
  else.* Flag tests that call the unit multiple times or assert several unrelated
  things.
- **The test name states what is tested.** A reader should know the scenario from
  the name alone — `test_parse_dir_output_with_empty_input`, not
  `test_parser_2` with a comment. Flag vague names.
- **Test to 'not fail', with specific assertions.** Reject weak assertions:
  `assert result` (truthiness), `assert x is not None` as the *only* check, "it
  didn't raise", or asserting only that a mock was called. Demand assertions on
  exact values, exact collection contents, and exact side effects.
- **Don't share mutable fixtures across tests or modules.** Prefer per-test helper
  methods/factories (e.g. `_make_one()`) that return freshly configured objects
  over shared `setUp`/`self` attributes or cross-module fixtures. Shared mutable
  state creates order dependencies and obscures intent.
- **Tests must be independent and order-independent.** No test may rely on another
  test having run first. Flag hidden ordering or shared global/registry state that
  isn't cleaned up.
- **Keep mocks minimal and contract-clarifying.** A mock should be the smallest
  object that makes the test meaningful. Flag over-mocking that mocks away the very
  behavior under test (a test that only verifies the mock, not the code).
- **Resist cleverness / over-DRY in test code.** A little duplication that keeps
  each test readable in isolation beats a clever helper that hides what failed.
  Flag test indirection that makes a failure hard to diagnose.
- **Defer imports of the module under test where appropriate.** Import failures
  should fail individual tests, not abort collection of the whole suite. (Apply
  pragmatically — match the project's existing convention.)
- **Avoid doctests as a testing mechanism.** They are poor tests and poor docs at
  once, break across versions, and resist debugging.
- **Coverage means paths, not lines.** 100% line coverage with every branch,
  error path, and boundary unexercised is a false signal. Look at what *paths*
  and *contracts* are covered, not the percentage.

## Step 1: Scope the Audit

- Confirm the target with the user: the whole suite, a specific test module, or
  the tests covering a specific source module/feature. Default to the whole **unit**
  suite (`tests/`) if unspecified.
- The **integration (HIL) suite** (`integration/`) is a *separate tier* — it drives
  the real app against a real CP/M machine over serial and is bench-only (not run
  by CI or the default `pytest`). It is **out of scope by default**: do not run it
  as part of a baseline (it needs hardware and minutes per case) and do not grade
  its end-to-end cases by the unit-test "Just One Thing" rule — a HIL case
  legitimately drives a whole flow. Audit it only when the user explicitly asks,
  and then judge it on HIL terms (deterministic waits, MT-ID/requirement tagging,
  scratch-drive safety, real round-trip integrity), not unit-test isolation.
- Identify the source modules in scope and their corresponding test files. In
  this repo the most safety-critical pure logic is `terminal/cpm_parser.py`,
  `terminal/xmodem.py`, and `utils/config_handler.py`; the GUI/serial layers are
  harder to unit-test (see `CR-014`, `NFR-004`).

## Step 2: Establish a Baseline

- Run the suite and capture the current state:
  - `pytest` — confirm it passes and note timing.
  - Generate coverage if available: `pytest --cov=cpm_fm --cov-report=term-missing`
    (note any missing-line ranges, but treat coverage as a *lead*, not a verdict).
- Build an inventory of every test: file, test name, the unit it targets, and the
  single thing it claims to verify.

## Step 3: Grade Each Existing Test (quality, not presence)

For every test in scope, assess it against the best-practices checklist above and
assign a grade. Record concrete findings, each citing `file:line`:

- **Just One Thing?** Does it set up, call once, and assert — or is it doing too
  much?
- **Tests to 'not fail'?** Are the assertions specific enough that a plausible
  *wrong* implementation would fail them? Try to imagine a bug the test would
  *miss* — if you can, the test is too weak. This is the most important check.
- **Name self-explanatory?**
- **Independent / no shared mutable state / cleans up?**
- **Mocks minimal and not mocking away the behavior under test?**
- **Readable in isolation (no over-clever indirection)?**

Classify each test as `Strong`, `Weak` (passes but wouldn't catch realistic
faults), or `Broken` (asserts the wrong thing, is tautological, or can't fail).

## Step 4: Hunt for Coverage Gaps — Boundaries, Edges, and Error Paths

This is the heart of the workflow. For each unit under test, enumerate the inputs
and states that *should* be tested and check whether they are. Be exhaustive and
adversarial — assume each missing case hides a fault:

- **Boundary values:** empty / zero-length, single element, exactly-at-limit,
  one-over-limit, max size, off-by-one around any index or count.
- **Degenerate / malformed input:** `None`, empty string, whitespace-only,
  wrong type, truncated data, garbage bytes, wrong line endings (relevant to the
  `eol` `CR`/`LF`/`CRLF` handling and to `cpm_parser` DIR scraping).
- **Quantity classes:** zero, one, many — e.g. a `DIR` listing with no files, one
  file, a full four-column page, more than one page.
- **Error and exception paths:** does the code raise the right exception on bad
  input? Is timeout / NAK / retry-exhaustion in `xmodem.py` exercised? Are both
  config shapes (flat and nested, per NFR-002) tested for
  `open_port` / `validate_serial_settings`?
- **State and ordering:** capture-buffer reset between refreshes, partial reads
  split across `_read_loop` polls, concurrent transfer + terminal use.
- **Round-trips and invariants:** send→receive a file and assert byte-for-byte
  identity; parse→reformat; load→save config and assert equality.

Produce a list of **missing high-value tests**, each tied to a specific
boundary/edge/error condition and the fault it would catch. Prioritize by the
severity of the fault that could hide there, not by ease of writing.

## Step 5: Prove the Weaknesses (optional but preferred)

For the highest-value gaps and the tests graded `Weak`/`Broken`, *demonstrate* the
problem rather than asserting it:

- **Mutation probe:** introduce a small deliberate fault in the source (e.g. flip a
  comparison, drop a boundary case, change a constant) and confirm the existing
  tests still pass. A suite that passes against a mutated implementation has proven
  it tests-to-fail in name only. **Revert the mutation immediately afterwards** —
  never leave probe edits in the tree.
- For a tautological/broken test, show the wrong implementation it would accept.

Report each demonstration as concrete evidence.

## Step 6: Report the Findings Table

Present all findings to the user as a single table:

| # | Type | Test / Unit (file:line) | Finding | Principle Violated | Severity | Suggested Fix |
|---|------|-------------------------|---------|--------------------|----------|---------------|

- **Type** is one of: `Weak Assertion`, `Tests Too Much`, `Shared/Order
  Dependency`, `Over-Mocked`, `Unclear Name`, `Missing Boundary`, `Missing Error
  Path`, `Missing Edge Case`, `Tautological/Can't Fail`, `Doctest`.
- **Principle Violated** cites the guiding principle (1–5) and/or the named
  best practice.
- **Severity** reflects the impact of the fault that could slip through
  (Critical / Major / Minor).

Follow the table with a short narrative: counts per type, the weakest tests, and
the highest-risk uncovered conditions. Give an honest overall verdict on suite
quality — resist grading on a curve just because coverage is high.

## Step 7: Propose New / Improved Tests

For the confirmed gaps and weak tests, write concrete proposals:

- One proposal per missing condition or per weak test to strengthen.
- Each follows canonical form (Just One Thing, call once, assert specific
  values/side effects), has a self-explanatory name, and is independent.
- New tests for a *suspected* fault must **fail against the current code** if the
  fault is real — state the expected failure explicitly.
- Match the project's existing test conventions and `pytest` style.

## Step 8: STOP — Confirm Before Changing Tests or Code

- **Do not modify tests or source as part of the audit itself** (the mutation
  probe in Step 5 is temporary and must be reverted).
- Present the findings table and the proposed tests, then explicitly ask the user
  whether to (a) add the proposed tests, (b) strengthen the weak tests, and/or
  (c) investigate any *real code faults* this audit uncovered via the
  `defect-investigator` workflow.
- Only after explicit approval may you write or modify tests/code. If the user
  approves only part, do only that part.

## Step 9: If Approved — Implement and Verify

- Add/strengthen the approved tests.
- Run `pytest`; confirm new fault-detecting tests fail before the fix and pass
  after, and that the full suite stays green with no regressions.
- If the audit revealed a genuine code defect (not just a test gap), hand it to the
  `defect-investigator` workflow rather than patching ad hoc here.

## Notes

- This is a quality audit, not a coverage report. A high coverage number with weak
  assertions is a *worse* signal than honest low coverage, because it hides risk.
- Always cite `file:line` so every finding is traceable.
- The default posture is suspicion: every passing test is assumed too weak until
  shown otherwise, and every untested boundary is assumed to hide a fault.
- Keep GUI-thread / signal constraints (`NFR-004`) and the no-GUI-imports rule for
  `terminal/` and `utils/` (`CR-014`) in mind when proposing tests — the pure
  layers are unit-testable; the GUI layer needs the smoke-test approach used in
  `tests/test_gui_smoke.py`.
