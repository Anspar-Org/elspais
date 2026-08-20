# Layer 2 — The item cascade

One section per fault code, plus one per bucket that has no code of its own.
Read `README.md` for the schema, the grammar key and the companion estate.

Inputs in this file are **item text**, i.e. what remains after the keyword and
its colon are removed, unless the case shows a whole line. A converter should
run each item through `parse_ref_list()` directly *and* through at least one
whole-line surface, since trait "tolerance is uniform across surfaces" is the
one this catalog is least able to check by inspection.

---

## 1. `E_NOT_AN_IDENTIFIER` — the whitespace test, and the leading-identifier rule

Two rules. The second amends the design — see Q21.

1. **Whitespace inside an item means it was not written as an identifier.** No
   shape heuristic.
2. **An item that *begins* with a whole identifier binds it**, and the residue
   after it is reported. The match is anchored at position 0 and is maximal, so
   `FROG-system-01` can never yield `ROG-system-01`. Anchoring, not abstention,
   is what guards against the invented edge. **Exactly one identifier binds per
   item**: a second one inside the residue does not, or the anchor has been
   abandoned and the search is unbounded again.

The two do not conflict. Rule 1 decides the item is faulty; rule 2 decides a
prefix of it is nonetheless readable. So an item may carry a binding *and* a
fault — see the structural note below the table.

| ID | Input | Grammar | Surface | Estate | Bindings | Verdict |
|---|---|---|---|---|---|---|
| NOTID-01 | `see the design doc` | G-STD | all | - | none | `0 -> MALFORMED / {E_NOT_AN_IDENTIFIER}` |
| NOTID-02 | `REQ-d00001 and REQ-d00002` | G-STD | all | both exist | `REQ-d00001` **only** | `0 -> MALFORMED / {E_NOT_AN_IDENTIFIER}`, residue `and REQ-d00002`. The second identifier must NOT bind — it sits inside the residue, not at the anchor. |
<!-- the trailing space inside the code span is the case -->
<!-- markdownlint-disable-next-line MD038 -->
| NOTID-03 | `REQ-d00001 ` (one trailing space, no separator) | G-STD | all | `REQ-d00001` | `REQ-d00001` | binds — the item is stripped before judging, so this is **not** a fault |
| NOTID-04 | `REQ-d00001\tREQ-d00002` (a literal tab between them) | G-STD | all | both | first only | as NOTID-02; a tab is whitespace |
| NOTID-05 | `REQ-p00047 (A` | G-STD | code | `REQ-p00047` **absent** | none | `0 -> UNKNOWN_REQUIREMENT` on the anchored `REQ-p00047`, plus the residue fault. The anchor reads; the index does not hold it. |
| NOTID-06 | `A reference to REQ-d00001` | G-STD | all | `REQ-d00001` | **none** | `0 -> MALFORMED / {E_NOT_AN_IDENTIFIER}` — position 0 holds `A`, not an identifier. Position still decides (problem statement C); it is anchored now rather than ignored. |
| NOTID-07 | `REQ-d00001 REQ-d00001` | G-STD | all | `REQ-d00001` | `REQ-d00001` once | one binding from the anchor, residue reported. Not a deduplication question. |
| NOTID-08 | `REQ -d00001` (non-breaking space) | G-STD | all | - | OPEN | Q7, and it now decides a *binding* as well as a code: if that space is whitespace, the anchor candidate is `REQ` and fails; if it is not, the item is one token. |
| NOTID-09 | `REQ-d00001-A and REQ-d00001-B` | G-STD | all | A, B exist | `REQ-d00001-A` only | the anchored match is maximal, so it takes the label; `and REQ-d00001-B` is residue |

NOTID-02 and NOTID-06 are the pair to assert **together**. The first binds
because the identifier is at the anchor; the second does not because it is not.
A rule that binds both has stopped anchoring; a rule that binds neither has not
been implemented.

**Structural consequence.** `RefItem` documents "Exactly one of `resolved` and
`fault_class` is set." Rule 2 breaks that invariant — NOTID-02 produces an item
that resolved *and* is faulty. Either the dataclass admits both, or the item
yields a binding plus a separate fault. That is an implementation decision, not
a wording one; it is Q21.

### The callisto shape, whole

The measured wild syntax, and the case rule 2 exists for.

