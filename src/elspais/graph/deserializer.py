# Implements: REQ-o00072-C
"""DomainDeserializer - Abstract controller for text domain deserialization.

This module provides the infrastructure for deserializing text from
various sources (files, stdin, CLI args) into parsed content.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from elspais.graph.file_selection import (
    file_is_skipped,
    select_files,
    within_skipped_dir,
)
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


# Implements: REQ-d00285-A, REQ-p00019-E
class SourceReadError(OSError):
    """A scanned file could not be read, named together with the cause.

    The underlying errors say what went wrong and, for a decoding failure,
    say nothing about where. A build scans thousands of files, so a message
    without the path leaves the reader to find it themselves -- a search the
    tool has already done.
    """

    def __init__(self, path: Path, cause: BaseException) -> None:
        self.path = path
        self.cause = cause
        super().__init__(f"cannot read {path}: {cause}")


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
        repo_root: Path | str | None = None,
    ) -> None:
        """Initialize file deserializer.

        Args:
            path: Path to file or directory.
            patterns: Glob patterns selecting among the files under *path*
                (default: ["*.md"]).
            recursive: Whether to search recursively.
            skip_dirs: Directories not to enter, named by their path from
                *repo_root* (e.g. ["spec/_generated", "**/node_modules"]).
                A bare name is a path: "junk" names ``junk`` at the repository
                root, NOT a directory called junk at some depth -- write
                "**/junk" for that.
            skip_files: Globs over a file's NAME (e.g. ["README.md", "*.pyc"]).
                A file pattern says nothing about where a file sits; the
                directory rules say that. The two lists are not
                interchangeable and are deliberately not spelled alike.
            repo_root: The repository every directory pattern is read from.
                Defaults to *path*, which is what a caller scanning one
                directory in isolation means.
        """
        self.path = Path(path)
        self.patterns = patterns or ["*.md"]
        self.recursive = recursive
        self.skip_dirs = skip_dirs or []
        self.skip_files = skip_files or []
        self.repo_root = Path(repo_root) if repo_root is not None else self.path
        self._walked: list[tuple[Path, bool]] | None = None

    # Implements: REQ-d00212-Q+W, REQ-p00015-H, REQ-d00241-F+G
    def _walk(self) -> list[tuple[Path, bool]]:
        """Every file this walk reached, paired with whether it is selected.

        ONE mechanism decides it: :func:`select_files`. A file a skip pattern
        names appears here NOT AT ALL -- not as selected and not as declined --
        so nothing downstream can report it (REQ-d00241-G). A file the walk
        reached but the patterns did not select appears as ``False``, which is
        what lets a *Traceability* keyword in it be reported (REQ-d00241-F).

        Cached, because the two callers ask about the same walk.
        """
        if self._walked is not None:
            return self._walked

        found: list[tuple[Path, bool]] = []
        root, relative = self._frame()
        if self.path.is_file():
            # A caller who names one file has already made the selection;
            # patterns are for choosing among the files in a directory. The
            # skip lists still answer, so naming a skipped file reads nothing.
            if not file_is_skipped(self.path.name, self.skip_files) and not within_skipped_dir(
                relative, self.skip_dirs
            ):
                found.append((self.path, True))
        elif self.path.is_dir():
            selection = select_files(
                repo_root=root,
                scan_dirs=[relative],
                skip_dirs=self.skip_dirs,
                skip_files=self.skip_files,
                include_files=self.patterns,
                recursive=self.recursive,
            )
            found = [(p, True) for p in sorted(selection.selected)]
            found += [(p, False) for p in sorted(selection.declined)]
            found.sort(key=lambda pair: pair[0])

        self._walked = found
        return found

    def _frame(self) -> tuple[Path, str]:
        """The root the directory patterns are read from, and this path under it.

        Normally the declared repository root, with the scanned path named
        relative to it. Where the scanned path is NOT under that root, the root
        is no frame for it and the path itself becomes the frame.

        Falling back to the path's NAME instead was a wrong answer rather than
        a degraded one: the name was resolved against the declared root, so a
        caller asking for one repository's ``spec`` directory was handed a
        same-named directory in another repository entirely.
        """
        root = Path(self.repo_root)
        try:
            return root, self.path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            return self.path, "."

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

    # Implements: REQ-d00285-A, REQ-p00019-E
    def _read_file(self, file_path: Path) -> tuple[DomainContext, str]:
        """Read a file and create context.

        A file that cannot be read is not passed over: the requirements,
        annotations or results in it would go missing from a build that
        otherwise reports success, and a requirement missing from the graph
        is a requirement no report can mention. The read fails, naming the
        file and what went wrong with it.

        Args:
            file_path: Path to file.

        Returns:
            Tuple of (DomainContext, content).

        Raises:
            SourceReadError: The file could not be read or decoded.
        """
        try:
            content = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise SourceReadError(file_path, exc) from exc
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

    # Implements: REQ-o00072-A
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
