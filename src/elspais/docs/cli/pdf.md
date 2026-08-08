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

Markdown image references to `.png`, `.jpg`, `.jpeg`, `.gif` and `.svg` files,
and to Mermaid sources (`.mmd`), are the compiler's own reference grammar: it
resolves them before pandoc runs. URLs are left untouched.

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

### Percent-encoded references

A reference may be written percent-encoded: `![](img/with%20space.png)` for a
file named `with space.png`. Every existence check uses the decoded form,
because that is what pandoc resolves against, so such a reference resolves and
is never reported as missing.

### Absolute paths

An absolute image path that exists is used as written. An absolute path that
does not exist is reported by name before compilation, and pandoc then fails
the run: the missing file is fatal to the engine, so no PDF is produced and the
exit code is non-zero.

### References inside code blocks

A reference inside a fenced code block -- opened by three backticks or three
tildes -- is left completely alone: it is not rewritten, so a Markdown sample
showing image syntax appears in the PDF verbatim, and it is not reported,
because a sample is text about a reference rather than a reference.

An indented (four-space or tab) code block carries the same exemption. It is
recognised the way Markdown defines it: an indented line that follows a blank
line and does not continue a paragraph. Indented continuation lines under a
list item are list content, not code, and references there stay live.

A code fence that is opened and never closed makes the rest of the file read as
code, so requirement structure after it is not rendered as structure. That is
reported as a `code-fence` reference naming the spec file, and counts toward
`INCOMPLETE:`.

### Media types outside the reference grammar

References the compiler does not resolve itself -- `.webp`, `.pdf`, `.eps` and
other media types, and reference-style links (`![alt][key]`) -- are handed to
pandoc, which resolves them through the resource path. When pandoc cannot fetch
one it says so, and that omission is folded into the report and the
`INCOMPLETE:` count alongside the compiler's own findings. The two sets are
deduplicated by reference, so a single missing file counts once.

### Raw HTML image tags are not supported

An HTML image tag in a spec file -- `<img src="...">` -- is **not** supported.
Pandoc passes it through into LaTeX, where it renders as nothing: neither
pandoc nor the compiler can see the loss, so it is not reported and the
`INCOMPLETE:` count does not include it. This is the one omission that is still
silent. Use Markdown image syntax (`![alt](path.png)`) for every figure that
must appear in the PDF.

## Incomplete documents

Content the compiler is asked to carry but cannot place is reported on stderr
rather than dropped in silence, with one exception: a raw HTML `<img>` tag,
described above, is invisible to both pandoc and the compiler.

Each of the compiler's own findings names the reference as written, the owning
repository, every location searched, the cause and the remedy -- and, where the
reference was declared inside a spec file, that file too.

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

A resource pandoc could not fetch is reported in a shorter shape: pandoc names
only the resource, so there is no declaring file, repository or search list to
report.

```text
$ elspais pdf --output out.pdf
[WARNING] Could not fetch resource img/missing.webp: replacing image with description
Warning: 1 reference could not be placed in the document.
  pandoc could not fetch 'img/missing.webp'
    cause: The resource was not found on the resource path.
    remedy: Add the file, correct the reference, or remove the reference from the spec.
PDF written to out.pdf (INCOMPLETE: 1 reference omitted -- see warnings above)
```

A spec file the graph knows about but which cannot be found in its owning
repository is reported through the same channel. That failure is larger than a
missing figure: every requirement, assertion and rationale the file holds is
absent from the document. Such a file is named as a `source-file` reference,
with the repository it was expected in:

```text
Warning: 1 reference could not be placed in the document.
  source-file reference 'spec/prd-assoc.md' [repo: assoc]
    cause: Spec file not found in its owning repository; every requirement it holds is absent from the document.
    searched: /repos/assoc/spec/prd-assoc.md
    remedy: Restore the file, or update the requirement's source location.
PDF written to out.pdf (INCOMPLETE: 1 reference omitted -- see warnings above)
```

A configured associate repository that fails to load -- a wrong path in
`[associates.<name>].path`, most often -- has no files to fail on: its
requirements never enter the graph at all. The absent repository is itself the
omission, reported by name with the path that was tried:

```text
Warning: 1 reference could not be placed in the document.
  repository reference 'assoc' [repo: assoc]
    cause: Associate repository could not be loaded; none of its requirements are in the document.
    searched: /repos/nowhere
    remedy: Correct the associate's configured path, or remove the associate from the configuration.
```

The document is still produced, and the repositories that did resolve still
render in full. It is degraded, and the degradation is on the record.

When anything was omitted, the completion line is qualified: a document missing
content it was asked to carry is not reported as an unqualified success. The
count spans the compiler's own findings and pandoc's unfetchable resources
together, deduplicated by reference, so one missing file counts once no matter
which of the two noticed it.

```text
PDF written to out.pdf (INCOMPLETE: 2 references omitted -- see warnings above)
```

## Engine output

A successful run prints only pandoc's own `[WARNING]` and `[ERROR]` lines --
including `Could not fetch resource X: replacing image with description`, which
pandoc emits while still exiting successfully. The TeX engine narrates font
substitution at length on a healthy run, and burying the one line that reports
a dropped image in sixty lines of font chatter discloses nothing.

A failed run prints the whole engine output, because the cause of the failure
usually lives there rather than in pandoc's own lines.

## Exit codes

- `0` - PDF produced. Omitted references are disclosed in the output, not
  fatal: the document still exists and is still worth reading.
- `1` - No PDF produced (pandoc or the TeX engine is missing, or pandoc failed
  -- a missing absolute image path is one way to fail it).

The compiler's `Warning:` blocks are printed whether or not pandoc goes on to
succeed, so a failed run still names what it could not place. The
`PDF written to ...` line -- qualified or not -- appears only when a PDF was
actually produced.

To make an incomplete document fail a pipeline, check the completion line for
`INCOMPLETE:` or treat any `Warning: N reference` line on stderr as an error.
