# Implements: REQ-o00072-C
"""DomainDeserializer - Abstract controller for text domain deserialization.

This module provides the infrastructure for deserializing text from
various sources (files, stdin, CLI args) into parsed content.
"""

from __future__ import annotations

import fnmatch
import os
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

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

    def deserialize(self, registry: ParserRegistry) -> Iterator[ParsedContentWithContext]:
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
        ignore_config: Any = None,
        scope: str = "global",
    ) -> None:
        """Initialize file deserializer.

        Args:
            path: Path to file or directory.
            patterns: Glob patterns selecting among the files under *path*
                (default: ["*.md"]).
            recursive: Whether to search recursively.
            skip_dirs: Directory names to skip (e.g., ["roadmap", "reference"]).
            skip_files: File name patterns to skip (e.g., ["README.md", "*.pyc"]).
            ignore_config: The project's ``IgnoreConfig``, when the caller has
                one. It is the exclusion half of file selection and is asked
                about every directory and every file before anything is read.
            scope: Which scanning kind this walk is for ("spec", "code",
                "test", "global"), naming the scope *ignore_config* answers in.
        """
        self.path = Path(path)
        self.patterns = patterns or ["*.md"]
        self.recursive = recursive
        self.skip_dirs = skip_dirs or []
        self.skip_files = skip_files or []
        self.ignore_config = ignore_config
        self.scope = scope
        self._walked: list[tuple[Path, bool]] | None = None

    # Implements: REQ-d00212-Q+W
    def _matches_patterns(self, file_path: Path) -> bool:
        """Whether *file_path* is one of the files this kind's patterns select.

        A pattern is matched against the file's name and against its path
        relative to the scanned directory, so ``*.py`` selects at any depth and
        ``api/*.py`` selects within a subdirectory. This is the ONE meaning
        selection has, and it is the same for every scanning kind.
        """
        try:
            rel = file_path.relative_to(self.path).as_posix()
        except ValueError:
            rel = file_path.name
        name = file_path.name
        for pattern in self.patterns:
            if fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(rel, pattern):
                return True
        return False

    def _ignored(self, path: Path) -> bool:
        """Whether the ignore configuration excludes *path*."""
        if self.ignore_config is None:
            return False
        return bool(self.ignore_config.should_ignore(path, scope=self.scope))

    def _should_skip(self, file_path: Path) -> bool:
        """Check if a file should be skipped based on skip_dirs and skip_files.

        Args:
            file_path: Path to check.

        Returns:
            True if the file should be skipped.
        """
        # Check if file name matches skip_files. Matched as a glob, the way
        # every other exclusion pattern in the configuration is matched, so
        # `*.pyc` excludes what it plainly says it excludes.
        if any(fnmatch.fnmatch(file_path.name, pattern) for pattern in self.skip_files):
            return True

        # Check if any parent directory matches skip_dirs
        # Supports both single-segment ("roadmap") and multi-segment
        # ("regulations/fda") entries.
        try:
            rel_path = file_path.relative_to(self.path)
        except ValueError:
            rel_path = file_path

        # Parent directory path (excluding the file name)
        rel_dir = str(Path(*rel_path.parts[:-1])) if len(rel_path.parts) > 1 else ""
        for skip in self.skip_dirs:
            # Single-segment: match any component. Multi-segment: prefix match.
            if "/" in skip or "\\" in skip:
                if rel_dir == skip or rel_dir.startswith(skip + "/"):
                    return True
            else:
                if skip in rel_path.parts[:-1]:
                    return True

        return self._ignored(file_path)

    # Implements: REQ-d00212-Q+W, REQ-d00241-G
    def _walk(self) -> list[tuple[Path, bool]]:
        """Every file under *path* the scan did not exclude, paired with
        whether this kind's patterns select it.

        ONE traversal answers both halves of the question, and it answers them
        in one order: a file the ignore configuration excludes never appears
        here at all -- not as selected, and not as declined -- so nothing
        downstream can report it. Cached, because the two callers ask about
        the same walk.
        """
        if self._walked is not None:
            return self._walked

        found: list[tuple[Path, bool]] = []
        if self.path.is_file():
            # A caller who names one file has already made the selection;
            # patterns are for choosing among the files in a directory.
            if not self._should_skip(self.path):
                found.append((self.path, True))
        elif self.path.is_dir():
            files: list[Path] = []
            for dir_path, dir_names, file_names in os.walk(self.path):
                here = Path(dir_path)
                # Prune excluded directories in place: their contents are not
                # scanned, and are not read to be reported on either.
                dir_names[:] = sorted(d for d in dir_names if not self._should_skip_dir(here / d))
                files.extend(here / f for f in file_names)
                if not self.recursive:
                    dir_names[:] = []
            for file_path in sorted(files):
                if file_path.is_file() and not self._should_skip(file_path):
                    found.append((file_path, self._matches_patterns(file_path)))

        self._walked = found
        return found

    def _should_skip_dir(self, dir_path: Path) -> bool:
        """Whether a directory is excluded, and so not descended into."""
        try:
            rel_path = dir_path.relative_to(self.path)
        except ValueError:
            rel_path = dir_path
        rel = rel_path.as_posix()
        for skip in self.skip_dirs:
            if "/" in skip or "\\" in skip:
                if rel == skip or rel.startswith(skip + "/"):
                    return True
            elif dir_path.name == skip:
                return True
        return self._ignored(dir_path)

    # Implements: REQ-d00212-W
    def iter_selected(self) -> Iterator[Path]:
        """Every file under *path* this kind's patterns select."""
        for file_path, selected in self._walk():
            if selected:
                yield file_path

    # Implements: REQ-d00241-F
    def iter_declined(self) -> Iterator[Path]:
        """Every file the scan reached but the patterns did not select.

        These files are not read for content here -- the caller decides what,
        if anything, is worth asking about a file this kind declined.
        """
        for file_path, selected in self._walk():
            if not selected:
                yield file_path

    # Implements: REQ-o00072-A
    def iterate_sources(self) -> Iterator[tuple[DomainContext, str]]:
        """Iterate over file sources.

        Yields:
            Tuples of (DomainContext, file_content).
        """
        for file_path, selected in self._walk():
            if selected:
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

    # Implements: REQ-o00072-A+B
    def deserialize(self, registry: ParserRegistry) -> Iterator[ParsedContentWithContext]:
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

    def dispatch(
        self,
        dispatch_fn: Any,
        file_path_key: str = "path",
    ) -> Iterator[ParsedContentWithContext]:
        """Deserialize files using a Lark FileDispatcher method.

        Args:
            dispatch_fn: A callable(content, file_path) -> list[ParsedContent].
            file_path_key: Metadata key for source path (default: "path").

        Yields:
            ParsedContentWithContext for each parsed region.
        """
        for ctx, content in self.iterate_sources():
            source_path = ctx.metadata.get(file_path_key, ctx.source_id)
            for parsed in dispatch_fn(content, str(source_path)):
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

    # Implements: REQ-o00072-A
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

    # Implements: REQ-o00072-A+B
    def deserialize(self, registry: ParserRegistry) -> Iterator[ParsedContentWithContext]:
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
