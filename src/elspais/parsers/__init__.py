"""Parser plugin system for the traceability tree.

This module provides the SpecParser protocol and parser registry for
parsing different source types into TraceNode instances.

The parser system supports:
- Protocol-based interface for all parsers (built-in and custom)
- Registry for discovering and loading parsers
- File pattern matching for multi-format sources
- Custom parser loading via module paths
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Protocol, runtime_checkable

if TYPE_CHECKING:
    from elspais.core.tree import SourceLocation, TraceNode
    from elspais.core.tree_schema import NodeTypeSchema


@runtime_checkable
class SpecParser(Protocol):
    """Protocol for all parsers (built-in and custom).

    All parsers must implement this interface to be used with the
    traceability tree builder.
    """

    def parse(
        self,
        content: str,
        source: SourceLocation,
        schema: NodeTypeSchema,
    ) -> list[TraceNode]:
        """Parse content and return nodes.

        Args:
            content: File content to parse.
            source: Source location for the file.
            schema: Schema for this node type.

        Returns:
            List of parsed TraceNodes.
        """
        ...

    def can_parse(self, file_path: Path) -> bool:
        """Check if this parser can handle the given file.

        Args:
            file_path: Path to the file.

        Returns:
            True if this parser can handle the file.
        """
        ...


class ParserRegistry:
    """Registry for parser discovery and loading.

    The registry maintains a mapping of source types to parser instances,
    and provides methods for loading parsers dynamically.
    """

    def __init__(self) -> None:
        """Initialize empty registry."""
        self._parsers: dict[str, SpecParser] = {}
        self._factories: dict[str, Callable[[], SpecParser]] = {}

    def register(self, source: str, parser: SpecParser) -> None:
        """Register a parser instance for a source type.

        Args:
            source: Source type (e.g., "spec", "test_results").
            parser: Parser instance.
        """
        self._parsers[source] = parser

    def register_factory(self, source: str, factory: Callable[[], SpecParser]) -> None:
        """Register a factory function for lazy parser creation.

        Args:
            source: Source type.
            factory: Function that creates a parser instance.
        """
        self._factories[source] = factory

    def get(self, source: str) -> SpecParser | None:
        """Get parser for a source type.

        If a factory is registered but no instance exists, creates the instance.

        Args:
            source: Source type.

        Returns:
            Parser instance, or None if not found.
        """
        if source not in self._parsers and source in self._factories:
            self._parsers[source] = self._factories[source]()
        return self._parsers.get(source)

    def load_parser(self, module_path: str) -> SpecParser | None:
        """Load a parser from a module path.

        The module should have a `create_parser()` function that returns
        a SpecParser instance, or a `Parser` class that can be instantiated.

        Args:
            module_path: Dotted module path (e.g., "elspais.parsers.junit_xml").

        Returns:
            Parser instance, or None if loading fails.
        """
        try:
            module = importlib.import_module(module_path)

            # Try create_parser() function first
            if hasattr(module, "create_parser"):
                return module.create_parser()

            # Try Parser class
            if hasattr(module, "Parser"):
                return module.Parser()

            # Try the module's default parser
            if hasattr(module, "parser"):
                return module.parser

            return None

        except ImportError:
            return None

    def list_sources(self) -> list[str]:
        """List all registered source types.

        Returns:
            List of source type names.
        """
        sources = set(self._parsers.keys())
        sources.update(self._factories.keys())
        return sorted(sources)


# Global registry instance
_registry = ParserRegistry()


def get_registry() -> ParserRegistry:
    """Get the global parser registry.

    Returns:
        The global ParserRegistry instance.
    """
    return _registry


def register_builtin_parsers() -> None:
    """Register all built-in parsers with the global registry.

    This function is called automatically when needed, but can be
    called explicitly for eager initialization.
    """
    from elspais.parsers.code import CodeParser
    from elspais.parsers.journey import JourneyParser
    from elspais.parsers.junit_xml import JUnitXMLParser
    from elspais.parsers.pytest_json import PytestJSONParser
    from elspais.parsers.requirement import RequirementParser
    from elspais.parsers.test import TestParser

    registry = get_registry()

    # Register parsers for each source type
    registry.register("spec", RequirementParser())
    registry.register("journey", JourneyParser())
    registry.register("code", CodeParser())
    registry.register("test", TestParser())
    registry.register("junit_xml", JUnitXMLParser())
    registry.register("pytest_json", PytestJSONParser())


def get_parser(source: str) -> SpecParser | None:
    """Get a parser for the given source type.

    Initializes built-in parsers on first call.

    Args:
        source: Source type (e.g., "spec", "test").

    Returns:
        Parser instance, or None if not found.
    """
    registry = get_registry()

    # Initialize built-in parsers if registry is empty
    if not registry.list_sources():
        try:
            register_builtin_parsers()
        except ImportError:
            pass  # Some parsers may not be available

    return registry.get(source)
