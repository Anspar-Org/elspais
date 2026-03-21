# Checks & Gaps Report Unification Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename `health` to `checks`, unify text/markdown rendering via a shared intermediate representation, extract gap listings into independent composable report sections, and implement bitfield exit codes.

**Architecture:** A `_ReportData` dataclass is built once from `HealthReport`, then consumed by thin text/markdown renderers. Gap listings (`uncovered`, `untested`, `unvalidated`, `failing`) move from health.py to a new `gaps.py` module as independent composable sections. A `gaps` meta-section expands to all four. The CLI command is renamed from `health` to `checks`. Exit codes use bitfield composition: each section gets a bit, composed reports OR them together.

**Tech Stack:** Python 3.10+, dataclasses, argparse, tyro, pytest

---

## Exit Code Design

Bitfield allocation — each section owns one bit:

| Bit | Value | Section | Semantic |
|-----|-------|---------|----------|
| 0 | 1 | checks | any enabled checks failed |
| 1 | 2 | summary | (reserved, currently always 0) |
| 2 | 4 | trace | (reserved, currently always 0) |
| 3 | 8 | changed | (reserved, currently always 0) |
| 4 | 16 | gaps/uncovered/untested/unvalidated/failing | (reserved, currently always 0) |

Standalone commands return their own bit. Composed reports `|` (OR) all section exit codes together. Today only `checks` ever returns non-zero. The `--lenient` flag suppresses the checks bit (clears bit 0).

Defined as constants in `report.py`:

```python
EXIT_BIT: dict[str, int] = {
    "checks": 1,
    "summary": 2,
    "trace": 4,
    "changed": 8,
    "uncovered": 16,
    "untested": 16,
    "unvalidated": 16,
    "failing": 16,
    "gaps": 16,
}
```

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `src/elspais/commands/health.py` | Modify | Replace `_print_text_report` + `_render_markdown` with `_build_report_data` + `_render_text` + `_render_markdown`; remove `_print_gap_listing` and gap flag handling from `run()`; update hint text from `health` to `checks` |
| `src/elspais/commands/gaps.py` | Create | Gap section data collection + rendering + `render_section()` for each gap type + standalone `run()`. Imports `_resolve_exclude_status` from `health.py` (no duplication). |
| `src/elspais/commands/args.py` | Modify | Rename `HealthArgs` to `ChecksArgs`; remove gap flags; add `GapsArgs`, `UncoveredArgs`, `UntestedArgs`, `UnvalidatedArgs`, `FailingArgs` |
| `src/elspais/commands/report.py` | Modify | Rename `"health"` to `"checks"` in `COMPOSABLE_SECTIONS`; register new gap sections; add `EXIT_BIT` constants; change composition from `max()` to `\|` (OR); update `graph_sections` to include gap sections |
| `src/elspais/cli.py` | Modify | Rename `HealthArgs` import to `ChecksArgs`; update `_CMD_MAP` and dispatch from `"health"` to `"checks"`; register gap command Args in `Command` union; add gap dispatch |
| `tests/commands/test_health_report_data.py` | Create | Tests for `_build_report_data`, `_render_text`, `_render_markdown` |
| `tests/commands/test_gaps.py` | Create | Tests for gap sections: data collection, text/markdown rendering, composability |
| `tests/commands/test_health_finding.py` | Modify | Update imports (`_render_markdown` signature change); update hint text assertions from `health` to `checks` |
| `tests/commands/test_health_detail_flags.py` | Modify | Update markdown assertions (checklist instead of tables); update CLI parsing test from `"health"` to `"checks"` |
| `tests/commands/test_exit_codes.py` | Create | Tests for bitfield exit code composition |
| `docs/cli/health.md` | Rename to `docs/cli/checks.md` | Remove gap flags, document `gaps` command, update command name |

---

### Task 1: Rename `health` CLI command to `checks`

**Files:**
- Modify: `src/elspais/commands/args.py:25-65`
- Modify: `src/elspais/cli.py:55-340`
- Modify: `src/elspais/commands/report.py:17-25`
- Modify: `src/elspais/commands/health.py` (hint text)
- Modify: `tests/commands/test_health_detail_flags.py`
- Modify: `tests/commands/test_health_finding.py`
- Rename: `docs/cli/health.md` → `docs/cli/checks.md`

**Note:** Internal class names (`HealthReport`, `HealthCheck`, `HealthFinding`) stay unchanged. Only the CLI-facing command name and Args class change.

- [ ] **Step 1: Rename `HealthArgs` to `ChecksArgs` in `args.py`**

Change class name and update the `tyro.conf.subcommand` in `Command` union from `"health"` to `"checks"`. Remove the gap flags (`uncovered`, `untested`, `unvalidated`, `untraced`, `failing`) from the dataclass at the same time.

- [ ] **Step 2: Update `cli.py`**

Update import: `HealthArgs` → `ChecksArgs`.
Update `_CMD_MAP`: `ChecksArgs: "checks"`.
Update dispatch: `if args.command == "checks":` → `return health.run(args)`.

- [ ] **Step 3: Update `report.py` registrations**

Replace `"health"` with `"checks"` in `COMPOSABLE_SECTIONS` and `FORMAT_SUPPORT`.
Update `_render_section` dispatch: `if name == "checks":`.

- [ ] **Step 4: Update hint text in `health.py`**

In `_build_hint` (to be added in Task 2, but if touching now): replace `'elspais -v health'` with `'elspais -v checks'` and `'elspais health'` with `'elspais checks'` in the hint strings.

In `_print_detail_hint` (existing function, will be replaced in Task 2): update `'elspais health'` → `'elspais checks'` for now.

- [ ] **Step 5: Rename `docs/cli/health.md` → `docs/cli/checks.md`**

```bash
git mv docs/cli/health.md docs/cli/checks.md
```

Update content: replace `health` command references with `checks`. Update `docs_loader.py` topic registration if it uses filenames.

