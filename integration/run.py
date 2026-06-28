"""Interactive bench launcher for the HIL suite (plan §2.2).

Reads ``hil_config.json``, prints a numbered menu of registered targets, lets the
operator pick one / several / all, then shells out to ``pytest integration/``
with the corresponding ``--target`` flags.

Run it as either::

    python integration/run.py
    python -m integration.run        # from the repo root

Extra pytest arguments are forwarded verbatim. The ``--`` separator is optional,
so both of these work the same::

    python integration/run.py --run-destructive
    python integration/run.py -- -k transfers --run-destructive
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# Make `helpers` importable whether launched as a script or via -m.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from helpers.config import HilConfigError, load_hil_config  # noqa: E402

REPO_ROOT = _HERE.parent


def _split_passthrough(argv: list[str]) -> list[str]:
    """Pytest args to forward: everything after an optional ``--`` separator.

    When no ``--`` is present, forward *all* args, so ``run.py --run-destructive``
    works the same as ``run.py -- --run-destructive`` (run.py has no options of
    its own — every arg is destined for pytest).
    """
    if "--" in argv:
        return argv[argv.index("--") + 1 :]
    return list(argv)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    passthrough = _split_passthrough(argv)

    try:
        cfg = load_hil_config()
    except HilConfigError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    names = list(cfg.targets)
    print("cpm-fm HIL harness — select target(s):\n")
    for i, name in enumerate(names, start=1):
        t = cfg.targets[name]
        default = "  (default)" if name == cfg.default_target else ""
        print(f"  {i}. {name}{default} — {t.description}")
    print(f"  {len(names) + 1}. ALL targets")
    print()

    choice = input("Enter number(s), comma-separated [default]: ").strip()
    selected: list[str] = []
    all_targets = False
    if not choice:
        if not cfg.default_target:
            print("error: no default_target set; pick a number", file=sys.stderr)
            return 2
        selected = [cfg.default_target]
    else:
        for tok in choice.replace(",", " ").split():
            if not tok.isdigit():
                print(f"error: invalid selection {tok!r}", file=sys.stderr)
                return 2
            idx = int(tok)
            if idx == len(names) + 1:
                all_targets = True
            elif 1 <= idx <= len(names):
                selected.append(names[idx - 1])
            else:
                print(f"error: selection {idx} out of range", file=sys.stderr)
                return 2

    pytest_args = [sys.executable, "-m", "pytest", "integration/"]
    if all_targets:
        pytest_args.append("--all-targets")
    else:
        for name in selected:
            pytest_args += ["--target", name]
    pytest_args += passthrough

    label = "ALL" if all_targets else ", ".join(selected)
    print(f"\nRunning against: {label}")
    print("  " + " ".join(pytest_args) + "\n")
    return subprocess.call(pytest_args, cwd=str(REPO_ROOT), env=os.environ.copy())


if __name__ == "__main__":
    raise SystemExit(main())
