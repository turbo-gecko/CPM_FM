import ast
import logging
import re
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

class CodeElement(BaseModel):
    """
    Represents a code element (class or function) that satisfies a requirement.

    Attributes:
        module: The path to the Python module containing the element.
        name: The name of the class or function.
        requirement_id: The ID of the requirement satisfied by this element.
        from_range: True if this ID was derived by expanding a range shorthand
            (e.g. ``DR-001-DR-032``) rather than written out explicitly. Range
            shorthand can span gaps in the numbering, so a range-derived ID that
            is absent from the docs is treated as a non-existent gap-filler, not
            a genuine new discovery.
    """
    module: str
    name: str
    requirement_id: str
    from_range: bool = False

class RequirementExtractor(ast.NodeVisitor):
    """
    AST visitor to extract requirement IDs from docstrings of functions and classes.
    """
    def __init__(self, module_path: str):
        self.module_path = module_path
        self.found_elements: list[CodeElement] = []

    def _extract_req_ids(self, docstring: Optional[str]) -> list[tuple]:
        """
        Extracts every requirement ID from a docstring's 'Satisfies:' line.

        A single ``Satisfies:`` tag commonly lists multiple IDs, in two forms:
          * a comma-separated list, e.g. ``Satisfies: FR-030, FR-031, FR-040.``
          * an inclusive range, e.g. ``Satisfies: FR-050-FR-058.`` or
            ``Satisfies: DR-001-DR-032.`` (same prefix on both ends).
        Both forms are expanded to the full set of individual IDs. Ranges are
        expanded across the contiguous numeric span sharing one prefix; the
        zero-padding width of the lower bound is preserved (FR-050 -> FR-051 …).

        Args:
            docstring: The docstring to search.

        Returns:
            A list of ``(requirement_id, from_range)`` tuples (empty if none /
            no docstring), de-duplicated while preserving first-seen order.
            ``from_range`` flags IDs produced by expanding a range shorthand —
            such a span can cover gaps in the numbering, so those IDs must not
            be reported as genuine new discoveries downstream.
        """
        if not docstring:
            return []

        ids: list[tuple] = []
        # Consider the text after the first "Satisfies:" tag. The clause may wrap
        # onto following lines, but ONLY lines consisting solely of requirement
        # IDs and separators are treated as continuations — the first line that
        # carries any prose ends the clause, so IDs mentioned elsewhere in the
        # docstring cannot leak in. This lets a long list (e.g. the X-Modem
        # NFR-003a..NFR-003o set) wrap without breaking parsing.
        cont_re = re.compile(r"(?:[A-Z]+-\d+[a-z]?[\s,.;]*)+")
        clause_parts: list[str] = []
        collecting = False
        for raw in docstring.splitlines():
            line = raw.strip()
            if not collecting:
                m = re.match(r"Satisfies:\s*(.*)", line)
                if m:
                    clause_parts.append(m.group(1))
                    collecting = True
                continue
            if line and cont_re.fullmatch(line):
                clause_parts.append(line)
            else:
                break
        if not clause_parts:
            return []
        clause = " ".join(clause_parts)

        # First consume ranges ("FR-050-FR-058" / "FR-050-058"), expanding each,
        # then strip them out so the leftover single IDs aren't double-counted.
        range_re = re.compile(r"([A-Z]+)-(\d+)\s*-\s*(?:([A-Z]+)-)?(\d+)")

        def _expand(m: "re.Match[str]") -> str:
            prefix, lo_str, end_prefix, hi_str = m.groups()
            # A range only makes sense within one prefix; if the end names a
            # different prefix, treat it as two separate IDs, not a span.
            if end_prefix and end_prefix != prefix:
                return m.group(0)
            width = len(lo_str)
            lo, hi = int(lo_str), int(hi_str)
            if hi < lo:
                return m.group(0)
            for n in range(lo, hi + 1):
                ids.append((f"{prefix}-{n:0{width}d}", True))
            return " "  # blank out so the trailing single-ID pass skips it

        leftover = range_re.sub(_expand, clause)
        # A trailing lowercase letter denotes a decomposed sub-requirement
        # (e.g. NFR-003a..NFR-003o); capture it so sub-IDs are not collapsed to
        # their bare numeric parent. Ranges (above) stay numeric.
        ids.extend((req_id, False) for req_id in re.findall(r"[A-Z]+-\d+[a-z]?", leftover))

        # De-duplicate, preserving order. An explicit mention wins over a
        # range-derived one for the same ID (from_range=False is "stronger").
        best: dict[str, bool] = {}
        order: list[str] = []
        for req_id, from_range in ids:
            if req_id not in best:
                order.append(req_id)
                best[req_id] = from_range
            elif not from_range:
                best[req_id] = False
        return [(req_id, best[req_id]) for req_id in order]

    def _record(self, name: str, docstring: Optional[str]) -> None:
        """Append a CodeElement for each requirement ID tagged on ``name``."""
        for req_id, from_range in self._extract_req_ids(docstring):
            self.found_elements.append(
                CodeElement(
                    module=self.module_path,
                    name=name,
                    requirement_id=req_id,
                    from_range=from_range,
                )
            )

    def visit_FunctionDef(self, node: ast.FunctionDef):
        """
        Visit function definitions.
        """
        self._record(node.name, ast.get_docstring(node))
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef):
        """
        Visit class definitions.
        """
        self._record(node.name, ast.get_docstring(node))
        self.generic_visit(node)

def scan_codebase(root_dir: str) -> list[CodeElement]:
    """
    Scans all .py files in the given directory for requirements mapped in docstrings.
    
    Args:
        root_dir: The root directory to start the scan from.
        
    Returns:
        A list of CodeElement objects representing the discovered mappings.
    """
    all_elements: list[CodeElement] = []
    root_path = Path(root_dir)
    
    if not root_path.exists():
        logger.error(f"Root directory {root_dir} does not exist.")
        return []

    logger.info(f"Scanning codebase in {root_dir} for requirement tags...")
    
    for py_file in root_path.rglob("*.py"):
        try:
            with open(py_file, encoding="utf-8") as f:
                source = f.read()
            
            tree = ast.parse(source)
            extractor = RequirementExtractor(str(py_file.relative_to(root_path)))
            extractor.visit(tree)
            all_elements.extend(extractor.found_elements)
            
        except Exception as e:
            logger.error(f"Failed to parse {py_file}: {e}")
            
    logger.info(f"Found {len(all_elements)} requirement mappings in code.")
    return all_elements