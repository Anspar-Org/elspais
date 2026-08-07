# PDF COMPILATION

Compile spec files into a single PDF document.

## Usage

```
elspais pdf [--output PATH] [--engine ENGINE] [--template PATH]
            [--title TITLE] [--cover PATH] [--overview] [--max-depth N]
```

## What it does

Assembles a structured Markdown document from the traceability graph -- every
repository in the compiled graph, ordered by level and hierarchy depth -- then
invokes pandoc with a LaTeX template to produce the PDF.

```bash
# Full specification document
elspais pdf

# Stakeholder overview: PRD requirements only, no OPS or DEV
elspais pdf --overview --title "Product Requirements Overview"
```

## Options

| Flag | Description |
|------|-------------|
| `--output PATH` | Output PDF file path (default: `spec-output.pdf`) |
| `--engine ENGINE` | PDF engine: `xelatex` (default), `lualatex`, `pdflatex` |
| `--template PATH` | Custom pandoc LaTeX template |
| `--title TITLE` | Document title (default: project name from config) |
| `--cover PATH` | Markdown file for a custom cover page |
| `--overview` | Stakeholder overview (PRD only, no OPS/DEV) |
| `--max-depth N` | Max graph depth for core PRDs in overview mode |

## Prerequisites

- pandoc: <https://pandoc.org/installing.html>
- xelatex: Install TeX Live, MiKTeX, or MacTeX
- mermaid CLI (`mmdc`), only if your specs reference `.mmd` diagram sources

## Figures and diagrams

Images (`.png`, `.jpg`, `.jpeg`, `.gif`, `.svg`) and Mermaid sources (`.mmd`)
referenced from a spec file are resolved before pandoc runs. Absolute paths and
URLs are left untouched.

A relative image reference is searched in this order:

```text
1. the declaring spec file's own directory
2. the root of the repository that owns the declaring spec file
3. the resource-path set: every repository's root and its spec/ directory
```

The resource-path set is what pandoc itself receives as `--resource-path`, so a
reference found there is placed by pandoc rather than rewritten in advance.

Each spec file resolves against **its own** repository. In a federated project
an associate repo's figures come from the associate repo, so two repositories
may both carry `images/architecture.png` and each spec file gets its own.

A Mermaid reference is searched in the declaring file's directory and then in
its owning repository's root. A `.mmd` source found there is rendered to a
`.png` beside it -- a `.png` already sitting beside the source is used as-is --
and the reference is rewritten to that image. Mermaid sources are not searched
on the resource path -- pandoc can place an image but cannot render a diagram.

## Incomplete documents

A referenced figure or diagram that no repository can supply is reported on
stderr, naming the reference as written, the spec file declaring it, the owning
repository, every location searched, the cause, and the remedy:

```text
Warning: 1 reference could not be placed in the document.
  image reference 'images/does-not-exist.png' declared in spec/sub/prd-sub.md [repo: imgdemo]
    cause: File not found in any repository of the compiled graph.
    searched: /repo/spec/sub/images/does-not-exist.png, /repo/images/does-not-exist.png, /repo/spec/images/does-not-exist.png
    remedy: Add the file, correct the reference, or remove the reference from the spec.
PDF written to out.pdf (INCOMPLETE: 1 reference omitted -- see warnings above)
```

A Mermaid diagram whose source is found but cannot be rendered -- `mmdc` is not
installed, or it failed -- is reported the same way, with the remedy to install
the mermaid CLI or commit a pre-rendered `.png` alongside the `.mmd` source.

When anything was omitted, the completion line is qualified: a document missing
content it was asked to carry is not reported as an unqualified success.

```text
PDF written to out.pdf (INCOMPLETE: 2 references omitted -- see warnings above)
```

Pandoc's own warnings are echoed to stderr whether or not pandoc succeeds --
including `Could not fetch resource X: replacing image with description`, which
pandoc emits while still exiting successfully.

## Exit codes

- `0` - PDF produced. Omitted references are disclosed in the output, not
  fatal: the document still exists and is still worth reading.
- `1` - No PDF produced (pandoc or the TeX engine is missing, or pandoc failed).

To make an incomplete document fail a pipeline, check the completion line for
`INCOMPLETE:` or treat any `Warning: N reference` line on stderr as an error.
