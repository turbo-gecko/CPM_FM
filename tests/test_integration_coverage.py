"""Regression tests for the integration evidence generator."""

from integration import generate_coverage


def test_destructive_audit_flags_unmarked_whole_drive_wipe(tmp_path):
    """An unmarked whole-drive wipe is rejected (test-tooling invariant)."""
    source = tmp_path / "test_unsafe.py"
    source.write_text(
        "def test_unsafe(peer):\n    peer.wipe_drive('J')\n",
        encoding="utf-8",
    )

    errors = generate_coverage.destructive_audit([source])

    assert len(errors) == 1
    assert "test_unsafe calls wipe_drive without a destructive test marker" in errors[0]


def test_destructive_audit_accepts_marked_whole_drive_wipe(tmp_path):
    """A destructive-marked wipe passes the audit (test-tooling invariant)."""
    source = tmp_path / "test_safe.py"
    source.write_text(
        "import pytest\n"
        "\n"
        "@pytest.mark.hil\n"
        "@pytest.mark.destructive\n"
        "def test_safe(peer):\n"
        "    peer.wipe_drive('J')\n",
        encoding="utf-8",
    )

    assert generate_coverage.destructive_audit([source]) == []


def test_manifest_decides_every_manual_case():
    """Mapped and unmapped IDs both get decisions (test-tooling invariant)."""
    entries = [
        {
            "nodeid": "integration/test_demo.py::test_demo",
            "tier": "hil",
            "evidence": "partial",
            "requirements": ["FR-001"],
            "manual_id": "MT-A01",
            "manual_still_required": True,
        }
    ]

    manifest = generate_coverage.build_manifest(entries, {"MT-A01", "MT-A02"})

    decisions = manifest["manual_coverage_decisions"]
    assert set(decisions) == {"MT-A01", "MT-A02"}
    assert decisions["MT-A01"]["status"] == "automated-support"
    assert decisions["MT-A02"]["status"] == "manual-only"
