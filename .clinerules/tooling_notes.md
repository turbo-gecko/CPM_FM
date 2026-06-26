# Tooling Environment Notes (Persistent Learnings)

This file captures hard-won knowledge about tool behavior in this environment, to avoid re-learning on future agents.

## PowerShell 7+ Quirks (Windows 11)

### Command Chaining with venv activation
**❌ Incorrect:**  
```powershell
& .venv\Scripts\Activate.ps1; python --version
```
**✅ Correct:** Use array syntax for parallel commands or chain via separate calls:
```json
["Set-Location D:\\workspace\\Python\\CPM_FM", ". .venv\\Scripts\\Activate.ps1; python -m pytest tests/ -q"]
```

### Missing Unix Pipes/Cmdlets  
- No `head`, use `Select-Object -First N`  
- No `tail`, use `Select-Object -Last N`

---

## Tool Call Format Requirements (JSON Schema Validation)

All tool calls **must** match the expected JSON structure:

| Tool | Required Format Example |
|------|-------------------------|
| `run_commands` | `{"commands": ["cmd1", "cmd2"]}` (array of strings) |
| `read_files`    | `{"files": [{"path":"file.py","start_line":1}]}` *(note nested object)* |
| `editor`        | `{"new_text":"...", "old_text":"..."}` or `{"insert_line":N, ...}` |

---

## Tool Verification Checklist (for Quick Self-Diagnostics)  

Run this sequence to verify full tool stack:

```powershell
# 1. Navigate + Activate venv
Set-Location D:\workspace\Python\CPM_FM; . .venv\Scripts\Activate.ps1

# 2. Core tools version check
python -m pytest --version
python -m mypy --version  
python -m ruff --version

# 3. Quick test execution (subset)
pytest tests/test_version.py -q

# 4-7. Verify all core APIs work: read_files, search_codebase, editor, fetch_web_content, spawn_agent, team_status, run_commands
```