import logging
import re

from parser_code import CodeElement, scan_codebase
from parser_docs import parse_requirements_md, update_requirements_md
from pydantic import BaseModel

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

class TraceabilityDiff(BaseModel):
    """
    Represents the difference between code-discovered traceability and
    document-recorded traceability.

    Attributes:
        to_update: Requirements that have a new or updated implementation path.
        to_remove: Requirements that are no longer satisfied by any code element.
        new_discoveries: Requirements found in code but missing from the documents.
    """
    to_update: dict[str, str] = {}
    to_remove: list[str] = []
    new_discoveries: list[str] = []

class TraceabilityAgent:
    """
    The logic engine that synchronizes source code implementation with requirements documentation.
    """
    def __init__(self, codebase_root: str, requirements_file):
        """``requirements_file`` may be a single path or a list of paths. The
        SRS and its architecture companion (`docs/cpm_fm_architecture.md`, which
        holds the CR-/NFR- constraints) are separate files; both must be parsed
        so that an architectural CR/NFR tag in code is not mis-reported as
        "missing from requirements" — mirroring generate_views.py.
        """
        self.codebase_root = codebase_root
        if isinstance(requirements_file, (str, bytes)):
            self.requirements_files = [requirements_file]
        else:
            self.requirements_files = list(requirements_file)
        # First file is the default write target / log label for messages.
        self.requirements_file = self.requirements_files[0]
        # Populated during analysis: requirement ID -> the file that defines it,
        # so write-backs land in the correct document.
        self._id_to_file: dict[str, str] = {}

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
        code_mapping: dict[str, list[CodeElement]] = {}
        for elem in discovered_elements:
            code_mapping.setdefault(elem.requirement_id, []).append(elem)

        logger.info("Step 2: Parsing requirements documentation...")
        doc_mapping: dict[str, str] = {}
        self._id_to_file = {}
        for req_file in self.requirements_files:
            for row in parse_requirements_md(req_file):
                doc_mapping[row.requirement_id] = row.implementation
                self._id_to_file[row.requirement_id] = req_file

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
    def _format_elements(elements: list[CodeElement]) -> str:
        """Render the satisfying elements as a doc-style citation list."""
        seen: list[str] = []
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
        if not diff.to_update:
            logger.info("No updates to apply.")
            return
        # Route each update to the file that defines that requirement so a CR/NFR
        # citation lands in the architecture doc, not the SRS.
        by_file: dict[str, dict[str, str]] = {}
        for req_id, new_impl in diff.to_update.items():
            target = self._id_to_file.get(req_id, self.requirements_file)
            by_file.setdefault(target, {})[req_id] = new_impl
        for target, updates in by_file.items():
            update_requirements_md(target, updates)
            logger.info(f"Applied {len(updates)} updates to {target}")

if __name__ == "__main__":
    # Example execution
    # Adjusted paths for the current project structure
    CODE_ROOT = "src"
    REQ_FILES = ["docs/cpm_fm_requirements.md", "docs/cpm_fm_architecture.md"]

    agent = TraceabilityAgent(CODE_ROOT, REQ_FILES)
    print(agent.generate_update_plan())