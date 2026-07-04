# REQUIREMENT AUTHORING DECISIONS

The other docs describe the *grammar* of a requirement (see `format`,
`hierarchy`, `assertions`). This one describes the *judgment*: while
authoring, should you mint a new requirement, add an assertion to an
existing one, or just cite a parent you already have -- and at what
level does the new thing belong?

The governing idea: **requirements document invariants** -- things that
must stay true regardless of implementation detail or lower-level
requirements. You do not need a requirement per function. Often the
right move is to cite the parent of the thing you were about to specify.

**Why this is hard.** Each level is a lossy compression of the one above
it -- detail is deliberately dropped so the obligation reads at its
audience's altitude. Requirements are authored both **top-down**
(anchoring what the project must be) and **bottom-up** (concrete choices
-- a syntax, a vocabulary, a wire format -- that surface only during
implementation); both are legitimate, and the two meet in the middle.
Trouble comes when a test has to span too many compression layers at
once: the detail lost between them has to be guessed back, and the test
becomes arbitrary. Keeping each obligation testable at its own altitude
is the discipline that prevents that.

## The Decision

Three questions, every time you are about to specify or test something:

- New **requirement**, new **assertion** on an existing requirement, or
  **cite** an existing one?
- At what **level**?
- When may a **test** cite an abstract parent, and when must it attach to
  a concrete leaf?

## Two Axes: Level And Verifiability Distance

A requirement sits on two independent axes. Confusing them causes most
authoring mistakes.

- **Level** (top-down): altitude and audience. *Who consumes this
  obligation, at what abstraction?* This is the `Level` field; it routes
  a requirement into (or out of) an audience's report.
- **Verifiability distance** (bottom-up): how much interpretation sits
  between the assertion text and a pass/fail check. Small distance = a
  **leaf** (directly testable). Large distance = an **anchor** (verified
  only through the requirements that refine it).

```
                      small distance        large distance
                      (leaf, testable)      (anchor)

  high level          "repo has a license"  "conforms to ALCOA+"
  low level           most impl. leaves     rare low-level anchor
```

**Leaf-ness is not a level.** A high-level obligation can be a directly
testable leaf (a license-file check); a low-level requirement can, rarely,
be an anchor. The axes usually correlate -- higher tends to mean more
abstract -- which is why "levels as compression tiers" works most of the
time. The skill is noticing when they decouple.

## The Funnel

Run this in order. The cheapest "create nothing" exits come first.

```
0. Is it an OBLIGATION (normative, SHALL) or a description?
   description -> no requirement at all. Stop.

1. INVARIANT TEST: would this still have to be true if the
   implementation were reasonably rewritten a different way?
   NO  -> it is an implementation detail, not an invariant.
          Do NOT mint a requirement. Cite the nearest parent.
   YES -> continue.

2. DUPLICATION TEST: does an existing assertion already state
   this closely enough that a test citing it is self-evidently
   checking it (no blank-filling)?
   YES -> cite it. State each obligation once. Stop.
   NO  -> you are creating something. Continue.

3. GRANULARITY: new assertion, or new requirement?
   Same obligation-boundary / entity / level
       -> add an assertion to the existing requirement.
   Distinct boundary, entity, or audience/level
       -> new requirement.

4. LEVEL = altitude + audience of the INVARIANT,
   not of the code that triggered it.

5. RELATE it to the nearest parent it elaborates
   (Refines / Implements / Satisfies / Integrates -- see
   `elspais docs hierarchy`).
```

## Two Tests That Do The Work

**Invariant / reimplementation test** (step 1) -- the gate against
*over-specification*. "Would this survive a reasonable rewrite?" If no,
it is a detail, not an invariant: cite the parent. This kills *one
requirement per function* and *one assertion per config value*.

**Arbitrariness / blank-fill test** (step 2) -- the gate against
*under-specification*. If linking a test to the candidate assertion
requires inventing a pass/fail criterion the assertion does not state,
the semantic distance is too large: author a leaf at the right altitude.

