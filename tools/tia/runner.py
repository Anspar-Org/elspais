"""Run a selection with pytest and complete its manifest with the outcome."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

from .selector import Selection


def junit_summary(path: str) -> dict:
    """Counts and per-test outcomes from a JUnit XML file (xunit1 or xunit2)."""
    if not os.path.isfile(path):
        return {"present": False}
    root = ET.parse(path).getroot()
    cases = {}
    for tc in root.iter("testcase"):
        file = tc.get("file")
        classname = tc.get("classname", "")
        name = tc.get("name", "")
        outcome = "passed"
        for child in tc:
            if child.tag in ("failure", "error"):
                outcome = "failed" if child.tag == "failure" else "error"
            elif child.tag == "skipped":
                outcome = "skipped" if outcome == "passed" else outcome
        key = junit_key(file, classname, name)
        cases[key] = {"outcome": outcome, "time": float(tc.get("time") or 0.0)}
    counts: dict[str, int] = {}
    for c in cases.values():
        counts[c["outcome"]] = counts.get(c["outcome"], 0) + 1
    return {"present": True, "tests": len(cases), "counts": counts, "cases": cases}


def junit_key(file: str | None, classname: str, name: str) -> str:
    """A stable key from JUnit fields: `<classname>::<name>`.

    xunit1 records `classname` as the dotted module path plus class
    (tests.graph.test_x.TestY); we keep it verbatim so two JUnit files from
    the same suite compare key for key.
    """
    return f"{classname}::{name}"


def worker_count(root: str) -> int:
    try:
        out = subprocess.run(
            [os.path.join(root, ".githooks", "test-workers")],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        return max(1, int(out))
    except (OSError, ValueError, subprocess.CalledProcessError):
        return 1


def pytest_command(sel: Selection, root: str, out_dir: str, extra: list[str]) -> list[str] | None:
    """The pytest invocation for a selection; None when there is nothing to run."""
    junit = os.path.join(out_dir, "junit.xml")
    base = [
        sys.executable,
        "-m",
        "pytest",
        "--no-cov",
        "-q",
        "--tb=short",
        f"--junitxml={junit}",
        "-o",
        "junit_family=xunit1",
        "-p",
        "no:cacheprovider",
    ]
    workers = worker_count(root)
    if sel.mode == "full":
        return base + ["tests/", "-n", str(workers), "--dist", "loadfile"] + extra
    if not sel.run_files:
        return None
    args = list(sel.run_files)
    if sel.granularity == "test":
        spec = os.path.join(out_dir, "selection.json")
        with open(spec, "w", encoding="utf-8") as fh:
            json.dump({"nodeids": sorted(sel.tests), "new_files": sel.whole_test_files}, fh)
        base += ["-p", "tools.tia.pytest_select"]
    # xdist only pays off once there is enough work to spread; with loadfile a
    # file is the unit of distribution.
    par = (
        ["-n", str(workers), "--dist", "loadfile"]
        if len(sel.run_files) >= 2 * workers and workers > 1
        else ["-n", "0"]
    )
    return base + args + par + extra


def run_selection(
    sel: Selection, root: str, out_dir: str, extra: list[str] | None = None
) -> tuple[int, dict]:
    os.makedirs(out_dir, exist_ok=True)
    junit = os.path.join(out_dir, "junit.xml")
    if os.path.exists(junit):
        os.remove(junit)
    manifest = sel.manifest()
    cmd = pytest_command(sel, root, out_dir, list(extra or []))
    env = dict(os.environ)
    env["PYTHONPATH"] = root + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["TIA_SELECT_FILE"] = os.path.join(out_dir, "selection.json")
    env.pop("TIA_RECORD_DIR", None)
    t0 = time.time()
    if cmd is None:
        rc = 0
        print("tia: no tests are affected by this change; nothing to run.")
    else:
        print("tia: " + " ".join(cmd[:12]) + (" ..." if len(cmd) > 12 else ""), flush=True)
        rc = subprocess.run(cmd, cwd=root, env=env).returncode
        if rc == 5 and sel.mode != "full":
            # every collected item was deselected (e.g. a changed e2e-only module)
            rc = 0
    elapsed = time.time() - t0
    js = junit_summary(junit)
    manifest["run"] = {
        "command": cmd,
        "exit_code": rc,
        "elapsed_seconds": round(elapsed, 2),
        "executed_tests": js.get("tests", 0),
        "outcomes": js.get("counts", {}),
        "junit": junit if js.get("present") else None,
    }
    write_manifest(manifest, out_dir)
    return rc, manifest


def write_manifest(manifest: dict, out_dir: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "manifest.json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=1)
    os.replace(tmp, path)
    return path


def nodeid_to_junit_key(nodeid: str) -> str:
    """The key `junit_summary` gives the test pytest calls `nodeid`."""
    parts = nodeid.split("::")
    module = parts[0][:-3] if parts[0].endswith(".py") else parts[0]
    classname = ".".join([module.replace("/", ".")] + parts[1:-1])
    return f"{classname}::{parts[-1]}"
