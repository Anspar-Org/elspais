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


def test_engine_call_with_a_request_hands_compute_fn_the_request_object(monkeypatch):
    """Migration scaffolding (deleted in Task 7): a ``request=`` call reaches
    ``compute_fn`` with the request object itself, not a re-serialized dict --
    the whole point of the request types is that a derived value survives the
    trip through the local path unchanged."""
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

    _engine.call("/api/run/summary", {}, compute_fn, request=request)

    assert received == [request]
    assert isinstance(received[0], SummaryRequest)
