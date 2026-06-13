import logging
import re
from typing import List, Dict, Tuple
from pydantic import BaseModel

from parser_code import scan_codebase, CodeElement
from parser_docs import parse_requirements_md, RequirementRow, update_requirements_md

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

class TraceabilityDiff(BaseModel):
    """
    Represents the difference between code-discovered traceability and document-recorded traceability.
    
    Attributes:
        to_update: Requirements that have a new or updated implementation path.
        to_remove: Requirements that are no longer satisfied by any code element.
        new_discoveries: Requirements found in code but missing from the documents.
    """
    to_update: Dict[str, str] = {}
    to_remove: List[str] = []
    new_discoveries: List[str] = []

class TraceabilityAgent:
    """
    The logic engine that synchronizes source code implementation with requirements documentation.
    """
    def __init__(self, codebase_root: str, requirements_file: str):
        self.codebase_root = codebase_root
        self.requirements_file = requirements_file

    def run_sync_analysis(self) -> TraceabilityDiff:
        """
        Performs the structural analysis and compares it against the documentation.
        
        Returns:
            A TraceabilityDiff object containing the required changes.
        """
        logger.info("Step 1: Identifying REQ-XXX tags in source code...")
        discovered_elements = scan_codebase(self.codebase_root)

        # Create a mapping: ReqID -> [CodeElement, ...]. A single requirement is
        # frequently satisfied by more than one class/function, so we keep every
        # element rather than letting the last writer win.
        code_mapping: Dict[str, List[CodeElement]] = {}
        for elem in discovered_elements:
            code_mapping.setdefault(elem.requirement_id, []).append(elem)

        logger.info("Step 2: Parsing requirements documentation...")
        doc_requirements = parse_requirements_md(self.requirements_file)

        # Create a mapping: ReqID -> implementation_string
        doc_mapping: Dict[str, str] = {row.requirement_id: row.implementation for row in doc_requirements}

        logger.info("Step 3: Calculating the diff...")
        diff = TraceabilityDiff()

        # Check for updates and removals
        for req_id, doc_impl in doc_mapping.items():
            elements = code_mapping.get(req_id)

            if elements:
                # In code: only flag an update when the doc's Source/impl text
                # does not already cite ANY of the satisfying code elements.
                # Compare on a normalised "basename:name" token so the tool's
                # "cpm_fm\app.py -> load_config" matches the doc's freeform
                # "impl. `app.py:load_config`" (differing path depth, separator
                # and slashes no longer cause spurious mismatches).
                if not any(self._doc_cites(doc_impl, e) for e in elements):
                    diff.to_update[req_id] = "impl. " + self._format_elements(elements)
            else:
                # In docs but not tagged in any code element. Only meaningful for
                # rows that previously claimed an implementation; rows sourced
                # solely to legacy docs ("Unmapped" here) are left alone.
                if doc_impl != "Unmapped":
                    diff.to_remove.append(req_id)

        # Check for new discoveries (in code but not in docs). Ignore IDs that
        # exist only as range-shorthand expansions (e.g. a gap inside
        # "DR-001-DR-032"): those are not real requirements, just artefacts of
        # the range covering a non-contiguous span. An ID counts as a genuine
        # discovery only if some element names it explicitly.
        for req_id, elements in code_mapping.items():
            if req_id not in doc_mapping and any(not e.from_range for e in elements):
                diff.new_discoveries.append(req_id)

        return diff

    @staticmethod
    def _normalize(text: str) -> str:
        """Lower-case, unify path slashes and the `->`/`:` separators, and drop
        backticks/whitespace so code-tool tokens and doc prose compare cleanly."""
        text = text.lower().replace("\\", "/").replace("`", "")
        text = text.replace("->", ":")
        return re.sub(r"\s+", "", text)

    @classmethod
    def _doc_cites(cls, doc_impl: str, elem: CodeElement) -> bool:
        """True if ``doc_impl`` references ``elem`` by file basename + name."""
        basename = elem.module.replace("\\", "/").split("/")[-1]
        token = cls._normalize(f"{basename}:{elem.name}")
        return token in cls._normalize(doc_impl)

    @staticmethod
    def _format_elements(elements: List[CodeElement]) -> str:
        """Render the satisfying elements as a doc-style citation list."""
        seen: List[str] = []
        for e in elements:
            basename = e.module.replace("\\", "/").split("/")[-1]
            cite = f"`{basename}:{e.name}`"
            if cite not in seen:
                seen.append(cite)
        return ", ".join(seen)

    def generate_update_plan(self) -> str:
        """
        Executes analysis and outputs a "Traceability Update Plan".
        
        Returns:
            A formatted string representing the update plan.
        """
        diff = self.run_sync_analysis()
        
        plan = ["\n=== Traceability Update Plan ===\n"]
        
        if not diff.to_update and not diff.to_remove and not diff.new_discoveries:
            plan.append("No discrepancies found. Code and Documentation are in sync.")
            return "\n".join(plan)

        if diff.to_update:
            plan.append("[MODIFICATIONS]")
            for req_id, new_path in diff.to_update.items():
                plan.append(f"- {req_id}: Update implementation to '{new_path}'")
        
        if diff.to_remove:
            plan.append("\n[POTENTIAL REMOVALS/ORPHANS]")
            for req_id in diff.to_remove:
                plan.append(f"- {req_id}: No longer found in source code tags.")

        if diff.new_discoveries:
            plan.append("\n[NEW DISCOVERIES]")
            for req_id in diff.new_discoveries:
                plan.append(f"- {req_id}: Found in code but missing from requirements.md")

        return "\n".join(plan)

    def apply_updates(self):
        """
        Actually writes the changes back to the requirements.md file.
        """
        diff = self.run_sync_analysis()
        if diff.to_update:
            update_requirements_md(self.requirements_file, diff.to_update)
            logger.info(f"Applied {len(diff.to_update)} updates to {self.requirements_file}")
        else:
            logger.info("No updates to apply.")

if __name__ == "__main__":
    # Example execution
    # Adjusted paths for the current project structure
    CODE_ROOT = "src"
    REQ_FILE = "docs/cpm_fm_requirements.md"
    
    agent = TraceabilityAgent(CODE_ROOT, REQ_FILE)
    print(agent.generate_update_plan())