#!/usr/bin/env bash
# PreToolUse guard (cpm-fm): this script runs ONLY when a Bash/PowerShell command
# begins with a bare Python-tool invocation (python/pip/pytest/mypy/ruff) — the
# `if` permission-rule filters in .claude/settings.json gate it. Reaching this
# script therefore means "block and tell the agent to use the .venv interpreter".
# Commands that already start with `.venv/` never match the filter, so they pass.
cat <<'JSON'
{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"BLOCKED by project policy: run ALL Python tooling through the project virtual environment, never the bare command. Re-run it as: .venv/Scripts/python.exe -m <tool>  — e.g.  .venv/Scripts/python.exe -m pytest -q  |  -m pip install -e .[dev]  |  -m mypy src  |  -m ruff check src tests. (Bare python/pip/pytest/mypy/ruff may use the wrong interpreter.) See AGENTS.md > Commands."}}
JSON
