# Verifies: REQ-d00254-C
"""flutter test --machine parser yields RESULT records with real paths."""

from pathlib import Path

from elspais.graph.parsers.results.flutter_machine import FlutterMachineParser

SAMPLE = (Path(__file__).parent / "fixtures" / "flutter-machine-sample.jsonl").read_text()


def _by_name(records):
    return {r["name"]: r for r in records}


def test_real_path_from_suite():
    recs = FlutterMachineParser().parse(SAMPLE, "stdout")
    assert all(r["source_file"] == "/repo/provenance/test/provenance_entry_test.dart" for r in recs)


def test_hidden_test_skipped():
    recs = FlutterMachineParser().parse(SAMPLE, "stdout")
    assert all("loading " not in r["name"] for r in recs)  # hidden loading test dropped


def test_pass_fail_skip_status():
    recs = _by_name(FlutterMachineParser().parse(SAMPLE, "stdout"))
    assert recs["ProvenanceEntry round-trip"]["status"] == "passed"
    assert recs["ProvenanceEntry rejects missing hop"]["status"] == "failed"
    assert recs["ProvenanceEntry skipped case"]["status"] == "skipped"


def test_line_and_count():
    recs = FlutterMachineParser().parse(SAMPLE, "stdout")
    assert len(recs) == 3  # the 3 non-hidden tests
    assert _by_name(recs)["ProvenanceEntry round-trip"]["line"] == 47


def test_garbage_lines_ignored():
    recs = FlutterMachineParser().parse('not json\n[{"event":"x"}]\n' + SAMPLE, "stdout")
    assert len(recs) == 3
