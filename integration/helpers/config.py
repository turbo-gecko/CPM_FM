"""Load and resolve the HIL harness configuration (``hil_config.json``).

The harness is parameterised by *targets*. Each target names one app settings
file (the same JSON the real ``cpm-fm`` app loads) plus a little bench-only
metadata that is not part of the app config (which drive is disposable, whether a
spare port exists, the per-target X-Modem sender capabilities, etc.). See the
plan in ``temp/integration_test_harness_plan.md`` §2 and the committed template
``hil_config.example.json``.

Ports, baud, EOL, and the remote command templates always come from the target's
settings file (parsed with the app's own ``utils.config_handler``, so both the
flat and nested config shapes Just Work) — the harness never duplicates them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cpm_fm.utils.config_handler import ConfigHandler

# integration/helpers/config.py -> parents[2] is the repo root.
REPO_ROOT = Path(__file__).resolve().parents[2]
INTEGRATION_DIR = REPO_ROOT / "integration"
HIL_CONFIG = INTEGRATION_DIR / "hil_config.json"
HIL_CONFIG_EXAMPLE = INTEGRATION_DIR / "hil_config.example.json"

# EOL keyword -> wire bytes, mirroring cpm_fm.gui.mw_remote.EOL_MAP. Duplicated
# here (rather than imported) so the protocol tier stays free of any GUI import
# (CR-014).
EOL_MAP = {"CR": "\r", "LF": "\n", "CRLF": "\r\n"}


class HilConfigError(RuntimeError):
    """Raised when the HIL configuration is missing or unusable."""


@dataclass
class Target:
    """One hardware target: an app settings file plus bench-only metadata."""

    name: str
    description: str = ""
    settings_file: str = ""
    two_port: bool = False
    spare_port: str | None = None
    scratch_drive: str | None = None
    # The declared PROTECTED home/working drive. The destructive guard requires
    # scratch_drive != connect_drive, comparing against THIS declared value (not
    # the live current prompt), so a scratch drive can never coincide with the
    # drive the operator considers precious.
    connect_drive: str | None = None
    has_1k_sender: bool = False
    has_checksum_sender: bool = False
    flow_control_peer: bool = False
    _settings: dict[str, Any] | None = field(default=None, repr=False, compare=False)

    @property
    def settings_path(self) -> Path:
        """Absolute path to the target's app settings file.

        A relative ``settings_file`` is resolved against the repo root so the
        committed example template stays portable across checkouts.
        """
        p = Path(self.settings_file)
        return p if p.is_absolute() else (REPO_ROOT / p)

    def load_settings(self) -> dict[str, Any]:
        """Parse (and cache) the target's app settings via the app's loader."""
        if self._settings is None:
            path = self.settings_path
            if not path.exists():
                raise HilConfigError(f"settings_file for target {self.name!r} not found: {path}")
            self._settings = ConfigHandler.load_json(str(path))
            if not self._settings:
                raise HilConfigError(
                    f"settings_file for target {self.name!r} is empty/unparseable: {path}"
                )
        return self._settings

    def eol(self) -> str:
        """The configured end-of-line bytes for this target (default CR)."""
        return EOL_MAP.get(str(self.load_settings().get("eol", "CR")), "\r")


@dataclass
class HilConfig:
    default_target: str | None
    targets: dict[str, Target]


def _target_from_spec(name: str, spec: dict[str, Any]) -> Target:
    return Target(
        name=name,
        description=str(spec.get("description", "")),
        settings_file=str(spec.get("settings_file", "")),
        two_port=bool(spec.get("two_port", False)),
        spare_port=spec.get("spare_port"),
        scratch_drive=spec.get("scratch_drive"),
        connect_drive=spec.get("connect_drive"),
        has_1k_sender=bool(spec.get("has_1k_sender", False)),
        has_checksum_sender=bool(spec.get("has_checksum_sender", False)),
        flow_control_peer=bool(spec.get("flow_control_peer", False)),
    )


def load_hil_config(path: str | Path | None = None) -> HilConfig:
    """Load ``hil_config.json`` (or the given path) into a :class:`HilConfig`.

    Raises :class:`HilConfigError` if the file is missing or malformed so callers
    (the conftest plugin, ``run.py``) can present a clear bench-side reason.
    """
    cfg_path = Path(path) if path else HIL_CONFIG
    if not cfg_path.exists():
        raise HilConfigError(
            f"{cfg_path} not found. Copy {HIL_CONFIG_EXAMPLE.name} to "
            f"{HIL_CONFIG.name} and edit it for your bench."
        )
    try:
        data = json.loads(cfg_path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        raise HilConfigError(f"could not read {cfg_path}: {e}") from e

    targets = {
        name: _target_from_spec(name, spec) for name, spec in data.get("targets", {}).items()
    }
    if not targets:
        raise HilConfigError(f"{cfg_path} defines no targets")
    return HilConfig(default_target=data.get("default_target"), targets=targets)


def resolve_targets(
    cfg: HilConfig,
    names: list[str] | None = None,
    all_targets: bool = False,
) -> list[Target]:
    """Resolve which targets to run from the CLI selection.

    Precedence: ``all_targets`` (every registered target), then explicit
    ``names`` (one or several, repeatable), then the ``default_target`` fallback.
    Raises :class:`HilConfigError` on an unknown name or a missing/unset default.
    """
    if all_targets:
        return list(cfg.targets.values())
    if names:
        resolved = []
        for n in names:
            if n not in cfg.targets:
                raise HilConfigError(f"unknown target {n!r}; known: {', '.join(cfg.targets)}")
            resolved.append(cfg.targets[n])
        return resolved
    if cfg.default_target:
        if cfg.default_target not in cfg.targets:
            raise HilConfigError(
                f"default_target {cfg.default_target!r} is not a registered target"
            )
        return [cfg.targets[cfg.default_target]]
    raise HilConfigError("no target selected: pass --target/--all-targets or set default_target")
