<!--
Thanks for contributing to CP/M File Manager (cpm-fm)!
Please fill out this template. See CONTRIBUTING.md for details.
-->

## Description

<!-- What does this PR do, and why? -->

## Related issues

<!-- Link issues, e.g. "Fixes #123". List relevant requirement IDs, e.g. FR-170. -->

- Fixes #
- Requirement IDs:

## Type of change

- [ ] Bug fix (non-breaking change that fixes an issue)
- [ ] New feature (non-breaking change that adds functionality)
- [ ] Breaking / architectural change
- [ ] Documentation only
- [ ] Translation
- [ ] Refactor / tooling (no behaviour change)

## How has this been tested?

<!-- Describe the tests you ran and how to reproduce them. -->

- [ ] Unit suite: `.venv/Scripts/python.exe -m pytest`
- [ ] Integration (HIL) suite on real hardware: `.venv/Scripts/python.exe -m pytest integration/`
      <!-- If you couldn't run this, say so and explain why. -->

## Checklist

- [ ] I used the `.venv` interpreter for all Python commands.
- [ ] `ruff check` and `ruff format --check` pass (`src` and `tests`).
- [ ] `mypy src` passes.
- [ ] The unit test suite passes.
- [ ] I read [CONTRIBUTING.md](CONTRIBUTING.md) and, where my change touches the
      GUI/threading/persistence layers, [AGENTS.md](../AGENTS.md) and the
      architecture doc.

### If this changes a requirement / behaviour

<!-- Skip this section for pure typo/refactor/tooling changes. -->

- [ ] Updated the SRS (`docs/cpm_fm_requirements.md`) or architecture doc
      (`docs/cpm_fm_architecture.md`) as appropriate.
- [ ] Added `Satisfies:` tags to new/changed functions and `Verifies:` tags to
      tests.
- [ ] Regenerated the requirement views
      (`generate_views.py`) and `--check` is green.
- [ ] Updated the manual test plan and scorecard, and (if user-visible) the user
      manual.
- [ ] Bumped `src/version.txt`, the SRS version field, and the manual version
      together, and added a change-history row.

## Notes for reviewers

<!-- Anything else reviewers should know: trade-offs, follow-ups, screenshots. -->
