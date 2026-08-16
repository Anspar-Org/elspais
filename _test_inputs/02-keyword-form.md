# Layer 1 — Recognition, keyword form, continuation

Inputs here are whole lines, and several are multi-line, because recognition is
about position rather than about item text.

The rule under test: a keyword is recognised in **any case**; everything else is
strict — the keyword is the first content of the comment or metadata line, and
the colon abuts it with no intervening space.

---

## 1. `references.keyword_case`

Canonical: initial capital, remainder lowercase, colon abutting.

**The negative is the assertion that matters: a wrong-case keyword must never
cost an edge.** Every case in this table binds `REQ-d00001` identically. They
differ only in the style finding.

| ID | Input | Grammar | Surface | Estate | Bindings | Finding |
|---|---|---|---|---|---|---|
| KWC-01 | `# Implements: REQ-d00001` | G-STD | code | exists | `REQ-d00001` | none — canonical |
| KWC-02 | `# IMPLEMENTS: REQ-d00001` | G-STD | code | exists | `REQ-d00001` | `references.keyword_case`, warning by default. The measured wild form — three lines across this repo and callisto. |
| KWC-03 | `# implements: REQ-d00001` | G-STD | code | exists | `REQ-d00001` | `references.keyword_case` |
| KWC-04 | `# ImPlEmEnTs: REQ-d00001` | G-STD | code | exists | `REQ-d00001` | `references.keyword_case` |
| KWC-05 | `# iMPLEMENTS: REQ-d00001` | G-STD | code | exists | `REQ-d00001` | `references.keyword_case` |
| KWC-06 | `**implements**: REQ-d00001` | G-STD | spec | exists | `REQ-d00001` | `references.keyword_case` only — the emphasis is canonical |
| KWC-07 | `# VERIFIES: REQ-d00001` | G-STD | test | exists | `REQ-d00001` | `references.keyword_case` — the rule is per keyword, not per `Implements` |
| KWC-08 | `# refines: REQ-d00001` | G-STD | spec | exists | `REQ-d00001` | `references.keyword_case` |
| KWC-09 | `**VALIDATES**: REQ-d00001` | G-STD | journey (metadata) | exists | `REQ-d00001` | `references.keyword_case` |
| KWC-10 | `# Satisfies: REQ-p00001` | G-STD | spec | exists | `REQ-p00001` | none |

Severity sweep, one input (KWC-02) across the four settings: `failing`,
`warning` (default), `informational`, `off`. In all four the edge exists. Only
the report changes. Under `off` there is no finding at all.

---

## 2. `references.keyword_emphasis`

Canonical in markdown: `**Implements**:` with the colon **outside** the wrapper.

| ID | Input | Grammar | Surface | Estate | Bindings | Finding |
|---|---|---|---|---|---|---|
| KWE-01 | `**Implements**: REQ-d00001` | G-STD | spec | exists | `REQ-d00001` | none — canonical |
| KWE-02 | `**Implements:** REQ-d00001` | G-STD | spec | exists | `REQ-d00001` | `references.keyword_emphasis` — colon inside the wrapper |
| KWE-03 | `*Implements*: REQ-d00001` | G-STD | spec | exists | `REQ-d00001` | `references.keyword_emphasis` — single-star |
| KWE-04 | `_Implements_: REQ-d00001` | G-STD | spec | exists | `REQ-d00001` | `references.keyword_emphasis` |
| KWE-05 | `Implements: REQ-d00001` | G-STD | spec | exists | `REQ-d00001` | `references.keyword_emphasis` — no emphasis at all, in a surface whose canonical form has it |
| KWE-06 | `***Implements***: REQ-d00001` | G-STD | spec | exists | `REQ-d00001` | `references.keyword_emphasis` |
| KWE-07 | `**implements:** REQ-d00001` | G-STD | spec | exists | `REQ-d00001` | **both** rules fire — they are independently configurable, so both must be reported and both must be separately suppressible |
| KWE-08 | `# **Implements**: REQ-d00001` | G-STD | code | exists | `REQ-d00001` | OPEN: emphasis in a code comment is not markdown. Q5. |

