# Layer 2 — List division, salvage, aliases

`parse_ref_list()` is the one place a list is divided and the one place an item
is judged. These cases are about the list, not about the item.

Inputs are item text (keyword removed) unless a whole line is shown.

---

## 1. `E_EMPTY_ITEM`

An empty item is a formatting slip, not evidence the line was read wrongly. It
reports and is skipped; **its neighbours still bind**. Identical on every
surface — this is where the old `reject`/`keep` divergence lived.

| ID | Input | Grammar | Estate | Bindings | Verdict |
|---|---|---|---|---|---|
| EMPTY-01 | `REQ-d00001,,REQ-d00002` | G-STD | both exist | `REQ-d00001`, `REQ-d00002` | `1 -> MALFORMED / {E_EMPTY_ITEM}` |
| EMPTY-02 | `,REQ-d00001` | G-STD | exists | `REQ-d00001` | `0 -> MALFORMED / {E_EMPTY_ITEM}` |
| EMPTY-03 | `REQ-d00001, ,REQ-d00002` | G-STD | both | both | `1 -> MALFORMED / {E_EMPTY_ITEM}` — whitespace-only is empty |
| EMPTY-04 | `REQ-d00001,,,REQ-d00002` | G-STD | both | both | `1` and `2` each `E_EMPTY_ITEM` — two faults, not one |
| EMPTY-05 | `,,` | G-STD | - | none | three empty items, three faults. Not an empty reference list — there is content. |
| EMPTY-06 | `REQ-d00001,` | G-STD | exists | `REQ-d00001` | `E_TRAILING_SEPARATOR`, **not** `E_EMPTY_ITEM` — see section 2 |
| EMPTY-07 | `,` | G-STD | - | none | OPEN, Q10: leading empty + trailing separator, or one of each? |

EMPTY-01 is measured failure A. Today the empty item discards the whole line and
the entire text including the comma is recorded as one unresolvable target.
The regression assertion is that `REQ-d00001` binds.

---

## 2. `E_TRAILING_SEPARATOR`

Reported only when there is nothing to continue onto. Where there is, the
separator is the continuation signal and no fault arises (see `CONT-01`).

| ID | Input | Grammar | Surface | Estate | Bindings | Verdict |
|---|---|---|---|---|---|---|
| TSEP-01 | `# Implements: REQ-d00001,` last line of its block | G-STD | code | exists | `REQ-d00001` | `E_TRAILING_SEPARATOR` |
| TSEP-02 | `# Implements: REQ-d00001,` followed by a comment line | G-STD | code | exists | `REQ-d00001` + whatever follows | no fault — this is CONT-01 |
<!-- the trailing space inside the code span is the case -->
<!-- markdownlint-disable-next-line MD038 -->
| TSEP-03 | `# Implements: REQ-d00001, ` (separator then trailing spaces) | G-STD | code | exists | `REQ-d00001` | `E_TRAILING_SEPARATOR` — "ends in the separator" survives trailing whitespace |
| TSEP-04 | `**Implements**: REQ-d00001,` at end of the metadata block | G-STD | spec | exists | `REQ-d00001` | `E_TRAILING_SEPARATOR` |
| TSEP-05 | `# Implements: REQ-d00001,,` | G-STD | code | exists | `REQ-d00001` | `E_EMPTY_ITEM` **and** `E_TRAILING_SEPARATOR` — codes are not disjoint |
| TSEP-06 | `# Implements: not a reference,` | G-STD | code | - | none | two faults on one line: the item's, and the line's trailing separator |
| TSEP-07 | `# Implements: ,REQ-d00001,` | G-STD | code | exists | `REQ-d00001` | leading empty + trailing separator; one binding survives both |

The design says the trailing separator "reports ... and its well-formed items
still bind". TSEP-06 is the case where there are none, and the trailing-separator
report must still appear rather than being absorbed into the item fault.

---

## 3. `E_EMPTY_REFERENCE_LIST`

`Implements:` with nothing after it. Currently vanishes — the unresolved
terminal requires content after the colon. Admitting it is a grammar change.

| ID | Input | Grammar | Surface | Bindings | Verdict |
|---|---|---|---|---|---|
| NIL-01 | `# Implements:` | G-STD | code | none | `MALFORMED / {E_EMPTY_REFERENCE_LIST}`, `item_index = -1` (the content is at fault, not one item of it) |
| NIL-02 | `# Implements:` + three trailing spaces | G-STD | code | none | `E_EMPTY_REFERENCE_LIST` — same verdict; trailing whitespace is not content |
| NIL-03 | `**Implements**:` | G-STD | spec | none | `E_EMPTY_REFERENCE_LIST` |
| NIL-04 | `# IMPLEMENTS:` | G-STD | code | none | **two** findings: `E_EMPTY_REFERENCE_LIST` and `references.keyword_case`. The tiers are independent. |
| NIL-05 | `# Implements:` followed by a comment line holding `REQ-d00001` | G-STD | code | none | `E_EMPTY_REFERENCE_LIST` on line 1 and `E_ORPHAN_REFERENCE` on line 2 — an empty list does not end in the separator, so it does not continue |
| NIL-06 | `# Verifies:` | G-STD | test | none | `E_EMPTY_REFERENCE_LIST` — the rule is per keyword |

