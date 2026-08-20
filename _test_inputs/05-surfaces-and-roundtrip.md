# Surfaces, checks, and round-trip

Three suites that are about the whole line and the whole file rather than about
one item: uniformity across surfaces, the checks that report the buckets, and
the fixed-point obligation.

---

## 1. Uniform tolerance across surfaces

REQ-p00014-T: tolerance is uniform; divergence must be stated policy, never
fallout. The old `reject`/`keep` split was fallout.

**Method**: take one item, spell it on all five surfaces, assert an identical
`FaultClass` and code set every time. The surface is recorded on the finding but
must not change the verdict.

Items to sweep (each is a case from `01-item-cascade.md`):

| ID | Item | Expected on every surface |
|---|---|---|
| UNIF-01 | `REQ-d00001` | binds |
| UNIF-02 | `REQ-d00001,` | binds + `E_TRAILING_SEPARATOR` (measured failure A — this is where code and spec diverged) |
| UNIF-03 | `REQ-d00001,,REQ-d00002` | both bind + `E_EMPTY_ITEM` |
| UNIF-04 | `not a reference` | `MALFORMED / {E_NOT_AN_IDENTIFIER}` |
| UNIF-05 | `req-d00001` | `MALFORMED / {E_WRONG_CASE}`, no binding |
| UNIF-06 | `REQ-d00001, not a reference` | one binding, one fault |
| UNIF-07 | `WIDGET-42` | `UNKNOWN_NAMESPACE` |
| UNIF-08 | (empty) | `E_EMPTY_REFERENCE_LIST` |

Surfaces: python `#`, C-style `//`, SQL `--`, spec metadata, journey metadata.
Keywords must be chosen per surface so the relationship is permitted —
`Implements` on code and spec, `Verifies` on test, `Validates` on journey —
otherwise the sweep measures the `forbidden` matrix instead of tolerance.

---

## 2. Keyword x surface validity matrix

Every cell. `bind` means a well-formed target produces its edge; `FORBIDDEN`
means the item reads but the relationship is refused.

| Keyword | spec | code | test | journey |
|---|---|---|---|---|
| `Implements` | bind | bind | FORBIDDEN | FORBIDDEN |
| `Refines` | bind | FORBIDDEN | FORBIDDEN | FORBIDDEN |
| `Satisfies` | bind | FORBIDDEN | FORBIDDEN | FORBIDDEN |
| `Integrates` | bind (external target only) | FORBIDDEN | FORBIDDEN | FORBIDDEN |
| `Verifies` | FORBIDDEN | bind | bind | FORBIDDEN |
| `Validates` | FORBIDDEN | FORBIDDEN | FORBIDDEN | bind (metadata only) |

**This matrix assumes a decision the design does not state — see Q20.** Every
cell above assumes a surface-invalid keyword is *recognised and then refused*
(`Implements:` in a test file reaches the matrix and reports `FORBIDDEN`). The
alternative is that layer 1 never recognises it there, making the line prose and
producing no finding at all. Settle Q20 before converting any `FORBIDDEN` cell.

Every `FORBIDDEN` cell should be run with a **well-formed, existing** target, so
the verdict is unambiguously about the relationship and not about the item. Run
each cell a second time with a malformed target and assert the class is
`MALFORMED`, not `FORBIDDEN` — reading order decides, and a class is never later
than reading reached.

Additional cells that are not keyword x surface:

| ID | Case | Expected |
|---|---|---|
| MTX-01 | `Refines` targeting a CODE node | FORBIDDEN — REFINES is req->req only |
| MTX-02 | `Implements` from `prd` to `dev` | FORBIDDEN — the level hierarchy |
| MTX-03 | `Integrates` targeting a same-repo requirement | FORBIDDEN — external-only |
| MTX-04 | `Validates` in a journey *section* rather than metadata | reported, never read (PATH-43) |

---

## 3. `code.no_traceability` stops lying

The check reports a file as carrying no traceability markers whenever its code
nodes carry no edges. A file whose every reference is faulty carries markers and
must not be named.

| ID | File content | Expected |
|---|---|---|
| NOTR-01 | no comment carrying a keyword | named by `code.no_traceability` — the true positive |
| NOTR-02 | `# Implements: REQ-d00001` (exists) | not named; one edge |
| NOTR-03 | `# Implements: not a reference` | **not named**; one reference fault. Separate "no markers" from "markers that produced no relationship". |
| NOTR-04 | `# Implements:` | not named; `E_EMPTY_REFERENCE_LIST` |
| NOTR-05 | `# Implements: REQ-d00001, not a reference` | not named; one edge, one fault. Salvage alone fixes this row. |
| NOTR-06 | `# Implements: REQ-d99999` | not named; `UNKNOWN_REQUIREMENT` |
| NOTR-07 | `# Refines: REQ-d00001` in a code file | not named; `FORBIDDEN`. The keyword is a marker even when the relationship is refused. |
| NOTR-08 | `# implements: REQ-d00001` | not named; one edge; keyword-case finding |
| NOTR-09 | `# Implements REQ-d00001` (no colon — prose) | **named**. Prose is not a marker, so the check is right here, and the row guards against over-correcting. |

