# Verifies: REQ-d00280-D, REQ-d00282-E
"""The two derivation edges arrive at the same final values.

A declared name is the project's and passes over what a report does not offer;
a written selection is the reader's and is refused. Only the CLI edge can tell
them apart, because only it has seen the config. Once derived, both edges
produce the same tuple -- a difference here is a daemon-served report
disagreeing with a locally computed one.
"""

from __future__ import annotations

import argparse

import pytest

OFFERED = ("level", "requirements", "tested")


def test_a_declared_name_passes_over_what_this_report_does_not_offer():
    from elspais.commands._edges import report_inputs_from_args

    config = {"scopes": {"board": {"values": ["id", "requirements", "tested"]}}}
    args = argparse.Namespace(scope="board", values=None)
    inputs = report_inputs_from_args(args, config, OFFERED, identity_key="level")
    assert inputs.values == ("level", "requirements", "tested")


def test_a_written_selection_naming_an_unoffered_value_is_refused():
    from elspais.commands._edges import report_inputs_from_args
    from elspais.commands._values import UnofferedValues

    args = argparse.Namespace(scope=None, values="id,tested")
    with pytest.raises(UnofferedValues) as excinfo:
        report_inputs_from_args(args, None, OFFERED, identity_key="level")
    assert excinfo.value.unoffered == ("id",)


def test_the_params_edge_reaches_the_same_values_the_args_edge_did():
    """What travels is the selection as RESOLVED, so the serving process is
    handed a finished list and judges it only against its own offer."""
    from elspais.commands._edges import report_inputs_from_args, report_inputs_from_params

    config = {"scopes": {"board": {"values": ["id", "requirements", "tested"]}}}
    args = argparse.Namespace(scope="board", values=None)
    local = report_inputs_from_args(args, config, OFFERED, identity_key="level")
    served = report_inputs_from_params(local.to_params(), OFFERED, identity_key="level")
    assert served.values == local.values


@pytest.mark.parametrize(
    "request_factory",
    (
        lambda R: R.GapsRequest(values=("tested",), command="untested", treat_active=("draft",)),
        lambda R: R.AnalysisRequest(values=("id",), top=5, include_code=True, weights="pagerank"),
        lambda R: R.ChecksRequest(spec_only=True, treat_active=("draft",)),
        lambda R: R.SearchRequest(q="widget", field="title", limit=5, regex=True),
    ),
)
def test_no_field_is_lost_on_the_way_to_a_serving_process(request_factory):
    """A field left out of ``to_params`` is a field a daemon-served report is
    computed without, and the report still looks like the one asked for."""
    import dataclasses

    from elspais.commands import _requests

    request = request_factory(_requests)
    params = request.to_params()
    for field in dataclasses.fields(request):
        if field.name == "scope":
            continue
        value = getattr(request, field.name)
        if value in ((), None, False, ""):
            continue
        assert any(field.name == key for key in params), f"{field.name} never travels"


def test_nothing_named_stays_None_so_the_default_report_is_distinguishable():
    """An unstamped payload IS the default report; collapsing None into the
    default set would make a consumer unable to tell a reader who asked for
    everything from one who asked for nothing."""
    from elspais.commands._edges import report_inputs_from_args

    args = argparse.Namespace(scope=None, values=None)
    assert report_inputs_from_args(args, None, OFFERED, identity_key="level").values is None


# Verifies: REQ-d00282-E
@pytest.mark.parametrize(
    "request_factory",
    (
        lambda R: R.ReportInputs(values=()),
        lambda R: R.SummaryRequest(values=()),
        lambda R: R.TraceRequest(values=()),
        lambda R: R.GapsRequest(values=()),
        lambda R: R.AnalysisRequest(values=()),
    ),
)
def test_an_empty_but_not_None_selection_is_refused_at_construction(request_factory):
    """``values=()`` is indistinguishable from "nothing named" once it has
    round-tripped through ``to_params()`` -- a request built directly (the MCP
    path, which skips ``to_params``/``report_inputs_from_params`` entirely)
    must never carry one, or a consumer reading ``values or default`` widens
    silently to the default report instead of the empty one asked for."""
    from elspais.commands import _requests

    with pytest.raises(ValueError, match="empty tuple"):
        request_factory(_requests)


