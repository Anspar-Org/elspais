# trace-view User Guide

This guide covers the enhanced traceability visualization features available in elspais when installed with optional dependencies.

## Installation

### Basic trace-view (HTML generation)

```bash
pip install elspais[trace-view]
```text

This installs Jinja2 for template-based HTML generation.

### Full trace-view with review server

```bash
pip install elspais[trace-review]
```text

This adds Flask and Flask-CORS for the collaborative review server.

### All optional features

```bash
pip install elspais[all]
```text

## Quick Start

```bash
# Generate interactive HTML traceability view
elspais trace --view -o trace.html

# Start review server for collaborative feedback
elspais trace --server

# Generate HTML with embedded content
elspais trace --view --embed-content -o trace.html
```text

## CLI Options

### Enhanced Trace Command

When trace-view is installed, the `elspais trace` command gains these options:

| Option | Description |
|--------|-------------|
| `--view` | Generate interactive HTML view (requires jinja2) |
| `--embed-content` | Embed full requirement content in HTML |
| `--edit-mode` | Enable client-side editing features |
| `--review-mode` | Enable collaborative review annotations |
| `--server` | Start Flask review server |
| `--port PORT` | Server port (default: 8080) |
| `--mode {core,combined}` | Include sponsor specs in output |
| `--sponsor NAME` | Filter to specific sponsor |

### Basic Examples

```bash
# Simple HTML matrix (no extras needed)
elspais trace --format html -o matrix.html

# Interactive trace-view HTML
elspais trace --view -o trace.html

# With embedded content for offline viewing
elspais trace --view --embed-content -o trace.html

# Enable editing features
elspais trace --view --edit-mode -o trace.html

# Include sponsor repository requirements
elspais trace --view --mode combined -o trace.html
```text

## Review Server

The review server provides a REST API for collaborative requirement review.

### Starting the Server

```bash
# Default port 8080
elspais trace --server

# Custom port
elspais trace --server --port 3000
```text

### API Endpoints

The server exposes these endpoints:

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/requirements` | List all requirements |
| GET | `/api/requirements/{id}` | Get requirement details |
| GET | `/api/threads` | List review threads |
| POST | `/api/threads` | Create new thread |
| GET | `/api/threads/{id}` | Get thread with comments |
| POST | `/api/threads/{id}/comments` | Add comment to thread |
| PUT | `/api/comments/{id}` | Update comment |
| DELETE | `/api/comments/{id}` | Delete comment |
| POST | `/api/requirements/{id}/flag` | Flag requirement for review |
| POST | `/api/requirements/{id}/status` | Request status change |
| GET | `/api/branches` | List review branches |
| POST | `/api/branches` | Create review branch |

### Data Storage

Review data is stored in `.elspais/reviews/`:

- `comments.json` - Thread and comment data
- `flags.json` - Review flags
- `status_requests.json` - Status change requests

## HTML Generation

### Template System

The HTML generator uses Jinja2 templates located in `trace_view/html/templates/`:

- `base.html` - Base template with common structure
- `trace.html` - Main traceability matrix view
- `requirement.html` - Single requirement detail view

### Customization

Templates use these CSS classes for styling:

- `.requirement-card` - Requirement display container
- `.level-prd`, `.level-dev`, `.level-ops` - Level indicators
- `.status-active`, `.status-draft` - Status indicators
- `.git-modified`, `.git-uncommitted` - Git state indicators

### JavaScript Features

When `--edit-mode` or `--review-mode` is enabled:

- Click requirement to expand/collapse
- Inline editing of requirement fields
- Comment threads on requirements
- Status change requests

## Requirement Reformatting

The `reformat-with-claude` command uses AI to transform legacy requirements from "Acceptance Criteria" to "Assertions" format.

### Usage

```bash
# Preview changes (no modifications)
elspais reformat-with-claude --dry-run

# Create backups before changes
elspais reformat-with-claude --backup

# Start from specific requirement
elspais reformat-with-claude --start-req REQ-p00010

