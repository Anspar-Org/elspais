# Implements: REQ-d00333-A+B+C+D+E+G+H+I+J+K, REQ-d00249-O+P
"""Run part of a test target: its units, the Unit Ledger, and *Retained Results*.

A test target that declares ``units`` is divided into units, one per test
file it scans. A run that asks to execute only stale targets (``--stale-only``)
executes, of a stale target, only the units whose *Dependency Evidence*
changed, and takes a *Retained Result* for every test of the others.

Terms:

- The *Unit Ledger* (``.elspais-units.json`` in the output area) records, for
  each unit, the run that last executed it, its outcome there, the observed
  files it reached with their digests at that run, and its result lines.
  Every finished run of a units target writes it.
- The observed set is the inputs of the target that its dependency source
  observes. A change of any other input, of the environment or of the
  configuration is in the evidence of every unit, so it executes them all.
  A probe declared ``affects_retention = false`` is left out (REQ-d00333-K).

Only the last fingerprint is needed. A unit is retained only when no input
of its evidence changed, and every unobserved input is in every unit's
evidence, so wherever a run retained a unit, its manifest equals that of the
run that executed the unit on every unobserved entry. Observed files are
judged per unit against the digests copied forward from the run that
executed it.

Anything uncertain selects more: a missing, malformed or foreign ledger, an
earlier run that recorded no end, a source that fails, a unit the source
gave no evidence for, a file the evidence reaches with no recorded digest,
and a result of the unit that the ledger cannot hold each execute the unit,
or the whole target.

Everything a run retains is computed before ``start_run`` empties the output
area. After the command exits, :func:`settle` builds the member's graph once,
reads each executed unit's outcome from the results bound to its tests, and
writes the ledger.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from elspais.graph.dependencies import (
    Evidence,
    Observation,
    ObservesFrame,
    SourceFailed,
    SourceRequest,
    gather_evidence,
    get_source,
)
from elspais.utilities.evidence import (
    ResultLine,
    SnapshotUnreadable,
    read_result_line,
    result_line_text,
)
from elspais.utilities.fingerprint import (
    ENVIRONMENT_PREFIX,
    RETAINED_COVERAGE_NAME,
    RETAINED_RESULTS_NAME,
    RUN_REFERENCE_KEYS,
    SELECTION_NAME,
    UNIT_LEDGER_NAME,
    Freshness,
    describe_inputs,
    differences,
    ended_run_refusal,
    input_files,
    judge,
    read_fingerprint,
    run_reference,
    target_folder,
)

LEDGER_VERSION = 1

#: Outcomes a unit may be retained after (REQ-d00333-G).
RETAINABLE = frozenset({"passed", "skipped"})

#: The reason every retained unit carries.
RETAINED_REASON = "no input of its evidence changed since it executed"

#: The reason a unit the dependency source omitted executes.
NO_EVIDENCE_REASON = "its dependency source gave no evidence for it"


@dataclass(frozen=True)
class UnitEntry:
    """What the ledger records about one unit."""

    unit: str
    executed_in: dict[str, str]
    outcome: str
    observed: dict[str, str]
    results: tuple[ResultLine, ...] = ()
    retained_reason: str = ""

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "unit": self.unit,
            "executed_in": dict(self.executed_in),
            "outcome": self.outcome,
            "observed": [{"path": p, "digest": d} for p, d in sorted(self.observed.items())],
            "results": [line.to_json() for line in sorted(self.results, key=ResultLine.key)],
        }
        if self.retained_reason:
            out["retained"] = {"reason": self.retained_reason}
        return out


@dataclass(frozen=True)
class Ledger:
    """The Unit Ledger of one recorded run of a target."""

    target: str
    units_digest: str
    source: str
    written_by: dict[str, str]
    units: dict[str, UnitEntry]
    source_failed: str = ""
    outside_inputs: tuple[str, ...] = ()

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "version": LEDGER_VERSION,
            "target": self.target,
            "units_digest": self.units_digest,
            "source": self.source,
            "written_by": dict(self.written_by),
            "outside_inputs": sorted(self.outside_inputs),
            "units": [self.units[u].to_json() for u in sorted(self.units)],
        }
        if self.source_failed:
            out["source_failed"] = self.source_failed
        return out


def _run_ref(value: Any) -> dict[str, str] | None:
    if not isinstance(value, dict):
        return None
    keys = RUN_REFERENCE_KEYS
    if set(value) != set(keys) or not all(isinstance(value[k], str) for k in keys):
        return None
    return {k: value[k] for k in keys}


def _entry(obj: Any) -> UnitEntry | None:
    if not isinstance(obj, dict):
        return None
    unit, outcome = obj.get("unit"), obj.get("outcome")
    executed_in = _run_ref(obj.get("executed_in"))
    observed_raw, results_raw = obj.get("observed"), obj.get("results")
    if not isinstance(unit, str) or not isinstance(outcome, str) or executed_in is None:
        return None
    if not isinstance(observed_raw, list) or not isinstance(results_raw, list):
        return None
    observed: dict[str, str] = {}
    for item in observed_raw:
        if not isinstance(item, dict):
            return None
        path, digest = item.get("path"), item.get("digest")
        if not isinstance(path, str) or not isinstance(digest, str):
            return None
        observed[path] = digest
    try:
        results = tuple(read_result_line(r) for r in results_raw)
    except SnapshotUnreadable:
        return None
    retained = obj.get("retained")
    reason = retained.get("reason") if isinstance(retained, dict) else ""
    return UnitEntry(
        unit=unit,
        executed_in=executed_in,
        outcome=outcome,
        observed=observed,
        results=results,
        retained_reason=reason if isinstance(reason, str) else "",
    )


def read_ledger(folder: Path) -> Ledger | None:
    """Return the Unit Ledger in the output area *folder*, or ``None`` where none is readable."""
    try:
        data = json.loads((folder / UNIT_LEDGER_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("version") != LEDGER_VERSION:
        return None
    written_by = _run_ref(data.get("written_by"))
    units_raw, outside = data.get("units"), data.get("outside_inputs")
    if written_by is None or not isinstance(units_raw, list) or not isinstance(outside, list):
        return None
    for key in ("target", "units_digest", "source"):
        if not isinstance(data.get(key), str):
            return None
    units: dict[str, UnitEntry] = {}
    for raw in units_raw:
        entry = _entry(raw)
        if entry is None:
            return None
        units[entry.unit] = entry
    failed = data.get("source_failed", "")
    return Ledger(
        target=data["target"],
        units_digest=data["units_digest"],
        source=data["source"],
        written_by=written_by,
        units=units,
        source_failed=failed if isinstance(failed, str) else "",
        outside_inputs=tuple(p for p in outside if isinstance(p, str)),
    )


def write_ledger(folder: Path, ledger: Ledger) -> Path:
    """Write *ledger* into the output area *folder*."""
    path = folder / UNIT_LEDGER_NAME
    path.write_text(json.dumps(ledger.to_json(), indent=1, sort_keys=True) + "\n")
    return path


def units_digest(target: Any) -> str:
    """The digest of the target's ``units`` table: a ledger is used only under the same one."""
    units = target.units.model_dump(mode="json") if target.units is not None else None
    return hashlib.sha256(json.dumps(units, sort_keys=True).encode("utf-8")).hexdigest()