NIL-01 must produce a `ReferenceFault` with `item_index = -1`. That field exists
precisely for this shape and for NIL-03; if every fault carries a real index,
the whole-content case has been forced into an item-shaped report.

---

## 4. Salvage — a bad item costs one reference, not the line

| ID | Input | Grammar | Estate | Bindings | Verdict |
|---|---|---|---|---|---|
| SALV-01 | `REQ-d00001, not a reference, REQ-d00002` | G-STD | both exist | `REQ-d00001`, `REQ-d00002` | `1 -> MALFORMED / {E_NOT_AN_IDENTIFIER}` — item 1 has no identifier at its anchor, so the leading-identifier rule adds nothing here |
| SALV-01b | `REQ-d00001, REQ-d00002 and friends` | G-STD | both exist | `REQ-d00001`, `REQ-d00002` | `1` binds at its anchor **and** reports its residue. Two levels of salvage in one line: across items, and within an item. |
| SALV-02 | `not a reference, REQ-d00001` | G-STD | exists | `REQ-d00001` | `0 -> MALFORMED` — a bad *first* item is the one that historically poisoned the line |
| SALV-03 | `REQ-d00001, WIDGET-42` | G-STD | exists | `REQ-d00001` | `1 -> UNKNOWN_NAMESPACE` — two different buckets from one line, and the line still binds |
| SALV-04 | `REQ-d00001, REQ-d99999, REQ-d00002-Q, XREQ-d00001` | G-STD | as estate | `REQ-d00001` | four items, four verdicts: bound / `UNKNOWN_REQUIREMENT` / `UNKNOWN_ASSERTION` / `UNKNOWN_NAMESPACE`. One line spanning four buckets. |
| SALV-05 | `REQ-d00001-A+Z` | G-STD | A exists, Z does not | `REQ-d00001-A` | salvage inside an expansion |
| SALV-06 | `REQ-d00001-A+B, REQ-d99999-A+B` | G-STD | first exists | `REQ-d00001-A`, `REQ-d00001-B` | second item -> one `UNKNOWN_REQUIREMENT`, not two — the requirement fails before the expansion is reached |
| SALV-07 | `req-d00001, REQ-d00002` | G-STD | both exist | `REQ-d00002` | `0 -> MALFORMED / {E_WRONG_CASE}`. A relaxation diagnoses and never binds, so item 0 costs exactly itself. |

SALV-04 is the single best regression row for the whole ticket: it is where
"one bucket per line" is impossible by construction.

---

## 5. Duplicate items

`parse_ref_list()` holds a `seen` set and skips a repeat entirely — no item, no
binding, no diagnostic. That is silence, and silence is a bug (trait 4). These
cases record the behaviour; the expected verdict is a design question, Q11.

| ID | Input | Grammar | Estate | Observed today | Question |
|---|---|---|---|---|---|
| DUP-01 | `REQ-d00001, REQ-d00001` | G-STD | exists | one `RefItem`, index 0 | should item 1 report a duplicate? |
| DUP-02 | `REQ-d00001, req-d00001` | G-STD | exists | item 0 binds; item 1 -> `E_WRONG_CASE` (it does not normalize to the same string, so it is not deduplicated) | is that the intended asymmetry with DUP-01? |
| DUP-03 | `d00001, REQ-d00001` | G-STD (alias) | exists | both normalize to `REQ-d00001`; second is skipped silently | same as DUP-01, reached via an alias |
| DUP-04 | `not a reference, not a reference` | G-STD | - | both are faults with the same `raw`; deduplication keys on the normalized string, so OPEN whether one or two faults are reported | |
| DUP-05 | `REQ-d00001-A+A` | G-STD | A exists | duplicate inside an expansion | one edge; one report or none? |

Do not convert DUP-* into passing assertions of current behaviour without
answering Q11 first — that would pin silence into the suite.

---

## 6. Aliases and underscore notation

The implementor's design change: an item whole-matches a member's grammar
*including its configured aliases*, because an alias is a spelling the owning
configuration admits. `G-STD` configures `short = "{level.letter}{component}"`;
`G-E2E` configures none. Every row below must be run on **both** and give
different answers.

