# WRITING ASSERTIONS

## What is an Assertion?

An assertion is a single, testable statement about system behavior.
Each assertion:
- Uses **SHALL** or **SHALL NOT** (normative language)
- Is labeled A, B, C, etc.
- Can be independently verified by a test

## Assertion Format

```
## Assertions

A. The system SHALL authenticate users via email and password.
B. The system SHALL lock accounts after 5 failed attempts.
C. The system SHALL NOT store passwords in plain text.
```

## Normative Keywords

  **SHALL**         Absolute requirement (must be implemented)
  **SHALL NOT**     Absolute prohibition (must never happen)
  **SHOULD**        Recommended but not required
  **SHOULD NOT**    Not recommended but not prohibited
  **MAY**           Optional behavior

Most assertions use **SHALL** or **SHALL NOT**.

## Good vs Bad Assertions

**Good** (testable, specific):
  A. The system SHALL respond to API requests within 200ms.
  B. The system SHALL encrypt data at rest using AES-256.

**Bad** (vague, untestable):
  A. The system should be fast.
  B. The system must be secure.

## Referencing Assertions

In implementing requirements:
```
**Implements**: REQ-p00001-A
```

In code comments, using the comment pattern of that file's own language --
`#` in Python, `//` in JavaScript, `--` in SQL. See `elspais docs linking` for
the full named set. A keyword inside a block comment (`/* */`, `<!-- -->`) is
never read:
```
# Implements: REQ-p00001-A     <- in a .py file
// Implements: REQ-p00001-A    <- in a .js file
```

In tests, by a comment above the test -- a test function's name references
nothing:
```python
# Verifies: REQ-p00001-A
def test_login(): ...
```

## Parsing Directives

Assertion text that begins with `<`, `[` or `{` carries a **parsing
directive**: an instruction addressed to the tool rather than an obligation.
The directive is what the opening delimiter and its matching closer enclose,
and anything after the closer is the assertion's ordinary content.

```
F. <RETIRED> Superseded by REQ-d00005-B.
```

All three delimiter pairs are accepted. Case is presentation, not identity --
`<RETIRED>`, `<Retired>` and `<retired>` name the same directive, and a rewrite
emits the one canonical spelling while leaving the delimiters and the trailing
commentary exactly as written.

A directive the tool does not recognize is never quietly read as prose: it is
reported by the `spec.unknown_directive` check, which names the directive, its
file and its line. Reporting it is not withdrawing the assertion -- the
assertion still counts, and still needs coverage.

## Retired Assertions

`RETIRED` is the one recognized directive. An assertion carrying it does not
exist for coverage and traceability purposes:

- It leaves every coverage denominator -- it is not counted among the
  assertions expected to be implemented, tested or validated.
- References targeting it do not resolve, and surface as unresolved
  references, exactly as a reference to an assertion that was never written.
- Its **label stays allocated** forever. The letter is never reused, so the
  next assertion added lands past it.

```
A. The system SHALL do X.
B. <RETIRED> Superseded by REQ-d00005-B.
C. The system SHALL do Z.
```

The informal `[Removed - ...]` placeholder is superseded by this directive.
A placeholder is read as an unrecognized directive, so it is reported and the
assertion goes on counting as a permanently-uncovered one until it is
converted. Converting one breaks any reference that still names its letter,
which is the point: retirement withdraws the obligation, so a citation of it
is a defect worth seeing.
