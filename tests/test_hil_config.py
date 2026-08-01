"""Tests for the integration harness target-configuration schema."""

from __future__ import annotations

import json

import pytest

from integration.helpers.config import CPM_TYPES, HilConfigError, load_hil_config


def _write_config(tmp_path, target_spec: dict) -> str:
    path = tmp_path / "hil_config.json"
    path.write_text(json.dumps({"default_target": "bench", "targets": {"bench": target_spec}}))
    return str(path)


def test_cpm_type_defaults_to_22(tmp_path):
    """An existing target without the new field remains base CP/M compatible."""
    config = load_hil_config(_write_config(tmp_path, {}))

    assert config.targets["bench"].cpm_type == "2.2"


@pytest.mark.parametrize("cpm_type", CPM_TYPES)
def test_cpm_type_accepts_each_declared_value(tmp_path, cpm_type):
    """Every value in the documented CP/M-family schema is preserved."""
    config = load_hil_config(_write_config(tmp_path, {"cpm_type": cpm_type}))

    assert config.targets["bench"].cpm_type == cpm_type


@pytest.mark.parametrize("cpm_type", ["3", "NZCOM", "zcpr", 2.2, None])
def test_cpm_type_rejects_unknown_or_non_string_values(tmp_path, cpm_type):
    """Invalid values cannot silently enable or disable specialized tests."""
    path = _write_config(tmp_path, {"cpm_type": cpm_type})

    with pytest.raises(
        HilConfigError,
        match=r"invalid cpm_type for target 'bench'.*2\.2, ZSDOS, ZCPR, QPM",
    ):
        load_hil_config(path)
