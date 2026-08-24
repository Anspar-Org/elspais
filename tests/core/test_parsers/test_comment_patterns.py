# Verifies: REQ-d00236-H
"""One comment pattern per file type, from one named set.

A *Traceability* keyword is read only in a comment opened by the pattern
associated with the language of the file it sits in (REQ-d00269-K). These
tests drive the real ``FileDispatcher`` so what they pin is what a scan of a
real tree does, not what a helper does in isolation.

The distinction under test is about WHERE a reference may be written, never
about WHAT it may say: the identifier grammar is one set of rules in every
context (REQ-p00014-T), and none of these tests varies it.
"""

from __future__ import annotations

import pytest

from elspais.config.schema import ElspaisConfig
from elspais.graph.parsers.lark import FileDispatcher
from elspais.graph.parsers.patterns import (
    COMMENT_PATTERN_BY_EXTENSION,
    METADATA_COMMENT_MARKERS,
    CommentPattern,
    comment_markers_for_path,
    comment_pattern_for_path,
    comment_style_fragment,
)
from elspais.graph.reference_faults import FaultClass, FaultCode
from elspais.utilities.patterns import IdPatternConfig, IdResolver

_CONFIG = {
    "project": {"namespace": "REQ"},
    "levels": {
        "prd": {"rank": 1, "letter": "p", "implements": ["prd"]},
        "ops": {"rank": 2, "letter": "o", "implements": ["ops", "prd"]},
        "dev": {"rank": 3, "letter": "d", "implements": ["dev", "ops", "prd"]},
    },
    "id-patterns": {
        "canonical": "{namespace}-{level.letter}{component}",
        "component": {"style": "numeric", "digits": 5, "leading_zeros": True},
        "assertions": {"label_style": "uppercase", "max_count": 26},
    },
}


@pytest.fixture
def dispatcher():
    ElspaisConfig.model_validate(_CONFIG)
    return FileDispatcher(IdResolver(IdPatternConfig.from_dict(_CONFIG)))


def _bound(dispatcher, content, path):
    """Every identifier the scan binds anywhere in *content*, read as code.

    Unresolved targets ride along here verbatim, so a test asking whether a
    clean identifier was bound must check for that identifier rather than for
    emptiness -- see ``_verdicts`` for what the scan thought of each one.
    """
    found: set[str] = set()
    for parsed in dispatcher.dispatch_code(content, path):
        for key in ("implements", "verifies", "forbidden"):
            found.update(parsed.parsed_data.get(key) or [])
    return found


def _verdicts(dispatcher, content, path):
    """Every reference verdict the scan reached, keyed by (keyword, target)."""
    verdicts: dict = {}
    for parsed in dispatcher.dispatch_code(content, path):
        verdicts.update(parsed.parsed_data.get("reference_verdicts") or {})
    return verdicts


# --- A keyword is read only in its own language's pattern ------------------ #


# Verifies: REQ-d00269-K
@pytest.mark.parametrize(
    ("marker", "honoured_in", "ignored_in"),
    [
        ("#", "svc.py", "svc.js"),
        ("//", "svc.js", "svc.py"),
        ("--", "schema.sql", "svc.py"),
        (";", "core.el", "svc.py"),
        ("%", "paper.tex", "svc.js"),
        ("'", "form.vb", "svc.py"),
    ],
)
def test_a_keyword_binds_only_behind_its_own_languages_marker(
    dispatcher, marker, honoured_in, ignored_in
):
    """The same annotation text binds in one language and not in another.

    Both halves matter. Honouring alone would pass with the old
    accepts-everything behaviour; the ignored half is what pins that a marker
    belonging to another language no longer opens a comment here.
    """
    content = f"{marker} Implements: REQ-d00001-A\n"

    assert _bound(dispatcher, content, honoured_in) == {"REQ-d00001-A"}
    assert _bound(dispatcher, content, ignored_in) == set()


# Verifies: REQ-d00269-K
def test_a_python_file_reads_a_double_dash_as_arithmetic_not_as_a_comment(dispatcher):
    """The specific misreading the association exists to remove.

    ``--`` opening a comment in every file meant a Python line could bind a
    reference the language has no way to write.
    """
    assert _bound(dispatcher, "-- Implements: REQ-d00001-A\n", "svc.py") == set()
    assert _bound(dispatcher, "-- Implements: REQ-d00001-A\n", "schema.sql") == {"REQ-d00001-A"}


# --- A comment ends a reference, in that language only --------------------- #


# Verifies: REQ-d00272-Q
@pytest.mark.parametrize(
    ("path", "marker"),
    [("svc.py", "#"), ("svc.js", "//"), ("schema.sql", "--")],
)
def test_a_reference_followed_by_its_own_comment_resolves_with_the_remainder_ignored(
    dispatcher, path, marker
):
    """Prose after a reference is comment, not a second reference."""
    content = f"{marker} Implements: REQ-d00001-A {marker} because the hash must be salted\n"
    assert _bound(dispatcher, content, path) == {"REQ-d00001-A"}