| ID | Input | Grammar | Estate | Bindings | Verdict |
|---|---|---|---|---|---|
| ALIAS-01 | `d00001` | G-STD | `REQ-d00001` | `REQ-d00001` | no fault — normalized to the canonical spelling |
| ALIAS-02 | `d00001` | G-E2E | `REQ-d00001` | none | `0 -> UNKNOWN_NAMESPACE` — no alias configured, so `d00001` names nothing |
| ALIAS-03 | `d00001-A` | G-STD | A exists | `REQ-d00001-A` | no fault |
| ALIAS-04 | `d1` | G-STD | `REQ-d00001` | none | `0 -> MALFORMED / {E_WRONG_PADDING}` — the alias is subject to the same component grammar |
| ALIAS-05 | `D00001` | G-STD | `REQ-d00001` | none | `0 -> MALFORMED / {E_WRONG_CASE}` |
| ALIAS-06 | `REQ-d00001, d00002` | G-STD | both | `REQ-d00001`, `REQ-d00002` | mixed spellings in one list both bind, and the *normalized* forms are what the graph holds |
| ALIAS-07 | `d00001, d00001` | G-STD | exists | `REQ-d00001` | duplicate via alias — see DUP-03 |
| ALIAS-08 | `d00001-A+B` | G-STD | A, B exist | `REQ-d00001-A`, `REQ-d00001-B` | expansion applies to the alias form |
| ALIAS-09 | `p00001` | G-FED | core `REQ-p00001` | OPEN | Q12: the federation members configure no aliases; does the invoking repo's alias reach a member's identifier? |

### Underscore notation

Read by `extract_underscored_ref()`, not by `parse_ref_list()`. Included because
it is the third spelling of the same identifier and a converter should check
that all three normalize to one string.

| ID | Input | Grammar | Expected |
|---|---|---|---|
| USCORE-01 | `def test_REQ_p00001_A(): ...` | G-STD | `REQ-p00001-A` |
| USCORE-02 | `def test_REQ_p00001_validates_things(): ...` | G-STD | `REQ-p00001` — a trailing lowercase run continues the name; `_v` is not a label |
| USCORE-03 | `def test_REQ_p00001_A_and_so_on(): ...` | G-STD | `REQ-p00001-A` — one label, not two |
| USCORE-04 | `def test_REQ_p00001_a(): ...` | G-STD | `REQ-p00001-A` — only the first label is read tolerantly of case. Relate to CASE-09 / Q1: label-case tolerance is deliberate *here*; the dispute is whether it belongs in a reference list. |
| USCORE-05 | `def test_REQ_p00001_A_B(): ...` | G-STD | OPEN: `REQ-p00001-A+B` or `REQ-p00001-A`? Q13. |

---

## 7. `E_AMBIGUOUS`

Two disjoint minimal relaxation sets of equal size compete. Report the generic
code **alone** and say the item is ambiguous — no specific relaxation is named,
because naming one would assert a reading the input does not determine.

| ID | Input | Grammar | Estate | Verdict |
|---|---|---|---|---|
| AMB-01 | `REQ-dToken-Store` | G-NAMED | `REQ-dTokenStore` absent, `REQ-dToken` absent | readable as component `Token-Store` or as component `Token` with label `Store`; both need one relaxation -> `MALFORMED / {E_SYNTAX_ERROR, E_AMBIGUOUS}` |
| AMB-02 | `REQ-dTokenStore-2` where both `REQ-dTokenStore` and `REQ-dTokenStore-2` could be read | G-NAMED | see note | the design's own `X-Y` / `X-Y-Z` shape |
| AMB-03 | `REQ-ALP-p00001` | G-FED with core's component style widened to admit `ALP-p00001` | contrived | two members can each read it whole -> ambiguous rather than attributed to the first resolver in iteration order. **This is the one that catches order-dependence.** |
| AMB-04 | `REQ-d00001+A` | G-STD | A exists | NOT ambiguous — `E_WRONG_ASSERTION_SEPARATOR` is a single minimal set. The negative control. |
| AMB-05 | `req-d1` | G-STD | `REQ-d00001` | NOT ambiguous — two relaxations (`E_WRONG_CASE`, `E_WRONG_PADDING`) that are the *same* minimal set, so both are reported together |

AMB-03 requires a bespoke config rather than a stock fixture. It is worth
building: iteration-order attribution is invisible until two members compete,
and `_classify()` returns the first resolver that claims a candidate.

AMB-05 is the distinction that keeps `E_AMBIGUOUS` rare: several codes in one
set is normal; two *competing* sets is ambiguity.