| ID | Input | Grammar | Surface | Estate | Bindings | Verdict |
|---|---|---|---|---|---|---|
| NOTID-10 | `# Implements: REQ-p00001 (A, C, F)` | G-STD | code | `REQ-p00001` (A, B) | `REQ-p00001` | three items. `0` = `REQ-p00001 (A` -> binds `REQ-p00001` at the anchor, residue `(A` reported. `1` = `C` -> `UNKNOWN_NAMESPACE`. `2` = `F)` -> `UNKNOWN_NAMESPACE`. |
| NOTID-11 | `# Implements: REQ-p00001(A, C, F)` | G-STD | code | as above | OPEN | item 0 is `REQ-p00001(A` — identifier then punctuation, no whitespace. Whether the anchor rule extends to a non-whitespace residue is Q22. |
| NOTID-12 | `# Implements: ROG-system-01/A and ROG-system-01/B` | a config whose canonical form is `ROG-system-01/A` | code | both exist | `ROG-system-01/A` only | one binding; residue `and ROG-system-01/B` reported as not an identifier — or as a missing separator, Q23 |
| NOTID-13 | `# Implements: FROG-system-01` | same config | code | `ROG-system-01` exists | **none** | the guard. Anchored matching must fail here, and it must be run in the same suite as NOTID-12 — they are the two halves of one rule. |

Items 1 and 2 of NOTID-10 have no whitespace and match no namespace, so they are
`unknown_namespace` and described as identifiers — the consequence the design
states explicitly and accepts.

NOTID-10 changes character under rule 2: `REQ-p00001` now binds, which is a
*blanket* edge to the requirement where the author meant assertions A, C and F.
That is honest — they wrote the requirement's name — but blanket and
assertion-targeted evidence enter the two coverage footings differently
(REQ-d00069-J/L), so this is a coverage change and not only a diagnostic one.
Decide it deliberately rather than inheriting it.

---

## 2. `E_IDENTIFIER_WITH_TRAILING_TEXT`

An item that *begins* with a valid identifier and continues into text the
grammar cannot account for.

**Whether the anchored identifier binds here is Q22.** Section 1's rule 2 binds
it when the residue is whitespace-separated. Every case below has a residue that
abuts the identifier with no space, and the two readings are:

- **Symmetric with rule 2** — the anchor binds and the residue is reported, so
  `REQ-d00001.` at the end of a sentence costs nothing.
- **Whitespace is the boundary** — an abutting residue means the author wrote
  one token, and one token that does not whole-match does not bind. `REQ-d00001;REQ-d00002`
  (TRAIL-04) is the case that argues for this: binding the first and dropping
  the second silently loses a reference the author plainly named.

The `Bindings` column below records the second reading, which is what the design
as written says. Flip the whole table if Q22 goes the other way — do not flip
rows individually, since the split would be arbitrary.

| ID | Input | Grammar | Surface | Estate | Bindings | Verdict |
|---|---|---|---|---|---|---|
| TRAIL-01 | `REQ-d00001(see note)` | G-STD | all | `REQ-d00001` | none | `0 -> MALFORMED / {E_IDENTIFIER_WITH_TRAILING_TEXT}`; the message names `REQ-d00001` and the residue `(see note)` |
| TRAIL-02 | `REQ-d00001:` | G-STD | all | `REQ-d00001` | none | `0 -> MALFORMED / {E_IDENTIFIER_WITH_TRAILING_TEXT}` |
| TRAIL-03 | `REQ-d00001.` | G-STD | all | `REQ-d00001` | none | `0 -> MALFORMED / {E_IDENTIFIER_WITH_TRAILING_TEXT}` — sentence punctuation is the commonest instance |
| TRAIL-04 | `REQ-d00001;REQ-d00002` | G-STD | all | both | none | `0 -> MALFORMED / {E_IDENTIFIER_WITH_TRAILING_TEXT}` — a wrong list separator is trailing text, not a list |
| TRAIL-05 | `REQ-d00001-A-B` | G-STD | all | `REQ-d00001` (A, B) | none | OPEN: `E_WRONG_MULTI_SEPARATOR` (read as `A+B` with the wrong separator) or `E_IDENTIFIER_WITH_TRAILING_TEXT` (residue `-B`). Minimal-relaxation should pick the former. Q3. |
| TRAIL-06 | `REQ-d00001**` | G-STD | spec | `REQ-d00001` | none | `0 -> MALFORMED / {E_IDENTIFIER_WITH_TRAILING_TEXT}` — stray emphasis leaking into the value |
| TRAIL-07 | `REQ-d00001)` | G-STD | all | `REQ-d00001` | none | `0 -> MALFORMED / {E_IDENTIFIER_WITH_TRAILING_TEXT}` |

