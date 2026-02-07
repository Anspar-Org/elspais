"""Import analyzer for Python source files.

Extracts import statements from Python files and resolves module paths
to source file paths. Used by test_code_linker to map test file imports
to CODE nodes in the traceability graph.
"""

from __future__ import annotations

import re
from pathlib import Path

# Patterns for Python import statements
_FROM_IMPORT = re.compile(r"^\s*from\s+([\w.]+)\s+import\s+")
_PLAIN_IMPORT = re.compile(r"^\s*import\s+([\w.]+(?:\s*,\s*[\w.]+)*)")


def extract_python_imports(content: str) -> list[str]:
    """Extract module paths from Python import statements.

    Parses ``from X import Y`` and ``import X`` statements.
    Only extracts the module path (X), not individual names (Y).

    Args:
        content: Full text content of a Python file.

    Returns:
        List of module paths (e.g., ["elspais.graph.annotators", "os.path"]).
    """
    modules: list[str] = []

    for line in content.splitlines():
        stripped = line.strip()

        # Skip comments and empty lines
        if not stripped or stripped.startswith("#"):
            continue

        # Stop at first non-import code (heuristic: imports are at top)
        # But allow blank lines, comments, docstrings, __future__, TYPE_CHECKING
        if (
            not stripped.startswith(("import ", "from ", "#", '"', "'", "if ", ")"))
            and stripped not in ("", ")")
            and "__future__" not in stripped
            and "TYPE_CHECKING" not in stripped
        ):
            # Allow continued lines and decorators
            if not stripped.startswith(("@", "(", ",")):
                break

        m = _FROM_IMPORT.match(line)
        if m:
            module = m.group(1)
            # Skip relative imports (start with .)
            if not module.startswith("."):
                modules.append(module)
            continue

        m = _PLAIN_IMPORT.match(line)
        if m:
            # Handle "import os, sys" → ["os", "sys"]
            for mod in m.group(1).split(","):
                mod = mod.strip()
                if mod and not mod.startswith("."):
                    modules.append(mod)

    return modules


def module_to_source_path(
    module: str,
    repo_root: Path,
    source_roots: list[str] | None = None,
) -> Path | None:
    """Map a Python module path to its source file path.

    Tries each source_root prefix to find the actual file.
    Handles both module files (.py) and packages (__init__.py).

    Args:
        module: Dotted module path (e.g., "elspais.graph.annotators").
        repo_root: Root of the repository.
        source_roots: List of source root directories relative to repo_root.
            Defaults to ["src", ""] (try src/ first, then repo root).

    Returns:
        Path relative to repo_root if found, None otherwise.
    """
    if source_roots is None:
        source_roots = ["src", ""]

    # Convert dotted module path to file path segments
    parts = module.split(".")
    rel_path = Path(*parts)

    for root in source_roots:
        root_path = repo_root / root if root else repo_root

        # Try as a .py file
        candidate = root_path / rel_path.with_suffix(".py")
        if candidate.is_file():
            return candidate.relative_to(repo_root)

        # Try as a package (__init__.py)
        candidate = root_path / rel_path / "__init__.py"
        if candidate.is_file():
            return candidate.relative_to(repo_root)

    return None
