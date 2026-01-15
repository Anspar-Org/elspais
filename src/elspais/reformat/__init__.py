# Implements: REQ-int-d00008 (Reformat Command)
"""
elspais.reformat - Requirement format transformation.

Transforms legacy Acceptance Criteria format to Assertions format.
Also provides line break normalization.

IMPLEMENTS REQUIREMENTS:
    REQ-int-d00008: Reformat Command
"""

from elspais.reformat.detector import detect_format, needs_reformatting, FormatAnalysis
from elspais.reformat.transformer import (
    reformat_requirement,
    assemble_new_format,
    validate_reformatted_content,
)
from elspais.reformat.line_breaks import (
    normalize_line_breaks,
    fix_requirement_line_breaks,
    detect_line_break_issues,
)
from elspais.reformat.hierarchy import (
    RequirementNode,
    get_all_requirements,
    build_hierarchy,
    traverse_top_down,
    normalize_req_id,
)

__all__ = [
    # Detection
    "detect_format",
    "needs_reformatting",
    "FormatAnalysis",
    # Transformation
    "reformat_requirement",
    "assemble_new_format",
    "validate_reformatted_content",
    # Line breaks
    "normalize_line_breaks",
    "fix_requirement_line_breaks",
    "detect_line_break_issues",
    # Hierarchy
    "RequirementNode",
    "get_all_requirements",
    "build_hierarchy",
    "traverse_top_down",
    "normalize_req_id",
]
