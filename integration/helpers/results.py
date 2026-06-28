"""Run tracking & results (plan §7).

Builds a self-contained artifact directory per (run, target) and appends a
compact header to a committed ledger so run history is reviewable in git without
committing bulky artifacts.

Layout::

    integration/results/
      runs_ledger.json                    # COMMITTED: one entry per (run, target)
      <target>/<UTC-ts>_<git-sha>/        # GITIGNORED: full artifacts
          run.json                        # full structured record
          report.md                       # human-readable summary
          junit.xml                       # machine-readable (generated here)
          console.log                     # captured output

Outcomes recorded per test: Pass / Fail / Blocked / Skipped / N-A / Error.
``Blocked`` and ``N-A`` are signalled by a test calling ``pytest.skip`` with a
reason starting ``BLOCKED:`` / ``N/A:`` (see ``helpers.ids``).
"""

from __future__ import annotations

import getpass
import json
import logging
import os
import platform
import subprocess
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import REPO_ROOT, Target
from .ids import BLOCKED_PREFIX, NA_PREFIX
from .settings_copy import file_sha256

RESULTS_DIR = REPO_ROOT / "integration" / "results"
LEDGER = RESULTS_DIR / "runs_ledger.json"

# The MT outcome vocabulary (plan §6/§7).
PASS, FAIL, BLOCKED, SKIPPED, NA, ERROR = (
    "Pass",
    "Fail",
    "Blocked",
    "Skipped",
    "N-A",
    "Error",
)


def _git(*args: str) -> str:
    try:
        out = subprocess.run(
            ["git", *args],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=10,
        )
        return out.stdout.strip()
    except Exception:
        return ""


def _git_info() -> dict[str, Any]:
    branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    sha = _git("rev-parse", "HEAD")
    dirty = bool(_git("status", "--porcelain"))
    return {"branch": branch, "commit": sha, "dirty": dirty}


def _pkg_version(name: str) -> str:
    try:
        from importlib.metadata import version

        return version(name)
    except Exception:
        return "unknown"


def _app_version() -> str:
    try:
        return (REPO_ROOT / "src" / "version.txt").read_text().strip()
    except OSError:
        return "unknown"


def _manual_test_plan_version() -> str:
    """Best-effort scrape of the manual test plan version line."""
    path = REPO_ROOT / "docs" / "manual_test_plan.md"
    try:
        for line in path.read_text(encoding="utf-8").splitlines()[:40]:
            low = line.lower()
            if "version" in low:
                return line.strip().lstrip("#").strip()
    except OSError:
        pass
    return "unknown"


class RecorderLogHandler(logging.Handler):
    """Routes ``hil.*`` log records into the recorder's per-test trace buffer.

    Used instead of pytest's ``report.caplog`` (which, with ``log_cli`` enabled,
    is duplicated across phases and carries ANSI colour codes). The plain
    formatter here yields one clean line per record for ``console.log``.
    """

    def __init__(self, recorder: ResultsRecorder):
        super().__init__()
        self._recorder = recorder
        self.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%H:%M:%S")
        )

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._recorder.capture_log(self.format(record))
        except Exception:  # never let logging break a test run
            pass


@dataclass
class TestRecord:
    nodeid: str
    mt_id: str | None
    reqs: list[str]
    outcome: str
    duration: float
    message: str = ""
    observation: str = ""


@dataclass
class _Pending:
    """Accumulates the setup/call/teardown reports for one test item."""

    nodeid: str
    mt_id: str | None
    reqs: list[str]
    target: str
    outcome: str = SKIPPED
    duration: float = 0.0
    message: str = ""
    observation: str = ""
    capstdout: str = ""
    finished: bool = False