### The negative that guards binding-strictness

| ID | Input | Grammar | Surface | Estate | Bindings | Verdict |
|---|---|---|---|---|---|---|
| TRAIL-20 | `XREQ-d00001` | G-STD | all | `REQ-d00001` | **none** | must NOT bind `REQ-d00001`. Expected `0 -> UNKNOWN_NAMESPACE` (no whitespace, leading component matches no declared namespace), **not** `E_IDENTIFIER_WITH_TRAILING_TEXT` — the unaccounted text is *leading*, and the code names a trailing residue. |
| TRAIL-21 | `(REQ-d00001)` | G-STD | all | `REQ-d00001` | none | as TRAIL-20: leading residue, must not bind |
| TRAIL-22 | `-REQ-d00001` | G-STD | all | `REQ-d00001` | none | must not bind |
| TRAIL-23 | `REQ-d000010` | G-STD | all | `REQ-d00001` | none | must not bind `REQ-d00001`. Six digits against a five-digit grammar -> `E_WRONG_PADDING` at most; never a prefix match. |

TRAIL-20 and TRAIL-23 are the two that catch a regex that forgot to anchor. Run
them on every grammar, not only `G-STD`.

Under section 1's rule 2 these become the load-bearing cases of the whole
cascade. Rule 2 makes matching anchored-and-maximal rather than whole-item, and
the *only* thing then standing between `XREQ-d00001` and a binding is that the
anchor is at position 0. NOTID-13 (`FROG-system-01`) is the same guard in the
user-supplied grammar. All four should be in one suite with a comment saying
what they protect, because a later "be a bit more helpful" change reads as
harmless and silently deletes the guarantee.

---

## 3. `E_WRONG_CASE`

Case is never repaired for a component or a namespace. The relaxation exists to
diagnose, and the item produces no edge.

| ID | Input | Grammar | Surface | Estate | Bindings | Verdict |
|---|---|---|---|---|---|---|
| CASE-01 | `req-d00001` | G-STD | all | `REQ-d00001` | none | `0 -> MALFORMED / {E_WRONG_CASE}` |
| CASE-02 | `REQ-D00001` | G-STD | all | `REQ-d00001` | none | `0 -> MALFORMED / {E_WRONG_CASE}` |
| CASE-03 | `Req-D00001` | G-STD | all | `REQ-d00001` | none | `0 -> MALFORMED / {E_WRONG_CASE}` — one code, not two; the relaxation is the dimension, not the character |
| CASE-04 | `dev-00010` | G-FDA | all | `DEV-00010` | none | `0 -> MALFORMED / {E_WRONG_CASE}` — the level name *is* the type token here |
| CASE-05 | `REQ-dtokenstore` | G-NAMED | all | `REQ-dTokenStore` | none | `0 -> MALFORMED / {E_WRONG_CASE}` — PascalCase component, so case is the whole identity |
| CASE-06 | `REQ-DTokenStore` | G-NAMED | all | `REQ-dTokenStore` | none | `0 -> MALFORMED / {E_WRONG_CASE}` |
| CASE-07 | `proj-7` | G-JIRA | all | `PROJ-7` | none | `0 -> MALFORMED / {E_WRONG_CASE}` |
| CASE-08 | `req-alp-p00001` | G-FED | all | alpha `REQ-ALP-p00001` | none | `0 -> MALFORMED / {E_WRONG_CASE}`, attributed to **alpha**, not core |
| CASE-09 | `REQ-d00001-a` | G-STD | all | `REQ-d00001` (A) | **DISPUTED** | Q1 — `_classify()` currently repairs label case and would bind `REQ-d00001-A`; REQ-d00212-R and the design say recovery never repairs. Record both. |

CASE-09 must not be quietly dropped from the catalog. It is the one place the
implementation and the stated obligation are known to disagree.

---

