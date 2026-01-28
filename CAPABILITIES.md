# elspais Capabilities Reference

This document lists the **interface capabilities** of elspais without implementation details.
Use this as a reference when implementing new features to ensure functional parity.

---

## CLI Commands

### `elspais validate`
Validates requirements format, links, and hashes. Checks consistency and can auto-fix fixable issues.
- Options: `--fix`, `--core-repo`, `--skip-rule`, `-j/--json`, `--tests`, `--no-tests`, `--mode (core|combined)`

### `elspais trace`
Generates traceability matrix and reports from requirements. Supports multiple output formats.
- Options: `--format (markdown|html|csv|both)`, `--output`, `--view`, `--embed-content`, `--edit-mode`, `--review-mode`, `--server`, `--port`, `--mode (core|sponsor|combined)`, `--sponsor`, `--graph`, `--graph-json`, `--report`, `--depth`

### `elspais hash`
Manages requirement hashes for change tracking.
- Subcommands: `verify`, `update`
- Options: `req_id`, `--dry-run`

### `elspais index`
Manages INDEX.md file validation and regeneration.
- Subcommands: `validate`, `regenerate`

### `elspais analyze`
Analyzes requirement hierarchy, orphans, and coverage metrics.
- Subcommands: `hierarchy`, `orphans`, `coverage`

### `elspais changed`
Detects and reports git changes to spec files.
- Options: `--base-branch`, `-j/--json`, `-a/--all`

### `elspais version`
Shows version number and checks for updates.
- Options: `check`

### `elspais init`
Creates .elspais.toml configuration file.
- Options: `--type (core|associated)`, `--associated-prefix`, `--force`, `--template`

### `elspais example`
Displays requirement format examples, templates, and ID patterns.
- Subcommands: `requirement`, `journey`, `assertion`, `ids`
- Options: `--full`

### `elspais edit`
Edits requirements in-place.
- Options: `--req-id`, `--implements`, `--status`, `--move-to`, `--from-json`, `--dry-run`, `--validate-refs`

### `elspais config`
Views and modifies configuration settings.
- Subcommands: `show`, `get`, `set`, `unset`, `add`, `remove`, `path`
- Options: `--section`, `-j/--json`, `key`, `value`

### `elspais rules`
Views and manages content rules.
- Subcommands: `list`, `show`
- Options: `file`

### `elspais reformat-with-claude`
Reformats requirements using AI to convert Acceptance Criteria to Assertions.
- Options: `--start-req`, `--depth`, `--dry-run`, `--backup`, `--force`, `--fix-line-breaks`, `--line-breaks-only`, `--mode`

### `elspais mcp`
Starts MCP server for Claude Code integration.
- Subcommands: `serve`
- Options: `--transport [stdio|sse|streamable-http]`

### Global Options
- `--version`, `--config PATH`, `--spec-dir PATH`, `-v/--verbose`, `-q/--quiet`

---

## Public API

### Core Classes

**Requirement**
- Represents a complete requirement specification
- Properties: `id`, `title`, `level`, `status`, `body`, `implements`, `refines`, `assertions`, `hash`, `file_path`, `line_number`, `subdir`
- Methods: `location()`, `get_assertion(label)`, `assertion_id(label)`
- Computed: `type_code`, `number`, `associated`, `is_roadmap`

**Assertion**
- Single testable assertion within a requirement
- Properties: `label`, `text`, `is_placeholder`
- Computed: `full_id`

**ParsedRequirement**
- Parsed requirement ID broken into components
- Properties: `prefix`, `type_code`, `number`, `associated`, `assertion_labels`
- Computed: `base_id`

**RuleEngine**
- Validates requirements against configured rules
- Methods: `validate(requirements)` → `List[RuleViolation]`

**RuleViolation**
- Represents a validation error/warning
- Properties: `rule_name`, `requirement_id`, `message`, `severity`, `location`

**PatternValidator**
- Validates requirement IDs against patterns
- Methods: `match(text)`, `is_valid_id(id)`, `parse_id(id)`

