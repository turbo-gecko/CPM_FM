---
description: Investigates, tests, and fixes defects in the codebase
---

# Defect Investigator Workflow

This workflow guides you through a systematic defect investigation and resolution process.

## Step 1: Gather Defect Information
- Ask the user for the defect description
- Ask clarifying questions if needed, such as:
  - What is the expected behavior?
  - What is the actual behavior?
  - Which component or module is affected?
  - How can the defect be reproduced?
  - Are there any error messages or stack traces?
  - Under what conditions does the defect occur?

## Step 2: Analyze Why Tests Missed the Defect
- Search for existing unit tests related to the affected component
- Identify the specific test coverage gaps
- Determine if the test scenarios were incomplete
- Check if edge cases or boundary conditions were not tested
- Review if the test data or mock configurations were inadequate

## Step 3: Create or Update Unit Tests
- Identify the test file(s) that should cover the defect scenario
- Write new unit tests that specifically trigger the defect
- Ensure the new tests fail initially (confirming they detect the defect)
- Add tests for edge cases and boundary conditions if applicable
- Follow the existing test patterns and conventions in the codebase

## Step 4: Run New Unit Tests
- Execute the new unit tests using pytest
- Confirm that the tests fail (proving they detect the defect)
- Document the test failure as evidence of defect detection
- If tests pass unexpectedly, review the test implementation

## Step 5: Create Fix Plan
- Analyze the root cause of the defect
- Identify the specific file(s) and function(s) that need modification
- Determine the minimal fix required (prefer upstream fixes over workarounds)
- Consider potential side effects and regression risks
- Plan the implementation approach

## Step 6: Implement the Fix
- Apply the fix to the identified code location(s)
- Use minimal, focused edits (single-line changes when sufficient)
- Follow existing code style and patterns
- Add comments if the fix is non-obvious
- Ensure the fix addresses the root cause, not just symptoms

## Step 7: Verify the Fix
- Rerun all affected unit tests including the new tests
- Confirm all tests now pass
- Run the full test suite to catch unexpected regressions
- Run related integration tests if available
- Check for any regressions in other parts of the codebase
- Check test coverage metrics before and after the fix to ensure improvement
- Document the fix and test coverage improvement

## Step 8: Check Requirement Documents
- Review relevant requirement documents to ensure the fix aligns with stated requirements
- If the defect reveals a gap or ambiguity in requirements, update the requirement document
- Verify that the fix doesn't violate any existing requirements
- Document any requirement clarifications or updates made during the investigation
