# PDF Compilation

This document defines the product requirement for compiling spec files into formal PDF documents.

---

# REQ-p00080: Spec-to-PDF Compilation

**Level**: PRD | **Status**: Active | **Implements**: REQ-p00001

## Rationale

UAT documentation review requires formal PDF output with professional formatting. A single compiled document with table of contents, per-requirement page breaks, and a topic index enables offline review, regulatory submission, and stakeholder sign-off. Currently, spec files exist only as Markdown with no PDF generation pipeline.

The `elspais pdf` command compiles requirement spec files into a professional PDF using Pandoc and LaTeX. Python assembles a clean Markdown document from the traceability graph; a custom LaTeX template controls formatting; Pandoc handles Markdown-to-LaTeX conversion.

## Assertions

A. The tool SHALL provide an `elspais pdf` CLI command that compiles spec files into a PDF document.

B. The assembled Markdown SHALL group requirements by level (PRD, OPS, DEV) with each level as a top-level section, and order files within each level by graph depth (root requirements first).

C. The generated PDF SHALL include an auto-generated table of contents derived from requirement headings.

D. The tool SHALL generate an alphabetized topic index with entries derived from filename words, file-level Topics lines, and requirement-level Topics lines, rendered as a Markdown section with hyperlinks.

E. The tool SHALL insert page breaks before each requirement heading to ensure each requirement starts on a new page.

*End* *Spec-to-PDF Compilation* | **Hash**: 20f51345