def _raw(config: Any) -> dict[str, Any]:
    return config if isinstance(config, dict) else config.model_dump(mode="json", by_alias=True)


def _typed(config: Any) -> Any:
    if isinstance(config, dict):
        from elspais.config import validate_config

        return validate_config(config)
    return config


def as_observation(kind_config: Any) -> Observation:
    """A scanning-kind selection as the dependency interface's *Observation*."""
    return Observation(
        directories=tuple(kind_config.directories),
        file_patterns=tuple(kind_config.file_patterns),
        skip_dirs=tuple(kind_config.skip_dirs),
        skip_files=tuple(kind_config.skip_files),
    )


def _cwd_rel(repo_root: Path, target: Any) -> str:
    from elspais.graph.factory import target_prefix

    return (target_prefix(target, repo_root) or "").rstrip("/")


def unit_inventory(repo_root: Path, config: Any, target: Any) -> tuple[str, ...]:
    """The units of *target*: the repo-relative test files it scans, sorted."""
    from elspais.graph.factory import kind_files, scan_plan, target_test_files

    root = Path(repo_root).resolve()
    scanned: set[str] = set()
    for kind in scan_plan(_raw(config), root, scan_code=False):
        if kind.kind != "test":
            continue
        for path in kind_files(root, kind):
            try:
                scanned.add(path.resolve().relative_to(root).as_posix())
            except ValueError:
                continue
    return tuple(sorted(target_test_files(target, scanned, root)))