class ResultsRecorder:
    """Collects per-test outcomes and writes per-target run artifacts + ledger."""

    def __init__(self, targets: list[Target], flags: dict[str, Any]):
        self.targets = {t.name: t for t in targets}
        self.flags = flags
        self.start = datetime.now(timezone.utc)
        self.sha = _git("rev-parse", "--short", "HEAD") or "nogit"
        self.run_id = f"{self.start.strftime('%Y%m%dT%H%M%SZ')}_{self.sha}"
        self._pending: dict[str, _Pending] = {}
        # Per-test step-trace lines, keyed by nodeid. Populated by a dedicated
        # logging handler (see ``conftest._install_log_capture``) rather than
        # ``report.caplog``, which with ``log_cli`` on is duplicated across phases
        # and carries ANSI colour codes. Keyed independently of ``_pending`` so
        # logs emitted during fixture *setup* (before the call report creates the
        # pending record) are still captured.
        self._logs: dict[str, list[str]] = {}
        self._current: str | None = None

    # ----- collection-time -------------------------------------------------

    def set_current(self, nodeid: str | None) -> None:
        """Mark which test the log-capture handler should attribute lines to."""
        self._current = nodeid

    def capture_log(self, line: str) -> None:
        """Append one formatted log line to the current test's trace."""
        if self._current is not None:
            self._logs.setdefault(self._current, []).append(line)

    def start_item(self, nodeid: str, mt_id: str | None, reqs: list[str], target: str) -> None:
        self._pending[nodeid] = _Pending(nodeid=nodeid, mt_id=mt_id, reqs=reqs, target=target)

    def add_report(self, report) -> None:
        """Fold one phase report (setup/call/teardown) into the pending record."""
        p = self._pending.get(report.nodeid)
        if p is None:
            return
        if getattr(report, "capstdout", ""):
            p.capstdout += report.capstdout
        # An attached observation (set via record_property("observation", ...)).
        for key, val in getattr(report, "user_properties", []):
            if key == "observation" and val:
                p.observation = str(val)

        if report.when == "call":
            p.duration += report.duration
            if report.passed:
                p.outcome = PASS
            elif report.failed:
                p.outcome = FAIL
                p.message = self._longrepr(report)
            elif report.skipped:
                p.outcome, p.message = self._skip_outcome(report)
        elif report.when == "setup":
            p.duration += report.duration
            if report.failed:
                p.outcome = ERROR
                p.message = self._longrepr(report)
                p.finished = True
            elif report.skipped:
                p.outcome, p.message = self._skip_outcome(report)
                p.finished = True
        elif report.when == "teardown":
            if report.failed and p.outcome == PASS:
                p.outcome = ERROR
                p.message = self._longrepr(report)

    @staticmethod
    def _skip_outcome(report) -> tuple[str, str]:
        reason = ""
        longrepr = getattr(report, "longrepr", None)
        if isinstance(longrepr, tuple) and len(longrepr) == 3:
            reason = str(longrepr[2])
        else:
            reason = str(longrepr or "")
        stripped = reason.split("Skipped: ", 1)[-1].strip()
        if stripped.startswith(BLOCKED_PREFIX):
            return BLOCKED, stripped[len(BLOCKED_PREFIX) :].strip()
        if stripped.startswith(NA_PREFIX):
            return NA, stripped[len(NA_PREFIX) :].strip()
        return SKIPPED, stripped

    @staticmethod
    def _longrepr(report) -> str:
        return str(getattr(report, "longrepr", "") or "")[:8000]

    # ----- session finish --------------------------------------------------

    def finish(self) -> list[Path]:
        """Write artifacts for every target seen and append ledger entries."""
        by_target: dict[str, list[_Pending]] = {}
        for p in self._pending.values():
            by_target.setdefault(p.target, []).append(p)

        written: list[Path] = []
        ledger_entries = []
        for target_name, records in sorted(by_target.items()):
            run_dir = RESULTS_DIR / target_name / self.run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            run_json, summary = self._build_run_json(target_name, records)
            (run_dir / "run.json").write_text(json.dumps(run_json, indent=2), encoding="utf-8")
            (run_dir / "report.md").write_text(
                self._build_report_md(run_json, summary), encoding="utf-8"
            )
            (run_dir / "junit.xml").write_bytes(self._build_junit(target_name, records))
            (run_dir / "console.log").write_text(
                "".join(self._console_block(p) for p in records),
                encoding="utf-8",
            )
            written.append(run_dir)
            ledger_entries.append(self._ledger_entry(target_name, run_json, summary, run_dir))

        self._append_ledger(ledger_entries)
        return written

    def _console_block(self, p: _Pending) -> str:
        """One per-test section for console.log: stdout then the step-log trace."""
        out = [f"===== {p.nodeid} =====\n"]
        if p.capstdout:
            out.append(p.capstdout)
            if not p.capstdout.endswith("\n"):
                out.append("\n")
        lines = self._logs.get(p.nodeid)
        if lines:
            out.append("----- log -----\n")
            out.extend(line + "\n" for line in lines)
        return "".join(out)

    def _build_run_json(
        self, target_name: str, records: list[_Pending]
    ) -> tuple[dict[str, Any], Counter]:
        target = self.targets.get(target_name)
        settings_path = str(target.settings_path) if target else ""
        settings_sha = (
            file_sha256(target.settings_path) if target and target.settings_path.exists() else ""
        )
        summary = Counter(p.outcome for p in records)
        mt_executed = sorted({p.mt_id for p in records if p.mt_id})
        run = {
            "run_id": self.run_id,
            "timestamp": self.start.isoformat(),
            "operator": os.environ.get("CPM_FM_OPERATOR") or getpass.getuser(),
            "flags": self.flags,
            "target": {
                "name": target_name,
                "description": target.description if target else "",
                "settings_file": settings_path,
                "settings_sha256": settings_sha,
                "scratch_drive": target.scratch_drive if target else None,
            },
            "app_version": _app_version(),
            "git": _git_info(),
            "environment": {
                "os": f"{platform.system()} {platform.release()} ({platform.version()})",
                "python": platform.python_version(),
                "pyside6": _pkg_version("PySide6"),
                "pyserial": _pkg_version("pyserial"),
            },
            "manual_test_plan_version": _manual_test_plan_version(),
            "summary": dict(summary),
            "mt_ids_executed": mt_executed,
            "tests": [
                asdict(
                    TestRecord(
                        nodeid=p.nodeid,
                        mt_id=p.mt_id,
                        reqs=p.reqs,
                        outcome=p.outcome,
                        duration=round(p.duration, 3),
                        message=p.message,
                        observation=p.observation,
                    )
                )
                for p in records
            ],
        }
        return run, summary

    @staticmethod
    def _build_report_md(run: dict[str, Any], summary: Counter) -> str:
        t = run["target"]
        lines = [
            f"# HIL run {run['run_id']} — target `{t['name']}`",
            "",
            f"- **When:** {run['timestamp']}",
            f"- **Operator:** {run['operator']}",
            f"- **Target:** {t['name']} — {t['description']}",
            f"- **Settings file:** `{t['settings_file']}`",
            f"- **Settings SHA-256:** `{t['settings_sha256']}`",
            f"- **Scratch drive:** {t['scratch_drive']}",
            f"- **App version:** {run['app_version']}",
            f"- **Git:** {run['git']['branch']} @ {run['git']['commit'][:10]}"
            f"{' (dirty)' if run['git']['dirty'] else ''}",
            f"- **Flags:** {run['flags']}",
            f"- **Manual test plan:** {run['manual_test_plan_version']}",
            "",
            "## Summary",
            "",
            "| Outcome | Count |",
            "|---|---|",
        ]
        for outcome in (PASS, FAIL, BLOCKED, SKIPPED, NA, ERROR):
            if summary.get(outcome):
                lines.append(f"| {outcome} | {summary[outcome]} |")
        lines += [
            "",
            f"MT-IDs executed: {', '.join(run['mt_ids_executed']) or '(none)'}",
            "",
            "## Tests",
            "",
            "| MT-ID | Outcome | Duration | Requirements | Node |",
            "|---|---|---|---|---|",
        ]
        for tr in run["tests"]:
            lines.append(
                f"| {tr['mt_id'] or ''} | {tr['outcome']} | {tr['duration']}s | "
                f"{', '.join(tr['reqs'])} | `{tr['nodeid'].split('::', 1)[-1]}` |"
            )
        return "\n".join(lines) + "\n"

    def _build_junit(self, target_name: str, records: list[_Pending]) -> bytes:
        suite = ET.Element(
            "testsuite",
            name=f"hil-{target_name}",
            tests=str(len(records)),
            failures=str(sum(1 for p in records if p.outcome == FAIL)),
            errors=str(sum(1 for p in records if p.outcome == ERROR)),
            skipped=str(sum(1 for p in records if p.outcome in (SKIPPED, BLOCKED, NA))),
            timestamp=self.start.isoformat(),
        )
        for p in records:
            case = ET.SubElement(
                suite,
                "testcase",
                name=p.nodeid.split("::", 1)[-1],
                classname=f"{target_name}.{p.mt_id or 'untagged'}",
                time=f"{p.duration:.3f}",
            )
            if p.outcome == FAIL:
                ET.SubElement(case, "failure", message=p.message[:200]).text = p.message
            elif p.outcome == ERROR:
                ET.SubElement(case, "error", message=p.message[:200]).text = p.message
            elif p.outcome in (SKIPPED, BLOCKED, NA):
                ET.SubElement(case, "skipped", message=f"{p.outcome}: {p.message}"[:200])
        return ET.tostring(suite, encoding="utf-8", xml_declaration=True)

    def _ledger_entry(
        self, target_name: str, run: dict[str, Any], summary: Counter, run_dir: Path
    ) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "timestamp": run["timestamp"],
            "target": target_name,
            "app_version": run["app_version"],
            "git_commit": run["git"]["commit"],
            "git_dirty": run["git"]["dirty"],
            "summary": dict(summary),
            "artifacts": str(run_dir.relative_to(REPO_ROOT)).replace("\\", "/"),
        }

    @staticmethod
    def _append_ledger(entries: list[dict[str, Any]]) -> None:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        existing: list[dict[str, Any]] = []
        if LEDGER.exists():
            try:
                existing = json.loads(LEDGER.read_text())
            except (OSError, json.JSONDecodeError):
                existing = []
        existing.extend(entries)
        LEDGER.write_text(json.dumps(existing, indent=2), encoding="utf-8")