def test_engine_call_hands_compute_fn_the_request_object(monkeypatch):
    """``_engine.call`` reaches ``compute_fn`` with the request object itself,
    not a re-serialized dict -- the whole point of the request types is that a
    derived value survives the trip through the local path unchanged."""
    from elspais.commands import _engine
    from elspais.commands._requests import SummaryRequest

    # Force the local fallback path: no daemon.json to find.
    monkeypatch.setattr(_engine, "_try_daemon", lambda endpoint, params: None)
    monkeypatch.setattr(_engine, "_ensure_local_graph", lambda config_path=None: (object(), {}))

    request = SummaryRequest(values=("level",))
    received: list[object] = []

    def compute_fn(graph, config, received_request):
        received.append(received_request)
        return {}

    _engine.call("/api/run/summary", request, compute_fn)

    assert received == [request]
    assert isinstance(received[0], SummaryRequest)


def test_engine_call_sends_request_to_params_to_the_daemon(monkeypatch):
    """The daemon path is fed ``request.to_params()``."""
    from elspais.commands import _engine
    from elspais.commands._requests import SummaryRequest

    request = SummaryRequest(values=("level",))
    observed: list[dict[str, str]] = []

    def fake_try_daemon(endpoint, params):
        observed.append(params)
        return ({}, {"type": "daemon"})

    monkeypatch.setattr(_engine, "_try_daemon", fake_try_daemon)

    _engine.call("/api/run/summary", request, lambda g, c, r: {})

    assert observed == [request.to_params()]


# Verifies: REQ-d00258-C
def test_statuses_weighed_active_reads_a_tuple_not_a_namespace():
    """`--treat-active Draft` promotes Draft to active-like. ``statuses_weighed_active``
    needs the names and nothing else, so an API caller has no reason to build an
    argparse.Namespace to reach it."""
    from elspais.config import statuses_weighed_active

    assert statuses_weighed_active(("draft", "review")) == {"Draft", "Review"}


def _scoped_args(**overrides) -> argparse.Namespace:
    """An invocation naming both axes: a level scope AND a values selection,
    so a parity test that passes cannot be passing by accident because one
    axis never travelled (``scope=None`` serializes to no params at all)."""
    fields = {
        "level": ["dev"],
        "not_level": None,
        "status": None,
        "not_status": None,
        "match_status_roles": False,
        "scope": None,
        "values": None,
    }
    fields.update(overrides)
    return argparse.Namespace(**fields)