def observes_frame(repo_root: Path, config: Any, target: Any) -> ObservesFrame:
    """What a source's default observation of *target* is derived from.

    The test selection is the one the scan reads by: its directory patterns
    expanded to the directories they name, repo-relative.
    """
    from elspais.graph.factory import scan_plan

    root = Path(repo_root).resolve()
    test = Observation()
    for kind in scan_plan(_raw(config), root, scan_code=False):
        if kind.kind != "test":
            continue
        directories = []
        for directory in kind.directories:
            try:
                directories.append(directory.resolve().relative_to(root).as_posix() or ".")
            except ValueError:
                continue
        test = Observation(
            directories=tuple(sorted(directories)),
            file_patterns=tuple(kind.patterns),
            skip_dirs=tuple(kind.skip_dirs),
            skip_files=tuple(kind.skip_files),
        )
    return ObservesFrame(
        cwd=_cwd_rel(root, target), inputs=as_observation(target.inputs), test=test
    )


def observation_of(repo_root: Path, config: Any, target: Any) -> Observation:
    """The files the target's dependency source observes: declared, or the source's default."""
    if target.units.observes is not None:
        return as_observation(target.units.observes)
    source = get_source(target.units.source_name())
    default = source.default_observes(observes_frame(repo_root, config, target))
    # The schema refuses a source without a default unless observes is declared.
    return default if default is not None else Observation()


def observed_set(
    repo_root: Path, observation: Observation, inputs: Iterable[str]
) -> frozenset[str]:
    """The inputs the observation selects, repo-relative: the walk every selection uses."""
    from elspais.graph.file_selection import select_files

    root = Path(repo_root).resolve()
    selection = select_files(
        root,
        list(observation.directories) or ["."],
        list(observation.skip_dirs),
        list(observation.skip_files),
        list(observation.file_patterns) or ["*"],
    )
    selected = {p.relative_to(root).as_posix() for p in selection.selected}
    return frozenset(selected & set(inputs))


def unaffecting_entries(target: Any) -> frozenset[str]:
    """The manifest entries of the probes the target declares as leaving retention unaffected."""
    return frozenset(
        ENVIRONMENT_PREFIX + probe.name
        for probe in target.environment_probes
        if not probe.affects_retention
    )


@dataclass(frozen=True)
class Judgement:
    """Which units a run executes, and why; which it retains."""

    selected: dict[str, str]
    retained: dict[str, UnitEntry]


# Implements: REQ-d00333-B+D+G+K
def judge_units(
    units: Iterable[str],
    ledger: Ledger,
    last_manifest: dict[str, str],
    current: dict[str, str],
    observed: frozenset[str],
    evidence: Evidence,
    unaffecting: frozenset[str] = frozenset(),
) -> Judgement:
    """Divide *units* into those a run executes and those whose results it retains.

    *last_manifest* is the manifest of the run that wrote *ledger*, and
    *current* is the manifest of the tree now. A path a unit's ledger entry
    recorded as observed counts as observed, so an observed file deleted
    since is judged by the units that reached it. A unit the evidence omits
    has no recorded evidence, so its evidence is every input: it executes,
    and the reason the source gave for it is stated.
    """
    recorded_observed = set().union(*(e.observed for e in ledger.units.values()))
    observed_all = set(observed) | recorded_observed
    unobserved_changed = [
        entry
        for entry in differences(last_manifest, current)
        if entry not in observed_all and entry not in unaffecting
    ]
    selected: dict[str, str] = {}
    retained: dict[str, UnitEntry] = {}
    for unit in units:
        entry = ledger.units.get(unit)
        if entry is None:
            selected[unit] = "a new test file"
            continue
        if entry.outcome not in RETAINABLE:
            selected[unit] = f"its last execution {_outcome_words(entry.outcome)}"
            continue
        if unobserved_changed:
            selected[unit] = f"{describe_inputs(unobserved_changed)} changed"
            continue
        if unit not in evidence.files:
            why = evidence.no_evidence.get(unit)
            selected[unit] = f"{NO_EVIDENCE_REASON}: {why}" if why else NO_EVIDENCE_REASON
            continue
        reached = {unit} | set(entry.observed) | set(evidence.files[unit])
        changed = _changed_for(reached, entry, current, observed_all)
        if changed:
            selected[unit] = f"{describe_inputs(changed)} changed"
            continue
        retained[unit] = UnitEntry(
            unit=entry.unit,
            executed_in=entry.executed_in,
            outcome=entry.outcome,
            observed=entry.observed,
            results=entry.results,
            retained_reason=RETAINED_REASON,
        )
    return Judgement(selected=selected, retained=retained)