- [ ] **Step 6: Update test assertions**

In `test_health_detail_flags.py`: change `parse_args(["health", ...])` to `parse_args(["checks", ...])`.

In `test_health_finding.py`: change hint assertions from `"elspais -v health"` to `"elspais -v checks"` and `"elspais health"` to `"elspais checks"`.

- [ ] **Step 7: Run tests**

Run: `pytest tests/commands/test_health_finding.py tests/commands/test_health_detail_flags.py -x -q`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "rename: health CLI command to checks (internal classes unchanged)"
```

---

### Task 2: Build the shared `_ReportData` intermediate representation

**Files:**
- Modify: `src/elspais/commands/health.py` (add above existing renderers)
- Create: `tests/commands/test_health_report_data.py`

- [ ] **Step 1: Write tests for `_build_report_data`**

```python
# tests/commands/test_health_report_data.py
# Verifies: REQ-d00085
"""Tests for unified health report rendering via _ReportData intermediate."""

from __future__ import annotations

from elspais.commands.health import (
    HealthCheck,
    HealthReport,
    _build_report_data,
)


def _make_mixed_report() -> HealthReport:
    """Report with config + spec categories, mixed pass/fail/info."""
    report = HealthReport()
    report.add(HealthCheck(
        name="config_exists", passed=True,
        message="Configuration found", category="config",
    ))
    report.add(HealthCheck(
        name="spec.parseable", passed=True,
        message="Parsed 5 requirements", category="spec",
    ))
    report.add(HealthCheck(
        name="spec.refs", passed=False,
        message="2 broken references", category="spec", severity="error",
    ))
    report.add(HealthCheck(
        name="code.coverage", passed=True,
        message="80% coverage", category="code", severity="info",
    ))
    return report


class TestBuildReportData:
    """_build_report_data produces correct intermediate representation."""

    def test_sections_only_for_nonempty_categories(self) -> None:
        report = _make_mixed_report()
        data = _build_report_data(report)
        names = [s.name for s in data.sections]
        assert "CONFIG" in names
        assert "SPEC" in names
        assert "CODE" in names
        assert "TESTS" not in names
        assert "UAT" not in names

    def test_info_checks_excluded_from_category_stats(self) -> None:
        report = _make_mixed_report()
        data = _build_report_data(report)
        code_section = [s for s in data.sections if s.name == "CODE"][0]
        assert "0 passed" in code_section.stats
        assert "1 skipped" in code_section.stats

    def test_check_icons_correct(self) -> None:
        report = _make_mixed_report()
        data = _build_report_data(report)
        spec_section = [s for s in data.sections if s.name == "SPEC"][0]
        icons = {c.name: c.icon for c in spec_section.checks}
        assert icons["spec.parseable"] == "\u2713"
        assert icons["spec.refs"] == "\u2717"

    def test_info_check_gets_tilde_icon(self) -> None:
        report = _make_mixed_report()
        data = _build_report_data(report)
        code_section = [s for s in data.sections if s.name == "CODE"][0]
        icons = {c.name: c.icon for c in code_section.checks}
        assert icons["code.coverage"] == "~"

    def test_summary_line_healthy(self) -> None:
        report = HealthReport()
        report.add(HealthCheck(
            name="ok", passed=True, message="good", category="spec",
        ))
        data = _build_report_data(report)
        assert "HEALTHY" in data.summary_line
        assert data.is_healthy is True

    def test_summary_line_unhealthy(self) -> None:
        report = _make_mixed_report()
        data = _build_report_data(report)
        assert "UNHEALTHY" in data.summary_line
        assert data.is_healthy is False

    def test_category_icon_all_passed(self) -> None:
        report = HealthReport()
        report.add(HealthCheck(
            name="ok", passed=True, message="good", category="config",
        ))
        data = _build_report_data(report)
        assert data.sections[0].icon == "\u2713"

    def test_category_icon_has_errors(self) -> None:
        report = _make_mixed_report()
        data = _build_report_data(report)
        spec_section = [s for s in data.sections if s.name == "SPEC"][0]
        assert spec_section.icon == "\u2717"

    def test_category_icon_warnings_only(self) -> None:
        report = HealthReport()
        report.add(HealthCheck(
            name="warn", passed=False, message="stale",
            category="spec", severity="warning",
        ))
        data = _build_report_data(report)
        assert data.sections[0].icon == "\u26a0"
```

- [ ] **Step 2: Run tests — expect ImportError**

Run: `pytest tests/commands/test_health_report_data.py -x -q`
Expected: FAIL — `_build_report_data` not found

- [ ] **Step 3: Implement `_ReportData` and `_build_report_data` in health.py**

Add these dataclasses and the builder function above the existing `_print_text_report`:

```python
@dataclass
class _CheckLine:
    icon: str    # "✓", "✗", "⚠", "~"
    name: str
    message: str


@dataclass
class _SectionData:
    name: str      # "CONFIG", "SPEC", etc.
    icon: str      # "✓", "✗", "⚠"
    stats: str     # "3 passed, 1 failed" or "3 passed, 1 failed, 1 skipped"
    checks: list[_CheckLine]


@dataclass
class _ReportData:
    sections: list[_SectionData]
    summary_line: str
    is_healthy: bool
    hint: str | None


