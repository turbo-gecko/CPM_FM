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

def update_requirements_md(file_path: str, updates: Dict[str, str]):
    """
    Updates the implementation column of a Markdown table with new mappings.
    
    Args:
        file_path: Path to the requirements.md file.
        updates: Dictionary mapping Requirement ID to the new implementation string.
    """
    path = Path(file_path)
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    new_lines = []
    for line in lines:
        if line.startswith("|") and not line.startswith("|---") and " | " in line:
            parts = [p.strip() for p in line.split("|")]
            # Remove empty strings from leading/trailing pipes
            filtered_parts = [p for p in parts if p != ""]
            
            if filtered_parts:
                req_id = filtered_parts[0]
                if req_id in updates:
                    # Replace the last column (Source/Implementation)
                    # We assume the structure: | ID | Req | Priority | Verif | Source |
                    # Since we can't easily know the exact column count without parsing the header 
                    # for every file, we'll replace the last element.
                    filtered_parts[-1] = updates[req_id]
                    
                    # Reconstruct the line
                    # Note: This is a bit naive as it doesn't preserve exact spacing,
                    # but for Markdown tables it's usually acceptable.
                    line = "| " + " | ".join(filtered_parts) + " |"
                    # Add the original line ending
                    if not line.endswith("\n"):
                        line += "\n"
        
        new_lines.append(line)
    
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)
    
    logger.info(f"Updated {len(updates)} rows in {file_path}.")