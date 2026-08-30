# Needed in elspais

Findings from producing the Callisto UAT dry-run traceability report against
0.121.233, federating `hht_diary_callisto` with `hht_diary` as its associate.
Every item below was hit in that work, and each names the evidence it rests on:
a source location where the cause was read, or the observation that produced it.

Ordered by how much damage the defect does before anyone notices it. The first
four are all the same species: **the tool silently declines to read a citation,
and the requirement then reports as uncovered.** That failure mode is worse than
an error, because an honest zero and a dropped citation are the same number.

---

## 1. The Dart annotation forward-look is a hard 5-line window, and a miss is silent

`src/elspais/graph/parsers/prescan.py:644-657`

A comment carrying a citation binds to the next `test(` / `testWidgets(` within
**five lines**:

```python
# 3) forward-look: a comment with no owner binds to the next test() within 5 lines
for ahead in range(1, min(6, len(lines) - idx)):
```

Past that window the comment binds to nothing, and the citation anchors a TEST
node at its own line that no test run can ever produce a result for. The
assertion then reads **Tested but never Passing, permanently** — which is
indistinguishable from a stale result, so the reflex is to re-run the suite,
which cannot move it.

The window is easy to exceed by accident, because the natural house style is a
citation line followed by the prose explaining what the test pins:

```text
// Verifies: DIARY-GUI-cra-dashboard/A          <- binds to nothing (6 lines)
// a CRA's permission set resolves the
//   Assigned Sites ("Sites") section first, so the CRA Dashboard is the
//   default landing surface on login (nothing selected yet -> index 0).
//   The CRA holds the dedicated site-audit permission (not a nav section)
//   instead of portal.audit.view, so it has NO global Audit Log tab.
test('a CRA-like set lands on Sites (the CRA Dashboard) by default', () {
```

Five lines of prose binds; six does not. Two annotations stacked above one test
is the same trap from the other direction — the lower one consumes the window
and strands the upper one.

`group(` is not in `_DART_TEST` at all (`prescan.py:43`), so a citation
describing a whole group orphans regardless of distance.

**Needed**

- Bind forward to the next test declaration without a line limit, stopping at
  the enclosing span's end or the previous span's close rather than at an
  arbitrary count. A comment block's length says nothing about what it
  describes.
- Independently of that: **a check that reports a citation in a scanned test
  file that binds to no test.** This is the load-bearing fix. Whatever the
  attachment rule, a citation that attaches to nothing must not be silently
  counted as evidence — today it inflates Tested and can never reach Passing.

---

## 2. A scoped report artifact does not carry its own scope

`src/elspais/commands/trace.py:1226` and `:1244`

`elspais trace --scope <name> -o report.html` prints the disclosure to stdout
and writes an artifact that does not contain it:

```python
result = resolve_scope_for_report(graph, params, config)
_print_scope(scope_disclosure(result))          # -> stdout
ids = None if len(result.ids) == result.population else result.ids
return _render_table_from_graph(graph, fmt, preset, ids, values, config)
```

`_render_table_from_graph` receives the selected `ids` but never the disclosure
lines. The html opens on a bare `<h1>Traceability Matrix</h1>`; the csv and
markdown start at the header row. Once the terminal is closed, the artifact is
mute about what it selected.

This is the exact harm `scope_disclosure` names in its own docstring, quoting
REQ-p00084-D: *"a report narrowed on purpose and one that lost requirements on
the way are the same artifact unless the narrowing is declared."* It is also a
disagreement between renderings of one report, which REQ-p00084-C forbids: the
composed summary path at `trace.py:1050` does prepend the lines
(`lines = list(scope_disclosure(result))`), so the same scope is declared in one
rendering and not in the other.

For a report going into a regulated dry-run package this is the difference
between an artifact a reviewer can check and one they have to take on trust.

**Needed**

Pass the disclosure into `_render_table_from_graph` and have every format emit
it — a leading comment row for csv, a subtitle for html, lines above the table
for markdown. The json path already carries `"scope"` in its payload; the
rendered formats should agree with it.

---

## 3. Dockerfiles are outside the default code-scan patterns

`src/elspais/graph/factory.py:421` (`DEFAULT_CODE_PATTERNS`)