def _changed_for(
    reached: set[str], entry: UnitEntry, current: dict[str, str], observed: set[str]
) -> list[str]:
    """The files of *reached*, a unit's evidence, that changed since the unit executed.

    An observed file, and the unit's own file, is judged against the digest
    recorded when the unit executed. A reached file that holds no recorded
    digest and is no input now -- one outside the inputs, or one never
    recorded -- counts as changed. An unobserved input is judged with every
    other unobserved input.
    """
    judged = {p for p in reached if p in observed or p == entry.unit}
    recorded = {p: entry.observed[p] for p in judged if p in entry.observed}
    now = {p: current[p] for p in judged if p in current}
    unknown = {p for p in reached if p not in recorded and p not in current}
    return sorted(set(differences(recorded, now)) | unknown)


def _outcome_words(outcome: str) -> str:
    return {
        "failed": "failed",
        "no-result": "produced no result",
        "unplaced": "produced a result that binds to no single test",
        "command-failed": "ended in a command that failed with no failing result",
    }.get(outcome, outcome)


# Implements: REQ-d00333-E
def ledger_refusal(ledger: Ledger | None, verdict: Freshness, target: Any, source_name: str) -> str:
    """Return why *ledger* cannot be retained from, or ``""``."""
    fingerprint = verdict.fingerprint
    if verdict.state not in ("stale", "fresh") or not fingerprint:
        return {
            "absent": "no earlier run of the target holds results",
            "running": "a run of the target is in progress",
        }.get(verdict.state, "no earlier run of the target recorded its fingerprint")
    if refusal := ended_run_refusal(fingerprint):
        return f"the earlier run cannot be retained from: {refusal}"
    if ledger is None:
        return "the earlier run recorded no readable Unit Ledger"
    if ledger.written_by != run_reference(fingerprint):
        return "the Unit Ledger was written by another run than the one recorded"
    if ledger.units_digest != units_digest(target):
        return "the target's units table changed since the earlier run"
    if ledger.source != source_name:
        return "the target's dependency source changed since the earlier run"
    return ""


@dataclass(frozen=True)
class UnitPlan:
    """What a run of a units target executes and retains.

    ``whole_reason`` is set where every unit executes, and says why.
    ``evidence`` is the source's answer on the current tree, or ``None`` where
    it failed; ``source_failed`` then says why. ``request`` is what the
    source was asked, so it can be asked again about some of the units.
    """

    target: str
    units: tuple[str, ...]
    selected: dict[str, str]
    retained: dict[str, UnitEntry]
    whole_reason: str
    source: str
    units_digest: str
    observed: frozenset[str]
    evidence: Evidence | None
    source_failed: str = ""
    outside_inputs: tuple[str, ...] = ()
    retained_coverage: dict[str, Any] | None = None
    receives: str = "placeholder"
    full_selection: str = ""
    cwd_rel: str = ""
    request: SourceRequest | None = None

    @property
    def whole(self) -> bool:
        return not self.retained

    def without_evidence(self) -> tuple[str, ...]:
        """The units the source answered for and gave no evidence for."""
        if self.evidence is None:
            return ()
        return tuple(u for u in self.units if u not in self.evidence.files)

    # Implements: REQ-d00311-E, REQ-d00333-B+C
    def describe_no_evidence(self) -> list[str]:
        """One line per reason the source gave for holding no evidence, with its units' count.

        A unit the source left out without a reason is counted under none.
        """
        by_reason: dict[str, int] = {}
        for unit in self.without_evidence():
            why = self.evidence.no_evidence.get(unit, "") if self.evidence else ""
            by_reason[why] = by_reason.get(why, 0) + 1
        lines = []
        for why, count in sorted(by_reason.items()):
            files = "test file" if count == 1 else "test files"
            words = f"no dependency evidence for {count} {files}"
            lines.append(f"{words}: {why}" if why else words)
        return lines

    def describe(self) -> str:
        """The words a stale-only run states for this target (REQ-d00315-H, REQ-d00323-O)."""
        if self.whole:
            return f"every test file: {self.whole_reason}"
        return (
            f"{len(self.selected)} of {len(self.units)} test files; {len(self.retained)} retained"
        )


