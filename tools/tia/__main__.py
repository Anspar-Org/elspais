"""Command line: python -m tools.tia <command>.

    baseline build   merge a recorded run into the baseline and publish it
    baseline show    validate a baseline and print what it holds
    baseline path    print where the baseline lives
    baseline fetch   install the baseline a full CI run of main published,
                     unless this worktree's own baseline is usable
    select           compute the selection and write its manifest
    run              select, then run the selected tests with pytest
    compare          compare a TIA run with a full run of the same revision
    calibrate        run TIA and the full suite on this revision and compare

Environment: ELSPAIS_TIA_BASELINE (the baseline directory; default
.results/tia/baseline in this worktree's root),
TIA_FULL=1 (bypass selection: run the full suite).
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from .baseline import BASELINE_ENV, BaselineError, baseline_dir, build_baseline, load_baseline
from .config import load_config
from .gitio import repo_root
from .selector import select

DEFAULT_OUT = os.path.join(".results", "tia", "run")


def _current_env() -> dict:
    from .recorder import environment_fingerprint

    return environment_fingerprint()


def _print_summary(m: dict, out=sys.stdout) -> None:
    w = out.write
    b = m["baseline"]
    w(f"TIA [{m['selection_mode']}] suite={m['suite']} granularity={m['granularity']}\n")
    if b.get("usable"):
        dirty = f", {len(b['dirty_files'])} dirty file(s)" if b.get("dirty_files") else ""
        w(
            f"  baseline: commit {str(b.get('commit'))[:12]} tree {str(b.get('tree'))[:12]}{dirty}"
            f" ({b.get('tests')} tests)\n"
        )
    else:
        w(f"  baseline: unusable ({b.get('path')})\n")
    files = m["change"]["files"]
    w(f"  changed files: {len(files)}\n")
    for f in files[:40]:
        flag = f["status"][0].upper()
        w(f"    {flag} {f['path']} [{f['category']}] -> {f['tests_selected']} test(s)\n")
        for r in f["regions"][:6]:
            w(f"        region: {r}\n")
        for n in f["notes"][:3]:
            if not n.startswith("hunk"):
                w(f"        note: {n}\n")
    if len(files) > 40:
        w(f"    ... {len(files) - 40} more\n")
    for fb in m["fallbacks"]:
        where = f" [{fb['path']}]" if fb.get("path") else ""
        w(f"  FALLBACK {fb['kind']}{where}: {fb['detail']}\n")
    for warn in m["warnings"][:5]:
        w(f"  warning: {warn.strip().splitlines()[0]}\n")
    total, chosen = m["total_tests"], m["selected_tests"]
    pct = (100.0 * (total - chosen) / total) if total else 0.0
    if m["selection_mode"] == "full":
        skipped, pct = 0, 0.0
    else:
        skipped = total - chosen
    w(f"  tests: {chosen} selected of {total} in the baseline ({skipped} skipped, {pct:.1f}%)")
    if m.get("new_test_files"):
        w(f", plus all tests in {len(m['new_test_files'])} new test file(s)")
    w("\n")
    if "run" in m:
        r = m["run"]
        w(f"  run: exit {r['exit_code']} in {r['elapsed_seconds']}s, ")
        w(f"{r['executed_tests']} executed {r['outcomes']}\n")


def cmd_baseline(args) -> int:
    root = repo_root()
    if args.action == "path":
        print(args.baseline)
        return 0
    if args.action == "fetch":
        from .fetch import FetchError, fetch_baseline

        try:
            print(
                "tia: "
                + fetch_baseline(
                    root,
                    args.baseline,
                    current_env=_current_env(),
                    max_age_days=load_config(args.config).max_baseline_age_days,
                    force=args.force,
                )
            )
        except FetchError as exc:
            print(f"tia: no baseline fetched: {exc}", file=sys.stderr)
            return 1
        return 0
    if args.action == "build":
        dest = args.baseline
        try:
            m = build_baseline(
                args.run_dir, dest, args.coverage, only_if_passed=args.only_if_passed
            )
        except BaselineError as exc:
            print(f"tia: cannot build a baseline: {exc}", file=sys.stderr)
            return 2
        bad = [n for n, t in m["tests"].items() if t["outcome"] != "passed"]
        print(
            f"tia: baseline of {len(m['tests'])} tests at tree {m['identity']['tree']} "
            f"(commit {m['identity']['commit']}, {len(m['identity']['dirty'])} dirty file(s), "
            f"{len(bad)} not passing) -> {dest}"
        )
        if m["errors"]:
            print(
                f"tia: WARNING: {len(m['errors'])} recorder error(s); "
                "this baseline will be refused",
                file=sys.stderr,
            )
        if not m["identity"]["consistent"]:
            print(
                "tia: WARNING: the tree changed during the run; this baseline will be refused",
                file=sys.stderr,
            )
        return 0
    cfg = load_config(args.config)
    try:
        b = load_baseline(
            args.baseline,
            root,
            current_env=_current_env(),
            on_environment_change="warn",
            max_age_days=cfg.max_baseline_age_days,
        )
    except BaselineError as exc:
        print(f"tia: baseline unusable -> {exc.kind}: {exc.detail}")
        return 1
    m = b.manifest
    print(
        json.dumps(
            {
                "identity": {
                    k: (v if k != "dirty" else sorted(v)) for k, v in m["identity"].items()
                },
                "tests": len(m["tests"]),
                "outcomes": {
                    o: sum(1 for t in m["tests"].values() if t["outcome"] == o)
                    for o in sorted({t["outcome"] for t in m["tests"].values()})
                },
                "coverage_contexts": m["coverage"]["contexts"],
                "files_read_as_data": len(m["data_reads"]),
                "opaque_spawning_tests": sum(1 for t in m["tests"].values() if t.get("spawns")),
                "warnings": b.warnings,
            },
            indent=1,
        )
    )
    return 0


def _select(args):
    root = repo_root()
    cfg = load_config(args.config)
    if args.granularity:
        cfg.granularity = args.granularity
    force = None
    if args.full:
        force = "--full given"
    elif os.environ.get("TIA_FULL") == "1":
        force = "TIA_FULL=1"
    return root, select(root, cfg, args.baseline, force_full=force, current_env=_current_env())


def cmd_select(args) -> int:
    from .runner import write_manifest

    _root, sel = _select(args)
    m = sel.manifest()
    path = write_manifest(m, args.out)
    _print_summary(m)
    print(f"  manifest: {path}")
    if args.list:
        for target in m["pytest_targets"]:
            print(target)
    return 0


def cmd_run(args) -> int:
    from .runner import run_selection

    root, sel = _select(args)
    _print_summary(sel.manifest())
    rc, m = run_selection(sel, root, args.out, args.pytest_args)
    _print_summary(m)
    print(f"  manifest: {os.path.join(args.out, 'manifest.json')}")
    return rc


def cmd_compare(args) -> int:
    from .calibrate import compare_runs

    report = compare_runs(args.tia_manifest, args.full_junit)
    print(json.dumps(report, indent=1))
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=1)
    return 1 if report["missed_failures"] else 0


def cmd_calibrate(args) -> int:
    from .calibrate import calibrate

    return calibrate(args)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="python -m tools.tia",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument(
            "--baseline",
            default=None,
            help=f"baseline directory (default ${BASELINE_ENV}, else this worktree's own)",
        )
        sp.add_argument("--config", default=None, help="rule file (default tools/tia/config.toml)")

    b = sub.add_parser("baseline", help="build or inspect a baseline")
    b.add_argument("action", choices=["build", "show", "path", "fetch"])
    b.add_argument("--run-dir", help="directory holding the recorder's tia-shard-*.json")
    b.add_argument("--coverage", help="the run's .coverage file (default <run-dir>/.coverage)")
    b.add_argument(
        "--only-if-passed",
        action="store_true",
        help="publish nothing unless the run passed outright",
    )
    b.add_argument(
        "--force",
        action="store_true",
        help="fetch: replace this worktree's baseline even where it is usable",
    )
    common(b)
    b.set_defaults(func=cmd_baseline)

    for name, fn, helptext in (
        ("select", cmd_select, "compute the selection"),
        ("run", cmd_run, "select and run the impacted tests"),
    ):
        s = sub.add_parser(name, help=helptext)
        common(s)
        s.add_argument("--full", action="store_true", help="bypass TIA: run the full suite")
        s.add_argument("--granularity", choices=["file", "test"])
        s.add_argument("--out", default=os.environ.get("TIA_OUT", DEFAULT_OUT))
        if name == "select":
            s.add_argument("--list", action="store_true", help="print the pytest targets")
        else:
            s.add_argument(
                "pytest_args", nargs=argparse.REMAINDER, help="extra pytest arguments, after --"
            )
        s.set_defaults(func=fn)

    c = sub.add_parser("compare", help="compare a TIA run with a full run of the same revision")
    c.add_argument("--tia-manifest", required=True)
    c.add_argument("--full-junit", required=True)
    c.add_argument("--out")
    c.set_defaults(func=cmd_compare)

    k = sub.add_parser("calibrate", help="run TIA and the full suite here and compare")
    common(k)
    k.add_argument("--out", default=os.path.join(".results", "tia", "calibration"))
    k.add_argument("--full-junit", help="reuse the JUnit of a full run of this exact revision")
    k.add_argument(
        "--mutants",
        type=int,
        default=0,
        help="also probe N seeded single-function faults (expensive)",
    )
    k.add_argument("--seed", type=int, default=0)
    k.set_defaults(func=cmd_calibrate)

    args = p.parse_args(argv)
    if "TIA_BASELINE" in os.environ:
        print(
            f"tia: TIA_BASELINE is not read; name the baseline directory with {BASELINE_ENV}",
            file=sys.stderr,
        )
        return 2
    if getattr(args, "pytest_args", None) and args.pytest_args[0] == "--":
        args.pytest_args = args.pytest_args[1:]
    if hasattr(args, "baseline") and not args.baseline:
        args.baseline = baseline_dir(repo_root())
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