def _build_report_data(
    report: HealthReport,
    verbose: bool = False,
) -> _ReportData:
    """Build unified intermediate representation from HealthReport."""
    categories = ["config", "spec", "code", "tests", "uat"]
    sections: list[_SectionData] = []

    for category in categories:
        checks = list(report.iter_by_category(category))
        if not checks:
            continue

        skipped = sum(1 for c in checks if c.severity == "info")
        passed = sum(
            1 for c in checks if c.passed and c.severity != "info"
        )
        total = len(checks) - skipped
        has_errors = any(
            not c.passed and c.severity == "error" for c in checks
        )
        failed = sum(
            1 for c in checks
            if not c.passed and c.severity in ("error", "warning")
        )

        if passed == total:
            cat_icon = "\u2713"
        elif has_errors:
            cat_icon = "\u2717"
        else:
            cat_icon = "\u26a0"

        parts = [f"{passed} passed", f"{failed} failed"]
        if skipped:
            parts.append(f"{skipped} skipped")

        check_lines: list[_CheckLine] = []
        for check in checks:
            if check.severity == "info":
                icon = "~"
            elif check.passed:
                icon = "\u2713"
            elif check.severity == "warning":
                icon = "\u26a0"
            else:
                icon = "\u2717"
            check_lines.append(
                _CheckLine(icon=icon, name=check.name, message=check.message)
            )

        sections.append(_SectionData(
            name=category.upper(),
            icon=cat_icon,
            stats=", ".join(parts),
            checks=check_lines,
        ))

    # Summary line
    counted = len(report.checks) - report.skipped
    skip_suffix = (
        f", {report.skipped} skipped" if report.skipped else ""
    )
    if (
        report.failed == 0
        and report.warnings == 0
        and report.passed == counted
    ):
        if report.skipped:
            summary = (
                f"HEALTHY: {counted}/{counted}"
                f" checks passed{skip_suffix}"
            )
        else:
            summary = f"HEALTHY: {counted}/{counted} checks passed"
    elif report.failed == 0 and report.warnings == 0:
        summary = (
            f"{report.passed}/{counted} checks passed{skip_suffix}"
        )
    elif report.failed == 0:
        summary = (
            f"{report.passed}/{counted} checks passed,"
            f" {report.warnings} warnings{skip_suffix}"
        )
    else:
        summary = (
            f"UNHEALTHY: {report.failed} errors,"
            f" {report.warnings} warnings{skip_suffix}"
        )

    # Hint for unhealthy reports
    hint = _build_hint(report, verbose) if not report.is_healthy else None

    return _ReportData(
        sections=sections,
        summary_line=summary,
        is_healthy=report.is_healthy,
        hint=hint,
    )


def _build_hint(report: HealthReport, already_verbose: bool) -> str | None:
    """Build hint string about how to get more details."""
    failed_categories = set()
    for check in report.checks:
        if not check.passed and check.severity in ("error", "warning"):
            failed_categories.add(check.category)

    if not failed_categories:
        return None

    category_flags = {
        "spec": "--spec", "code": "--code",
        "tests": "--tests", "config": "",
    }
    if len(failed_categories) == 1:
        cat = next(iter(failed_categories))
        flag = category_flags.get(cat, "")
        scope = f" {flag}" if flag else ""
    else:
        scope = ""

    lines = []
    if not already_verbose:
        lines.append(f"Run 'elspais -v checks{scope}' for details,")
        lines.append(
            f" or 'elspais checks{scope} --format json"
            " -o checks.json' for machine-readable output."
        )
    else:
        lines.append(
            f"Run 'elspais checks{scope} --format json"
            " -o checks.json' for machine-readable output."
        )
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests — all pass**

Run: `pytest tests/commands/test_health_report_data.py -x -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/elspais/commands/health.py tests/commands/test_health_report_data.py
git commit -m "feat: add _ReportData intermediate representation for checks rendering"
```

---

### Task 3: Rewrite text renderer to consume `_ReportData`

**Files:**
- Modify: `src/elspais/commands/health.py`
- Modify: `tests/commands/test_health_report_data.py`

**Design note:** The old `_print_text_report` showed `check.details` in verbose mode. This is intentionally dropped — `checks` is a checklist, not a detailed report. Detailed traceability belongs in `trace`/`summary` sections. `_print_text_report` is kept as a thin wrapper since existing tests import it.

- [ ] **Step 1: Write tests for `_render_text`**

Add to `tests/commands/test_health_report_data.py`:

```python
from elspais.commands.health import _render_text


class TestRenderText:
    """_render_text produces checklist output from _ReportData."""

    def test_category_header_format(self) -> None:
        report = _make_mixed_report()
        data = _build_report_data(report)
        output = _render_text(data)
        assert "\u2717 SPEC (1 passed, 1 failed)" in output
        assert "-" * 40 in output

    def test_check_line_format(self) -> None:
        report = _make_mixed_report()
        data = _build_report_data(report)
        output = _render_text(data)
        assert "  \u2713 spec.parseable: Parsed 5 requirements" in output
        assert "  \u2717 spec.refs: 2 broken references" in output

    def test_summary_block(self) -> None:
        report = _make_mixed_report()
        data = _build_report_data(report)
        output = _render_text(data)
        assert "=" * 40 in output
        assert "UNHEALTHY" in output

    def test_hint_shown_when_unhealthy(self) -> None:
        report = _make_mixed_report()
        data = _build_report_data(report, verbose=False)
        output = _render_text(data)
        assert "elspais -v checks" in output

    def test_info_check_tilde(self) -> None:
        report = _make_mixed_report()
        data = _build_report_data(report)
        output = _render_text(data)
        assert "  ~ code.coverage: 80% coverage" in output
```

- [ ] **Step 2: Run tests — expect ImportError**

Run: `pytest tests/commands/test_health_report_data.py::TestRenderText -x -q`
Expected: FAIL — `_render_text` not found

- [ ] **Step 3: Implement `_render_text` and wire into `_format_report`**

```python
def _render_text(data: _ReportData) -> str:
    """Render _ReportData as plain text checklist."""
    lines: list[str] = []
    for section in data.sections:
        lines.append(
            f"\n{section.icon} {section.name} ({section.stats})"
        )
        lines.append("-" * 40)
        for check in section.checks:
            lines.append(f"  {check.icon} {check.name}: {check.message}")

    lines.append("")
    lines.append("=" * 40)
    lines.append(data.summary_line)
    if data.hint:
        lines.append(data.hint)
    lines.append("=" * 40)
    return "\n".join(lines)
```

