# MASTER PLAN — COMPLETED

> **Status**: ARCHIVED — All phases complete, pushed to origin.
> **Branch**: `feature/CUR-514-viewtrace-port`
> **Final default**: `normalized-text` (changed from `full-text` during Phase 6)

## Overview

Added a configurable `hash_mode` setting under `[validation]` in `.elspais.toml` with two modes:

- **`full-text`**: Hash every line between header and footer, no normalization.
- **`normalized-text`** (default): Hash assertions only, with cosmetic normalization.

## Completed Phases

1. [x] **Spec Update** — Documented both modes in `spec/requirements-spec.md`
2. [x] **Config Defaults** — Added `hash_mode` to `DEFAULT_CONFIG`
3. [x] **Hasher Normalization** — `normalize_assertion_text()`, `compute_normalized_hash()`
4. [x] **Builder + Commands** — Hash mode branching in builder, hash_cmd, validate
5. [x] **Tests** — 20 hasher unit tests, 17 hash mode integration tests
6. [x] **Fixture Alignment** — All hashes updated, pre-push hook passes

## Verification (all passed)

- [x] 933 tests pass (`pytest`)
- [x] No lint errors (`ruff check`)
- [x] All commits with `[CUR-514]` prefix
- [x] `elspais hash verify` — all hashes valid
- [x] `normalized-text` mode verified: non-assertion changes ignored, assertion changes tracked
- [x] `git push` — pre-push hook passes
