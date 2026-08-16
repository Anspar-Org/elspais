# Open questions and disputes

Cases whose expected verdict the design does not settle. Each is cited from the
case tables. **Answer before converting the citing case into an assertion** — a
test written against a guess pins the guess.

---

## Q1 (DISPUTED) — is a mis-cased assertion label repaired?

**Cited by**: CASE-09, USCORE-04, DUP-02.

`_classify()` in `utilities/patterns.py` documents deliberate asymmetry: "case
is repaired for a label, never for a component, since a component's case is its
identity." So `REQ-d00001-a` binds `REQ-d00001-A` today.

Against that: `CLAUDE.md` says "Case is never repaired: an identifier resolves in
the one spelling its repository's configuration admits"; REQ-d00212-R obliges
recovery never to repair; and this design says relaxation diagnoses and never
binds, giving `req-d00001` (component case) as the worked example — it does not
address label case.

The two readings give opposite answers for the same input, and the divergence is
invisible unless someone writes the case down. Both readings are recorded in
CASE-09. If label-case repair is intended, it is an exception that should be
stated in the design rather than living only in a docstring.

---

## Q2 — does a variable-length numeric component admit leading zeros?

**Cited by**: PAD-05.

`G-JIRA` sets `digits = 0, leading_zeros = false`. If the component pattern is
`\d+`, `PROJ-007` reads whole as a distinct requirement and lands in
`unknown_requirement`. If leading zeros are excluded from the pattern, it is
`E_WRONG_PADDING`. The first is defensible (`PROJ-007` and `PROJ-7` may genuinely
be different Jira keys); the second is friendlier. Pick one and say so — the
answer also decides whether `PROJ-0` is a valid identifier.

---

## Q3 — which relaxation wins when two account for the same residue?

**Cited by**: TRAIL-05, PAD-08, SERIES-09, ASEP-05.

Minimal-set selection is defined by *size*, but several of these have competing
sets of size one:

- `REQ-d00001-A-B`: wrong multi-separator, or trailing text `-B`?
- `REQ-d00001-0A`: label out of series, or wrong padding on an unpadded series?
- `REQ-d00001-`: trailing text, or an out-of-series empty label?
- `REQ-d00001:A`: wrong assertion separator, or trailing text `:A`?

If `E_IDENTIFIER_WITH_TRAILING_TEXT` is always available as a size-one reading,
it competes with every other relaxation and either wins everything or must be
ranked last. Ranking it last is the reading these cases assume; that ranking is
not in the design and should be.

Note the interaction with `E_AMBIGUOUS`: if these are genuinely tied, they are
ambiguous by the design's own rule, and the codes above would never be issued at
all.

---

## Q4 — is a `numeric` label series 0-based everywhere?

**Cited by**: SERIES-08.

`label_style = "numeric"` is documented as `(0,1,2)` and `numeric_1based` as
`(1,2,3)`. `G-NAMED` configures `numeric` with `max_count = 99`, and this
catalog's companion estate gives it labels 1..3. So `REQ-dTokenStore-0` is in
series and absent (`unknown_assertion`), not out of series. Confirm the fixture
estate rather than the config here — the catalog may simply have authored the
estate wrongly, in which case fix the estate, not the case.

---

## Q5 — emphasis in a non-markdown comment

**Cited by**: KWE-08.

`references.keyword_emphasis` is defined for markdown. A code comment reading
`# **Implements**: REQ-d00001` is not markdown. Three options: recognise and
report emphasis (uniformity), recognise and stay silent (the rule does not apply
off markdown), or do not recognise the keyword at all (emphasis is not the first
content). The third costs an edge and contradicts "a style finding never costs
an edge", so it should be rejected explicitly rather than by omission.

---

## Q6 — is a keyword with no space after the comment marker the first content?

**Cited by**: PROSE-05.

`#Implements: REQ-d00001`. "First content of the comment" is satisfied; nothing
in the design mentions the space. Whatever the answer, it must be identical for
`#`, `//` and `--`, and it should be stated because it is the difference between
a recognised annotation and a remainder.

---

## Q7 — is the whitespace test Unicode-aware?

**Cited by**: NOTID-08, PATH-29, PATH-30.

`str.split()` and `\s` differ on non-breaking space, and the whitespace test is
the load-bearing decision of the whole cascade. A non-breaking space that is not
whitespace turns `REQ -d00001` from an honest "not an identifier" into an
`unknown_namespace` claim about an identifier-shaped thing. Cheap to decide,
expensive to discover.

---

## Q8 — continuation across an empty comment line

**Cited by**: CONT-05.

`# Implements: REQ-d00001,` / `#` / `#    REQ-d00002`. One line of lookahead sees
a comment line of the same block that is empty. Is that the continuation (and
therefore an empty item), the end of the list (`E_TRAILING_SEPARATOR`, and
`REQ-d00002` an orphan), or does lookahead skip blank comment lines? Skipping
would make lookahead more than one line, which the design rules out.

---

## Q9 — a keyword on a continuation line

