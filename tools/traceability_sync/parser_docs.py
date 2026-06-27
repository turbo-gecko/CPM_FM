import difflib
import logging
import re
from pathlib import Path

from pydantic import BaseModel

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Splits a Markdown table row on cell boundaries only — pipes escaped as ``\|``
# inside a cell (e.g. the DR-006 vertical-bar requirement) are left intact, so
# the columns of such a row stay aligned.
_CELL_SPLIT = re.compile(r"(?<!\\)\|")


def _split_row(line: str) -> list[str]:
    """Split a table row into its cells (stripped), dropping the empty artefacts
    produced by the leading and trailing pipe but keeping interior cells
    positional (interior blanks are preserved, not discarded)."""
    cells = _CELL_SPLIT.split(line.rstrip("\n"))
    if cells and cells[0].strip() == "":
        cells = cells[1:]
    if cells and cells[-1].strip() == "":
        cells = cells[:-1]
    return [c.strip() for c in cells]

class RequirementRow(BaseModel):
    """
    Represents a single requirement row from the Markdown table.
    
    Attributes:
        requirement_id: The unique ID of the requirement (e.g., FR-001).
        description: The text description of the requirement.
        implementation: The current implementation mapping
            (e.g., 'app.py:load_config' or 'Unmapped').
    """
    requirement_id: str
    description: str
    implementation: str

def parse_requirements_md(file_path: str) -> list[RequirementRow]:
    """
    Parses a Markdown file containing requirements tables and extracts the 
    Requirement ID, Description, and Implementation.
    
    Args:
        file_path: Path to the requirements.md file.
        
    Returns:
        A list of RequirementRow objects.
    """
    requirements: list[RequirementRow] = []
    path = Path(file_path)
    
    if not path.exists():
        logger.error(f"Requirements file {file_path} not found.")
        return []

    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        logger.error(f"Error reading {file_path}: {e}")
        return []

    # We look for tables. A table starts with a header row and a separator row.
    # We are looking for tables that have 'ID' and 'Source' or 'Implementation' columns.
    # Based on the provided docs/cpm_fm_requirements.md, the columns are:
    # | ID | Requirement | Priority | Verification | Source |
    # Note: The "Source" column often contains implementation details like
    # 'impl. app.py:load_config'.
    
    in_table = False
    header_cols = []

    for line in lines:
        line = line.strip()
        if not line:
            in_table = False
            continue
        
        if line.startswith("|") and not in_table:
            # Potential header
            cols = [c.strip() for c in line.split("|") if c.strip()]
            if "ID" in cols and ("Source" in cols or "Implementation" in cols):
                in_table = True
                header_cols = cols
                # Skip the separator row (e.g., |---|---|)
                continue 
        
        if in_table:
            if line.startswith("|") and "---" in line:
                # This is the separator row, just continue
                continue
            
            if line.startswith("|"):
                # Data row. Split on unescaped pipes only and keep interior
                # cells positional, so a literal "\|" inside a cell (the DR-006
                # vertical-bar requirement) cannot fragment the row and push the
                # Source column out of alignment.
                parts = _split_row(line)

                if len(parts) >= 2:
                    req_id = parts[0]
                    description = parts[1]
                    
                    # Find the index of 'Source' or 'Implementation'
                    impl_val = "Unmapped"
                    try:
                        # The Source column is usually the last one in the provided MD
                        # | ID | Requirement | Priority | Verification | Source |
                        # index: 0 | 1 | 2 | 3 | 4
                        source_idx = -1
                        if "Source" in header_cols:
                            source_idx = header_cols.index("Source")
                        elif "Implementation" in header_cols:
                            source_idx = header_cols.index("Implementation")
                        
                        if source_idx != -1 and len(parts) > source_idx:
                            val = parts[source_idx]
                            # Check if it contains 'impl.' or actual paths
                            if val and val != "—" and val != "None":
                                impl_val = val
                        else:
                            impl_val = "Unmapped"
                    except Exception:
                        impl_val = "Unmapped"
                    
                    requirements.append(RequirementRow(
                        requirement_id=req_id,
                        description=description,
                        implementation=impl_val
                    ))
            else:
                in_table = False

    logger.info(f"Parsed {len(requirements)} requirements from {file_path}.")
    return requirements

# A *plain citation list*: one or more backticked tokens separated only by
# commas (e.g. ```app.py:foo`, `config.py:bar```) — exactly the shape the
# traceability tool itself emits. A trailing ``impl.`` segment of this shape is
# safe to auto-rewrite; anything richer (a parenthetical, a ``; tests ...``
# citation, a ``; FR-...`` cross-ref) is curated prose that must not be clobbered.
_PLAIN_CITATIONS = re.compile(r"^`[^`]+`(?:\s*,\s*`[^`]+`)*$")


