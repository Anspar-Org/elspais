"""Per-relationship coverage status words (single source for dimension labels).

The label shown on a coverage badge/button/hover is defined per RELATIONSHIP
(the edge kind whose presence confers the coverage), not by the raw edge-kind
name -- "Verifies"/"Yields" would read poorly as labels (design §2).
"""

from __future__ import annotations

from typing import Any

# relationship (config key) -> internal RollupMetrics dimension key
RELATIONSHIP_TO_DIMENSION: dict[str, str] = {
    "implements": "implemented",
    "verifies": "tested",
    "yields": "verified",
    "validates": "uat_coverage",
    "validated": "uat_verified",
}

_DEFAULT_WORDS: dict[str, str] = {
    "implemented": "Implemented",
    "tested": "Tested",
    "verified": "Passing",
    "uat_coverage": "UAT Covered",
    "uat_verified": "UAT Passed",
}


# Implements: REQ-d00258-K
def get_status_words(config: dict[str, Any] | None) -> dict[str, str]:
    """dimension-key -> label, defaults overridable via [rules.coverage.status_words]."""
    words = dict(_DEFAULT_WORDS)
    rules = (config or {}).get("rules", {})
    cov = rules.get("coverage", {}) if isinstance(rules, dict) else {}
    overrides = cov.get("status_words", {}) if isinstance(cov, dict) else {}
    if isinstance(overrides, dict):
        for rel, word in overrides.items():
            dim = RELATIONSHIP_TO_DIMENSION.get(str(rel).lower())
            if dim and isinstance(word, str) and word:
                words[dim] = word
    return words