# Verifies: REQ-d00272-R
def test_another_languages_marker_does_not_end_a_reference(dispatcher):
    """``--`` closes nothing in a c-like file, so it cannot silently truncate.

    The reference is followed by content that opens neither a further
    reference nor a comment this language admits. It is therefore reported
    rather than repaired: the clean identifier is NOT bound, and the item is
    carried through verbatim under a fault of its own. Truncating at a marker
    the language does not admit would create an edge the author never wrote
    and report nothing.
    """
    content = "// Implements: REQ-d00001-A -- because the hash must be salted\n"
    assert "REQ-d00001-A" not in _bound(dispatcher, content, "svc.js")

    verdicts = _verdicts(dispatcher, content, "svc.js")
    assert len(verdicts) == 1
    ((target, (fault_class, codes)),) = verdicts.items()
    assert target == ("implements", "REQ-d00001-A -- because the hash must be salted")
    assert fault_class is FaultClass.MALFORMED
    assert codes == (FaultCode.IDENTIFIER_WITH_TRAILING_TEXT,)

    # The same line in the language that DOES admit that marker resolves
    # cleanly and reports nothing -- the difference is the language, and only
    # the language.
    sql = "-- Implements: REQ-d00001-A -- because the hash must be salted\n"
    assert _bound(dispatcher, sql, "schema.sql") == {"REQ-d00001-A"}
    assert _verdicts(dispatcher, sql, "schema.sql") == {}


# --- An extension the set does not name ------------------------------------ #


# Verifies: REQ-d00269-K
@pytest.mark.parametrize("path", ["theme.css", "page.html", "matrix.m", "boot.s", "Makefile"])
def test_an_unassociated_extension_reads_a_keyword_nowhere(dispatcher, path):
    """No pattern means no place a keyword counts -- for every marker.

    Under-reporting is the deliberate direction: an extension the set cannot
    associate with ONE pattern is associated with none, rather than being
    given a permissive default.
    """
    assert comment_pattern_for_path(path) is None
    for marker in ("#", "//", "--", ";", "%", "'"):
        assert _bound(dispatcher, f"{marker} Implements: REQ-d00001-A\n", path) == set()


# Verifies: REQ-d00269-K
def test_a_bare_keyword_outside_any_comment_never_binds_in_an_unassociated_file(dispatcher):
    """An empty marker set must never collapse into "match anything".

    An alternation of nothing matches the empty string, which would let a
    keyword with no marker at all bind. The never-matching fragment is what
    stops that, so it is pinned directly as well as through the scan.
    """
    assert comment_style_fragment(()) == "(?!)"
    assert _bound(dispatcher, "Implements: REQ-d00001-A\n", "theme.css") == set()


# Verifies: REQ-d00236-H
def test_a_template_is_c_like_whatever_it_renders_to(dispatcher):
    """A scanned file type carries ONE pattern, so `.j2` cannot carry several.

    Reading the suffix beneath the template suffix would make `page.css.j2`
    and `viewer.js.j2` different file types, and would silence the annotations
    in every template rendering to a block-comment language -- real code
    implementing real requirements.
    """
    for path in ("viewer.js.j2", "page.css.j2", "conf.yml.j2", "report.j2"):
        assert comment_pattern_for_path(path) is CommentPattern.C_LIKE
        assert _bound(dispatcher, "// Implements: REQ-d00001-A\n", path) == {"REQ-d00001-A"}

    # And only that one pattern: the language beneath the template suffix does
    # not get a second say.
    assert _bound(dispatcher, "# Implements: REQ-d00001-A\n", "conf.yml.j2") == set()


# --- One named set, defined once ------------------------------------------- #


# Verifies: REQ-d00236-H
def test_every_associated_extension_names_exactly_one_pattern_from_the_set():
    """The association is a mapping, so no extension can hold two patterns.

    A dict cannot express a duplicate key, so what this checks is the other
    half: every value is a member of the named set, and every member of that
    set is reachable -- six names that no file type uses would be vocabulary
    the docs publish and the tool never applies.
    """
    values = set(COMMENT_PATTERN_BY_EXTENSION.values())
    assert values == set(CommentPattern)
    for extension, pattern in COMMENT_PATTERN_BY_EXTENSION.items():
        assert extension.startswith(".") and extension == extension.lower()
        assert comment_markers_for_path(f"file{extension}") == (pattern.marker,)