Update `_format_report` text branch — replace `redirect_stdout` + `_print_text_report` with:

```python
else:
    if quiet:
        return _build_report_data(report, verbose=verbose).summary_line
    data = _build_report_data(report, verbose=verbose)
    return _render_text(data)
```

Keep `_print_text_report` as a thin backward-compat wrapper (tests import it):

```python
def _print_text_report(
    report: HealthReport,
    verbose: bool = False,
    include_passing_details: bool = False,
) -> None:
    """Print human-readable health report (legacy wrapper)."""
    data = _build_report_data(report, verbose=verbose)
    print(_render_text(data))
```

Remove old `_print_summary_line` and `_print_detail_hint` functions (logic is now in `_build_report_data` and `_build_hint`). Remove `_print_quiet_report`. Remove the `import io` and `redirect_stdout` from `_format_report`.

- [ ] **Step 4: Run all health tests**

Run: `pytest tests/commands/test_health_report_data.py tests/commands/test_health_finding.py tests/commands/test_health_detail_flags.py -x -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/elspais/commands/health.py tests/commands/test_health_report_data.py
git commit -m "refactor: rewrite text renderer to consume _ReportData"
```

---

### Task 4: Rewrite markdown renderer to consume `_ReportData`

**Files:**
- Modify: `src/elspais/commands/health.py`
- Modify: `tests/commands/test_health_report_data.py`
- Modify: `tests/commands/test_health_detail_flags.py`
- Modify: `tests/commands/test_health_finding.py`

- [ ] **Step 1: Write tests for new `_render_markdown`**

Add to `tests/commands/test_health_report_data.py`:

```python
from elspais.commands.health import _render_markdown


class TestRenderMarkdown:
    """_render_markdown uses checklist format, no title, same stats."""

    def test_no_h1_title(self) -> None:
        report = _make_mixed_report()
        data = _build_report_data(report)
        output = _render_markdown(data)
        assert not output.startswith("# ")
        assert "# Health Report" not in output

    def test_category_header_h2_with_icon(self) -> None:
        report = _make_mixed_report()
        data = _build_report_data(report)
        output = _render_markdown(data)
        assert "## \u2717 SPEC (1 passed, 1 failed)" in output

    def test_passing_check_uses_checked_box(self) -> None:
        report = _make_mixed_report()
        data = _build_report_data(report)
        output = _render_markdown(data)
        assert "- [x] spec.parseable: Parsed 5 requirements" in output

    def test_failing_check_uses_unchecked_box(self) -> None:
        report = _make_mixed_report()
        data = _build_report_data(report)
        output = _render_markdown(data)
        assert "- [ ] spec.refs: 2 broken references" in output

    def test_info_check_uses_tilde_prefix(self) -> None:
        report = _make_mixed_report()
        data = _build_report_data(report)
        output = _render_markdown(data)
        assert "- [ ] ~ code.coverage: 80% coverage" in output

    def test_no_tables(self) -> None:
        report = _make_mixed_report()
        data = _build_report_data(report)
        output = _render_markdown(data)
        assert "| Check" not in output
        assert "|---" not in output

    def test_no_details_blocks(self) -> None:
        from elspais.commands.health import HealthFinding
        report = HealthReport()
        report.add(HealthCheck(
            name="ok", passed=True, message="good", category="spec",
            findings=[HealthFinding(message="detail")],
        ))
        data = _build_report_data(report)
        output = _render_markdown(data)
        assert "<details>" not in output

    def test_summary_line(self) -> None:
        report = _make_mixed_report()
        data = _build_report_data(report)
        output = _render_markdown(data)
        assert "UNHEALTHY" in output

    def test_separator_between_categories(self) -> None:
        report = _make_mixed_report()
        data = _build_report_data(report)
        output = _render_markdown(data)
        assert "---" in output

    def test_same_stats_as_text(self) -> None:
        """Markdown and text renderers produce identical category stats."""
        report = _make_mixed_report()
        data = _build_report_data(report)
        text = _render_text(data)
        md = _render_markdown(data)
        assert "1 passed, 1 failed" in text
        assert "1 passed, 1 failed" in md
```

- [ ] **Step 2: Run tests — expect failure**

Run: `pytest tests/commands/test_health_report_data.py::TestRenderMarkdown -x -q`
Expected: FAIL — old `_render_markdown` has wrong signature

- [ ] **Step 3: Rewrite `_render_markdown` to consume `_ReportData`**

```python
# Implements: REQ-d00085-E
def _render_markdown(data: _ReportData) -> str:
    """Render _ReportData as markdown checklist."""
    lines: list[str] = []

    for i, section in enumerate(data.sections):
        if i > 0:
            lines.append("---")
            lines.append("")
        lines.append(
            f"## {section.icon} {section.name} ({section.stats})"
        )
        lines.append("")
        for check in section.checks:
            if check.icon == "~":
                lines.append(
                    f"- [ ] ~ {check.name}: {check.message}"
                )
            elif check.icon == "\u2713":
                lines.append(f"- [x] {check.name}: {check.message}")
            else:
                lines.append(f"- [ ] {check.name}: {check.message}")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(data.summary_line)

    return "\n".join(lines)
```

Update `_format_report` markdown branch:

```python
elif fmt == "markdown":
    data = _build_report_data(report)
    return _render_markdown(data)
```

- [ ] **Step 4: Update `test_health_detail_flags.py` for new markdown format**