**ConfigLoader**
- Configuration container with dot-notation access
- Methods: `from_dict(data)`, `get(key, default)`, `get_raw()`

**GraphNode**
- Unified node in traceability graph
- Properties: `id`, `kind`, `label`, `source`, `content`, `children`, `parents`, `metrics`
- Methods: `add_child(child)`

### Enums

**Severity**: `ERROR`, `WARNING`, `INFO`

**NodeKind**: `REQUIREMENT`, `ASSERTION`, `CODE`, `TEST`, `TEST_RESULT`, `USER_JOURNEY`, `TODO`

**EdgeKind**: `IMPLEMENTS`, `REFINES`, `VALIDATES`, `ADDRESSES`, `CONTAINS`

### Key Functions

**Loading:**
- `load_requirements_from_directories(spec_dirs, config, ...)`
- `load_requirements_from_directory(spec_dir, config, ...)`
- `load_requirements_from_repo(repo_path, config)`
- `parse_requirements_from_directories(spec_dirs, config, ...)`
- `create_parser(config)`

**Configuration:**
- `find_config_file(start_path)`
- `load_config(config_path)`
- `get_config(config_path, start_path, quiet)`
- `get_spec_directories(override, config, base_path)`
- `get_code_directories(config, base_path)`

**Hashing:**
- `calculate_hash(content, length, algorithm)`
- `verify_hash(content, hash, ...)`
- `clean_requirement_body(content, ...)`

**Content Rules:**
- `load_content_rule(file_path)`
- `load_content_rules(directory)`
- `parse_frontmatter(text)`

**Associates (Multi-Repo):**
- `load_associates_config(config, base_path)`
- `get_associate_spec_directories(config, base_path)`

---

## MCP Tools

### Validation & Parsing
| Tool | Description | Parameters |
|------|-------------|------------|
| `validate` | Validates all requirements | `skip_rules` (optional) |
| `parse_requirement` | Parses requirement text | `text`, `file_path` (optional) |
| `search` | Searches requirements by pattern | `query`, `field` (optional), `regex` (optional) |
| `get_requirement` | Gets requirement details | `req_id` |
| `analyze` | Analyzes structure | `analysis_type` (optional) |

### Graph Operations
| Tool | Description | Parameters |
|------|-------------|------------|
| `get_graph_status` | Gets graph status/stats | (none) |
| `refresh_graph` | Rebuilds graph | `full` (optional) |
| `get_hierarchy` | Gets ancestors/children | `req_id` |
| `get_traceability_path` | Full trace tree | `req_id`, `max_depth` (optional) |
| `get_coverage_breakdown` | Per-assertion coverage | `req_id` |
| `list_by_criteria` | Filter requirements | `level`, `status`, `coverage_below`, `has_gaps` |
| `show_requirement_context` | Full requirement context | `req_id`, `include_assertions`, `include_implementers` |

### Mutation Operations
| Tool | Description | Parameters |
|------|-------------|------------|
| `change_reference_type` | Switch Implements ↔ Refines | `source_id`, `target_id`, `new_type` |
| `specialize_reference` | REQ→Assertion reference | `source_id`, `target_id`, `assertions` |
| `move_requirement` | Move between files | `req_id`, `target_file`, `position`, `after_id` |
| `prepare_file_deletion` | Check if file can be deleted | `file_path` |
| `delete_spec_file` | Delete spec file | `file_path`, `force`, `extract_content_to` |

### AI Transformation
| Tool | Description | Parameters |
|------|-------------|------------|
| `get_node_as_json` | JSON for AI processing | `node_id`, `include_full_text` |
| `transform_with_ai` | AI-assisted rewrite | `node_id`, `prompt`, `output_mode`, `save_branch`, `dry_run` |
| `restore_from_safety_branch` | Restore from backup | `branch_name` |
| `list_safety_branches` | List git safety branches | (none) |

