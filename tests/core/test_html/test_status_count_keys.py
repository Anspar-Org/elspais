# Verifies: REQ-d00060-B
"""The navigation badges read the counts under the names the server writes.

The server names each count after the kind it counts, and it takes the name
from the kind itself. A name written by hand in the client is a second
spelling of the same thing: it reads as no count, the badge hides itself,
and a reader believes the graph holds none of that kind. No test of the
server alone can catch it, because the server was never wrong.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from elspais.graph import NodeKind

_NAV_TREE = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "elspais"
    / "html"
    / "templates"
    / "partials"
    / "js"
    / "_nav-tree.js.j2"
)


# Verifies: REQ-d00060-B
@pytest.mark.parametrize("kind", [NodeKind.TEST, NodeKind.RESULT], ids=lambda k: k.value)
def test_the_badge_reads_the_name_the_server_writes(kind):
    """Each count the badges read is named after the kind the server counted."""
    source = _NAV_TREE.read_text(encoding="utf-8")

    reads = set(re.findall(r"\bnc\.([A-Za-z_][A-Za-z0-9_]*)", source))

    assert kind.value in reads, (
        f"the badge reads no count named {kind.value!r}; "
        f"it reads {sorted(reads)}, and the server writes one name per kind"
    )
