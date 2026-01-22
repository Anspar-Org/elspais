# Requirements Format Enhancements Roadmap

**Date**: 2026-01-04
**Status**: Planned
**ADR**: [ADR-010](https://github.com/cure-hht/hht_diary/docs/adr/ADR-010-requirements-format-enhancements.md)

---

## Overview

Implementation roadmap for requirements format enhancements as defined in ADR-010. The enhancements add Type and Validation fields, matrix view generation, PlantUML diagram support, and LLM-assisted reformatting.

---

## Phase 1: Format Enhancement

**Effort**: 4-8 hours

### Tasks

1. Update `.elspais.toml` with Type and Validation field configuration
2. Update `spec/requirements-spec.md` with new format documentation
3. Add elspais validation for new fields
4. Backfill Type and Validation for critical requirements (p00001-p00050)

### Deliverables

- [ ] Updated configuration schema
- [ ] Format specification document
- [ ] 50 requirements with new metadata
- [ ] Validation rules for Type field (required)
- [ ] Validation rules for Validation field (optional, default: test)

### Acceptance Criteria

- `elspais validate` passes with new fields
- Synonym mapping works (e.g., `component` → `artifact` category)
- Missing Type field fails validation
- Missing Validation field defaults to `test`

---

## Phase 2: Matrix View

**Effort**: 8-16 hours

### Tasks

1. Implement `elspais matrix` command
2. Generate artifact × function matrix from Type field
3. Support HTML and CSV output formats
4. Add matrix to CI/CD report generation

### Deliverables

- [ ] `elspais matrix` command implementation
- [ ] HTML output with styling
- [ ] CSV output for spreadsheet import
- [ ] CI/CD integration for automated reports

### Acceptance Criteria

- Matrix correctly maps artifacts (rows) × functions (columns)
- Cells contain child requirements implementing both parents
- Empty cells display `-`
- Reports auto-generate on CI/CD runs

---

## Phase 3: Diagram Support

**Effort**: 16-24 hours

### Tasks

1. Implement `elspais diagram` command
2. Generate PlantUML from requirement hierarchy
3. Include Type-based coloring/grouping
4. Optionally parse PlantUML annotations back to requirements

### Deliverables

- [ ] `elspais diagram --format plantuml` command
- [ ] PlantUML generation with hierarchy
- [ ] Type-based visual grouping (artifacts vs functions)
- [ ] Diagram templates for common views
- [ ] Integration documentation

### Acceptance Criteria

- Generated PlantUML renders correctly
- Requirement IDs linkable in diagrams
- Type categories visually distinguished
- Diagrams version-controllable (text-based)

### Reference

See: [PlantUML Diagram Support](../research/plantuml-diagram-support.md) (in hht_diary repo)

---

## Phase 4: Reformat Integration

**Effort**: 8-16 hours

### Tasks

1. Integrate reformat_reqs functionality into elspais
2. Add custom handler fallback mechanism
3. Implement helpful error messages
4. Document custom handler interface

### Deliverables

- [ ] `elspais reformat` command
- [ ] Claude Code integration (default)
- [ ] Custom handler support via `.elspais.toml`
- [ ] Example handlers (OpenAI, rule-based)
- [ ] Handler interface documentation

### Acceptance Criteria

- Reformat works with Claude Code when available
- Falls back to custom handler when configured
- Clear error message when neither available
- Handler interface documented with examples

### Reference

See: [LLM Reformatting Integration](../research/llm-reformatting-integration.md) (in hht_diary repo)

---

## Summary

| Phase | Effort | Key Deliverable |
|-------|--------|-----------------|
| 1. Format Enhancement | 4-8 hrs | Type/Validation fields |
| 2. Matrix View | 8-16 hrs | `elspais matrix` command |
| 3. Diagram Support | 16-24 hrs | `elspais diagram` command |
| 4. Reformat Integration | 8-16 hrs | `elspais reformat` command |
| **Total** | **36-64 hrs** | Full enhancement suite |

---

## Dependencies

- elspais core validation framework
- TOML configuration parser
- PlantUML (for Phase 3)
- Claude Code or custom LLM handler (for Phase 4)

---

## Notes

- Phases can be implemented incrementally
- Each phase delivers standalone value
- Phase 1 is prerequisite for Phase 2
- Phases 3 and 4 can be parallelized after Phase 1
