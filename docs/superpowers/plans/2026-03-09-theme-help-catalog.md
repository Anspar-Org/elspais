# Theme & Help Catalog Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify all UI visual semantics into two TOML data files with a Python LegendCatalog, replacing hardcoded CSS colors with CSS custom properties and generating the legend modal from the catalog.

**Architecture:** Two TOML files (theme.toml for colors/symbols, help.toml for descriptions) are read by theme.py into a LegendCatalog. The catalog generates CSS custom properties per theme, populates the legend modal, and feeds compute_validation_color descriptions. This replaces ~176 hardcoded color values across 15 CSS template files and enables arbitrary named themes.

**Tech Stack:** Python 3.10+, tomlkit, Jinja2 templates, CSS custom properties, pytest

**Spec:** `docs/superpowers/specs/2026-03-09-theme-help-catalog-design.md`

---

## Chunk 1: Foundation — TOML Files and LegendCatalog

### Task 1: Create the semantic color token map

Before writing TOML, we need to define the ~50 semantic tokens that replace ~176 hardcoded values. These tokens are the bridge between theme.toml and the CSS partials.

**Files:**
- Create: `src/elspais/html/theme.toml`

- [ ] **Step 1: Create theme.toml with palette and light theme tokens**

The palette defines reusable color sets. Theme tokens map semantic names to hex values. Categorical entries map UI elements to palette references.

Reference the color inventory from the spec review to ensure every hardcoded color in the 15 CSS files maps to a token. The core tokens needed (grouped by purpose):

**Structural tokens** (backgrounds, borders, text):
- `body-bg`, `body-text`
- `panel-bg`, `panel-border`
- `surface-bg` (cards, modals, dropdowns)
- `surface-hover-bg`
- `surface-focus-bg`, `surface-focus-border`, `surface-focus-shadow`
- `muted-text`, `secondary-text`, `primary-text`
- `border-color`, `border-light`
- `input-bg`, `input-border`, `input-text`

**Primary interaction** (blue family):
- `primary`, `primary-hover`, `primary-light-bg`, `primary-light-text`, `primary-soft`

**Semantic colors** (status/result):
- `success-bg`, `success-text`, `success-border`
- `warning-bg`, `warning-text`, `warning-border`
- `danger-bg`, `danger-text`, `danger-border`
- `info-bg`, `info-text`, `info-border`

**Level badges**:
- `level-prd-bg`, `level-prd-text`
- `level-ops-bg`, `level-ops-text`
- `level-dev-bg`, `level-dev-text`

**Status badges**:
- `status-draft-bg`, `status-draft-text`
- `status-active-bg`, `status-active-text`
- `status-deprecated-bg`, `status-deprecated-text`
- `status-proposed-bg`, `status-proposed-text`

**Validation tiers** (active badge overlays):
- `val-green-bg`, `val-green-text`
- `val-yellow-green-bg`, `val-yellow-green-text`
- `val-yellow-bg`, `val-yellow-text`
- `val-red-bg`, `val-red-text`
- `val-orange-bg`, `val-orange-text`

**Assertion buttons**:
- `impl-yes-border`, `impl-yes-text`, `impl-yes-active-bg`
- `impl-no-border`, `impl-no-text`
- `valid-pass-border`, `valid-pass-text`, `valid-pass-active-bg`
- `valid-partial-border`, `valid-partial-text`, `valid-partial-active-bg`
- `valid-fail-border`, `valid-fail-text`, `valid-fail-active-bg`
- `valid-unknown-border`, `valid-unknown-text`, `valid-unknown-active-bg`

**Coverage icons**:
- `coverage-none`, `coverage-partial`, `coverage-full`, `coverage-warning`

**Change indicator**:
- `change-color`

**Stat badges** (header):
- `stat-main-bg`, `stat-tests-bg`, `stat-results-bg`, `stat-repo-bg`

**Toast**:
- `toast-success-bg`, `toast-success-text`, `toast-success-border`
- `toast-error-bg`, `toast-error-text`, `toast-error-border`
- `toast-info-bg`, `toast-info-text`, `toast-info-border`

**File viewer**:
- `fv-on-disk-bg`, `fv-on-disk-text`
- `fv-mutations-bg`, `fv-mutations-text`
- `fv-highlight-bg`, `fv-highlight-hover`
- `fv-line-num-text`, `fv-line-num-bg`

**Assertion panels and test items**:
- `assertion-code-panel-bg`, `assertion-code-panel-border`
- `assertion-tests-panel-bg`, `assertion-tests-panel-border`
- `assertion-test-passed-text`, `assertion-test-failed-text`, `assertion-test-no-result-text`
- `assertion-test-link`, `assertion-test-link-hover`

**Test result rows**:
- `result-passed-border`, `result-passed-bg`, `result-passed-text`
- `result-failed-border`, `result-failed-bg`, `result-failed-text`
- `result-error-border`, `result-error-bg`, `result-error-text`
- `result-skipped-border`, `result-skipped-bg`, `result-skipped-text`