```python
# In TestMarkdownFormatPassingDetails — markdown is now a checklist,
# never shows findings regardless of flag:

def test_REQ_d00085_F_markdown_include_passing_details_shows_findings(
    self,
) -> None:
    """Markdown is a checklist — no findings even with flag."""
    report = _make_passing_report()
    args = _make_args(format="markdown", include_passing_details=True)
    output = _format_report(report, args)
    assert "valid_references" in output
    assert "- [x]" in output
    assert "<details>" not in output

def test_REQ_d00085_F_markdown_skip_passing_details_hides_findings(
    self,
) -> None:
    """Markdown checklist shows check name/message, never findings."""
    report = _make_passing_report()
    args = _make_args(format="markdown", include_passing_details=False)
    output = _format_report(report, args)
    assert "valid_references" in output
    assert "- [x]" in output
    assert "REQ-p00001-A resolves" not in output
```

- [ ] **Step 5: Update `test_health_finding.py` markdown test**

The `test_REQ_d00085_I_markdown_rendering_unaffected` test called `_render_markdown(report)` directly, but the signature now takes `_ReportData`. Replace:

```python
# In TestHealthFindingRendererCompat:

def test_REQ_d00085_I_markdown_rendering_unaffected(self) -> None:
    """Markdown rendering is the same with or without findings."""
    import argparse
    from elspais.commands.health import _format_report

    report_with = self._make_report_with_findings()
    report_without = self._make_report_without_findings()

    args = argparse.Namespace(
        format="markdown", verbose=False, quiet=False,
        lenient=False, include_passing_details=False,
    )
    md_with = _format_report(report_with, args)
    md_without = _format_report(report_without, args)

    assert md_with == md_without
```

Also update the import at the top of the file — remove `_render_markdown` from the import list and add `_format_report` if not already imported.

- [ ] **Step 6: Run all health tests**

Run: `pytest tests/commands/test_health_report_data.py tests/commands/test_health_finding.py tests/commands/test_health_detail_flags.py -x -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/elspais/commands/health.py tests/commands/test_health_report_data.py tests/commands/test_health_detail_flags.py tests/commands/test_health_finding.py
git commit -m "refactor: rewrite markdown renderer as checklist consuming _ReportData"
```

---

### Task 5: Create `gaps.py` with gap data collection

**Files:**
- Create: `src/elspais/commands/gaps.py`
- Create: `tests/commands/test_gaps.py`

**Important:** `gaps.py` imports `_resolve_exclude_status` from `health.py` — no duplication.

- [ ] **Step 1: Write tests for gap data collection**

```python
# tests/commands/test_gaps.py
# Verifies: REQ-d00085
"""Tests for gap listing composable sections."""

from __future__ import annotations

import pytest

from elspais.commands.gaps import collect_gaps, GapData


class TestCollectGaps:
    """collect_gaps returns structured gap data from graph."""

    @pytest.fixture
    def gap_graph(self, tmp_path):
        """Build a graph with known coverage gaps."""
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        (spec_dir / "req-p00001.md").write_text(
            "# REQ-p00001 Covered Requirement\n"
            "Status: Active\n"
            "Body text.\n"
            "*End*\n"
        )
        (spec_dir / "req-p00002.md").write_text(
            "# REQ-p00002 Uncovered Requirement\n"
            "Status: Active\n"
            "Body text.\n"
            "*End*\n"
        )

        toml_path = tmp_path / ".elspais.toml"
        toml_path.write_text(
            '[project]\nname = "test"\n'
            '[levels.prd]\nrank = 1\nprefix = "p"\n'
            '[id-patterns]\nprefix = "REQ"\n'
        )

        from elspais.graph.factory import build_graph
        return build_graph(
            spec_dirs=[spec_dir],
            config_path=toml_path,
            canonical_root=tmp_path,
        )

    def test_uncovered_finds_zero_coverage_reqs(self, gap_graph) -> None:
        data = collect_gaps(gap_graph, exclude_status=set())
        ids = [g[0] for g in data.uncovered]
        assert "REQ-p00001" in ids
        assert "REQ-p00002" in ids

    def test_untested_finds_zero_test_reqs(self, gap_graph) -> None:
        data = collect_gaps(gap_graph, exclude_status=set())
        ids = [g[0] for g in data.untested]
        assert "REQ-p00001" in ids

    def test_exclude_status_filters(self, gap_graph) -> None:
        data = collect_gaps(gap_graph, exclude_status={"Active"})
        # Both reqs are Active, so all filtered out
        assert len(data.uncovered) == 0
        assert len(data.untested) == 0
```

- [ ] **Step 2: Run tests — expect ImportError**

Run: `pytest tests/commands/test_gaps.py -x -q`
Expected: FAIL — module not found

- [ ] **Step 3: Implement `gaps.py` data collection**

```python
# src/elspais/commands/gaps.py
"""Gap listing composable sections for traceability coverage gaps."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from elspais.graph.federated import FederatedGraph


@dataclass
class GapData:
    """Collected gap data across all gap types."""

    uncovered: list[tuple[str, str]] = field(default_factory=list)
    untested: list[tuple[str, str]] = field(default_factory=list)
    unvalidated: list[tuple[str, str]] = field(default_factory=list)
    failing: list[tuple[str, str, str]] = field(default_factory=list)


def collect_gaps(
    graph: FederatedGraph,
    exclude_status: set[str],
) -> GapData:
    """Collect all gap data from the graph in a single pass."""
    from elspais.graph import NodeKind

    data = GapData()

    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        if node.status in exclude_status:
            continue
        rid = node.id
        title = node.get_label() or ""
        metrics = node.get_metric("rollup_metrics")

        has_code = metrics is not None and metrics.referenced_pct > 0
        if not has_code:
            data.uncovered.append((rid, title))

        has_test = metrics is not None and metrics.direct_tested > 0
        if not has_test:
            data.untested.append((rid, title))

        has_uat = metrics is not None and metrics.uat_covered > 0
        if not has_uat:
            data.unvalidated.append((rid, title))

        if metrics is not None:
            if metrics.has_failures:
                data.failing.append((rid, title, "test"))
            if metrics.uat_has_failures:
                data.failing.append((rid, title, "uat"))

    return data
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/commands/test_gaps.py -x -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/elspais/commands/gaps.py tests/commands/test_gaps.py
git commit -m "feat: add gaps.py with gap data collection"
```