```
  UNDER-SPECIFY                        OVER-SPECIFY
  (cite a parent too abstract;         (one requirement per function;
   pass/fail needs blank-filling;       a detail frozen as an invariant;
   the test link is arbitrary)          the spec turns brittle)

        --- GOLDILOCKS: create only when BOTH hold ---
        (1) it states a genuine invariant, and
        (2) nothing existing is close enough to cite.
```

An auditor-mandated exact value *is* an invariant -- the auditor froze
it, so it survives reimplementation by fiat. It passes step 1 cleanly.

## Which Level

Level is the altitude and audience of the *invariant*, never the location
of the code that triggered it. A detail discovered deep in the
implementation may still express a product-level guarantee; an abstract
product goal may only ever be verified through engineering leaves.

Levels are configurable (`[levels]` in `.elspais.toml`); the built-in
default is `PRD -> OPS -> DEV`. Many regulated projects adopt a fuller
exemplar schema:

```
  BASE  apex framing         internal, anchor-only (filtered from
                             external reports)
  PRD   product behavior     what the product provides
  GUI   presentation         interface behavior; usually refines a PRD
  OPS   operations           deployment, runbooks
  DEV   realization          how it is implemented
```

Choose the set that fits your project; the concepts here hold for any
schema. Authoring a requirement bottom-up is normal, not a failure of
top-down planning: implementation routinely forces a concrete choice --
a syntax, a vocabulary, a wire format -- that no high-level requirement
could have stated in advance. Such an invariant lands at the lowest level
where it is still an invariant -- often DEV -- and refines an abstract
parent that stays abstract. Top-down anchors and bottom-up leaves meet in
the middle; each is tested at its own altitude.

## The "Why" Stopping Rule

Refining a testable leaf under an abstract "why" parent is optional, and
"why" regresses forever. Bound it:

Add a higher "why" parent only when it does verification or governance
work the leaf alone cannot -- when at least one holds:

- **Two or more children ladder to it** -- the parent earns its keep by
  grouping siblings.
- **The "why" is itself audited** -- someone gates on it directly, so it
  is an obligation, not just motivation.
- **You can see the seam** where future children will attach.

If none hold, stop: keep the single assertion at its natural altitude and
put the "why" in a non-normative Rationale section. "Why" ends where the
next level up would have exactly one child and is not independently
audited.

## Tests Attach To Leaves

A test attaches to an assertion only if pass/fail is decidable from the
assertion text alone. A test may cite a higher-level assertion only when
the distance is small; otherwise its target must be a lower leaf, and if
none exists, authoring one is mandatory (back to step 3).

"Anchor-only" is a property of large semantic distance, not of a level.
The smell is not "a test cites a high-level requirement" -- it is "a test
cites an assertion whose text does not decide the test."

## Anti-Patterns

- **One requirement per function / per config value.** Fails step 1 --
  a detail, not an invariant. Cite the parent.
- **Testing an abstract anchor directly.** Its text does not decide the
  test; you are really checking a child (author it), or the anchor is a
  mislevelled leaf (relevel it).
- **Premature "why" parent.** An elaboration chain up to a justification
  with one child that nobody audits. Collapse it into Rationale until a
  second sibling appears.
- **Levelling by code location.** Assigning DEV because the trigger was
  found in code, when the invariant is a product guarantee.

## Worked Example: A High-Level Leaf

Suppose a project must keep its repository open-source (a licensing or
funding policy). The obligation is **high level** -- it is about the
product's standing, not its code -- yet **directly testable**: is there
an approved license file? is the repo public? Verification distance is
tiny.

If the license file is the *only* manifestation of the policy, keep one
high-level assertion, put "so the project satisfies the policy" in
Rationale, and test it directly. Do not invent a "policy-compliant"
parent (stopping rule: one child, not audited). The moment a second
sibling appears -- public-repo, permissive-dependencies -- promote the
policy to an anchor and refine both leaves under it.

## See Also

  $ elspais docs hierarchy      # levels and relationships
  $ elspais docs assertions     # writing testable assertions
  $ elspais docs format         # requirement structure
  $ elspais docs linking        # attaching code and tests