def _source_request(
    repo_root: Path,
    target: Any,
    units: tuple[str, ...],
    inputs: frozenset[str],
    observed: frozenset[str],
) -> SourceRequest:
    """What *target*'s dependency source is asked about *units* on the current tree."""
    return SourceRequest(
        repo_root=Path(repo_root).resolve(),
        cwd=(Path(repo_root) / target.cwd).resolve(),
        target_name=target.name,
        units=units,
        inputs=inputs,
        observed=observed,
        settings=target.units.source_settings(),
        environment_probes=tuple(
            probe.name for probe in target.environment_probes if probe.affects_retention
        ),
    )


def _evidence_of(source_name: str, request: SourceRequest) -> tuple[Evidence | None, str]:
    source = get_source(source_name)
    try:
        return gather_evidence(source, request), ""
    except SourceFailed as exc:
        return None, exc.reason
    except Exception as exc:  # a source's own defect costs a whole run, never a wrong retention
        return None, f"the {source.name!r} dependency source raised {type(exc).__name__}: {exc}"


def _outside_inputs(
    repo_root: Path, evidence: Evidence | None, inputs: frozenset[str]
) -> tuple[str, ...]:
    """Repository files the evidence reaches that are not inputs (REQ-d00333-D)."""
    from elspais.graph.parsers.results.placement import placed_in_repo

    if evidence is None:
        return ()
    reached = set().union(*evidence.files.values()) if evidence.files else set()
    outside = set()
    for path in reached:
        rel = placed_in_repo(path, repo_root, repo_root)
        if rel is not None and rel not in inputs:
            outside.add(rel)
    return tuple(sorted(outside))


# Implements: REQ-d00333-B+E+I
def plan_run(
    repo_root: Path,
    config: Any,
    target: Any,
    *,
    stale_only: bool,
    full: bool,
    digest_cache: dict[Path, str] | None = None,
) -> UnitPlan | None:
    """Decide what a run of *target* executes. ``None`` where the target declares no units.

    The evidence is computed on every run, so the ledger a whole run writes
    records the digests a later run judges against.
    """
    if target.units is None:
        return None
    root = Path(repo_root).resolve()
    typed = _typed(config)
    units = unit_inventory(root, config, target)
    inputs = frozenset(p.relative_to(root).as_posix() for p in input_files(root, typed, target))
    observed = observed_set(root, observation_of(root, config, target), inputs)
    request = _source_request(root, target, units, inputs, observed)
    evidence, failed = _evidence_of(target.units.source_name(), request)
    none_held = ""
    if evidence is not None and units and not evidence.files:
        # The source answered, so this is no failure: the evidence is kept,
        # the run states each reason, and settling asks the source again
        # once the command has ended.
        reasons = sorted(set(evidence.no_evidence.values()))
        none_held = "the dependency source gave no evidence for any test file" + (
            f": {'; '.join(reasons)}" if reasons else ""
        )
    common = {
        "target": target.name,
        "units": units,
        "source": target.units.source_name(),
        "units_digest": units_digest(target),
        "observed": observed,
        "evidence": evidence,
        "source_failed": failed,
        "outside_inputs": _outside_inputs(root, evidence, inputs),
        "receives": target.units.receives,
        "full_selection": target.units.full_selection,
        "cwd_rel": _cwd_rel(root, target),
        "request": request,
    }

    def whole(reason: str) -> UnitPlan:
        return UnitPlan(
            selected=dict.fromkeys(units, reason), retained={}, whole_reason=reason, **common
        )

    if full:
        return whole("the run asks to execute every test (--full)")
    if not stale_only:
        return whole("a run that is not stale-only executes every test")
    if evidence is None:
        return whole(failed)
    if none_held:
        return whole(none_held)
    verdict = judge(root, typed, target.name, digest_cache=digest_cache)
    folder = target_folder(root, typed, target.name)
    ledger = read_ledger(folder)
    if refusal := ledger_refusal(ledger, verdict, target, target.units.source_name()):
        return whole(refusal)
    assert ledger is not None
    # The judgement of the target computed the manifest of the tree now, so
    # the units are judged against that one manifest.
    current = verdict.current
    if current is None:
        return whole("the judgement of the target computed no manifest of the tree")
    judgement = judge_units(
        units,
        ledger,
        verdict.fingerprint["manifest"],
        current,
        observed,
        evidence,
        unaffecting_entries(target),
    )
    if not judgement.retained:
        # One cause selecting every unit, such as a changed input the source
        # does not observe, is named rather than summarised.
        causes = set(judgement.selected.values())
        if len(causes) == 1:
            return whole(causes.pop())
        return whole("the evidence of every test file changed")
    coverage = retained_coverage(root, typed, target, verdict.fingerprint, current)
    return UnitPlan(
        selected=judgement.selected,
        retained=judgement.retained,
        whole_reason="",
        retained_coverage=coverage,
        **common,
    )