---

### Task 6: Add gap section rendering, `render_section()`, and standalone `run()`

**Files:**
- Modify: `src/elspais/commands/gaps.py`
- Modify: `tests/commands/test_gaps.py`

- [ ] **Step 1: Write tests for gap text/markdown rendering**

Add to `tests/commands/test_gaps.py`:

```python
from elspais.commands.gaps import render_gap_text, render_gap_markdown


class TestRenderGapText:
    def test_uncovered_section(self) -> None:
        data = GapData(
            uncovered=[("REQ-p00001", "Login"), ("REQ-p00002", "Signup")]
        )
        output = render_gap_text("uncovered", data)
        assert "UNCOVERED (no code refs)" in output
        assert "(2)" in output
        assert "REQ-p00001" in output
        assert "Login" in output

    def test_empty_shows_none(self) -> None:
        data = GapData()
        output = render_gap_text("uncovered", data)
        assert "none" in output

    def test_failing_shows_source(self) -> None:
        data = GapData(
            failing=[("REQ-p00001", "Login", "test")]
        )
        output = render_gap_text("failing", data)
        assert "[test]" in output


class TestRenderGapMarkdown:
    def test_uncovered_section(self) -> None:
        data = GapData(uncovered=[("REQ-p00001", "Login")])
        output = render_gap_markdown("uncovered", data)
        assert "## UNCOVERED" in output
        assert "| REQ-p00001" in output

    def test_empty_shows_none(self) -> None:
        data = GapData()
        output = render_gap_markdown("uncovered", data)
        assert "No gaps" in output or "none" in output.lower()
```

- [ ] **Step 2: Run tests — expect ImportError**

Run: `pytest tests/commands/test_gaps.py::TestRenderGapText -x -q`
Expected: FAIL

- [ ] **Step 3: Implement rendering functions, `render_section`, and `run`**

Add to `gaps.py`. Note: `_resolve_exclude_status` is imported from `health.py`, not duplicated:

```python
_LABELS = {
    "uncovered": "UNCOVERED (no code refs)",
    "untested": "UNTESTED (no test coverage)",
    "unvalidated": "UNVALIDATED (no UAT coverage)",
    "failing": "FAILING",
}

# Map Args classes to gap types (used by standalone run())
_GAP_TYPE_MAP: dict[str, str | None] = {
    "gaps": None,  # None = all gap types
    "uncovered": "uncovered",
    "untested": "untested",
    "unvalidated": "unvalidated",
    "failing": "failing",
}


def _get_gap_list(
    gap_type: str, data: GapData
) -> list[tuple[str, ...]]]:
    """Get the gap list for a specific type."""
    return getattr(data, gap_type)


def render_gap_text(gap_type: str, data: GapData) -> str:
    """Render a single gap type as text."""
    label = _LABELS[gap_type]
    gaps = _get_gap_list(gap_type, data)

    if not gaps:
        return f"\n{label}: none"

    lines = [f"\n{label} ({len(gaps)}):"]
    if gap_type == "failing":
        for rid, title, source in sorted(gaps):
            lines.append(f"  {rid:20s} [{source}] {title}")
    else:
        for rid, title in sorted(gaps):
            lines.append(f"  {rid:20s} {title}")
    return "\n".join(lines)


def render_gap_markdown(gap_type: str, data: GapData) -> str:
    """Render a single gap type as markdown."""
    label = _LABELS[gap_type]
    gaps = _get_gap_list(gap_type, data)

    if not gaps:
        return f"## {label}\n\nNo gaps found."

    lines = [f"## {label} ({len(gaps)})", ""]
    if gap_type == "failing":
        lines.append("| Requirement | Source | Title |")
        lines.append("|-------------|--------|-------|")
        for rid, title, source in sorted(gaps):
            lines.append(f"| {rid} | {source} | {title} |")
    else:
        lines.append("| Requirement | Title |")
        lines.append("|-------------|-------|")
        for rid, title in sorted(gaps):
            lines.append(f"| {rid} | {title} |")
    return "\n".join(lines)


def render_section(
    graph: FederatedGraph,
    config: dict[str, Any] | None,
    args: argparse.Namespace,
    gap_types: list[str] | None = None,
) -> tuple[str, int]:
    """Render gap sections as a composed report section.

    Returns (output, exit_code). Exit code is always 0
    (gap sections are informational; bit 4 reserved for future use).
    """
    from elspais.commands.health import _resolve_exclude_status

    if gap_types is None:
        gap_types = ["uncovered", "untested", "unvalidated", "failing"]

    raw_config = config if config else {}
    exclude_status = _resolve_exclude_status(args, raw_config)
    data = collect_gaps(graph, exclude_status)

    fmt = getattr(args, "format", "text") or "text"
    if fmt == "json":
        import json

        result: dict[str, list[dict[str, str]]] = {}
        for gt in gap_types:
            gaps = _get_gap_list(gt, data)
            if gt == "failing":
                result[gt] = [
                    {"id": t[0], "title": t[1], "source": t[2]}
                    for t in gaps
                ]
            else:
                result[gt] = [
                    {"id": t[0], "title": t[1]} for t in gaps
                ]
        return json.dumps(result, indent=2), 0

    renderer = (
        render_gap_markdown if fmt == "markdown" else render_gap_text
    )
    outputs = [renderer(gt, data) for gt in gap_types]
    return "\n\n".join(outputs), 0


def run(args: argparse.Namespace) -> int:
    """Run a standalone gap listing command."""
    from elspais.config import get_config
    from elspais.graph.factory import build_graph

    config_path = getattr(args, "config", None)
    spec_dir = getattr(args, "spec_dir", None)
    canonical_root = getattr(args, "canonical_root", None)

    graph = build_graph(
        spec_dirs=[spec_dir] if spec_dir else None,
        config_path=config_path,
        canonical_root=canonical_root,
    )
    config = get_config(config_path)

    # Derive gap type from command name
    cmd = getattr(args, "command", "gaps")
    gap_type_name = _GAP_TYPE_MAP.get(cmd)
    if gap_type_name:
        gap_types = [gap_type_name]
    else:
        gap_types = ["uncovered", "untested", "unvalidated", "failing"]

    output, exit_code = render_section(
        graph, config, args, gap_types=gap_types
    )

    out_path = getattr(args, "output", None)
    if out_path:
        out_path.write_text(output + "\n" if output else "")
    elif output:
        print(output)

    return exit_code
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/commands/test_gaps.py -x -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/elspais/commands/gaps.py tests/commands/test_gaps.py
git commit -m "feat: add gap section rendering, render_section, and standalone run"
```

