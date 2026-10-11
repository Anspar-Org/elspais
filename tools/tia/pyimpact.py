"""Python adapter: what a change to a Python file can affect.

Line numbers are never compared across revisions. Both versions of a file
are parsed and compared *structurally*, unit by unit, where a unit is a
function or method (keyed by its qualified name) or a class header. The
impact of a changed unit is expressed in BASELINE coordinates -- the line
range the unit occupied in the baseline file -- because that is the
coordinate system the baseline coverage was recorded in. Inserting or
deleting lines elsewhere in the file therefore cannot misdirect selection.

Each change is classified into one of three impact scopes, from narrowest:

  FUNCTION  the body/arguments of an existing function or method changed:
            tests whose baseline coverage touches the function's baseline
            lines.
  FILE      something new was defined that nothing existing can reach
            except through other changes (a fresh top-level function, a
            fresh method on a base-less class, an added import): tests
            covering any line of the file.
  MODULE    anything evaluated at import time or visible to other modules
            changed (constants, class attributes, decorators, class bases,
            removed/renamed definitions, memoized functions, a file that no
            longer parses): tests covering this module or any module that
            imports it (transitively), plus test files importing them.

A FUNCTION region nobody covered escalates to FILE, and a FILE nobody
covered to MODULE (the selector does that, it owns the coverage).
"""

from __future__ import annotations

import ast
import difflib
import os
from dataclasses import dataclass, field

FUNCTION, FILE, MODULE = "function", "file", "module"
_SCOPE_RANK = {FUNCTION: 0, FILE: 1, MODULE: 2}

_DEFS = (ast.FunctionDef, ast.AsyncFunctionDef)


@dataclass
class Impact:
    scope: str
    detail: str
    lines: tuple[int, int] | None = None  # baseline line range, FUNCTION only
    unit: str | None = None


@dataclass
class Unit:
    key: str
    kind: str  # "function" | "class"
    name: str
    node: ast.AST
    start: int
    end: int
    container: str | None  # enclosing class key, None at module level
    decorators: str
    payload: str  # function: args+returns+body; class: bases+keywords
    decorator_names: tuple[str, ...] = ()


def _dump(node) -> str:
    return ast.dump(node, annotate_fields=False, include_attributes=False)


def _dump_list(nodes) -> str:
    return "[" + ",".join(_dump(n) for n in nodes) + "]"


def _decorator_name(node) -> str:
    if isinstance(node, ast.Call):
        node = node.func
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ""


def collect_units(tree: ast.Module) -> tuple[dict[str, Unit], list[tuple[str, str]]]:
    """Units keyed by qualified name, and the remaining (non-def) statements.

    Statements are returned as (container, dump) so module- and class-level
    code can be compared as a multiset, independent of where it sits.
    A qualified name defined twice (a property setter, a conditional def)
    gets an occurrence suffix (`C.x#1`).
    """
    units: dict[str, Unit] = {}
    stmts: list[tuple[str, str]] = []

    def visit(body, prefix: str, container: str | None) -> None:
        for node in body:
            if isinstance(node, (*_DEFS, ast.ClassDef)):
                key = prefix + node.name
                n = 0
                while (key if n == 0 else f"{key}#{n}") in units:
                    n += 1
                key = key if n == 0 else f"{key}#{n}"
                start = min([node.lineno] + [d.lineno for d in node.decorator_list])
                decorators = _dump_list(node.decorator_list)
                names = tuple(_decorator_name(d) for d in node.decorator_list)
                if isinstance(node, ast.ClassDef):
                    payload = (
                        _dump_list(node.bases)
                        + _dump_list(node.keywords)
                        + _dump_list(getattr(node, "type_params", []))
                    )
                    units[key] = Unit(
                        key,
                        "class",
                        node.name,
                        node,
                        start,
                        node.end_lineno,
                        container,
                        decorators,
                        payload,
                        names,
                    )
                    visit(node.body, key + ".", key)
                else:
                    payload = (
                        type(node).__name__
                        + _dump(node.args)
                        + (_dump(node.returns) if node.returns else "")
                        + _dump_list(getattr(node, "type_params", []))
                        + _dump_list(node.body)
                    )
                    units[key] = Unit(
                        key,
                        "function",
                        node.name,
                        node,
                        start,
                        node.end_lineno,
                        container,
                        decorators,
                        payload,
                        names,
                    )
            else:
                stmts.append((container or "", _dump(node)))

    visit(tree.body, "", None)
    return units, stmts


def string_literals(tree: ast.AST) -> set[str]:
    return {
        n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)
    }


