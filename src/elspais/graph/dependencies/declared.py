# Implements: REQ-d00333-C
"""The ``declared`` dependency source: each test file reaches itself alone.

Choosing it is the project's statement that no test file depends on another
test file. The source observes the test files the target scans, so a change
to one of them executes that file alone, and a change to any other input is
unobserved, which executes every test file of the target.

It reads nothing and runs nothing, so it serves a target in any language.
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel

from elspais.graph.dependencies import (
    Evidence,
    NoSettings,
    Observation,
    ObservesFrame,
    SourceRequest,
)


class DeclaredSource:
    name: ClassVar[str] = "declared"
    settings_model: ClassVar[type[BaseModel]] = NoSettings
    extra: ClassVar[str | None] = None

    def default_observes(self, frame: ObservesFrame) -> Observation | None:
        """The test files the test scanning kind selects."""
        return frame.test

    def evidence(self, request: SourceRequest) -> Evidence:
        """Each unit reaches its own file."""
        return Evidence(files={unit: frozenset({unit}) for unit in request.units})
