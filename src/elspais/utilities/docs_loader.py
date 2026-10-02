# Implements: REQ-d00254-C
"""Documentation loader for CLI docs command.

Loads the markdown topics shipped inside the package, which are the same
files whether elspais is installed from a wheel or checked out.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, get_args

# Implements: REQ-d00286-A+C
# The one declaration of what the tool documents. It is a Literal because the
# CLI positional it types has to be checked statically; every runtime list of
# topics is derived from it, so there is nothing to keep in step by hand. The
# declaration order is the reading order used by `docs topics` and `docs all`.
#
# `topics` and `all` are not subjects — they are the two ways of asking for
# the index and for everything, and they carry no file. PSEUDO_TOPICS names
# them so the derivation below can subtract them.
DOCS_TOPICS = Literal[
    "quickstart",
    "format",
    "hierarchy",
    "assertions",
    "authoring",
    "traceability",
    "scoping",
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
    "comments",
    "topics",
    "all",
]

PSEUDO_TOPICS = ("topics", "all")

# Implements: REQ-d00286-C
# Ordered list of documentation topics, each backed by `<topic>.md`.
TOPIC_ORDER = [t for t in get_args(DOCS_TOPICS) if t not in PSEUDO_TOPICS]


# Implements: REQ-d00286-A+D
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


# Implements: REQ-d00286-G
def load_topic(topic: str) -> str | None:
    """Load a single documentation topic.

    Only a declared topic is served. A name outside `TOPIC_ORDER` loads
    nothing, so no surface can reach a file the declaration does not name.

    Args:
        topic: Topic name (e.g., 'quickstart', 'format').

    Returns:
        Markdown content, or None if the name is not a declared topic or its
        file is missing.
    """
    if topic not in TOPIC_ORDER:
        return None
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


# The two pseudo-topics, as the topic index describes them.
PSEUDO_TOPIC_DESCRIPTIONS = {
    "all": "Display all topics",
    "topics": "This listing",
}


def topic_description(topic: str) -> str:
    """The one-line description of a topic: its file's first heading.

    Returns:
        The heading text, or the empty string if the topic has no file.
    """
    if topic in PSEUDO_TOPIC_DESCRIPTIONS:
        return PSEUDO_TOPIC_DESCRIPTIONS[topic]
    content = load_topic(topic)
    if content is None:
        return ""
    for line in content.splitlines():
        stripped = line.strip().lstrip("#").strip()
        if stripped:
            return stripped
    return ""


# Implements: REQ-d00286-E+G
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
    for topic in get_available_topics():
        lines.append(f"  {topic:<{max_name}}  {topic_description(topic)}")

    lines.append("")
    for pseudo in ("all", "topics"):
        lines.append(f"  {pseudo:<{max_name}}  {topic_description(pseudo)}")
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
