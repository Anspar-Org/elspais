"""Documentation loader for CLI docs command.

Loads markdown documentation files from docs/cli/ directory.
Supports both installed package and development repository layouts.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


# Ordered list of documentation topics
TOPIC_ORDER = [
    "quickstart",
    "format",
    "hierarchy",
    "assertions",
    "traceability",
    "validation",
    "git",
    "config",
    "commands",
    "health",
]


def find_docs_dir() -> Path | None:
    """Locate the docs/cli directory.

    Checks two locations:
    1. Package location: <package>/docs/cli (installed via wheel)
    2. Repository location: <repo>/docs/cli (development mode)

    Returns:
        Path to docs/cli directory, or None if not found.
    """
    # Try package location first (installed wheel)
    package_dir = Path(__file__).parent.parent  # src/elspais
    package_docs = package_dir / "docs" / "cli"
    if package_docs.is_dir():
        return package_docs

    # Try repository root (development mode)
    # Walk up from utilities/ to find docs/cli
    repo_root = package_dir.parent.parent  # src/../..
    repo_docs = repo_root / "docs" / "cli"
    if repo_docs.is_dir():
        return repo_docs

    return None


def load_topic(topic: str) -> str | None:
    """Load a single documentation topic.

    Args:
        topic: Topic name (e.g., 'quickstart', 'format').

    Returns:
        Markdown content, or None if topic not found.
    """
    docs_dir = find_docs_dir()
    if docs_dir is None:
        return None

    topic_file = docs_dir / f"{topic}.md"
    if not topic_file.is_file():
        return None

    return topic_file.read_text(encoding="utf-8")


def load_all_topics() -> str:
    """Load and concatenate all documentation topics.

    Returns topics in the defined order, separated by blank lines.

    Returns:
        Combined markdown content from all topics.
    """
    docs_dir = find_docs_dir()
    if docs_dir is None:
        return ""

    parts: list[str] = []
    for topic in TOPIC_ORDER:
        content = load_topic(topic)
        if content:
            parts.append(content)

    return "\n\n".join(parts)


def get_available_topics() -> list[str]:
    """Get list of available documentation topics.

    Returns:
        List of topic names that have corresponding files.
    """
    docs_dir = find_docs_dir()
    if docs_dir is None:
        return []

    available = []
    for topic in TOPIC_ORDER:
        topic_file = docs_dir / f"{topic}.md"
        if topic_file.is_file():
            available.append(topic)

    return available
