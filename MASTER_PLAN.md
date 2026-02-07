# MASTER PLAN — Inline File Viewer Panel for Trace View

**Branch**: `feature/CUR-514-viewtrace-port`
**CURRENT_ASSERTIONS**: REQ-p00006-C

## Goal

Add a right-side file viewer column to `elspais trace view` that displays source files inline (as rendered markdown with line numbers), instead of opening them in an external application (VS Code). One line number per source line, even when the line wraps in the display. Files with known syntaxes (Python, Dart, YAML, JSON, XML, etc.) are displayed with syntax highlighting.

## Architecture Overview

Currently, all file links in the trace view use `vscode://file/PATH:LINE:COL` URIs to open files externally. The new design adds:

1. **A resizable right-side panel** (`file-viewer-panel`) that sits alongside the existing trace table
2. **File content embedded** as JSON in the HTML (leveraging the existing `--embed-content` mechanism)
3. **Syntax highlighting** via Pygments (Python-side, at generation time) — supports 500+ languages
4. **Markdown rendering** for `.md` files — rendered as formatted HTML with a toggle for source view
5. **Line numbers** rendered as a gutter column — one number per source line, stable even when text wraps
6. **Click-to-view** behavior on existing file links (intercept `vscode://` links, display inline instead)

### Layout Change

```
BEFORE:
┌──────────────────────────────────────────┐
│  Header / Toolbar / Tabs                 │
├──────────────────────────────────────────┤
│  Trace Table (full width)                │
│                                          │
└──────────────────────────────────────────┘

AFTER:
┌──────────────────────────────────────────┐
│  Header / Toolbar / Tabs                 │
├─────────────────────┬────────────────────┤
│  Trace Table        │  File Viewer       │
│  (resizable left)   │  (resizable right) │
│                     │  ┌─ file path ───┐ │
│                     │  │ 1 │ # Header  │ │
│                     │  │ 2 │ Content.. │ │
│                     │  │ 3 │           │ │
│                     │  └────────────────┘ │
└─────────────────────┴────────────────────┘
```

## Phases

### Phase 1: Embed File Content with Syntax Highlighting (Python)

**Goal**: Collect source file contents, apply syntax highlighting with Pygments, and pass pre-highlighted HTML to the Jinja2 template as embedded JSON.

**Files to modify**:
- `src/elspais/html/generator.py`
- `pyproject.toml`

**Steps**:

- [x] Add `pygments>=2.0` to the `trace-view` optional dependency group in `pyproject.toml`
  - Also add to `trace-review` and `all` groups

- [x] Add `_collect_source_files()` method to `HTMLGenerator`
  - Walk graph nodes, collect unique `source.path` values
  - Read each file's content (text only, skip binaries via `is_binary` heuristic)
  - Respect a max file size limit (e.g., 500KB) to keep HTML manageable
  - Detect language from file extension using `pygments.lexers.get_lexer_for_filename()`
  - For each file, produce **two representations**:
    - `highlighted_lines`: list of pre-highlighted HTML strings (one per source line), via Pygments `HtmlFormatter(nowrap=True)` — each line gets its own highlight pass or the full output is split by `\n`
    - `raw_content`: plain text (for markdown rendered view toggle)
  - Store as `{path: {lines: [...], language: "python", raw: "..."}}` dict
  - For `.md` files, also produce `rendered_html` via Python `markdown` lib or simple Jinja2 rendering (optional — can defer to JS-side)

- [x] Add `_get_pygments_css()` helper
  - Generate the Pygments CSS theme (e.g., `HtmlFormatter(style='default').get_style_defs('.highlight')`)
  - This CSS is embedded once in the template `<style>` block

- [x] Update `generate()` to call `_collect_source_files()` and pass `source_files` + `pygments_css` to template render context
  - Only collect when `embed_content=True` (keeps default behavior lightweight)
  - Graceful fallback if Pygments not installed: embed raw content without highlighting

- [x] Add `source_files` and `pygments_css` to template render kwargs

**Pygments approach rationale**: Highlighting happens once at generation time, so the embedded JSON contains pre-rendered HTML spans. The browser just inserts them — no JS highlighting library needed. This keeps the self-contained HTML fast and dependency-free on the client side.

### Phase 2: File Viewer Panel HTML + CSS (Template)

**Goal**: Add the right-side panel structure with proper CSS for split-pane layout.

**Files to modify**:
- `src/elspais/html/templates/trace_view.html.j2`

**Steps**:

- [x] Add `<div class="file-viewer-panel">` after the main content area
  - Header bar: file path display, close button, "Open in VS Code" fallback link
  - Content area: scrollable `<pre>` with line-number gutter
  - Initially hidden (panel closed state)

- [x] Wrap existing `main-content` and new panel in a `<div class="split-layout">` flex container

- [x] CSS for split layout:
  - `.split-layout` — `display: flex; height: calc(100vh - header/toolbar height)`
  - `.main-content` — `flex: 1; overflow-y: auto; min-width: 400px`
  - `.file-viewer-panel` — `width: 50%; overflow-y: auto; border-left: 1px solid #e9ecef`
  - `.file-viewer-panel.closed` — `display: none` (table gets full width)

- [x] CSS for line-number gutter:
  - Use CSS grid or table layout: gutter column (fixed-width) + content column
  - Line numbers: `user-select: none`, monospace, right-aligned, muted color
  - Content: `white-space: pre-wrap; word-wrap: break-word` for wrapping
  - Each line is its own row so line numbers never duplicate on wrap

- [x] CSS for resizable divider:
  - A drag handle between left/right panels (vertical bar, cursor: col-resize)
  - Visual affordance (dots or grip pattern)