NOTR-03, NOTR-04 and NOTR-07 are the three callisto workflow files. NOTR-09 is
the boundary that keeps the fix honest.

---

## 4. Summary surface

The design's own worked rendering. Assert the shape as well as the numbers: the
three `unknown_*` buckets group under one heading while remaining separately
configurable.

```text
references
  malformed        3    does not read as a reference
  unknown referent
    namespace    108    no configured repository claims this identifier
    requirement    2    claimed, but no such requirement exists
    assertion      1    the requirement exists, but not that label
  forbidden        1    exists, but not for this keyword
```

| ID | Case | Expected |
|---|---|---|
| SUM-01 | SALV-04's line, alone in a project | `malformed 0 / namespace 1 / requirement 1 / assertion 1 / forbidden 0`, and one edge in the graph |
| SUM-02 | set `unknown_namespace = "ok"` | the namespace row is suppressed; malformed still reports. This is the replacement for `validation.allow_unresolved_cross_repo` and the reason it is retired. |
| SUM-03 | set `unknown_namespace = "ok"` with a syntax error present | the syntax error **still** reports. The whole point: the retired flag took syntax errors down as collateral. |
| SUM-04 | each of the five buckets set to `failing` in turn | exit status changes for that bucket only |
| SUM-05 | a config still carrying `validation.allow_unresolved_cross_repo` | refused with a message naming the replacement — the estate refuses a superseded setting rather than dropping it (see commit `8c7627e0`) |
| SUM-06 | one finding | appears under exactly one bucket. Double-reporting is a class of the truthful-reporting catalog. |
| SUM-07 | detail report for any fault | names the code, the item, and the item's position — not merely the line |

---

## 5. Round-trip

The trait most easily lost and least visibly: **every classification outcome, on
every surface, followed by `fix`, with the author's text unchanged.**

Method: build a fixture holding one file per surface, each carrying every case
from files 01–04 that is expected to produce a fault. Run `fix`. Diff.

| ID | Assertion |
|---|---|
| RT-01 | A code file's text is byte-identical after `fix`. elspais does not rewrite code, so this is absolute. |
| RT-02 | A test file's text is byte-identical after `fix`. |
| RT-03 | A spec file's *unresolved reference text* survives verbatim (REQ-d00132-G) — a malformed item must not be dropped, repaired or reordered by the metadata renderer. |
| RT-04 | `fix` twice = `fix` once, on a file holding faults on every surface (REQ-d00248-A, the fixed point). |
| RT-05 | A wrong-case keyword in **spec** metadata is canonicalised by `fix`; in **code** it is untouched. The asymmetry is a consequence of what each surface renders, so assert both halves in one test. |
| RT-06 | A wrong-emphasis keyword in spec metadata is canonicalised; in code untouched. |
| RT-07 | `fix` on a file carrying `E_EMPTY_REFERENCE_LIST` does not delete the empty keyword line. |
| RT-08 | `fix` on a file carrying a trailing separator does not silently repair it — the diagnostic exists because the tool does not guess. OPEN for spec metadata, where the renderer legitimately rewrites the line: Q19. |
| RT-09 | Requirement hashes are unchanged under the default `normalized-text` mode across all of the above. |

RT-04 is the assertion that should be parametrized over every fixture grammar,
because a renderer that canonicalises under one config and not another is how a
fixed-point violation hides.

---

## 6. Phase B — the metadata block and progressive splitting

Deferred, listed here so phase A's suite does not have to be rewritten to hold
them.

| ID | Case | Expected |
|---|---|---|
| FMT-01 | metadata fitting the width | one line, fields pipe-separated |
| FMT-02 | metadata exceeding the width | split at the fields, one field per line |
| FMT-03 | one field still exceeding the width | exploded, one reference per line, each line but the last ending in `,` |
| FMT-04 | an exploded list re-read | binds every reference — the explosion form **is** the continuation form |
| FMT-05 | a reference added to an exploded list | exactly one line changes |
| FMT-06 | a reference removed such that the field now fits | re-joins. **No sticky explosion**: output depends on content and width alone, never on the file's prior state. |
| FMT-07 | width configured under `[output]` to something other than 100 | reflow follows it |
| FMT-08 | `fix` twice on an exploded file | idempotent |
| FMT-09 | the longest metadata line in this repository (92 chars) | does not reflow at the default width — the stated no-op for this estate |
| FMT-10 | a metadata line after prose | reported, not merged (PATH-42) |
| FMT-11 | exploded list containing a malformed item | the malformed item survives the reflow verbatim (RT-03 under explosion) |