## 4. `E_WRONG_PADDING`

| ID | Input | Grammar | Surface | Estate | Bindings | Verdict |
|---|---|---|---|---|---|---|
| PAD-01 | `REQ-d1` | G-STD | all | `REQ-d00001` | none | `0 -> MALFORMED / {E_WRONG_PADDING}` |
| PAD-02 | `REQ-d001` | G-STD | all | `REQ-d00001` | none | `0 -> MALFORMED / {E_WRONG_PADDING}` |
| PAD-03 | `REQ-d000001` | G-STD | all | `REQ-d00001` | none | `0 -> MALFORMED / {E_WRONG_PADDING}` — over-padding, not under |
| PAD-04 | `DEV-10` | G-FDA | all | `DEV-00010` | none | `0 -> MALFORMED / {E_WRONG_PADDING}` |
| PAD-05 | `PROJ-007` | G-JIRA | all | `PROJ-7` | none | OPEN: `digits = 0, leading_zeros = false` may accept `\d+` whole, in which case this reads as a distinct (absent) requirement `PROJ-007` -> `UNKNOWN_REQUIREMENT`. Q2. |
| PAD-06 | `PROJ-7-1` | G-JIRA | all | `PROJ-7` (01) | none | `0 -> MALFORMED / {E_WRONG_PADDING}` — the *label* is zero-padded in this grammar |
| PAD-07 | `PROJ-7-001` | G-JIRA | all | `PROJ-7` (01) | none | `0 -> MALFORMED / {E_WRONG_PADDING}` |
| PAD-08 | `REQ-d00001-0A` | G-STD | all | `REQ-d00001` (A) | none | `0 -> MALFORMED / {E_LABEL_OUT_OF_SERIES}` or `{E_WRONG_PADDING}` — OPEN, Q3: padding is not a dimension of an uppercase series |
| PAD-09 | `REQ-p1` | G-STD | all | `REQ-p00001` | none | `0 -> MALFORMED / {E_WRONG_PADDING}` |
| PAD-10 | `d1` | G-STD | all | `REQ-d00001` | none | `0 -> MALFORMED / {E_WRONG_PADDING}` — the alias form is padded too |

PAD-10 only means anything under `G-STD`. Under `G-E2E` the same text is
`UNKNOWN_NAMESPACE` (no alias configured), which is ALIAS-04 in
`03-lists-and-salvage.md`.

---

## 5. `E_WRONG_ASSERTION_SEPARATOR`

The separator between component and label. `-` in every configuration here, so
the fault is any other character in that position.

| ID | Input | Grammar | Surface | Estate | Bindings | Verdict |
|---|---|---|---|---|---|---|
| ASEP-01 | `REQ-d00001+A` | G-STD | all | `REQ-d00001` (A) | none | `0 -> MALFORMED / {E_WRONG_ASSERTION_SEPARATOR}` — the design's own worked example |
| ASEP-02 | `REQ-d00001.A` | G-STD | all | `REQ-d00001` (A) | none | `0 -> MALFORMED / {E_WRONG_ASSERTION_SEPARATOR}` |
| ASEP-03 | `REQ-d00001_A` | G-STD | all | `REQ-d00001` (A) | none | `0 -> MALFORMED / {E_WRONG_ASSERTION_SEPARATOR}` — underscore notation is for function names, not for a reference list |
| ASEP-04 | `REQ-d00001/A` | G-STD | all | `REQ-d00001` (A) | none | `0 -> MALFORMED / {E_WRONG_ASSERTION_SEPARATOR}` — `Refines: P/A` prose in the docs uses this shape; it is not the grammar |
| ASEP-05 | `REQ-d00001:A` | G-STD | all | `REQ-d00001` (A) | none | `0 -> MALFORMED / {E_WRONG_ASSERTION_SEPARATOR}` — competes with TRAIL-02; minimal set should prefer the separator reading since it accounts for `A` too |
| ASEP-06 | `DEV-00010.1` | G-FDA | all | `DEV-00010` (1) | none | `0 -> MALFORMED / {E_WRONG_ASSERTION_SEPARATOR}` |
| ASEP-07 | `REQ-dTokenStore.2` | G-NAMED | all | `REQ-dTokenStore` (2) | none | `0 -> MALFORMED / {E_WRONG_ASSERTION_SEPARATOR}` |
| ASEP-08 | `REQ-d00001 - A` | G-STD | all | `REQ-d00001` (A) | none | `0 -> MALFORMED / {E_NOT_AN_IDENTIFIER}` — whitespace is tested before any relaxation, and this is why the order matters |

