"""DomainDeserializer - Abstract controller for text domain deserialization.

This module provides the infrastructure for deserializing text from
various sources (files, stdin, CLI args) into parsed content.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Protocol, runtime_checkable

from elspais.graph.parsers import ParseContext, ParsedContent, ParserRegistry


@dataclass
class DomainContext:
    """Context for a source being deserialized.

    Attributes:
        source_type: Type of source ("file", "stdin", "cli").
        source_id: Identifier for the source (file path, etc.).
        metadata: Additional metadata about the source.
    """

    source_type: str
    source_id: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedContentWithContext(ParsedContent):
    """ParsedContent with source context attached.

    Extends ParsedContent to include the DomainContext from which
    the content was parsed.
    """

    source_context: DomainContext | None = None


@runtime_checkable
class DomainDeserializer(Protocol):
    """Protocol for domain deserializers.

    Deserializers iterate over sources and use parsers to extract
    structured content.
    """

    def iterate_sources(self) -> Iterator[tuple[DomainContext, str]]:
        """Iterate over sources, yielding context and content.

        Yields:
            Tuples of (DomainContext, content_string).
        """
        ...

    def deserialize(
        self, registry: ParserRegistry
    ) -> Iterator[ParsedContentWithContext]:
        """Deserialize all sources using the parser registry.

        Args:
            registry: ParserRegistry with registered parsers.

        Yields:
            ParsedContentWithContext for each parsed region.
        """
        ...


class DomainFile:
    """Deserializer for files and directories.

    Can deserialize:
    - A single file
    - All matching files in a directory
    """

    def __init__(
        self,
        path: Path | str,
        patterns: list[str] | None = None,
        recursive: bool = False,
        skip_dirs: list[str] | None = None,
        skip_files: list[str] | None = None,
    ) -> None:
        """Initialize file deserializer.

        Args:
            path: Path to file or directory.
            patterns: Glob patterns for directory (default: ["*.md"]).
            recursive: Whether to search recursively.
            skip_dirs: Directory names to skip (e.g., ["roadmap", "reference"]).
            skip_files: File names to skip (e.g., ["README.md", "INDEX.md"]).
        """
        self.path = Path(path)
        self.patterns = patterns or ["*.md"]
        self.recursive = recursive
        self.skip_dirs = skip_dirs or []
        self.skip_files = skip_files or []

    def _should_skip(self, file_path: Path) -> bool:
        """Check if a file should be skipped based on skip_dirs and skip_files.

        Args:
            file_path: Path to check.

        Returns:
            True if the file should be skipped.
        """
        # Check if file name matches skip_files
        if file_path.name in self.skip_files:
            return True

        # Check if any parent directory matches skip_dirs
        # Get path relative to base to check directory names
        try:
            rel_path = file_path.relative_to(self.path)
            # Check each part of the relative path (excluding the file name)
            for part in rel_path.parts[:-1]:
                if part in self.skip_dirs:
                    return True
        except ValueError:
            # file_path is not relative to self.path, check absolute path parts
            for part in file_path.parts:
                if part in self.skip_dirs:
                    return True

        return False

    def iterate_sources(self) -> Iterator[tuple[DomainContext, str]]:
        """Iterate over file sources.

        Yields:
            Tuples of (DomainContext, file_content).
        """
        if self.path.is_file():
            if not self._should_skip(self.path):
                yield self._read_file(self.path)
        elif self.path.is_dir():
            for pattern in self.patterns:
                if self.recursive:
                    file_iter = self.path.rglob(pattern)
                else:
                    file_iter = self.path.glob(pattern)

                for file_path in sorted(file_iter):
                    if file_path.is_file() and not self._should_skip(file_path):
                        yield self._read_file(file_path)

    def _read_file(self, file_path: Path) -> tuple[DomainContext, str]:
        """Read a file and create context.

        Args:
            file_path: Path to file.

        Returns:
            Tuple of (DomainContext, content).
        """
        content = file_path.read_text(encoding="utf-8")
        ctx = DomainContext(
            source_type="file",
            source_id=str(file_path),
            metadata={"path": file_path},
        )
        return ctx, content

    def deserialize(
        self, registry: ParserRegistry
    ) -> Iterator[ParsedContentWithContext]:
        """Deserialize files using parser registry.

        Args:
            registry: ParserRegistry with registered parsers.

        Yields:
            ParsedContentWithContext for each parsed region.
        """
        for ctx, content in self.iterate_sources():
            # Convert content to lines
            lines = [(i + 1, line) for i, line in enumerate(content.split("\n"))]

            # Create parse context
            parse_ctx = ParseContext(
                file_path=ctx.source_id,
                config=ctx.metadata,
            )

            # Parse and yield with context
            for parsed in registry.parse_all(lines, parse_ctx):
                yield ParsedContentWithContext(
                    content_type=parsed.content_type,
                    start_line=parsed.start_line,
                    end_line=parsed.end_line,
                    raw_text=parsed.raw_text,
                    parsed_data=parsed.parsed_data,
                    source_context=ctx,
                )


class DomainStdio:
    """Deserializer for stdin content."""

    def __init__(self, content: str, source_id: str = "<stdin>") -> None:
        """Initialize stdin deserializer.

        Args:
            content: Content read from stdin.
            source_id: Identifier for the source.
        """
        self.content = content
        self.source_id = source_id

    def iterate_sources(self) -> Iterator[tuple[DomainContext, str]]:
        """Yield the stdin content.

        Yields:
            Single tuple of (DomainContext, content).
        """
        ctx = DomainContext(
            source_type="stdin",
            source_id=self.source_id,
        )
        yield ctx, self.content

    def deserialize(
        self, registry: ParserRegistry
    ) -> Iterator[ParsedContentWithContext]:
        """Deserialize stdin using parser registry.

        Args:
            registry: ParserRegistry with registered parsers.

        Yields:
            ParsedContentWithContext for each parsed region.
        """
        for ctx, content in self.iterate_sources():
            lines = [(i + 1, line) for i, line in enumerate(content.split("\n"))]

            parse_ctx = ParseContext(
                file_path=ctx.source_id,
                config={},
            )

            for parsed in registry.parse_all(lines, parse_ctx):
                yield ParsedContentWithContext(
                    content_type=parsed.content_type,
                    start_line=parsed.start_line,
                    end_line=parsed.end_line,
                    raw_text=parsed.raw_text,
                    parsed_data=parsed.parsed_data,
                    source_context=ctx,
                )
