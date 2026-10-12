"""Empirical evaluation of the selector.

Two instruments, both meant for occasional/nightly runs, not every PR:

compare / calibrate
    Run the TIA selection and the complete suite on the SAME revision and
    compare outcomes. A test that fails in the full run but was not selected
    is a *missed failure* -- a false negative of the selector. Tests that ran
    in both runs and disagree are reported as flaky/order-dependent.

mutants (calibrate --mutants N --seed S)
    A real change rarely makes a test fail, so the comparison above mostly
    reports "nothing missed" without having been put to the test. A mutant
    is a seeded, deterministic fault: one production function picked at
    random (among those the baseline saw executed) gets
    `raise RuntimeError("tia-mutant")` as its first statement. The selector
    is asked what to run for that change, and then the tests it did NOT
    select are run. Any of them failing is a missed failure: a test that
    executes the function but that the baseline did not attribute to it.
    Running only the complement keeps the probe affordable.
"""

from __future__ import annotations

import ast
import json
import os
import random
import subprocess
import sys
import time

from .runner import junit_summary, nodeid_to_junit_key, run_selection, worker_count


def _failing(cases: dict) -> set[str]:
    return {k for k, c in cases.items() if c["outcome"] in ("failed", "error")}


def _baseline_failing(m: dict) -> set[str]:
    """JUnit keys of the tests that did not pass in the manifest's baseline."""
    path = os.path.join(m.get("baseline", {}).get("path") or "", "baseline.json")
    try:
        with open(path, encoding="utf-8") as fh:
            tests = json.load(fh)["tests"]
    except (OSError, ValueError, KeyError):
        return set()
    return {
        nodeid_to_junit_key(n) for n, t in tests.items() if t.get("outcome") in ("failed", "error")
    }


def compare_runs(tia_manifest: str | dict, full_junit: str) -> dict:
    """A failing full-run test TIA did not select is a missed failure --
    unless it already failed in the baseline: a failure no change caused is
    not one the selection could have caught, and is listed apart."""
    m = tia_manifest
    if not isinstance(m, dict):
        with open(m, encoding="utf-8") as fh:
            m = json.load(fh)
    full = junit_summary(full_junit)
    if not full.get("present"):
        raise FileNotFoundError(full_junit)
    tia_cases = {}
    if m.get("run", {}).get("junit"):
        tia_cases = junit_summary(m["run"]["junit"]).get("cases", {})
    if m["selection_mode"] == "full":
        selected_keys = set(full["cases"])
    else:
        selected_keys = {nodeid_to_junit_key(t["test"]) for t in m["tests"]}
        selected_keys |= set(tia_cases)  # new tests the baseline did not know
    full_fail = _failing(full["cases"])
    known = _baseline_failing(m)
    unselected = full_fail - selected_keys
    missed = sorted(unselected - known)
    disagree = sorted(
        k
        for k in set(tia_cases) & set(full["cases"])
        if tia_cases[k]["outcome"] != full["cases"][k]["outcome"]
    )
    full_time = sum(c["time"] for c in full["cases"].values())
    tia_time = sum(c["time"] for c in tia_cases.values())
    return {
        "selection_mode": m["selection_mode"],
        "full_tests": full["tests"],
        "full_failures": sorted(full_fail),
        "selected_tests": len(selected_keys & set(full["cases"])),
        "tia_failures": sorted(_failing(tia_cases)),
        "missed_failures": missed,
        "unselected_known_failures": sorted(unselected & known),
        "outcome_disagreements": disagree,
        "full_test_seconds": round(full_time, 1),
        "tia_test_seconds": round(tia_time, 1),
        "tia_wall_seconds": m.get("run", {}).get("elapsed_seconds"),
        "verdict": "MISSED FAILURES" if missed else "no missed failures",
    }


def _run_full(root: str, out_dir: str) -> tuple[str, float]:
    os.makedirs(out_dir, exist_ok=True)
    junit = os.path.join(out_dir, "junit.xml")
    w = worker_count(root)
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/",
        "--no-cov",
        "-q",
        "--tb=line",
        f"--junitxml={junit}",
        "-o",
        "junit_family=xunit1",
        "-p",
        "no:cacheprovider",
        "-n",
        str(w),
        "--dist",
        "loadfile",
    ]
    t0 = time.time()
    subprocess.run(cmd, cwd=root)
    return junit, time.time() - t0


# -- mutants -----------------------------------------------------------------


def mutant_candidates(root: str, cfg, cov) -> list[tuple[str, int, str, int, int]]:
    """(path, insert_line, qualname, indent, test_hits) for covered functions."""
    out = []
    for dp, dns, fns in os.walk(os.path.join(root, *cfg.production_roots[0].split("/"))):
        dns[:] = [d for d in dns if d != "__pycache__"]
        for fn in sorted(fns):
            if not fn.endswith(".py"):
                continue
            rel = os.path.relpath(os.path.join(dp, fn), root).replace(os.sep, "/")
            try:
                src = open(os.path.join(root, rel), encoding="utf-8").read()
                tree = ast.parse(src)
            except (OSError, SyntaxError):
                continue

            def visit(body, prefix, rel=rel):
                for node in body:
                    if isinstance(node, ast.ClassDef):
                        visit(node.body, prefix + node.name + ".", rel)
                    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        stmts = node.body
                        first = stmts[0]
                        if (
                            isinstance(first, ast.Expr)
                            and isinstance(getattr(first, "value", None), ast.Constant)
                            and isinstance(first.value.value, str)
                        ):
                            if len(stmts) == 1:
                                continue
                            first = stmts[1]
                        if first.lineno == node.lineno:
                            continue
                        hits = cov.hits(rel, first.lineno, node.end_lineno)
                        if hits:
                            out.append(
                                (rel, first.lineno, prefix + node.name, first.col_offset, len(hits))
                            )

            visit(tree.body, "")
    return sorted(out)


