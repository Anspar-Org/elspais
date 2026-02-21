"""Multi-term search engine with scoring and OR support.

Implements: REQ-d00061-F, REQ-d00061-G, REQ-d00061-H, REQ-d00061-I,
            REQ-d00061-J, REQ-d00061-K, REQ-d00061-L, REQ-d00061-M
"""

from __future__ import annotations

from dataclasses import dataclass

from elspais.graph.GraphNode import GraphNode


@dataclass(frozen=True)
class SearchTerm:
    """A single search term with modifiers."""

    text: str  # lowercased
    exact: bool  # True for =prefix (keyword set match)
    negated: bool  # True for -prefix (exclusion)


@dataclass(frozen=True)
class ParsedQuery:
    """Parsed query structure: AND of OR-groups, with exclusions and phrases.

    Each element of and_groups is a tuple of SearchTerms joined by OR.
    All and_groups must match (AND logic).
    All phrases must match as contiguous substrings.
    All excluded terms must NOT match.
    """

    and_groups: tuple[tuple[SearchTerm, ...], ...]  # AND of OR-groups
    excluded: tuple[SearchTerm, ...]  # NOT terms
    phrases: tuple[str, ...]  # AND'd exact phrases

    @property
    def is_empty(self) -> bool:
        return not self.and_groups and not self.excluded and not self.phrases


# -- Field weights for scoring --
_WEIGHT_ID = 100
_WEIGHT_TITLE = 50
_WEIGHT_KEYWORD_EXACT = 40
_WEIGHT_KEYWORD_SUBSTRING = 25
_WEIGHT_BODY = 10


def parse_query(raw: str) -> ParsedQuery:
    """Parse a raw query string into a structured ParsedQuery.

    Implements: REQ-d00061-F, REQ-d00061-G, REQ-d00061-H, REQ-d00061-I,
                REQ-d00061-J, REQ-d00061-K, REQ-d00061-M

    Syntax:
        term          -> substring match (default)
        =term         -> exact keyword set match
        "phrase"      -> exact phrase substring
        -term         -> exclude nodes containing term
        OR            -> disjunction between terms
        AND / (space) -> conjunction (implicit)
        (...)         -> grouping for explicit precedence
    """
    tokens = _tokenize(raw)
    return _build_groups(tokens)


def score_node(
    node: GraphNode,
    parsed: ParsedQuery,
    field: str = "all",
) -> float:
    """Score a node against a parsed query.

    Implements: REQ-d00061-L, REQ-d00061-M

    Returns 0 if any exclusion matches, any phrase is missing,
    or any AND-group has no matching term.
    Otherwise returns the sum of best-match scores per AND-group.
    """
    # Exclusion check first
    for term in parsed.excluded:
        if _term_matches_any_field(node, term, field):
            return 0.0

    # Phrase check
    for phrase in parsed.phrases:
        if not _phrase_matches(node, phrase, field):
            return 0.0

    # Score AND-groups
    if not parsed.and_groups:
        # Query has only phrases/exclusions; if we got here, they matched
        return 1.0 if parsed.phrases else 0.0

    total = 0.0
    for or_group in parsed.and_groups:
        best = _best_or_group_score(node, or_group, field)
        if best <= 0.0:
            return 0.0  # AND-group not satisfied
        total += best

    return total


def matches_node(
    node: GraphNode,
    parsed: ParsedQuery,
    field: str = "all",
) -> bool:
    """Check if a node matches the parsed query.

    Thin wrapper around score_node().
    """
    return score_node(node, parsed, field) > 0.0


# ---------------------------------------------------------------------------
# Field extraction
# ---------------------------------------------------------------------------


def _get_field_text(node: GraphNode, field_name: str) -> str:
    """Extract text for a single field from a node."""
    if field_name == "id":
        return node.id
    if field_name == "title":
        return node.get_label() or ""
    if field_name == "body":
        return node.get_field("body_text", "")
    if field_name == "keywords":
        keywords = node.get_field("keywords", [])
        return " ".join(keywords) if keywords else ""
    return ""


def _get_keywords_list(node: GraphNode) -> list[str]:
    """Get the keywords list from a node."""
    return node.get_field("keywords", []) or []


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

_TOKEN_LPAREN = "LPAREN"
_TOKEN_RPAREN = "RPAREN"
_TOKEN_OR = "OR"
_TOKEN_AND = "AND"
_TOKEN_PHRASE = "PHRASE"
_TOKEN_TERM = "TERM"


@dataclass
class _Token:
    kind: str
    value: str = ""