**Cited by**: CONT-07, PATH-06.

`# Implements: REQ-d00001,` / `#    Implements: REQ-d00002`. The second line is
positioned as a continuation and is *also* shaped as a declaration. If
continuation wins, `Implements: REQ-d00002` is one whitespace-bearing item and
reports `E_NOT_AN_IDENTIFIER`, losing an edge the author plainly intended. If
declaration wins, the trailing separator on line 1 has nothing to continue onto.
Both are defensible; only one can be implemented.

---

## Q10 — `,` alone

**Cited by**: EMPTY-07, PATH-10.

Splitting `,` yields two empty items. Is that two `E_EMPTY_ITEM` faults, one
`E_EMPTY_ITEM` plus one `E_TRAILING_SEPARATOR`, or one fault total? The counts
appear in a summary that must be "actionable at a glance", so the answer is
visible to users.

---

## Q11 — a duplicate item is currently silent

**Cited by**: DUP-01..05.

`parse_ref_list()` holds a `seen` set and `continue`s on a repeat: no `RefItem`,
no binding, no diagnostic. Trait "silence is a bug" says every recognised
construct produces a binding or a diagnostic. A duplicate is a recognised
construct.

Three readings: report `E_DUPLICATE_ITEM` (new code, open vocabulary permits it);
emit a `RefItem` that resolves to the same target so the edge is idempotent and
the item is accounted for; or state duplication as a deliberate silent
deduplication and exempt it. The third is a policy and should be written down if
chosen.

