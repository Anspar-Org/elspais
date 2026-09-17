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

    # Implements: REQ-p00015-H, REQ-d00212-Q
    # Judged by the rules the WALK judges by, and by nothing else. This route
    # decides where a new spec file may be written; a file it admits that the
    # scan would then skip is a file the project cannot see, so the two must
    # answer alike. It matched each path component loosely here while the walk
    # read a path from the repository root, so one spelling was honoured by one
    # and ignored by the other.
    from elspais.config import scan_exclusions
    from elspais.graph.file_selection import file_is_skipped, within_skipped_dir

    all_skip_dirs, all_skip_files = scan_exclusions(config, "spec")
    all_skip_dirs = list(skip_dirs) + all_skip_dirs
    all_skip_files = list(skip_files) + all_skip_files

    if within_skipped_dir(relative_path, all_skip_dirs):
        return f"Path '{relative_path}' is under a directory the configuration skips"

    if file_is_skipped(filename, all_skip_files):
        return f"Filename '{filename}' matches a skip pattern"

    return None


# Implements: REQ-p00015-H, REQ-d00275-C, REQ-d00212-Q
def iter_spec_files(repo_root: Any, config: dict[str, Any]) -> list[Any]:
    """Every spec file the project's own configuration selects.

    ONE walk, for every surface that must read spec files without a built
    graph. It reads the directories the project declares -- where a
    repository's files are is a fact about that repository (REQ-d00275-C) --
    and it selects through the same helper the build scan uses, so a surface
    off the build path admits and excludes exactly what the build does.

    A file the configuration skips is never returned and never opened
    (REQ-p00015-H).
    """
    from pathlib import Path

    from elspais.config import get_spec_directories, scan_exclusions
    from elspais.graph.file_selection import select_files

    root = Path(repo_root)
    spec_cfg = (config.get("scanning") or {}).get("spec") or {}
    patterns = [p for p in (spec_cfg.get("file_patterns") or []) if isinstance(p, str)]
    if not patterns:
        patterns = ["*.md"]
    skip_dirs, skip_files = scan_exclusions(config, "spec")

    scan_dirs: list[str] = []
    for spec_dir in get_spec_directories(None, config, base_path=root):
        try:
            scan_dirs.append(Path(spec_dir).resolve().relative_to(root.resolve()).as_posix())
        except ValueError:
            continue

    selection = select_files(root, scan_dirs, skip_dirs, skip_files, patterns)
    return sorted(selection.selected)


# Implements: REQ-p00015-H, REQ-d00275-C
def find_spec_file_holding(req_id: str, repo_root: Any, config: dict[str, Any]) -> Any:
    """The spec file that declares *req_id*, or ``None``.

    Reads the one walk, and asks the ONE header authority. A second identifier
    regex spelled here would recognise a different set of headers than the
    rest of the tool does.
    """
    from elspais.utilities.patterns import find_req_header

    for spec_file in iter_spec_files(repo_root, config):
        if find_req_header(spec_file.read_text(encoding="utf-8"), req_id):
            return spec_file
    return None
