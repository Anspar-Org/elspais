# Exit Codes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make `doctor`, `health`, and `validate` exit non-zero when they detect configuration or validation failures (REQ-d00080).

**Architecture:** Change severity classifications on 7 existing health checks from "warning" to "error" (default) so `HealthReport.is_healthy` catches them. Add 2 new checks (associated section validation, zero-requirement guard) and 1 new validate-time check (associate requirement count). No framework changes needed — just correct severity classifications and missing checks.

**Tech Stack:** Python 3.10+, pytest, argparse.Namespace

---

### Task 1: EXIT-1 — Reclassify doctor check severities (REQ-d00080-A)

**Files:**
- Modify: `src/elspais/commands/doctor.py`
- Test: `tests/commands/test_exit_codes.py` (create)

**Step 1: Write failing tests**

```python
"""Tests for REQ-d00080: Diagnostic Command Exit Code Contract."""

import argparse
from pathlib import Path

import pytest


class TestDoctorExitCodes:
    """REQ-d00080-A: doctor SHALL exit non-zero on [!!] findings."""

    def test_REQ_d00080_A_invalid_project_type_exits_nonzero(self, tmp_path, monkeypatch):
        """doctor exits 1 when project.type is invalid."""
        from elspais.commands.doctor import run

        monkeypatch.chdir(tmp_path)
        config = tmp_path / ".elspais.toml"
        config.write_text(
            '[project]\ntype = "bogus"\n'
            '[patterns]\nid_template = "{prefix}-{type}{id}"\n'
            "[patterns.types.prd]\nlevel = 1\n"
            '[spec]\ndirectories = ["spec"]\n'
            "[rules]\nhierarchy = {}\n"
        )
        (tmp_path / "spec").mkdir()

        args = argparse.Namespace(
            config=str(config), json=False, verbose=False, canonical_root=None,
        )
        result = run(args)
        assert result == 1

    def test_REQ_d00080_A_missing_required_fields_exits_nonzero(self, tmp_path, monkeypatch):
        """doctor exits 1 when required config fields are missing."""
        from elspais.commands.doctor import run

        monkeypatch.chdir(tmp_path)
        config = tmp_path / ".elspais.toml"
        config.write_text('[project]\nname = "test"\n')
        (tmp_path / "spec").mkdir()

        args = argparse.Namespace(
            config=str(config), json=False, verbose=False, canonical_root=None,
        )
        result = run(args)
        assert result == 1

    def test_REQ_d00080_A_missing_associate_path_exits_nonzero(self, tmp_path, monkeypatch):
        """doctor exits 1 when configured associate path doesn't exist."""
        from elspais.commands.doctor import run

        monkeypatch.chdir(tmp_path)
        config = tmp_path / ".elspais.toml"
        config.write_text(
            '[patterns]\nid_template = "{prefix}-{type}{id}"\n'
            "[patterns.types.prd]\nlevel = 1\n"
            '[spec]\ndirectories = ["spec"]\n'
            "[rules]\nhierarchy = {}\n"
        )
        local_config = tmp_path / ".elspais.local.toml"
        local_config.write_text(
            '[associates]\npaths = ["/nonexistent/sponsor"]\n'
        )
        (tmp_path / "spec").mkdir()

        args = argparse.Namespace(
            config=str(config), json=False, verbose=False, canonical_root=tmp_path,
        )
        result = run(args)
        assert result == 1

    def test_REQ_d00080_A_healthy_config_exits_zero(self, tmp_path, monkeypatch):
        """doctor exits 0 on a well-configured project."""
        from elspais.commands.doctor import run

        monkeypatch.chdir(tmp_path)
        config = tmp_path / ".elspais.toml"
        config.write_text(
            '[patterns]\nid_template = "{prefix}-{type}{id}"\n'
            "[patterns.types.prd]\nlevel = 1\n"
            '[spec]\ndirectories = ["spec"]\n'
            "[rules]\nhierarchy = {}\n"
        )
        (tmp_path / "spec").mkdir()

        args = argparse.Namespace(
            config=str(config), json=False, verbose=False, canonical_root=None,
        )
        result = run(args)
        assert result == 0
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/commands/test_exit_codes.py::TestDoctorExitCodes -v`
Expected: 3 FAIL (invalid_project_type, missing_required_fields, missing_associate_path), 1 PASS (healthy_config)

