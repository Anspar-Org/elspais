# Theme & Help Catalog Design

**Date:** 2026-03-09
**Scope:** KNOWN_ISSUES chores #1 (Update the Legend) and #2 (Trace Edit title)

## Problem

The trace view UI has grown beyond what the legend documents. Colors, icons, badges, and validation states are hardcoded across multiple CSS template files with no single source of truth. Dark theme colors are duplicated in a separate file. The legend modal is static HTML that drifts from the actual UI. The page title is static and uninformative.

## Solution

Two TOML data files define all visual semantics and help text. A Python module joins them into a `LegendCatalog` that feeds CSS generation, the legend modal, and future help systems. CSS custom properties replace all hardcoded colors, enabling arbitrary named themes beyond light/dark.

## Architecture

```text
theme.toml + help.toml
        |
        v
    theme.py  -->  LegendCatalog
        |
        +---> _variables.css.j2 (NEW: :root + .theme-* CSS custom properties)
        +---> _legend_modal.html.j2 (legend content from catalog entries)
        +---> existing CSS partials (use var(--token) instead of hardcoded hex)
        +---> generator.py / app.py (reuse descriptions, pass catalog to templates)
        |
        x---> _dark-theme.css.j2 (DELETED: fully replaced by _variables.css.j2)
```

## File Inventory

### New Files

| File | Location | Purpose |
|------|----------|---------|
| `theme.toml` | `src/elspais/html/` | Color palettes, symbols, CSS classes |
| `help.toml` | `src/elspais/html/` | Labels, short descriptions, long descriptions |
| `theme.py` | `src/elspais/html/` | Reads both TOML files, exposes `LegendCatalog` |
| `_variables.css.j2` | `templates/partials/css/` | Generated CSS custom properties per theme |

### Deleted Files

| File | Reason |
|------|--------|
| `_dark-theme.css.j2` | All color overrides replaced by CSS variables |

### Modified Files

| File | Change |
|------|--------|
| `_status-badges.css.j2` | Hardcoded hex to `var(--token)` |
| `_card-stack.css.j2` | Hardcoded hex to `var(--token)` |
| `_nav-panel.css.j2` | Hardcoded hex to `var(--token)` |
| `_base.css.j2` | Hardcoded hex to `var(--token)` |
| `_coverage.css.j2` | Hardcoded hex to `var(--token)` |
| `_legend.css.j2` | Hardcoded hex to `var(--token)` |
| `_legend_modal.html.j2` | Rewritten to loop over catalog entries |
| `_header.html.j2` | Theme buttons generated from catalog theme list |
| `trace_unified.html.j2` | Include `_variables.css.j2`, remove dark-theme include, update `setTheme`/`applyTheme` JS, update `<title>` |
| `generator.py` | Import catalog, pass to template context (including `repo_name`), reuse descriptions in `compute_validation_color` |
| `server/app.py` | Pass catalog and `repo_name` to template context |

**Note:** Every CSS partial that currently has colors overridden in `_dark-theme.css.j2` must migrate those colors to `var(--token)` references. The dark theme file overrides colors for: body, header, search, nav panel, nav tree, toolbar, stat badges, dividers, card stack, cards, assertions, parent/child links, status badges, buttons, edit mode, file viewer, toasts, legend modal, hamburger menu, and journey cards. All of these become CSS variable references in their respective partials.

## `theme.toml` Structure

### Palette

Reusable named color sets with per-theme variants. The first theme listed is the default and maps to `:root`.

```toml
[palette.green]
bg = "#198754"
text = "#fff"

[palette.green.dark]
bg = "#146c43"
text = "#d1e7dd"
```

### Themes

Named themes with labels and icons for the menu.

```toml
[themes.light]
label = "Light"
icon = "&#9728;"

[themes.light.tokens]
body-bg = "#ffffff"
body-text = "#212529"
# ... structural tokens (panels, borders, inputs, etc.)

[themes.dark]
label = "Dark"
icon = "&#9790;"

[themes.dark.tokens]
body-bg = "#1a1d21"
body-text = "#e9ecef"
# ...
```