The list covers 31 extensions and admits no Dockerfile, in either spelling —
extensionless `Dockerfile` or `<image>.Dockerfile`. A `# Implements:` comment in
one is read as ordinary prose.

In the sponsor repo this hid a correct, reviewed citation
(`CAL-PRD-notification-data-sync/B+C+E`, on the `ENV` lines that set the
sync-compliance thresholds) for over two weeks. The requirement read 0/8
implemented the whole time. Nothing reported it: not `checks`, not `broken`, not
`gaps`. A container image is where a deployment's configuration values are
actually bound, so this is not an exotic surface to be citing from.

**Needed**

- Add `Dockerfile`, `*.Dockerfile` and `Containerfile` to `DEFAULT_CODE_PATTERNS`.
- More generally, the class of defect matters more than the instance: a file
  inside a scanned `directories` root that contains a citation keyword but
  matches no pattern should be reported. Silence is the wrong answer to "this
  file is talking to you and you are not listening." Files in the ignore list should still be skipped
  with no message.

---

## 4. `[scanning.code].file_patterns` and `[scanning.test].file_patterns` have opposite semantics

`factory.py:768-796` (code) against `factory.py:820-823` (test)

Under `[scanning.code]`, `file_patterns` is **additive**: step 5a globs each
pattern from the repo root, and step 5b then scans `directories` with
`DEFAULT_CODE_PATTERNS` regardless of what was declared.

Under `[scanning.test]`, `file_patterns` is a **filter** applied to
`directories`.

Same key name, opposite meaning, no note in either place. Reading the code-side
key as a filter — the natural reading, and the one the test-side key teaches —
leads you to redeclare the full default list to avoid unbinding everything,
which is unnecessary; reading the test-side key as additive leads you to add a
directory and wonder why nothing scans.

**Needed**

The proper behavior for both is:
within the directories declared {
   scan the files which are not in the 'ignore' list
   if the file name matches the pattern given {
     include its citations normally
   }
   Otherwise {
     if the file contains citation keywords like implements:, verifies:, etc {
       then report it with a configuratble severity (info/warn/error)
     }
   }
}

---

## 5. A citation identifier absorbs trailing prose on the same line

Observed across three repos; each of these is reported unresolved rather than
resolved-with-a-comment:

```text
# Implements: DIARY-OPS-single-promotable-artifact/B — one environment-
# Implements: CAL-OPS-ci-secret-vulnerability-scanning/A (secret scanning on every push),
# Implements: HHT-OPS-secret-taxonomy/D + HHT-OPS-storage-rules/E
```

An em-dash gloss, a parenthetical, and a spaced `+` between two ids all fold
into the identifier. Writing the explanation on the citation line is the
obvious thing to do and it costs the edge every time.

It does at least surface in `elspais broken`, so this is a papercut rather than
a silent loss — but the report reads as a *broken reference* when the reference
is fine and the parse is not, which sends the reader looking in the wrong place.

**Needed**

Terminate the identifier at the first character the id grammar does not admit.
Note: Whitespace is never allowed as an id character.

If a proper identifier is followed by any combination of whitespace and an ID-separator
character (i.e. a comma), then look for another Identifier.

If there is a trailing comma and the next thing does NOT match an ID pattern, then it
is an finding with configurable severity (this behavior has been discussed and I expect is
captured in a spec).

New: Each scannable file type declares an associated comment pattern:
  C-like: //
  shell-like: #
  function-like: --
  lisp-like: ;
  math-like: %
  basic-like: '

A file-type is associated with only a single comment pattern.
The file-type declarations use this enumerated set by name. The specific set and names
must appear in the help docs, and should only be defined in one place (DRY).

To simplify parsing, the C-like block comment `/* */` is not supported.

New: If the there is an ID followed by whitespace, and the next thing is a
a comment pattern associated with the file type, then treat it as a valid comment for that line.

New: If the there is an ID followed by whitespace, and the next thing is NOT a comma and NOT ID and
NOT the configured comment pattern, then treat it as a `malformed comment` finding with configurable severity.

---

## 6. Comma-separated assertion lists half-parse into a phantom reference

```text
# Implements: HHT-OPS-confidential-keywords-scrubbing/H,I
```

produces two references: `HHT-OPS-confidential-keywords-scrubbing/H`, and a bare
`I` with no requirement attached. The estate's configured `multi_separator` is
`+`, so `,` is not a valid joiner — but instead of being rejected, the comma
splits the reference and the second half becomes a nonsense identifier that then
reports as broken.

