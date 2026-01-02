"""
elspais.commands.rules_cmd - Content rules management command.

View and manage content rule files.
"""

import argparse
import sys
from pathlib import Path
from typing import Optional

from elspais.config.loader import find_config_file, load_config
from elspais.core.content_rules import load_content_rules, load_content_rule


def run(args: argparse.Namespace) -> int:
    """
    Run the rules command.

    Args:
        args: Parsed command line arguments

    Returns:
        Exit code (0 for success)
    """
    action = getattr(args, "rules_action", None)

    if action == "list":
        return cmd_list(args)
    elif action == "show":
        return cmd_show(args)
    else:
        # Default to list
        return cmd_list(args)


def cmd_list(args: argparse.Namespace) -> int:
    """List configured content rules."""
    config_path = _get_config_path(args)

    if not config_path:
        print("No configuration file found. Run 'elspais init' to create one.")
        return 1

    config = load_config(config_path)
    base_path = config_path.parent

    rules = load_content_rules(config, base_path)

    if not rules:
        print("No content rules configured.")
        print("\nTo add content rules, use:")
        print('  elspais config add rules.content_rules "spec/AI-AGENT.md"')
        return 0

    print("Content Rules:")
    print("-" * 60)
    for rule in rules:
        rel_path = rule.file_path.relative_to(base_path) if base_path in rule.file_path.parents else rule.file_path
        print(f"  {rel_path}")
        print(f"    Title: {rule.title}")
        print(f"    Type: {rule.type}")
        if rule.applies_to:
            print(f"    Applies to: {', '.join(rule.applies_to)}")
        print()

    return 0


def cmd_show(args: argparse.Namespace) -> int:
    """Show content of a specific content rule."""
    config_path = _get_config_path(args)
    file_name = args.file

    if not config_path:
        print("No configuration file found.", file=sys.stderr)
        return 1

    config = load_config(config_path)
    base_path = config_path.parent

    # Load all rules and find the matching one
    rules = load_content_rules(config, base_path)

    matching_rule = None
    for rule in rules:
        if rule.file_path.name == file_name or str(rule.file_path).endswith(file_name):
            matching_rule = rule
            break

    # If not in config, try loading directly
    if not matching_rule:
        file_path = base_path / file_name
        if file_path.exists():
            try:
                matching_rule = load_content_rule(file_path)
            except Exception as e:
                print(f"Error loading file: {e}", file=sys.stderr)
                return 1
        else:
            print(f"Content rule not found: {file_name}", file=sys.stderr)
            return 1

    # Display the rule
    print(f"# {matching_rule.title}")
    print(f"Type: {matching_rule.type}")
    if matching_rule.applies_to:
        print(f"Applies to: {', '.join(matching_rule.applies_to)}")
    print(f"File: {matching_rule.file_path}")
    print("-" * 60)
    print(matching_rule.content)

    return 0


def _get_config_path(args: argparse.Namespace) -> Optional[Path]:
    """Get configuration file path from args or by discovery."""
    if hasattr(args, "config") and args.config:
        return args.config
    return find_config_file(Path.cwd())
