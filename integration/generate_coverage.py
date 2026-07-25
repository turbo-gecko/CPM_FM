"""Generate coverage_manifest.json and coverage_report.md from the integration suite.

Reads every collected test node, extracts its markers (mt / req), tier, and
evidence classification, then writes:

- ``integration/coverage_manifest.json`` — machine-readable evidence mapping
- ``integration/coverage_report.md`` — human-readable summary report

Run after adding/removing tests or changing markers::

    .venv/Scripts/python.exe -m integration.generate_coverage

The manifest is the source of truth for validation scripts and reports.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

MANIFEST_PATH = Path(__file__).parent / "coverage_manifest.json"
REPORT_PATH = Path(__file__).parent.parent / "docs" / "manual_test_plan.md"
SCORECARD_PATH = Path(__file__).parent.parent / "docs" / "manual_test_scorecard.md"

# --------------------------------------------------------------------------- #
# Evidence classification helpers
# --------------------------------------------------------------------------- #

EVIDENCE_CLASSES = ("equivalent", "partial", "supplementary", "manual-only")

# Tests that drive the full manual workflow with real serial peer → equivalent
_EQUIVALENT_NODES = frozenset({
    # Batch / transfer round-trips that exercise the complete manual scenario
    "integration/test_protocol_transfers.py::test_round_trip_sample_files[rc2014]",
    "integration/test_protocol_transfers.py::test_uploaded_file_visible_then_removable[rc2014]",
    "integration/test_protocol_listing.py::test_dir_listing_parses[rc2014]",
    "integration/test_gui_connect.py::test_connect_opens_ports_and_probes[rc2014]",
    "integration/test_gui_connect.py::test_disconnect_closes_ports_and_clears_list[rc2014]",
    "integration/test_gui_connect.py::test_reconnect_after_disconnect[rc2014]",
})

# Tests that exercise a meaningful subset but leave manual evidence unverified
_PARTIAL_NODES = frozenset({
    # Conflict resolution — real conflict but no apply-to-all batch (MT-CF08 req-only)
    "integration/test_gui_conflict.py::test_overwrite_existing_remote_file[rc2014]",
    "integration/test_gui_conflict.py::test_skip_existing_remote_file[rc2014]",
    # Filename validation — real prompt but MT-FV08 is req-only
    "integration/test_gui_validation.py::test_invalid_name_rename_uploads_conforming[rc2014]",
    "integration/test_gui_validation.py::test_invalid_name_skip_does_not_upload[rc2014]",
    # Drag-and-drop — internal drop only (no external file-manager gesture)
    "integration/test_gui_dragdrop.py::test_internal_drop_host_to_remote_uploads[rc2014]",
    "integration/test_gui_dragdrop.py::test_drop_cancelled_does_not_transfer[rc2014]",
    # History — single upload recorded, not the full history dialog workflow
    "integration/test_gui_history.py::test_upload_records_history_entry[rc2014]",
    # Context menu — real delete/rename but limited to two actions
    "integration/test_context_menu.py::test_remote_delete_removes_file[rc2014]",
    "integration/test_context_menu.py::test_remote_rename_changes_name[rc2014]",
    # Terminal window — live serial but not full-screen rendering or all menu items
    "integration/test_terminal_window.py::test_terminal_window_shows_live_response[rc2014]",
    "integration/test_terminal_window.py::test_terminal_window_keyboard_input[rc2014]",
    "integration/test_terminal_window.py::test_terminal_context_menu_copy_selection[rc2014]",
    "integration/test_terminal_window.py::test_terminal_context_menu_paste_sends_over_serial[rc2014]",
    "integration/test_terminal_window.py::test_terminal_context_menu_reset_size[rc2014]",
    "integration/test_terminal_window.py::test_terminal_context_menu_terminal_type_submenu[rc2014]",
    "integration/test_terminal_window.py::test_terminal_context_menu_macros_submenu_runs_over_serial[rc2014]",
    # Protocol boundary tests — req-only (MT-T17, MT-T18)
    "integration/test_protocol_transfers.py::test_round_trip_exactly_1024_bytes[rc2014]",
    "integration/test_protocol_transfers.py::test_recv_port_closed_mid_transfer_graceful_failure[rc2014]",
    # Connection recovery — req-only (MT-C16, MT-C17)
    "integration/test_gui_connect.py::test_connect_transport_open_failure_reports_error_and_skips_probe[rc2014]",
    "integration/test_gui_connect.py::test_rapid_disconnect_during_probe_no_crash[rc2014]",
    # Conflict apply-to-all — req-only (MT-CF08)
    "integration/test_gui_conflict.py::test_conflict_apply_to_all_persists_across_batch[rc2014]",
    # Filename special chars — req-only (MT-FV08)
    "integration/test_gui_validation.py::test_invalid_name_special_chars_sanitized[rc2014]",
    # Smoke test — req-only (MT-SMOKE)
    "integration/test_smoke.py::test_peer_connects_and_sees_ccp_prompt[rc2014]",
    # Two-port specific — req-only (MT-C16, MT-T18)
    "integration/test_gui_connect.py::test_disconnect_prompt_with_ports_swapped[rc2014]",
    # Config reload while connected — valid MT but partial workflow
    "integration/test_gui_connect.py::test_load_config_while_connected_closes_ports[rc2014]",
    # User-area listing — real switch but limited scenarios
    "integration/test_protocol_listing.py::test_user_area_switch_lists[rc2014]",
    "integration/test_protocol_listing.py::test_transfer_targets_selected_user_area[rc2014]",
    # Drive change — real but single scenario
    "integration/test_protocol_listing.py::test_change_to_scratch_drive[rc2014]",
    # Empty/single-file listing — partial evidence
    "integration/test_protocol_listing.py::test_dir_listing_empty_directory[rc2014]",
    "integration/test_protocol_listing.py::test_dir_listing_single_file[rc2014]",
    "integration/test_protocol_listing.py::test_detect_current_drive[rc2014]",
    # 1K / checksum round-trips — gated, partial evidence
    "integration/test_protocol_transfers.py::test_round_trip_1k[rc2014]",
    "integration/test_protocol_transfers.py::test_round_trip_checksum[rc2014]",
    "integration/test_protocol_transfers.py::test_round_trip_zero_byte_file[rc2014]",
    "integration/test_protocol_transfers.py::test_round_trip_exactly_128_bytes[rc2014]",
    # Terminal clear — partial (MT-W05 is autoscroll, not clear)
    "integration/test_terminal_window.py::test_terminal_window_clear[rc2014]",
    # VT100 escape sequences — visual rendering, partial
    "integration/test_terminal_window.py::test_terminal_vt100_escape_sequences_render_without_crash[rc2014]",
})

# Destructive tests are always partial (require --run-destructive + bench)
_DESTRUCTIVE_NODES = frozenset({
    "integration/test_gui_backup_restore.py::test_restore_wipes_scratch_then_uploads[rc2014]",
    "integration/test_gui_backup_restore.py::test_restore_erase_all_sequence_wipes_scratch[rc2014]",
    "integration/test_gui_backup_restore.py::test_backup_downloads_remote_to_host[rc2014]",
})

# Visual tests — widget-tree assertions, no peer required
_VISUAL_NODES = frozenset({
    "integration/test_visual_assertions.py::test_window_title_contains_app_name",
    "integration/test_visual_assertions.py::test_remote_list_empty_at_startup",
    "integration/test_visual_assertions.py::test_menubar_has_file_and_help",
    "integration/test_visual_assertions.py::test_drive_combo_lists_a_to_p",
    "integration/test_visual_assertions.py::test_lists_have_context_menus",
    "integration/test_visual_assertions.py::test_main_panes_have_push_buttons",
    "integration/test_visual_assertions.py::test_material_theme_applied",
    "integration/test_visual_assertions.py::test_terminal_window_has_no_control_row_and_font_in_context_menu",
    "integration/test_visual_assertions.py::test_font_dialog_lists_usable_under_material_theme",
    "integration/test_visual_assertions.py::test_about_dialog_contents",
    "integration/test_visual_assertions.py::test_manual_dialog_renders",
    "integration/test_visual_assertions.py::test_i18n_language_switch_updates_ui",
})


def classify(nodeid: str, has_destructive: bool) -> str:
    """Return the evidence classification for a test node."""
    if has_destructive:
        return "partial"  # destructive tests always need bench + --run-destructive
    if nodeid in _EQUIVALENT_NODES:
        return "equivalent"
    if nodeid in _PARTIAL_NODES or nodeid in _VISUAL_NODES:
        return "partial"
    return "supplementary"


def tier_for(nodeid: str, has_visual: bool, has_hil: bool) -> str:
    """Return the test tier string."""
    if has_visual:
        return "visual"
    if has_hil:
        return "hil"
    return "gui-integration"


# --------------------------------------------------------------------------- #
# Collection
# --------------------------------------------------------------------------- #

def collect_tests() -> list[dict[str, Any]]:
    """Parse pytest collection output and build the manifest entries."""
    import subprocess

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "integration/", "--collect-only", "-q"],
        capture_output=True, text=True, cwd=Path(__file__).parent.parent,
    )
    lines = result.stdout.strip().splitlines()

    entries: list[dict[str, Any]] = []
    for line in lines:
        if not line.strip() or (not line.startswith("test_") and "[" not in line):
            continue
        # Parse nodeid like: integration/test_foo.py::test_bar[target]
        match = re.match(r"^(?:integration/)?(.+\.py)::(.+)$", line.strip())
        if not match:
            continue
        file_part, test_name_with_param = match.groups()
        # Strip pytest parametrization suffix (e.g., [rc2014])
        test_name = re.sub(r"\[.*\]$", "", test_name_with_param)
        nodeid = f"integration/{file_part}::{test_name_with_param}"

        # Determine markers by reading the source file
        filepath = Path(__file__).parent / file_part
        markers = parse_markers(filepath, test_name)

        has_hil = "hil" in markers
        has_visual = "visual" in markers
        has_destructive = "destructive" in markers
        has_two_port = "two_port" in markers

        mt_id = markers.get("mt")  # first arg of mt marker, or None
        req_ids = markers.get("req", [])  # list from req marker

        entry = {
            "nodeid": nodeid,
            "file": file_part,
            "test": test_name,
            "tier": tier_for(nodeid, has_visual, has_hil),
            "markers": sorted(markers.keys()),
            "manual_id": mt_id,
            "requirements": sorted(set(req_ids)),
            "evidence": classify(nodeid, has_destructive),
            "gated": [] if not (has_two_port or has_destructive) else (
                ["two_port"] if has_two_port else ["destructive"]
            ),
        }
        entries.append(entry)

    return entries


def parse_markers(filepath: Path, test_name: str) -> dict[str, Any]:
    """Extract markers for a test function from its source file."""
    content = filepath.read_text(encoding="utf-8")
    lines = content.splitlines()

    # Check for module-level pytestmark (e.g. pytestmark = [pytest.mark.hil, ...] or pytestmark = pytest.mark.visual)
    module_markers: dict[str, Any] = {}
    for line in lines:
        stripped = line.strip()
        pm_match = re.match(r"pytestmark\s*=\s*(.+)", stripped)
        if pm_match:
            args_str = pm_match.group(1)
            # Handle both list [...] and single pytest.mark.xxx forms
            if args_str.startswith("["):
                # List form: extract content between [ and ]
                inner = args_str[1:]
                if inner.endswith("]"):
                    inner = inner[:-1]
                args_str = inner
            for m in re.finditer(r'pytest\.mark\.(\w+)(?:\(([^)]*)\))?', args_str):
                mark_name = m.group(1)
                args_str_inner = m.group(2) or ""
                args = re.findall(r'"([^"]*)"', args_str_inner) if args_str_inner else []
                module_markers[mark_name] = True

    # Find the line where the target test function is defined
    test_line_idx = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("def ") and f"def {test_name}(" in stripped:
            test_line_idx = i
            break

    if test_line_idx is None:
        return module_markers  # return module markers even if test not found

    # Collect decorators immediately above the test function (backwards from def)
    decorator_lines: list[str] = []
    for i in range(test_line_idx - 1, -1, -1):
        stripped = lines[i].strip()
        if stripped.startswith("@pytest.mark."):
            decorator_lines.append(stripped)
        elif stripped == "" or stripped.startswith("#"):
            continue  # skip blank lines and comments between decorators
        else:
            break  # hit a non-decorator line

    markers: dict[str, Any] = {}
    # Start with module-level markers (test-level can override by presence)
    markers.update(module_markers)

    for dec in reversed(decorator_lines):  # restore original order
        # Parse @pytest.mark.mt("MT-T03", "FR-081") or @pytest.mark.hil (no args)
        mark_match = re.match(r"@pytest\.mark\.(\w+)(?:\((.+)\))?", dec)
        if not mark_match:
            continue
        mark_name = mark_match.group(1)
        args_str = mark_match.group(2) or ""
        # Simple arg parsing (handles strings and basic types)
        args = re.findall(r'"([^"]*)"', args_str) if args_str else []
        if mark_name == "mt":
            markers["mt"] = args[0] if args else None
            markers["req"] = args[1:] if len(args) > 1 else []
        elif mark_name == "req":
            markers["req"] = args
        else:
            # Tier/safety markers (hil, visual, two_port, destructive)
            markers[mark_name] = True

    return markers


# --------------------------------------------------------------------------- #
# Manifest generation
# --------------------------------------------------------------------------- #

def build_manifest(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Build the full manifest structure."""
    # Group by manual ID
    mt_groups: dict[str, list[str]] = {}
    for e in entries:
        mid = e["manual_id"]
        if mid:
            mt_groups.setdefault(mid, []).append(e["nodeid"])

    # Collect all unique requirement IDs
    all_reqs: set[str] = set()
    for e in entries:
        all_reqs.update(e["requirements"])

    # Evidence classification counts
    evidence_counts: dict[str, int] = {}
    for e in entries:
        evidence_counts[e["evidence"]] = evidence_counts.get(e["evidence"], 0) + 1

    # Tier counts
    tier_counts: dict[str, int] = {}
    for e in entries:
        tier_counts[e["tier"]] = tier_counts.get(e["tier"], 0) + 1

    return {
        "version": "2.1",
        "generated": "auto",
        "total_tests": len(entries),
        "tiers": tier_counts,
        "evidence_classification": evidence_counts,
        "manual_id_coverage": {
            mid: {"tests": nodes, "count": len(nodes)}
            for mid, nodes in sorted(mt_groups.items())
        },
        "requirement_ids": sorted(all_reqs),
        "tests": entries,
    }