def text_hunks(old: str, new: str) -> list[tuple[int, int, int, int]]:
    """(old_start, old_end, new_start, new_end), 1-based inclusive; an empty
    side has end == start - 1 (a pure insertion/deletion point)."""
    a, b = old.splitlines(), new.splitlines()
    out = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag != "equal":
            out.append((i1 + 1, i2, j1 + 1, j2))
    return out


def outermost_def(units: dict[str, Unit], lo: int, hi: int) -> Unit | None:
    """The outermost function/method whose baseline lines contain [lo, hi]."""
    best = None
    for u in units.values():
        if u.kind == "function" and u.start <= lo and hi <= u.end:
            if best is None or (u.end - u.start) > (best.end - best.start):
                best = u
    return best


@dataclass
class FileAnalysis:
    impacts: list[Impact] = field(default_factory=list)
    hunks: list[tuple[int, int, int, int]] = field(default_factory=list)

    @property
    def scope(self) -> str | None:
        if not self.impacts:
            return None
        return max(self.impacts, key=lambda i: _SCOPE_RANK[i.scope]).scope


def analyze_python_change(
    path: str,
    old: bytes | None,
    new: bytes | None,
    *,
    memoizing: set[str],
    referenced_names: set[str],
) -> FileAnalysis:
    """Classify a change to one production Python file (see module doc)."""
    res = FileAnalysis()
    if old is None:
        # A new module: nothing in the baseline executed it.
        res.impacts.append(Impact(FILE, "new module"))
        return res
    if new is None:
        res.impacts.append(Impact(MODULE, "module deleted; importers break"))
        return res
    old_s = old.decode("utf-8", errors="replace")
    new_s = new.decode("utf-8", errors="replace")
    res.hunks = text_hunks(old_s, new_s)
    try:
        old_tree = ast.parse(old_s, path)
    except SyntaxError:
        res.impacts.append(Impact(MODULE, "baseline version does not parse"))
        return res
    try:
        new_tree = ast.parse(new_s, path)
    except SyntaxError as exc:
        res.impacts.append(Impact(MODULE, f"does not parse (line {exc.lineno}); importers break"))
        return res

    old_units, old_stmts = collect_units(old_tree)
    new_units, new_stmts = collect_units(new_tree)
    is_init = os.path.basename(path) == "__init__.py"

    # Module/class-level statements: a multiset comparison.
    from collections import Counter

    oc, nc = Counter(old_stmts), Counter(new_stmts)
    added = nc - oc
    removed = oc - nc
    if added or removed:
        only_added_imports = not removed and all(
            d.startswith(("Import(", "ImportFrom(")) for (_c, d) in added
        )
        if only_added_imports and not is_init:
            res.impacts.append(Impact(FILE, "import added"))
        else:
            what = sorted({(c or "<module>") for c, _ in list(added) + list(removed)})
            res.impacts.append(
                Impact(MODULE, "module/class-level statements changed in " + ", ".join(what))
            )

    for key, ou in old_units.items():
        nu = new_units.get(key)
        if nu is None or nu.kind != ou.kind:
            res.impacts.append(Impact(MODULE, f"{ou.kind} {key} removed or renamed", unit=key))
            continue
        if ou.decorators != nu.decorators:
            res.impacts.append(Impact(MODULE, f"decorators of {key} changed", unit=key))
            continue
        if ou.payload == nu.payload:
            continue
        if ou.kind == "class":
            res.impacts.append(Impact(MODULE, f"bases of class {key} changed", unit=key))
        elif memoizing & set(ou.decorator_names):
            res.impacts.append(
                Impact(
                    MODULE,
                    f"memoized function {key} changed (first caller only is recorded)",
                    unit=key,
                )
            )
        else:
            outer = outermost_def(old_units, ou.start, ou.end) or ou
            res.impacts.append(
                Impact(FUNCTION, f"{key} changed", lines=(outer.start, outer.end), unit=outer.key)
            )

    for key, nu in new_units.items():
        if key in old_units:
            continue
        container = old_units.get(nu.container) if nu.container else None
        if nu.container and container is None:
            continue  # inside a class that is itself new; the class decides
        fresh = nu.name not in referenced_names and not (
            nu.name.startswith("__") and nu.name.endswith("__")
        )
        if container is not None:
            baseless = not container.node.bases and not container.node.keywords
            if fresh and baseless:
                res.impacts.append(Impact(FILE, f"method {key} added", unit=key))
            else:
                res.impacts.append(
                    Impact(
                        MODULE,
                        f"method {key} added to a class with bases or by a name "
                        "referenced elsewhere (may override or be looked up)",
                        unit=key,
                    )
                )
        elif fresh:
            res.impacts.append(Impact(FILE, f"{nu.kind} {key} added", unit=key))
        else:
            res.impacts.append(
                Impact(
                    MODULE,
                    f"{nu.kind} {key} added under a name referenced as a string "
                    "elsewhere (may be looked up dynamically)",
                    unit=key,
                )
            )

    # Text-only edits (comments, blank lines, formatting) inside a function
    # change no bytecode, but the cost of running that function's tests is
    # small and some tests read sources as text. Module-level text edits are
    # left to the data-read records.
    flagged = {i.unit for i in res.impacts if i.scope == FUNCTION}
    for o1, o2, _n1, _n2 in res.hunks:
        lo, hi = (o1, o2) if o2 >= o1 else (o1 - 1, o1)  # insertion: both neighbours
        u = outermost_def(old_units, max(lo, 1), max(hi, 1))
        if u is not None and u.key not in flagged:
            flagged.add(u.key)
            res.impacts.append(
                Impact(FUNCTION, f"{u.key}: text-only edit", lines=(u.start, u.end), unit=u.key)
            )
    return res


