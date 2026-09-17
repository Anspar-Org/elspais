# Implements: REQ-o00062-M
"""
elspais.utilities.spec_paths - Validation for newly created spec file paths.

Single home for the "may a mutation create a spec file at this path" check,
shared by the viewer HTTP route and the MCP move tool so both surfaces accept
and reject identically (REQ-o00062-O).
"""

from __future__ import annotations

import fnmatch
from pathlib import PurePosixPath
from typing import Any


def file_id_for_reference(reference: str, config: dict[str, Any]) -> str:
    """Resolve a caller-supplied file reference to a FILE node id.

    A mutation surface accepts either a FILE node id, which already names
    the repository holding the file, or a bare repo-relative path, which
    does not. A path can only mean the repository the surface is serving
    -- its writes go under that repository's root -- so it is read in that
    repository's namespace. Shared by the viewer routes and the MCP tools
    so a path means the same thing on both.
    """
    from elspais.graph.GraphNode import FILE_ID_PREFIX, make_file_id

    if reference.startswith(FILE_ID_PREFIX):
        return reference
    namespace = (config or {}).get("project", {}).get("namespace", "") or ""
    if not namespace:
        raise ValueError(
            f"Cannot resolve '{reference}' to a file: this project declares no namespace."
        )
    return make_file_id(namespace, reference)


def validate_new_spec_path(relative_path: str, config: dict[str, Any]) -> str | None:
    """Validate that a new file path is under a configured spec directory.

    Returns an error message string if invalid, or None if valid.
    """
    from elspais.config import get_ignore_config
    from elspais.config.schema import ElspaisConfig

    typed_config = ElspaisConfig.model_validate(config)
    spec_cfg = typed_config.scanning.spec
    spec_dirs = list(spec_cfg.directories)
    file_patterns = list(spec_cfg.file_patterns)
    skip_dirs = list(spec_cfg.skip_dirs)
    skip_files = list(spec_cfg.skip_files)

    parts = PurePosixPath(relative_path).parts
    if not parts:
        return "Path is empty"

    # Check that path starts with a configured spec directory
    under_spec_dir = False
    for spec_dir in spec_dirs:
        spec_parts = PurePosixPath(spec_dir).parts
        if parts[: len(spec_parts)] == spec_parts:
            under_spec_dir = True
            break
    if not under_spec_dir:
        return f"Path '{relative_path}' is not under any configured spec directory ({spec_dirs})"

    # Check filename matches file_patterns
    filename = parts[-1]
    matches_pattern = any(fnmatch.fnmatch(filename, pat) for pat in file_patterns)
    if not matches_pattern:
        return f"Filename '{filename}' does not match any spec file pattern ({file_patterns})"

    # Check skip_dirs
    for part in parts[:-1]:
        if any(fnmatch.fnmatch(part, pat) for pat in skip_dirs):
            return f"Path contains skipped directory '{part}'"

    # Check skip_files
    if any(fnmatch.fnmatch(filename, pat) for pat in skip_files):
        return f"Filename '{filename}' matches a skip pattern"

    # Check IgnoreConfig
    ignore_cfg = get_ignore_config(config)
    if ignore_cfg.should_ignore(relative_path, scope="spec"):
        return f"Path '{relative_path}' is ignored by ignore configuration"

    return None


# Implements: REQ-p00015-H, REQ-d00275-C
def find_spec_file_holding(req_id: str, repo_root: Any, config: dict[str, Any]) -> Any:
    """The spec file that declares *req_id*, or ``None``.

    ONE search, for every surface that must find a requirement's file without
    a built graph. Two things were wrong where a surface wrote this loop for
    itself, and both are why it is here.

    The search reads the directories the project declares. A surface that
    looks in a fixed directory named ``spec`` finds nothing in a project that
    keeps its requirements elsewhere, and where its files are is a fact about
    that repository (REQ-d00275-C).

    The search asks the ignore configuration before it opens a file, so a file
    the reader excluded is not read (REQ-p00015-H).
    """
    from pathlib import Path

    from elspais.config import get_ignore_config, get_spec_directories
    from elspais.utilities.patterns import find_req_header

    root = Path(repo_root)
    ignore_config = get_ignore_config(config)

    # The files a spec scan selects are the ones the project declares, not a
    # fixed ``*.md``. A project that writes its requirements under another
    # extension is otherwise searched in part.
    spec_cfg = (config.get("scanning") or {}).get("spec") or {}
    patterns = [p for p in (spec_cfg.get("file_patterns") or []) if isinstance(p, str)]
    if not patterns:
        patterns = ["*.md"]

    for spec_dir in get_spec_directories(None, config, base_path=root):
        if not spec_dir.exists():
            continue
        candidates = sorted({f for pattern in patterns for f in spec_dir.rglob(pattern)})
        for spec_file in candidates:
            if ignore_config.should_ignore(spec_file, "spec", base=spec_dir):
                continue
            # ONE authority decides whether a file declares an identifier.
            # A second regex spelled here would recognise a different set of
            # headers than the rest of the tool does.
            if find_req_header(spec_file.read_text(encoding="utf-8"), req_id):
                return spec_file
    return None
