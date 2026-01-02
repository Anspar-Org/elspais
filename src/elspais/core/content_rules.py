"""
elspais.core.content_rules - Content rule loading and parsing.

Content rules are markdown files that provide semantic validation guidance
for requirements authoring. They can include YAML frontmatter for metadata.
"""

import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

from elspais.core.models import ContentRule


def parse_frontmatter(text: str) -> Tuple[Dict[str, Any], str]:
    """
    Parse YAML frontmatter from markdown text.

    Frontmatter is enclosed between --- markers at the start of the file.

    Args:
        text: Full markdown text

    Returns:
        Tuple of (metadata dict, content without frontmatter)
    """
    # Check for frontmatter markers
    if not text.startswith("---"):
        return {}, text

    # Find the closing ---
    lines = text.split("\n")
    end_idx = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end_idx = i
            break

    if end_idx is None:
        return {}, text

    # Extract frontmatter lines
    frontmatter_lines = lines[1:end_idx]
    content_lines = lines[end_idx + 1 :]

    # Parse simple YAML (zero-dependency)
    metadata = _parse_simple_yaml(frontmatter_lines)
    content = "\n".join(content_lines).lstrip("\n")

    return metadata, content


def _parse_simple_yaml(lines: List[str]) -> Dict[str, Any]:
    """
    Parse simple YAML format (zero-dependency).

    Supports:
    - key: value
    - key: [item1, item2]
    - key:
        - item1
        - item2
    """
    result: Dict[str, Any] = {}
    current_key = None
    current_list: List[str] = []

    for line in lines:
        stripped = line.strip()

        # Skip empty lines and comments
        if not stripped or stripped.startswith("#"):
            continue

        # Check for list item
        if stripped.startswith("- "):
            if current_key:
                current_list.append(stripped[2:].strip())
            continue

        # Check for key: value
        if ":" in stripped:
            # Save previous list if any
            if current_key and current_list:
                result[current_key] = current_list
                current_list = []

            key, _, value = stripped.partition(":")
            key = key.strip()
            value = value.strip()

            if value:
                # Inline value
                if value.startswith("[") and value.endswith("]"):
                    # Inline list
                    items = value[1:-1].split(",")
                    result[key] = [item.strip().strip("\"'") for item in items if item.strip()]
                else:
                    # Simple value
                    result[key] = value.strip("\"'")
                current_key = None
            else:
                # Start of a list
                current_key = key
                current_list = []

    # Save final list if any
    if current_key and current_list:
        result[current_key] = current_list

    return result


def load_content_rule(file_path: Path) -> ContentRule:
    """
    Load a single content rule file.

    Args:
        file_path: Path to the markdown file

    Returns:
        ContentRule object

    Raises:
        FileNotFoundError: If file doesn't exist
    """
    if not file_path.exists():
        raise FileNotFoundError(f"Content rule file not found: {file_path}")

    text = file_path.read_text(encoding="utf-8")
    metadata, content = parse_frontmatter(text)

    return ContentRule(
        file_path=file_path,
        title=metadata.get("title", file_path.name),
        content=content,
        type=metadata.get("type", "guidance"),
        applies_to=metadata.get("applies_to", []),
    )


def load_content_rules(
    config: Dict[str, Any],
    base_path: Path,
) -> List[ContentRule]:
    """
    Load all content rules from configuration.

    Args:
        config: Configuration dictionary
        base_path: Base path for resolving relative paths

    Returns:
        List of ContentRule objects (missing files are skipped)
    """
    rules_config = config.get("rules", {})
    rule_paths = rules_config.get("content_rules", [])

    rules = []
    for rel_path in rule_paths:
        full_path = base_path / rel_path
        if full_path.exists():
            try:
                rule = load_content_rule(full_path)
                rules.append(rule)
            except Exception:
                # Skip files that can't be loaded
                pass

    return rules