# --------------------------------------------------------------------------- #
# Report generation
# --------------------------------------------------------------------------- #

def generate_report(manifest: dict[str, Any]) -> str:
    """Generate the markdown coverage report."""
    lines: list[str] = []
    lines.append("# Integration Test Coverage Report")
    lines.append("")
    lines.append(f"**Generated from:** `integration/coverage_manifest.json` v{manifest['version']}")
    lines.append(f"**Total automated tests:** {manifest['total_tests']}")
    lines.append("")

    # Tiers
    lines.append("## Test Tiers")
    lines.append("")
    lines.append("| Tier | Count |")
    lines.append("|---|---:|")
    for tier, count in sorted(manifest["tiers"].items()):
        lines.append(f"| {tier} | {count} |")
    lines.append("")

    # Evidence classification
    lines.append("## Evidence Classification")
    lines.append("")
    lines.append("| Classification | Count |")
    lines.append("|---|---:|")
    for cls in EVIDENCE_CLASSES:
        count = manifest["evidence_classification"].get(cls, 0)
        lines.append(f"| {cls} | {count} |")
    lines.append("")

    # Manual ID coverage summary
    mt_coverage = manifest["manual_id_coverage"]
    lines.append(f"## Manual ID Coverage ({len(mt_coverage)} unique IDs)")
    lines.append("")
    if mt_coverage:
        lines.append("| MT-ID | Tests | Evidence |")
        lines.append("|---|---|---|")
        for mid, info in sorted(mt_coverage.items()):
            nodes = info["tests"]
            evidence = "partial"  # default; would need per-test lookup
            lines.append(f"| {mid} | {info['count']} | {evidence} |")
    else:
        lines.append("*No manual IDs mapped.*")
    lines.append("")

    # Requirement coverage
    reqs = manifest["requirement_ids"]
    lines.append(f"## Requirements Covered ({len(reqs)} unique)")
    lines.append("")
    if reqs:
        lines.append("".join(f"`{r}` " for r in reqs))
    else:
        lines.append("*No requirements tagged.*")
    lines.append("")

    # Full test inventory
    lines.append("## Test Inventory")
    lines.append("")
    lines.append("| Node ID | Tier | MT-ID | Requirements | Evidence | Gated |")
    lines.append("|---|---|---|---|---|---|")
    for e in manifest["tests"]:
        mt = e["manual_id"] or "—"
        reqs_str = ", ".join(e["requirements"]) if e["requirements"] else "—"
        gated = ", ".join(e["gated"]) if e["gated"] else "—"
        lines.append(
            f"| `{e['test']}` | {e['tier']} | {mt} | {reqs_str} | {e['evidence']} | {gated} |"
        )
    lines.append("")

    # Untested manual IDs note
    lines.append("## Notes")
    lines.append("")
    lines.append("- Tests marked `partial` exercise a meaningful subset but leave some manual evidence unverified.")
    lines.append("- Tests marked `supplementary` verify related internal logic but do not perform the manual workflow.")
    lines.append("- Destructive tests require `--run-destructive` and a configured scratch drive.")
    lines.append("- Two-port gated tests require a target with distinct Terminal/Transport ports.")
    lines.append("")

    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main():
    entries = collect_tests()
    manifest = build_manifest(entries)

    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"[coverage] manifest written: {MANIFEST_PATH} ({manifest['total_tests']} tests)")

    report = generate_report(manifest)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Actually write to integration/coverage_report.md per plan convention
    INTEGRATION_REPORT = Path(__file__).parent / "coverage_report.md"
    INTEGRATION_REPORT.write_text(report, encoding="utf-8")
    print(f"[coverage] report written: {INTEGRATION_REPORT}")

    # Validation summary
    stale_mt = [e["nodeid"] for e in entries if e["manual_id"] and not e["manual_id"].startswith("MT-")]
    orphan_reqs = [r for r in manifest["requirement_ids"] if not any(
        r.startswith(("FR-", "NFR-", "DR-", "UIR-")) for r in [r]
    )]
    if stale_mt:
        print(f"[coverage] WARNING: {len(stale_mt)} tests have non-MT manual IDs")
    if orphan_reqs:
        print(f"[coverage] WARNING: {len(orphan_reqs)} requirement IDs may be stale")
    else:
        print("[coverage] validation passed: no stale markers or requirement IDs detected")


if __name__ == "__main__":
    main()
