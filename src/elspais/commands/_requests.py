# Implements: REQ-d00282-A+E, REQ-d00280-D
"""What a report operation is asked for, as final values.

A request is what reaches a ``compute_*`` function. It holds values that have
already been derived -- a scope expanded, a selection resolved, a repeated flag
flattened -- so the operation states a report rather than deciding what was
asked for. Deriving happens once, at whichever edge was invoked; nothing here
reads a config, an ``argparse.Namespace`` or a query string.

``values`` is ``None`` where nothing was named, which is NOT the same as the
default set: an unstamped payload is the default report (REQ-d00282-E).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from elspais.graph.scope import ReportScope


@dataclass(frozen=True)
class ReportInputs:
    """The two axes every report over a set of requirements reads."""

    scope: ReportScope | None = None
    values: tuple[str, ...] | None = None

    def to_params(self) -> dict[str, str]:
        """Serialize for a serving process. The mirror of ``report_inputs_from_params``."""
        from elspais.commands._scope import scope_to_params
        from elspais.commands._values import VALUES_PARAM
        from elspais.graph.values import VALUE_LIST_SEPARATOR

        params = dict(scope_to_params(self.scope))
        if self.values is not None:
            params[VALUES_PARAM] = VALUE_LIST_SEPARATOR.join(self.values)
        return params


@dataclass(frozen=True)
class SummaryRequest(ReportInputs):
    """Coverage rolled up by level."""


@dataclass(frozen=True)
class TraceRequest(ReportInputs):
    """Facts about each requirement."""


@dataclass(frozen=True)
class GapsRequest(ReportInputs):
    """Requirements one dimension has not credited.

    ``command`` names which shorthand is being produced, so a section asked for
    alone and the same section composed with others offer the same values
    (REQ-d00279-C).
    """

    command: str = "gaps"
    treat_active: tuple[str, ...] = ()

    def to_params(self) -> dict[str, str]:
        """Every field, not only the inherited two: a field left out of this
        map is a field a daemon-served report is computed without."""
        params = super().to_params()
        params["command"] = self.command
        if self.treat_active:
            params["treat_active"] = ",".join(self.treat_active)
        return params


@dataclass(frozen=True)
class AnalysisRequest(ReportInputs):
    """Requirements ranked by foundational importance."""

    top: int = 10
    include_code: bool = False
    weights: str | None = None

    def to_params(self) -> dict[str, str]:
        params = super().to_params()
        params["top"] = str(self.top)
        if self.include_code:
            params["include_code"] = "true"
        if self.weights:
            params["weights"] = self.weights
        return params


@dataclass(frozen=True)
class ChecksRequest:
    """Health findings about the project.

    Reads no scope and no value selection: it reports findings rather than facts
    about each requirement (REQ-d00282-F).
    """

    spec_only: bool = False
    code_only: bool = False
    tests_only: bool = False
    terms_only: bool = False
    lenient: bool = False
    treat_active: tuple[str, ...] = ()

    @property
    def run_all(self) -> bool:
        return not any([self.spec_only, self.code_only, self.tests_only, self.terms_only])

    def to_params(self) -> dict[str, str]:
        params = {
            name: "true"
            for name in ("spec_only", "code_only", "tests_only", "terms_only", "lenient")
            if getattr(self, name)
        }
        if self.treat_active:
            params["treat_active"] = ",".join(self.treat_active)
        return params


@dataclass(frozen=True)
class SearchRequest:
    """A multi-term query over the graph."""

    q: str = ""
    field: str = "all"
    limit: int = 50
    regex: bool = False

    def to_params(self) -> dict[str, str]:
        params = {"q": self.q, "limit": str(self.limit)}
        if self.field:
            params["field"] = self.field
        if self.regex:
            params["regex"] = "true"
        return params
