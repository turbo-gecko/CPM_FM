"""Validate the repository's vendor-neutral agent, skill, and workflow assets."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AI_ROOT = ROOT / ".agents"
FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)
FIELD_RE = re.compile(r"^([a-z][a-z0-9-]*):\s*(.+)$")
LINK_RE = re.compile(r"\]\(([^)]+)\)")


def _metadata(path: Path) -> dict[str, str]:
    """Return simple scalar YAML frontmatter fields from a Markdown asset."""
    text = path.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(text)
    if match is None:
        raise ValueError("missing YAML frontmatter")

    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        field = FIELD_RE.fullmatch(line)
        if field is None:
            raise ValueError(f"unsupported frontmatter line: {line!r}")
        fields[field.group(1)] = field.group(2).strip()
    return fields


def _validate_named_asset(path: Path, expected_name: str) -> list[str]:
    """Validate required metadata and its correspondence to the asset path."""
    try:
        fields = _metadata(path)
    except ValueError as error:
        return [f"{path.relative_to(ROOT)}: {error}"]

    errors: list[str] = []
    if fields.get("name") != expected_name:
        errors.append(
            f"{path.relative_to(ROOT)}: name must be {expected_name!r}, "
            f"found {fields.get('name')!r}"
        )
    if not fields.get("description"):
        errors.append(f"{path.relative_to(ROOT)}: missing description")
    unexpected = set(fields) - {"name", "description"}
    if unexpected:
        errors.append(
            f"{path.relative_to(ROOT)}: unsupported metadata {', '.join(sorted(unexpected))}"
        )
    return errors


def _validate_links(path: Path) -> list[str]:
    """Return errors for unresolved relative Markdown links."""
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
    for match in LINK_RE.finditer(text):
        raw_target = match.group(1).strip("<>")
        target = raw_target.split("#", 1)[0]
        if not target or target.startswith("#") or re.match(r"^[a-z]+:", target):
            continue
        if not (path.parent / target).exists():
            errors.append(f"{path.relative_to(ROOT)}: unresolved link {raw_target!r}")
    return errors


def validate() -> list[str]:
    """Return all structural, metadata, placeholder, and link errors."""
    errors: list[str] = []

    actual_catalog: dict[str, set[str]] = {}
    for area in ("agents", "workflows"):
        actual_catalog[area] = set()
        for path in sorted((AI_ROOT / area).glob("*.md")):
            actual_catalog[area].add(path.stem)
            errors.extend(_validate_named_asset(path, path.stem))

    actual_catalog["skills"] = set()
    for skill_dir in sorted((AI_ROOT / "skills").iterdir()):
        if not skill_dir.is_dir():
            continue
        actual_catalog["skills"].add(skill_dir.name)
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.is_file():
            errors.append(f"{skill_dir.relative_to(ROOT)}: missing required SKILL.md")
            continue
        errors.extend(_validate_named_asset(skill_file, skill_dir.name))

    catalog_text = (AI_ROOT / "README.md").read_text(encoding="utf-8")
    for heading, area in (
        ("Agents", "agents"),
        ("Skills", "skills"),
        ("Workflows", "workflows"),
    ):
        section = re.search(rf"(?ms)^### {heading}\s+(.*?)(?=^### |\Z)", catalog_text)
        listed = set(re.findall(r"(?m)^- `([^`]+)`$", section.group(1))) if section else set()
        if listed != actual_catalog[area]:
            errors.append(
                f".agents/README.md: {area} catalog differs from filesystem "
                f"(listed={sorted(listed)}, actual={sorted(actual_catalog[area])})"
            )

    markdown_files = [
        ROOT / "AGENTS.md",
        ROOT / "docs" / "dev_guideline.md",
        ROOT / "docs" / "requirements_views" / "README.md",
        *sorted(AI_ROOT.rglob("*.md")),
    ]
    for path in markdown_files:
        text = path.read_text(encoding="utf-8")
        if "[TODO" in text or re.search(r"(?m)^TODO\b", text):
            errors.append(f"{path.relative_to(ROOT)}: unresolved TODO placeholder")
        errors.extend(_validate_links(path))

    return errors


def main() -> int:
    """Print validation errors and return a process exit code."""
    errors = validate()
    if errors:
        print("AI asset validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("AI assets are valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