The `elspais broken` output of a repo using this form is littered with bare
`B`, `D`, `F`, `I` entries whose origin is not obvious from the listing.

**Needed**

This is covered by Issue 5 above. Attempting to explain that the comma should be
a + is beyond the hueristics we will implement at present. However, wehen reporting 'broken'
or malformed references, we can cite the correct configured pattern the repo.

Note: Now that we are taking more care with error reporting, we should ensure that the
legacy nomenclature is consistent with the new phrasing. E.g. how is 'broken' different from
malformed? Answer: `broken` means it is a valid ID which matches nothing in the graph,
while `malformed` means it doesn't match the ID pattern.

---

## 7. No reporter can ingest an exit-code-only test producer

`src/elspais/graph/parsers/results/registry.py:60-67`

The registry offers `flutter-machine`, `junit`, `pytest-json` for results, and
three coverage formats. Every one of them requires the producer to emit a
structured per-test record.

A large class of real tests does not. `hht_diary` carries four deliberately
pytest-free check-tests under `.github/` that guard the CI machinery itself —
each asserts at module level and exits non-zero on the first failure, precisely
so it runs in a container holding nothing but an interpreter. They are genuine
tests, they carry correct `Verifies:` citations, they run in CI on every PR, and
their verdicts cannot reach the graph by any configuration available today.

Two things block it, and both need addressing:

- **No reporter fits.** pytest collects zero testcases from them (verified:
  `no tests ran`), so `pytest-json` and pytest's junitxml are empty.
- **A test node requires a recognised test function.** Wrapping them in a
  JUnit-emitting runner was tried: the results carried the correct repo-relative
  `file` attribute, and `match = "source"` bound them to nothing, because the
  scan creates no test node for a file with no test function.
  `match = "aggregate"` matched the results but credited no assertion.

**Needed**

An `exit-code` reporter, or an equivalent target shape, that takes a command and
credits the citations in the files the target names when it exits zero. The
granularity is the file rather than the assertion, which is exactly the
granularity a script that exits on first failure can honestly offer.

---

## 8. Scanning a test file that no target can run makes Tested worse, silently

Directly consequent on 7, and the reason it is worth fixing rather than
documenting.

Adding `.github/scripts` and `.github/tests` to `[scanning.test].directories`
raised the Tested figure from 165/251 to 166/251 while Passing did not move: the
newly scanned citations were counted as evidence and then waited forever for a
verdict. The configuration change made the report *less* truthful, and the only
signal was a `2 ingested result(s) matched no test` warning that pointed at the
results rather than at the cause.

`rules.coverage.uncredited_evidence` exists for adjacent territory (evidence
naming an assertion the denominator dimension does not count) and does not cover
this case.

**Needed**

A check reporting citations in scanned test files that no target with a
`command` can execute. "This file is scanned as a test, and nothing in your
configuration can ever run it" is a statement the tool is in a position to make
and the author is not.

---

## 9. `unmatched_results` gives a count and no names

```text
[!] tests.unmatched_results: 2 ingested result(s) matched no test
```

There is no way to learn which two. `-v` does not expand it and no follow-up
command is offered, though other findings in the same output do name one
(`references.malformed -> elspais broken`).

Isolating them meant moving the results file aside and re-running to diff the
totals.

**Needed**

Name them under `-v`, or offer a follow-up command the way the other checks do.
This one matters more than most, because an unmatched result is usually a
misconfigured target — the failure it reports is in the configuration, and the
identity of the result is the whole clue.

---

## Summary

| # | Item | Silent? | Kind |
|---|------|---------|------|
| 1 | Dart forward-look is a hard 5 lines | yes | bug + missing check |
| 2 | Scoped artifact omits its scope | yes | bug, against REQ-p00084-C/D |
| 3 | Dockerfiles outside default patterns | yes | gap |
| 4 | `file_patterns` means two things | n/a | consistency / docs |
| 5 | Identifier absorbs trailing prose | no | parser |
| 6 | see 5 | no | parser |
| 7 | No exit-code reporter | n/a | missing feature |
| 8 | Unrunnable test citations inflate Tested | yes | missing check |
| 9 | `unmatched_results` names nothing | no | diagnostics |