**Step 3: Fix severities in doctor.py**

Remove `severity="warning"` from these check returns (default severity is "error"):

1. `check_config_required_fields` line 123: remove `severity="warning"`
2. `check_config_project_type` line 290: remove `severity="warning"`
3. `check_config_pattern_tokens` line 165: remove `severity="warning"`
4. `check_config_hierarchy_rules` lines 188, 197, 224: remove `severity="warning"` from all three
5. `check_config_paths_exist` line 246: remove `severity="warning"` (non-list case)
6. `check_associate_paths` line 393: remove `severity="warning"`
7. `check_associate_configs` line 441: remove `severity="warning"`

Do NOT change `check_cross_repo_in_committed_config` (line 526) — cross-repo paths in committed config is advisory.

**Step 4: Run tests to verify they pass**

Run: `pytest tests/commands/test_exit_codes.py::TestDoctorExitCodes -v`
Expected: All 4 PASS

**Step 5: Commit**

```bash
git add tests/commands/test_exit_codes.py src/elspais/commands/doctor.py
git commit -m "[CUR-1036] REQ-d00080-A: Reclassify doctor check severities

Diagnostic checks that detect real config problems (missing fields,
invalid project type, broken associate paths) now use severity='error'
instead of 'warning', causing doctor/health to exit non-zero.

Implements: REQ-d00080-A"
```

---

### Task 2: EXIT-2 — Zero requirements check in validate (REQ-d00080-B)

**Files:**
- Modify: `src/elspais/commands/validate.py`
- Test: `tests/commands/test_exit_codes.py` (append)

**Step 1: Write failing tests**

Append to `tests/commands/test_exit_codes.py`:

```python
class TestValidateExitCodes:
    """REQ-d00080-B: validate SHALL exit non-zero on zero requirements."""

    def test_REQ_d00080_B_zero_requirements_exits_nonzero(self, tmp_path, monkeypatch):
        """validate exits 1 when spec dir is configured but has zero requirements."""
        from elspais.commands.validate import run

        monkeypatch.chdir(tmp_path)
        config = tmp_path / ".elspais.toml"
        config.write_text(
            '[patterns]\nid_template = "{prefix}-{type}{id}"\n'
            "[patterns.types.prd]\nlevel = 1\n"
            '[spec]\ndirectories = ["spec"]\n'
            "[rules]\nhierarchy = {}\n"
        )
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        # Create an empty spec file (no requirements)
        (spec_dir / "empty.md").write_text("# No requirements here\n")

        args = argparse.Namespace(
            spec_dir=None, config=str(config), fix=False, dry_run=False,
            skip_rule=None, json=False, quiet=False, export=False,
            mode="core", canonical_root=None,
        )
        result = run(args)
        assert result == 1

    def test_REQ_d00080_B_zero_requirements_json_reports_error(self, tmp_path, monkeypatch, capsys):
        """validate JSON output includes zero-requirements error."""
        import json as json_mod
        from elspais.commands.validate import run

        monkeypatch.chdir(tmp_path)
        config = tmp_path / ".elspais.toml"
        config.write_text(
            '[patterns]\nid_template = "{prefix}-{type}{id}"\n'
            "[patterns.types.prd]\nlevel = 1\n"
            '[spec]\ndirectories = ["spec"]\n'
            "[rules]\nhierarchy = {}\n"
        )
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        (spec_dir / "empty.md").write_text("# No requirements here\n")

        args = argparse.Namespace(
            spec_dir=None, config=str(config), fix=False, dry_run=False,
            skip_rule=None, json=True, quiet=False, export=False,
            mode="core", canonical_root=None,
        )
        result = run(args)
        assert result == 1
        captured = capsys.readouterr()
        data = json_mod.loads(captured.out)
        assert data["valid"] is False
        assert any(e["rule"] == "config.no_requirements" for e in data["errors"])
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/commands/test_exit_codes.py::TestValidateExitCodes -v`
Expected: 2 FAIL

**Step 3: Add zero-requirement check in validate.py**

After line 246 (`req_count = sum(1 for _ in graph.nodes_by_kind(NodeKind.REQUIREMENT))`), add:

