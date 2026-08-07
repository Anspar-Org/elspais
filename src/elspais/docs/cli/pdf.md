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

## Federated projects

One run from the root repository compiles the whole federation. Every
repository in the compiled graph contributes its requirements to the same
document -- there is no per-associate run to make and no output to stitch
together afterwards.

Each spec file is read from **its own** repository, resolved through the
graph's ownership map, so an associate's requirement text comes from the
associate checkout rather than from a same-named path under the root repo.

Topic Index entries name the repository an associate requirement comes from:

```text
**telemetry**: REQ-p00004, [assoc] REQ-p00011, [assoc] REQ-p00012
```

Requirements owned by the root repository are listed bare; only entries from
another repository carry the `[<repo-name>]` prefix, so the annotation marks
what is foreign rather than repeating what is already the default.

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

Content the compiler is asked to carry but cannot place is reported on stderr
rather than dropped in silence. Every report names the reference as written,
the owning repository, every location searched, the cause and the remedy -- and,
where the reference was declared inside a spec file, that file too.

A referenced figure or diagram that no repository can supply looks like this:

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

A spec file the graph knows about but which cannot be found in its owning
repository is reported through the same channel. That failure is larger than a
missing figure: every requirement, assertion and rationale the file holds is
absent from the document, and in a federated project a misconfigured associate
path can take an entire repository's content out. Such a file is named as a
`source-file` reference, with the repository it was expected in:

```text
Warning: 1 reference could not be placed in the document.
  source-file reference 'spec/prd-assoc.md' [repo: assoc]
    cause: Spec file not found in its owning repository; every requirement it holds is absent from the document.
    searched: /repos/assoc/spec/prd-assoc.md, /repos/core/spec/prd-assoc.md
    remedy: Restore the file, or correct the associate's configured path so the repository resolves.
PDF written to out.pdf (INCOMPLETE: 1 reference omitted -- see warnings above)
```

The document is still produced, and the repositories that did resolve still
render in full. It is degraded, and the degradation is on the record.

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