Note DUP-02: `REQ-d00001, req-d00001` is **not** deduplicated (the second does
not normalize to the same string under Q1's component rule), so it reports —
while the exact duplicate says nothing. That asymmetry is the strongest argument
that the silence is unintentional.

---

## Q12 — do aliases cross federation members?

**Cited by**: ALIAS-09.

`FederatedIdReader` alternates each member's own grammar fragments and never
merges configs (REQ-d00251-L). An alias is part of a member's grammar, so
`p00001` should read only under a member that configures that alias. Confirm
that the invoking repository's alias is not applied to another member's
identifiers — that would be a config merge by the back door.

---

## Q13 — how many labels does underscore notation read?

**Cited by**: USCORE-05.

`test_REQ_p00001_A_B`. The docstring says the notation has spent its
distinguishing punctuation and `test_REQ_p00001_A_and_so_on` names one label.
`_B` is uppercase, so the tail pattern (`assertion_label_exact`) may read it as a
second label, giving `REQ-p00001-A+B`. Determine which, since a test function
naming two assertions is a real authoring pattern.

---

## Q14 — does a keyword-shaped item deserve its own code?

**Cited by**: PATH-01, PATH-03.

`Implements: Implements:` yields the item `Implements:`, which reports
`unknown_namespace` and is described as an identifier. Truthful under the stated
rule, unhelpful to the author. An `E_KEYWORD_AS_REFERENT` code would be a
decidable, non-disjoint addition — exactly what the open vocabulary is for. The
question is whether it is worth a code or whether the generic report suffices.

---

## Q15 — a namespace with an empty component

**Cited by**: PATH-15 (`REQ-`).

The leading component `REQ` matches a declared namespace, so the cascade's
namespace test says "malformed with relaxation codes" rather than
`unknown_namespace`. But no relaxation from the closed set makes `REQ-` match.
An item that reaches the relaxation branch and produces an empty relaxation set
needs a defined outcome: the generic code alone, most likely.

---

## Q16 — `::` from author text

**Cited by**: PATH-17, PATH-18.

`INSTANCE_SEPARATOR` is `::`, and composite IDs (`declaring_id::original_id`) are
built by the graph for INSTANCE nodes. An author reference containing `::` must
not resolve to one — the author cannot see those nodes, and an edge to one would
be an invented relationship. Confirm the cascade refuses it rather than relying
on the component grammar happening not to admit `:`.

---

## Q17 — `Implements::`

**Cited by**: PATH-23.

Is the keyword `Implements` with content `:`, or is the recogniser looking at
`Implements:` as a keyword token and failing? Both produce a finding, but
different ones, and the answer generalises to any keyword followed by repeated
punctuation.

---

## Q18 — self-reference and cycles

**Cited by**: PATH-50..52.

A requirement implementing itself reads whole and reaches the matrix. Whether
that is `forbidden`, a separate hierarchy check, or permitted is outside this
ticket's cascade — but the cascade must have *an* answer and must not crash. If
it is an existing check, cite it and drop the cases from this catalog.

---

## Q19 — does `fix` repair a trailing separator in spec metadata?

**Cited by**: RT-08.

Repair is asymmetric because rendering is. `fix` renders spec metadata, and the
renderer emits the separator itself when it explodes a list — so a
trailing-separator fault in spec metadata is repaired by rendering whether or not
anyone decided to repair it. On code, it is report-only. That asymmetry is
consistent with the design's stated principle, but it means the *same* fault
class behaves differently on two surfaces, which brushes against uniform
tolerance. Worth stating as policy rather than discovering as fallout — the trait
itself says divergence must be stated policy, never fallout.

---

## Q20 — is a surface-invalid keyword recognised then refused, or not recognised?

**Cited by**: FORB-01..04, the whole keyword x surface matrix, MTX-01..03.

`# Implements: REQ-d00001` in a **test** file. Two readings:

- **Recognised, then refused.** The line enters the reference machinery, the item
  reads whole, and the matrix rejects the relationship: bucket `forbidden`,
  message "exists, but not for this keyword". The author gets told why their
  annotation did nothing.
- **Not recognised.** Layer 1 admits only the keywords valid for the surface, so
  the line is prose and produces no finding — the same silence PROSE-01 asserts
  is correct for a space before the colon.

The design says layer 1 is "unchanged" and does not address it. The first
reading is what this catalog assumes, on the strength of trait 4 (silence is a
bug) and the REQ-p00014-V precedent, where a `Validates:` in a journey section is
explicitly *reported* rather than ignored. But it is an assumption, and it
decides every cell of the matrix in file 05 as well as the size of the
`forbidden` bucket in the summary.

---

## Q21 — the leading-identifier rule: an item may bind and be faulty at once

**Cited by**: NOTID-02, NOTID-04, NOTID-05, NOTID-07, NOTID-09..13, SALV-01b.

**Decided by the user, 2026-08-15, amending the design.** An item that begins
with a whole identifier binds it; the residue after it is reported. Matching is
anchored at position 0 and maximal, and exactly one identifier binds per item.

The design says "salvage never searches inside an item ... an item either
whole-matches a member's grammar or it is an error item", justified by
`XREQ-d00001` binding `REQ-d00001`. That justification survives: an *anchored*
match cannot produce it, because the invented-edge hazard is unanchored search,
not reading past a valid prefix. What the design forbids and this rule keeps
forbidding is binding an identifier the author's text does not begin with.

Three things this decides that the sentence does not:

1. **`RefItem`'s invariant breaks.** Its docstring says "Exactly one of
   `resolved` and `fault_class` is set", and `parse_ref_list()` builds items in
   two exclusive branches. Either the dataclass admits a resolved-and-faulty
   item, or one item yields a binding plus a separate `ReferenceFault`. The
   second keeps the invariant but breaks the one-item-one-verdict shape the
   test tables are written against.
2. **Which bucket the item lands in.** NOTID-05 (`REQ-p00047 (A`, requirement
   absent) reaches the index, so it is `unknown_requirement` — a later class
   than `malformed`, on an item that is plainly malformed. The class is
   "how far reading got", and reading now gets further. Confirm that is
   intended; the alternative is that the *fault* stays `malformed` while the
   *binding* proceeds independently.
3. **Coverage.** NOTID-10 makes callisto's `REQ-p00047 (A, C, F)` produce a
   blanket edge to the requirement. Blanket and assertion-targeted evidence
   enter the strict and generous footings differently (REQ-d00069-J/L), so
   this changes reported coverage, not only reported faults.

## Q22 — does the anchor rule apply to an abutting residue?

**Cited by**: NOTID-11, the whole `E_IDENTIFIER_WITH_TRAILING_TEXT` table.

Q21's rule was stated for `ROG-system-01/A and ROG-system-01/B` — residue
separated by whitespace. `REQ-d00001.`, `REQ-d00001(see note)`, `REQ-p00001(A`
have a residue that abuts. Symmetry says they bind too, which is friendly to
sentence punctuation. Against it: `REQ-d00001;REQ-d00002` would bind the first
and lose the second, and an abutting residue is weaker evidence that the author
finished writing an identifier — `REQ-d000010` (TRAIL-23) is the same shape and
must not bind.

A middle reading: the anchor rule requires the residue to begin with whitespace
or an established punctuation boundary, so `.` and `)` bind but a character the
component grammar could have contained does not. That is a shape heuristic of
the kind the design deliberately removed, which is an argument against it.

## Q23 — is a missing list separator its own code?

**Cited by**: NOTID-12, NOTID-02, NOTID-09.

`ROG-system-01/A and ROG-system-01/B` is not merely "not an identifier" — it is
a *list* whose separator is missing, and the user's framing names it that way.
The residue is diagnosable more precisely than `E_NOT_AN_IDENTIFIER`: it
contains a further identifier of a member's grammar, so the tool can say "a
comma is missing here" and point at the position.

That is decidable, which is the bar a code must clear, and the vocabulary is
open, so `E_MISSING_SEPARATOR` costs no bucket and no configuration. The
question is whether it fires only when the residue holds an identifier (narrow,
always true when issued) or whenever a residue follows an anchored identifier
(broad, but then it duplicates `E_IDENTIFIER_WITH_TRAILING_TEXT`).

Note the interaction with Q21's rule that exactly one identifier binds per item:
`E_MISSING_SEPARATOR` is the diagnostic that tells the author why the second one
did not. Without it, NOTID-12 reports a fault whose message does not explain the
missing edge, and the author's most likely next move is to assume the tool
cannot read their file.
