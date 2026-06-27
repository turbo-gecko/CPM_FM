---
description: Requirements checker that analyses, reviews and edits requirements using ISO/IEC/IEEE 29148 standard
---

# Requirements Checker Workflow

This skill provides expert analysis, review, and editing of requirements following the ISO/IEC/IEEE 29148 standard for systems and software engineering — life cycle processes — requirements engineering.

## Document Structure (read this first)

The requirements set is split across several files; know the layout before editing:
- **`docs/cpm_fm_requirements.md`** — the SRS and the single source of truth for requirements. This is the file you hand-edit to add or change a requirement (its header carries the document Version field, DR-040/DR-041) — **except** the architectural `CR-`/`NFR-` constraints, which live in the architecture companion below.
- **`docs/cpm_fm_architecture.md`** — the Software Architecture Description (companion). Holds the architectural design constraints (CR-001–009, CR-012–014) and architectural NFRs (NFR-001, NFR-004, NFR-005), with IDs unchanged, plus the authoritative architecture narrative. Hand-edit these `CR-`/`NFR-` requirements here, not in the SRS. The behavioural constraints CR-010, CR-011, CR-015, NFR-002 and the X-Modem protocol requirements NFR-003a–NFR-003o (SRS §8.1) remain in the SRS.
- **`docs/requirements_change_history.md`** — the §11 Change History (companion file). Add a row here for every edit; do **not** put change history back in the SRS.
- **`docs/requirements_issue_log.md`** — the §10 Issue Resolution Log (companion file). Record resolved ambiguities/conflicts/gaps here as OI entries.
- **`docs/requirements_views/`** — generated, **read-only** views (`requirements_index.md` for a terse one-line-per-requirement summary; `code_to_requirements.md`/`.json` mapping source files to requirement IDs from code `Satisfies:` tags; `requirements_to_tests.md`/`.json` mapping each requirement to the test(s) that verify it from test `Verifies:` tags, with untested-requirement and stale-tag lists). Use them for quick lookup, but **never hand-edit them** — regenerate with `python tools/traceability_sync/generate_views.py` after any requirement-ID, Source-citation, code `Satisfies:`-tag, or test `Verifies:`-tag change.

In the SRS, §10 and §11 are now one-line stub redirects pointing to the two companion files above.

## Core Principles

The requirements expert follows ISO/IEC/IEEE 29148 principles:
- **Clarity**: Requirements must be unambiguous and understandable
- **Completeness**: Requirements must cover all necessary system capabilities
- **Correctness**: Requirements must accurately reflect stakeholder needs
- **Consistency**: Requirements must not conflict with each other
- **Verifiability**: Requirements must be testable and measurable
- **Feasibility**: Requirements must be technically and economically achievable
- **Necessity**: Each requirement must add value and be justified

## Analysis Process

### 1. Initial Requirements Assessment
When presented with requirements:
- Read and understand the complete requirements document
- Identify the type of requirements (functional, non-functional, interface, performance, etc.)
- Assess the context and scope of the requirements
- Check for basic structure and organization

### 2. ISO/IEC/IEEE 29148 Compliance Review
Evaluate requirements against the standard:

**Structure and Documentation:**
- Requirements are uniquely identified
- Requirements are traceable
- Requirements have clear ownership and approval status
- Change history is maintained
- Requirements are appropriately categorized

**Quality Attributes:**
- Each requirement is complete and self-contained
- Requirements are atomic (single concern per requirement)
- Requirements are not redundant
- Requirements are prioritized
- Requirements have acceptance criteria

**Content Quality:**
- Functional requirements specify what the system must do
- Non-functional requirements specify how the system must perform
- Interface requirements specify external interactions
- Design constraints specify limitations and restrictions
- Data requirements specify data structures and flows

### 3. Clarification Process
When ambiguities, missing information, or conflicts are identified:

**Ask Clarifying Questions For:**
- **Ambiguities**: Vague terms, multiple interpretations, unclear scope
- **Missing Information**: Incomplete descriptions, undefined terms, omitted scenarios
- **Conflicting Requirements**: Contradictory statements, incompatible constraints
- **Assumptions**: Implicit assumptions that need validation
- **Dependencies**: Relationships between requirements that are unclear
- **Verification**: How requirements will be tested or validated

**Question Categories:**
- Scope and boundary questions
- Functional behavior questions
- Performance and capacity questions
- Interface and integration questions
- Security and compliance questions
- User experience questions
- Operational environment questions
- Maintenance and support questions

**Continue Questioning Until:**
- All identified ambiguities are resolved
- All missing information is provided
- All conflicts are addressed
- All assumptions are validated
- All dependencies are clarified
- Verification methods are defined

### 4. Requirements Critique
Provide detailed feedback on:

**Accuracy:**
- Does the requirement accurately reflect stakeholder needs?
- Is the requirement technically sound?
- Are the values and parameters realistic?
- Are the constraints appropriate?

**Relevancy:**
- Is the requirement necessary for the system?
- Does it align with project goals and objectives?
- Is it within scope?
- Does it add value to stakeholders?

**Adherence to Standard:**
- Does it follow ISO/IEC/IEEE 29148 guidelines?
- Is it properly structured and formatted?
- Is it traceable and verifiable?
- Does it have proper metadata (ID, priority, status)?

### 5. Requirements Editing
When editing requirements:

**Improvement Actions:**
- Rewrite ambiguous statements to be clear and precise
- Add missing details and context
- Resolve conflicts by reconciling or prioritizing
- Add acceptance criteria where missing
- Improve structure and organization
- Add traceability information
- Ensure consistent terminology
- Add verification methods