def _inject(path: str, line: int, indent: int) -> str:
    with open(path, encoding="utf-8") as fh:
        original = fh.read()
    lines = original.splitlines(keepends=True)
    lines.insert(line - 1, " " * indent + 'raise RuntimeError("tia-mutant")\n')
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("".join(lines))
    return original


def run_mutants(
    root: str, cfg, baseline_path: str, out_dir: str, n: int, seed: int, current_env: dict
) -> list[dict]:
    from .baseline import load_baseline
    from .selector import select

    base = load_baseline(baseline_path, root, on_environment_change="warn")
    cands = mutant_candidates(root, cfg, base.coverage)
    rng = random.Random(seed)
    picks = rng.sample(cands, min(n, len(cands)))
    results = []
    for i, (rel, line, qual, indent, hits) in enumerate(picks):
        path = os.path.join(root, rel)
        original = _inject(path, line, indent)
        try:
            sel = select(root, cfg, baseline_path, current_env=current_env)
            mdir = os.path.join(out_dir, f"mutant-{i:02d}")
            os.makedirs(mdir, exist_ok=True)
            selected_files = set(sel.run_files) if sel.mode != "full" else None
            record = {
                "mutant": f"{rel}:{line} {qual}",
                "baseline_hits": hits,
                "selection_mode": sel.mode,
                "selected_tests": sel.selected_count,
                "fallbacks": [f.kind for f in sel.fallbacks],
            }
            if selected_files is None:
                record.update(complement_tests=0, missed_failures=[], verdict="full suite selected")
            else:
                # Every baseline test the selector did not choose, by node id:
                # at test granularity an unselected test can share a file with
                # selected ones, and those are the ones this probe is about.
                complement_ids = sorted(n_ for n_ in base.tests if n_ not in sel.tests)
                complement = sorted({base.tests[n_]["file"] for n_ in complement_ids})
                spec = os.path.join(mdir, "complement.json")
                with open(spec, "w", encoding="utf-8") as fh:
                    json.dump({"nodeids": complement_ids, "new_files": []}, fh)
                junit = os.path.join(mdir, "complement.xml")
                cmd = [
                    sys.executable,
                    "-m",
                    "pytest",
                    "--no-cov",
                    "-q",
                    "--tb=no",
                    f"--junitxml={junit}",
                    "-o",
                    "junit_family=xunit1",
                    "-p",
                    "no:cacheprovider",
                    "-p",
                    "tools.tia.pytest_select",
                    "-n",
                    str(worker_count(root)),
                    "--dist",
                    "loadfile",
                    *complement,
                ]
                env = dict(os.environ, TIA_SELECT_FILE=spec)
                env["PYTHONPATH"] = root + (
                    os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
                )
                t0 = time.time()
                subprocess.run(
                    cmd, cwd=root, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                js = junit_summary(junit)
                baseline_failing = {
                    nodeid_to_junit_key(n_)
                    for n_, t in base.tests.items()
                    if t["outcome"] in ("failed", "error")
                }
                missed = sorted(_failing(js.get("cases", {})) - baseline_failing)
                record.update(
                    complement_tests=js.get("tests", 0),
                    complement_seconds=round(time.time() - t0, 1),
                    missed_failures=missed,
                    verdict="MISSED" if missed else "no missed failures",
                )
            results.append(record)
            print(json.dumps(record), flush=True)
        finally:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(original)
    return results


def calibrate(args) -> int:
    from .__main__ import _current_env
    from .config import load_config
    from .gitio import repo_root
    from .selector import select

    root = repo_root()
    cfg = load_config(args.config)
    os.makedirs(args.out, exist_ok=True)
    env = _current_env()
    report: dict = {}
    sel = select(root, cfg, args.baseline, current_env=env)
    rc, manifest = run_selection(sel, root, os.path.join(args.out, "tia"))
    if args.full_junit:
        full_junit, full_wall = args.full_junit, None
    else:
        full_junit, full_wall = _run_full(root, os.path.join(args.out, "full"))
    report["same_revision"] = compare_runs(manifest, full_junit)
    report["same_revision"]["full_wall_seconds"] = round(full_wall, 1) if full_wall else None
    if args.mutants:
        report["mutants"] = run_mutants(
            root, cfg, args.baseline, args.out, args.mutants, args.seed, env
        )
        report["mutants_missed"] = sum(1 for r in report["mutants"] if r["missed_failures"])
    path = os.path.join(args.out, "calibration.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1)
    print(json.dumps({k: v for k, v in report.items() if k != "mutants"}, indent=1))
    print(f"calibration report: {path}")
    missed = report["same_revision"]["missed_failures"] or report.get("mutants_missed")
    return 1 if missed else 0
