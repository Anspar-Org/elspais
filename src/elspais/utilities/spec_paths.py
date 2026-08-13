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
