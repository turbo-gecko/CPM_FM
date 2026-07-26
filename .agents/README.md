# Repository AI assets

This directory is the vendor-neutral canonical source for specialized agents,
reusable skills, and project workflows. `AGENTS.md` remains the authoritative
repository-wide policy.

## Responsibilities

| Area | Purpose | Format |
|---|---|---|
| `agents/` | Role, scope, responsibility boundary, and expected output | Markdown with `name` and `description` frontmatter |
| `skills/` | Reusable expertise loaded when relevant | Open Agent Skills layout: `<name>/SKILL.md` |
| `workflows/` | Project-owned ordered procedures, gates, and hand-offs | Markdown with `name` and `description` frontmatter |

Vendor-specific directories such as `.codex/`, `.github/agents/`, or
`.claude/agents/` are adapters only. They must not redefine repository policy or
become the source of shared content.

Changes confined to these AI assets or their adapters are developer-tooling
changes. They do not trigger an application/SRS version bump unless they also
change an application requirement or user-visible application behavior.

## Catalog

### Agents

- `python-developer`
- `python-test-engineer`

### Skills

- `python-engineering`
- `python-testing`
- `requirements-engineering`
- `requirements-traceability`

### Workflows

- `requirements-change`
- `code-requirements-align`
- `defect-investigation`
- `test-case-implementation`
- `test-quality-audit`
- `context-budget-audit`
- `pre-commit-checks`
- `handoff`

Agents may consume skills and workflows, but skills must not depend on a
particular vendor's model, permission vocabulary, or tool names. Workflows
reference `AGENTS.md` for commands and mandatory repository policy instead of
copying those rules.