### Annotation Operations
| Tool | Description | Parameters |
|------|-------------|------------|
| `add_annotation` | Add metadata | `node_id`, `key`, `value`, `source` |
| `get_annotations` | Get node annotations | `node_id` |
| `add_tag` / `remove_tag` | Tag operations | `node_id`, `tag` |
| `list_tagged` | Nodes with tag | `tag` |
| `list_all_tags` | All tags in use | (none) |
| `nodes_with_annotation` | Find by annotation | `key`, `value` |
| `clear_annotations` | Clear annotations | `node_id` (optional) |
| `annotation_stats` | Annotation statistics | (none) |

## MCP Resources

| URI Pattern | Description |
|-------------|-------------|
| `requirements://all` | All requirements |
| `requirements://{req_id}` | Single requirement |
| `requirements://level/{level}` | By level (PRD/OPS/DEV) |
| `content-rules://list` | Content rule files |
| `content-rules://{filename}` | Single content rule |
| `config://current` | Current configuration |
| `graph://status` | Graph status |
| `graph://validation` | Validation warnings |
| `traceability://{req_id}` | Full trace path |
| `coverage://{req_id}` | Coverage breakdown |
| `hierarchy://{req_id}/ancestors` | Requirement ancestors |
| `hierarchy://{req_id}/descendants` | Requirement descendants |

---

## Configuration Sections

### [patterns]
- `id_template`: Template for requirement IDs (e.g., `{prefix}-{type}{id}`)
- `prefix`: ID prefix (e.g., "REQ")
- `types`: Type definitions with `id`, `name`, `level`
- `id_format`: Format with `style`, `digits`, `leading_zeros`
- `assertions`: Assertion config with `label_style`, `max_count`
- `associated`: Multi-repo config with `enabled`, `position`, `format`, `length`

### [spec]
- `directories`: Spec directory paths
- `patterns`: File patterns (e.g., `["*.md"]`)
- `skip_files` / `skip_dirs`: Exclusions
- `index_file`: Optional INDEX.md

### [rules.hierarchy]
- `allowed_implements`: Valid parent-child type relationships
- `allow_circular`: Permit circular dependencies
- `allow_orphans`: Permit parentless requirements

### [rules.format]
- `require_hash` / `require_rationale` / `require_assertions` / `require_status`
- `allowed_statuses`: Valid status values
- `labels_sequential` / `labels_unique`: Assertion label rules
- `placeholder_values`: Placeholder text patterns

### [validation]
- `strict_hierarchy`: Enforce strict parent-child rules
- `hash_algorithm`: Hash algorithm (default: sha256)
- `hash_length`: Hash truncation length

### [testing]
- `enabled`: Enable test scanning
- `test_dirs`: Test directory paths
- `patterns`: Test file patterns
- `reference_keyword`: Keyword for requirement references

### [traceability]
- `output_formats`: Output format list
- `output_dir`: Output directory
- `scan_patterns`: Code patterns to scan

### [trace.reports.{name}]
Custom report definitions with:
- `fields`: Requirement fields to include
- `metric_fields`: Metrics to display
- `filters`: Field filters
- `sort_by` / `sort_descending`: Sorting options

### Environment Variables
- `ELSPAIS_*` prefix: Override any config key (e.g., `ELSPAIS_PATTERNS_PREFIX=MYREQ`)

---

## Key Capabilities Summary

1. **Requirement Parsing** - Load/parse Markdown requirements with structure preservation
2. **Pattern Validation** - Validate IDs against configurable patterns
3. **Hierarchy Validation** - Check allowed type relationships (PRD→OPS→DEV)
4. **Content Hashing** - SHA-256 hashes for change detection
5. **Graph Traceability** - DAG with requirements, assertions, code, tests
6. **Multi-Repository** - Associate/sponsor repository support
7. **Configuration** - TOML config with environment overrides
8. **Content Rules** - Semantic validation guidance files
9. **MCP Integration** - Claude Code integration via Model Context Protocol
10. **Git Integration** - Change detection, safety branches for mutations