KWE-07 is the case that proves the two rules are separate policy units rather
than one rule with two spellings. Assert that setting `keyword_case = "off"`
leaves KWE-07 reporting emphasis only.

---

## 3. Keyword syntax is strict — these are prose, and prose is not a finding

Nothing here binds, and nothing here reports. A line that is not recognised is a
remainder, and a remainder is not a defect. Asserting *silence* here is as
important as asserting noise elsewhere.

| ID | Input | Grammar | Surface | Expected |
|---|---|---|---|---|
| PROSE-01 | `# Implements : REQ-d00001` | G-STD | code | prose. No binding, **no finding** — a space before the colon is the design's stated negative |
| PROSE-02 | `# This Implements: REQ-d00001` | G-STD | code | prose — the keyword is not the first content |
| PROSE-03 | `# See how it Implements: REQ-d00001` | G-STD | code | prose |
| PROSE-04 | `# Implements REQ-d00001` | G-STD | code | prose — no colon |
| PROSE-05 | `#Implements: REQ-d00001` | G-STD | code | OPEN: is the keyword the first *content* of the comment when there is no space after the marker? Q6. Whatever the answer, it must be the same on `//` and `--`. |
| PROSE-06 | `This paragraph implements: nothing in particular.` | G-STD | spec body (outside the metadata block) | prose |
| PROSE-07 | `# Implements:REQ-d00001` (no space after the colon) | G-STD | code | binds `REQ-d00001` — the colon abuts the *keyword*; nothing is said about after it. Assert the binding, not prose. |
| PROSE-08 | `# implements-a-thing: REQ-d00001` | G-STD | code | prose — the colon does not abut the keyword |

PROSE-01 and PROSE-02 are the two the design names explicitly. PROSE-07 is their
complement and stops the rule being over-applied.

---

## 4. The legacy block-header form

Retained so existing files keep parsing, governed by the same rules: case-lax,
plural `REQUIREMENTS`, colon mandatory. The renderer never emits it.

| ID | Input | Grammar | Surface | Expected |
|---|---|---|---|---|
| BLOCK-01 | see below, canonical | G-STD | spec | header recognised; indented identifiers bind |
| BLOCK-02 | lowercase header | G-STD | spec | header recognised; `references.keyword_case` finding; identifiers bind |
| BLOCK-03 | singular `REQUIREMENT` | G-STD | spec | header **not** recognised -> prose; indented identifiers become `E_ORPHAN_REFERENCE` |
| BLOCK-04 | no colon | G-STD | spec | header not recognised -> prose; identifiers become `E_ORPHAN_REFERENCE` |
| BLOCK-05 | `IMPLEMENTS requirement` | G-STD | spec | not recognised — today this opens a block, and that is the breaking change the design accepts |

BLOCK-01:

```text
IMPLEMENTS REQUIREMENTS:
    REQ-d00001
    REQ-d00002
```

BLOCK-03:

```text
IMPLEMENTS REQUIREMENT:
    REQ-d00001
    REQ-d00002
```

BLOCK-04:

```text
IMPLEMENTS REQUIREMENTS
    REQ-d00001
    REQ-d00002
```

BLOCK-05:

```text
IMPLEMENTS requirement
    REQ-d00001
```

---

## 5. `E_ORPHAN_REFERENCE`

An identifier standing under no keyword. Today problem-statement B: silently
dropped, no node, no remainder, no diagnostic. **Silence is the bug.**

| ID | Input | Grammar | Surface | Expected |
|---|---|---|---|---|
| ORPH-01 | below | G-STD | spec | both indented identifiers -> `MALFORMED / {E_ORPHAN_REFERENCE}`; no bindings; the lines still render verbatim through `fix` |
| ORPH-02 | below | G-STD | code | continuation-line identifier under a header-less comment block -> `E_ORPHAN_REFERENCE` |
| ORPH-03 | below | G-STD | code | the exact reproduction of measured failure B: a well-formed multi-line list whose first line has **no** trailing separator |