ASEP-08 pins the cascade order. If it reports a separator relaxation, the
whitespace test has been moved below the relaxation pass.

---

## 6. `E_WRONG_MULTI_SEPARATOR`

Between two labels. `+` in `G-STD`/`G-E2E`/`G-FDA`/`G-JIRA`, `&` in `G-NAMED`.

| ID | Input | Grammar | Surface | Estate | Bindings | Verdict |
|---|---|---|---|---|---|---|
| MSEP-01 | `REQ-d00001-A&B` | G-STD | all | `REQ-d00001` (A, B) | none | `0 -> MALFORMED / {E_WRONG_MULTI_SEPARATOR}` |
| MSEP-02 | `REQ-dTokenStore-1+2` | G-NAMED | all | `REQ-dTokenStore` (1, 2) | none | `0 -> MALFORMED / {E_WRONG_MULTI_SEPARATOR}` — the mirror of MSEP-01; `+` is wrong *here* |
| MSEP-03 | `REQ-d00001-A/B` | G-STD | all | `REQ-d00001` (A, B) | none | `0 -> MALFORMED / {E_WRONG_MULTI_SEPARATOR}` |
| MSEP-04 | `REQ-d00001-A B` | G-STD | all | `REQ-d00001` (A, B) | none | `0 -> MALFORMED / {E_NOT_AN_IDENTIFIER}` — whitespace first again |
| MSEP-05 | `REQ-d00001-A+B+C` | G-STD | all | `REQ-d00001` (A, B, C) | `REQ-d00001-A`, `REQ-d00001-B`, `REQ-d00001-C` | no fault — the positive control for this section |
| MSEP-06 | `REQ-d00001-A;B` | G-STD | all | `REQ-d00001` (A, B) | none | `0 -> MALFORMED / {E_WRONG_MULTI_SEPARATOR}` |
| MSEP-07 | `REQ-d00001-A+B&C` | G-STD | all | `REQ-d00001` (A, B, C) | none | `0 -> MALFORMED / {E_WRONG_MULTI_SEPARATOR}` — one code for a mixed run, not one per offending character |

A configuration whose `multi_separator` is `,` is refused by
`config/schema.py` (REQ-d00251-M) and belongs in a config-validation test, not
here. Noted so nobody adds it to this table.

---

## 7. `E_LABEL_OUT_OF_SERIES`

The label is well-formed as a token but is not in the series this grammar
configures, or is past `max_count`.

| ID | Input | Grammar | Surface | Estate | Bindings | Verdict |
|---|---|---|---|---|---|---|
| SERIES-01 | `REQ-d00001-9` | G-STD | all | `REQ-d00001` (A..C) | none | `0 -> MALFORMED / {E_LABEL_OUT_OF_SERIES}` — numeric label, uppercase series |
| SERIES-02 | `DEV-00010-A` | G-FDA | all | `DEV-00010` (0..2) | none | `0 -> MALFORMED / {E_LABEL_OUT_OF_SERIES}` — the mirror |
| SERIES-03 | `REQ-dTokenStore-100` | G-NAMED | all | `REQ-dTokenStore` | none | `0 -> MALFORMED / {E_LABEL_OUT_OF_SERIES}` — past `max_count = 99` |
| SERIES-04 | `PROJ-7-27` | G-JIRA | all | `PROJ-7` | none | `0 -> MALFORMED / {E_LABEL_OUT_OF_SERIES}` — past `max_count = 26` |
| SERIES-05 | `REQ-d00001-AA` | G-STD | all | `REQ-d00001` | none | `0 -> MALFORMED / {E_LABEL_OUT_OF_SERIES}` — a two-letter label is not in an A..Z series |
| SERIES-06 | `REQ-d00001-Z` | G-STD | all | `REQ-d00001` (A..C only) | none | `0 -> UNKNOWN_ASSERTION` — **in** series (26th of 26), simply absent. The boundary case that separates this section from section 10. |
| SERIES-07 | `DEV-00010-0` | G-FDA | all | `DEV-00010` (0..2) | `DEV-00010-0` | no fault — a 0-based series really does start at zero |
| SERIES-08 | `REQ-dTokenStore-0` | G-NAMED | all | `REQ-dTokenStore` (1..3) | none | OPEN: `max_count = 99` with `label_style = "numeric"`; whether `0` is in series and merely absent (`UNKNOWN_ASSERTION`) or out of series depends on whether the fixture is 0-based. Q4. |
| SERIES-09 | `REQ-d00001-` (trailing separator, no label) | G-STD | all | `REQ-d00001` | none | `0 -> MALFORMED / {E_IDENTIFIER_WITH_TRAILING_TEXT}` or `{E_LABEL_OUT_OF_SERIES}` — OPEN, Q3 |

