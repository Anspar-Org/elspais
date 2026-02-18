# Stakeholder Overview PDF (`--overview`)

## Goal

A lighter PDF for non-technical stakeholders showing only high-level product requirements. No OPS or DEV content from any source.

## Filtering Rules

- **Core repo**: PRD requirements only, limited to first N graph depths (configurable via `--max-depth`, default = all).
- **Associated repos**: PRD requirements only, all depths.
- **OPS and DEV**: Excluded entirely from both core and associated repos.

## CLI Interface

Two new flags on `elspais pdf`:

```
elspais pdf --overview                    # PRD-only, all depths
elspais pdf --overview --max-depth 2      # PRD-only, depths 0 and 1
```

- `--overview`: Boolean flag. Only PRD-level requirements included.
- `--max-depth N`: Integer, optional. Limits core PRDs to graph depth < N (depth 0 = root, depth 1 = direct children). Associates are not depth-limited. Only meaningful with `--overview`.

## Implementation Scope

Changes confined to assembler + CLI wiring. No changes to graph, parsers, or config.

1. `MarkdownAssembler.__init__` — Accept `overview: bool = False`, `max_depth: int | None = None`.
2. `MarkdownAssembler.assemble()` — When `overview=True`, emit only PRD bucket. When `max_depth` set, filter core files by minimum depth.
3. `pdf_cmd.py` — Pass new args to assembler.
4. `cli.py` — Register `--overview` and `--max-depth` on the pdf parser.

## Unchanged

- Graph building, file rendering, topic index scoping, Pandoc rendering, LaTeX template.

## Title Default

When `--overview` and no `--title`, default to "Product Requirements Overview".