def selection_words(plan: UnitPlan) -> list[str]:
    """The selected units as paths relative to the target's working directory."""
    words = []
    for unit in sorted(plan.selected):
        if plan.cwd_rel and unit.startswith(plan.cwd_rel + "/"):
            words.append(unit[len(plan.cwd_rel) + 1 :])
        else:
            words.append(os.path.relpath(unit, plan.cwd_rel or "."))
    return words


# Implements: REQ-d00249-O+P
def command_for(command: str, plan: UnitPlan | None) -> str:
    """The command a run spawns, with the selection placeholder filled."""
    from elspais.config.schema import SELECTION_PLACEHOLDER
    from elspais.utilities.commands import fill_placeholder

    if plan is None or plan.receives != "placeholder":
        return command
    if plan.whole:
        return command.replace(SELECTION_PLACEHOLDER, plan.full_selection)
    return fill_placeholder(command, SELECTION_PLACEHOLDER, selection_words(plan))


# Implements: REQ-d00333-A+J, REQ-d00249-O
def write_artifacts(folder: Path, plan: UnitPlan | None) -> dict[str, str]:
    """Write the run's retained artifacts and selection; return the environment to add.

    The output area has just been emptied by ``start_run``.
    """
    from elspais.utilities.fingerprint import SELECTION_ENV

    if plan is None or plan.whole:
        return {}
    write_retained(folder, plan.retained)
    if plan.retained_coverage:
        from elspais.graph.parsers.results.coverage_json import render_coverage_json

        (folder / RETAINED_COVERAGE_NAME).write_text(
            render_coverage_json(plan.retained_coverage), encoding="utf-8"
        )
    selection = folder / SELECTION_NAME
    selection.write_text("".join(w + "\n" for w in selection_words(plan)), encoding="utf-8")
    return {SELECTION_ENV: str(selection)}


# Implements: REQ-d00333-J+L
def retained_coverage(
    repo_root: Path,
    config: Any,
    target: Any,
    last_fingerprint: dict[str, Any],
    current: dict[str, str],
) -> dict[str, Any] | None:
    """The line coverage a partial run keeps from earlier runs, in coverage-json form.

    A file's measurement is kept only where the file holds the content it
    held in the run that measured it. The earlier area's own coverage file
    was measured by the last run; a measurement that run itself retained
    carries the digest and the runs recorded with it.
    """
    from elspais.graph.factory import context_placer
    from elspais.graph.parsers.results.coverage_json import CoverageJsonParser, merge_readings
    from elspais.graph.parsers.results.placement import origin_dir, placed_in_repo
    from elspais.graph.parsers.results.registry import coverage_reader_for, get_reporter

    folder = target_folder(repo_root, config, target.name)
    root = Path(repo_root).resolve()
    kept: dict[str, Any] = {}
    last_run = run_reference(last_fingerprint)
    last_manifest = last_fingerprint.get("manifest") or {}
    if target.coverage:
        path = folder / target.coverage
        found = coverage_reader_for(path) if path.is_file() else None
        if found is not None:
            name, reader = found
            content = "" if getattr(reader, "binary", False) else path.read_text(encoding="utf-8")
            measured = reader.parse(content, str(path))
            cwd = (root / target.cwd) if target.cwd else root
            _origin, frame = origin_dir(
                get_reporter(name), target.coverage_origin, cwd, root, foreign=False
            )
            # The retained coverage is written with its test names
            # repo-relative, as the build places a run's own.
            place_contexts = context_placer(target, cwd, root)
            for source, data in measured.items():
                rel = placed_in_repo(source, frame, root)
                digest = last_manifest.get(rel) if rel else None
                if rel is None or digest is None or current.get(rel) != digest:
                    continue
                placed = dict(data)
                if data.get("contexts"):
                    placed["contexts"] = place_contexts(data["contexts"])
                kept[rel] = {**placed, "provenance": {"digest": digest, "measured_in": [last_run]}}
    earlier = folder / RETAINED_COVERAGE_NAME
    if earlier.is_file():
        for rel, data in (
            CoverageJsonParser().parse(earlier.read_text(encoding="utf-8"), str(earlier)).items()
        ):
            provenance = data.get("provenance") or {}
            digest = provenance.get("digest")
            if not digest or current.get(rel) != digest:
                continue
            kept[rel] = merge_readings(kept.get(rel), data)
    return kept or None