**Editing Principles:**
- Preserve original intent while improving clarity
- Maintain consistency with related requirements
- Follow established requirement templates
- Document all changes with rationale
- Ensure changes don't introduce new issues
- Always increment the SRS document Version field (DR-040/DR-041) when making edits
- Always add an entry to the **Change History companion file** (`docs/requirements_change_history.md`) — not the SRS itself — summarising every requirement modified, added, or deleted, including the requirement IDs affected
- When a review resolves an ambiguity, conflict, or gap, record it as a new OI entry in the **Issue Resolution Log companion file** (`docs/requirements_issue_log.md`)
- After editing requirement IDs, Source-column citations, or code `Satisfies:` tags, regenerate the read-only views by running `python tools/traceability_sync/generate_views.py` and commit `docs/requirements_views/` (never hand-edit the views)
- After editing, review `AGENTS.md` and update any architecture, component, or behaviour descriptions that are no longer accurate given the changed requirements
- When the change alters user-visible behaviour, update the **end-user manual** (`src/cpm_fm/docs/cpm_fm_manual.md`) — the affected section(s), the Table of Contents, and the **Reference: Default Settings** table — and bump its `**Version X.Y.Z**` line to match `src/version.txt`. This is the user manual, distinct from `docs/manual_test_plan.md`. For architecture-only changes with no user-visible effect, state that no manual change was needed rather than skipping the step silently
- After editing, review the test suite (`tests/`) and update or add tests so that every new or modified requirement has corresponding test coverage; tag each test function's docstring with a `Verifies:` line citing the requirement ID(s) it exercises (the test-suite counterpart of code `Satisfies:` tags) so the `requirements_to_tests` view picks it up. If tests are added or changed, run the full test suite (`pytest`), check `python tools/traceability_sync/agent_toolset.py --coverage` for untested requirements and stale tags, and record any failures in a new plan file at `temp\fixes.md` listing the failing tests and the code changes needed to resolve them

## Usage

When the user provides requirements for analysis:
1. Read the requirements document completely
2. Perform initial assessment
3. Identify areas needing clarification
4. Ask targeted clarifying questions
5. Continue questioning until satisfied
6. Provide comprehensive critique
7. Suggest specific improvements
8. Edit requirements if requested
9. After editing, increment the SRS Version field and add an entry to the Change History companion file (`docs/requirements_change_history.md`); record any resolved ambiguity/conflict/gap as an OI entry in the Issue Resolution Log companion file (`docs/requirements_issue_log.md`)
9a. After editing requirement IDs, Source citations, or code `Satisfies:` tags, regenerate the views (`python tools/traceability_sync/generate_views.py`) and commit `docs/requirements_views/`
10. After editing, update `AGENTS.md` to reflect any changed architecture, component descriptions, or cross-cutting behaviours introduced or modified by the new/changed requirements
10a. When the change alters user-visible behaviour, update the end-user manual (`src/cpm_fm/docs/cpm_fm_manual.md`) — affected section(s), Table of Contents, and Reference: Default Settings table — and bump its version line to match `src/version.txt`; for architecture-only changes, state that no manual change was needed
11. After editing, update or add tests in `tests/` to cover every new or modified requirement, tagging each test function's docstring with a `Verifies:` line for the requirement ID(s) it exercises; if any tests are added or changed, run `pytest`, check `agent_toolset.py --coverage` for untested requirements/stale tags, and — if there are failures — create `temp\fixes.md` as a plan listing each failing test, the root cause, and the code changes required to fix it

## Output Format

**Clarification Questions:**
- Numbered list of questions
- Categorized by type (ambiguity, missing info, conflict, etc.)
- Reference specific requirement IDs where applicable
- Explain why clarification is needed

**Critique Report:**
- Overall assessment summary
- Detailed findings by requirement
- Issues categorized by severity (critical, major, minor)
- Specific references to ISO/IEC/IEEE 29148 clauses
- Recommendations for improvement

**Edited Requirements:**
- Revised requirement text
- Change log with rationale
- Updated metadata (IDs, priorities, etc.)
- Traceability information
- Incremented SRS Version field
- Change History entry added to `docs/requirements_change_history.md` (companion file) listing all affected requirement IDs and the nature of each change
- Views regenerated (`docs/requirements_views/`) if any IDs, Source citations, or `Satisfies:` tags changed

**AGENTS.md Update:**
- Sections updated to reflect any new or changed architecture, components, or cross-cutting behaviours
- No update needed if the requirement change has no impact on the architecture description

**User Manual Update:**
- Sections/ToC/Reference: Default Settings table of `src/cpm_fm/docs/cpm_fm_manual.md` updated to match any new or changed user-visible behaviour, with its version line bumped to match `src/version.txt`
- Explicitly note "no manual change needed" for architecture-only changes (no user-visible effect)

**Test Update:**
- New or modified test cases listed, with the requirement ID each covers
- `pytest` run result (pass count, failure count)
- If failures exist: `temp\fixes.md` created as a plan with one entry per failing test — failing test name, root cause, and the code change needed to fix it

## Notes

- Always reference specific requirement IDs when providing feedback
- Base all critiques on ISO/IEC/IEEE 29148 standard principles
- Be thorough in questioning - don't assume intent
- Prioritize issues by impact and risk
- Provide actionable, specific recommendations
- Maintain professional, constructive tone
- When editing, preserve stakeholder intent while improving quality
- Never delete existing entries in the Change History or Issue Resolution Log companion files
- Steps 10, 10a, and 11 (AGENTS.md, user manual, and test updates) are mandatory whenever requirements are edited — do not skip them even for minor or cosmetic changes (for step 10a, "no manual change needed" is an acceptable outcome for architecture-only edits, but the decision must be stated, not skipped silently)
