# Diagnostic Command Exit Codes

## Purpose

This document defines requirements for reliable exit codes from diagnostic CLI commands (`doctor`, `health`, `validate`). A diagnostic command that reports problems but exits successfully is lying to its caller, making it CI-unsafe.

---

## REQ-d00080: Diagnostic Command Exit Code Contract

**Level**: DEV | **Status**: Draft | **Implements**: REQ-p00002, REQ-p00005-E

Diagnostic commands (`doctor`, `health`, `validate`) SHALL exit non-zero when they detect configuration or validation failures, ensuring CI pipelines and callers can rely on exit codes to gate merges.

## Assertions

A. All diagnostic commands (`doctor`, `health`, `validate`) SHALL exit non-zero when any check produces a warning-level (`[!!]`) or error-level (`[XX]`) finding.

B. `validate` SHALL exit non-zero when zero requirements are found and a spec directory is configured. A configured project with no parseable requirements is an error, not an empty success.

C. `doctor` and `health` path-existence checks SHALL verify directories exist on disk, not merely that a path string is present in the config.

D. For `project.type = "associated"`, `doctor` SHALL validate that the `[associated]` section exists and has a non-empty `prefix`. A missing or misconfigured `[associated]` section in an associated project is a configuration error.

E. For `project.type = "core"` with configured associate paths, `validate` SHALL exit non-zero when an associate path is missing, misconfigured, or produces zero requirements. A silent requirement count drop is a data-loss condition.

## Rationale

The `HealthReport.is_healthy` property only considers `severity == "error"` failures. Many checks that detect real configuration problems use `severity = "warning"`, which maps to the `[!!]` output icon but does not affect the exit code. This means `doctor` can print multiple `[!!]` warnings about missing paths, invalid project types, and broken associate configurations, yet still exit 0.

Similarly, `validate` treats zero parsed requirements as a successful validation ("Validated 0 requirements") rather than recognizing it as a configuration error. When associate paths are broken, `validate` silently drops from the combined requirement count to core-only, reporting success on a partial graph.

These behaviors make the diagnostic commands unsuitable for CI gating, which is their primary automated use case (REQ-o00066-C).

*End* *Diagnostic Command Exit Code Contract* | **Hash**: c313e2a4
