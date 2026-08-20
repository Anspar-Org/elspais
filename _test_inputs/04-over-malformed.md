# Beyond the anticipated — pathological inputs

Inputs more malformed than the design contemplates. The bar for every case here
is the same and it is low: **a binding or a diagnostic, never nothing**, and
never an exception. Where the design does not determine which diagnostic, the
case says so rather than inventing one.

A converter should treat this file as two suites: an *assertion* suite for the
cases with a determined verdict, and a *survival* suite for the rest — parse it,
assert no exception, assert at least one finding, assert `fix` round-trips the
line unchanged.

---

## 1. Keyword where a referent should be

The user's named case. A keyword is not an identifier, and the recogniser must
not treat the second one as content it can read.

| ID | Input | Grammar | Surface | Expected |
|---|---|---|---|---|
| PATH-01 | `# Implements: Implements:` | G-STD | code | one item, `Implements:`, no whitespace, matches no namespace -> `UNKNOWN_NAMESPACE`. OPEN whether a keyword-shaped item deserves its own code. Q14. |
| PATH-02 | `# Implements: Implements: REQ-d00001` | G-STD | code | item text contains whitespace -> `MALFORMED / {E_NOT_AN_IDENTIFIER}`. Must **not** bind `REQ-d00001`: position 0 holds `Implements:`, so the anchor fails and the identifier is inside the residue. This is NOTID-06's rule with a keyword as the leading noise, and it survives the leading-identifier rule unchanged. |
| PATH-03 | `# Implements: Verifies: REQ-d00001` | G-STD | code | as PATH-02. The second keyword is not a keyword; only the first content of the line is. |
| PATH-04 | `# Implements: Implements:,` | G-STD | code | item fault **and** `E_TRAILING_SEPARATOR` |
| PATH-05 | `# Implements: Implements: Implements:` | G-STD | code | one item, whitespace-bearing -> `E_NOT_AN_IDENTIFIER`. One fault, not three. |
| PATH-06 | `# Implements: REQ-d00001, Implements: REQ-d00002` | G-STD | code | item 0 binds; item 1 is whitespace-bearing -> `E_NOT_AN_IDENTIFIER`. Salvage under a keyword-shaped item. |
| PATH-07 | `# Implements Implements: REQ-d00001` | G-STD | code | prose — the keyword is not the first content, and the colon abuts the *second* word |

PATH-02 is the sharpest of these. A tolerant implementation that scans the item
for anything identifier-shaped binds `REQ-d00001` and reports nothing, which is
exactly the invented edge salvage forbids.

---

## 2. Punctuation with no referent at all

| ID | Input | Grammar | Surface | Expected |
|---|---|---|---|---|
| PATH-10 | `# Implements: ,` | G-STD | code | no bindings. Empty item and/or trailing separator — Q10. Must produce at least one finding. |
| PATH-11 | `# Implements: ,,,` | G-STD | code | no bindings; three or four empty-item findings plus a trailing separator |
| PATH-12 | `# Implements: -` | G-STD | code | one item `-`; no whitespace; matches no namespace -> `UNKNOWN_NAMESPACE`. A bare separator described as an identifier is odd but is the stated consequence of dropping the shape heuristic. |
| PATH-13 | `# Implements: +` | G-STD | code | as PATH-12 |
| PATH-14 | `# Implements: -A` | G-STD | code | `UNKNOWN_NAMESPACE` — a label with no requirement. Tempting to read as "assertion of the current requirement"; the grammar has no such form and must not acquire one here. |
| PATH-15 | `# Implements: REQ-` | G-STD | code | OPEN: `UNKNOWN_NAMESPACE`, or `E_IDENTIFIER_WITH_TRAILING_TEXT` with an empty component, or `E_WRONG_PADDING`. Q15. |
| PATH-16 | `# Implements: -,-,-` | G-STD | code | three items, three `UNKNOWN_NAMESPACE` faults. Assert the count. |
| PATH-17 | `# Implements: ::` | G-STD | code | `UNKNOWN_NAMESPACE`. `::` is `INSTANCE_SEPARATOR`; a composite ID must not be readable from an author's reference list. |
| PATH-18 | `# Implements: REQ-d00001::REQ-d00002` | G-STD | code | must **not** bind either. A composite instance ID is built by the graph, never written by an author -> `E_IDENTIFIER_WITH_TRAILING_TEXT` or `UNKNOWN_NAMESPACE`. Q16. |

PATH-17 and PATH-18 are the ones with a real hazard behind them: `::` is a
structural separator elsewhere in the system, and admitting it from author text
would let a reference name a node the author cannot see.

---

## 3. Degenerate keyword lines