@dataclass
class Settled:
    """What settling a finished run found for one target."""

    target: str
    executed: int = 0
    retained: int = 0
    missing: list[str] = field(default_factory=list)
    overrun: list[str] = field(default_factory=list)
    ledger_written: bool = False


# Implements: REQ-d00333-A+G+H
def settle(
    repo_root: Path,
    config: Any,
    raw_config: dict[str, Any] | None,
    plans: dict[str, UnitPlan],
) -> dict[str, Settled]:
    """Read each executed unit's outcome after its run; write each target's ledger.

    *plans* maps each units target the run executed (and finished) to its
    plan. The member's graph is built once. Each RESULT a target's own
    results hold is bound to the units of the tests it yields to, and becomes
    a result line of its unit where it binds to one test. A test of a unit
    that ends without its retained entry, and holds neither a result of this
    run nor a *Retained Result*, is named in ``missing``, and the caller fails
    the run (REQ-d00333-H). A retained unit that the command executed anyway
    is named in ``overrun``: its fresh results replace the retained ones.
    """
    if not plans:
        return {}
    from elspais.graph.factory import build_graph
    from elspais.graph.GraphNode import NodeKind
    from elspais.graph.relations import EdgeKind
    from elspais.utilities.evidence import OUTCOME_OF, result_line_of

    root = Path(repo_root).resolve()
    typed = _typed(config)
    raw = raw_config if raw_config is not None else _raw(config)
    graph = build_graph(config=raw, repo_root=root, scan_code=False)
    namespace = typed.project.namespace

    def test_file(test: Any) -> str | None:
        file_node = test.file_node()
        return file_node.get_field("relative_path") if file_node else None

    tests_by_file: dict[str, list[Any]] = {}
    for test in graph.nodes_by_kind(NodeKind.TEST, namespace=namespace):
        if rel := test_file(test):
            tests_by_file.setdefault(rel, []).append(test)

    out: dict[str, Settled] = {}
    for name, plan in plans.items():
        settled = Settled(target=name)
        out[name] = settled
        folder = target_folder(root, typed, name)
        fingerprint = read_fingerprint(folder)
        if fingerprint is None or not fingerprint.get("finished_at"):
            continue
        # Each fresh result of the target, by the unit it binds to: a line
        # where it binds to one test, and its outcome either way. A result
        # that binds to no test of the target is held against every unit
        # that executed.
        lines: dict[str, list[ResultLine]] = {}
        outcomes: dict[str, set[str]] = {}
        unplaced: set[str] = set()
        fresh_ids: set[str] = set()
        unbound: set[str] = set()
        for node in graph.nodes_by_kind(NodeKind.RESULT, namespace=namespace):
            if node.get_field("target") != name or node.get_field("retained_from"):
                continue
            fresh_ids.add(node.id)
            line = result_line_of(node)
            bound = {
                rel
                for t in node.iter_parents(edge_kinds={EdgeKind.YIELDS})
                if (rel := test_file(t))
            }
            if not isinstance(line, str):
                bound.add(line.runner or line.file)
                lines.setdefault(line.runner or line.file, []).append(line)
            outcome = OUTCOME_OF.get(node.get_field("status") or "")
            for unit in bound or {""}:
                outcomes.setdefault(unit, set()).add(outcome or "unknown")
                if isinstance(line, str):
                    unplaced.add(unit)
            if not bound:
                unbound.add(outcome or "unknown")
        # A command that exited non-zero while no result it wrote failed
        # holds a failure no result names, against every unit it executed.
        exit_status = fingerprint.get("exit_status")
        unexplained_exit = (
            isinstance(exit_status, int)
            and exit_status != 0
            and not any("failed" in seen for seen in outcomes.values())
        )
        start_manifest: dict[str, str] = fingerprint.get("manifest") or {}
        executed_in = run_reference(fingerprint)
        later, outside = _evidence_after_run(root, plan)
        entries: dict[str, UnitEntry] = {}
        retained = dict(plan.retained)
        for unit in plan.units:
            ran = unit in lines or unit in outcomes
            if unit in retained and not ran:
                entries[unit] = retained[unit]
                settled.retained += len(retained[unit].results)
                continue
            if unit in retained:
                settled.overrun.append(unit)
            # A unit the runner ran though it was retained keeps the fresh result.
            retained.pop(unit, None)
            unit_lines = lines.get(unit, [])
            missing = [
                f"{unit}:{t.get_field('parse_line')} {t.get_field('test_name') or t.id}"
                for t in tests_by_file.get(unit, [])
                if not any(
                    r.kind is NodeKind.RESULT and r.id in fresh_ids
                    for r in t.iter_children(edge_kinds={EdgeKind.YIELDS})
                )
            ]
            settled.missing.extend(missing)
            seen = outcomes.get(unit, set()) | unbound
            if "failed" in seen:
                outcome = "failed"
            elif missing or not ran:
                outcome = "no-result"
            elif unexplained_exit:
                outcome = "command-failed"
            elif unit in unplaced or unbound or "unknown" in seen:
                outcome = "unplaced"
            elif seen == {"skipped"}:
                outcome = "skipped"
            else:
                outcome = "passed"
            reached: set[str] = {unit}
            evidence = plan.evidence.files.get(unit) if plan.evidence is not None else None
            if evidence is None:
                evidence = later.get(unit)
            no_evidence = evidence is None
            if evidence is not None:
                reached |= set(evidence)
            # A unit's own file is judged like an observed one wherever it
            # lies, so its digest is recorded whether or not it is observed.
            observed = {
                p: start_manifest[p]
                for p in reached
                if (p in plan.observed or p == unit) and p in start_manifest
            }
            entries[unit] = UnitEntry(
                unit=unit,
                executed_in=executed_in,
                outcome=outcome,
                # A unit with no evidence records none, so it executes again.
                observed={} if no_evidence else observed,
                results=tuple(unit_lines),
            )
            settled.executed += len(unit_lines)
        if set(retained) != set(plan.retained):
            write_retained(folder, retained)
        write_ledger(
            folder,
            Ledger(
                target=name,
                units_digest=plan.units_digest,
                source=plan.source,
                written_by=executed_in,
                units=entries,
                source_failed=plan.source_failed,
                outside_inputs=outside,
            ),
        )
        settled.ledger_written = True
    return out