# Verifies: REQ-d00282-E, REQ-d00279-C
class TestSurfaceParity:
    """The same request, built three ways, produces identical output.

    ``local_request`` (built from ``report_inputs_from_args``, the CLI edge)
    IS the direct-construction shape the design also blesses for MCP -- a
    request built straight from already-derived values with no params round
    trip. ``served_request`` rebuilds from ``local_request.to_params()`` via
    ``report_inputs_from_params``, the HTTP/daemon edge. So the two
    comparisons below (the requests themselves, then the computed output)
    cover all three surfaces the design names: CLI, direct construction, and
    HTTP params -- agreement between the CLI-built request and its own
    params round trip is what keeps a daemon-served report from silently
    drifting from a locally computed one (the defect this branch removes),
    and the requests only match if BOTH axes -- scope and value selection --
    survived the trip, not merely the report each happens to produce.
    """

    def test_summary(self, canonical_federated_graph, canonical_config):
        from elspais.commands._edges import report_inputs_from_args, report_inputs_from_params
        from elspais.commands._requests import SummaryRequest
        from elspais.commands.summary import IDENTITY_VALUE, OFFERED_VALUES, compute_summary

        args = _scoped_args(values="level,implemented")
        inputs = report_inputs_from_args(
            args, canonical_config, OFFERED_VALUES, identity_key=IDENTITY_VALUE
        )
        local_request = SummaryRequest(scope=inputs.scope, values=inputs.values)

        served_inputs = report_inputs_from_params(
            local_request.to_params(), OFFERED_VALUES, identity_key=IDENTITY_VALUE
        )
        served_request = SummaryRequest(scope=served_inputs.scope, values=served_inputs.values)
        assert served_request == local_request

        local = compute_summary(canonical_federated_graph, canonical_config, local_request)
        served = compute_summary(canonical_federated_graph, canonical_config, served_request)
        assert local == served

    def test_trace(self, canonical_federated_graph, canonical_config):
        from elspais.commands._edges import report_inputs_from_args, report_inputs_from_params
        from elspais.commands._requests import TraceRequest
        from elspais.commands.trace import IDENTITY_VALUE, OFFERED_VALUES, compute_trace

        args = _scoped_args(values="id,title")
        inputs = report_inputs_from_args(
            args, canonical_config, OFFERED_VALUES, identity_key=IDENTITY_VALUE
        )
        local_request = TraceRequest(scope=inputs.scope, values=inputs.values)

        served_inputs = report_inputs_from_params(
            local_request.to_params(), OFFERED_VALUES, identity_key=IDENTITY_VALUE
        )
        served_request = TraceRequest(scope=served_inputs.scope, values=served_inputs.values)
        assert served_request == local_request

        local = compute_trace(canonical_federated_graph, canonical_config, local_request)
        served = compute_trace(canonical_federated_graph, canonical_config, served_request)
        assert local == served

    def test_gaps(self, canonical_federated_graph, canonical_config):
        from elspais.commands._edges import report_inputs_from_args, report_inputs_from_params
        from elspais.commands._requests import GapsRequest
        from elspais.commands.gaps import OFFERED_VALUES, compute_gaps

        args = _scoped_args(values="implemented,tested")
        inputs = report_inputs_from_args(args, canonical_config, OFFERED_VALUES, identity_key="")
        local_request = GapsRequest(scope=inputs.scope, values=inputs.values, command="gaps")

        served_inputs = report_inputs_from_params(
            local_request.to_params(), OFFERED_VALUES, identity_key=""
        )
        served_request = GapsRequest(
            scope=served_inputs.scope, values=served_inputs.values, command="gaps"
        )
        assert served_request == local_request

        local = compute_gaps(canonical_federated_graph, canonical_config, local_request)
        served = compute_gaps(canonical_federated_graph, canonical_config, served_request)
        assert local == served

    def test_analysis(self, canonical_federated_graph, canonical_config):
        """`analysis` offers no values (REQ-d00282-F), so its request is built
        straight from a scope -- the one axis it reads -- via the same two
        edges (``scope_from_args`` / ``scope_from_params``) rather than
        ``report_inputs_from_*``, matching ``analysis_cmd.run``."""
        from elspais.commands._requests import AnalysisRequest
        from elspais.commands._scope import scope_from_args, scope_from_params
        from elspais.commands.analysis_cmd import compute_analysis

        args = _scoped_args()
        local_request = AnalysisRequest(
            scope=scope_from_args(args, canonical_config), top=5, include_code=False
        )

        params = local_request.to_params()
        served_request = AnalysisRequest(
            scope=scope_from_params(params),
            top=int(params.get("top", 10)),
            include_code=params.get("include_code") == "true",
            weights=params.get("weights"),
        )
        assert served_request == local_request

        local = compute_analysis(canonical_federated_graph, canonical_config, local_request)
        served = compute_analysis(canonical_federated_graph, canonical_config, served_request)
        assert local == served