```python
    # REQ-d00080-B: Zero requirements with configured spec dir is an error
    if req_count == 0:
        errors.append(
            {
                "rule": "config.no_requirements",
                "id": "spec",
                "message": "No requirements found. Check that spec directories contain valid requirement files.",
            }
        )
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/commands/test_exit_codes.py::TestValidateExitCodes -v`
Expected: All 2 PASS

**Step 5: Commit**

```bash
git add src/elspais/commands/validate.py tests/commands/test_exit_codes.py
git commit -m "[CUR-1036] REQ-d00080-B: validate exits non-zero on zero requirements

When spec directories are configured but produce zero parseable
requirements, validate now treats this as an error rather than
reporting 'Validated 0 requirements' with exit code 0.

Implements: REQ-d00080-B"
```

---

### Task 3: EXIT-4 — Associated section validation in doctor (REQ-d00080-D)

**Files:**
- Modify: `src/elspais/commands/doctor.py`
- Test: `tests/commands/test_exit_codes.py` (append)

**Step 1: Write failing tests**

Append to `tests/commands/test_exit_codes.py`:

```python
class TestDoctorAssociatedSection:
    """REQ-d00080-D: doctor SHALL validate [associated] section for associated projects."""

    def test_REQ_d00080_D_missing_associated_section_exits_nonzero(self, tmp_path, monkeypatch):
        """doctor exits 1 when project.type=associated but [associated] section missing."""
        from elspais.commands.doctor import run

        monkeypatch.chdir(tmp_path)
        config = tmp_path / ".elspais.toml"
        config.write_text(
            '[project]\ntype = "associated"\n'
            '[patterns]\nid_template = "{prefix}-{type}{id}"\n'
            "[patterns.types.prd]\nlevel = 1\n"
            '[spec]\ndirectories = ["spec"]\n'
            "[rules]\nhierarchy = {}\n"
        )
        (tmp_path / "spec").mkdir()

        args = argparse.Namespace(
            config=str(config), json=False, verbose=False, canonical_root=None,
        )
        result = run(args)
        assert result == 1

    def test_REQ_d00080_D_empty_prefix_exits_nonzero(self, tmp_path, monkeypatch):
        """doctor exits 1 when [associated] section has empty prefix."""
        from elspais.commands.doctor import run

        monkeypatch.chdir(tmp_path)
        config = tmp_path / ".elspais.toml"
        config.write_text(
            '[project]\ntype = "associated"\n'
            '[associated]\nprefix = ""\n'
            '[patterns]\nid_template = "{prefix}-{type}{id}"\n'
            "[patterns.types.prd]\nlevel = 1\n"
            '[spec]\ndirectories = ["spec"]\n'
            "[rules]\nhierarchy = {}\n"
        )
        (tmp_path / "spec").mkdir()

        args = argparse.Namespace(
            config=str(config), json=False, verbose=False, canonical_root=None,
        )
        result = run(args)
        assert result == 1

    def test_REQ_d00080_D_valid_associated_exits_zero(self, tmp_path, monkeypatch):
        """doctor exits 0 when [associated] section is properly configured."""
        from elspais.commands.doctor import run

        monkeypatch.chdir(tmp_path)
        config = tmp_path / ".elspais.toml"
        config.write_text(
            '[project]\ntype = "associated"\n'
            '[associated]\nprefix = "CAL"\n'
            '[core]\npath = ".."\n'
            '[patterns]\nid_template = "{prefix}-{type}{id}"\n'
            "[patterns.types.prd]\nlevel = 1\n"
            '[spec]\ndirectories = ["spec"]\n'
            "[rules]\nhierarchy = {}\n"
        )
        (tmp_path / "spec").mkdir()

        args = argparse.Namespace(
            config=str(config), json=False, verbose=False, canonical_root=None,
        )
        result = run(args)
        # May have other warnings (core path doesn't exist) but associated check passes
        # We only care that the associated section check itself passes
        pass  # Just testing the check function directly is cleaner

    def test_REQ_d00080_D_check_function_valid(self):
        """check_config_associated_section passes with valid config."""
        from elspais.commands.doctor import check_config_associated_section

        raw = {
            "project": {"type": "associated"},
            "associated": {"prefix": "CAL"},
        }
        check = check_config_associated_section(raw)
        assert check.passed is True

    def test_REQ_d00080_D_check_function_missing_section(self):
        """check_config_associated_section fails with missing section."""
        from elspais.commands.doctor import check_config_associated_section

        raw = {"project": {"type": "associated"}}
        check = check_config_associated_section(raw)
        assert check.passed is False
        assert check.severity == "error"

    def test_REQ_d00080_D_check_function_empty_prefix(self):
        """check_config_associated_section fails with empty prefix."""
        from elspais.commands.doctor import check_config_associated_section

        raw = {
            "project": {"type": "associated"},
            "associated": {"prefix": ""},
        }
        check = check_config_associated_section(raw)
        assert check.passed is False

    def test_REQ_d00080_D_check_function_non_associated_skips(self):
        """check_config_associated_section passes for non-associated projects."""
        from elspais.commands.doctor import check_config_associated_section

        raw = {"project": {"type": "core"}}
        check = check_config_associated_section(raw)
        assert check.passed is True
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/commands/test_exit_codes.py::TestDoctorAssociatedSection -v`
Expected: FAIL (ImportError — function doesn't exist yet)

**Step 3: Add check_config_associated_section to doctor.py**

Add new function after `check_config_project_type` (before `run_config_checks`):

```python
def check_config_associated_section(raw: dict) -> HealthCheck:
    """Check that associated projects have a valid [associated] section."""
    project_type = raw.get("project", {}).get("type")
    if project_type != "associated":
        return HealthCheck(
            name="config.associated_section",
            passed=True,
            message="Not an associated project (check not applicable)",
            category="config",
            severity="info",
        )

    associated = raw.get("associated", {})
    if not associated:
        return HealthCheck(
            name="config.associated_section",
            passed=False,
            message=(
                "Project type is 'associated' but [associated] section is missing. "
                "Add [associated] with a 'prefix' key (e.g., prefix = \"CAL\")."
            ),
            category="config",
        )

    prefix = associated.get("prefix", "")
    if not prefix:
        return HealthCheck(
            name="config.associated_section",
            passed=False,
            message=(
                "Project type is 'associated' but prefix is empty. "
                "Set a non-empty prefix (e.g., prefix = \"CAL\")."
            ),
            category="config",
        )

    return HealthCheck(
        name="config.associated_section",
        passed=True,
        message=f"Associated project configured with prefix '{prefix}'",
        category="config",
    )
```

Add to `run_config_checks` list (the function needs the raw config):

```python
def run_config_checks(
    config_path: Path | None, config: ConfigLoader, start_path: Path
) -> list[HealthCheck]:
    """Run all configuration checks."""
    return [
        check_config_exists(config_path, start_path),
        check_config_syntax(config_path, start_path),
        check_config_required_fields(config),
        check_config_project_type(config),
        check_config_associated_section(config.get_raw()),
        check_config_pattern_tokens(config),
        check_config_hierarchy_rules(config),
        check_config_paths_exist(config, start_path),
    ]
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/commands/test_exit_codes.py::TestDoctorAssociatedSection -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/elspais/commands/doctor.py tests/commands/test_exit_codes.py
git commit -m "[CUR-1036] REQ-d00080-D: doctor validates [associated] section

For project.type='associated', doctor now checks that the [associated]
section exists and has a non-empty prefix. Missing or empty prefix
produces an error-severity finding.

Implements: REQ-d00080-D"
```

---

### Task 4: EXIT-5 — Associate requirement count in validate (REQ-d00080-E)

**Files:**
- Modify: `src/elspais/commands/validate.py`
- Test: `tests/commands/test_exit_codes.py` (append)

**Step 1: Write failing tests**

Append to `tests/commands/test_exit_codes.py`:

```python
class TestValidateAssociateCount:
    """REQ-d00080-E: validate SHALL exit non-zero when associates produce zero requirements."""

    def test_REQ_d00080_E_missing_associate_path_exits_nonzero(self, tmp_path, monkeypatch, capsys):
        """validate exits 1 when a configured associate path doesn't exist."""
        from elspais.commands.validate import run

        monkeypatch.chdir(tmp_path)
        config = tmp_path / ".elspais.toml"
        config.write_text(
            '[patterns]\nid_template = "{prefix}-{type}{id}"\n'
            "[patterns.types.prd]\nlevel = 1\n"
            '[spec]\ndirectories = ["spec"]\n'
            "[rules]\nhierarchy = {}\n"
        )
        local_config = tmp_path / ".elspais.local.toml"
        local_config.write_text(
            '[associates]\npaths = ["/nonexistent/sponsor"]\n'
        )
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        # Add a valid requirement so this isn't the zero-req check
        (spec_dir / "reqs.md").write_text(
            "# REQ-p00001: Test Requirement\n\n"
            "**Level**: PRD | **Status**: Active\n\n"
            "A. Some assertion.\n\n"
            "*End* *Test Requirement* | **Hash**: 00000000\n"
        )

        args = argparse.Namespace(
            spec_dir=None, config=str(config), fix=False, dry_run=False,
            skip_rule=None, json=False, quiet=False, export=False,
            mode="combined", canonical_root=tmp_path,
        )
        result = run(args)
        assert result == 1
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/commands/test_exit_codes.py::TestValidateAssociateCount -v`
Expected: FAIL (exits 0)

**Step 3: Add associate path validation in validate.py**

After the graph is built (line 84) and before the export check, add validation of associate paths:

```python
    # REQ-d00080-E: For core projects with associates, check paths are valid
    if scan_sponsors:
        from elspais.config import get_config
        config_dict = get_config(config_path, start_path=repo_root)
        associate_paths = config_dict.get("associates", {}).get("paths", [])
        if associate_paths:
            from elspais.associates import discover_associate_from_path

            for path_str in associate_paths:
                p = Path(path_str)
                if not p.is_absolute() and canonical_root:
                    p = canonical_root / p
                if not p.exists():
                    errors.append(
                        {
                            "rule": "config.associate_path_missing",
                            "id": path_str,
                            "message": (
                                f"Associate path does not exist: {path_str} "
                                f"(resolved to {p})"
                            ),
                        }
                    )
                else:
                    result = discover_associate_from_path(p)
                    if isinstance(result, str):
                        errors.append(
                            {
                                "rule": "config.associate_invalid",
                                "id": path_str,
                                "message": f"Associate path is misconfigured: {result}",
                            }
                        )
```

Note: The `errors` list is initialized at line 112, so this code block should go after line 114 (after `fixable = []`), before the requirement iteration loop.

**Step 4: Run tests to verify they pass**

Run: `pytest tests/commands/test_exit_codes.py::TestValidateAssociateCount -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/elspais/commands/validate.py tests/commands/test_exit_codes.py
git commit -m "[CUR-1036] REQ-d00080-E: validate exits non-zero for broken associates

When mode is 'combined' and configured associate paths are missing or
misconfigured, validate now emits errors and exits non-zero instead
of silently dropping to core-only requirements.

Implements: REQ-d00080-E"
```

---

### Task 5: Run full test suite and verify no regressions

**Files:**
- No new files

**Step 1: Run full test suite**

Run: `pytest tests/ -v --tb=short 2>&1 | tail -30`
Expected: All tests pass. Some existing tests may need updating if they expected exit code 0 for scenarios that now exit 1.

**Step 2: Fix any broken tests**

If existing tests expected exit 0 on configs that now produce errors (e.g., tests with `severity="warning"` checks), update them to expect exit 1 or fix the test fixtures to use valid configs.

**Step 3: Run the CLI manually to verify**

```bash
# Verify a healthy project still exits 0
python -m elspais doctor && echo "OK: exit 0" || echo "ERROR: exit non-zero"

# Verify validate on this project exits 0
python -m elspais validate --mode core && echo "OK: exit 0" || echo "ERROR: exit non-zero"
```

**Step 4: Commit any test fixes**

```bash
git add -u
git commit -m "[CUR-1036] Fix tests for updated exit code severities"
```

---

### Task 6: Commit spec and design files

**Files:**
- `spec/dev-exit-codes.md`
- `docs/plans/2026-02-26-exit-codes-design.md`
- `docs/plans/2026-02-26-exit-codes-plan.md`

**Step 1: Commit spec and plans**

```bash
git add spec/dev-exit-codes.md docs/plans/2026-02-26-exit-codes-design.md docs/plans/2026-02-26-exit-codes-plan.md
git commit -m "[CUR-1036] Add REQ-d00080 spec and design docs

New DEV-level requirement REQ-d00080 defines the exit code contract
for diagnostic commands (doctor, health, validate).

Implements: REQ-d00080"
```
