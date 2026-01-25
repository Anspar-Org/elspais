"""
elspais.core - Core data models, pattern matching, and rule validation
"""

from elspais.core.hasher import calculate_hash, verify_hash
from elspais.core.models import ParsedRequirement, Requirement, RequirementType
from elspais.core.patterns import PatternConfig, PatternValidator
from elspais.core.rules import RuleEngine, RuleViolation, Severity

__all__ = [
    "Requirement",
    "ParsedRequirement",
    "RequirementType",
    "PatternValidator",
    "PatternConfig",
    "RuleEngine",
    "RuleViolation",
    "Severity",
    "calculate_hash",
    "verify_hash",
]
