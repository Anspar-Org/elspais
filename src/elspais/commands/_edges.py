# Implements: REQ-d00282-E, REQ-d00280-D
"""The two places a report's inputs are derived.

There are exactly two, because there are exactly two things an invocation can
arrive as: what a reader typed, and what a serving process was handed. They
differ in one respect only -- the first has seen the project's config and can
expand a declared name, the second has not and must not try.

Derivation is the SAME operation at both edges: ``resolve_values`` passes over
what a declaration names and this report does not offer, and refuses what a
reader wrote. On an already-resolved list it validates and changes nothing, so
the params edge judges a finished selection only against its own offer.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from elspais.commands._requests import ReportInputs


# Implements: REQ-d00280-D
def report_inputs_from_args(
    args: Any,
    config: Mapping[str, Any] | None,
    offered: Sequence[str],
    identity_key: str = "id",
) -> ReportInputs:
    """Derive from what a reader typed. The ONLY edge that reads config."""
    from elspais.commands._scope import flag_values, scope_from_args
    from elspais.commands._values import values_from_args
    from elspais.graph.values import resolve_values

    selection = values_from_args(args, config)
    return ReportInputs(
        scope=scope_from_args(args, config),
        values=None if selection is None else resolve_values(selection, offered, identity_key),
        treat_active=flag_values(args, "treat_active"),
    )


# Implements: REQ-d00282-E
def report_inputs_from_params(
    params: Mapping[str, str],
    offered: Sequence[str],
    identity_key: str = "id",
) -> ReportInputs:
    """Derive from what a serving process was handed.

    No config: a declaration was expanded by the edge that had one, so what
    arrives here is a finished list. Judging it again is validation, and a name
    this report does not offer is a caller's mistake (REQ-d00282-F).
    """
    from elspais.commands._requests import treat_active_from_params
    from elspais.commands._scope import scope_from_params
    from elspais.commands._values import values_from_params
    from elspais.graph.values import resolve_values

    selection = values_from_params(params)
    return ReportInputs(
        scope=scope_from_params(params),
        values=None if selection is None else resolve_values(selection, offered, identity_key),
        treat_active=treat_active_from_params(params),
    )
