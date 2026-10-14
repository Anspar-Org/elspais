"""Declarations and tests read from a tree-sitter syntax tree.

The ``ast`` extra installs tree-sitter and one grammar package per language
named in ``_GRAMMARS``. For a file in one of those languages this module
reads where each function, class and test begins and ends, and the
descriptions the test framework builds a test's name from. ``prescan.py``
turns a reading into the line context every pre-scan returns, so what a
citation binds to is decided there and nowhere here. A comment marker is
never read here either: which marker introduces a citation is decided by
``patterns.comment_pattern_for_path``.

Python is read with ``ast`` and Dart with ``dart_lexer``; neither has an
entry here.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

# The extra that installs every library this module imports.
EXTRA = "ast"

# extension -> (distribution, module, the module's function returning the
# grammar, family).  The family selects the node types and test conventions.
_GRAMMARS: dict[str, tuple[str, str, str, str]] = {
    ".js": ("tree-sitter-javascript", "tree_sitter_javascript", "language", "js"),
    ".jsx": ("tree-sitter-javascript", "tree_sitter_javascript", "language", "js"),
    ".mjs": ("tree-sitter-javascript", "tree_sitter_javascript", "language", "js"),
    ".cjs": ("tree-sitter-javascript", "tree_sitter_javascript", "language", "js"),
    ".ts": ("tree-sitter-typescript", "tree_sitter_typescript", "language_typescript", "js"),
    ".mts": ("tree-sitter-typescript", "tree_sitter_typescript", "language_typescript", "js"),
    ".cts": ("tree-sitter-typescript", "tree_sitter_typescript", "language_typescript", "js"),
    ".tsx": ("tree-sitter-typescript", "tree_sitter_typescript", "language_tsx", "js"),
    ".go": ("tree-sitter-go", "tree_sitter_go", "language", "go"),
    ".java": ("tree-sitter-java", "tree_sitter_java", "language", "java"),
    ".kt": ("tree-sitter-kotlin", "tree_sitter_kotlin", "language", "kotlin"),
    ".kts": ("tree-sitter-kotlin", "tree_sitter_kotlin", "language", "kotlin"),
    ".rs": ("tree-sitter-rust", "tree_sitter_rust", "language", "rust"),
    ".cs": ("tree-sitter-c-sharp", "tree_sitter_c_sharp", "language", "csharp"),
}

# Node types holding a function body, per family.
_FUNCTIONS: dict[str, frozenset[str]] = {
    "js": frozenset(
        {"function_declaration", "generator_function_declaration", "method_definition"}
    ),
    "go": frozenset({"function_declaration", "method_declaration"}),
    "java": frozenset({"method_declaration", "constructor_declaration"}),
    "kotlin": frozenset({"function_declaration", "secondary_constructor"}),
    "rust": frozenset({"function_item"}),
    "csharp": frozenset(
        {"method_declaration", "constructor_declaration", "local_function_statement"}
    ),
}

# Node types that enclose functions and give them a class name, per family.
_CLASSES: dict[str, frozenset[str]] = {
    "js": frozenset({"class_declaration", "abstract_class_declaration", "class"}),
    "go": frozenset(),
    "java": frozenset(
        {"class_declaration", "interface_declaration", "enum_declaration", "record_declaration"}
    ),
    "kotlin": frozenset({"class_declaration", "object_declaration"}),
    "rust": frozenset({"impl_item", "trait_item", "mod_item"}),
    "csharp": frozenset(
        {
            "class_declaration",
            "struct_declaration",
            "record_declaration",
            "interface_declaration",
        }
    ),
}

# A variable whose value is one of these is a function declared by assignment.
_JS_FUNCTION_VALUES = frozenset({"arrow_function", "function_expression", "function"})

# Lines written above a declaration that belong to it: an attribute or a
# decorator the grammar places beside the declaration instead of inside it.
_LEADING_SIBLINGS = frozenset({"attribute_item", "decorator"})

# The callee a JavaScript test framework names a test or a group with.
_JS_TEST_CALLS = frozenset({"it", "test", "fit", "xit"})
_JS_GROUP_CALLS = frozenset({"describe", "fdescribe", "xdescribe", "context", "suite"})

# The annotation or attribute marking a test method, by its last name segment.
_TEST_ANNOTATIONS: dict[str, frozenset[str]] = {
    "java": frozenset({"Test", "ParameterizedTest", "RepeatedTest", "TestFactory", "TestTemplate"}),
    "kotlin": frozenset(
        {"Test", "ParameterizedTest", "RepeatedTest", "TestFactory", "TestTemplate"}
    ),
    "rust": frozenset({"test", "rstest"}),
    "csharp": frozenset(
        {"Test", "TestCase", "TestCaseSource", "Fact", "Theory", "TestMethod", "DataTestMethod"}
    ),
}

# The prefixes ``go test`` runs a function for.
_GO_TEST_PREFIXES = ("Test", "Benchmark", "Fuzz", "Example")


@dataclass(frozen=True)
class SyntaxReading:
    """What one tree-sitter parse of a source yields for the pre-scans.

    Every line is 1-based.  A start is the first line of the declaration,
    including the attributes, annotations or decorators written above it.
    """

    # (start, end, name, enclosing class) for every function, in pre-order.
    functions: tuple[tuple[int, int, str, str | None], ...] = ()
    # (start, end, name) for every class, in pre-order.
    classes: tuple[tuple[int, int, str], ...] = ()
    # (start, end, name, enclosing group name) for every test, in pre-order.
    # The name is None where the framework names a test by descriptions.
    tests: tuple[tuple[int, int, str | None, str | None], ...] = ()
    # (start, end, name) for every group of tests, in pre-order.
    groups: tuple[tuple[int, int, str | None], ...] = ()
    # Each test's full name (REQ-d00284-G), by its start line, where the
    # framework names tests by descriptions and every description is literal.
    names: dict[int, str] | None = None
    # Every line of a class's header: from its first attribute down to the
    # line its body opens on.
    class_header_lines: frozenset[int] = frozenset()

    @property
    def declaration_starts(self) -> list[int]:
        return sorted({start for start, _end, _name, _class in self.functions})


def handles(path: str) -> bool:
    """Whether a file at *path* is read through this module when the extra is installed."""
    return Path(path).suffix.lower() in _GRAMMARS


def names_tests_by_description(path: str) -> bool:
    """Whether the framework of a test file at *path* names a test by descriptions."""
    grammar = _GRAMMARS.get(Path(path).suffix.lower())
    return grammar is not None and grammar[3] == "js"


def available() -> bool:
    """Whether the extra is installed: tree-sitter and every grammar package."""
    return all(v is not None for _dist, v in reader_identity())


def reader_identity() -> tuple[tuple[str, str | None], ...]:
    """Each library a reading depends on, with its installed version or None.

    A reading differs with the libraries that made it, so the parse cache
    keys a reading by this.  It asks the installed metadata alone and imports
    nothing.
    """
    dists = ["tree-sitter", *sorted({g[0] for g in _GRAMMARS.values()})]
    identity = []
    for dist in dists:
        try:
            identity.append((dist, version(dist)))
        except PackageNotFoundError:
            identity.append((dist, None))
    return tuple(identity)


_PARSERS: dict[str, object] = {}


def _parser(path: str):
    """The parser for *path*'s language; raises ImportError without the extra."""
    dist, module, attribute, _family = _GRAMMARS[Path(path).suffix.lower()]
    key = f"{module}.{attribute}"
    parser = _PARSERS.get(key)
    if parser is None:
        import tree_sitter

        grammar = getattr(import_module(module), attribute)()
        parser = tree_sitter.Parser(tree_sitter.Language(grammar))
        _PARSERS[key] = parser
    return parser


