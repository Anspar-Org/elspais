"""pytest plugin: keep only the node ids listed in ``TIA_SELECT_FILE``.

Used for ``granularity = "test"``, where handing thousands of node ids to
pytest on the command line could exceed the argument-length limit. The test
files are still passed as arguments so only they are collected. Items
collected from a file the selection names as *new* are all kept: the baseline
never saw them, so every one of them is a new test.
"""

from __future__ import annotations

import json
import os

ENV = "TIA_SELECT_FILE"


def pytest_collection_modifyitems(session, config, items):
    path = os.environ.get(ENV)
    if not path:
        return
    with open(path, encoding="utf-8") as fh:
        spec = json.load(fh)
    keep_ids = set(spec["nodeids"])
    keep_files = set(spec.get("new_files", []))
    kept, dropped = [], []
    for item in items:
        file = item.nodeid.split("::", 1)[0]
        (kept if item.nodeid in keep_ids or file in keep_files else dropped).append(item)
    if dropped:
        config.hook.pytest_deselected(items=dropped)
        items[:] = kept