---

### Task 7: Register gap commands in CLI and report composition

**Files:**
- Modify: `src/elspais/commands/args.py`
- Modify: `src/elspais/cli.py`
- Modify: `src/elspais/commands/report.py`
- Modify: `src/elspais/commands/health.py` (remove `_print_gap_listing` and gap flag handling)
- Create: `tests/commands/test_exit_codes.py`
- Modify: `tests/commands/test_gaps.py`

- [ ] **Step 1: Add gap Args dataclasses to `args.py`**

After `ChecksArgs` (formerly `HealthArgs`), add:

```python
# ---------------------------------------------------------------------------
# Gap listing commands
# ---------------------------------------------------------------------------
@dataclasses.dataclass
class GapsArgs:
    """List all traceability gaps."""

    format: Literal["text", "markdown", "json"] = "text"
    """Output format."""

    status: list[str] | None = None
    """Statuses to include (default: Active)."""

    output: Annotated[Path | None, tyro.conf.arg(aliases=["-o"])] = None
    """Write output to file instead of stdout."""


@dataclasses.dataclass
class UncoveredArgs:
    """List requirements without code coverage."""

    format: Literal["text", "markdown", "json"] = "text"
    """Output format."""

    status: list[str] | None = None
    """Statuses to include (default: Active)."""

    output: Annotated[Path | None, tyro.conf.arg(aliases=["-o"])] = None
    """Write output to file instead of stdout."""


@dataclasses.dataclass
class UntestedArgs:
    """List requirements without test coverage."""

    format: Literal["text", "markdown", "json"] = "text"
    """Output format."""

    status: list[str] | None = None
    """Statuses to include (default: Active)."""

    output: Annotated[Path | None, tyro.conf.arg(aliases=["-o"])] = None
    """Write output to file instead of stdout."""


@dataclasses.dataclass
class UnvalidatedArgs:
    """List requirements without UAT (journey) coverage."""

    format: Literal["text", "markdown", "json"] = "text"
    """Output format."""

    status: list[str] | None = None
    """Statuses to include (default: Active)."""

    output: Annotated[Path | None, tyro.conf.arg(aliases=["-o"])] = None
    """Write output to file instead of stdout."""


@dataclasses.dataclass
class FailingArgs:
    """List requirements with failing test or UAT results."""

    format: Literal["text", "markdown", "json"] = "text"
    """Output format."""

    status: list[str] | None = None
    """Statuses to include (default: Active)."""

    output: Annotated[Path | None, tyro.conf.arg(aliases=["-o"])] = None
    """Write output to file instead of stdout."""
```

Add to the `Command` union:

```python
    | Annotated[GapsArgs, tyro.conf.subcommand("gaps")]
    | Annotated[UncoveredArgs, tyro.conf.subcommand("uncovered")]
    | Annotated[UntestedArgs, tyro.conf.subcommand("untested")]
    | Annotated[UnvalidatedArgs, tyro.conf.subcommand("unvalidated")]
    | Annotated[FailingArgs, tyro.conf.subcommand("failing")]
```

- [ ] **Step 2: Register in `cli.py`**

Add to `_CMD_MAP`:

```python
GapsArgs: "gaps",
UncoveredArgs: "uncovered",
UntestedArgs: "untested",
UnvalidatedArgs: "unvalidated",
FailingArgs: "failing",
```

Add dispatch:

```python
elif args.command in (
    "gaps", "uncovered", "untested", "unvalidated", "failing"
):
    from elspais.commands import gaps
    return gaps.run(args)
```

- [ ] **Step 3: Update `report.py` with gap sections, exit bits, and OR composition**

```python
COMPOSABLE_SECTIONS = (
    "checks", "summary", "trace", "changed",
    "uncovered", "untested", "unvalidated", "failing", "gaps",
)

FORMAT_SUPPORT = {
    "checks": {"text", "markdown", "json", "junit", "sarif"},
    "summary": {"text", "markdown", "json", "csv"},
    "trace": {"text", "markdown", "json", "csv"},
    "changed": {"text", "json"},
    "uncovered": {"text", "markdown", "json"},
    "untested": {"text", "markdown", "json"},
    "unvalidated": {"text", "markdown", "json"},
    "failing": {"text", "markdown", "json"},
    "gaps": {"text", "markdown", "json"},
}

EXIT_BIT: dict[str, int] = {
    "checks": 1,
    "summary": 2,
    "trace": 4,
    "changed": 8,
    "uncovered": 16,
    "untested": 16,
    "unvalidated": 16,
    "failing": 16,
    "gaps": 16,
}
```

Update `graph_sections` to include gap sections:

```python
graph_sections = {
    "checks", "summary", "trace",
    "uncovered", "untested", "unvalidated", "failing", "gaps",
}
```

Update composition in `run()` — change `worst_exit = max(worst_exit, exit_code)` to:

```python
combined_exit = 0
# ...
for section in sections:
    output, exit_code = _render_section(section, graph, config, args)
    if output:
        outputs.append(output)
    if exit_code:
        combined_exit |= EXIT_BIT.get(section, 0)
```