- [x] Embed Pygments CSS theme:
  - `{{ pygments_css }}` injected into the `<style>` block, scoped under `.file-viewer-panel .highlight`
  - Uses a light theme (e.g., `default` or `friendly`) that matches the existing trace view palette

- [x] Embed source files JSON:
  - `<script type="application/json" id="source-files">{{ source_files | tojson }}</script>`
  - Each file entry contains pre-highlighted HTML lines (from Pygments) — browser just inserts them

### Phase 3: JavaScript Interactivity

**Goal**: Wire up click handlers, file display logic, resizing, and line highlighting.

**Files to modify**:
- `src/elspais/html/templates/trace_view.html.j2` (JS section)

**Steps**:

- [x] **File display function** `showFile(filePath, lineNumber)`:
  - Look up file content from embedded `source-files` JSON
  - Render into viewer panel with line-numbered gutter
  - Scroll to and highlight the target line number
  - Open the panel if closed
  - Update header bar with file path and line info

- [x] **Line number rendering with syntax highlighting**:
  - Read pre-highlighted lines from embedded JSON (Pygments already applied)
  - Create one `<div class="source-line">` per line
  - Each div contains: `<span class="line-num">N</span><code class="line-content highlight">...pygments spans...</code>`
  - Line numbers are stable — wrapping text doesn't affect numbering
  - No HTML escaping needed — Pygments output is already safe
  - Unsupported/unknown file types fall back to plain text (HTML-escaped)

- [x] **All files show line numbers**:
  - Every file type (code, markdown, config, test output) displays with a line-number gutter
  - Line numbers are always visible regardless of view mode

- [x] **Markdown rendering** for `.md` files:
  - Default view: rendered markdown alongside line-number gutter (line numbers correspond to source lines)
  - Toggle button: switch between "Rendered" and "Source" views
  - Source view uses Pygments-highlighted markdown syntax with line numbers
  - For code files: always show syntax-highlighted source with line numbers (no rendered view toggle)

- [x] **Intercept file links**:
  - Add click handler to all `a[href^="vscode://"]` links
  - Extract file path and line from `vscode://file/PATH:LINE:COL` URI
  - Call `showFile(path, line)` instead of navigating
  - Keep VS Code link available as a secondary action (button in viewer header)

- [x] **Resizable divider**:
  - Mousedown on divider starts resize mode
  - Mousemove adjusts flex-basis of left/right panels
  - Mouseup ends resize
  - Persist split ratio in cookie (alongside existing cookie persistence)

- [x] **Line highlighting**:
  - Add `.highlighted` class to target line
  - Smooth scroll to line with offset
  - Visual: yellow/gold background fade effect

- [x] **Close panel**: Button to hide viewer, restoring full-width table

- [x] **State persistence**: Remember panel open/closed and width ratio in cookies

### Phase 4: Fallback for Non-Embedded Mode

**Goal**: Graceful degradation when `--embed-content` is not used.

**Steps**:

- [x] When `source_files` is empty (no `--embed-content`):
  - File links retain original `vscode://` behavior (open externally)
  - No panel is shown
  - OR: Show panel with "File content not available — regenerate with --embed-content" message

- [x] Consider making `--embed-content` the default when `--view` is used (since the viewer panel is the primary interaction model)

### Phase 5: Polish and Testing

**Steps**:

- [x] Test syntax highlighting with various file types: `.py`, `.dart`, `.toml`, `.yml`, `.json`, `.xml` (JUnit), `.md`
- [x] Verify Pygments produces correct language-specific tokens (keywords, strings, comments colored distinctly)
- [x] Test with large files (500+ lines) — verify scroll performance
- [x] Test line wrapping behavior — confirm one line number per source line
- [x] Test with fixtures: `hht-like`, `assertions`, `fda-style`
- [x] Verify no regressions in non-embedded mode
- [x] Verify graceful fallback when Pygments is not installed (plain text display)
- [x] Mobile/responsive: collapse panel below a breakpoint
- [x] Keyboard navigation: Escape to close panel
- [x] Write integration tests for `_collect_source_files()` method (with and without Pygments)

### Phase 6: Commit and Push

- [x] Commit with `[CUR-514]` prefix
- [x] Push branch

## Key Design Decisions

1. **Self-contained HTML**: All file content embedded as JSON, no server needed
2. **Pygments for syntax highlighting**: Runs at generation time in Python — browser receives pre-rendered HTML spans. Supports Python, Dart, YAML, JSON, XML, TOML, JUnit XML, Markdown, and 500+ other languages automatically
3. **CSS Grid for line numbers**: Ensures one number per source line regardless of wrapping
4. **Intercept, don't replace**: VS Code links still work as fallback; panel is the primary UX
5. **Gated on `--embed-content`**: Keeps lightweight default; opt-in for full viewer
6. **No external JS dependencies**: Syntax highlighting is pre-computed by Pygments; markdown rendering via simple inline JS parser
7. **Resizable split pane**: User controls how much screen real estate each panel gets
8. **Graceful degradation**: If Pygments is not installed, files display as plain text. If `--embed-content` not used, links open in VS Code as before

## Files Affected

| File | Change |
|------|--------|
| `pyproject.toml` | Add `pygments>=2.0` to `trace-view`, `trace-review`, `all` extras |
| `src/elspais/html/generator.py` | Add `_collect_source_files()`, `_get_pygments_css()`, update `generate()` |
| `src/elspais/html/templates/trace_view.html.j2` | Split layout, file viewer panel, Pygments CSS, JS |
| `tests/test_html_generator.py` (or new) | Test `_collect_source_files()`, syntax highlighting |
