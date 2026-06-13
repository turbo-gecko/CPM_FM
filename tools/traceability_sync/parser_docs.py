import logging
import re
from pathlib import Path
from typing import List, Dict, Optional
from pydantic import BaseModel

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

class RequirementRow(BaseModel):
    """
    Represents a single requirement row from the Markdown table.
    
    Attributes:
        requirement_id: The unique ID of the requirement (e.g., FR-001).
        description: The text description of the requirement.
        implementation: The current implementation mapping (e.g., 'app.py:load_config' or 'Unmapped').
    """
    requirement_id: str
    description: str
    implementation: str

def parse_requirements_md(file_path: str) -> List[RequirementRow]:
    """
    Parses a Markdown file containing requirements tables and extracts the 
    Requirement ID, Description, and Implementation.
    
    Args:
        file_path: Path to the requirements.md file.
        
    Returns:
        A list of RequirementRow objects.
    """
    requirements: List[RequirementRow] = []
    path = Path(file_path)
    
    if not path.exists():
        logger.error(f"Requirements file {file_path} not found.")
        return []

    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        logger.error(f"Error reading {file_path}: {e}")
        return []

    # We look for tables. A table starts with a header row and a separator row.
    # We are looking for tables that have 'ID' and 'Source' or 'Implementation' columns.
    # Based on the provided docs/cpm_fm_requirements.md, the columns are:
    # | ID | Requirement | Priority | Verification | Source |
    # Note: The "Source" column often contains implementation details like 'impl. app.py:load_config'.
    
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
                # Data row
                parts = [p.strip() for p in line.split("|")]
                # Filter out empty strings from split at start/end
                parts = [p for p in parts if p != ""]
                
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

# Splits a Markdown table row on cell boundaries only — pipes escaped as ``\|``
# inside a cell (e.g. the DR-006 vertical-bar requirement) are left intact.
_CELL_SPLIT = re.compile(r"(?<!\\)\|")


def _merge_source(existing: str, new_impl: str) -> str:
    """Merge a freshly computed ``impl. ...`` citation into a Source cell
    without discarding the cell's legacy document reference.

    * If the cell already carries an ``impl.`` segment (always the trailing
      part in this SRS), that segment is replaced with ``new_impl`` and any
      legacy reference before it is preserved.
    * If the cell holds only a legacy reference, ``new_impl`` is appended after
      a ``; `` separator.
    * If the cell is empty or a placeholder (``—``/``None``), it becomes
      ``new_impl`` alone.

    Args:
        existing: The current Source cell text (already stripped).
        new_impl: The new implementation citation, e.g. ``impl. `app.py:foo` ``.

    Returns:
        The merged Source cell text.
    """
    if existing in ("", "—", "None"):
        return new_impl

    lowered = existing.lower()
    idx = lowered.find("impl.")
    if idx != -1:
        prefix = existing[:idx].rstrip().rstrip(";").rstrip()
        return f"{prefix}; {new_impl}" if prefix else new_impl

    return f"{existing.rstrip().rstrip(';').rstrip()}; {new_impl}"


def update_requirements_md(file_path: str, updates: Dict[str, str]):
    """
    Updates the implementation citation of a Markdown table without discarding
    the existing Source-column content.

    Only genuine data rows whose first cell is a requirement ID present in
    ``updates`` are touched, and only their final (Source) cell is rewritten
    via :func:`_merge_source`. All other cells — and the spacing of every cell
    that is not changed — are preserved verbatim, including literal ``\\|``
    sequences inside a cell.

    Args:
        file_path: Path to the requirements.md file.
        updates: Dictionary mapping Requirement ID to the new implementation string.
    """
    path = Path(file_path)
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    applied = 0
    new_lines: List[str] = []
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
                    inner[-1] = f" {merged} "
                    body = "|" + "|".join(inner) + "|"
                    line = body + (ending or "\n")
                    applied += 1

        new_lines.append(line)

    with open(path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    logger.info(f"Updated {applied} rows in {file_path}.")