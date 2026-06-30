# Design evaluation: a shared "container + addressable sub-units" abstraction

**Date:** 2026-06-30
**Status:** Evaluation (decision recorded below)
**Context:** CUR-1556 added `USER_JOURNEY → STEP` as the journey-axis twin of
`REQUIREMENT → ASSERTION`. This doc evaluates whether the two structures should
be unified under one base abstraction, per a request to assess code-sharing,
duplication, and quality before committing to any rewrite.

## Question

Should `REQUIREMENT/ASSERTION` and `USER_JOURNEY/STEP` become instances of a
single "container with addressable typed sub-units" abstraction (shared base
type and/or shared code paths)?

## Bottom line

The abstraction is **well-justified and low-risk for the read/coverage/serialize/
render-card axis**, but **forcing it onto the write/persist axis is a large, risky
project** that collides with a hard project directive (CLAUDE.md: *"DO NOT change
the structure of Graph/GraphTrace/GraphBuilder; do not violate the current
encapsulation"*) and with YAGNI.

Recommendation: capture the genuine commonality via **shared helpers + a thin
`AddressableUnit` protocol** (composition), and explicitly **decline a literal
unifying base class** that spans persistence/mutation/render until there is a
concrete driver for editable steps.

## The core finding: commonality is on the read side; divergence is on the write side

The two structures already share the graph *primitives* — `STRUCTURES` edges with
`render_order`, the suffix-id convention, `direct_coverage_for` (REQUIREMENT and
STEP literally share its outgoing-edge branch today), and the GUI serialization
envelope. They genuinely diverge in **how the parent is persisted**:

| Axis | Assertion (in REQUIREMENT) | Step (in JOURNEY) |
|---|---|---|
| Source of truth | the **graph node IS truth**; text reconstructed from children | a **read-only shadow** of verbatim `body`/`sections` text |
| Editable | full CRUD + undo + MCP tools | none, by design |
| Renders to disk | reconstructed from children (`_render_requirement`) | journey renders verbatim `body`; steps never consulted |

A literal base *class* would be clean for the read half and **leaky for the write
half** (pervasive `if kind == STEP` overrides in render/mutation), which is worse
than honest separation.

## Inventory (where they share / duplicate / diverge)

| Area | Verdict | Unify effort |
|---|---|---|
| 1. Builder child-node creation (`_add_requirement` 3221-3303 vs `_add_journey` 3436-3456) | DUPLICATED (near-identical link/render_order loop) | Small — one `_add_typed_children` helper |
| 2. ID formation + rename cascade (`builder.py` 971-982 vs 984-999) + shared undo gap | DUPLICATED (+ shared bug) | Small — one cascade helper + undo id-map |
| 3. Coverage rollup — leaf (`direct_coverage_for`) | already SHARED | — |
| 3. Coverage rollup — parent loop (`annotate_coverage` ~250 lines, 6-dim+transitive vs `annotate_journey_verification` ~50 lines, 1 tier) | DIVERGENT | Medium — a shared `tier_from_children` only |
| 4. GUI serialization (`_serialize_node_generic`) | SHARED envelope / missing per-step payload | Small–Med — add STEP data branch + per-step coverage |
| 5. Card rendering (`buildAssertionHtml` vs `buildJourneyCardHtml`) | DIVERGENT now / DUPLICATE-in-waiting | Medium — parameterize the assertion-row builder + step caller |
| 6. Mutation API (assertions: full CRUD+undo+MCP; steps: none) | DIVERGENT by design | Large — 4-layer assertion-parity set + step↔text reconciliation |
| 7. Render to disk (reconstructive vs verbatim-body) | DIVERGENT (biggest) | Largest — port the REQ render+persist pipeline onto journeys |

## Risks

1. **Encapsulation directive.** Areas 1–5 are achievable as helper functions
   inside existing modules (compatible). Areas 6–7 restructure the node-kind model
   and journey persistence — they brush directly against the CLAUDE.md directive
   and need explicit sign-off to revisit.
2. **Over-abstraction.** The structures are ~80% similar on read, ~20% on write.
   A base class forced over both makes the 20% leak everywhere. Shared helpers + a
   thin protocol (a container exposing `iter_units()`; a unit exposing
   `label`/`render_order`/`status`) capture the 80% without lying about the 20%.

## Incidental bug (independent of this decision)

`_undo_rename_node` (`builder.py:479-486`) reverses only the parent id; it does
**not** reverse the child-id cascade for **either** assertions or steps. So
`rename → undo` leaves child ids stale on both axes. Small standalone fix.

## Decision

- **Do (small, serves the motivating need — implemented in PR #100):** render
  steps on the journey card by adding a per-step serialization branch symmetric to
  the assertion one and a step-row renderer that reuses the verification-badge
  styling. No graph-model restructure.
- **Do (small, encapsulation-safe):** fix the `_undo_rename_node` child-cascade
  bug.
- **Optional later (low-risk cleanup):** extract the duplicated child-creation and
  rename-cascade into shared helpers (areas 1, 2).
- **Defer / decline:** the full base abstraction with editable steps and
  graph-is-truth journey rendering (areas 6–7). High cost, collides with the
  encapsulation directive, unjustified without a concrete need for editable steps.

In short: adopt the abstraction's *spirit* (shared helpers + a thin protocol for
the read/coverage/serialize/card path); decline its *literal form* (a unifying
base class over the persistence model) for now.
