"""Generate and validate integration evidence coverage artifacts.

The generated manifest separates collection from execution evidence and keeps
manual-scenario mappings conservative: a test is ``partial`` when it supports a
real manual scenario, and ``supplementary`` when it is requirement-only. No test
is classified ``equivalent`` without an explicit, reviewed rationale.

Generate artifacts::

    .venv/Scripts/python.exe -m integration.generate_coverage

Validate committed artifacts without rewriting them::

    .venv/Scripts/python.exe -m integration.generate_coverage --check
"""

from __future__ import annotations

import argparse
import ast
import difflib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
INTEGRATION_DIR = ROOT / "integration"
MANIFEST_PATH = INTEGRATION_DIR / "coverage_manifest.json"
REPORT_PATH = INTEGRATION_DIR / "coverage_report.md"
MANUAL_PLAN_PATH = ROOT / "docs" / "manual_test_plan.md"
SPEC_PATHS = (
    ROOT / "docs" / "cpm_fm_requirements.md",
    ROOT / "docs" / "cpm_fm_architecture.md",
)

EVIDENCE_CLASSES = ("equivalent", "partial", "supplementary", "manual-only")
EVIDENCE_RANK = {"manual-only": 0, "supplementary": 1, "partial": 2, "equivalent": 3}
TIER_MARKERS = ("hil", "visual", "gui_integration")
REQUIREMENT_RE = re.compile(r"\b(?:STR|FR|UIR|IFR|DR|CR|NFR)-\d+[a-z]?\b")
MANUAL_ID_RE = re.compile(r"^\|\s*(MT-[A-Za-z0-9]+)(?:\s+\[[^]]+\])?\s*\|")


class CoverageError(RuntimeError):
    """Raised when collection or source parsing cannot produce valid evidence."""


def _attribute_path(node: ast.AST) -> list[str]:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return list(reversed(parts))


def _marker(node: ast.AST) -> tuple[str, list[str]] | None:
    call = node if isinstance(node, ast.Call) else None
    target = call.func if call is not None else node
    path = _attribute_path(target)
    if len(path) != 3 or path[:2] != ["pytest", "mark"]:
        return None
    args: list[str] = []
    if call is not None:
        for arg in call.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                args.append(arg.value)
    return path[2], args


def _markers_from_nodes(nodes: list[ast.AST]) -> dict[str, Any]:
    markers: dict[str, Any] = {}
    for node in nodes:
        parsed = _marker(node)
        if parsed is None:
            continue
        name, args = parsed
        if name == "mt":
            markers["mt"] = args[0] if args else None
            markers["requirements"] = args[1:]
        elif name == "req":
            markers["requirements"] = args
        else:
            markers[name] = True
    return markers


def _module_marker_nodes(tree: ast.Module) -> list[ast.AST]:
    nodes: list[ast.AST] = []
    for statement in tree.body:
        if not isinstance(statement, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in statement.targets):
            continue
        value = statement.value
        nodes.extend(value.elts if isinstance(value, (ast.List, ast.Tuple)) else [value])
    return nodes


def _verifies_ids(function: ast.FunctionDef) -> list[str]:
    docstring = ast.get_docstring(function) or ""
    match = re.search(r"(?ms)^\s*Verifies:\s*(.+?)(?:\n\s*\n|\Z)", docstring)
    return sorted(set(REQUIREMENT_RE.findall(match.group(1)))) if match else []