# -- import graph ----------------------------------------------------------


def module_name(path: str, import_roots: list[str]) -> str | None:
    """`src/elspais/a/b.py` -> `elspais.a.b` for the first matching root."""
    if not path.endswith(".py"):
        return None
    for root in import_roots:
        root = root.strip("/")
        if root in ("", "."):
            rel = path
        elif path.startswith(root + "/"):
            rel = path[len(root) + 1 :]
        else:
            continue
        parts = rel[:-3].split("/")
        if parts[-1] == "__init__":
            parts = parts[:-1]
        if parts and all(p.isidentifier() for p in parts):
            return ".".join(parts)
    return None


def imported_modules(tree: ast.AST, this_module: str, is_package: bool) -> set[str]:
    """Every module an import statement anywhere in the file names (including
    the candidate submodule `pkg.name` of `from pkg import name`)."""
    out: set[str] = set()
    pkg_parts = this_module.split(".") if is_package else this_module.split(".")[:-1]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base_parts = (
                    pkg_parts[: len(pkg_parts) - (node.level - 1)] if node.level > 1 else pkg_parts
                )
                base = ".".join(base_parts + ([node.module] if node.module else []))
            else:
                base = node.module or ""
            if base:
                out.add(base)
                for alias in node.names:
                    if alias.name != "*":
                        out.add(f"{base}.{alias.name}")
    # importing a.b.c executes a and a.b too
    closed = set()
    for m in out:
        parts = m.split(".")
        for i in range(1, len(parts) + 1):
            closed.add(".".join(parts[:i]))
    return closed


@dataclass
class ImportGraph:
    path_of: dict[str, str]  # module -> repo-relative path
    module_of: dict[str, str]  # path -> module
    importers: dict[str, set[str]]  # module -> modules importing it
    toplevel_importers: dict[str, set[str]]  # same, module-level imports only

    def reverse_closure(self, modules: set[str], *, toplevel_only: bool = False) -> set[str]:
        graph = self.toplevel_importers if toplevel_only else self.importers
        seen = set(modules)
        stack = list(modules)
        while stack:
            m = stack.pop()
            for imp in graph.get(m, ()):
                if imp not in seen:
                    seen.add(imp)
                    stack.append(imp)
        return seen


def build_import_graph(root: str, py_files: list[str], import_roots: list[str]) -> ImportGraph:
    path_of: dict[str, str] = {}
    module_of: dict[str, str] = {}
    for p in py_files:
        m = module_name(p, import_roots)
        if m and m not in path_of:  # the first import root wins, as on sys.path
            path_of[m] = p
            module_of[p] = m
    importers: dict[str, set[str]] = {}
    toplevel: dict[str, set[str]] = {}
    for p, m in module_of.items():
        try:
            with open(os.path.join(root, p), "rb") as fh:
                tree = ast.parse(fh.read(), p)
        except (OSError, SyntaxError, ValueError):
            continue
        is_pkg = p.endswith("__init__.py")
        for dep in imported_modules(tree, m, is_pkg):
            if dep in path_of and dep != m:
                importers.setdefault(dep, set()).add(m)
        top = ast.Module(
            body=[
                s for s in tree.body if isinstance(s, (ast.Import, ast.ImportFrom, ast.If, ast.Try))
            ],
            type_ignores=[],
        )
        for dep in imported_modules(top, m, is_pkg):
            if dep in path_of and dep != m:
                toplevel.setdefault(dep, set()).add(m)
    return ImportGraph(path_of, module_of, importers, toplevel)