# Implements: REQ-d00333-B
def _evidence_after_run(
    root: Path, plan: UnitPlan
) -> tuple[dict[str, frozenset[str]], tuple[str, ...]]:
    """Ask the source again, after the command, about the units it gave no evidence for.

    A cause the run itself removes -- a package configuration the test runner
    resolved again -- then costs those units one execution rather than two.
    The units executed on the tree the run started from, so what the answer
    reaches is recorded with the digests of the run's start; an input that
    changed while the run went on makes the next run refuse the ledger. A
    source that failed when the run was planned is not asked again. Returns
    the evidence found and the repository files reached that are not inputs.
    """
    asked = plan.without_evidence()
    if not asked or plan.request is None:
        return {}, plan.outside_inputs
    answer, _failed = _evidence_of(plan.source, replace(plan.request, units=asked))
    if answer is None:
        return {}, plan.outside_inputs
    later = {u: frozenset(answer.files[u]) for u in asked if u in answer.files}
    outside = set(plan.outside_inputs) | set(
        _outside_inputs(root, Evidence(files=later), plan.request.inputs)
    )
    return later, tuple(sorted(outside))


def write_retained(folder: Path, retained: dict[str, UnitEntry]) -> None:
    """Write the *Retained Results* of *retained* units into the output area *folder*.

    Where no unit holds a result line, no file is left.
    """
    lines = [
        line.as_retained(entry.executed_in, entry.retained_reason)
        for entry in retained.values()
        for line in entry.results
    ]
    path = folder / RETAINED_RESULTS_NAME
    if not lines:
        if path.is_file():
            path.unlink()
        return
    path.write_text(
        "".join(result_line_text(line) for line in sorted(lines, key=ResultLine.key)),
        encoding="utf-8",
    )


def outside_inputs_of(folder: Path) -> tuple[str, ...]:
    """The repository files the ledger in *folder* records as reached and not inputs."""
    ledger = read_ledger(folder)
    return ledger.outside_inputs if ledger is not None else ()


__all__ = [
    "LEDGER_VERSION",
    "NO_EVIDENCE_REASON",
    "RETAINED_REASON",
    "Judgement",
    "Ledger",
    "Settled",
    "UnitEntry",
    "UnitPlan",
    "command_for",
    "judge_units",
    "ledger_refusal",
    "observed_set",
    "outside_inputs_of",
    "plan_run",
    "read_ledger",
    "retained_coverage",
    "settle",
    "unit_inventory",
    "write_artifacts",
    "write_ledger",
]
