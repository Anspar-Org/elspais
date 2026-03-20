# Feature Product Requirements

# REQ-p00005: Multi-Repository Requirements

**Level**: prd | **Status**: Active | **Implements**: REQ-p00001

## Rationale

Large organizations often split requirements across multiple repositories:

- A **core** repository containing product-level requirements
- **Associated** repositories for subsystems, services, or components
- **Sponsor** repositories for customer-specific or partner-specific requirements

Each repository maintains its own spec directory, but requirements must reference and implement requirements from other repositories. The tool must validate these cross-repository links and generate combined traceability matrices.

This architecture supports:

- Independent versioning of subsystem specifications
- Access control (not everyone needs access to all specs)
- Modular development with clear interface contracts
- Combined views for regulatory submissions

CI/CD pipelines and diverse developer environments mean associated repositories may be located at different filesystem paths on each machine. Rather than requiring each environment to maintain a separate override file, the tool treats all cross-repository resolution as a local path concern: CI systems clone repos and then configure paths via the CLI, developers set paths to match their local directory layout, and the associated repository's own configuration file declares its identity (project type, namespace prefix). This keeps repository topology — which repos exist and where they are hosted — as a CI/infrastructure concern outside the tool, while the tool focuses on discovering and validating whatever local repos it is pointed at.

## Assertions

A. The tool SHALL support requirement references across repository boundaries using configurable namespace prefixes.

B. The tool SHALL generate combined traceability matrices spanning multiple repositories.

C. The tool SHALL support CLI-based configuration of associate repository paths so that external systems can register associates without manually editing configuration files.

D. The tool SHALL discover an associated repository's identity — including its project type and namespace prefix — by reading that repository's own configuration file.

E. The tool SHALL report a clear configuration error when a configured associate path does not exist or does not contain a valid associated-repository configuration.

F. The tool SHALL resolve relative associate paths from the canonical (non-worktree) repository root so that cross-repository paths remain valid when working from git worktrees.

*End* *Multi-Repository Requirements* | **Hash**: 7964180f
---

# REQ-p00006: Interactive Traceability Viewer

**Level**: prd | **Status**: Active | **Implements**: REQ-p00003

## Rationale

Static traceability matrices—whether Markdown tables or CSV exports—answer the question "what implements what?" but fail to support exploratory analysis. Reviewers need to navigate requirement hierarchies, drill into specific branches, and understand the full context of a requirement including its test coverage, implementation references, and change history.

The interactive trace viewer transforms the traceability matrix into an explorable interface:

- **Clickable navigation**: Click a requirement to see what it implements and what implements it
- **Test coverage overlay**: See which requirements have tests, which are untested, and test pass/fail status
- **Git state awareness**: Visual indicators for uncommitted changes, moved requirements, and branch differences
- **Implementation references**: Links to source files that reference each requirement
- **Embedded content**: Optionally include full requirement text for offline review

This supports:

- Design reviews (navigate the hierarchy without switching files)
- Test planning (identify coverage gaps)
- Change impact analysis (see what's affected by a modification)
- Regulatory audits (demonstrate complete traceability in one view)

## Assertions

A. The tool SHALL generate an interactive HTML view with clickable requirement navigation.

B. The tool SHALL display test coverage information per requirement when test data is available.

C. The viewer SHALL display source files inline in a side panel with syntax-highlighted content and stable line numbers, when embedded content is enabled.

*End* *Interactive Traceability Viewer* | **Hash**: b3dd4d1a
---

## REQ-p00014: Satisfies Relationship

**Level**: prd | **Status**: Active | **Implements**: REQ-p00001

## Rationale

Cross-cutting concerns — regulatory compliance frameworks, security policies, accessibility standards, operational baselines — define obligations that multiple independent subsystems must satisfy. The `Satisfies:` relationship enables a template-instance pattern: a set of requirements is defined once as a reusable template, and individual subsystems declare that they satisfy it. When a requirement declares `Satisfies: X`, the graph builder clones the template's REQ subtree with composite IDs, creating instance nodes that participate in normal coverage computation. A `Stereotype` enum (`CONCRETE`, `TEMPLATE`, `INSTANCE`) classifies nodes, and an `INSTANCE` edge connects each clone to its template original.

## Assertions

A. The system SHALL support a `Satisfies:` metadata field on requirements. The target MAY be a requirement or a specific assertion.

B. When a requirement declares `Satisfies: X`, the graph builder SHALL clone the template's REQ subtree (all descendant REQs and their assertions) with composite IDs of the form `declaring_id::original_id`. The cloned root SHALL be linked to the declaring requirement via a SATISFIES edge. Internal edges and assertions SHALL be preserved exactly as in the original. Coverage of cloned nodes SHALL use the standard coverage mechanism — no special computation is needed.

C. The system SHALL classify nodes using a `Stereotype` field: `CONCRETE` (default), `TEMPLATE` (original nodes targeted by Satisfies), or `INSTANCE` (cloned copies). Each instance node SHALL have an INSTANCE edge to its template original.

D. The system SHALL attribute `Implements:` references to template assertions to the correct instance by finding a sibling `Implements:` reference to a CONCRETE node in the same source file, walking that node's ancestors to the first node with a `Satisfies:` declaration matching the template, and constructing the instance ID from the declaring node's ID and the referenced node's ID.

*End* *Satisfies Relationship* | **Hash**: c3352c1a
---

## REQ-p00016: NOT APPLICABLE Status

**Level**: prd | **Status**: Draft | **Implements**: REQ-p00001

## Rationale

When a cross-cutting template assertion does not apply to a specific subsystem, the declaring requirement must be able to explicitly exclude it. This uses normative assertion language consistent with the rest of the spec system, and follows the same semantics as deprecated status — the assertion is excluded from the coverage denominator.

## Assertions

A. The system SHALL support explicit N/A declarations for template assertions using normative assertions on the declaring requirement (e.g., `REQ-p80001-D SHALL be NOT APPLICABLE`).

B. N/A assertions SHALL be treated the same as deprecated status: they SHALL NOT count toward the coverage target for the relevant template instance.

C. Any `Implements:` references to a N/A assertion SHALL NOT count toward coverage and SHALL produce errors.

*End* *NOT APPLICABLE Status* | **Hash**: b026a15f
---

## REQ-p00050: Unified Graph Architecture

**Level**: prd | **Status**: Active | **Implements**: REQ-p00001

The elspais system SHALL use a unified graph-based architecture where TraceGraph is the single source of truth for all requirement data, hierarchy, and metrics.

## Assertions

A. The system SHALL use TraceGraph as the ONE and ONLY data structure for representing requirement hierarchies and relationships.

B. ALL outputs (HTML, Markdown, CSV, JSON, MCP resources) SHALL consume TraceGraph directly without creating intermediate data structures.

C. The system SHALL NOT create parallel data structures that duplicate information already in the graph.

D. The system SHALL NOT have multiple code paths that independently compute hierarchy, coverage, or relationships.

## Rationale

Multiple data structures lead to synchronization bugs, duplicated logic, and maintenance burden. A single graph provides:

- Single source of truth
- Consistent hierarchy traversal
- Centralized metrics computation
- Easier testing and debugging

*End* *Unified Graph Architecture* | **Hash**: 4a1e5d0b
---

## REQ-p00060: MCP Server for AI-Driven Requirements Management

**Level**: prd | **Status**: Active | **Implements**: REQ-p00050

The elspais system SHALL provide an MCP server that enables AI agents to query, navigate, and mutate requirements through the unified TraceGraph.

## Assertions

A. The MCP server SHALL expose TraceGraph data through standardized MCP tools.

B. The MCP server SHALL consume TraceGraph directly without creating intermediate data structures, per REQ-p00050-B.

C. The MCP server SHALL provide read-only query tools for requirement discovery and navigation.

D. The MCP server SHALL provide mutation tools for AI-assisted requirement management.

E. The MCP server SHALL support undo operations for all graph mutations.

## Rationale

AI agents need programmatic access to requirements data for tasks like coverage analysis, requirement drafting, and traceability verification. The MCP protocol provides a standardized interface that works with multiple AI platforms.

*End* *MCP Server for AI-Driven Requirements Management* | **Hash**: 3ebc237a
---