Adding a new theme (e.g., synthwave, high-contrast) means adding a `[themes.<name>]` section with its token values. The menu and CSS generation pick it up automatically.

### Categorical Entries

Map semantic keys to palette references, CSS classes, and symbols.

```toml
[icons.coverage.full]
symbol = "&#x25CF;"
css_class = "coverage-icon full"
palette = "green"

[badges.status.active]
css_class = "status-badge active"
palette = "green"

[buttons.validation.pass]
css_class = "assertion-validation-btn validation-pass"
palette = "green"

[validation_tiers.full-direct]
css_class = "val-green"
color_key = "green"           # returned by compute_validation_color()
palette = "green"
```

**Note on `color_key`:** `compute_validation_color()` returns a tuple of `(color_key, description)` where `color_key` is the suffix used in CSS classes (e.g., `"green"` becomes `.val-green`). The `color_key` field stores this value directly, avoiding fragile string manipulation of `css_class`.

### Categories

| Category | Keys | Purpose |
|----------|------|---------|
| `icons.coverage` | full, partial, none, warning | Coverage status icons |
| `icons.change` | changed | Change indicator diamond |
| `badges.status` | draft, active, deprecated, proposed | Requirement status badges |
| `badges.level` | prd, ops, dev | Requirement level badges |
| `badges.kind` | code, test, result, journey | Node kind badges |
| `badges.edge` | implements, refines | Edge type labels |
| `badges.result` | passed, failed, error, skipped | Test result badges |
| `buttons.implemented` | yes, no | Assertion implementation button states |
| `buttons.validation` | pass, partial, fail, unknown | Assertion validation button states |
| `validation_tiers` | full-direct, full-indirect, partial, failing, anomalous | Active status badge color overlays |

## `help.toml` Structure

Same categories and keys as `theme.toml`, text only. Each entry has:

- `label` — Short display name (e.g., "Full Direct")
- `description` — One-line summary (e.g., "All assertions covered and validated")
- `long_description` — Multi-line explanation for help systems

```toml
[validation_tiers.full-direct]
label = "Full Direct"
description = "All assertions covered and validated"
long_description = """All assertions have direct code implementations and all
tests are passing. This is the highest quality tier."""

[validation_tiers.full-indirect]
label = "Full Indirect"
description = "All assertions validated (including indirect)"
long_description = """All assertions are validated, but some coverage comes
through inherited implementations from child requirements rather than
direct code references."""

[validation_tiers.partial]
label = "Partial"
description = "Some coverage, no failures"
long_description = """Some assertions have implementations and passing tests,
but not all assertions are fully covered yet."""

[validation_tiers.failing]
label = "Failing"
description = "Test failures detected"
long_description = """One or more tests referencing this requirement are failing.
This takes priority over coverage level."""

[validation_tiers.anomalous]
label = "Anomalous"
description = "Unexpected coverage gaps"
long_description = """Tests exist but results are missing, or tests exist but
no code implementation is found. Investigate the test/code linkage."""
```

Internationalization: `help.fr.toml`, `help.de.toml`, etc. Same keys, different text.

## `theme.py` — `LegendCatalog`

```python
@dataclass
class ThemeColor:
    bg: str
    text: str
    border: str = ""

@dataclass
class ThemeInfo:
    name: str                  # "light", "dark", "synthwave"
    label: str                 # "Light", "Dark", "Synthwave"
    icon: str                  # HTML entity for menu button
    tokens: dict[str, str]     # token_name -> color value

@dataclass
class CatalogEntry:
    key: str                          # "icons.coverage.full"
    category: str                     # "icons.coverage"
    symbol: str                       # HTML entity or empty
    css_class: str
    label: str                        # from help.toml
    description: str                  # from help.toml
    long_description: str             # from help.toml
    colors: dict[str, ThemeColor]     # theme_name -> colors

class LegendCatalog:
    themes: list[ThemeInfo]
    entries: list[CatalogEntry]

    def by_category(self, prefix: str) -> list[CatalogEntry]: ...
    def by_key(self, key: str) -> CatalogEntry: ...
    def css_variables(self) -> str: ...        # :root + .theme-* blocks
    def theme_names(self) -> list[str]: ...
    def grouped_entries(self) -> list[tuple[str, list[CatalogEntry]]]: ...
```