ORPH-01:

```text
Some prose that is not a keyword line.
    REQ-d00001
    REQ-d00002
```

ORPH-02:

```text
# some ordinary comment
# REQ-d00001
def thing(): ...
```

ORPH-03:

```text
# Implements: REQ-d00001
#             REQ-d00002
#             REQ-d00003
def thing(): ...
```

ORPH-03 is the sharpest case in this file. Line 1 binds `REQ-d00001`. Lines 2
and 3 carry no keyword and the line above them does **not** end in the
separator, so continuation does not apply — they must each report
`E_ORPHAN_REFERENCE` and must not bind. Today they vanish. Whatever the outcome,
it must not be nothing.

---

## 6. Continuation

A recognised reference line whose content ends in `,` continues onto the next
comment line of the same block (code/test) or the next line of the metadata
block (spec). One line of lookahead.

| ID | Input | Grammar | Surface | Bindings | Verdict |
|---|---|---|---|---|---|
| CONT-01 | below | G-STD | code | `REQ-d00001`, `REQ-d00002` | no fault |
| CONT-02 | below | G-STD | code | `REQ-d00001`, `REQ-d00002`, `REQ-d00003` | no fault — two continuations, so lookahead is applied repeatedly and not once |
| CONT-03 | below | G-STD | code | `REQ-d00001` | trailing separator with nothing to continue onto -> `E_TRAILING_SEPARATOR`; the well-formed item still binds |
| CONT-04 | below | G-STD | code | `REQ-d00001` | continuation onto a **non-comment** line: the code line is not part of the comment block, so `E_TRAILING_SEPARATOR` |
| CONT-05 | below | G-STD | code | `REQ-d00001` | continuation onto a blank comment line -> `E_TRAILING_SEPARATOR` plus an empty item, or `E_EMPTY_ITEM`. OPEN, Q8. |
| CONT-06 | below | G-STD | code | `REQ-d00001`, `REQ-d00002` | the continuation line carries a *faulty* item alongside a good one — salvage applies across the line boundary exactly as within a line |
| CONT-07 | below | G-STD | code | `REQ-d00001` | continuation line opens with a keyword of its own — OPEN, Q9: is `Implements:` on the continuation an item, or a new declaration? |
| CONT-08 | below | G-STD | spec | `REQ-d00001`, `REQ-d00002` | **Phase B**. Inert until the metadata block exists. Mark `xfail` in phase A rather than omitting — the design says the rule is uniform only once B lands. |
| CONT-09 | below | G-STD | code | `REQ-d00001`, `REQ-d00002` | continuation across a `//` block; the rule is per comment block, not per language |

CONT-01:

```text
# Implements: REQ-d00001,
#             REQ-d00002
def thing(): ...
```

CONT-02:

```text
# Implements: REQ-d00001,
#             REQ-d00002,
#             REQ-d00003
def thing(): ...
```

CONT-03:

```text
# Implements: REQ-d00001,
def thing(): ...
```

CONT-04:

```text
# Implements: REQ-d00001,
x = 1
# REQ-d00002
```

CONT-05:

```text
# Implements: REQ-d00001,
#
#             REQ-d00002
def thing(): ...
```

CONT-06:

```text
# Implements: REQ-d00001,
#             not a reference, REQ-d00002
def thing(): ...
```

CONT-07:

```text
# Implements: REQ-d00001,
#             Implements: REQ-d00002
def thing(): ...
```

CONT-08:

```text
# REQ-d00060: A Requirement

**Level**: dev | **Status**: Active
**Implements**: REQ-d00001,
                REQ-d00002
```

CONT-09:

```text
// Implements: REQ-d00001,
//             REQ-d00002
function thing() {}
```

CONT-04 is worth two assertions: the trailing-separator fault on line 1, and
that `REQ-d00002` on line 3 reports `E_ORPHAN_REFERENCE` rather than being
swept into the list it does not belong to.
