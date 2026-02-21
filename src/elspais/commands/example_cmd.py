"""
elspais.commands.example_cmd - Display requirement format examples.

Quick reference command for requirement format discovery.
"""

import argparse
from pathlib import Path

# ============================================================================
# Requirement Format Templates
# ============================================================================

REQUIREMENT_TEMPLATE = """# REQ-{type}{id}: Requirement Title

**Level**: {level} | **Status**: Draft | **Implements**: {implements}

## Assertions

A. The system SHALL <do something specific>.
B. The system SHALL <do another thing>.

## Rationale

<optional non-normative explanation>

*End* *Requirement Title* | **Hash**: 00000000

---
Level codes: p = PRD (Product), o = OPS (Operations), d = DEV (Development)
Implements: Use "-" for top-level requirements, or REQ-pXXXXX for children
Hash: Run `elspais fix` to compute automatically
"""

REQUIREMENT_TEMPLATE_PRD = REQUIREMENT_TEMPLATE.format(
    type="p", id="00001", level="PRD", implements="-"
)

REQUIREMENT_TEMPLATE_OPS = REQUIREMENT_TEMPLATE.format(
    type="o", id="00001", level="Ops", implements="REQ-p00001"
)

REQUIREMENT_TEMPLATE_DEV = REQUIREMENT_TEMPLATE.format(
    type="d", id="00001", level="Dev", implements="REQ-o00001"
)

JOURNEY_TEMPLATE = """# JNY-{prefix}-01: User Journey Title

**Actor**: End User
**Goal**: <what the user wants to accomplish>

## Steps

1. User <does something>
2. System <responds with something>
3. User <completes action>

## Requirements

- REQ-p00001: <requirement title>
- REQ-p00002: <requirement title>

*End* *User Journey Title*

---
Journey prefix: Use meaningful 2-4 char codes (e.g., AUTH, PAY, ONBD)
Steps: Describe the happy path interaction
Requirements: Link to PRD requirements this journey validates
"""

ASSERTION_RULES = """# Assertion Format Rules

## Basic Format
Each assertion is a labeled statement using SHALL language:

    A. The system SHALL <do something specific>.
    B. The system SHALL <do another thing>.

## Label Styles (configurable)
- uppercase: A, B, C ... Z (default, max 26)
- numeric: 1, 2, 3 ... or 01, 02, 03 ...
- alphanumeric: 0-9, A-Z (max 36)

## Keywords
- SHALL: Required functionality (normative)
- SHOULD: Recommended but not required
- MAY: Optional functionality

## Placeholders for Removed Assertions
When an assertion is removed, use a placeholder to maintain sequential labels:

    A. The system SHALL validate user input.
    B. Removed.
    C. The system SHALL log all transactions.

Valid placeholder values: "Removed", "obsolete", "deprecated", "N/A", "-", "reserved"

## Test References
Tests can reference specific assertions:

    # test_auth.py
    def test_user_validation():
        \"\"\"Test REQ-d00001-A assertion.\"\"\"
        ...

## Configuration

```toml
[patterns.assertions]
label_style = "uppercase"  # "uppercase", "numeric", "alphanumeric"
max_count = 26

[rules.format]
require_assertions = true
require_shall = true
labels_sequential = true
```
"""

ID_PATTERNS_TEMPLATE = """# Requirement ID Patterns

## Current Configuration

The ID pattern is built from these components:
  prefix     = {prefix}
  id_template = {id_template}

## Standard ID Formats

**Core repository:**
  PRD: {prefix}-p00001
  OPS: {prefix}-o00001
  DEV: {prefix}-d00001

**With assertion reference:**
  {prefix}-d00001-A    (assertion A of DEV requirement)

**Associated repository (if enabled):**
  TTN-{prefix}-p00001  (prefixed with associated code)

## Type Levels

{types}

## Examples in this project

  {prefix}-p00001: PRD requirement (Product, Level 1)
  {prefix}-o00001: OPS requirement (Operations, Level 2)
  {prefix}-d00001: DEV requirement (Development, Level 3)

Run `elspais config show --section patterns` for full pattern configuration.
"""

