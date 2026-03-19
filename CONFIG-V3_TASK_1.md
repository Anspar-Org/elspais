# Task 1: New Pydantic Models — LevelConfig, ScanningConfig, OutputConfig, ChangelogRequireConfig

**Plan**: MASTER_PLAN.md (Config Schema v3 — Schema Models, 1/4)
**Ticket**: CONFIG-V3

## Description

Create new Pydantic models for the v3 config schema shape. These models are additive — they don't replace existing models yet (that's Task 2). This task creates the building blocks.

## Applicable Assertions

- **REQ-d00212-A**: LevelConfig model with rank, letter, display_name, implements
- **REQ-d00212-B**: ScanningKindConfig base + per-kind subclasses
- **REQ-d00212-C**: ScanningConfig composite with all kinds + global skip
- **REQ-d00212-D**: OutputConfig with formats and dir
- **REQ-d00212-E**: ChangelogRequireConfig sub-model + renamed ChangelogConfig fields

## Progress

- [x] Baseline: 2831 passed
- [x] TASK_FILE created
- [x] Assertions found/created: REQ-d00212-A through E
- [x] Failing tests written: 40 tests in tests/core/test_config_v3_models.py
- [x] Implementation: all models added to schema.py, all callers updated
- [x] Verification: 2872 passed, 321 deselected, 1 warning
- [x] Docs update: CHANGELOG.md, docs/configuration.md
- [x] Version bump: 0.106.5 → 0.107.0
- [ ] Commit
