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
# Per-field comments for generated TOML.  Keyed by dotted TOML path.
# Section-level comments use the bare section name (e.g. "project").
# Field-level comments use the full path (e.g. "project.namespace").
# 1 line max.  For enums, list valid values.  Refer to docs for detail.
_FIELD_COMMENTS: dict[str, str] = {
    # --- top-level scalars ---
    "version": "Config schema version (do not change)",
    "cli_ttl": "Daemon TTL in minutes (>0 = auto-start, 0 = disabled, <0 = no timeout)",
    "stats": "File path for MCP tool-usage statistics (optional)",
    # --- [project] ---
    "project": "Project identity",
    "project.namespace": "Prefix for requirement IDs (e.g. REQ -> REQ-p00001)",
    "project.name": "Project display name",
    # --- [id-patterns] ---
    "id-patterns": "Requirement ID format and type definitions",
    "id-patterns.canonical": "ID template; vars: {namespace}, {level.letter}, {component}",
    "id-patterns.separators": "Characters treated as equivalent separators when matching IDs",
    "id-patterns.prefix_optional": "If true, namespace prefix is optional when matching IDs",
    "id-patterns.aliases": "Named shorthand patterns for ID matching",
    "id-patterns.component": "Component (numeric part) of the ID",
    "id-patterns.component.style": '"numeric" | "alphanumeric" | "named"',
    "id-patterns.component.digits": "Number of digits in numeric components",
    "id-patterns.component.leading_zeros": "Pad numeric components with leading zeros",
    "id-patterns.component.pattern": "Regex pattern (alphanumeric style only)",
    "id-patterns.component.max_length": "Max length (named style only)",
    "id-patterns.assertions": "Assertion label format",
    "id-patterns.assertions.label_style": (
        '"uppercase" (A,B,C) | "numeric" (0,1,2) | "numeric_1based" | "alphanumeric"'
    ),
    "id-patterns.assertions.max_count": "Maximum number of assertions per requirement",
    "id-patterns.assertions.zero_pad": "Pad numeric assertion labels with leading zero",
    "id-patterns.assertions.multi_separator": (
        'Separator for multi-assertion refs (e.g. "+" -> A+B+C)'
    ),
    "id-patterns.associated": "Associated (cross-repo) prefix formatting",
    "id-patterns.associated.enabled": "Enable associated prefix in IDs",
    "id-patterns.associated.position": '"after_prefix" | "before_prefix"',
    "id-patterns.associated.format": '"uppercase" | "lowercase"',
    "id-patterns.associated.length": "Length of associated prefix code",
    "id-patterns.associated.separator": "Separator between associated prefix and rest of ID",
    # --- [levels] ---
    "levels": "Requirement hierarchy levels (name -> config)",
    "levels.*.rank": "Numeric rank (1 = highest, e.g. PRD)",
    "levels.*.letter": "Single letter used in IDs (e.g. p -> REQ-p00001)",
    "levels.*.display_name": "Human-readable name for reports",
    "levels.*.implements": "Which levels this level can implement (list of level names)",
    # --- [scanning] ---
    "scanning": "File scanning configuration",
    "scanning.skip": "Global skip patterns (applied to all scan kinds)",
    "scanning.spec": "Spec file scanning",
    "scanning.spec.directories": "Directories to scan for spec files",
    "scanning.spec.file_patterns": "Glob patterns for spec files",
    "scanning.spec.skip_files": "Filenames to skip in spec directories",
    "scanning.spec.skip_dirs": "Subdirectories to skip in spec directories",
    "scanning.spec.index_file": "Index file for ordering (e.g. INDEX.md)",
    "scanning.code": "Code file scanning",
    "scanning.code.directories": "Directories to scan for code files",
    "scanning.code.file_patterns": "Glob patterns for code files",
    "scanning.code.skip_files": "Filenames to skip in code directories",
    "scanning.code.skip_dirs": "Subdirectories to skip in code directories",
    "scanning.code.source_roots": "Import resolution roots",
    "scanning.test": "Test file scanning and reference detection",
    "scanning.test.enabled": "Enable test file scanning",
    "scanning.test.directories": "Directories to scan for test files",
    "scanning.test.file_patterns": "Glob patterns for test files",
    "scanning.test.skip_files": "Filenames to skip in test directories",
    "scanning.test.skip_dirs": "Subdirectories to skip in test directories",
    "scanning.test.prescan_command": (
        "External command for function detection (stdin: paths, stdout: JSON)"
    ),
    "scanning.test.reference_keyword": 'Keyword for test->requirement refs (e.g. "Verifies")',
    "scanning.test.reference_patterns": "Additional regex patterns for reference detection",
    "scanning.result": "Test result file scanning",
    "scanning.result.directories": "Directories to scan for test results",
    "scanning.result.file_patterns": "Glob patterns for result files",
    "scanning.result.skip_files": "Filenames to skip in result directories",
    "scanning.result.skip_dirs": "Subdirectories to skip in result directories",
    "scanning.result.run_meta_file": "Path to test run metadata JSON file",
    "scanning.coverage": "Code coverage report scanning",
    "scanning.coverage.directories": "Directories to scan for coverage reports",
    "scanning.coverage.file_patterns": "Glob patterns for coverage files",
    "scanning.coverage.skip_files": "Filenames to skip in coverage directories",
    "scanning.coverage.skip_dirs": "Subdirectories to skip in coverage directories",
    "scanning.journey": "User journey file scanning",
    "scanning.journey.directories": "Directories to scan for journey files",
    "scanning.journey.file_patterns": "Glob patterns for journey files",
    "scanning.journey.skip_files": "Filenames to skip in journey directories",
    "scanning.journey.skip_dirs": "Subdirectories to skip in journey directories",
    "scanning.docs": "Documentation file scanning",
    "scanning.docs.directories": "Directories to scan for documentation",
    "scanning.docs.file_patterns": "Glob patterns for doc files",
    "scanning.docs.skip_files": "Filenames to skip in docs directories",
    "scanning.docs.skip_dirs": "Subdirectories to skip in docs directories",
    # --- [rules] ---
    "rules": "Validation rules",
    "rules.protected_branches": "Branches where edit mode is disabled (names or globs)",
    "rules.content_rules": "Content validation rules (list of rule module paths)",
    "rules.hierarchy": "Hierarchy validation settings",
    "rules.hierarchy.allow_circular": "Allow circular requirement references",
    "rules.hierarchy.allow_structural_orphans": "Allow nodes without a FILE ancestor",
    "rules.hierarchy.cross_repo_implements": "Allow implements edges across repos",
    "rules.hierarchy.allow_orphans": "Allow orphaned nodes in the graph",
    "rules.format": "Format enforcement rules",
    "rules.format.require_hash": "Require content hash in requirement footer",
    "rules.format.require_assertions": "Require at least one assertion per requirement",
    "rules.format.require_status": "Require Status field in requirement metadata",
    "rules.format.require_rationale": "Require Rationale section in requirements",
    "rules.format.no_assertions_severity": (
        '"warning" | "info" — severity for REQs with no assertions'
    ),
    "rules.format.no_traceability_severity": (
        '"warning" | "info" — severity for code/test files with no REQ markers'
    ),
    "rules.format.status_roles": "Status role classification (metrics/viewer behavior)",
    "rules.format.status_roles.active": "Committed, normative — counted in all metrics",
    "rules.format.status_roles.provisional": "In-progress toward active — excluded from coverage",
    "rules.format.status_roles.aspirational": "Future/planning — excluded from coverage+analysis",
    "rules.format.status_roles.retired": "Concluded — excluded from everything, hidden by default",
    "rules.coverage": "Coverage severity tiers per dimension (ok | info | warning | error)",
    "rules.coverage.implemented": "Code implements assertions",
    "rules.coverage.tested": "Tests reference assertions",
    "rules.coverage.verified": "Test results exist for assertions",
    "rules.coverage.uat_coverage": "User journeys validate assertions",
    "rules.coverage.uat_verified": "User journey results exist",
    "rules.coverage.*.full_direct": "All assertions covered by direct references",
    "rules.coverage.*.full_indirect": "Covered via parent/child rollup only",
    "rules.coverage.*.partial": "Some assertions covered, some not",
    "rules.coverage.*.none": "No coverage at all",
    "rules.coverage.*.failing": "Has coverage but test results show failures",
    "rules.references": "Severity for code/test references to non-active requirements",
    "rules.references.retired": ('"ok" | "info" | "warning" | "error" — refs to retired REQs'),
    "rules.references.provisional": (
        '"ok" | "info" | "warning" | "error" — refs to provisional REQs'
    ),
    "rules.references.aspirational": (
        '"ok" | "info" | "warning" | "error" — refs to aspirational REQs'
    ),
    # --- [changelog] ---
    "changelog": "Changelog enforcement for requirement changes",
    "changelog.hash_current": "Track current content hash in changelog entries",
    "changelog.present": "Require changelog section in requirements",
    "changelog.id_source": '"gh" (GitHub) | "env" | "manual" — source for author IDs',
    "changelog.date_format": '"iso" (YYYY-MM-DD) | "us" (MM/DD/YYYY) | "eu" (DD/MM/YYYY)',
    "changelog.author_id_format": '"email" | "username" | "full_name"',
    "changelog.allowed_author_ids": '"all" or list of allowed author identifiers',
    "changelog.require": "Which changelog fields are mandatory",
    "changelog.require.reason": "Require a reason for each change",
    "changelog.require.author_name": "Require author name in changelog entries",
    "changelog.require.author_id": "Require author ID in changelog entries",
    "changelog.require.change_order": "Require changes in chronological order",
    # --- [keywords] ---
    "keywords": "Keyword extraction settings",
    "keywords.min_length": "Minimum word length for keyword extraction",
    # --- [validation] ---
    "validation": "Hash and validation settings",
    "validation.hash_mode": '"normalized-text" — how requirement content is hashed',
    "validation.hash_algorithm": '"sha256" (default) — hash algorithm',
    "validation.hash_length": "Hash truncation length in chars (default: 8)",
    "validation.allow_unresolved_cross_repo": "Suppress errors for unresolved cross-repo refs",
    "validation.strict_hierarchy": "Strict hierarchy validation mode",
    # --- [terms] ---
    "terms": "Defined terms: glossary, index, and health checks",
    "terms.output_dir": "Directory for generated glossary and index files",
    "terms.markup_styles": "Markup styles recognized as term references",
    "terms.exclude_files": "Files excluded from term scanning",
    "terms.severity": "Severity levels for defined-terms health checks",
    "terms.severity.duplicate": "Duplicate term definitions",
    "terms.severity.undefined": "References to undefined terms",
    "terms.severity.unmarked": "Unmarked usages of defined terms",
    "terms.severity.unused": "Defined terms with no references",
    "terms.severity.bad_definition": "Malformed term definitions",
    "terms.severity.collection_empty": "Empty collection terms",
    "terms.severity.canonical_form": "Non-canonical form usage",
    "terms.severity.changed": "Changed definitions with unresolved review",
    # --- [output] ---
    "output": "Output settings",
    "output.formats": 'Output format list (e.g. ["json", "csv"])',
    "output.dir": "Directory for generated output files",
    # --- [associates] ---
    "associates": "Associated repository definitions for cross-repo federation",
    "associates.*.path": "Path to the associated repository (absolute or relative to repo root)",
    "associates.*.namespace": "Namespace prefix for the associated repo's requirements",
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
        "result": {
            "directories": [],
            "file_patterns": [],
        },
        "coverage": {
            "directories": ["."],
            "file_patterns": [],
        },
        "journey": {
            "directories": ["spec"],
            "file_patterns": ["*.md"],
        },
        "docs": {
            "directories": ["docs"],
            "file_patterns": ["*.md"],
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
            "status_roles": {
                "active": ["Active"],
                "provisional": ["Draft", "Proposed"],
                "aspirational": ["Roadmap", "Future"],
                "retired": ["Deprecated", "Superseded"],
            },
        },
        "protected_branches": ["main", "master"],
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
# Top-level scalars (version, cli_ttl, stats) are handled separately.
_CORE_SECTIONS = [
    "project",
    "id-patterns",
    "levels",
    "scanning",
    "rules",
    "changelog",
    "keywords",
    "validation",
    "terms",
    "output",
]

# Sections to include in associated template.
_ASSOCIATED_SECTIONS = [
    "project",
    "id-patterns",
    "levels",
    "scanning",
    "rules",
    "keywords",
    "validation",
    "terms",
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


def _add_field_comment(container: Any, field_path: str) -> None:
    """Add a TOML comment line above a field if one exists in _FIELD_COMMENTS."""
    comment = _FIELD_COMMENTS.get(field_path)
    if not comment:
        # Try wildcard match for dict-of-model fields like levels.*, coverage.*
        parts = field_path.rsplit(".", 1)
        if len(parts) == 2:
            parent, field = parts
            parent_parts = parent.rsplit(".", 1)
            if len(parent_parts) == 2:
                comment = _FIELD_COMMENTS.get(f"{parent_parts[0]}.*.{field}")
            if not comment:
                comment = _FIELD_COMMENTS.get(f"{parent}.*.{field}")
    if comment:
        container.add(tomlkit.comment(comment))


def _add_table(
    doc: tomlkit.TOMLDocument,
    key: str,
    value: Any,
    comment: str | None = None,
) -> None:
    """Add a key/value pair to *doc*, inserting field-level comments."""
    if comment:
        for line in comment.split("\n"):
            doc.add(tomlkit.comment(line))

    if not isinstance(value, dict):
        _add_field_comment(doc, key)
        doc.add(key, value)
        return

    tbl = tomlkit.table()
    for k, v in value.items():
        field_path = f"{key}.{k}"
        if isinstance(v, dict):
            sub = tomlkit.table()
            for sk, sv in v.items():
                sub_field_path = f"{field_path}.{sk}"
                if isinstance(sv, dict):
                    inner = tomlkit.table()
                    for ik, iv in sv.items():
                        _add_field_comment(inner, f"{sub_field_path}.{ik}")
                        inner.add(ik, iv)
                    sub.add(sk, inner)
                else:
                    _add_field_comment(sub, sub_field_path)
                    sub.add(sk, sv)
            sub_comment = _FIELD_COMMENTS.get(field_path)
            if sub_comment:
                sub.comment(sub_comment)
            tbl.add(k, sub)
        else:
            _add_field_comment(tbl, field_path)
            tbl.add(k, v)
    doc.add(key, tbl)


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

    # Top-level scalars (field comments are looked up by _add_field_comment)
    _add_table(doc, "version", data["version"])
    _add_table(doc, "cli_ttl", data.get("cli_ttl", 30))
    _add_table(doc, "stats", data.get("stats", ""))
    doc.add(tomlkit.nl())

    for section in sections:
        if section not in data:
            continue
        comment = _FIELD_COMMENTS.get(section)
        _add_table(doc, section, data[section], comment)
        doc.add(tomlkit.nl())

    return tomlkit.dumps(doc)
