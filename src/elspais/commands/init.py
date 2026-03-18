# Implements: REQ-d00052-G
"""
elspais.commands.init - Initialize configuration command.

Creates .elspais.toml configuration file.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import tomlkit

# Example requirement template for --template flag
EXAMPLE_REQUIREMENT = """# REQ-d00001: Example Requirement Title

**Level**: Dev | **Status**: Draft | **Implements**: -

## Assertions

A. The system SHALL demonstrate the assertion format.
B. The system SHALL show proper use of SHALL language.

## Rationale

This is an example requirement demonstrating the proper format.
Delete this file after reviewing the structure.

---

**Format Notes** (delete this section):

- **Title line**: `# REQ-{type}{id}: Title` where type is p/o/d for PRD/OPS/DEV
- **Metadata line**: Level, Status, and Implements (use `-` for top-level reqs)
- **Assertions**: Labeled A-Z, each using SHALL for required behavior
- **Rationale**: Optional explanation section (non-normative)
- **Footer**: `*End* *Title* | **Hash**: XXXXXXXX` - hash computed by `elspais fix`

Run `elspais format` for more templates and `elspais validate` to check this file.

*End* *Example Requirement Title* | **Hash**: 00000000
"""


def run(args: argparse.Namespace) -> int:
    """
    Run the init command.

    Args:
        args: Parsed command line arguments

    Returns:
        Exit code (0 for success)
    """
    # Handle --template flag separately
    if getattr(args, "template", False):
        return create_template_requirement(args)

    config_path = Path.cwd() / ".elspais.toml"

    if config_path.exists() and not args.force:
        print(f"Configuration file already exists: {config_path}")
        print("Use --force to overwrite.")
        return 1

    # Determine project type
    project_type = args.type or "core"
    associated_prefix = args.associated_prefix

    if project_type == "associated" and not associated_prefix:
        print("Error: --associated-prefix required for associated repositories")
        return 1

    # Generate configuration
    config_content = generate_config(project_type, associated_prefix)

    # Write file
    config_path.write_text(config_content, encoding="utf-8")
    print(f"Created configuration: {config_path}")

    return 0


def create_template_requirement(args: argparse.Namespace) -> int:
    """Create an example requirement file in the spec directory."""
    from elspais.config import load_config

    # Try to load config to find spec directory
    try:
        config = load_config(args.config if hasattr(args, "config") else None)
        spec_dir_name = config.get("directories", {}).get("spec", "spec")
    except Exception:
        spec_dir_name = "spec"

    spec_dir = Path.cwd() / spec_dir_name

    # Create spec directory if it doesn't exist
    if not spec_dir.exists():
        spec_dir.mkdir(parents=True)
        print(f"Created directory: {spec_dir}")

    # Create example file
    example_path = spec_dir / "EXAMPLE-requirement.md"

    if example_path.exists() and not getattr(args, "force", False):
        print(f"Example file already exists: {example_path}")
        print("Use --force to overwrite.")
        return 1

    example_path.write_text(EXAMPLE_REQUIREMENT, encoding="utf-8")
    print(f"Created example requirement: {example_path}")
    print()
    print("Next steps:")
    print("  1. Review the example to understand the format")
    print("  2. Delete or rename it when creating real requirements")
    print("  3. Run `elspais validate` to check format compliance")
    print("  4. Run `elspais fix` to compute content hashes")

    return 0


# Implements: REQ-d00209
# Section-level comments for the generated TOML, keyed by TOML section path.
_SECTION_COMMENTS: dict[str, str] = {
    "project": "Project identity",
    "directories": "Directory scanning paths",
    "id-patterns": "Requirement ID format and type definitions",
    "id-patterns.assertions": ('"uppercase" | "numeric" | "alphanumeric" | "numeric_1based"'),
    "spec": "Spec file scanning configuration",
    "rules": "Validation rules",
    "rules.hierarchy": "Allowed implements relationships between levels",
    "rules.format": "Format enforcement rules",
    "rules.format.status_roles": (
        "Status role classification (determines behavior in metrics/viewer)\n"
        "# active: committed, normative - counted in all metrics\n"
        "# provisional: in-progress toward active - excluded from coverage\n"
        "# aspirational: future/planning - excluded from coverage and analysis\n"
        "# retired: concluded - excluded from everything"
    ),
    "changelog": "Changelog enforcement",
    "testing": "Test file scanning and reference detection",
    "references": "Reference parsing configuration",
    "references.defaults": "Default reference parsing settings",
    "ignore": "File/directory ignore patterns",
    "keywords": "Keyword extraction settings",
    "validation": "Hash and validation settings",
    "graph": "Graph construction settings",
    "traceability": "Traceability output settings",
    "associated": "Associated repository identity",
    "core": "Path to core repository (relative or absolute)",
}

# Per-project-type overrides applied on top of schema defaults.
_CORE_OVERRIDES: dict[str, Any] = {
    "project": {"name": "my-project", "type": "core"},
    "directories": {"code": ["src", "apps", "packages"]},
    "spec": {
        "index_file": "INDEX.md",
        "skip_files": ["README.md", "requirements-format.md", "INDEX.md"],
    },
    "rules": {
        "hierarchy": {
            "dev": ["dev", "ops", "prd"],
            "ops": ["ops", "prd"],
            "prd": ["prd"],
            "allow_circular": False,
            "allow_structural_orphans": False,
        },
        "format": {
            "require_hash": True,
            "require_rationale": False,
            "require_assertions": True,
            "require_status": True,
            "allowed_statuses": ["Active", "Draft", "Deprecated", "Superseded"],
            "status_roles": {
                "active": ["Active"],
                "provisional": ["Draft", "Proposed"],
                "aspirational": ["Roadmap", "Future"],
                "retired": ["Deprecated", "Superseded"],
            },
        },
    },
    "changelog": {
        "enforce": True,
        "id_source": "gh",
        "date_format": "iso",
        "require_change_order": False,
        "require_reason": True,
        "require_author_name": True,
        "require_author_id": True,
        "author_id_format": "email",
    },
    "testing": {
        "enabled": False,
        "test_dirs": ["tests"],
        "patterns": ["test_*.py", "*_test.py"],
        "reference_keyword": "Validates",
    },
    "references": {
        "defaults": {
            "separators": ["-", "_"],
            "multi_assertion_separator": "+",
        },
    },
    "ignore": {
        "global": ["node_modules", ".git", "__pycache__", "*.pyc", ".venv", ".env"],
        "spec": ["README.md", "INDEX.md", "drafts/**"],
        "code": ["*_test.py", "conftest.py", "test_*.py"],
        "test": ["fixtures/**", "__snapshots__"],
    },
}

# Sections to include in core template (order determines output order).
_CORE_SECTIONS = [
    "version",
    "project",
    "directories",
    "id-patterns",
    "spec",
    "rules",
    "changelog",
    "testing",
    "references",
    "ignore",
    "keywords",
    "validation",
    "graph",
    "traceability",
]

# Sections to include in associated template.
_ASSOCIATED_SECTIONS = [
    "version",
    "project",
    "associated",
    "core",
    "directories",
    "id-patterns",
    "spec",
    "rules",
    "testing",
    "references",
    "ignore",
    "keywords",
    "validation",
    "graph",
    "traceability",
]


def _deep_merge(base: dict, override: dict) -> dict:
    """Deep-merge *override* into a copy of *base*."""
    result = dict(base)
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result


def _add_table(
    doc: tomlkit.TOMLDocument,
    key: str,
    value: Any,
    comment: str | None = None,
) -> None:
    """Add a key/value pair to *doc*, inserting a comment above tables."""
    if comment:
        for line in comment.split("\n"):
            doc.add(tomlkit.comment(line))
    if isinstance(value, dict):
        tbl = tomlkit.table()
        for k, v in value.items():
            if isinstance(v, dict):
                sub = tomlkit.table()
                for sk, sv in v.items():
                    if isinstance(sv, dict):
                        inner = tomlkit.table()
                        for ik, iv in sv.items():
                            inner.add(ik, iv)
                        sub.add(sk, inner)
                    else:
                        sub.add(sk, sv)
                sub_comment = _SECTION_COMMENTS.get(f"{key}.{k}")
                if sub_comment:
                    sub.comment(sub_comment)
                tbl.add(k, sub)
            else:
                tbl.add(k, v)
        doc.add(key, tbl)
    else:
        doc.add(key, value)


def generate_config(project_type: str, associated_prefix: str | None = None) -> str:
    """Generate configuration file content from the ElspaisConfig schema.

    Walks the Pydantic model defaults and applies project-type-specific
    overrides to produce valid, schema-compliant TOML.
    """
    from elspais import __version__
    from elspais.config import config_defaults

    defaults = config_defaults()

    if project_type == "associated":
        if associated_prefix is None:
            associated_prefix = "XXX"
        overrides: dict[str, Any] = {
            "project": {
                "name": f"{associated_prefix.lower()}-project",
                "type": "associated",
            },
            "associated": {
                "prefix": associated_prefix,
                "id_range": [1, 99999],
            },
            "core": {"path": "../core"},
            "directories": {"code": ["src", "lib"]},
            "id-patterns": {
                **defaults.get("id-patterns", {}),
                "associated": {
                    "enabled": True,
                    "position": "after_prefix",
                    "format": "uppercase",
                    "length": 3,
                    "separator": "-",
                },
            },
            "rules": {
                "hierarchy": {
                    "dev": ["dev", "ops", "prd"],
                    "ops": ["ops", "prd"],
                    "prd": ["prd"],
                    "cross_repo_implements": True,
                    "allow_structural_orphans": True,
                },
                "format": {
                    "require_hash": True,
                    "require_assertions": True,
                },
            },
        }
        sections = _ASSOCIATED_SECTIONS
        label = "Associated Repository"
        gen_by = f"elspais init --type associated (v{__version__})"
    else:
        overrides = _CORE_OVERRIDES
        sections = _CORE_SECTIONS
        label = "Core Repository"
        gen_by = f"elspais init (v{__version__})"

    data = _deep_merge(defaults, overrides)

    doc = tomlkit.document()
    doc.add(tomlkit.comment(f"elspais configuration - {label}"))
    doc.add(tomlkit.comment(f"Generated by: {gen_by}"))
    doc.add(tomlkit.comment(""))
    doc.add(
        tomlkit.comment("Tip: Create .elspais.local.toml alongside this file for developer-local")
    )
    doc.add(tomlkit.comment("overrides (e.g. associate paths). It is deep-merged and gitignored."))
    doc.add(tomlkit.nl())

    for section in sections:
        if section not in data:
            continue
        comment = _SECTION_COMMENTS.get(section)
        _add_table(doc, section, data[section], comment)
        doc.add(tomlkit.nl())

    return tomlkit.dumps(doc)
