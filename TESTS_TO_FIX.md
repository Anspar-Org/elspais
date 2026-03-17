# Weak Test Report

**64 weak tests identified across 24 files** (out of ~80 test files reviewed). The remaining ~56 files had no issues.

---

## REMOVE (42 tests)

These tests validate nothing beyond Python language mechanics or are strict subsets of other tests.

| # | File | Line | Test | Issue |
|---|------|------|------|-------|
| 1 | `commands/test_health_finding.py` | 27 | `test_REQ_d00085_I_finding_instantiation_all_fields` | Tautological dataclass round-trip |
| 2 | `commands/test_health_finding.py` | 42 | `test_REQ_d00085_I_finding_defaults` | Tautological dataclass defaults |
| 3 | `commands/test_health_finding.py` | 51 | `test_REQ_d00085_I_finding_partial_fields` | Redundant with #1 and #2 |
| 4 | `commands/test_health_finding.py` | 67 | `test_REQ_d00085_I_healthcheck_findings_default_empty` | Tautological default value |
| 5 | `commands/test_health_finding.py` | 96 | `test_REQ_d00085_I_finding_to_dict` | Tests `dataclasses.asdict()`, not app code |
| 6 | `commands/test_health_finding.py` | 136 | `test_REQ_d00085_I_report_to_dict_empty_findings` | Redundant with line 117 test |
| 7 | `commands/test_summary.py` | 390 | `test_REQ_d00086_C_json_is_valid` | Subsumed by `json_has_levels_and_excluded` |
| 8 | `commands/test_summary.py` | 541 | `test_REQ_d00086_C_render_all_formats_non_empty` | Redundant with individual format tests |
| 9 | `commands/test_report.py` | 480 | `test_REQ_d00085_A_composable_sections_tuple` | Tests a constant equals its known value |
| 10 | `commands/test_report.py` | 484 | `test_REQ_d00085_A_all_sections_in_format_support` | Duplicate of `format_support_dict_exists` |
| 11 | `core/test_coverage_metrics.py` | 17 | `test_source_values` | Tautological enum value check |
| 12 | `core/test_coverage_metrics.py` | 27 | `test_contribution_fields` | Tautological dataclass round-trip |
| 13 | `core/test_coverage_metrics.py` | 43 | `test_default_values` | Tautological dataclass defaults |
| 14 | `core/test_mutations.py` | 39 | `test_create_entry` | Tautological dataclass round-trip |
| 15 | `core/test_mutations.py` | 56 | `test_entry_with_affects_hash` | Tautological dataclass round-trip |
| 16 | `core/test_mutations.py` | 239 | `test_graph_has_mutation_log` | `hasattr`/`isinstance` structural check |
| 17 | `core/test_mutations.py` | 249 | `test_graph_deleted_nodes_empty` | Tautological initial-state check |
| 18 | `core/test_relations.py` | 18 | `test_all_edge_kinds_exist` | Tautological enum value check |
| 19 | `core/test_relations.py` | 35 | `test_create_edge` | Tautological dataclass round-trip |
| 20 | `core/test_relations.py` | 45 | `test_edge_with_assertion_targets` | Tautological dataclass round-trip |
| 21 | `core/test_version_check.py` | 123 | `test_all_methods_have_commands` | Trivial + redundant with individual tests |
| 22 | `core/test_render_protocol.py` | 145 | `test_REQ_d00131_A_render_function_importable` | `assert callable(render_node)` |
| 23 | `core/test_parsers/test_mdparser_base.py` | 14 | `test_create_minimal` (ParseContext) | Tautological dataclass round-trip |
| 24 | `core/test_parsers/test_mdparser_base.py` | 19 | `test_create_with_config` | Tautological dataclass round-trip |
| 25 | `core/test_parsers/test_mdparser_base.py` | 40 | `test_create_with_parsed_data` | Tautological dataclass round-trip |
| 26 | `core/test_parsers/test_mdparser_base.py` | 63 | `test_protocol_has_priority` | Trivial `hasattr` on protocol |
| 27 | `core/test_parsers/test_mdparser_base.py` | 67 | `test_protocol_has_claim_and_parse` | Trivial `hasattr` on protocol |
| 28 | `core/test_deserializer/test_domain_base.py` | 12 | `test_create_minimal` | Tautological dataclass round-trip |
| 29 | `core/test_deserializer/test_domain_base.py` | 18 | `test_create_with_metadata` | Tautological dataclass round-trip |
| 30 | `core/test_deserializer/test_domain_base.py` | 30 | `test_protocol_has_iterate_sources` | Trivial `hasattr` on protocol |
| 31 | `core/test_deserializer/test_domain_base.py` | 33 | `test_protocol_has_deserialize` | Trivial `hasattr` on protocol |
| 32 | `core/test_html/test_file_viewer.py` | 78 | `test_REQ_p00006_C_collect_source_files_returns_dict` | Type-check only, subsumed by next test |
| 33 | `core/test_html/test_file_viewer.py` | 95 | `test_REQ_p00006_C_collect_source_files_lines_is_list` | Type-check only, redundant |
| 34 | `core/test_html/test_file_viewer.py` | 105 | `test_REQ_p00006_C_collect_source_files_raw_is_string` | Type-check only, redundant |
| 35 | `core/test_html/test_file_viewer.py` | 267 | `test_REQ_p00006_C_get_pygments_css_returns_nonempty_string` | Subsumed by `contains_highlight_class` |
| 36 | `mcp/test_matches_query.py` | 303 | `test_REQ_p00050_D_returns_bool` | Type-check only |
| 37 | `mcp/test_search_scorer.py` | 407 | `test_REQ_d00061_M_matches_node_returns_bool_type` | Type-check only, subsumed |
| 38 | `test_health.py` | 43 | `test_with_details` | Tautological dataclass round-trip |
| 39 | `test_server_app.py` | 391 | `test_REQ_d00010_A_tree_data_returns_list` | Type-check only, subsumed by next test |
| 40 | `test_example_cmd.py` | 264 | `test_cli_example_help` | Redundant -- tests argparse, not behavior |
| 41 | `test_example_cmd.py` | 273 | `test_cli_example_requirement` | Redundant -- tests argparse, not behavior |
| 42 | `test_example_cmd.py` | 282 | `test_cli_example_with_full_flag` | Redundant -- tests argparse, not behavior |

