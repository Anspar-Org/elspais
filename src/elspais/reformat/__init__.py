# Implements: REQ-int-d00008 (Reformat Command)
"""
elspais.reformat - Requirement format transformation.

Transforms legacy Acceptance Criteria format to Assertions format.
Also provides line break normalization.

IMPLEMENTS REQUIREMENTS:
    REQ-int-d00008: Reformat Command
"""

from elspais.reformat.detector import FormatAnalysis, detect_format, needs_reformatting
from elspais.reformat.hierarchy import (
    RequirementNode,
    get_all_requirements,
    traverse_top_down,
)
from elspais.reformat.line_breaks import (
    detect_line_break_issues,
    fix_requirement_line_breaks,
    normalize_line_breaks,
)
from elspais.reformat.transformer import (
    assemble_new_format,
    reformat_requirement,
    validate_reformatted_content,
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
    "traverse_top_down",
]