# Reformat with cross-repo hierarchy (for associated repositories)
elspais reformat-with-claude --mode combined

# Reformat only local requirements
elspais reformat-with-claude --mode local-only
```text

### Format Transformation

Converts from:

```markdown
**Acceptance Criteria**:
- The system does X
- The system provides Y
```text

To:

```markdown
## Assertions

A. The system SHALL do X.
B. The system SHALL provide Y.
```text

### Options

| Option | Description |
|--------|-------------|
| `--dry-run` | Preview without modifying files |
| `--backup` | Create .bak files before changes |
| `--start-req ID` | Start processing from this requirement |
| `--depth N` | Maximum traversal depth (default: unlimited) |
| `--mode {combined,core-only,local-only}` | Which repos to include in hierarchy (default: combined) |
| `--force` | Reformat even if already in new format |
| `--fix-line-breaks` | Normalize line breaks during reformatting |
| `--line-breaks-only` | Only fix line breaks, skip AI reformatting |
| `--verbose` | Show detailed progress |

### Cross-Repository Support (v0.11.0+)

When working in an associated repository that implements requirements from a core repository, use `--mode combined` to build the complete hierarchy graph across repository boundaries.

**Example**: Starting from a core PRD requirement, the command will traverse into associated repository DEV requirements that implement it, ensuring proper hierarchical reformatting.

See [Commands Reference](commands.md#reformat-with-claude) for detailed documentation.

## Architecture

### Package Structure

```text
src/elspais/trace_view/
├── __init__.py          # Public API
├── models.py            # TraceViewRequirement adapter
├── coverage.py          # Coverage calculations
├── scanning.py          # Implementation scanning
├── generators/
│   ├── base.py         # TraceViewGenerator base
│   ├── markdown.py     # Markdown output
│   └── csv.py          # CSV export
├── html/
│   ├── __init__.py     # JINJA2_AVAILABLE flag
│   ├── generator.py    # HTMLGenerator
│   ├── templates/      # Jinja2 templates
│   └── static/         # CSS/JS assets
└── review/
    ├── __init__.py     # FLASK_AVAILABLE flag
    ├── models.py       # Comment, Thread, etc.
    ├── storage.py      # JSON persistence
    ├── branches.py     # Git branch management
    └── server.py       # Flask application
```text

### TraceViewRequirement

The `TraceViewRequirement` class wraps core requirements with visualization metadata:

```python
from elspais.trace_view.models import TraceViewRequirement, GitChangeInfo

# Create from core requirement
tv_req = TraceViewRequirement.from_core(core_req)

# Inject git state
tv_req.git_info = GitChangeInfo(
    is_modified=True,
    is_uncommitted=False,
    moved_from=None
)

# Access properties
print(tv_req.display_filename)  # Relative path
print(tv_req.is_roadmap)        # True if in roadmap/
```text

### Coverage Calculation

```python
from elspais.trace_view.coverage import (
    calculate_coverage,
    count_by_level,
    find_orphaned_requirements
)

# Get coverage statistics
stats = calculate_coverage(requirements)
print(f"Total: {stats.total}, Covered: {stats.covered}")

# Count by level
counts = count_by_level(requirements)
print(f"PRD: {counts['PRD']}, Dev: {counts['Dev']}")

# Find orphans (no parent)
orphans = find_orphaned_requirements(requirements)
```text

## Troubleshooting

### Missing Dependencies

```text
ImportError: trace-view features require jinja2
Install with: pip install elspais[trace-view]
```text

Install the required extras.

### Server Won't Start

Check port availability:

```bash
lsof -i :8080
```text

Use a different port:

```bash
elspais trace --server --port 3001
```text

### Template Not Found

Ensure package data is installed correctly:

```bash
pip install -e ".[trace-view]"
```text

## Requirements

This feature implements:

- REQ-tv-p00001: HTML Generator Maintainability
- REQ-tv-d00001: Jinja2 Template Architecture
- REQ-tv-p00002: Collaborative Review System
- REQ-tv-d00014: Review API Server
- REQ-int-d00003: CLI Extension