---

## CHANGE (32 tests)

These tests exist for a valid reason but have assertions too loose or misleading to provide real signal.

| # | File | Line | Test | Issue | Fix |
|---|------|------|------|-------|-----|
| 1 | `commands/test_completion.py` | 69 | `test_bash_snippet_contains_marker` | Only checks one substring | Assert functional content (e.g. `register-python-argcomplete`) |
| 2 | `commands/test_completion.py` | 72 | `test_fish_snippet_uses_source` | `"source" in snippet` too loose | Assert full `source (...)` pattern |
| 3 | `commands/test_completion.py` | 75 | `test_tcsh_snippet_uses_eval` | `"eval" in snippet` too loose | Assert more specific pattern |
| 4 | `commands/test_health_detail_flags.py` | 83 | `test_default_skips_passing_details` | `getattr` fallback masks missing attr | Assert attribute directly without fallback |
| 5 | `commands/test_summary.py` | 113 | `test_returns_levels_and_excluded_keys` | `isinstance(data["levels"], list)` only | Add value assertions or merge with next test |
| 6 | `commands/test_report.py` | 124 | `test_sections_separated_by_blank_lines` | `"\n\n" in output` too loose | Check position relative to section markers |
| 7 | `commands/test_report.py` | 525 | `test_multi_section_with_spec_dir` | Uses `or` instead of `and` | Use `and` to verify both sections rendered |
| 8 | `commands/test_trace_grouped_refs.py` | 521 | `test_html_test_refs_in_code_tags` | `"<code>" in output` too loose | Assert specific ref IDs within `<code>` tags |
| 9 | `commands/test_validate_export.py` | 96 | `test_export_outputs_requirement_dict` | Only checks key presence, not values | Assert actual values like `req["title"]` |
| 10 | `commands/test_doctor.py` | 48 | `test_run_config_checks_returns_list` | Type-check only | Assert `len >= N` and specific check names |
| 11 | `core/test_mutations.py` | 68 | `test_entry_str` | `"rename_node" in s` too loose | Assert specific expected format |
| 12 | `core/test_graph/test_analysis.py` | 222 | `test_composite_is_weighted_combination` | Only `isinstance(float)` and `>= 0.0` | Compute expected score or verify relative ordering |
| 13 | `core/test_hasher.py` | 66 | `test_sha1_algorithm` | Only checks length, not algorithm | Assert specific expected hash for known input |
| 14 | `core/test_hasher.py` | 71 | `test_md5_algorithm` | Only checks length, not algorithm | Assert specific expected hash for known input |
| 15 | `core/test_config.py` | 57 | `test_load_applies_defaults` | Only checks explicitly-set value | Assert a default value NOT in the toml file |
| 16 | `core/test_render_protocol.py` | 160 | `test_render_unknown_kind_raises` | Name misleading; tests REMAINDER, not unknown | Rename or test an actual unknown kind |
| 17 | `core/test_parsers/test_mdparser_base.py` | 27 | `test_create_minimal` (ParsedContent) | Mostly tautological round-trip | Keep only non-obvious default check (`parsed_data == {}`) |
| 18 | `core/test_parsers/test_result_pipeline.py` | 53 | `test_returns_parsed_content_with_test_result_type` (JUnit) | `isinstance(ParsedContent)` trivial | Drop isinstance, keep content_type check |
| 19 | `core/test_parsers/test_result_pipeline.py` | 136 | `test_returns_parsed_content_with_test_result_type` (Pytest) | `isinstance(ParsedContent)` trivial | Drop isinstance, keep content_type check |
| 20 | `core/test_html/test_generator.py` | 46 | `test_generate_returns_html` | `isinstance(result, str)` trivial | Drop isinstance, keep HTML structure check |
| 21 | `core/test_html/test_generator.py` | 76 | `test_generate_includes_styles` | `"<style>" or "css"` too loose | Assert a specific CSS class |
| 22 | `core/test_html/test_generator.py` | 109 | `test_embed_content_includes_json` | `"data-" in result` too broad | Assert specific embedded data element |
| 23 | `core/test_html/test_generator.py` | 122 | `test_shows_hierarchy_structure` | 3-letter strings match anything | Assert structural elements proving hierarchy |
| 24 | `core/test_html/test_generator.py` | 210 | `test_coverage_values` | `"none" in result.lower()` too loose | Assert specific coverage filter UI elements |
| 25 | `core/test_html/test_generator.py` | 331 | `test_git_state_in_embedded_json` | Doesn't check for git data at all | Assert `"git_branch"` or `"git_commit"` in JSON |
| 26 | `core/test_html/test_theme.py` | 11 | `test_returns_legend_catalog` | `isinstance(catalog, LegendCatalog)` only | Also assert the catalog has entries |
| 27 | `core/test_html/test_highlighting.py` | 36 | `test_detects_markdown_language` | `language != ""` too loose | Assert `language == "markdown"` |
| 28 | `mcp/test_matches_query.py` | 357 | `test_regex_ignores_parsed` | Doesn't verify `parsed` is ignored | Pass contradicting `parsed` to prove it's ignored |
| 29 | `mcp/test_mcp_query_fixes.py` | 335 | `test_search_body_returns_list` | `isinstance(results, list)` trivial | Rename to reflect value assertion; drop isinstance |
| 30 | `test_health.py` | 27 | `test_basic_creation` | Mostly tautological | Keep only default-value assertions |
| 31 | `test_health.py` | 59 | `test_empty_report` | Tautological zeros | Combine with `test_all_passed`; keep only `is_healthy` |
| 32 | `test_health.py` | 143 | `test_required_fields_missing` | Name doesn't match behavior | Rename to `test_required_fields_present_with_defaults` |
| 33 | `test_health.py` | 331 | `test_full_health_check` | `assert result in (0, 1)` accepts both | Assert specific expected return code |
| 34 | `test_server_app.py` | 181 | `test_create_app_accepts_config` | `assert app is not None` | Assert config was applied |
| 35 | `test_server_app.py` | 313 | `test_search_default_limit` | Never verifies the limit is 50 | Insert >50 nodes, confirm only 50 returned |
| 36 | `test_server_app.py` | 1845 | `test_dirty_reflects_mutation_state` | `isinstance(data["dirty"], bool)` | Assert expected True/False state |
| 37 | `test_embedded_data.py` | 48+ | 5 tests with `break` after first entry | Only checks first item in collection | Remove `break` to check all entries |
| 38 | `test_doc_sync.py` | 193 | `test_render_preserves_blank_lines` | `or` with loose second condition | Assert blank lines between specific paragraphs |

---

## Pattern Summary

| Category | Count | Most Common In |
|----------|-------|----------------|
| Tautological (dataclass round-trip) | 20 | `test_health_finding`, `test_mutations`, `test_relations`, `test_mdparser_base` |
| Type-check only / trivially passing | 15 | `test_file_viewer`, `test_generator`, `test_server_app` |
| Redundant (subsumed by other test) | 10 | `test_health_finding`, `test_summary`, `test_report` |
| Misleading name | 4 | `test_render_protocol`, `test_health`, `test_mcp_query_fixes` |
| Overly loose assertions (`or`, substring) | 8 | `test_generator`, `test_completion`, `test_report` |
| Protocol `hasattr` checks | 4 | `test_mdparser_base`, `test_domain_base` |
