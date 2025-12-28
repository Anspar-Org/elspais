"""
elspais.commands.validate - Validate requirements command.

Validates requirements format, links, and hashes.
"""

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional

from elspais.config.loader import load_config, find_config_file, get_spec_directories
from elspais.config.defaults import DEFAULT_CONFIG
from elspais.core.patterns import PatternConfig, PatternValidator
from elspais.core.parser import RequirementParser
from elspais.core.rules import RuleEngine, RulesConfig, RuleViolation, Severity
from elspais.core.hasher import calculate_hash, verify_hash
from elspais.core.models import Requirement


def run(args: argparse.Namespace) -> int:
    """
    Run the validate command.

    Args:
        args: Parsed command line arguments

    Returns:
        Exit code (0 for success, 1 for validation errors)
    """
    # Find and load configuration
    config = load_configuration(args)
    if config is None:
        return 1

    # Determine spec directories (can be string or list)
    spec_dirs = get_spec_directories(args.spec_dir, config)
    if not spec_dirs:
        print("Error: No spec directories found", file=sys.stderr)
        return 1

    if not args.quiet:
        if len(spec_dirs) == 1:
            print(f"Validating requirements in: {spec_dirs[0]}")
        else:
            print(f"Validating requirements in: {', '.join(str(d) for d in spec_dirs)}")

    # Parse requirements
    pattern_config = PatternConfig.from_dict(config.get("patterns", {}))
    spec_config = config.get("spec", {})
    no_reference_values = spec_config.get("no_reference_values")
    parser = RequirementParser(pattern_config, no_reference_values=no_reference_values)
    skip_files = spec_config.get("skip_files", [])

    try:
        requirements = parser.parse_directories(spec_dirs, skip_files=skip_files)
    except Exception as e:
        print(f"Error parsing requirements: {e}", file=sys.stderr)
        return 1

    if not requirements:
        print("No requirements found.", file=sys.stderr)
        return 1

    if not args.quiet:
        print(f"Found {len(requirements)} requirements")

    # Run validation
    rules_config = RulesConfig.from_dict(config.get("rules", {}))
    engine = RuleEngine(rules_config)

    violations = engine.validate(requirements)

    # Add hash validation
    hash_violations = validate_hashes(requirements, config)
    violations.extend(hash_violations)

    # Add broken link validation
    link_violations = validate_links(requirements, args, config)
    violations.extend(link_violations)

    # Filter skipped rules
    if args.skip_rule:
        violations = [
            v for v in violations
            if not any(skip in v.rule_name for skip in args.skip_rule)
        ]

    # Report results
    errors = [v for v in violations if v.severity == Severity.ERROR]
    warnings = [v for v in violations if v.severity == Severity.WARNING]
    infos = [v for v in violations if v.severity == Severity.INFO]

    if violations and not args.quiet:
        print()
        for violation in sorted(violations, key=lambda v: (v.severity.value, v.requirement_id)):
            print(violation)
            print()

    # Summary
    if not args.quiet:
        print("─" * 60)
        valid_count = len(requirements) - len(set(v.requirement_id for v in errors))
        print(f"✓ {valid_count}/{len(requirements)} requirements valid")

        if errors:
            print(f"❌ {len(errors)} errors")
        if warnings:
            print(f"⚠️  {len(warnings)} warnings")

    # Return error if there are errors
    if errors:
        return 1

    if not args.quiet and not violations:
        print("✓ All requirements valid")

    return 0


def load_configuration(args: argparse.Namespace) -> Optional[Dict]:
    """Load configuration from file or use defaults."""
    if args.config:
        config_path = args.config
    else:
        config_path = find_config_file(Path.cwd())

    if config_path and config_path.exists():
        try:
            return load_config(config_path)
        except Exception as e:
            print(f"Error loading config: {e}", file=sys.stderr)
            return None
    else:
        # Use defaults
        return DEFAULT_CONFIG


def validate_hashes(requirements: Dict[str, Requirement], config: Dict) -> List[RuleViolation]:
    """Validate requirement hashes."""
    violations = []
    hash_length = config.get("validation", {}).get("hash_length", 8)
    algorithm = config.get("validation", {}).get("hash_algorithm", "sha256")

    for req_id, req in requirements.items():
        if req.hash:
            # Verify hash matches content
            expected_hash = calculate_hash(req.body, length=hash_length, algorithm=algorithm)
            if not verify_hash(req.body, req.hash, length=hash_length, algorithm=algorithm):
                violations.append(
                    RuleViolation(
                        rule_name="hash.mismatch",
                        requirement_id=req_id,
                        message=f"Hash mismatch: expected {expected_hash}, found {req.hash}",
                        severity=Severity.WARNING,
                        location=req.location(),
                    )
                )

    return violations


def validate_links(
    requirements: Dict[str, Requirement],
    args: argparse.Namespace,
    config: Dict,
) -> List[RuleViolation]:
    """Validate requirement links (implements references)."""
    violations = []

    # Load core requirements if this is an associated repo
    core_requirements = {}
    if args.core_repo:
        core_requirements = load_core_requirements(args.core_repo, config)

    all_requirements = {**core_requirements, **requirements}
    all_ids = set(all_requirements.keys())

    # Build set of all valid short IDs too
    short_ids = set()
    for req_id in all_ids:
        # Add various shortened forms
        parts = req_id.split("-")
        if len(parts) >= 2:
            # REQ-p00001 -> p00001
            short_ids.add("-".join(parts[1:]))
            # REQ-CAL-p00001 -> CAL-p00001
            if len(parts) >= 3:
                short_ids.add("-".join(parts[2:]))
                short_ids.add("-".join(parts[1:]))

    for req_id, req in requirements.items():
        for impl_id in req.implements:
            # Check if reference is valid
            if impl_id not in all_ids and impl_id not in short_ids:
                violations.append(
                    RuleViolation(
                        rule_name="link.broken",
                        requirement_id=req_id,
                        message=f"Implements reference not found: {impl_id}",
                        severity=Severity.ERROR,
                        location=req.location(),
                    )
                )

    return violations


def load_core_requirements(core_path: Path, config: Dict) -> Dict[str, Requirement]:
    """Load requirements from core repository."""
    if not core_path.exists():
        return {}

    # Find core config
    core_config_path = core_path / ".elspais.toml"
    if core_config_path.exists():
        core_config = load_config(core_config_path)
    else:
        core_config = config  # Use same config

    spec_dir = core_path / core_config.get("directories", {}).get("spec", "spec")
    if not spec_dir.exists():
        return {}

    pattern_config = PatternConfig.from_dict(core_config.get("patterns", {}))
    spec_config = core_config.get("spec", {})
    no_reference_values = spec_config.get("no_reference_values")
    parser = RequirementParser(pattern_config, no_reference_values=no_reference_values)
    skip_files = spec_config.get("skip_files", [])

    try:
        return parser.parse_directory(spec_dir, skip_files=skip_files)
    except Exception:
        return {}
