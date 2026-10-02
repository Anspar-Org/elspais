"""Read the embedded content a static viewer page carries.

A page generated with embedded content holds one script data block whose text
is a gzip-compressed JSON document spelled in base64. These helpers cut that
block where a browser would end it and restore the document it carries.
"""

from __future__ import annotations

import base64
import gzip
import json
import re
from typing import Any

# The values the block carries, by the name the page reads each one under.
EMBEDDED_KEYS = ("tree", "sources", "nodes", "coverage", "status")

# The block runs from its opening tag to the first end tag the browser finds.
_EMBEDDED_BLOCK = re.compile(
    r'<script type="application/octet-stream" id="embedded-data"'
    r' data-encoding="gzip\+base64">(.*?)</script>',
    re.S,
)


def embedded_block_text(page: str) -> str:
    """The page text of the embedded-content block, cut where a browser would end it."""
    blocks = _EMBEDDED_BLOCK.findall(page)
    assert len(blocks) == 1, f"expected one embedded-content block, found {len(blocks)}"
    return blocks[0]


def embedded_gzip(page: str) -> bytes:
    """The compressed bytes the block spells in base64."""
    return base64.b64decode(embedded_block_text(page).strip(), validate=True)


def embedded_data(page: str) -> dict[str, Any]:
    """The values the block carries, restored from its compressed form."""
    data = json.loads(gzip.decompress(embedded_gzip(page)).decode("utf-8"))
    assert set(data) == set(EMBEDDED_KEYS), f"embedded content holds {sorted(data)}"
    return data