def _merge_source(existing: str, new_impl: str) -> str | None:
    """Merge a freshly computed ``impl. ...`` citation into a Source cell, or
    signal that doing so safely is impossible.

    Conservative by design — it never overwrites curated annotation:

    * Empty / placeholder cell (``—``/``None``/``""``): becomes ``new_impl``.
    * Cell with **no** ``impl.`` segment (legacy reference only): ``new_impl``
      is appended after a ``; `` separator (nothing is discarded).
    * Cell with an ``impl.`` segment whose trailing text is a *plain citation
      list* (see :data:`_PLAIN_CITATIONS`): that segment is replaced with
      ``new_impl`` and any legacy prefix before it is preserved.
    * Cell with an ``impl.`` segment carrying any curated annotation after the
      citation (a parenthetical, ``; tests ...``, a ``; FR-...`` cross-ref):
      **returns ``None``** so the caller leaves the cell untouched and reports
      it for manual review rather than clobbering the curation. This is the
      DR-045/DR-047/CR-015 data-loss trap the v2.14.0 sync hit.

    Args:
        existing: The current Source cell text (already stripped).
        new_impl: The new implementation citation, e.g. ``impl. `app.py:foo` ``.

    Returns:
        The merged Source cell text, or ``None`` when the cell must be left
        untouched and flagged for manual review.
    """
    if existing in ("", "—", "None"):
        return new_impl

    lowered = existing.lower()
    idx = lowered.find("impl.")
    if idx != -1:
        trailing = existing[idx + len("impl.") :].strip()
        if not _PLAIN_CITATIONS.match(trailing):
            # Curated annotation follows the citation — do not clobber it.
            return None
        prefix = existing[:idx].rstrip().rstrip(";").rstrip()
        return f"{prefix}; {new_impl}" if prefix else new_impl

    return f"{existing.rstrip().rstrip(';').rstrip()}; {new_impl}"


def update_requirements_md(
    file_path: str, updates: dict[str, str], *, dry_run: bool = False
) -> dict:
    """
    Update the implementation citation of a Markdown table without discarding
    the existing Source-column content.

    Only genuine data rows whose first cell is a requirement ID present in
    ``updates`` are touched, and only their final (Source) cell is rewritten
    via :func:`_merge_source`. All other cells — and the spacing of every cell
    that is not changed — are preserved verbatim, including literal ``\\|``
    sequences inside a cell.

    A row whose Source cell carries curated annotation after its ``impl.``
    citation is **never** rewritten: :func:`_merge_source` returns ``None`` for
    it, the row is left exactly as-is, and its ID is added to the returned
    ``skipped`` list for manual review.

    Args:
        file_path: Path to the requirements.md file.
        updates: Dictionary mapping Requirement ID to the new implementation string.
        dry_run: When True, write nothing; the returned ``diff`` is a unified-diff
            preview of the rewrites that *would* be applied.

    Returns:
        ``{"applied": int, "skipped": list[str], "diff": str}``.
    """
    path = Path(file_path)
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()

    applied = 0
    skipped: list[str] = []
    new_lines: list[str] = []
    for line in lines:
        body = line.rstrip("\n")
        ending = line[len(body):]  # preserve the original line ending (or none)

        # Only consider table data rows: start with '|', not a separator row.
        if body.lstrip().startswith("|") and "---" not in body:
            cells = _CELL_SPLIT.split(body)
            # A well-formed row splits to ['', cell0, cell1, ..., cellN, ''];
            # the first/last entries are the artefacts of the edge pipes.
            if len(cells) >= 3 and cells[0].strip() == "" and cells[-1].strip() == "":
                inner = cells[1:-1]
                req_id = inner[0].strip()
                if req_id in updates:
                    merged = _merge_source(inner[-1].strip(), updates[req_id])
                    if merged is None:
                        # Curated Source cell — leave it untouched, flag it.
                        skipped.append(req_id)
                    else:
                        inner[-1] = f" {merged} "
                        body = "|" + "|".join(inner) + "|"
                        line = body + (ending or "\n")
                        applied += 1

        new_lines.append(line)

    diff = "".join(
        difflib.unified_diff(
            lines,
            new_lines,
            fromfile=f"{file_path} (current)",
            tofile=f"{file_path} (proposed)",
        )
    )

    if dry_run:
        logger.info(f"[dry-run] {applied} row(s) would change in {file_path}.")
    else:
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
        logger.info(f"Updated {applied} rows in {file_path}.")

    if skipped:
        logger.warning(
            f"Skipped {len(skipped)} row(s) in {file_path} with curated Source "
            f"annotation (manual review needed): {', '.join(skipped)}"
        )

    return {"applied": applied, "skipped": skipped, "diff": diff}