Loads TOML files lazily on first access using `importlib.resources` to locate them within the `elspais.html` package. The TOML files must be included as package data. A module-level `get_catalog()` function caches the result after first load. If files are missing or malformed, raises a clear error with the expected file path.

## CSS Variable Generation

`_variables.css.j2` receives the catalog and generates:

```css
:root, .theme-light {
    --body-bg: #ffffff;
    --body-text: #212529;
    --status-active-bg: #d1e7dd;
    --status-active-text: #0f5132;
    /* ... all tokens */
}

.theme-dark {
    --body-bg: #1a1d21;
    --body-text: #e9ecef;
    --status-active-bg: #1a3328;
    --status-active-text: #5cb85c;
    /* ... */
}
```

Existing CSS partials change from `background: #d1e7dd` to `background: var(--status-active-bg)`.

## Theme Switching

### JS Changes

`applyTheme()` changes from toggling `dark-theme` class to:

```javascript
html.className = html.className.replace(/\btheme-\S+/g, '');
html.classList.add('theme-' + resolved);
```

Where `resolved` handles the "system" preference by checking `prefers-color-scheme` and falling back to the first theme (light).

### Menu

The hamburger menu theme buttons are generated from the catalog's theme list instead of three hardcoded buttons. The selected theme is persisted in `editState.theme` via `localStorage` (existing mechanism).

## Legend Modal

`_legend_modal.html.j2` becomes a loop over catalog entries:

```jinja2
{% for cat_name, entries in catalog.grouped_entries() %}
<div class="legend-section">
    <h4>{{ cat_name }}</h4>
    {% for e in entries %}
    <div class="legend-item" title="{{ e.long_description }}">
        <span class="legend-icon {{ e.css_class }}">{{ e.symbol }}</span>
        <span><strong>{{ e.label }}</strong> -- {{ e.description }}</span>
    </div>
    {% endfor %}
</div>
{% endfor %}
```

The long description is available on hover via `title` attribute, and accessible programmatically for a future "More Help" feature.

**Validation tier rendering:** Validation tier entries render in the legend as sample status badges with both the base class and the modifier: `<span class="status-badge active {{ e.css_class }}">`. This shows the actual color the user would see on an Active requirement at that validation level.

## Title Change (Chore #2)

Simple template edit in `trace_unified.html.j2`:

```jinja2
{% if mode == 'edit' %}
<title>Elspais {{ version }} ({{ repo_name }}) -- PRD: {{ stats.prd_count }} OPS: {{ stats.ops_count }} DEV: {{ stats.dev_count }}</title>
{% else %}
<title>Elspais {{ version }} -- Requirements Traceability</title>
{% endif %}
```

`repo_name` is extracted from `base_path` via `os.path.basename()`. Both code paths must provide it:
- **Flask server** (`server/app.py`): extracts from its `base_path` argument and passes to the template
- **Static HTML** (`generator.py`): accepts `repo_name` as an optional parameter (defaults to basename of the output path or working directory)

## Integration with `compute_validation_color`

`compute_validation_color()` in `generator.py` currently returns hardcoded description strings. These are replaced with lookups from the catalog:

```python
catalog = get_catalog()
entry = catalog.by_key("validation_tiers.full-direct")
return (entry.color_key, entry.description)
```

The `color_key` field provides the exact string expected by the template (e.g., `"green"` which becomes `.val-green`). This ensures the tooltip text on status badges matches the legend descriptions exactly.

## Testing

- Unit tests for `theme.py`: TOML parsing, catalog joining, CSS variable generation
- Unit tests for `compute_validation_color`: verify descriptions match catalog
- Visual regression: verify light and dark themes render correctly after migration
- Legend modal: verify all categories render with correct entries

## Future Extensions

- **Custom themes**: Users add `[themes.synthwave]` sections to `theme.toml`
- **Help system**: The "More Help" feature (KNOWN_ISSUES #4) can consume `long_description` from the catalog
- **Internationalization**: `help.fr.toml` etc. with same keys, different text
- **Theme sharing**: Theme sections could be extracted to separate files
