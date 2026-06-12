import logging
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
        
        # Create a mapping: ReqID -> "module_path -> element_name"
        code_mapping: Dict[str, str] = {}
        for elem in discovered_elements:
            # Format: module_path -> class_or_function_name
            mapping_str = f"{elem.module} -> {elem.name}"
            code_mapping[elem.requirement_id] = mapping_str

        logger.info("Step 2: Parsing requirements documentation...")
        doc_requirements = parse_requirements_md(self.requirements_file)
        
        # Create a mapping: ReqID -> implementation_string
        doc_mapping: Dict[str, str] = {row.requirement_id: row.implementation for row in doc_requirements}

        logger.info("Step 3: Calculating the diff...")
        diff = TraceabilityDiff()

        # Check for updates and removals
        for req_id, doc_impl in doc_mapping.items():
            code_impl = code_mapping.get(req_id)
            
            if code_impl:
                # If it's in code, check if the doc is outdated or unmapped
                # We consider it outdated if the mapping string doesn't match the doc
                # Note: The doc might have "impl. app.py:load_config", while our tool produces "app.py -> load_config"
                # For a strict diff, we compare the essence.
                if doc_impl == "Unmapped" or code_impl not in doc_impl:
                    diff.to_update[req_id] = f"impl. {code_impl}"
            else:
                # If it's in docs but not in code, it might be a removal (or just not tagged yet)
                # For this tool, we mark it as potentially removed if it was previously mapped
                if doc_impl != "Unmapped":
                    diff.to_remove.append(req_id)

        # Check for new discoveries (in code but not in docs)
        for req_id in code_mapping:
            if req_id not in doc_mapping:
                diff.new_discoveries.append(req_id)

        return diff

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