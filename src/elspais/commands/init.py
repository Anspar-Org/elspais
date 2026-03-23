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
        scanning = config.get("scanning", {})
        spec_config = scanning.get("spec", {})
        spec_dirs = spec_config.get("directories", ["spec"])
        spec_dir_name = spec_dirs[0] if spec_dirs else "spec"
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
    "id-patterns": "Requirement ID format and type definitions",
    "id-patterns.assertions": ('"uppercase" | "numeric" | "alphanumeric" | "numeric_1based"'),
    "levels": "Requirement level definitions with hierarchy rules",
    "scanning": "File scanning configuration",
    "scanning.spec": "Spec file scanning",
    "scanning.code": "Code file scanning",
    "scanning.test": "Test file scanning and reference detection",
    "scanning.result": "Test result file scanning",
    "scanning.coverage": "Code coverage report scanning",
    "scanning.journey": "User journey file scanning",
    "scanning.docs": "Documentation file scanning",
    "rules": "Validation rules",
    "rules.hierarchy": "Global hierarchy settings",
    "rules.format": "Format enforcement rules",
    "rules.format.status_roles": (
        "Status role classification (determines behavior in metrics/viewer)\n"
        "# active: committed, normative - counted in all metrics\n"
        "# provisional: in-progress toward active - excluded from coverage\n"
        "# aspirational: future/planning - excluded from coverage and analysis\n"
        "# retired: concluded - excluded from everything"
    ),
    "changelog": "Changelog enforcement",
    "keywords": "Keyword extraction settings",
    "validation": "Hash and validation settings",
    "output": "Output settings",
    "associates": "Associated repository definitions",
}

# Per-project-type overrides applied on top of schema defaults.
_CORE_OVERRIDES: dict[str, Any] = {
    "project": {"name": "my-project"},
    "levels": {
        "prd": {
            "rank": 1,
            "letter": "p",
            "display_name": "Product",
            "implements": ["prd"],
        },
        "ops": {
            "rank": 2,
            "letter": "o",
            "display_name": "Operations",
            "implements": ["ops", "prd"],
        },
        "dev": {
            "rank": 3,
            "letter": "d",
            "display_name": "Development",
            "implements": ["dev", "ops", "prd"],
        },
    },
    "scanning": {
        "skip": ["node_modules", ".git", "__pycache__", "*.pyc", ".venv", ".env"],
        "spec": {
            "directories": ["spec"],
            "file_patterns": ["*.md"],
            "skip_files": ["README.md", "requirements-format.md", "INDEX.md"],
        },
        "code": {
            "directories": ["src", "apps", "packages"],
        },
        "test": {
            "enabled": False,
            "directories": ["tests"],
            "file_patterns": ["test_*.py", "*_test.py"],
            "reference_keyword": "Verifies",
        },
    },
    "rules": {
        "hierarchy": {
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
        "hash_current": True,
        "present": False,
        "id_source": "gh",
        "date_format": "iso",
        "author_id_format": "email",
        "require": {
            "reason": True,
            "author_name": True,
            "author_id": True,
            "change_order": False,
        },
    },
}

# Sections to include in core template (order determines output order).
_CORE_SECTIONS = [
    "version",
    "project",
    "id-patterns",
    "levels",
    "scanning",
    "rules",
    "changelog",
    "keywords",
    "validation",
    "output",
]

# Sections to include in associated template.
_ASSOCIATED_SECTIONS = [
    "version",
    "project",
    "id-patterns",
    "levels",
    "scanning",
    "rules",
    "keywords",
    "validation",
    "output",
    "associates",
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


# Optional fields not in config_defaults() (None values are excluded).
# Keyed by the TOML line after which to insert; value is a list of
# commented-out lines to append.
_OPTIONAL_FIELD_INJECTIONS: list[tuple[str, list[str]]] = [
    # id-patterns.component
    (
        "leading_zeros = true",
        [
            '# pattern = "[A-Z]{2}[0-9]{3}"  # For alphanumeric',
            "# max_length = 32               # For named style",
        ],
    ),
    # id-patterns.assertions
    (
        "max_count = 26",
        [
            "# zero_pad = false              # Pad numeric labels",
            '# multi_separator = "+"         # Multi-assertion (A+B+C)',
        ],
    ),
    # rules.hierarchy
    (
        "allow_structural_orphans = false",
        [
            "# cross_repo_implements = true  # Cross-repo implements",
            "# allow_orphans = false         # Allow orphaned nodes",
        ],
    ),
    # rules.format
    (
        'allowed_statuses = ["Active"',
        [
            "# content_rules = []            # Content validation rules",
        ],
    ),
    # validation
    (
        "allow_unresolved_cross_repo = false",
        [
            '# hash_algorithm = "sha256"     # Hash algorithm',
            "# hash_length = 8               # Hash truncation length",
            "# strict_hierarchy = false       # Strict hierarchy mode",
        ],
    ),
]


def _inject_optional_fields(toml_text: str) -> str:
    """Insert commented-out optional fields into generated TOML."""
    lines = toml_text.split("\n")
    result: list[str] = []
    current_section = ""
    for line in lines:
        result.append(line)
        stripped = line.strip()
        # Track current section for context-aware injection
        if stripped.startswith("[") and "]" in stripped:
            current_section = stripped[1 : stripped.index("]")]
        for anchor, inj_lines in _OPTIONAL_FIELD_INJECTIONS:
            if anchor in stripped:
                result.extend(inj_lines)
                break
        # Section-specific optional fields (only inject in the right section)
        if current_section == "scanning.spec" and stripped.startswith("skip_dirs"):
            result.append('# index_file = "INDEX.md"  # Index file for ordering')
        if current_section == "scanning.coverage" and stripped.startswith("skip_dirs"):
            result.append('# file_patterns = ["coverage.json", "**/lcov.info"]')
        if current_section == "scanning.code" and stripped.startswith("skip_dirs"):
            result.append("# source_roots = []    # Import resolution roots")
    return "\n".join(result)


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
                "namespace": associated_prefix,
            },
            "levels": {
                "prd": {
                    "rank": 1,
                    "letter": "p",
                    "display_name": "Product",
                    "implements": ["prd"],
                },
                "ops": {
                    "rank": 2,
                    "letter": "o",
                    "display_name": "Operations",
                    "implements": ["ops", "prd"],
                },
                "dev": {
                    "rank": 3,
                    "letter": "d",
                    "display_name": "Development",
                    "implements": ["dev", "ops", "prd"],
                },
            },
            "scanning": {
                "spec": {"directories": ["spec"]},
                "code": {"directories": ["src", "lib"]},
            },
            "rules": {
                "hierarchy": {
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

    return _inject_optional_fields(tomlkit.dumps(doc))