| ID | Input | Grammar | Surface | Expected |
|---|---|---|---|---|
| PATH-20 | `#` | G-STD | code | a bare comment marker. Prose. No finding. |
| PATH-21 | `# :` | G-STD | code | prose — no keyword |
| PATH-22 | `# :REQ-d00001` | G-STD | code | prose. Must not bind. |
| PATH-23 | `# Implements::` | G-STD | code | OPEN: keyword + colon, then content `:` -> one item `:` -> `UNKNOWN_NAMESPACE`; or the keyword is `Implements:` and unrecognised. Q17. Either way, a finding. |
| PATH-24 | `# Implements: :` | G-STD | code | item `:` -> `UNKNOWN_NAMESPACE` |
| PATH-25 | `# Implements` | G-STD | code | prose — PROSE-04 |
| PATH-26 | 512 repetitions of `REQ-d00001,` on one line | G-STD | code | binds once (deduplication), no exception, no quadratic blowup. A performance guard as much as a correctness one. |
| PATH-27 | an item of 10,000 characters with no whitespace | G-STD | code | `UNKNOWN_NAMESPACE`, and the report must not embed the whole item unbounded in a summary line |
| PATH-28 | `# Implements: REQ-d00001` where the line ends with a lone `\r` | G-STD | code | binds `REQ-d00001` — a CRLF file must not turn every last item into a trailing-text fault |
| PATH-29 | `# Implements: REQ‑d00001` (Unicode non-breaking hyphen) | G-STD | code | `UNKNOWN_NAMESPACE` or `MALFORMED`; must not bind, must not raise. Homoglyph separators are the wild form of this. |
| PATH-30 | `# Implements: РЕQ-d00001` (Cyrillic Р and Е) | G-STD | code | must not bind. Assert the negative explicitly — a case-insensitive Unicode-aware regex is where this leaks. |

PATH-28 is not exotic. A repository checked out with `core.autocrlf` produces it
on every line, and it converts the entire estate into faults if the line ending
survives into the item.

---

## 4. Nesting and structure abuse

| ID | Input | Grammar | Surface | Expected |
|---|---|---|---|---|
| PATH-40 | below | G-STD | code | a keyword inside a string literal, not a comment. Python `ast.parse()` sees no comment -> nothing. Assert nothing, including no fault. |
| PATH-41 | below | G-STD | code | a keyword inside a docstring. Same expectation as PATH-40, and the reason the pre-scan uses `ast.parse()` rather than regex. |
| PATH-42 | below | G-STD | spec | a metadata line **after** prose, inside a requirement. Phase B: reported rather than silently merged. Phase A: currently merged. Mark `xfail` in A. |
| PATH-43 | below | G-STD | journey | a `Validates:` inside a journey *section* rather than its metadata. Per REQ-p00014-V this is read by nothing and must be reported as a declared reference that produced no relationship — never silently. |
| PATH-44 | below | G-STD | code | a keyword line inside a `/* */` block in a C-style file. Documented gap: the reference is never read. Assert the gap deliberately so it is visible when it closes. |
| PATH-45 | below | G-STD | code | continuation onto a line that opens a new comment *block* (blank line between). Must not continue -> `E_TRAILING_SEPARATOR` + `E_ORPHAN_REFERENCE`. |

PATH-40:

```text
QUERY = "# Implements: REQ-d00001"
```

PATH-41:

```text
def thing():
    """# Implements: REQ-d00001"""
```

PATH-42:

```text
# REQ-d00060: A Requirement

**Level**: dev | **Status**: Active

Some prose that ends the metadata block.

**Implements**: REQ-d00001
```

PATH-43:

```text
# JNY-001: A Journey

**Status**: Active

## Step 1

**Validates**: REQ-d00001
```

PATH-44:

```text
/* Implements: REQ-d00001 */
int thing(void) { return 0; }
```

PATH-45:

```text
# Implements: REQ-d00001,

# REQ-d00002
def thing(): ...
```

---

## 5. Self-referential and cyclical targets

Not syntax faults. Included because they read whole and therefore reach the
matrix, where the `forbidden` bucket has to have an answer.

| ID | Input | Grammar | Surface | Expected |
|---|---|---|---|---|
| PATH-50 | `REQ-d00001` declared by `REQ-d00001` itself | G-STD | spec | `FORBIDDEN` — a requirement implementing itself. Must not silently create a self-edge. |
| PATH-51 | `REQ-d00001-A` declared by assertion `REQ-d00001-B` | G-STD | spec | `FORBIDDEN` |
| PATH-52 | `REQ-d00001` and `REQ-d00002` each implementing the other | G-STD | spec | both `FORBIDDEN`, or a cycle diagnostic. Q18 — outside this ticket's cascade, but the cascade must not crash on it. |

---

## 6. Empty and absent everything

| ID | Input | Grammar | Surface | Expected |
|---|---|---|---|---|
| PATH-60 | a code file that is entirely empty | G-STD | code | no findings; `code.no_traceability` may name it, and truthfully |
| PATH-61 | a code file whose only line is `# Implements:` | G-STD | code | `E_EMPTY_REFERENCE_LIST`, **and** `code.no_traceability` must not name it as carrying no markers — it carries one. See `05-surfaces-and-roundtrip.md`. |
| PATH-62 | a code file whose only line is `# Implements: not a reference` | G-STD | code | one fault; `code.no_traceability` must not name it |
| PATH-63 | a spec requirement whose metadata block is entirely absent | G-STD | spec | existing format checks fire; no reference fault |

PATH-61 and PATH-62 are the two that make `code.no_traceability` stop lying, and
they are the shape of the three callisto workflow files in the problem
statement.