SERIES-06 versus SERIES-05 is the pair to assert together. One is a grammar
fault, the other an index fault, and they must not share a bucket.

---

## 8. `UNKNOWN_NAMESPACE` (bucket, no dedicated code)

No whitespace, and the leading component matches no namespace any member
declares.

| ID | Input | Grammar | Surface | Estate | Bindings | Verdict |
|---|---|---|---|---|---|---|
| NS-01 | `WIDGET-42` | G-STD | all | - | none | `0 -> UNKNOWN_NAMESPACE / {E_SYNTAX_ERROR}` alone |
| NS-02 | `foo` | G-STD | all | - | none | `0 -> UNKNOWN_NAMESPACE` — the stated consequence: a single prose token is described as an identifier. Assert it; it is a decision, not a bug. |
| NS-03 | `TODO` | G-STD | code | - | none | `0 -> UNKNOWN_NAMESPACE` — the commonest wild instance of NS-02 |
| NS-04 | `REQ-BET-p00001` | G-STD (alone, no federation) | all | - | none | `0 -> UNKNOWN_NAMESPACE` — a real identifier of a repository this build does not include |
| NS-05 | `REQ-BET-p00001` | G-FED | all | beta `REQ-BET-p00001` | `REQ-BET-p00001` | binds — same text, different membership. The pair NS-04/NS-05 is the membership test. |
| NS-06 | `REQ-ALP-p00001` | G-FED | all | alpha, exists | `REQ-ALP-p00001` | binds under **alpha's** grammar |
| NS-07 | `REQ-ALP-p99999` | G-FED | all | alpha, absent | none | `0 -> UNKNOWN_REQUIREMENT`, attributed to alpha. Must NOT read as core's `REQ` namespace with component `ALP-p99999`. |
| NS-08 | `REQ-ALP-p00001-0` | G-FED | all | alpha uses uppercase labels | none | `0 -> MALFORMED / {E_LABEL_OUT_OF_SERIES}` — judged under alpha's series, not beta's, though beta is a member and 0 is legal there |
| NS-09 | `REQ-BET-p00001-A` | G-FED | all | beta uses numeric labels | none | `0 -> MALFORMED / {E_LABEL_OUT_OF_SERIES}` — the mirror of NS-08. Together they prove configs are not merged (REQ-d00251-L). |
| NS-10 | `REQ-ALPHA-p00001` | G-FED | all | - | none | `0 -> UNKNOWN_NAMESPACE` — `REQ-ALP` prefixes it, and prefixing is not claiming |
| NS-11 | `REQ-AL-p00001` | G-FED | all | - | none | `0 -> UNKNOWN_NAMESPACE` — the other side of the prefix hazard |
| NS-12 | `REQ-ALPp00001` | G-FED | all | - | none | `0 -> UNKNOWN_NAMESPACE` or `MALFORMED` — the component boundary is configurable and must not be hardcoded as `-` |

NS-07 and NS-10..12 are the regression battery for the documented
`startswith(f"{namespace}-")` mis-attribution. Run all four.

---

## 9. `UNKNOWN_REQUIREMENT` (bucket, no dedicated code)

Grammar accepts the item whole; the index has no such requirement.