Write the full `theme.toml` with:
1. `[themes.light]` — label, icon, all token values (light theme hex colors from current CSS)
2. `[themes.dark]` — label, icon, all token values (dark theme hex colors from `_dark-theme.css.j2`)
3. Categorical entries for icons, badges, buttons, validation tiers (with css_class, symbol, and color_key where applicable)

Cross-reference with:
- Every color in `src/elspais/html/templates/partials/css/_dark-theme.css.j2` (dark values)
- Every color in the 15 CSS partial files (light values)

- [ ] **Step 2: Verify theme.toml parses correctly**

```bash
python -c "import tomlkit; print(tomlkit.loads(open('src/elspais/html/theme.toml').read()).keys())"
```

Expected: dict keys showing themes and category sections.

---

### Task 2: Create help.toml

**Files:**
- Create: `src/elspais/html/help.toml`

- [ ] **Step 1: Create help.toml with all categories**

Every key in theme.toml's categorical entries gets a matching help entry with `label`, `description`, and `long_description`. Categories:

- `icons.coverage` — full, partial, none, warning
- `icons.change` — changed
- `badges.status` — draft, active, deprecated, proposed
- `badges.level` — prd, ops, dev
- `badges.kind` — code, test, result, journey
- `badges.edge` — implements, refines
- `badges.result` — passed, failed, error, skipped
- `buttons.implemented` — yes, no
- `buttons.validation` — pass, partial, fail, unknown
- `validation_tiers` — full-direct, full-indirect, partial, failing, anomalous

Use the descriptions from the spec document. Ensure `long_description` fields use TOML multi-line strings (`"""..."""`).

- [ ] **Step 2: Verify help.toml parses correctly**

```bash
python -c "import tomlkit; print(tomlkit.loads(open('src/elspais/html/help.toml').read()).keys())"
```

---

### Task 3: Create theme.py with LegendCatalog

**Files:**
- Create: `src/elspais/html/theme.py`
- Test: `tests/core/test_html/test_theme.py`

- [ ] **Step 1: Write failing tests for LegendCatalog**

Test file: `tests/core/test_html/test_theme.py`

```python
"""Tests for theme.py LegendCatalog — validates TOML parsing, catalog joining, and CSS generation."""
import pytest
from elspais.html.theme import get_catalog, LegendCatalog, CatalogEntry, ThemeInfo


class TestGetCatalog:
    """Test catalog loading and caching."""

    def test_REQ_p00006_A_returns_legend_catalog(self):
        catalog = get_catalog()
        assert isinstance(catalog, LegendCatalog)

    def test_REQ_p00006_A_caches_result(self):
        a = get_catalog()
        b = get_catalog()
        assert a is b


class TestThemes:
    """Test theme enumeration."""

    def test_REQ_p00006_A_has_light_and_dark(self):
        catalog = get_catalog()
        names = catalog.theme_names()
        assert "light" in names
        assert "dark" in names

    def test_REQ_p00006_A_first_theme_is_default(self):
        catalog = get_catalog()
        assert catalog.themes[0].name == "light"

    def test_REQ_p00006_A_themes_have_labels_and_icons(self):
        catalog = get_catalog()
        for t in catalog.themes:
            assert t.label
            assert t.icon


class TestCatalogEntries:
    """Test catalog entry lookup and joining."""

    def test_REQ_p00006_A_by_key_finds_entry(self):
        catalog = get_catalog()
        entry = catalog.by_key("icons.coverage.full")
        assert entry.label == "Full Coverage"
        assert entry.css_class == "coverage-icon full"

    def test_REQ_p00006_A_by_key_raises_for_missing(self):
        catalog = get_catalog()
        with pytest.raises(KeyError):
            catalog.by_key("nonexistent.key")

    def test_REQ_p00006_A_by_category_returns_entries(self):
        catalog = get_catalog()
        entries = catalog.by_category("badges.status")
        keys = [e.key for e in entries]
        assert "badges.status.draft" in keys
        assert "badges.status.active" in keys

    def test_REQ_p00006_A_entries_have_descriptions(self):
        catalog = get_catalog()
        entry = catalog.by_key("validation_tiers.full-direct")
        assert entry.description
        assert entry.long_description

    def test_REQ_p00006_A_validation_tiers_have_color_key(self):
        catalog = get_catalog()
        entry = catalog.by_key("validation_tiers.full-direct")
        assert entry.color_key == "green"


class TestCSSVariableGeneration:
    """Test CSS custom property output."""

    def test_REQ_p00006_A_generates_root_block(self):
        catalog = get_catalog()
        css = catalog.css_variables()
        assert ":root" in css
        assert "--body-bg:" in css

    def test_REQ_p00006_A_generates_dark_theme_block(self):
        catalog = get_catalog()
        css = catalog.css_variables()
        assert ".theme-dark" in css

    def test_REQ_p00006_A_all_tokens_present(self):
        catalog = get_catalog()
        css = catalog.css_variables()
        # Spot-check key tokens
        assert "--primary:" in css
        assert "--status-active-bg:" in css
        assert "--val-green-bg:" in css


class TestGroupedEntries:
    """Test legend modal grouping."""

    def test_REQ_p00006_A_returns_category_groups(self):
        catalog = get_catalog()
        groups = catalog.grouped_entries()
        cat_names = [name for name, _ in groups]
        assert "Coverage Status" in cat_names or "Coverage" in cat_names
        assert len(groups) >= 5  # at least 5 categories
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/core/test_html/test_theme.py -v
```

