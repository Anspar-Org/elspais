# Implements: REQ-d00333-C
"""The ``command`` dependency source: a project's own program states the evidence.

The command runs in the repository root. It receives the repo-relative path
of each unit on its standard input, one per line, and prints a JSON array:

    [{"unit": "<repo-relative test file>", "files": ["<path>", ...]}, ...]

A path in ``files`` may be repo-relative or absolute. A path inside the
repository, through symbolic links or not, is made repo-relative; any other
path is kept as written, so it lies outside the target's inputs and counts as
changed. A unit the output omits has no recorded evidence, so it executes.

The project declares what the command observes (``units.observes``), because
only the project knows what its program looks at.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from pydantic import BaseModel, field_validator

from elspais.graph.dependencies import (
    Evidence,
    Observation,
    ObservesFrame,
    SourceFailed,
    SourceRequest,
)


class CommandSettings(BaseModel):
    """The settings of the ``command`` source."""

    model_config = {"extra": "forbid"}

    command: str

    @field_validator("command")
    @classmethod
    def _present(cls, v: str) -> str:
        if not v.strip():
            raise ValueError(
                'the command source needs a command: dependencies = { source = "command", '
                'command = "tools/test-deps" }'
            )
        return v


def _repo_relative(path: str, root: Path) -> str:
    from elspais.graph.parsers.results.placement import placed_in_repo

    placed = placed_in_repo(path, root, root)
    return placed if placed is not None else path


class CommandSource:
    name: ClassVar[str] = "command"
    settings_model: ClassVar[type[BaseModel]] = CommandSettings
    extra: ClassVar[str | None] = None

    def default_observes(self, frame: ObservesFrame) -> Observation | None:
        """None: the project declares what its command observes."""
        return None

    def evidence(self, request: SourceRequest) -> Evidence:
        """Run the command over the units and read the files each one reaches."""
        from elspais.utilities.commands import CommandFailed, run_json_command

        settings: Any = request.settings
        root = Path(request.repo_root).resolve()
        try:
            answer = run_json_command(settings.command, request.units, root)
        except CommandFailed as exc:
            raise SourceFailed(f"the dependency command {settings.command!r} {exc}") from exc
        if not isinstance(answer, list):
            raise SourceFailed(
                f"the dependency command {settings.command!r} printed JSON that is not an array"
            )
        wanted = set(request.units)
        files: dict[str, frozenset[str]] = {}
        for index, entry in enumerate(answer):
            unit = entry.get("unit") if isinstance(entry, dict) else None
            reached = entry.get("files") if isinstance(entry, dict) else None
            if (
                not isinstance(unit, str)
                or not isinstance(reached, list)
                or not all(isinstance(p, str) for p in reached)
            ):
                raise SourceFailed(
                    f"the dependency command {settings.command!r} printed entry {index} "
                    f'that is not {{"unit": "<path>", "files": ["<path>", ...]}}'
                )
            unit = _repo_relative(unit, root)
            if unit not in wanted:
                continue
            files[unit] = files.get(unit, frozenset()) | frozenset(
                _repo_relative(p, root) for p in reached
            )
        return Evidence(files=files)