DEFAULT_TEMPLATE = """# Requirement Format Quick Reference

Use `elspais example <type>` for detailed templates:

  elspais example requirement   Show full requirement template
  elspais example journey       Show user journey template
  elspais example assertion     Show assertion rules and examples
  elspais example ids           Show ID patterns from your config
  elspais example --full        Display spec/requirements-spec.md

## Basic Requirement Structure

```markdown
# REQ-d00001: Title

**Level**: Dev | **Status**: Draft | **Implements**: REQ-o00001

## Assertions

A. The system SHALL <do something>.

## Rationale

<optional explanation>

*End* *Title* | **Hash**: 00000000
```

## Key Rules

1. **Assertions** - Use SHALL for required behavior
2. **Implements** - Children reference parents (dev -> ops -> prd)
3. **Hash** - Auto-computed with `elspais fix`
4. **Sequential labels** - A, B, C... don't skip letters

Run `elspais validate` to check format compliance.
"""


def run(args: argparse.Namespace) -> int:
    """
    Run the example command.

    Args:
        args: Parsed command line arguments

    Returns:
        Exit code (0 for success)
    """
    # Handle --full flag first
    if args.full:
        return show_full_spec(args)

    # Handle subcommand
    subcommand = args.example_type

    if subcommand == "requirement":
        return show_requirement_template(args)
    elif subcommand == "journey":
        return show_journey_template(args)
    elif subcommand == "assertion":
        return show_assertion_rules(args)
    elif subcommand == "ids":
        return show_id_patterns(args)
    else:
        # Default: show quick reference
        print(DEFAULT_TEMPLATE)
        return 0


def show_requirement_template(args: argparse.Namespace) -> int:
    """Show requirement template."""
    print("# Requirement Templates\n")
    print("## PRD (Product Requirement)")
    print(REQUIREMENT_TEMPLATE_PRD)
    print("\n## OPS (Operations Requirement)")
    print(REQUIREMENT_TEMPLATE_OPS)
    print("\n## DEV (Development Requirement)")
    print(REQUIREMENT_TEMPLATE_DEV)
    return 0


def show_journey_template(args: argparse.Namespace) -> int:
    """Show user journey template."""
    print(JOURNEY_TEMPLATE)
    return 0


def show_assertion_rules(args: argparse.Namespace) -> int:
    """Show assertion format rules."""
    print(ASSERTION_RULES)
    return 0


def show_id_patterns(args: argparse.Namespace) -> int:
    """Show ID patterns from current configuration."""
    from elspais.config import load_config

    try:
        config = load_config(args.config if hasattr(args, "config") else None)
    except Exception:
        # Use defaults if no config found
        config = {
            "patterns": {
                "prefix": "REQ",
                "id_template": "{prefix}-{type}{id}",
                "types": {
                    "prd": {"id": "p", "name": "Product Requirement", "level": 1},
                    "ops": {"id": "o", "name": "Operations Requirement", "level": 2},
                    "dev": {"id": "d", "name": "Development Requirement", "level": 3},
                },
            }
        }

    patterns = config.get("patterns", {})
    prefix = patterns.get("prefix", "REQ")
    id_template = patterns.get("id_template", "{prefix}-{type}{id}")
    types = patterns.get("types", {})

    # Format types section
    types_text = ""
    for type_key, type_info in types.items():
        if isinstance(type_info, dict):
            type_id = type_info.get("id", type_key[0])
            type_name = type_info.get("name", type_key.upper())
            type_level = type_info.get("level", "?")
            types_text += f"  {type_key.upper()}: {type_id} = Level {type_level} ({type_name})\n"

    output = ID_PATTERNS_TEMPLATE.format(
        prefix=prefix,
        id_template=id_template,
        types=types_text.strip() if types_text else "  (no types configured)",
    )
    print(output)
    return 0


def show_full_spec(args: argparse.Namespace) -> int:
    """Display the full requirements-spec.md if it exists."""
    from elspais.config import load_config

    try:
        config = load_config(args.config if hasattr(args, "config") else None)
    except Exception:
        config = {"directories": {"spec": "spec"}}

    spec_dir = config.get("directories", {}).get("spec", "spec")
    spec_path = Path.cwd() / spec_dir / "requirements-spec.md"

    # Also check for requirements-format.md (alternative name)
    alt_path = Path.cwd() / spec_dir / "requirements-format.md"

    if spec_path.exists():
        print(spec_path.read_text())
        return 0
    elif alt_path.exists():
        print(alt_path.read_text())
        return 0
    else:
        print("No requirements specification found.")
        print("Searched:")
        print(f"  - {spec_path}")
        print(f"  - {alt_path}")
        print()
        print("Use `elspais format requirement` for a template instead.")
        return 1
