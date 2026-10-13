# Implements: REQ-d00333-C
"""Sources of *Dependency Evidence*: the one interface every language plugs into.

A test target that declares units names a dependency source. For each unit
(a test file the target scans), the source states which files of the
repository that unit reaches. The retention judgement in
:mod:`elspais.utilities.retention` reads that evidence and decides which
units a run executes. It never asks how the evidence was found, so a source
for one language and a source for another serve the judgement alike.

A source is a class registered here by name. It declares:

- ``name``: the name a project writes in ``dependencies = { source = NAME }``;
- ``settings_model``: a pydantic model that validates the keys a project
  writes beside ``source``;
- ``extra``: the pip extra holding the optional libraries the source needs,
  or ``None`` where it needs none;
- ``default_observes(frame)``: the files the source observes where the
  project declares none, or ``None`` where the project must declare them;
- ``evidence(request)``: the files each unit reaches on the current tree.

A source module imports its optional libraries inside ``evidence()`` alone,
so validating a configuration that names it never needs them. A source asked
through :func:`gather_evidence` lets a missing library's ``ImportError``
propagate, and is reported as :class:`SourceUnavailable` naming the extra it
declares. Every other reason a source cannot answer raises
:class:`SourceFailed`. Either one makes every unit of the target execute.

A unit that the evidence omits has no recorded evidence. The retention
judgement executes such a unit, whatever the source, because what a source
cannot see counts as a dependency. A source that knows why it holds no
evidence for a unit says so in ``Evidence.no_evidence``, and the run states
it, so a project can see what would end the re-execution. A source prefers
leaving out the units an uncertainty reaches to raising
:class:`SourceFailed`, where the uncertainty reaches only some of them.

This package reads no configuration. A caller hands a source what it needs.
"""

from __future__ import annotations

import importlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, Protocol

from pydantic import BaseModel


@dataclass(frozen=True)
class Observation:
    """A selection of files in the vocabulary of a scanning kind, read from the repository root."""

    directories: tuple[str, ...] = ()
    file_patterns: tuple[str, ...] = ()
    skip_dirs: tuple[str, ...] = ()
    skip_files: tuple[str, ...] = ()


@dataclass(frozen=True)
class ObservesFrame:
    """What a source's default observation may be derived from.

    ``cwd`` is the target's working directory, repo-relative (``""`` for the
    root). ``inputs`` is the target's declared input selection. ``test`` is the
    selection the test scanning kind reads by.
    """

    cwd: str
    inputs: Observation
    test: Observation


@dataclass(frozen=True)
class SourceRequest:
    """What a source is asked about: one target's units on the current tree.

    ``units`` are repo-relative test files. ``inputs`` are the target's file
    inputs, repo-relative. ``observed`` are the inputs the source observes.
    ``settings`` is the source's own validated settings model.
    ``environment_probes`` names the target's environment probes whose change
    makes its results stale, so a source whose tests load something outside
    the repository can tell whether a change to it would be seen.
    """

    repo_root: Path
    cwd: Path
    target_name: str
    units: tuple[str, ...]
    inputs: frozenset[str]
    observed: frozenset[str]
    settings: BaseModel
    environment_probes: tuple[str, ...] = ()


# Implements: REQ-d00311-E, REQ-d00333-B+C
@dataclass(frozen=True)
class Evidence:
    """The files each unit reaches, repo-relative, and why a unit has none.

    A unit ``files`` omits has no recorded evidence, so it executes.
    ``no_evidence`` gives, for such a unit, the reason the source holds none,
    worded by its cause so that units sharing a cause share the words; the
    run states it. A path may lie outside the target's inputs; the judgement
    reports it and counts it as changed.
    """

    files: Mapping[str, frozenset[str]] = field(default_factory=dict)
    no_evidence: Mapping[str, str] = field(default_factory=dict)


class SourceFailed(Exception):
    """The source cannot give evidence for this target now. ``reason`` says why."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class SourceUnavailable(SourceFailed):
    """A library the source needs is not installed. ``extra`` names the pip extra."""

    def __init__(self, reason: str, extra: str) -> None:
        super().__init__(f"{reason}; install elspais[{extra}]")
        self.extra = extra


class NoSettings(BaseModel):
    """The settings model of a source that takes no settings."""

    model_config = {"extra": "forbid"}


class DependencySource(Protocol):
    """A source of *Dependency Evidence*."""

    name: ClassVar[str]
    settings_model: ClassVar[type[BaseModel]]
    extra: ClassVar[str | None]

    def default_observes(self, frame: ObservesFrame) -> Observation | None:
        """The files observed where the project declares none; ``None`` requires a declaration."""
        ...

    def evidence(self, request: SourceRequest) -> Evidence:
        """The files each unit reaches on the current tree. Raises :class:`SourceFailed`."""
        ...


#: Each registered source by name, as ``module:class``. A module is imported
#: only when its source is asked for.
_SOURCES: dict[str, str] = {
    "declared": "elspais.graph.dependencies.declared:DeclaredSource",
    "imports:dart": "elspais.graph.dependencies.dart_imports:DartImportsSource",
    "command": "elspais.graph.dependencies.command:CommandSource",
}


def source_names() -> tuple[str, ...]:
    """The names a project may write as ``source``, sorted."""
    return tuple(sorted(_SOURCES))


def get_source(name: str) -> DependencySource:
    """Return the source registered under *name*.

    Raises:
        KeyError: No source has that name. The message names every one.
    """
    where = _SOURCES.get(name)
    if where is None:
        known = ", ".join(repr(n) for n in source_names())
        raise KeyError(f"no dependency source named {name!r}; known sources: {known}")
    module_name, _, class_name = where.partition(":")
    cls: Any = getattr(importlib.import_module(module_name), class_name)
    return cls()


def observes_required(source: DependencySource) -> bool:
    """Whether *source* has no default observation, so a project must declare one.

    A source's default depends on the frame only through what it selects,
    never on whether it has one, so an empty frame answers.
    """
    empty = Observation()
    return source.default_observes(ObservesFrame(cwd="", inputs=empty, test=empty)) is None


def gather_evidence(source: DependencySource, request: SourceRequest) -> Evidence:
    """Ask *source* for the evidence of *request*'s units.

    Raises:
        SourceUnavailable: A library the source imports is missing; it names
            the extra the source declares.
        SourceFailed: The source cannot answer for any other reason.
    """
    try:
        return source.evidence(request)
    except ImportError as exc:
        if source.extra is None:
            raise SourceFailed(
                f"the {source.name!r} dependency source could not import {exc.name or exc}"
            ) from exc
        raise SourceUnavailable(
            f"the {source.name!r} dependency source needs {exc.name or 'a library'}", source.extra
        ) from exc


def validate_settings(name: str, settings: Mapping[str, Any]) -> BaseModel:
    """Validate *settings* with the settings model of the source *name*.

    Raises:
        KeyError: No source has that name.
        pydantic.ValidationError: The settings do not suit the source.
    """
    return get_source(name).settings_model.model_validate(dict(settings))


__all__ = [
    "DependencySource",
    "Evidence",
    "NoSettings",
    "Observation",
    "ObservesFrame",
    "SourceFailed",
    "SourceRequest",
    "SourceUnavailable",
    "gather_evidence",
    "get_source",
    "observes_required",
    "source_names",
    "validate_settings",
]