def source_inventory() -> dict[str, dict[str, Any]]:
    """Return one source-derived record per integration test function."""
    inventory: dict[str, dict[str, Any]] = {}
    for path in sorted(INTEGRATION_DIR.glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        module_markers = _markers_from_nodes(_module_marker_nodes(tree))
        for function in (n for n in tree.body if isinstance(n, ast.FunctionDef)):
            if not function.name.startswith("test_"):
                continue
            markers = dict(module_markers)
            markers.update(_markers_from_nodes(list(function.decorator_list)))
            nodeid = f"integration/{path.name}::{function.name}"
            inventory[nodeid] = {
                "nodeid": nodeid,
                "file": path.name,
                "line": function.lineno,
                "test": function.name,
                "markers": markers,
                "verifies": _verifies_ids(function),
            }
    return inventory


def collected_nodeids() -> set[str]:
    """Collect through pytest and return stable function-level node IDs."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "integration/", "--collect-only", "-q"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise CoverageError(
            "integration collection failed:\n" + (result.stdout + result.stderr).strip()
        )

    nodeids: set[str] = set()
    for raw in result.stdout.splitlines():
        line = raw.strip().replace("\\", "/")
        if "::test_" not in line or ".py::" not in line:
            continue
        if not line.startswith("integration/"):
            line = f"integration/{line}"
        nodeids.add(re.sub(r"\[[^]]*\]$", "", line))
    return nodeids


def manual_ids(path: Path = MANUAL_PLAN_PATH) -> set[str]:
    """Return every current manual-test ID defined by the plan."""
    found: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        match = MANUAL_ID_RE.match(line)
        if match:
            found.add(match.group(1))
    return found


def requirement_ids(paths: tuple[Path, ...] = SPEC_PATHS) -> set[str]:
    """Return requirement IDs defined by the SRS and architecture companion."""
    found: set[str] = set()
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("|"):
                match = re.match(r"^\|\s*((?:STR|FR|UIR|IFR|DR|CR|NFR)-\d+[a-z]?)\s*\|", line)
                if match:
                    found.add(match.group(1))
    return found


def _tier(markers: dict[str, Any]) -> str | None:
    present = [name for name in TIER_MARKERS if markers.get(name)]
    return present[0].replace("_", "-") if len(present) == 1 else None


def _evidence(manual_id: str | None) -> tuple[str, str]:
    if manual_id:
        return (
            "partial",
            "Semantically reviewed automated support; retained manual steps remain required.",
        )
    return (
        "supplementary",
        "Requirement evidence only; this test is not mapped to a manual workflow.",
    )


def build_entries(
    inventory: dict[str, dict[str, Any]], collected: set[str]
) -> list[dict[str, Any]]:
    """Combine source metadata with actual pytest collection."""
    entries: list[dict[str, Any]] = []
    for nodeid in sorted(collected):
        source = inventory.get(nodeid)
        if source is None:
            continue
        markers = source["markers"]
        manual_id = markers.get("mt")
        evidence, rationale = _evidence(manual_id)
        gated = [name for name in ("two_port", "flow_control", "destructive") if markers.get(name)]
        entries.append(
            {
                "nodeid": nodeid,
                "file": source["file"],
                "line": source["line"],
                "test": source["test"],
                "tier": _tier(markers),
                "markers": sorted(
                    name for name, value in markers.items() if value and name != "requirements"
                ),
                "manual_id": manual_id,
                "requirements": sorted(set(markers.get("requirements", []))),
                "evidence": evidence,
                "evidence_rationale": rationale,
                "manual_still_required": True,
                "gated": gated,
                "collection_status": "collected",
                "execution_status": "not-run-by-coverage-generator",
                "bench_evidence": "integration/results/runs_ledger.json"
                if markers.get("hil")
                else None,
                "semantic_review": "reviewed-2026-08-01",
                "verifies": source["verifies"],
            }
        )
    return entries


def destructive_audit(paths: list[Path] | None = None) -> list[str]:
    """Find whole-destination operations outside destructive-marked tests."""
    errors: list[str] = []
    audit_paths = paths or [INTEGRATION_DIR / "conftest.py", *INTEGRATION_DIR.glob("test_*.py")]
    destructive_calls = {"wipe_drive", "do_backup", "do_restore"}
    for path in audit_paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        module_markers = _markers_from_nodes(_module_marker_nodes(tree))
        for function in (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)):
            called = {
                call.func.attr
                for call in ast.walk(function)
                if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
            }
            risky = sorted(called & destructive_calls)
            if not risky:
                continue
            markers = dict(module_markers)
            markers.update(_markers_from_nodes(list(function.decorator_list)))
            if not function.name.startswith("test_") or not markers.get("destructive"):
                try:
                    display_path = path.relative_to(ROOT)
                except ValueError:
                    display_path = path
                errors.append(
                    f"{display_path}:{function.lineno}: {function.name} calls "
                    f"{', '.join(risky)} without a destructive test marker"
                )
    return errors


def validate(
    inventory: dict[str, dict[str, Any]],
    collected: set[str],
    entries: list[dict[str, Any]],
    known_manual_ids: set[str],
    known_requirement_ids: set[str],
) -> list[str]:
    """Return all structural, traceability, tier, and safety errors."""
    errors: list[str] = []
    for nodeid in sorted(collected - set(inventory)):
        errors.append(f"collected node has no source record: {nodeid}")
    for nodeid in sorted(set(inventory) - collected):
        errors.append(f"source test was not collected: {nodeid}")

    for entry in entries:
        location = f"integration/{entry['file']}:{entry['line']}"
        if entry["tier"] is None:
            errors.append(f"{location}: test must declare exactly one tier marker")
        manual_id = entry["manual_id"]
        if manual_id and manual_id not in known_manual_ids:
            errors.append(f"{location}: stale manual ID {manual_id}")
        stale_requirements = sorted(set(entry["requirements"]) - known_requirement_ids)
        if stale_requirements:
            errors.append(f"{location}: stale requirement IDs: {', '.join(stale_requirements)}")
        if entry["requirements"] != entry["verifies"]:
            errors.append(
                f"{location}: marker requirements {entry['requirements']} do not match "
                f"Verifies tag {entry['verifies']}"
            )
        if entry["evidence"] == "equivalent" and not entry["evidence_rationale"].strip():
            errors.append(f"{location}: equivalent evidence requires a rationale")

    errors.extend(destructive_audit())
    return errors


def build_manifest(entries: list[dict[str, Any]], known_manual_ids: set[str]) -> dict[str, Any]:
    """Build deterministic machine-readable coverage and decision records."""
    tiers: dict[str, int] = {}
    evidence_counts: dict[str, int] = {}
    requirements: set[str] = set()
    by_manual: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        tiers[entry["tier"]] = tiers.get(entry["tier"], 0) + 1
        evidence_counts[entry["evidence"]] = evidence_counts.get(entry["evidence"], 0) + 1
        requirements.update(entry["requirements"])
        if entry["manual_id"]:
            by_manual.setdefault(entry["manual_id"], []).append(entry)

    decisions: dict[str, dict[str, Any]] = {}
    for manual_id in sorted(known_manual_ids):
        supporting = by_manual.get(manual_id, [])
        if supporting:
            best = max((entry["evidence"] for entry in supporting), key=EVIDENCE_RANK.get)
            decisions[manual_id] = {
                "status": "automated-support",
                "tests": [entry["nodeid"] for entry in supporting],
                "best_evidence": best,
                "manual_still_required": any(
                    entry["manual_still_required"] for entry in supporting
                ),
                "note": "Reviewed automated support; see per-test rationale.",
            }
        else:
            decisions[manual_id] = {
                "status": "manual-only",
                "tests": [],
                "best_evidence": "manual-only",
                "manual_still_required": True,
                "note": "No semantically matching integration test is currently mapped.",
            }

    return {
        "version": "3.0",
        "generated": "deterministic",
        "semantic_review": "completed-2026-08-01",
        "total_tests": len(entries),
        "tiers": dict(sorted(tiers.items())),
        "evidence_classification": {
            name: evidence_counts.get(name, 0) for name in EVIDENCE_CLASSES
        },
        "manual_plan_total": len(known_manual_ids),
        "manual_ids_with_automated_support": len(by_manual),
        "raw_mapped_case_ratio": round(100 * len(by_manual) / len(known_manual_ids), 1),
        "manual_coverage_decisions": decisions,
        "requirement_ids": sorted(requirements),
        "tests": entries,
    }


def generate_report(manifest: dict[str, Any]) -> str:
    """Render a concise human-readable report from the manifest."""
    lines = [
        "# Integration Test Coverage Report",
        "",
        f"**Generated from:** `integration/coverage_manifest.json` v{manifest['version']}",
        f"**Total collected test functions:** {manifest['total_tests']}",
        "**Execution status:** Not run by this generator; physical outcomes remain in "
        "`integration/results/runs_ledger.json`.",
        "",
        "## Test Tiers",
        "",
        "| Tier | Count |",
        "|---|---:|",
    ]
    for tier, count in manifest["tiers"].items():
        lines.append(f"| {tier} | {count} |")

    lines.extend(["", "## Evidence Classification", "", "| Classification | Count |", "|---|---:|"])
    for evidence, count in manifest["evidence_classification"].items():
        lines.append(f"| {evidence} | {count} |")

    lines.extend(
        [
            "",
            "## Manual Scenario Decisions",
            "",
            f"- Manual plan cases: **{manifest['manual_plan_total']}**",
            "- Cases with reviewed automated support: "
            f"**{manifest['manual_ids_with_automated_support']}** "
            f"(**{manifest['raw_mapped_case_ratio']}%** raw mapped-case ratio)",
            "- Every remaining case has an explicit `manual-only` decision in the manifest.",
            "",
            "| MT-ID | Tests | Best evidence | Manual retained |",
            "|---|---:|---|---|",
        ]
    )
    for manual_id, decision in manifest["manual_coverage_decisions"].items():
        if decision["status"] != "automated-support":
            continue
        retained = "yes" if decision["manual_still_required"] else "no"
        lines.append(
            f"| {manual_id} | {len(decision['tests'])} | {decision['best_evidence']} | {retained} |"
        )

    lines.extend(
        [
            "",
            "## Test Inventory",
            "",
            "| Test | Tier | MT-ID | Requirements | Evidence | Gated |",
            "|---|---|---|---|---|---|",
        ]
    )
    for entry in manifest["tests"]:
        manual_id = entry["manual_id"] or "—"
        requirements = ", ".join(entry["requirements"]) or "—"
        gated = ", ".join(entry["gated"]) or "—"
        lines.append(
            f"| `{entry['test']}` | {entry['tier']} | {manual_id} | "
            f"{requirements} | {entry['evidence']} | {gated} |"
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- `partial` means the exact manual scenario has reviewed automated support, "
            "but retained steps or evidence remain.",
            "- `supplementary` means requirement evidence only; it does not count as a "
            "mapped manual scenario.",
            "- No test is currently labelled `equivalent`.",
            "- Pass, Fail, Blocked, Skipped, and N-A are execution outcomes and are not "
            "inferred from collection.",
            "",
        ]
    )
    return "\n".join(lines)


def _manifest_text(manifest: dict[str, Any]) -> str:
    return json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"


def _check_file(path: Path, expected: str) -> bool:
    actual = path.read_text(encoding="utf-8") if path.exists() else ""
    if actual == expected:
        return True
    diff = difflib.unified_diff(
        actual.splitlines(), expected.splitlines(), fromfile=str(path), tofile="generated"
    )
    print("\n".join(diff))
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="validate without rewriting")
    args = parser.parse_args(argv)

    try:
        inventory = source_inventory()
        collected = collected_nodeids()
    except (CoverageError, OSError, SyntaxError) as exc:
        print(f"[coverage] ERROR: {exc}", file=sys.stderr)
        return 2

    known_manual_ids = manual_ids()
    entries = build_entries(inventory, collected)
    errors = validate(
        inventory,
        collected,
        entries,
        known_manual_ids,
        requirement_ids(),
    )
    if errors:
        for error in errors:
            print(f"[coverage] ERROR: {error}", file=sys.stderr)
        return 1

    manifest = build_manifest(entries, known_manual_ids)
    manifest_text = _manifest_text(manifest)
    report_text = generate_report(manifest)
    if args.check:
        current = _check_file(MANIFEST_PATH, manifest_text)
        current &= _check_file(REPORT_PATH, report_text)
        if not current:
            print("[coverage] ERROR: generated coverage artifacts are stale", file=sys.stderr)
            return 1
        print(
            f"[coverage] check passed: {manifest['total_tests']} tests, "
            f"{manifest['manual_ids_with_automated_support']}/{manifest['manual_plan_total']} "
            "manual IDs mapped"
        )
        return 0

    MANIFEST_PATH.write_text(manifest_text, encoding="utf-8")
    REPORT_PATH.write_text(report_text, encoding="utf-8")
    print(f"[coverage] manifest written: {MANIFEST_PATH}")
    print(f"[coverage] report written: {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
