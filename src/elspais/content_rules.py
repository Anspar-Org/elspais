"""
elspais.content_rules - Content rule loading and parsing.

Content rules are markdown files that provide semantic validation guidance
for requirements authoring. They can include YAML frontmatter for metadata.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from elspais.config.schema import ElspaisConfig

_log = logging.getLogger(__name__)


def _validate_config(config: dict[str, Any]) -> ElspaisConfig:
    """Validate a config dict into ElspaisConfig (see config.validate_config)."""
    from elspais.config import validate_config

    return validate_config(config)


@dataclass
class ContentRule:
    """A content rule loaded from a markdown file."""

    file_path: Path
    title: str
    content: str
    type: str = "guidance"
    applies_to: list[str] = field(default_factory=list)


# Implements: REQ-d00285-A, REQ-d00285-G
@dataclass(frozen=True)
class ContentRuleFault:
    """A configured content rule that was not loaded, and why.

    A project configures a rule so that authoring is guided by it. A rule
    that is not there, or that cannot be read, guides nothing -- and the
    authoring surface that never mentions it looks exactly like one where the
    project configured no such rule at all. The path is the one the
    configuration named, so a reader can see whether the entry or the file is
    what is wrong.

    Attributes:
        path: The rule file as the configuration named it, resolved against
            the base path.
        cause: Why it was not loaded.
    """

    path: str
    cause: str


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
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


def _parse_simple_yaml(lines: list[str]) -> dict[str, Any]:
    """
    Parse simple YAML format (zero-dependency).

    Supports:
    - key: value
    - key: [item1, item2]
    - key:
        - item1
        - item2
    """
    result: dict[str, Any] = {}
    current_key = None
    current_list: list[str] = []

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


# Implements: REQ-d00285-G
def load_content_rules(
    config: dict[str, Any],
    base_path: Path,
    faults: list[ContentRuleFault] | None = None,
) -> list[ContentRule]:
    """
    Load all content rules from configuration.

    A rule the configuration names and this call did not load is recorded,
    never dropped: an absent rule and a rule a project never configured
    produce the same empty guidance, and only the record tells them apart.

    Args:
        config: Configuration dictionary
        base_path: Base path for resolving relative paths
        faults: Collector for the rules that were not loaded. A caller that
            supplies one reports them itself. A caller that supplies none
            gets them on the warning log, so the condition is disclosed
            somewhere in every case.

    Returns:
        List of ContentRule objects
    """
    typed_config = _validate_config(config)
    rule_paths = typed_config.rules.content_rules

    recorded: list[ContentRuleFault] = faults if faults is not None else []
    rules = []
    for rel_path in rule_paths:
        full_path = base_path / rel_path
        if not full_path.exists():
            recorded.append(
                ContentRuleFault(
                    path=str(full_path),
                    cause="the configuration names this content rule, but there is no file there",
                )
            )
            continue
        try:
            rule = load_content_rule(full_path)
        except (OSError, UnicodeDecodeError) as exc:
            recorded.append(
                ContentRuleFault(
                    path=str(full_path),
                    cause=f"the content rule file could not be read: {exc}",
                )
            )
            continue
        rules.append(rule)

    if faults is None:
        for fault in recorded:
            _log.warning("content rule not loaded: %s -- %s", fault.path, fault.cause)

    return rules


__all__ = [
    "ContentRule",
    "ContentRuleFault",
    "parse_frontmatter",
    "load_content_rule",
    "load_content_rules",
]
