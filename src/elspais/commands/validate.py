"""
elspais.commands.validate - Validate requirements command.

Validates requirements format, links, and hashes.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from elspais.config.defaults import DEFAULT_CONFIG
from elspais.config.loader import find_config_file, get_spec_directories, load_config
from elspais.core.hasher import calculate_hash, verify_hash
from elspais.core.models import ParseWarning, Requirement
from elspais.core.parser import RequirementParser
from elspais.core.patterns import PatternConfig
from elspais.core.rules import RuleEngine, RulesConfig, RuleViolation, Severity
from elspais.testing.config import TestingConfig


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
        parse_result = parser.parse_directories(spec_dirs, skip_files=skip_files)
        requirements = dict(parse_result)  # ParseResult supports dict-like access
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

    # Add parser warnings (duplicates, etc.) as violations
    parse_violations = convert_parse_warnings_to_violations(parse_result.warnings)
    violations.extend(parse_violations)

    # Filter skipped rules
    if args.skip_rule:
        violations = [
            v for v in violations
            if not any(skip in v.rule_name for skip in args.skip_rule)
        ]

    # JSON output mode - output and exit
    if getattr(args, 'json', False):
        # Test mapping (if enabled)
        test_data = None
        testing_config = TestingConfig.from_dict(config.get("testing", {}))
        if should_scan_tests(args, testing_config):
            from elspais.testing.mapper import TestMapper

            base_path = find_project_root(spec_dirs)
            ignore_dirs = config.get("directories", {}).get("ignore", [])
            mapper = TestMapper(testing_config)
            test_data = mapper.map_tests(
                requirement_ids=set(requirements.keys()),
                base_path=base_path,
                ignore=ignore_dirs,
            )

        print(format_requirements_json(requirements, violations, test_data))
        errors = [v for v in violations if v.severity == Severity.ERROR]
        return 1 if errors else 0

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
        valid_count = len(requirements) - len({v.requirement_id for v in errors})
        print(f"✓ {valid_count}/{len(requirements)} requirements valid")

        if errors:
            print(f"❌ {len(errors)} errors")
        if warnings:
            print(f"⚠️  {len(warnings)} warnings")
        if infos and getattr(args, "verbose", False):
            print(f"ℹ️  {len(infos)} info")

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


def should_scan_tests(args: argparse.Namespace, config: TestingConfig) -> bool:
    """
    Determine if test scanning should run based on args and config.

    Args:
        args: Command line arguments
        config: Testing configuration

    Returns:
        True if test scanning should run
    """
    if getattr(args, 'no_tests', False):
        return False
    if getattr(args, 'tests', False):
        return True
    return config.enabled


def find_project_root(spec_dirs: List[Path]) -> Path:
    """
    Find the project root from spec directories.

    Looks for .elspais.toml or .git directory above spec dirs.

    Args:
        spec_dirs: List of spec directories

    Returns:
        Project root path
    """
    if not spec_dirs:
        return Path.cwd()

    # Start from first spec dir and look upward
    current = spec_dirs[0].resolve()
    while current != current.parent:
        if (current / ".elspais.toml").exists():
            return current
        if (current / ".git").exists():
            return current
        current = current.parent

    return Path.cwd()


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


def convert_parse_warnings_to_violations(
    warnings: List[ParseWarning],
) -> List[RuleViolation]:
    """Convert parser warnings (like duplicates) to rule violations.

    The parser detects duplicate REQ IDs and generates ParseWarning objects.
    This function converts them to RuleViolation objects so they appear in
    validation output.

    Args:
        warnings: List of ParseWarning objects from parser

    Returns:
        List of RuleViolation objects for duplicate IDs
    """
    violations = []
    for warning in warnings:
        if "duplicate" in warning.message.lower():
            violations.append(
                RuleViolation(
                    rule_name="id.duplicate",
                    requirement_id=warning.requirement_id,
                    message=warning.message,
                    severity=Severity.ERROR,
                    location=f"{warning.file_path}:{warning.line_number}",
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


def format_requirements_json(
    requirements: Dict[str, Requirement],
    violations: List[RuleViolation],
    test_data: Optional[Any] = None,
) -> str:
    """
    Format requirements as JSON in hht_diary compatible format.

    Args:
        requirements: Dictionary of requirement ID to Requirement
        violations: List of rule violations for error metadata
        test_data: Optional TestMappingResult with test coverage data

    Returns:
        JSON string with requirement data
    """
    # Build violation lookup for cycle/conflict detection
    violation_by_req: Dict[str, List[RuleViolation]] = {}
    for v in violations:
        if v.requirement_id not in violation_by_req:
            violation_by_req[v.requirement_id] = []
        violation_by_req[v.requirement_id].append(v)

    output = {}
    for req_id, req in requirements.items():
        req_violations = violation_by_req.get(req_id, [])

        # Check for specific violation types
        is_cycle = any("cycle" in v.rule_name.lower() for v in req_violations)
        is_conflict = any(
            "conflict" in v.rule_name.lower() or "duplicate" in v.rule_name.lower()
            for v in req_violations
        )
        conflict_with = None
        cycle_path = None

        for v in req_violations:
            if "duplicate" in v.rule_name.lower():
                # Try to extract conflicting ID from message
                conflict_with = v.message
            if "cycle" in v.rule_name.lower():
                cycle_path = v.message

        # Build requirement data matching hht_diary format
        output[req_id] = {
            "title": req.title,
            "status": req.status,
            "level": req.level,
            "body": req.body.strip(),
            "rationale": (req.rationale or "").strip(),
            "file": req.file_path.name if req.file_path else "",
            "filePath": str(req.file_path) if req.file_path else "",
            "line": req.line_number or 0,
            "implements": req.implements,
            "hash": req.hash or "",
            "subdir": req.subdir,
            "isConflict": is_conflict,
            "conflictWith": conflict_with,
            "isCycle": is_cycle,
            "cyclePath": cycle_path,
        }

        # Include assertions if present
        if req.assertions:
            output[req_id]["assertions"] = [
                {"label": a.label, "text": a.text, "isPlaceholder": a.is_placeholder}
                for a in req.assertions
            ]

        # Include test data if available
        if test_data and req_id in test_data.requirement_data:
            td = test_data.requirement_data[req_id]
            output[req_id]["test_count"] = td.test_count
            output[req_id]["test_passed"] = td.test_passed
            output[req_id]["test_result_files"] = td.test_result_files
        else:
            # Default values when no test data
            output[req_id]["test_count"] = 0
            output[req_id]["test_passed"] = 0
            output[req_id]["test_result_files"] = []

    return json.dumps(output, indent=2)
