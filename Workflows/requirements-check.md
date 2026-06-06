---
description: Requirements checker that analyses, reviews and edits requirements using ISO/IEC/IEEE 29148 standard
---

# Requirements Checker Workflow

This skill provides expert analysis, review, and editing of requirements following the ISO/IEC/IEEE 29148 standard for systems and software engineering — life cycle processes — requirements engineering.

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
- Always increment the document version number when making edits
- Always add an entry to the Change History table summarising every requirement modified, added, or deleted, including the requirement IDs affected

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
9. After editing, increment the document version number and add a Change History entry summarising all changes made (requirement IDs, nature of change)

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
- Incremented document version number
- Change History table entry added to the document listing all affected requirement IDs and the nature of each change

## Notes

- Always reference specific requirement IDs when providing feedback
- Base all critiques on ISO/IEC/IEEE 29148 standard principles
- Be thorough in questioning - don't assume intent
- Prioritize issues by impact and risk
- Provide actionable, specific recommendations
- Maintain professional, constructive tone
- When editing, preserve stakeholder intent while improving quality
- Never delete existing entries in the version history