# Verifies: REQ-d00236-H
def test_the_marker_a_file_type_uses_has_one_spelling_across_the_tool():
    """Grammar, term scanner and metadata convention all read the one map.

    Each of these three surfaces previously spelled the marker set itself.
    Comparing them against the map rather than against a literal is what
    makes a future divergence fail here.
    """
    from elspais.graph import term_scanner
    from elspais.utilities.patterns import default_comment_markers

    for pattern, langs in (
        (CommentPattern.SHELL_LIKE, term_scanner._HASH_LANGS),
        (CommentPattern.C_LIKE, term_scanner._SLASH_LANGS),
        (CommentPattern.FUNCTION_LIKE, term_scanner._DASH_LANGS),
    ):
        assert langs == {ext for ext, p in COMMENT_PATTERN_BY_EXTENSION.items() if p is pattern}

    # The spec/journey metadata convention is drawn from the same set rather
    # than respelled. It is not a per-file reference override: a metadata line
    # is markdown, not a comment in any language.
    assert default_comment_markers() == METADATA_COMMENT_MARKERS
    assert set(METADATA_COMMENT_MARKERS) <= {p.marker for p in CommentPattern}


# Verifies: REQ-d00236-H
def test_a_block_comment_language_is_associated_with_no_pattern():
    """Block comments carry no citation, so they name no pattern.

    Reasserting the limitation as an association rather than as a special
    case: nothing in the set spells ``/*`` or ``<!--``.
    """
    markers = {p.marker for p in CommentPattern}
    assert "/*" not in markers
    assert "<!--" not in markers
    for path in ("theme.css", "page.html", "icon.svg", "data.xml"):
        assert comment_pattern_for_path(path) is None


# --- The set is published -------------------------------------------------- #


# Verifies: REQ-d00236-J
def test_the_named_set_appears_in_the_help_documentation():
    """Every name and marker is reachable through ``elspais docs linking``.

    The assertion is about the tool's help documentation, so the packaged
    docs file is what is read -- not a repository-root copy.
    """
    from pathlib import Path

    import elspais

    text = (Path(elspais.__file__).parent / "docs" / "cli" / "linking.md").read_text()

    for pattern in CommentPattern:
        assert f"`{pattern.label}`" in text, f"{pattern.label} is not published"
        assert f"`{pattern.marker}`" in text, f"marker for {pattern.label} is not published"

    # The published set must not read as a per-file reference grammar
    # (REQ-p00014-T): the distinction is stated, not left to be inferred.
    assert "never WHAT it may say" in text


# --- Writing a link uses the same association as reading one --------------- #


# Verifies: REQ-d00269-K
@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("svc.py", "# Implements: REQ-d00001-A"),
        ("svc.js", "// Implements: REQ-d00001-A"),
        ("schema.sql", "-- Implements: REQ-d00001-A"),
        ("viewer.js.j2", "// Implements: REQ-d00001-A"),
    ],
)
def test_an_applied_link_is_written_in_the_files_own_comment_pattern(path, expected):
    """A link this tool writes must be one the next scan reads.

    Spelling `#` into a JavaScript file would leave a line that is neither
    valid there nor ever read back -- a relationship the author was told
    existed and that nothing records.
    """
    from pathlib import Path

    from elspais.graph.link_suggest import apply_link_to_file

    assert apply_link_to_file(Path(path), 0, "REQ-d00001-A", dry_run=True) == expected


# Verifies: REQ-d00269-K
@pytest.mark.parametrize("path", ["theme.css", "page.html", "Makefile"])
def test_no_link_is_written_into_a_file_that_could_not_carry_one(path):
    """Refusing beats writing a declaration that declares nothing."""
    from pathlib import Path

    from elspais.graph.link_suggest import apply_link_to_file

    assert apply_link_to_file(Path(path), 0, "REQ-d00001-A", dry_run=True) is None


# Verifies: REQ-d00269-K
@pytest.mark.parametrize(
    ("path", "rule", "continues"),
    [
        # A rule drawn in the file's OWN marker characters is an empty
        # comment, so it does not interrupt a block being read.
        ("svc.py", "# ####", True),
        ("schema.sql", "-- ----", True),
        # A rule drawn in another language's characters is content here, so
        # it ends the block rather than being skipped over.
        ("svc.py", "# ------", False),
    ],
)
def test_a_decorative_rule_is_empty_only_in_its_own_marker_characters(
    dispatcher, path, rule, continues
):
    """Which characters make a rule "decorative" is a fact about the language.

    Dashes are a comment's own characters in SQL and an expression's in
    Python, so the same rule reads differently in each -- pinned here because
    nothing else would stop it being "corrected" back to one global charset.
    """
    marker = comment_markers_for_path(path)[0]
    content = (
        f"{marker} IMPLEMENTS REQUIREMENTS:\n"
        f"{marker}   REQ-d00001-A\n"
        f"{rule}\n"
        f"{marker}   REQ-d00002-B\n"
    )
    bound = _bound(dispatcher, content, path)
    assert "REQ-d00001-A" in bound
    assert ("REQ-d00002-B" in bound) is continues
