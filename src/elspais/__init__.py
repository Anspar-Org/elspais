"""
elspais - Requirements validation and traceability tools

L-Space is the ultimate library, connecting all libraries everywhere
through the sheer weight of accumulated knowledge.
    — Terry Pratchett

elspais validates requirement formats, generates traceability matrices,
and supports multi-repository requirement management with configurable
ID patterns and validation rules.
"""

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("elspais")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"  # Not installed
__author__ = "Anspar"
__license__ = "MIT"

from elspais.core.models import Assertion, ContentRule, ParsedRequirement, Requirement
from elspais.core.patterns import PatternValidator
from elspais.core.rules import RuleEngine, RuleViolation, Severity

__all__ = [
    "__version__",
    "Assertion",
    "ContentRule",
    "Requirement",
    "ParsedRequirement",
    "PatternValidator",
    "RuleEngine",
    "RuleViolation",
    "Severity",
]