def _tokenize(raw: str) -> list[_Token]:
    """Stage 1: Walk character-by-character to produce tokens."""
    tokens: list[_Token] = []
    i = 0
    n = len(raw)

    while i < n:
        ch = raw[i]

        # Skip whitespace (but it acts as implicit AND between tokens)
        if ch in (" ", "\t"):
            i += 1
            continue

        # Parentheses
        if ch == "(":
            tokens.append(_Token(_TOKEN_LPAREN))
            i += 1
            continue
        if ch == ")":
            tokens.append(_Token(_TOKEN_RPAREN))
            i += 1
            continue

        # Quoted phrase
        if ch == '"':
            j = raw.find('"', i + 1)
            if j == -1:
                # Unclosed quote - treat rest as phrase
                phrase_text = raw[i + 1 :]
                i = n
            else:
                phrase_text = raw[i + 1 : j]
                i = j + 1
            if phrase_text:
                tokens.append(_Token(_TOKEN_PHRASE, phrase_text.lower()))
            continue

        # Word token (may be OR, AND, -term, =term, or plain term)
        j = i
        while j < n and raw[j] not in (" ", "\t", "(", ")", '"'):
            j += 1
        word = raw[i:j]
        i = j

        if word == "OR":
            tokens.append(_Token(_TOKEN_OR))
        elif word == "AND":
            tokens.append(_Token(_TOKEN_AND))
        else:
            tokens.append(_Token(_TOKEN_TERM, word))

    return tokens


# ---------------------------------------------------------------------------
# Group builder
# ---------------------------------------------------------------------------


def _build_groups(tokens: list[_Token]) -> ParsedQuery:
    """Stage 2: Build ParsedQuery from token list.

    Precedence: Parentheses > OR > AND (implicit space = AND).
    """
    and_groups: list[tuple[SearchTerm, ...]] = []
    excluded: list[SearchTerm] = []
    phrases: list[str] = []

    # Flatten into a sequence of "items" where each item is either
    # a SearchTerm, a phrase, or an OR-group (list of SearchTerms).
    # Then combine adjacent non-OR items as AND-groups.

    # First, resolve parenthesized groups into sub-lists
    items = _resolve_parens(tokens)

    # Now process: items is a flat list of tokens (with parens resolved to sub-lists)
    # Build OR-groups: terms linked by OR become one group
    current_or: list[SearchTerm] = []
    pending_or = False

    for item in items:
        if isinstance(item, str):
            # Phrase
            phrases.append(item)
            # If we had a pending OR group, flush it
            if current_or:
                and_groups.append(tuple(current_or))
                current_or = []
            pending_or = False
        elif isinstance(item, list):
            # Resolved paren group - it's already an OR-group of SearchTerms
            if current_or:
                and_groups.append(tuple(current_or))
                current_or = []
            and_groups.append(tuple(item))
            pending_or = False
        elif isinstance(item, _Token) and item.kind == _TOKEN_OR:
            pending_or = True
        elif isinstance(item, _Token) and item.kind == _TOKEN_AND:
            # Explicit AND - flush current OR group
            if current_or:
                and_groups.append(tuple(current_or))
                current_or = []
            pending_or = False
        elif isinstance(item, SearchTerm):
            if item.negated:
                excluded.append(item)
            elif pending_or and current_or:
                current_or.append(item)
                pending_or = False
            else:
                if current_or:
                    and_groups.append(tuple(current_or))
                current_or = [item]
                pending_or = False

    if current_or:
        and_groups.append(tuple(current_or))

    return ParsedQuery(
        and_groups=tuple(and_groups),
        excluded=tuple(excluded),
        phrases=tuple(phrases),
    )


def _resolve_parens(tokens: list[_Token]) -> list:
    """Resolve parenthesized groups into sub-lists of SearchTerms.

    Returns a mixed list of:
    - SearchTerm (for plain terms)
    - str (for phrases)
    - list[SearchTerm] (for parenthesized OR-groups)
    - _Token (for OR/AND operators)
    """
    result: list = []
    i = 0
    n = len(tokens)

    while i < n:
        tok = tokens[i]

        if tok.kind == _TOKEN_LPAREN:
            # Collect tokens until matching RPAREN
            depth = 1
            j = i + 1
            while j < n and depth > 0:
                if tokens[j].kind == _TOKEN_LPAREN:
                    depth += 1
                elif tokens[j].kind == _TOKEN_RPAREN:
                    depth -= 1
                j += 1
            # tokens[i+1:j-1] are the contents of the parens
            inner_tokens = tokens[i + 1 : j - 1]
            # Parse inner as OR-group: collect all terms, ignore AND
            or_terms = _parse_paren_group(inner_tokens)
            if or_terms:
                result.append(or_terms)
            i = j
        elif tok.kind == _TOKEN_RPAREN:
            # Stray rparen, skip
            i += 1
        elif tok.kind == _TOKEN_PHRASE:
            result.append(tok.value)  # str
            i += 1
        elif tok.kind in (_TOKEN_OR, _TOKEN_AND):
            result.append(tok)
            i += 1
        elif tok.kind == _TOKEN_TERM:
            result.append(_make_search_term(tok.value))
            i += 1
        else:
            i += 1

    return result