| ID | Input | Grammar | Surface | Estate | Bindings | Verdict |
|---|---|---|---|---|---|---|
| UREQ-01 | `REQ-d99999` | G-STD | all | absent by construction | none | `0 -> UNKNOWN_REQUIREMENT` |
| UREQ-02 | `DEV-99999` | G-FDA | all | absent | none | `0 -> UNKNOWN_REQUIREMENT` |
| UREQ-03 | `REQ-dNoSuchThing` | G-NAMED | all | absent | none | `0 -> UNKNOWN_REQUIREMENT` |
| UREQ-04 | `PROJ-99999` | G-JIRA | all | absent | none | `0 -> UNKNOWN_REQUIREMENT` |
| UREQ-05 | `REQ-d99999-A` | G-STD | all | requirement absent | none | `0 -> UNKNOWN_REQUIREMENT`, **not** `UNKNOWN_ASSERTION` — the cascade tests the requirement first, and a class is never later than reading reached |
| UREQ-06 | `d99999` | G-STD | all | absent | none | `0 -> UNKNOWN_REQUIREMENT` — an alias resolves before the index is consulted |
| UREQ-07 | `REQ-p99999` | G-FED | all | absent in core | none | `0 -> UNKNOWN_REQUIREMENT` attributed to core |

---

## 10. `UNKNOWN_ASSERTION` (bucket, no dedicated code)

| ID | Input | Grammar | Surface | Estate | Bindings | Verdict |
|---|---|---|---|---|---|---|
| UASRT-01 | `REQ-d00001-Q` | G-STD | all | `REQ-d00001` (A, B, C) | none | `0 -> UNKNOWN_ASSERTION` |
| UASRT-02 | `DEV-00010-5` | G-FDA | all | `DEV-00010` (0, 1, 2) | none | `0 -> UNKNOWN_ASSERTION` |
| UASRT-03 | `PROJ-7-09` | G-JIRA | all | `PROJ-7` (01, 02) | none | `0 -> UNKNOWN_ASSERTION` |
| UASRT-04 | `REQ-d00001-A+Q` | G-STD | all | A exists, Q does not | `REQ-d00001-A` | expansion salvages: A binds, Q reports `UNKNOWN_ASSERTION`. Item index is shared; the *expansion* position must also be reported. |
| UASRT-05 | `REQ-d00001-Q+R` | G-STD | all | neither exists | none | two faults, both `UNKNOWN_ASSERTION`, one per expansion member — not one fault for the item |
| UASRT-06 | `REQ-dTokenStore-99` | G-NAMED | all | labels 1..3 | none | `0 -> UNKNOWN_ASSERTION` — in series (`max_count = 99`), absent from the requirement |

UASRT-04 is the design's own salvage-inside-expansion example with the letters
changed to match this catalog's estate. It is the case most likely to be
implemented as all-or-nothing.

---

## 11. `FORBIDDEN` (bucket, no dedicated code)

The target exists and reads; the relationship is not permitted for this keyword,
this surface, or this pair of levels. Inputs here are whole lines, since the
keyword is half the case. The full matrix is in `05-surfaces-and-roundtrip.md`;
these are the item-level verdicts.

| ID | Input | Grammar | Surface | Estate | Bindings | Verdict |
|---|---|---|---|---|---|---|
| FORB-01 | `# Refines: REQ-d00001` | G-STD | code | exists | none | `0 -> FORBIDDEN` — REFINES is req->req only, never from code |
| FORB-02 | `# Implements: REQ-d00001` | G-STD | test | exists | none | `0 -> FORBIDDEN` — a test file accepts only `Verifies` |
| FORB-03 | `**Verifies**: REQ-d00001` | G-STD | spec | exists | none | `0 -> FORBIDDEN` |
| FORB-04 | `**Validates**: REQ-d00001` | G-STD | spec | exists | none | `0 -> FORBIDDEN` — journey-only keyword |
| FORB-05 | `**Implements**: REQ-d00002` from a `prd`-level requirement | G-STD | spec | `REQ-d00002` exists | none | `0 -> FORBIDDEN` — the level hierarchy forbids it; same bucket, different reason, and the diagnostic must say which |
| FORB-06 | `**Integrates**: REQ-d00001` where the target is same-repo | G-STD | spec | exists locally | none | `0 -> FORBIDDEN` — `Integrates` is external-only |
| FORB-07 | `# Verifies: REQ-d00001` | G-STD | code | exists | `REQ-d00001` | binds — the positive control; code accepts `Implements` and `Verifies` |

FORB-05 is the one that shows `forbidden` is not a syntax bucket. Its message
must be true of it as well as of FORB-01.
