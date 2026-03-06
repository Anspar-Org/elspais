# Diagnostic Command Exit Codes

## Purpose

This document defines requirements for reliable exit codes from diagnostic CLI commands (`doctor`, `health`). A diagnostic command that reports problems but exits successfully is lying to its caller, making it CI-unsafe.

---

## REQ-d00080: Diagnostic Command Exit Code Contract

**Level**: DEV | **Status**: Active | **Implements**: REQ-p00002, REQ-p00005-E

Diagnostic commands (`doctor`, `health`) SHALL exit non-zero when they detect configuration or validation failures, ensuring CI pipelines and callers can rely on exit codes to gate merges.

## Assertions

A. Diagnostic commands (`doctor`, `health`) SHALL exit non-zero when any check produces a warning-level or error-level finding. The `--lenient` flag SHALL relax this so that only error-level findings cause non-zero exit.

B. `health` SHALL exit non-zero when zero requirements are found and a spec directory is configured. A configured project with no parseable requirements is an error, not an empty success.

C. `doctor` and `health` path-existence checks SHALL verify directories exist on disk, not merely that a path string is present in the config.

D. For `project.type = "associated"`, `doctor` SHALL validate that the `[associated]` section exists and has a non-empty `prefix`. A missing or misconfigured `[associated]` section in an associated project is a configuration error.

E. For `project.type = "core"` with configured associate paths, `health` SHALL exit non-zero when an associate path is missing, misconfigured, or produces zero requirements. A silent requirement count drop is a data-loss condition.

## Rationale

Warnings represent real problems: missing paths, orphaned nodes, unresolved references. By default, any warning causes a non-zero exit code, making diagnostic commands safe for CI gating (REQ-o00066-C). The `--lenient` flag provides an escape hatch for development workflows where warnings are informational and should not block.

The previous `validate` command's responsibilities are absorbed by `health`. References to `validate` in assertions B and E now refer to the `health` command's spec-checking category.

*End* *Diagnostic Command Exit Code Contract* | **Hash**: ada92a29
