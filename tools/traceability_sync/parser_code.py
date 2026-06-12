import ast
import logging
import os
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field

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
    """
    module: str
    name: str
    requirement_id: str

class RequirementExtractor(ast.NodeVisitor):
    """
    AST visitor to extract requirement IDs from docstrings of functions and classes.
    """
    def __init__(self, module_path: str):
        self.module_path = module_path
        self.found_elements: List[CodeElement] = []

    def _extract_req_id(self, docstring: Optional[str]) -> Optional[str]:
        """
        Extracts the requirement ID from the docstring based on the pattern 'Satisfies: REQ-XXX'.
        
        Args:
            docstring: The docstring to search.
            
        Returns:
            The requirement ID if found, otherwise None.
        """
        if not docstring:
            return None
        
        # Search for "Satisfies: REQ-XXX" or similar patterns like "Satisfies: FR-001"
        import re
        match = re.search(r"Satisfies:\s*([A-Z]+-\d+)", docstring)
        if match:
            return match.group(1)
        return None

    def visit_FunctionDef(self, node: ast.FunctionDef):
        """Visit function definitions."""
        docstring = ast.get_docstring(node)
        req_id = self._extract_req_id(docstring)
        if req_id:
            self.found_elements.append(
                CodeElement(module=self.module_path, name=node.name, requirement_id=req_id)
            )
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef):
        """Visit class definitions."""
        docstring = ast.get_docstring(node)
        req_id = self._extract_req_id(docstring)
        if req_id:
            self.found_elements.append(
                CodeElement(module=self.module_path, name=node.name, requirement_id=req_id)
            )
        self.generic_visit(node)

def scan_codebase(root_dir: str) -> List[CodeElement]:
    """
    Scans all .py files in the given directory for requirements mapped in docstrings.
    
    Args:
        root_dir: The root directory to start the scan from.
        
    Returns:
        A list of CodeElement objects representing the discovered mappings.
    """
    all_elements: List[CodeElement] = []
    root_path = Path(root_dir)
    
    if not root_path.exists():
        logger.error(f"Root directory {root_dir} does not exist.")
        return []

    logger.info(f"Scanning codebase in {root_dir} for requirement tags...")
    
    for py_file in root_path.rglob("*.py"):
        try:
            with open(py_file, "r", encoding="utf-8") as f:
                source = f.read()
            
            tree = ast.parse(source)
            extractor = RequirementExtractor(str(py_file.relative_to(root_path)))
            extractor.visit(tree)
            all_elements.extend(extractor.found_elements)
            
        except Exception as e:
            logger.error(f"Failed to parse {py_file}: {e}")
            
    logger.info(f"Found {len(all_elements)} requirement mappings in code.")
    return all_elements