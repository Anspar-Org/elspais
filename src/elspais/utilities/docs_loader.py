# Implements: REQ-d00254-C
"""Documentation loader for CLI docs command.

Loads the markdown topics shipped inside the package, which are the same
files whether elspais is installed from a wheel or checked out.
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
    "authoring",
    "traceability",
    "linking",
    "satisfies",
    "validation",
    "git",
    "config",
    "commands",
    "checks",
    "pdf",
    "test-targets",
    "doctor",
    "analysis",
    "terms",
    "associate",
    "ignore",
    "graph-model",
    "mcp",
    "concurrency",
]


def find_docs_dir() -> Path | None:
    """Locate the shipped CLI documentation directory.

    The topics live inside the package, so the same files answer `elspais
    docs` from a wheel and from an editable checkout. There is no second
    copy at the repository root to fall back to.

    Returns:
        Path to the docs directory, or None if not found.
    """
    package_docs = Path(__file__).parent.parent / "docs" / "cli"
    return package_docs if package_docs.is_dir() else None


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


def list_topics() -> str:
    """Build a topic index with descriptions from each file's first heading.

    Returns:
        Formatted topic listing as plain text.
    """
    docs_dir = find_docs_dir()
    if docs_dir is None:
        return "Documentation files not found."

    lines: list[str] = ["# Available Topics", "", "Usage: elspais docs <topic>", ""]
    max_name = max(len(t) for t in TOPIC_ORDER)
    for topic in TOPIC_ORDER:
        topic_file = docs_dir / f"{topic}.md"
        if not topic_file.is_file():
            continue
        # Extract description from first markdown heading
        desc = ""
        for line in topic_file.read_text(encoding="utf-8").splitlines():
            stripped = line.strip().lstrip("#").strip()
            if stripped:
                desc = stripped
                break
        lines.append(f"  {topic:<{max_name}}  {desc}")

    lines.append("")
    lines.append(f"  {'all':<{max_name}}  Display all topics")
    lines.append(f"  {'topics':<{max_name}}  This listing")
    return "\n".join(lines)


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
