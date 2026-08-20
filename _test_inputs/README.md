# Reference Syntax Classification — Test Input Catalog

Independent test-generation step for the design at
`docs/superpowers/specs/2026-08-15-reference-syntax-classification-design.md`
(TOOL-58).

This catalog holds **inputs and expected verdicts only**. It is not Python and
does not import anything. Each case is written so it converts mechanically into
one row of a `@pytest.mark.parametrize` table.

## Files

| File | Layer | Contents |
|---|---|---|
| `01-item-cascade.md` | 2 | One section per fault code; the whole cascade, per grammar |
| `02-keyword-form.md` | 1 | Keyword case, emphasis, syntax negatives, legacy block header, continuation |
| `03-lists-and-salvage.md` | 2 | Empty items, trailing separator, salvage, multi-assertion, aliases, dedup |
| `04-over-malformed.md` | 1+2 | Inputs more malformed than the design anticipates |
| `05-surfaces-and-roundtrip.md` | 1–3 | Keyword x surface matrix, `code.no_traceability`, `fix` round-trip |
| `06-open-questions.md` | — | Cases whose expected verdict the design does not settle. Read before asserting. |

## Per-case schema

Every case carries all seven fields. A case missing **Estate** is untestable for
`unknown_requirement` / `unknown_assertion` / `forbidden`, which are verdicts
about index state rather than about text.

| Field | Meaning |
|---|---|
| **ID** | Stable case identifier, e.g. `PAD-03`. Cite it from the test. |
| **Input** | The author's text, verbatim. Single-line inputs appear as inline code; multi-line inputs as fenced blocks. Inputs are the *whole* line including the keyword unless the section says otherwise. |
| **Grammar** | Which configuration reads it — see the key below. |
| **Surface** | `code` \| `test` \| `spec` \| `journey`. Some cases are marked `all` and should be run on each. |
| **Estate** | Which identifiers must exist in the index for the expected verdict to hold. `-` means the verdict is independent of index state. |
| **Bindings** | Normalized references the item is expected to produce, in order. `none` is a real expectation, not a shrug. An item may produce a binding **and** a fault — see Q21, the leading-identifier rule — so this column and `Verdict` are not mutually exclusive. |
| **Verdict** | Per item: `index -> FaultClass / {codes}`. `E_SYNTAX_ERROR` is implicit on every fault (`ReferenceFault.__post_init__` adds it) and is written only where it is expected to stand *alone*. |

`OPEN:` on a case means the design does not determine the answer; the expected
column records the candidate readings instead of picking one. `DISPUTED:` means
two authored obligations appear to disagree. Neither should be silently resolved
by whoever converts this catalog — see `06-open-questions.md`.

## Grammar key

Six configurations, chosen because they already exist on disk and they cross
the dimensions a relaxation code can fire on (component style, digit padding,
label series, label padding, multi-separator, namespace prefixing).

| Key | Config | Canonical ID | Component | Labels | Multi-sep | Aliases |
|---|---|---|---|---|---|---|
| `G-STD` | `./.elspais.toml` (this repo) | `REQ-d00001` | numeric, 5 digits, zero-padded | uppercase `A`..`Z`, max 26 | `+` | `short = "{level.letter}{component}"` -> `d00001` |
| `G-E2E` | `tests/fixtures/e2e-standard` | `REQ-d00001` | numeric, 5 digits, zero-padded | uppercase, max 26 | `+` | **none** |
| `G-FDA` | `tests/fixtures/e2e-fda-numeric` | `DEV-00010` | numeric, 5 digits, zero-padded | numeric 0-based, max 26 | `+` | none |
| `G-NAMED` | `tests/fixtures/e2e-named-custom` | `REQ-dTokenStore` | PascalCase | numeric 0-based, max 99 | `&` | none |
| `G-JIRA` | `tests/fixtures/e2e-jira-edge` | `PROJ-123` | numeric, variable length, **not** zero-padded | numeric, max 26, **zero-padded** (`-01`) | `+` | none |
| `G-FED` | `tests/fixtures/e2e-associated` | federation of three | see below | see below | `+` | none |

`G-STD` and `G-E2E` differ **only** in aliases. That pairing is the whole test
for the implementor's design change: an alias item must read under `G-STD` and
must fall out as `unknown_namespace` under `G-E2E`. Do not collapse them.

`G-FED` members:

| Member | Namespace | Labels |
|---|---|---|
| core | `REQ` | uppercase |
| alpha | `REQ-ALP` | uppercase |
| beta | `REQ-BET` | numeric 0-based |

`REQ` prefixes `REQ-ALP`, which is the documented mis-attribution bug the
namespace test replaces (`target_id.startswith(f"{namespace}-")`). Every
namespace-test case that matters lives in this federation.

The assertion separator is `-` in all six. `REF_LIST_SEPARATOR` is `,` in all
six and is not configurable (REQ-d00251-M).

## Companion estate

Identifiers the cases assume exist. A converter should author exactly these and
nothing more — a case that expects `unknown_requirement` is only meaningful
against a known-closed index.

| Grammar | Requirements (assertions) |
|---|---|
| `G-STD` / `G-E2E` | `REQ-p00001` (A, B) - `REQ-o00030` (A) - `REQ-d00001` (A, B, C) - `REQ-d00002` (A) |
| `G-FDA` | `PRD-00001` (0, 1) - `DEV-00010` (0, 1, 2) |
| `G-NAMED` | `REQ-pUserAuth` (1, 2) - `REQ-dTokenStore` (1, 2, 3) |
| `G-JIRA` | `PROJ-7` (01, 02) - `PROJ-123` (01) |
| `G-FED` | core `REQ-p00001` (A) - alpha `REQ-ALP-p00001` (A) - beta `REQ-BET-p00001` (0) |

Deliberately absent everywhere, and cited by cases that expect
`unknown_requirement`: `REQ-d99999`, `DEV-99999`, `REQ-dNoSuchThing`,
`PROJ-99999`, `REQ-ALP-p99999`, `REQ-BET-p99999`.

## Surface spelling

The same item is expected to classify identically on every surface
(REQ-p00014-T). The surrounding syntax differs, so a converter needs the four
spellings. `<CONTENT>` is the case's input.

```text
code     (python)     # <CONTENT>
code     (go/ts)      // <CONTENT>
code     (sql)        -- <CONTENT>
test     (python)     # <CONTENT>
spec                  **Level**: dev | **Status**: Active | **<CONTENT>**
journey               **<CONTENT>**   (journey metadata block only)
```

Where a case's input is already a whole line including the keyword, the spec
spelling is the emphasis-wrapped form of that same keyword and content.

## Conventions

- Inputs are inline code or fenced blocks throughout, never bare text, so this
  directory cannot be mistaken for spec content by a scanner or by a reader.
- `_test_inputs/` is outside every `[scanning.*].directories` entry in this
  repo's `.elspais.toml`, so nothing here enters the repository's own graph.
- Trailing whitespace matters in several cases. Where it does, the case says so
  in words as well as showing it, because it does not survive an editor.
- Case IDs are stable. Add cases with new numbers; do not renumber.