# Implements: REQ-d00332-A, REQ-d00254-D
def read(path: str, source: str) -> SyntaxReading | None:
    """Parse *source* once and read its declarations and tests.

    Returns None where *path*'s language has no grammar here, or where the
    extra is not installed.  A source holding a syntax error is still read:
    tree-sitter recovers around the error, and every declaration outside it
    keeps its extent.
    """
    if not handles(path):
        return None
    try:
        parser = _parser(path)
    except ImportError:
        return None
    family = _GRAMMARS[Path(path).suffix.lower()][3]
    data = source.encode("utf-8")
    tree = parser.parse(data)
    return _Walk(family, data).run(tree.root_node)


class _Walk:
    """One pre-order walk of a tree, collecting a ``SyntaxReading``."""

    def __init__(self, family: str, data: bytes) -> None:
        self.family = family
        self.data = data
        self.functions: list[tuple[int, int, str, str | None]] = []
        self.classes: list[tuple[int, int, str]] = []
        self.tests: list[tuple[int, int, str | None, str | None]] = []
        self.groups: list[tuple[int, int, str | None]] = []
        self.names: dict[int, str] | None = {} if family == "js" else None
        self.header_lines: set[int] = set()

    def text(self, node) -> str:
        return self.data[node.start_byte : node.end_byte].decode("utf-8", "replace")

    def start(self, node) -> int:
        """The first line of *node*, including the attributes written above it."""
        first = node
        sibling = node.prev_named_sibling
        while sibling is not None and sibling.type in _LEADING_SIBLINGS:
            first = sibling
            sibling = sibling.prev_named_sibling
        return first.start_point[0] + 1

    @staticmethod
    def end(node) -> int:
        return node.end_point[0] + 1

    def run(self, root) -> SyntaxReading:
        # (node, enclosing class, enclosing group names outermost first; None
        #  where a description is not literal)
        stack: list[tuple[object, str | None, tuple[str | None, ...]]] = [(root, None, ())]
        while stack:
            node, class_name, groups = stack.pop()
            class_name, groups = self.visit(node, class_name, groups)
            stack.extend((child, class_name, groups) for child in reversed(node.named_children))
        return SyntaxReading(
            functions=tuple(self.functions),
            classes=tuple(self.classes),
            tests=tuple(self.tests),
            groups=tuple(self.groups),
            names=self.names,
            class_header_lines=frozenset(self.header_lines),
        )

    def visit(self, node, class_name, groups):
        """Record *node*; return the class and groups its children are inside."""
        kind = node.type
        if kind in _CLASSES[self.family]:
            name = self.declared_name(node)
            if name is not None:
                self.classes.append((self.start(node), self.end(node), name))
                self.header_lines.update(range(self.start(node), self.body_line(node) + 1))
                class_name = name
                if self.family != "js":
                    groups = (*groups, name)
                    if self.holds_test(node):
                        self.groups.append((self.start(node), self.end(node), name))
            return class_name, groups
        if kind in _FUNCTIONS[self.family]:
            name = self.declared_name(node)
            if name is not None:
                start, end = self.start(node), self.end(node)
                self.functions.append((start, end, name, class_name))
                if self.is_test(node, name):
                    self.tests.append((start, end, name, groups[-1] if groups else None))
            return class_name, groups
        if self.family == "js":
            if kind == "variable_declarator":
                self.assigned_function(node, class_name)
            elif kind == "call_expression":
                groups = self.js_call(node, groups)
        return class_name, groups

    @staticmethod
    def body_line(node) -> int:
        """The line a class's body opens on, or its first line where it has none."""
        body = node.child_by_field_name("body")
        if body is None:
            body = next(
                (
                    c
                    for c in node.named_children
                    if c.type.endswith("body") or c.type == "declaration_list"
                ),
                None,
            )
        return (body if body is not None else node).start_point[0] + 1

    def declared_name(self, node) -> str | None:
        """The identifier a declaration introduces, or None where it has none."""
        if self.family == "rust" and node.type == "impl_item":
            target = node.child_by_field_name("type")
            return self.text(target) if target is not None else None
        named = node.child_by_field_name("name")
        if named is None:
            named = next(
                (
                    c
                    for c in node.named_children
                    if c.type in ("identifier", "type_identifier", "simple_identifier")
                ),
                None,
            )
        return self.text(named) if named is not None else None

    def assigned_function(self, node, class_name) -> None:
        """``const f = () => ...`` declares ``f``; its extent is the whole statement."""
        value = node.child_by_field_name("value")
        name = node.child_by_field_name("name")
        if value is None or name is None or value.type not in _JS_FUNCTION_VALUES:
            return
        statement = node.parent if node.parent is not None else node
        self.functions.append(
            (self.start(statement), self.end(statement), self.text(name), class_name)
        )

    # -- tests -----------------------------------------------------------

    def is_test(self, node, name: str) -> bool:
        if self.family == "go":
            return node.type == "function_declaration" and name.startswith(_GO_TEST_PREFIXES)
        marks = _TEST_ANNOTATIONS.get(self.family)
        return marks is not None and bool(marks & self.annotations(node))

    def annotations(self, node) -> set[str]:
        """The last name segment of each annotation or attribute on *node*."""
        found: set[str] = set()
        holders = [node]
        sibling = node.prev_named_sibling
        while sibling is not None and sibling.type in _LEADING_SIBLINGS:
            holders.append(sibling)
            sibling = sibling.prev_named_sibling
        for holder in holders:
            for child in holder.named_children:
                if child.type in ("modifiers", "attribute_list"):
                    found.update(self.mark_names(child))
            if holder.type in _LEADING_SIBLINGS:
                found.update(self.mark_names(holder))
        return found

    def mark_names(self, node) -> set[str]:
        names: set[str] = set()
        for child in node.named_children:
            if child.type in ("marker_annotation", "annotation", "attribute"):
                names.add(self._last_segment(child))
            elif child.type in ("modifiers", "attribute_list"):
                names.update(self.mark_names(child))
        return names

    def _last_segment(self, mark) -> str:
        text = self.text(mark).lstrip("@#[").split("(")[0].rstrip("]").strip()
        segment = text.replace("::", ".").split(".")[-1]
        return segment[: -len("Attribute")] if segment.endswith("Attribute") else segment

    def holds_test(self, node) -> bool:
        """Whether a test is declared anywhere inside *node*."""
        stack = list(node.named_children)
        while stack:
            child = stack.pop()
            if child.type in _FUNCTIONS[self.family]:
                name = self.declared_name(child)
                if name is not None and self.is_test(child, name):
                    return True
            stack.extend(child.named_children)
        return False

    def js_call(self, node, groups):
        """Record a ``describe``/``it``/``test`` call; return the groups inside it."""
        parent = node.parent
        if parent is not None and parent.type == "call_expression":
            if parent.child_by_field_name("function") == node:
                # ``test.each(table)`` is the callee of the call naming the test.
                return groups
        callee = self._callee_root(node.child_by_field_name("function"))
        if callee not in _JS_TEST_CALLS and callee not in _JS_GROUP_CALLS:
            return groups
        description = self._description(node)
        start, end = self.start(node), self.end(node)
        if callee in _JS_GROUP_CALLS:
            if self._holds_js_test(node):
                self.groups.append((start, end, description))
            return (*groups, description)
        self.tests.append((start, end, None, None))
        # Implements: REQ-d00284-G+H
        parts = (*groups, description)
        if self.names is not None and all(part is not None for part in parts):
            self.names[start] = " ".join(parts)  # type: ignore[arg-type]
        return groups

    def _callee_root(self, node) -> str | None:
        while node is not None:
            if node.type == "identifier":
                return self.text(node)
            if node.type == "member_expression":
                node = node.child_by_field_name("object")
            elif node.type == "call_expression":
                node = node.child_by_field_name("function")
            else:
                return None
        return None

    def _description(self, call) -> str | None:
        """The literal first argument of a test or group call, or None."""
        arguments = call.child_by_field_name("arguments")
        if arguments is None or not arguments.named_children:
            return None
        first = arguments.named_children[0]
        if first.type == "string":
            return "".join(
                self.text(c) for c in first.named_children if c.type == "string_fragment"
            )
        if first.type == "template_string" and not any(
            c.type == "template_substitution" for c in first.named_children
        ):
            return self.text(first)[1:-1]
        return None

    def _holds_js_test(self, call) -> bool:
        stack = list(call.named_children)
        while stack:
            child = stack.pop()
            if child.type == "call_expression":
                parent = child.parent
                is_callee = (
                    parent is not None
                    and parent.type == "call_expression"
                    and parent.child_by_field_name("function") == child
                )
                if not is_callee and (
                    self._callee_root(child.child_by_field_name("function")) in _JS_TEST_CALLS
                ):
                    return True
            stack.extend(child.named_children)
        return False