def _parse_paren_group(tokens: list[_Token]) -> list[SearchTerm]:
    """Parse tokens inside parentheses into an OR-group of SearchTerms.

    Inside parens, OR is the primary operator. All terms are collected
    into a single OR-group.
    """
    terms: list[SearchTerm] = []
    for tok in tokens:
        if tok.kind == _TOKEN_TERM:
            term = _make_search_term(tok.value)
            if not term.negated:
                terms.append(term)
        # OR, AND tokens are just separators inside parens
    return terms


def _make_search_term(word: str) -> SearchTerm:
    """Create a SearchTerm from a raw word, handling - and = prefixes."""
    if word.startswith("-") and len(word) > 1:
        return SearchTerm(text=word[1:].lower(), exact=False, negated=True)
    if word.startswith("=") and len(word) > 1:
        return SearchTerm(text=word[1:].lower(), exact=True, negated=False)
    return SearchTerm(text=word.lower(), exact=False, negated=False)


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------


def _term_matches_any_field(
    node: GraphNode,
    term: SearchTerm,
    field: str,
) -> bool:
    """Check if a term matches any of the specified fields."""
    fields = _fields_for(field)
    for f in fields:
        if f == "keywords":
            if _term_matches_keywords(node, term):
                return True
        else:
            text = _get_field_text(node, f).lower()
            if text and term.text in text:
                return True
    return False


def _term_matches_keywords(node: GraphNode, term: SearchTerm) -> bool:
    """Check if a term matches any keyword."""
    keywords = _get_keywords_list(node)
    for kw in keywords:
        kw_lower = kw.lower()
        if term.exact:
            if term.text == kw_lower:
                return True
        else:
            if term.text in kw_lower:
                return True
    return False


def _phrase_matches(node: GraphNode, phrase: str, field: str) -> bool:
    """Check if an exact phrase matches in any specified field."""
    fields = _fields_for(field)
    phrase_lower = phrase  # Already lowered during tokenization
    for f in fields:
        if f == "keywords":
            # Phrases don't match against keyword lists individually,
            # but match against concatenated keywords
            keywords = _get_keywords_list(node)
            text = " ".join(kw.lower() for kw in keywords)
        else:
            text = _get_field_text(node, f).lower()
        if text and phrase_lower in text:
            return True
    return False


def _best_or_group_score(
    node: GraphNode,
    or_group: tuple[SearchTerm, ...],
    field: str,
) -> float:
    """Find the best score among terms in an OR-group."""
    best = 0.0
    for term in or_group:
        s = _score_term(node, term, field)
        if s > best:
            best = s
    return best


def _score_term(node: GraphNode, term: SearchTerm, field: str) -> float:
    """Score a single term against a node's fields."""
    best = 0.0
    fields = _fields_for(field)

    for f in fields:
        if f == "id":
            text = node.id.lower()
            if text and term.text in text:
                best = max(best, _WEIGHT_ID)
        elif f == "title":
            text = (node.get_label() or "").lower()
            if text and term.text in text:
                best = max(best, _WEIGHT_TITLE)
        elif f == "keywords":
            keywords = _get_keywords_list(node)
            for kw in keywords:
                kw_lower = kw.lower()
                if term.exact:
                    if term.text == kw_lower:
                        best = max(best, _WEIGHT_KEYWORD_EXACT)
                else:
                    if term.text in kw_lower:
                        best = max(best, _WEIGHT_KEYWORD_SUBSTRING)
        elif f == "body":
            text = _get_field_text(node, "body").lower()
            if text and term.text in text:
                best = max(best, _WEIGHT_BODY)

    return best


def _fields_for(field: str) -> tuple[str, ...]:
    """Return the list of field names to search."""
    if field == "all":
        return ("id", "title", "keywords", "body")
    return (field,)
