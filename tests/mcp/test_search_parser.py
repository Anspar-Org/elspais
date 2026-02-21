# Validates REQ-d00061-F, REQ-d00061-G, REQ-d00061-H, REQ-d00061-I,
# Validates REQ-d00061-J, REQ-d00061-K, REQ-d00061-M
"""Tests for parse_query() in elspais.mcp.search.

Validates REQ-d00061-F, REQ-d00061-G, REQ-d00061-H,
REQ-d00061-I, REQ-d00061-J, REQ-d00061-K, REQ-d00061-M:
  Multi-term AND queries, OR operator support, parenthesized grouping,
  quoted phrases, exclusion with -prefix, exact keyword with =prefix,
  and parse_query function behaviour.
"""

from elspais.mcp.search import SearchTerm, parse_query

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _plain(text: str) -> SearchTerm:
    """Shortcut for a plain (non-exact, non-negated) search term."""
    return SearchTerm(text=text.lower(), exact=False, negated=False)


def _exact(text: str) -> SearchTerm:
    """Shortcut for an exact keyword search term."""
    return SearchTerm(text=text.lower(), exact=True, negated=False)


def _negated(text: str) -> SearchTerm:
    """Shortcut for a negated (exclusion) search term."""
    return SearchTerm(text=text.lower(), exact=False, negated=True)


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestParseQuery:
    """Validates REQ-d00061-F, REQ-d00061-G, REQ-d00061-H,
    REQ-d00061-I, REQ-d00061-J, REQ-d00061-K, REQ-d00061-M:

    parse_query transforms raw query strings into a structured ParsedQuery
    containing AND-groups, excluded terms, and phrase matches.
    """

    # -- 1. Empty / whitespace queries ----------------------------------------

    def test_REQ_d00061_M_empty_string_is_empty(self):
        """Empty string produces an empty ParsedQuery."""
        result = parse_query("")
        assert result.is_empty

    def test_REQ_d00061_M_whitespace_only_is_empty(self):
        """Whitespace-only string produces an empty ParsedQuery."""
        result = parse_query("   \t  ")
        assert result.is_empty

    # -- 2. Single term -------------------------------------------------------

    def test_REQ_d00061_F_single_term(self):
        """A single term produces one and_group with one SearchTerm."""
        result = parse_query("auth")
        assert result.and_groups == ((_plain("auth"),),)
        assert result.excluded == ()
        assert result.phrases == ()

    def test_REQ_d00061_M_single_term_is_lowercased(self):
        """Terms are lowercased in the parsed output."""
        result = parse_query("AuthToken")
        assert result.and_groups == ((_plain("authtoken"),),)

    # -- 3. Two terms (implicit AND) ------------------------------------------

    def test_REQ_d00061_F_implicit_and_two_terms(self):
        """Two space-separated terms produce two separate and_groups (implicit AND)."""
        result = parse_query("auth token")
        assert len(result.and_groups) == 2
        assert result.and_groups[0] == (_plain("auth"),)
        assert result.and_groups[1] == (_plain("token"),)

    def test_REQ_d00061_F_multiple_terms_implicit_and(self):
        """Three space-separated terms produce three and_groups."""
        result = parse_query("auth token session")
        assert len(result.and_groups) == 3
        assert result.and_groups[0] == (_plain("auth"),)
        assert result.and_groups[1] == (_plain("token"),)
        assert result.and_groups[2] == (_plain("session"),)

    # -- 4. OR between terms --------------------------------------------------

    def test_REQ_d00061_G_or_between_two_terms(self):
        """OR between two terms produces one and_group with both terms."""
        result = parse_query("auth OR token")
        assert len(result.and_groups) == 1
        assert result.and_groups[0] == (_plain("auth"), _plain("token"))

    def test_REQ_d00061_G_or_chain_three_terms(self):
        """Chained OR between three terms produces one and_group with all three."""
        result = parse_query("auth OR token OR session")
        assert len(result.and_groups) == 1
        assert result.and_groups[0] == (
            _plain("auth"),
            _plain("token"),
            _plain("session"),
        )

    # -- 5. Mixed AND and OR --------------------------------------------------

    def test_REQ_d00061_F_G_mixed_and_or(self):
        """Mixed AND and OR: 'a OR b c' -> two and_groups: (a, b) and (c,)."""
        result = parse_query("auth OR password security")
        assert len(result.and_groups) == 2
        assert result.and_groups[0] == (_plain("auth"), _plain("password"))
        assert result.and_groups[1] == (_plain("security"),)

    def test_REQ_d00061_F_G_and_before_or(self):
        """'a b OR c' -> two and_groups: (a,) and (b, c)."""
        result = parse_query("security auth OR password")
        assert len(result.and_groups) == 2
        assert result.and_groups[0] == (_plain("security"),)
        assert result.and_groups[1] == (_plain("auth"), _plain("password"))

    # -- 6. Parenthesized groups -----------------------------------------------

    def test_REQ_d00061_H_parenthesized_group(self):
        """Parenthesized group becomes a single OR-group and_group."""
        result = parse_query("(auth password)")
        assert len(result.and_groups) == 1
        assert result.and_groups[0] == (_plain("auth"), _plain("password"))

    def test_REQ_d00061_H_parenthesized_with_or(self):
        """Parenthesized OR group becomes a single and_group."""
        result = parse_query("(auth OR password)")
        assert len(result.and_groups) == 1
        assert result.and_groups[0] == (_plain("auth"), _plain("password"))

    # -- 7. Parenthesized group AND term --------------------------------------

    def test_REQ_d00061_H_F_paren_group_and_term(self):
        """Parenthesized group AND a plain term -> two and_groups."""
        result = parse_query("(auth OR password) security")
        assert len(result.and_groups) == 2
        assert result.and_groups[0] == (_plain("auth"), _plain("password"))
        assert result.and_groups[1] == (_plain("security"),)

    def test_REQ_d00061_H_F_term_and_paren_group(self):
        """A plain term AND a parenthesized group -> two and_groups."""
        result = parse_query("security (auth OR password)")
        assert len(result.and_groups) == 2
        assert result.and_groups[0] == (_plain("security"),)
        assert result.and_groups[1] == (_plain("auth"), _plain("password"))

    # -- 8. Quoted phrases ----------------------------------------------------

    def test_REQ_d00061_I_quoted_phrase(self):
        """Quoted phrase is stored in phrases tuple, lowercased."""
        result = parse_query('"Row Level Security"')
        assert result.phrases == ("row level security",)
        assert result.and_groups == ()

    def test_REQ_d00061_I_quoted_phrase_with_term(self):
        """Quoted phrase alongside a term: phrase in phrases, term in and_groups."""
        result = parse_query('auth "row level"')
        assert result.and_groups == ((_plain("auth"),),)
        assert result.phrases == ("row level",)

    def test_REQ_d00061_I_multiple_quoted_phrases(self):
        """Multiple quoted phrases are all captured."""
        result = parse_query('"alpha bravo" "charlie delta"')
        assert result.phrases == ("alpha bravo", "charlie delta")

    # -- 9. Exclusion terms ---------------------------------------------------

    def test_REQ_d00061_J_exclusion_term(self):
        """A -prefixed term is stored in excluded tuple."""
        result = parse_query("-deprecated")
        assert result.excluded == (_negated("deprecated"),)
        assert result.and_groups == ()

    def test_REQ_d00061_J_exclusion_with_positive_term(self):
        """Exclusion terms sit in excluded; positive terms in and_groups."""
        result = parse_query("auth -deprecated")
        assert result.and_groups == ((_plain("auth"),),)
        assert result.excluded == (_negated("deprecated"),)

    def test_REQ_d00061_J_multiple_exclusions(self):
        """Multiple exclusion terms are all captured."""
        result = parse_query("-deprecated -obsolete")
        assert result.excluded == (_negated("deprecated"), _negated("obsolete"))
        assert result.and_groups == ()

    # -- 10. Exact keyword terms -----------------------------------------------

    def test_REQ_d00061_K_exact_keyword(self):
        """An =prefixed term has exact=True."""
        result = parse_query("=security")
        assert len(result.and_groups) == 1
        assert result.and_groups[0] == (_exact("security"),)

    def test_REQ_d00061_K_exact_keyword_with_plain(self):
        """Exact keyword alongside plain term: both in separate and_groups."""
        result = parse_query("auth =security")
        assert len(result.and_groups) == 2
        assert result.and_groups[0] == ((_plain("auth")),)
        assert result.and_groups[1] == ((_exact("security")),)

    def test_REQ_d00061_K_exact_keyword_is_lowercased(self):
        """Exact keywords are lowercased."""
        result = parse_query("=Security")
        assert result.and_groups[0] == (_exact("security"),)

    # -- 11. Complex combined query --------------------------------------------

    def test_REQ_d00061_F_G_H_J_complex_query(self):
        """Complex query: (auth OR password) AND RLS -deprecated.

        Expects:
        - and_groups: ((auth, password), (rls,))
        - excluded: (deprecated,)
        """
        result = parse_query("(auth OR password) RLS -deprecated")
        assert len(result.and_groups) == 2
        assert result.and_groups[0] == (_plain("auth"), _plain("password"))
        assert result.and_groups[1] == (_plain("rls"),)
        assert result.excluded == (_negated("deprecated"),)
        assert result.phrases == ()

    def test_REQ_d00061_F_G_H_I_J_K_M_kitchen_sink(self):
        """All features combined: groups, OR, phrases, exclusions, exact.

        Query: (auth OR session) =security "row level" -deprecated
        """
        result = parse_query('(auth OR session) =security "row level" -deprecated')
        assert len(result.and_groups) == 2
        assert result.and_groups[0] == (_plain("auth"), _plain("session"))
        assert result.and_groups[1] == (_exact("security"),)
        assert result.phrases == ("row level",)
        assert result.excluded == (_negated("deprecated"),)
        assert not result.is_empty

    # -- 12. Explicit AND keyword ----------------------------------------------

    def test_REQ_d00061_F_explicit_and_keyword(self):
        """Explicit AND keyword behaves same as space (implicit AND)."""
        result = parse_query("auth AND token")
        assert len(result.and_groups) == 2
        assert result.and_groups[0] == (_plain("auth"),)
        assert result.and_groups[1] == (_plain("token"),)

    def test_REQ_d00061_F_explicit_and_same_as_space(self):
        """Explicit AND produces the same result as implicit space."""
        explicit = parse_query("auth AND token")
        implicit = parse_query("auth token")
        assert explicit.and_groups == implicit.and_groups
        assert explicit.excluded == implicit.excluded
        assert explicit.phrases == implicit.phrases
