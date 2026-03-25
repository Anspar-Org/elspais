# Implements: REQ-d00131-B
"""Shared regex patterns for requirement parsing.

These patterns are used by the Lark transformer, builder, and spec_writer.
Relocated from the legacy RequirementParser class.
"""
from __future__ import annotations

import re

ALT_STATUS_PATTERN = re.compile(r"\*\*Status\*\*:\s*(?P<status>\w+)")
IMPLEMENTS_PATTERN = re.compile(r"\*\*Implements\*\*:\s*(?P<implements>[^|\n]+)")
REFINES_PATTERN = re.compile(r"\*\*Refines\*\*:\s*(?P<refines>[^|\n]+)")
ASSERTION_LINE_PATTERN = re.compile(r"^\s*([A-Z0-9]+)\.\s+(.+)$", re.MULTILINE)