Remove the `--lenient` safety net block. Lenient is handled by individual sections (checks returns 0 when lenient and warnings-only).

Update `_render_section` dispatch — rename `"health"` to `"checks"`, add gap dispatch:

```python
if name == "checks":
    from elspais.commands.health import render_section
    return render_section(graph, config, args)
# ... existing summary, trace, changed ...
elif name in ("uncovered", "untested", "unvalidated", "failing"):
    from elspais.commands.gaps import render_section as gap_render
    return gap_render(graph, config, args, gap_types=[name])
elif name == "gaps":
    from elspais.commands.gaps import render_section as gap_render
    return gap_render(graph, config, args)
```

- [ ] **Step 4: Remove gap flag handling from `health.py:run()`**

Remove the gap flag block (lines ~1929-1947) from `run()`. Remove `_print_gap_listing` function entirely.

- [ ] **Step 5: Write exit code tests**

```python
# tests/commands/test_exit_codes.py
# Verifies: REQ-d00085
"""Tests for bitfield exit code composition."""

from elspais.commands.report import EXIT_BIT


class TestExitBitAllocation:
    def test_checks_is_bit_0(self) -> None:
        assert EXIT_BIT["checks"] == 1

    def test_summary_is_bit_1(self) -> None:
        assert EXIT_BIT["summary"] == 2

    def test_trace_is_bit_2(self) -> None:
        assert EXIT_BIT["trace"] == 4

    def test_changed_is_bit_3(self) -> None:
        assert EXIT_BIT["changed"] == 8

    def test_gap_sections_share_bit_4(self) -> None:
        for name in ("uncovered", "untested", "unvalidated",
                      "failing", "gaps"):
            assert EXIT_BIT[name] == 16

    def test_bits_dont_overlap(self) -> None:
        """Non-gap sections each have unique bits."""
        seen = set()
        for name in ("checks", "summary", "trace", "changed"):
            bit = EXIT_BIT[name]
            assert bit not in seen, f"{name} bit {bit} overlaps"
            seen.add(bit)

    def test_or_composition(self) -> None:
        """Checks fail + gap fail = both bits set."""
        result = EXIT_BIT["checks"] | EXIT_BIT["gaps"]
        assert result == 17  # 1 | 16
        assert result & EXIT_BIT["checks"]  # checks bit set
        assert result & EXIT_BIT["gaps"]    # gaps bit set
        assert not (result & EXIT_BIT["summary"])  # summary bit clear
```

- [ ] **Step 6: Write composability tests**

Add to `tests/commands/test_gaps.py`:

```python
from elspais.commands.report import COMPOSABLE_SECTIONS, FORMAT_SUPPORT


class TestGapComposability:
    def test_gap_sections_registered(self) -> None:
        for name in (
            "uncovered", "untested", "unvalidated", "failing", "gaps"
        ):
            assert name in COMPOSABLE_SECTIONS

    def test_gap_format_support(self) -> None:
        for name in (
            "uncovered", "untested", "unvalidated", "failing", "gaps"
        ):
            assert "text" in FORMAT_SUPPORT[name]
            assert "markdown" in FORMAT_SUPPORT[name]
            assert "json" in FORMAT_SUPPORT[name]

    def test_checks_renamed_from_health(self) -> None:
        assert "checks" in COMPOSABLE_SECTIONS
        assert "health" not in COMPOSABLE_SECTIONS
```

- [ ] **Step 7: Run all tests**

Run: `pytest tests/commands/ -x -q`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add src/elspais/commands/args.py src/elspais/commands/gaps.py src/elspais/commands/health.py src/elspais/commands/report.py src/elspais/cli.py tests/commands/test_exit_codes.py tests/commands/test_gaps.py
git commit -m "feat: register gap commands, bitfield exit codes, rename health to checks"
```

---

### Task 8: Update docs and run full test suite

**Files:**
- Modify: `docs/cli/checks.md` (renamed from health.md in Task 1)

- [ ] **Step 1: Update `docs/cli/checks.md`**

Remove `--uncovered`, `--untested`, `--unvalidated`, `--untraced`, `--failing` from the options table.

Update command name from `health` to `checks` throughout.

Add a "Gap Listings" section:

```markdown
## Gap Listings

Use standalone gap commands or compose them with checks:

    elspais gaps                      # All gaps
    elspais uncovered                 # Requirements without code coverage
    elspais untested                  # Requirements without test coverage
    elspais unvalidated               # Requirements without UAT coverage
    elspais failing                   # Requirements with failing results
    elspais checks gaps               # Checklist + all gaps
    elspais checks untested           # Checklist + untested gaps

## Exit Codes

Exit codes use a bitfield so composed reports indicate which sections failed:

| Bit | Value | Section |
|-----|-------|---------|
| 0 | 1 | checks |
| 1 | 2 | summary (reserved) |
| 2 | 4 | trace (reserved) |
| 3 | 8 | changed (reserved) |
| 4 | 16 | gaps (reserved) |

Composed reports OR the bits together. Currently only `checks` returns non-zero.
```

- [ ] **Step 2: Run full test suite**

Run: `pytest -x -q`
Expected: PASS

- [ ] **Step 3: Run e2e tests**

Run: `pytest -m e2e -x -q`
Expected: PASS

- [ ] **Step 4: Manual smoke test**

```bash
elspais checks --format text
elspais checks --format markdown
elspais gaps
elspais uncovered
elspais checks gaps --format markdown
```

Verify:
- `elspais checks` works (not `health`)
- No `# Health Report` title in markdown
- Markdown uses `- [x]`/`- [ ]` checklist items
- Stats match between text and markdown
- Gap commands work standalone and composed
- `elspais checks gaps` returns bitfield exit code

- [ ] **Step 5: Commit**

```bash
git add docs/cli/checks.md
git commit -m "docs: update checks docs for gap commands, exit codes, command rename"
```
