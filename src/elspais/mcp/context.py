"""
elspais.mcp.context - Workspace context for MCP server.

Manages workspace state including configuration, requirements cache,
and content rules.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from elspais.config.loader import find_config_file, get_spec_directories, load_config
from elspais.core.content_rules import load_content_rules
from elspais.core.models import ContentRule, Requirement
from elspais.core.parser import RequirementParser
from elspais.core.patterns import PatternConfig


@dataclass
class WorkspaceContext:
    """
    Manages workspace state for MCP server operations.

    Provides caching of parsed requirements and access to configuration,
    content rules, and other workspace resources.
    """

    working_dir: Path
    config: Dict[str, Any] = field(default_factory=dict)
    _requirements_cache: Optional[Dict[str, Requirement]] = field(default=None, repr=False)
    _parser: Optional[RequirementParser] = field(default=None, repr=False)

    @classmethod
    def from_directory(cls, directory: Path) -> "WorkspaceContext":
        """
        Initialize context from a working directory.

        Loads configuration from .elspais.toml if found.

        Args:
            directory: Working directory path

        Returns:
            Initialized WorkspaceContext
        """
        directory = directory.resolve()
        config_path = find_config_file(directory)

        if config_path:
            config = load_config(config_path)
        else:
            # Use defaults
            from elspais.config.defaults import DEFAULT_CONFIG
            config = DEFAULT_CONFIG.copy()

        return cls(working_dir=directory, config=config)

    def get_requirements(self, force_refresh: bool = False) -> Dict[str, Requirement]:
        """
        Get all parsed requirements, with caching.

        Args:
            force_refresh: If True, ignore cache and re-parse

        Returns:
            Dict mapping requirement IDs to Requirement objects
        """
        if self._requirements_cache is None or force_refresh:
            self._requirements_cache = self._parse_requirements()
        return self._requirements_cache

    def get_requirement(self, req_id: str) -> Optional[Requirement]:
        """
        Get a single requirement by ID.

        Args:
            req_id: Requirement ID (e.g., "REQ-p00001")

        Returns:
            Requirement if found, None otherwise
        """
        requirements = self.get_requirements()
        return requirements.get(req_id)

    def get_content_rules(self) -> List[ContentRule]:
        """
        Get all configured content rules.

        Returns:
            List of ContentRule objects
        """
        return load_content_rules(self.config, self.working_dir)

    def search_requirements(
        self,
        query: str,
        field: str = "all",
        regex: bool = False,
    ) -> List[Requirement]:
        """
        Search requirements by pattern.

        Args:
            query: Search query string
            field: Field to search - "all", "id", "title", "body", "assertions"
            regex: If True, treat query as regex pattern

        Returns:
            List of matching requirements
        """
        requirements = self.get_requirements()
        results = []

        if regex:
            pattern = re.compile(query, re.IGNORECASE)
        else:
            pattern = re.compile(re.escape(query), re.IGNORECASE)

        for req in requirements.values():
            if self._matches(req, pattern, field):
                results.append(req)

        return results

    def invalidate_cache(self) -> None:
        """Clear cached requirements (call after edits)."""
        self._requirements_cache = None

    def _parse_requirements(self) -> Dict[str, Requirement]:
        """Parse requirements from spec directories."""
        if self._parser is None:
            pattern_config = PatternConfig.from_dict(self.config.get("patterns", {}))
            self._parser = RequirementParser(pattern_config)

        spec_dirs = get_spec_directories(None, self.config, self.working_dir)
        skip_files = self.config.get("spec", {}).get("skip_files", [])

        all_requirements: Dict[str, Requirement] = {}

        for spec_dir in spec_dirs:
            if spec_dir.exists():
                requirements = self._parser.parse_directory(spec_dir, skip_files=skip_files)
                all_requirements.update(requirements)

        return all_requirements

    def _matches(self, req: Requirement, pattern: re.Pattern, field: str) -> bool:
        """Check if requirement matches search pattern."""
        if field == "id":
            return bool(pattern.search(req.id))
        elif field == "title":
            return bool(pattern.search(req.title))
        elif field == "body":
            return bool(pattern.search(req.body))
        elif field == "assertions":
            for assertion in req.assertions:
                if pattern.search(assertion.text):
                    return True
            return False
        else:  # "all"
            if pattern.search(req.id):
                return True
            if pattern.search(req.title):
                return True
            if pattern.search(req.body):
                return True
            for assertion in req.assertions:
                if pattern.search(assertion.text):
                    return True
            return False
