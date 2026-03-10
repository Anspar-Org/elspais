# analysis

Analyze foundational requirement importance using graph-based metrics. Identifies which requirements are most structurally critical and which uncovered leaf requirements would deliver the most impact if addressed.

## Usage

```
elspais analysis [OPTIONS]
```

## How it works

The analysis builds the full traceability graph, then computes three complementary metrics for each requirement node:

| Metric | Description |
|--------|-------------|
| **Centrality** | PageRank-style score with reversed edges. Requirements that many children point to score higher, indicating cross-cutting structural importance. |
| **Fan-in** | Number of distinct root-level subtrees that can reach a node. Higher fan-in means the requirement is depended on across multiple independent branches. |
| **Uncovered** | Count of leaf descendants with zero coverage. Highlights requirements whose subtrees have the most unverified work remaining. |

These three metrics are combined into a weighted **composite score** used to rank results.

## Output sections

The command produces two ranked lists:

- **Top Foundations** — non-leaf requirements with the highest composite scores. These are the most structurally important nodes in the graph.
- **Most Impactful Work Items** — uncovered leaf requirements ranked by their ancestors' composite scores. These are the highest-leverage items to work on next.

## Options

| Option | Description |
|--------|-------------|
| `--top N` | Number of top results to show per section (default: 10) |
| `--weights W1,W2,W3` | Centrality, fan-in, uncovered weights (default: 0.4,0.3,0.3) |
| `--format` | Output format: `table`, `json` (default: table) |
| `--show` | Which sections to show: `foundations`, `leaves`, `all` (default: all) |
| `--level` | Filter results by requirement level: `prd`, `ops`, `dev` |
| `--include-code` | Include CODE nodes in the analysis graph |

## Examples

```bash
# Default analysis — top 10 foundations and work items
elspais analysis

# Show only the top 5 foundations
elspais analysis --top 5 --show foundations

# Filter to OPS-level requirements
elspais analysis --level ops

# Custom weights emphasizing uncovered dependents
elspais analysis --weights 0.2,0.2,0.6

# JSON output for scripting
elspais analysis --format json
```

### Example table output

```
Top Foundations:
  Rank  ID              Title                           Centrality  Fan-In  Uncovered  Score
  ----  ----------      ------------------------------  ----------  ------  ---------  -----
     1  REQ-p00001      Core Platform Requirements        0.0842       3          5   0.87
     2  REQ-o00010      Deployment Pipeline                0.0614       2          3   0.65
     3  REQ-o00005      Authentication System              0.0531       2          2   0.58

Most Impactful Work Items:
  Rank  ID              Title                           Level  Score
  ----  ----------      ------------------------------  -----  -----
     1  REQ-d00042      OAuth token refresh             DEV     0.31
     2  REQ-d00018      Health check endpoint           DEV     0.28
```

## Exit codes

- `0` — Analysis completed successfully
- `1` — Error (invalid weights, graph build failure)