Expected: ImportError — `elspais.html.theme` does not exist yet.

- [ ] **Step 3: Implement theme.py**

Create `src/elspais/html/theme.py` with:

```python
"""Unified theme and help catalog — single source of truth for UI visual semantics.

Reads theme.toml (colors, symbols, CSS classes) and help.toml (labels, descriptions)
and exposes a LegendCatalog that generates CSS custom properties and legend content.
"""
from __future__ import annotations

import functools
from dataclasses import dataclass, field
from importlib import resources
from typing import Any

import tomlkit


@dataclass
class ThemeInfo:
    name: str
    label: str
    icon: str
    tokens: dict[str, str] = field(default_factory=dict)


@dataclass
class CatalogEntry:
    key: str
    category: str
    symbol: str = ""
    css_class: str = ""
    label: str = ""
    description: str = ""
    long_description: str = ""
    color_key: str = ""  # for validation_tiers: suffix used in CSS class
    # Note: spec's `colors: dict[str, ThemeColor]` is intentionally omitted.
    # Per-entry color lookup is unnecessary because CSS custom properties handle
    # all theme-specific color resolution. Colors live in ThemeInfo.tokens.


# Category display names for legend grouping
_CATEGORY_LABELS: dict[str, str] = {
    "icons.coverage": "Coverage Status",
    "icons.change": "Change Indicators",
    "badges.status": "Status Badges",
    "badges.level": "Requirement Levels",
    "badges.kind": "Node Types",
    "badges.edge": "Relationship Types",
    "badges.result": "Test Results",
    "buttons.implemented": "Implementation Status",
    "buttons.validation": "Validation Status",
    "validation_tiers": "Active Badge Quality",
}


class LegendCatalog:
    def __init__(
        self,
        themes: list[ThemeInfo],
        entries: list[CatalogEntry],
    ) -> None:
        self.themes = themes
        self.entries = entries
        self._index: dict[str, CatalogEntry] = {e.key: e for e in entries}

    def theme_names(self) -> list[str]:
        return [t.name for t in self.themes]

    def by_key(self, key: str) -> CatalogEntry:
        return self._index[key]  # raises KeyError if missing

    def by_category(self, prefix: str) -> list[CatalogEntry]:
        return [e for e in self.entries if e.category == prefix]

    def grouped_entries(self) -> list[tuple[str, list[CatalogEntry]]]:
        groups: dict[str, list[CatalogEntry]] = {}
        for e in self.entries:
            groups.setdefault(e.category, []).append(e)
        return [
            (_CATEGORY_LABELS.get(cat, cat), entries)
            for cat, entries in groups.items()
        ]

    def css_variables(self) -> str:
        lines: list[str] = []
        for i, theme in enumerate(self.themes):
            if i == 0:
                selector = f":root, .theme-{theme.name}"
            else:
                selector = f".theme-{theme.name}"
            lines.append(f"{selector} {{")
            for token, value in sorted(theme.tokens.items()):
                lines.append(f"    --{token}: {value};")
            lines.append("}")
            lines.append("")
        return "\n".join(lines)


def _load_toml(filename: str) -> dict[str, Any]:
    """Load a TOML file from the elspais.html package."""
    ref = resources.files("elspais.html").joinpath(filename)
    return tomlkit.loads(ref.read_text(encoding="utf-8"))


def _build_catalog(theme_data: dict, help_data: dict) -> LegendCatalog:
    """Join theme.toml and help.toml into a LegendCatalog."""
    # Build themes
    themes: list[ThemeInfo] = []
    for name, tdata in theme_data.get("themes", {}).items():
        themes.append(ThemeInfo(
            name=name,
            label=tdata.get("label", name.title()),
            icon=tdata.get("icon", ""),
            tokens=dict(tdata.get("tokens", {})),
        ))

    # Build entries from categorical sections in theme.toml, joined with help.toml
    entries: list[CatalogEntry] = []
    # Categories are all top-level keys except "themes" and "palette"
    skip = {"themes", "palette"}

    def _walk(theme_section: dict, help_section: dict, prefix: str) -> None:
        for key, val in theme_section.items():
            full_key = f"{prefix}.{key}" if prefix else key
            if isinstance(val, dict) and "css_class" not in val and "symbol" not in val:
                # Nested category — recurse
                _walk(val, help_section.get(key, {}), full_key)
            elif isinstance(val, dict):
                # Leaf entry
                h = help_section.get(key, {}) if isinstance(help_section, dict) else {}
                entries.append(CatalogEntry(
                    key=full_key,
                    category=prefix,
                    symbol=val.get("symbol", ""),
                    css_class=val.get("css_class", ""),
                    color_key=val.get("color_key", ""),
                    label=h.get("label", ""),
                    description=h.get("description", ""),
                    long_description=h.get("long_description", "").strip(),
                ))

    for section_key in theme_data:
        if section_key in skip:
            continue
        _walk(
            {section_key: theme_data[section_key]},
            {section_key: help_data.get(section_key, {})},
            "",
        )

    return LegendCatalog(themes=themes, entries=entries)


@functools.cache
def get_catalog() -> LegendCatalog:
    """Load and cache the LegendCatalog. Lazy — loaded on first call."""
    theme_data = _load_toml("theme.toml")
    help_data = _load_toml("help.toml")
    return _build_catalog(theme_data, help_data)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/core/test_html/test_theme.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Declare TOML files as package data in pyproject.toml**

TOML files are non-Python data files and are NOT automatically included in wheel builds. Add to `pyproject.toml`:

```toml
[tool.hatch.build.targets.wheel.force-include]
"src/elspais/html/theme.toml" = "elspais/html/theme.toml"
"src/elspais/html/help.toml" = "elspais/html/help.toml"
```

Without this, `importlib.resources.files("elspais.html").joinpath("theme.toml")` will raise `FileNotFoundError` in installed wheels (works in dev mode because files are on disk).

- [ ] **Step 6: Commit**

```bash
git add src/elspais/html/theme.toml src/elspais/html/help.toml src/elspais/html/theme.py tests/core/test_html/test_theme.py pyproject.toml
git commit -m "[CUR-1081] feat: add theme.toml, help.toml, and LegendCatalog"
```

---

## Chunk 2: CSS Variable Generation and Integration

### Task 4: Create _variables.css.j2 and integrate into template

**Files:**
- Create: `src/elspais/html/templates/partials/css/_variables.css.j2`
- Modify: `src/elspais/html/templates/trace_unified.html.j2`
- Modify: `src/elspais/html/generator.py`
- Modify: `src/elspais/server/app.py`

- [ ] **Step 1: Create _variables.css.j2**

This template receives the catalog and outputs the CSS custom properties:

```jinja2
{# Partial: _variables.css.j2 — CSS custom properties generated from theme.toml #}
{{ catalog.css_variables() }}
```

- [ ] **Step 2: Pass catalog to template context in generator.py**

In `src/elspais/html/generator.py`, find where `render_template` or `env.get_template().render()` is called. Add `catalog=get_catalog()` to the template context.

Look at `HTMLGenerator.generate()` method — it calls `template.render(...)`. Add the import and pass `catalog`:

```python
from elspais.html.theme import get_catalog
```

In the `render()` call, add `catalog=get_catalog()`.

- [ ] **Step 3: Pass catalog to template context in server/app.py**

In `src/elspais/server/app.py`, find the `index()` route where `render_template()` is called. Add `catalog=get_catalog()` to the template arguments.

```python
from elspais.html.theme import get_catalog
```

- [ ] **Step 4: Include _variables.css.j2 in trace_unified.html.j2**

In `src/elspais/html/templates/trace_unified.html.j2`, add the include right after the opening `<style>` tag (before other CSS includes):

```jinja2
{% include "partials/css/_variables.css.j2" %}
```

This must come before all other CSS so that `var(--token)` references resolve.

- [ ] **Step 5: Verify the CSS variables appear in rendered output**

Start the review server and inspect the page source to confirm `:root` and `.theme-dark` blocks appear with all tokens.

```bash
cd $(git rev-parse --show-toplevel) && python -m elspais review --port 8765 &
sleep 2
curl -s http://localhost:8765/ | grep -c "var(--"
kill %1
```

Expected: Output shows 0 `var(--` references (not yet migrated), but the `:root` block should be present.

- [ ] **Step 6: Commit**

```bash
git add src/elspais/html/templates/partials/css/_variables.css.j2 src/elspais/html/templates/trace_unified.html.j2 src/elspais/html/generator.py src/elspais/server/app.py
git commit -m "[CUR-1081] feat: integrate CSS variable generation into template pipeline"
```

---

### Task 5: Migrate CSS partials to use CSS variables — Status badges and coverage

**Files:**
- Modify: `src/elspais/html/templates/partials/css/_status-badges.css.j2`
- Modify: `src/elspais/html/templates/partials/css/_coverage.css.j2`

- [ ] **Step 1: Migrate _status-badges.css.j2**

Replace every hardcoded color with its `var(--token)` equivalent. Example:

Before:
```css
.status-badge.draft { background: #cfe2ff; color: #084298; }
```

After:
```css
.status-badge.draft { background: var(--status-draft-bg); color: var(--status-draft-text); }
```

Do this for all rules in the file: draft, active, deprecated, proposed, val-green through val-orange, tooltip, and change-indicator.

- [ ] **Step 2: Migrate _coverage.css.j2**

Replace coverage icon colors with variables.

- [ ] **Step 3: Verify no visual regression**

Start the review server, check that status badges and coverage icons render identically in light mode.

- [ ] **Step 4: Commit**

```bash
git add src/elspais/html/templates/partials/css/_status-badges.css.j2 src/elspais/html/templates/partials/css/_coverage.css.j2
git commit -m "[CUR-1081] refactor: migrate status badges and coverage CSS to variables"
```

---

### Task 6: Migrate CSS partials — Nav panel

**Files:**
- Modify: `src/elspais/html/templates/partials/css/_nav-panel.css.j2`

- [ ] **Step 1: Replace all hardcoded colors in _nav-panel.css.j2**

Key replacements:
- Panel bg: `white` -> `var(--surface-bg)`
- Panel border: `#e9ecef` -> `var(--panel-border)`
- Tab colors, tree row colors, ID/title colors, level badge colors, test/result row colors, result badge colors, action button colors

- [ ] **Step 2: Verify nav panel renders correctly**

- [ ] **Step 3: Commit**

```bash
git add src/elspais/html/templates/partials/css/_nav-panel.css.j2
git commit -m "[CUR-1081] refactor: migrate nav panel CSS to variables"
```

---

### Task 7: Migrate CSS partials — Card stack

**Files:**
- Modify: `src/elspais/html/templates/partials/css/_card-stack.css.j2`

- [ ] **Step 1: Replace all hardcoded colors in _card-stack.css.j2**

This is the largest file (~38 colors). Key groups:
- Card backgrounds and borders
- Card ID, title, meta text colors
- Status badges (duplicate of _status-badges.css.j2 — use same tokens)
- Parent link colors
- Kind toggle button colors
- Add relationship form colors
- Assertion label/text colors
- Assertion validation button colors (implemented-yes/no, validation-pass/partial/fail/unknown)
- Code and test panel colors
- Journey card colors

- [ ] **Step 2: Verify cards render correctly**

- [ ] **Step 3: Commit**

```bash
git add src/elspais/html/templates/partials/css/_card-stack.css.j2
git commit -m "[CUR-1081] refactor: migrate card stack CSS to variables"
```

---

### Task 8: Migrate CSS partials — Header, buttons, base

**Files:**
- Modify: `src/elspais/html/templates/partials/css/_header.css.j2`
- Modify: `src/elspais/html/templates/partials/css/_buttons.css.j2`
- Modify: `src/elspais/html/templates/partials/css/_base.css.j2`

- [ ] **Step 1: Migrate _header.css.j2**

Header title, version badge, stat badges (PRD/OPS/DEV/MAIN/TESTS/RESULTS/REPO), separator, search box, edit toggle, hamburger dropdown, theme controls.

- [ ] **Step 2: Migrate _buttons.css.j2**

Base button, primary, warning, danger, unsaved badge.

- [ ] **Step 3: Migrate _base.css.j2**

Body text and background colors.

- [ ] **Step 4: Verify header and buttons render correctly**

- [ ] **Step 5: Commit**

```bash
git add src/elspais/html/templates/partials/css/_header.css.j2 src/elspais/html/templates/partials/css/_buttons.css.j2 src/elspais/html/templates/partials/css/_base.css.j2
git commit -m "[CUR-1081] refactor: migrate header, buttons, base CSS to variables"
```

---

### Task 9: Migrate CSS partials — Remaining files

**Files:**
- Modify: `src/elspais/html/templates/partials/css/_toast.css.j2`
- Modify: `src/elspais/html/templates/partials/css/_dividers.css.j2`
- Modify: `src/elspais/html/templates/partials/css/_file-viewer.css.j2`
- Modify: `src/elspais/html/templates/partials/css/_toolbar.css.j2`
- Modify: `src/elspais/html/templates/partials/css/_journey.css.j2`
- Modify: `src/elspais/html/templates/partials/css/_legend.css.j2`
- Modify: `src/elspais/html/templates/partials/css/_edit-mode.css.j2`
- Modify: `src/elspais/html/templates/partials/css/_req-search-dropdown.css.j2`
- Modify: `src/elspais/html/templates/partials/css/_topic-tags.css.j2`

- [ ] **Step 1: Migrate all remaining CSS files**

For each file, replace hardcoded colors with `var(--token)` references using the same token names established in theme.toml. Group the work but commit all together since these are smaller files.

Key mappings:
- Toast: success/error/info bg/text/border tokens
- Dividers: border-color and primary tokens
- File viewer: surface-bg, panel-border, highlight tokens, line number tokens
- Toolbar: input-border, primary, muted-text tokens
- Journey: surface-bg, primary, border-color, muted-text tokens
- Legend: surface-bg, muted-text tokens
- Edit mode: primary-soft, warning/danger tokens
- Req search dropdown: primary, surface-bg, border-color tokens
- Topic tags: muted-text

- [ ] **Step 2: Verify all components render correctly in light mode**

- [ ] **Step 3: Commit**

```bash
git add src/elspais/html/templates/partials/css/_toast.css.j2 src/elspais/html/templates/partials/css/_dividers.css.j2 src/elspais/html/templates/partials/css/_file-viewer.css.j2 src/elspais/html/templates/partials/css/_toolbar.css.j2 src/elspais/html/templates/partials/css/_journey.css.j2 src/elspais/html/templates/partials/css/_legend.css.j2 src/elspais/html/templates/partials/css/_edit-mode.css.j2 src/elspais/html/templates/partials/css/_req-search-dropdown.css.j2 src/elspais/html/templates/partials/css/_topic-tags.css.j2
git commit -m "[CUR-1081] refactor: migrate remaining CSS partials to variables"
```

---

## Chunk 3: Theme Switching and Dark Theme Deletion

### Task 10: Update theme switching JS and delete dark theme CSS

**Files:**
- Modify: `src/elspais/html/templates/trace_unified.html.j2` (JS section)
- Modify: `src/elspais/html/templates/partials/_header.html.j2`
- Delete: `src/elspais/html/templates/partials/css/_dark-theme.css.j2`

- [ ] **Step 1: Update applyTheme() in trace_unified.html.j2**

Find the `applyTheme()` function (~line 276) and the early theme init block (~line 202). Replace both with multi-theme logic:

```javascript
function applyTheme() {
    var theme = editState.theme || 'system';
    var html = document.documentElement;
    // Remove all theme classes
    html.className = html.className.replace(/\btheme-\S+/g, '');
    var resolved = theme;
    if (theme === 'system') {
        resolved = (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) ? 'dark' : 'light';
    }
    html.classList.add('theme-' + resolved);
}
```

Update the early init block similarly.

- [ ] **Step 2: Update theme buttons in _header.html.j2**

Replace the three hardcoded theme buttons with a loop over themes from the catalog. The catalog is passed as template context.

```jinja2
{% for theme in catalog.themes %}
<button class="btn theme-btn"
        data-theme="{{ theme.name }}"
        onclick="event.stopPropagation(); setTheme('{{ theme.name }}')"
        title="{{ theme.label }} theme">{{ theme.icon }}</button>
{% endfor %}
<button class="btn theme-btn active" data-theme="system"
        onclick="event.stopPropagation(); setTheme('system')"
        title="System theme">&#9881;</button>
```

Note: "system" is NOT a theme in the TOML — it's a special value meaning "follow OS preference". It is hardcoded as a separate button after the catalog theme loop. The `active` class default on `system` matches the current behavior. The `setTheme()` JS handles toggling `active` classes on all buttons.

- [ ] **Step 3: Remove dark-theme include from trace_unified.html.j2**

Find and remove the line:
```jinja2
{% include "partials/css/_dark-theme.css.j2" %}
```

- [ ] **Step 4: Delete _dark-theme.css.j2**

```bash
git rm src/elspais/html/templates/partials/css/_dark-theme.css.j2
```

- [ ] **Step 5: Update Pygments dark-mode CSS scope**

The existing code uses `.dark-theme .highlight` as the Pygments CSS scope for dark mode. This must change to `.theme-dark .highlight` to match the new class naming.

Check and update in:
- `src/elspais/server/app.py` — search for `dark-theme` in the Pygments CSS scope string
- `src/elspais/html/generator.py` — search for `dark-theme` in any Pygments scope

- [ ] **Step 6: Verify both light and dark themes work**

Start the review server, toggle between light and dark themes. Verify:
- All components render with correct colors in both themes
- Theme selection persists across page reload
- System theme follows OS preference

- [ ] **Step 7: Commit**

```bash
git add src/elspais/html/templates/trace_unified.html.j2 src/elspais/html/templates/partials/_header.html.j2 src/elspais/server/app.py src/elspais/html/generator.py
git commit -m "[CUR-1081] feat: multi-theme switching with CSS variables, delete dark-theme.css.j2"
```

---

## Chunk 4: Legend Modal and compute_validation_color

### Task 11: Rewrite legend modal to use catalog

**Files:**
- Modify: `src/elspais/html/templates/partials/_legend_modal.html.j2`

- [ ] **Step 1: Rewrite _legend_modal.html.j2**

Replace the static HTML with a loop over catalog entries:

```jinja2
{# Partial: _legend_modal.html.j2 — Legend overlay modal generated from LegendCatalog #}

<div class="modal-overlay" id="legend-modal" onclick="closeLegendOnOverlay(event)">
    <div class="modal" onclick="event.stopPropagation()">
        <div class="modal-header">
            <h3 class="modal-title">Legend</h3>
            <button class="modal-close" onclick="toggleLegend()">&times;</button>
        </div>

        {% for cat_name, entries in catalog.grouped_entries() %}
        <div class="legend-section">
            <h4>{{ cat_name }}</h4>
            {% for e in entries %}
            <div class="legend-item" title="{{ e.long_description }}">
                {% if e.category == 'validation_tiers' %}
                <span class="status-badge active {{ e.css_class }}">{{ e.label }}</span>
                {% elif e.category.startswith('badges.') %}
                <span class="{{ e.css_class }}">{{ e.symbol or e.label }}</span>
                {% elif e.symbol %}
                <span class="legend-icon {{ e.css_class }}">{{ e.symbol }}</span>
                {% else %}
                <span class="legend-icon">{{ e.label }}</span>
                {% endif %}
                <span>{{ e.description }}</span>
            </div>
            {% endfor %}
        </div>
        {% endfor %}
    </div>
</div>
```

- [ ] **Step 2: Verify legend renders all categories**

Open the review server, click the legend button, confirm all categories appear with correct icons and descriptions.

- [ ] **Step 3: Commit**

```bash
git add src/elspais/html/templates/partials/_legend_modal.html.j2
git commit -m "[CUR-1081] feat: legend modal generated from LegendCatalog"
```

---

### Task 12: Integrate catalog with compute_validation_color

**Files:**
- Modify: `src/elspais/html/generator.py`
- Test: `tests/core/test_html/test_theme.py` (add tests)

- [ ] **Step 1: Write failing tests for compute_validation_color integration**

Add to `tests/core/test_html/test_theme.py`. These tests call the actual `compute_validation_color` function and verify it returns descriptions from the catalog rather than hardcoded strings.

```python
from elspais.html.generator import compute_validation_color
from elspais.graph.metrics import RollupMetrics
from tests.core.graph_test_helpers import build_graph, make_requirement


class TestComputeValidationColorCatalog:
    """Test that compute_validation_color returns catalog descriptions."""

    def _make_active_node_with_metrics(self, **rollup_kwargs):
        """Create an Active requirement node with specified RollupMetrics."""
        req = make_requirement("REQ-p00001", title="Test", status="Active",
                               assertions=[("A", "Assert A")])
        graph = build_graph(req)
        node = graph.find_by_id("REQ-p00001")
        metrics = RollupMetrics(**rollup_kwargs)
        node.set_metric("rollup_metrics", metrics)
        return node

    def test_REQ_p00006_A_green_description_from_catalog(self):
        """Full-direct tier returns catalog description, not hardcoded string."""
        catalog = get_catalog()
        expected_desc = catalog.by_key("validation_tiers.full-direct").description
        node = self._make_active_node_with_metrics(
            total_assertions=1, coverage_pct=100, validated=1,
            has_failures=False, direct_covered=1)
        color, desc = compute_validation_color(node)
        assert color == "green"
        assert desc == expected_desc

    def test_REQ_p00006_A_red_description_from_catalog(self):
        """Failing tier returns catalog description."""
        catalog = get_catalog()
        expected_desc = catalog.by_key("validation_tiers.failing").description
        node = self._make_active_node_with_metrics(
            total_assertions=1, has_failures=True)
        color, desc = compute_validation_color(node)
        assert color == "red"
        assert desc == expected_desc

    def test_REQ_p00006_A_catalog_color_keys_are_consistent(self):
        """All validation tier color_keys match their CSS class suffix."""
        catalog = get_catalog()
        tier_map = {
            "full-direct": "green",
            "full-indirect": "yellow-green",
            "partial": "yellow",
            "failing": "red",
            "anomalous": "orange",
        }
        for tier_key, color_key in tier_map.items():
            entry = catalog.by_key(f"validation_tiers.{tier_key}")
            assert entry.color_key == color_key
```

- [ ] **Step 2: Run tests to verify they FAIL**

```bash
pytest tests/core/test_html/test_theme.py::TestComputeValidationColorCatalog -v
```

Expected: FAIL — `compute_validation_color` currently returns hardcoded strings, not catalog descriptions.

- [ ] **Step 3: Update compute_validation_color to use catalog descriptions**

In `src/elspais/html/generator.py`, modify `compute_validation_color()` to look up descriptions from the catalog instead of hardcoding them:

```python
from elspais.html.theme import get_catalog

def compute_validation_color(node: GraphNode) -> tuple[str, str]:
    catalog = get_catalog()
    # ... existing logic unchanged ...
    # Where it currently returns ("green", "All N assertions covered and validated"),
    # change to:
    entry = catalog.by_key("validation_tiers.full-direct")
    return (entry.color_key, entry.description)
    # etc. for each tier
```

Keep the existing branching logic (rollup metrics checks) but replace the hardcoded description strings with catalog lookups. For descriptions that include dynamic values (e.g., `f"All {n} assertions covered and validated"`), use the catalog description as a template or prefix, appending the dynamic part.

- [ ] **Step 4: Run full test suite**

```bash
pytest tests/core/test_html/ -v
```

Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/elspais/html/generator.py tests/core/test_html/test_theme.py
git commit -m "[CUR-1081] refactor: compute_validation_color uses catalog descriptions"
```

---

## Chunk 5: Title Change and Cleanup

### Task 13: Update page title (Chore #2)

**Files:**
- Modify: `src/elspais/html/templates/trace_unified.html.j2`
- Modify: `src/elspais/html/generator.py`
- Modify: `src/elspais/server/app.py`

- [ ] **Step 1: Update the template title**

In `src/elspais/html/templates/trace_unified.html.j2`, change lines 8-12:

```jinja2
{% if mode == 'edit' %}
<title>Elspais {{ version }} ({{ repo_name }}) -- PRD: {{ stats.prd_count }} OPS: {{ stats.ops_count }} DEV: {{ stats.dev_count }}</title>
{% else %}
<title>Elspais {{ version }} -- Requirements Traceability</title>
{% endif %}
```

Note: The static HTML (view mode) omits `repo_name` because it may be viewed offline without server context. The edit mode (Flask server) always has `repo_name` available.

- [ ] **Step 2: Pass repo_name from server/app.py**

In the Flask index route, extract repo name and pass to template:

```python
import os
repo_name = os.path.basename(str(self.repo_root))
```

Add `repo_name=repo_name` to the `render_template()` call.

- [ ] **Step 3: Pass repo_name from generator.py**

In `HTMLGenerator.generate()`, extract repo name from the output path or repo root:

```python
import os
repo_name = os.path.basename(str(self.repo_root))
```

Add `repo_name=repo_name` to the `template.render()` call.

- [ ] **Step 4: Verify title appears correctly**

Start the review server and check the browser tab title.

- [ ] **Step 5: Commit**

```bash
git add src/elspais/html/templates/trace_unified.html.j2 src/elspais/html/generator.py src/elspais/server/app.py
git commit -m "[CUR-1081] feat: dynamic page title with version, repo name, and level counts"
```

---

### Task 14: Update KNOWN_ISSUES, CHANGELOG, version

**Files:**
- Modify: `KNOWN_ISSUES.md`
- Modify: `CHANGELOG.md`
- Modify: `pyproject.toml`
- Modify: `CLAUDE.md` (if architectural changes need documenting)

- [ ] **Step 1: Mark chores as done in KNOWN_ISSUES.md**

Change:
```
[ ] Chore: Update the Legend
[ ] Chore: Trace Edit title -> Elspais vx.x.x (repo name) PRD: xyz OPS: pdq ...
```
To:
```
[x] Chore: Update the Legend
[x] Chore: Trace Edit title -> Elspais vx.x.x (repo name) PRD: xyz OPS: pdq ...
```

- [ ] **Step 2: Update CHANGELOG.md**

Add entry for this release:
- feat: Unified theme catalog (theme.toml + help.toml) with CSS custom properties
- feat: Legend modal generated from catalog — documents all icons, colors, badges
- feat: Multi-theme support — arbitrary named themes beyond light/dark
- feat: Dynamic page title with version, repo name, and level counts
- refactor: All CSS colors use CSS custom properties (single source of truth)
- delete: Removed _dark-theme.css.j2 (replaced by CSS variables)

- [ ] **Step 3: Bump version in pyproject.toml**

- [ ] **Step 4: Update CLAUDE.md if needed**

Add a note about `theme.toml`/`help.toml`/`theme.py` as the source of truth for UI colors and help text.

- [ ] **Step 5: Run full test suite**

```bash
pytest -m "" -v
```

Expected: All tests pass (unit + e2e).

- [ ] **Step 6: Commit**

```bash
git add KNOWN_ISSUES.md CHANGELOG.md pyproject.toml CLAUDE.md
git commit -m "[CUR-1081] chore: update docs, changelog, version for theme catalog"
```

---

## Execution Notes

### Risk Mitigation

1. **Visual regression is the main risk.** After each CSS migration task (Tasks 5-9), visually verify both light and dark themes before proceeding.

2. **The dark theme deletion (Task 10) should only happen after ALL CSS partials are migrated.** If any partial still has hardcoded colors, dark mode will break for those components.

3. **Token naming consistency is critical.** Use the exact token names from theme.toml throughout. A typo in a `var(--token)` reference will silently fall back to the initial value (usually transparent/inherited), breaking the UI.

### Dependencies

```text
Task 1-2 (TOML files) -> Task 3 (theme.py) -> Task 4 (integration)
Task 4 -> Tasks 5-9 (CSS migration, can be parallelized)
Tasks 5-9 -> Task 10 (theme switching + dark theme deletion)
Task 10 -> Task 11 (legend modal)
Task 3 -> Task 12 (compute_validation_color, can parallel with CSS work)
Task 4 -> Task 13 (title change, independent of CSS migration)
All tasks -> Task 14 (cleanup)
```

### Parallelizable Work

Tasks 5-9 (CSS migration) are independent of each other and can be done in parallel by separate agents. Task 12 and Task 13 are independent of the CSS migration and can run in parallel with Tasks 5-9.
