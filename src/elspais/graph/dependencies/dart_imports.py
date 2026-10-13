# Implements: REQ-d00333-C
"""The ``imports:dart`` dependency source: the files a Dart test file imports.

Each unit is a Dart test file. Its evidence is every file of the repository
that the ``import``, ``export`` and ``part`` directives reach from it,
followed transitively, together with the files the Dart and Flutter test
runners load by rule: the nearest ``flutter_test_config.dart`` and the build
hooks of the repository's packages. Every branch of a conditional import is
followed, because the branch the compiler takes depends on the platform the
test runs on.

A ``package:`` URI is resolved the way the compiler resolves it: through the
one package configuration of the program, the ``.dart_tool/package_config.json``
that lists the package holding the test file. A package in the pub cache or
the Flutter SDK is part of the environment, wherever the cache lies:
``pubspec.lock`` pins the one, and the target's environment probe the other,
so a target declaring no probe that affects retention gets no evidence. Such
a package is still read, because an override or a pub workspace can place a
package it imports in the repository; only the repository files reached
through it are evidence.

The source reads; it runs nothing. Whatever it cannot be sure of leaves the
units it reaches without evidence, so they execute, and the reason names the
cause:

- a test file with no ``pubspec.yaml`` above it, or whose package no package
  configuration lists;
- a package configuration that does not read, that is older than a
  ``pubspec.yaml``, ``pubspec.lock`` or ``pubspec_overrides.yaml`` it
  depends on (the test runner then resolves the packages again), or that
  places a package outside the repository, the pub cache and the Flutter SDK;
- a file, in the repository or the environment, that cannot be read, a
  directive that cannot be read, and a URI that names an unlisted package or
  a scheme the source does not follow.

Only the directives a file opens with are read: Dart allows none after the
first declaration. Comments and strings are skipped through
:mod:`elspais.graph.parsers.dart_lexer`, with the comment marker the one
association of languages and markers gives ``.dart``.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel

from elspais.graph.dependencies import (
    Evidence,
    NoSettings,
    Observation,
    ObservesFrame,
    SourceFailed,
    SourceRequest,
)

_IDENT = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")
_CONFIG = os.path.join(".dart_tool", "package_config.json")
_PUB_GET = "run `dart pub get` or `flutter pub get`"


@dataclass(frozen=True)
class Directive:
    """One ``import``, ``export``, ``part`` or ``part of`` directive.

    ``uris`` holds every URI the directive names, each branch of a
    conditional one included. A ``part of`` naming its library by a dotted
    name holds none.
    """

    keyword: str
    uris: tuple[str, ...]
    line: int


class DirectivesUnreadable(ValueError):
    """The directives of a file do not read. ``line`` is where, ``why`` says why."""

    def __init__(self, line: int, why: str) -> None:
        super().__init__(f"line {line}: {why}")
        self.line = line
        self.why = why


class _Cause(str):
    """A reason that names its own cause, so it is stated without the file that met it."""


class _Reader:
    """Reads the directives at the start of one Dart file."""

    def __init__(self, text: str, marker: str) -> None:
        self.text = text
        self.marker = marker
        self.i = 1 if text.startswith("﻿") else 0
        if text.startswith("#!", self.i):
            line_end = text.find("\n", self.i)
            self.i = len(text) if line_end < 0 else line_end + 1

    def line(self, offset: int | None = None) -> int:
        return self.text.count("\n", 0, self.i if offset is None else offset) + 1

    def fail(self, why: str, offset: int | None = None) -> DirectivesUnreadable:
        return DirectivesUnreadable(self.line(offset), why)

    def skip(self) -> None:
        from elspais.graph.parsers.dart_lexer import DartLexError, skip_trivia

        try:
            self.i = skip_trivia(self.text, self.i, self.marker)
        except DartLexError as exc:
            raise self.fail(exc.why, exc.offset) from exc

    def peek(self) -> str | None:
        self.skip()
        match = _IDENT.match(self.text, self.i)
        return match.group(0) if match else None

    def ident(self) -> str | None:
        word = self.peek()
        if word is not None:
            self.i += len(word)
        return word

    def punct(self, mark: str) -> bool:
        self.skip()
        if self.text.startswith(mark, self.i):
            self.i += len(mark)
            return True
        return False

    def balanced(self) -> None:
        from elspais.graph.parsers.dart_lexer import DartLexError, skip_balanced

        try:
            self.i = skip_balanced(self.text, self.i, self.marker)
        except DartLexError as exc:
            raise self.fail(exc.why, exc.offset) from exc

    def at_string(self) -> bool:
        from elspais.graph.parsers.dart_lexer import opens_string

        self.skip()
        return opens_string(self.text, self.i)

    def uri(self, keyword: str) -> str:
        from elspais.graph.parsers.dart_lexer import dart_string

        if not self.at_string():
            raise self.fail(f"{keyword} is not followed by a string literal")
        start = self.i
        read = dart_string(self.text, start)
        if read is None:
            raise self.fail("a URI that interpolates a value or does not close")
        value, self.i = read
        if "\\" in self.text[start : self.i]:
            raise self.fail("a URI written with an escape", start)
        return value

    def dotted(self, what: str) -> None:
        if self.ident() is None:
            raise self.fail(f"{what} has no name")
        while self.punct("."):
            if self.ident() is None:
                raise self.fail(f"{what} has a name ending in '.'")

    def configurations(self, keyword: str) -> list[str]:
        uris = []
        while self.peek() == "if":
            self.ident()
            if not self.punct("("):
                raise self.fail("a configuration without '('")
            self.dotted("a configuration")
            if self.punct("=="):
                self.uri("a configuration's '=='")
            if not self.punct(")"):
                raise self.fail("a configuration without ')'")
            uris.append(self.uri(keyword))
        return uris

    def end(self) -> None:
        """Pass a directive's combinators and prefix, up to and past its ';'."""
        while not self.punct(";"):
            if self.ident() is None and not self.punct(",") and not self.punct("."):
                raise self.fail("text in a directive that is no name, ',' or '.'")

    def annotation(self) -> None:
        self.i += 1  # the '@'
        self.dotted("an annotation")
        self.skip()
        if self.text.startswith("<", self.i):
            self.balanced()
            self.skip()
        if self.text.startswith("(", self.i):
            self.balanced()

    def directives(self) -> tuple[Directive, ...]:
        found: list[Directive] = []
        while True:
            self.skip()
            if self.i >= len(self.text):
                return tuple(found)
            if self.text[self.i] == "@":
                self.annotation()
                continue
            start = self.i
            word = self.peek()
            line = self.line(start)
            if word == "library":
                self.ident()
                if self.peek() is not None:
                    self.dotted("a library")
                if not self.punct(";"):
                    raise self.fail("a library directive without ';'")
            elif word in ("import", "export"):
                self.ident()
                uris = [self.uri(word), *self.configurations(word)]
                self.end()
                found.append(Directive(word, tuple(uris), line))
            elif word == "part":
                self.ident()
                if self.peek() == "of":
                    self.ident()
                    if self.at_string():
                        uri = self.uri("part of")
                        self.end()
                        found.append(Directive("part of", (uri,), line))
                    else:
                        self.dotted("a part of directive")
                        if not self.punct(";"):
                            raise self.fail("a part of directive without ';'")
                        found.append(Directive("part of", (), line))
                else:
                    uris = [self.uri("part"), *self.configurations("part")]
                    self.end()
                    found.append(Directive("part", tuple(uris), line))
            elif word == "augment":
                self.ident()
                if self.peek() in ("library", "import", "part"):
                    raise self.fail("an augmentation directive, which is not followed", start)
                return tuple(found)
            else:
                return tuple(found)


def read_directives(text: str, marker: str) -> tuple[Directive, ...]:
    """The directives *text*, a Dart file, opens with.

    *marker* opens a line comment. Reading stops at the first token that
    belongs to no directive, annotation or comment.

    Raises:
        DirectivesUnreadable: A directive, comment or annotation does not read.
    """
    return _Reader(text, marker).directives()


def _file_path(uri: str) -> Path | None:
    """The normalised local path a ``file:`` URI names, or ``None`` for any other URI."""
    from elspais.graph.parsers.results.placement import file_url_path

    path = file_url_path(uri)
    return None if path is None else Path(os.path.normpath(path))


def _default_pub_cache() -> Path:
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", "")) / "Pub" / "Cache"
    return Path.home() / ".pub-cache"


@dataclass
class _Config:
    """One package configuration: each package's root and library directory."""

    path: Path
    packages: dict[str, tuple[Path, Path]]
    pub_cache: Path
    flutter_root: Path | None
    problem: str = ""
    placed: dict[Path, bool] = field(default_factory=dict)

    @property
    def directory(self) -> Path:
        """The directory holding ``.dart_tool``: the package or workspace root."""
        return self.path.parent.parent

    def environment(self, path: Path) -> bool:
        """Whether *path* lies in the pub cache or the Flutter SDK, wherever those lie."""
        from elspais.graph.parsers.results.placement import placed_in_repo

        if path not in self.placed:
            self.placed[path] = any(
                directory is not None
                and placed_in_repo(str(path), directory, directory) is not None
                for directory in (self.pub_cache, self.flutter_root)
            )
        return self.placed[path]


class _Reading:
    """One call's reading of a repository; everything read is held for that call alone."""

    def __init__(self, root: Path) -> None:
        from elspais.graph.parsers.patterns import comment_pattern_for_path

        pattern = comment_pattern_for_path(".dart")
        assert pattern is not None
        self.marker = pattern.marker
        self.root = Path(os.path.normpath(Path(root).absolute()))
        self.configs: dict[Path, _Config | str] = {}
        self.read: dict[Path, tuple[Directive, ...] | str] = {}
        self.edges: dict[tuple[Path, Path], tuple[Path, ...] | str] = {}
        self.implicit: dict[Path, tuple[Path, ...]] = {}
        self.through: dict[tuple[Path, Path], frozenset[Path] | str] = {}
        self.placed: dict[Path, Path | None] = {}

    def rel(self, path: Path) -> str:
        from elspais.graph.parsers.results.placement import placed_in_repo

        placed = placed_in_repo(str(path), self.root, self.root)
        return placed if placed is not None else str(path)

    def in_repo(self, path: Path) -> Path | None:
        """*path* as a path under the repository root, or ``None`` where it lies outside."""
        from elspais.graph.parsers.results.placement import placed_in_repo

        if path not in self.placed:
            placed = placed_in_repo(str(path), self.root, self.root)
            self.placed[path] = (
                None if placed is None else Path(os.path.normpath(self.root / placed))
            )
        return self.placed[path]

    def upward(self, start: Path):
        """*start* and each directory above it, up to the repository root."""
        directory = start
        while True:
            yield directory
            if directory == self.root or directory.parent == directory:
                return
            directory = directory.parent

    # -- the package configuration -------------------------------------------

    def package_of(self, unit: Path) -> Path | None:
        for directory in self.upward(unit.parent):
            if (directory / "pubspec.yaml").is_file():
                return directory
        return None

    def config_for(self, package: Path) -> _Config | str:
        """The configuration of the program whose entry lies in *package*, or why there is none."""
        for directory in self.upward(package):
            path = directory / _CONFIG
            if not path.is_file():
                continue
            config = self.config(path)
            if isinstance(config, str):
                return config
            if any(root == package for root, _lib in config.packages.values()):
                return config.problem or config
        return (
            f"no package configuration lists the package at {self.rel(package)}; {_PUB_GET} there"
        )

    def config(self, path: Path) -> _Config | str:
        if path not in self.configs:
            self.configs[path] = self.load_config(path)
            config = self.configs[path]
            if isinstance(config, _Config):
                config.problem = self.config_problem(config)
        return self.configs[path]

    def load_config(self, path: Path) -> _Config | str:
        from urllib.parse import urljoin

        where = self.rel(path)
        unreadable = f"{where} is not a version 2 package configuration; {_PUB_GET}"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError):
            return unreadable
        if not isinstance(data, dict) or data.get("configVersion") != 2:
            return unreadable
        entries = data.get("packages")
        if not isinstance(entries, list):
            return unreadable
        base = path.absolute().as_uri()

        def located(uri: object) -> Path | None:
            return _file_path(urljoin(base, uri)) if isinstance(uri, str) else None

        pub_cache = located(data.get("pubCache"))
        if pub_cache is None and os.environ.get("PUB_CACHE"):
            pub_cache = Path(os.environ["PUB_CACHE"])
        config = _Config(
            path=path,
            packages={},
            pub_cache=pub_cache or _default_pub_cache(),
            flutter_root=located(data.get("flutterRoot")),
        )
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
                return unreadable
            root_uri = entry.get("rootUri")
            if not isinstance(root_uri, str):
                return unreadable
            root_uri = root_uri if root_uri.endswith("/") else root_uri + "/"
            root = located(root_uri)
            package_uri = entry.get("packageUri", "")
            library = (
                _file_path(urljoin(urljoin(base, root_uri), package_uri))
                if isinstance(package_uri, str)
                else None
            )
            if root is None or library is None:
                return f"{where} places package {entry['name']} at no file location; {_PUB_GET}"
            # A package of the environment keeps the path it was written with,
            # even where the pub cache lies inside the repository.
            inside = None if config.environment(root) else self.in_repo(root)
            if inside is not None:
                library = Path(os.path.normpath(inside / os.path.relpath(library, root)))
                root = inside
            config.packages[entry["name"]] = (root, library)
        return config

    def config_problem(self, config: _Config) -> str:
        """Why *config* cannot say how its program resolves, or ``""``."""
        for name, (root, _lib) in sorted(config.packages.items()):
            if not config.environment(root) and self.in_repo(root) is None:
                return (
                    f"package {name} resolves to {root}, outside the repository, the pub "
                    f"cache and the Flutter SDK, whose changes elspais cannot see"
                )
        return self.staleness(config)

    def repository_packages(self, config: _Config) -> list[Path]:
        """The roots of the packages *config* places in the repository and not the environment."""
        return sorted(
            {
                root
                for root, _lib in config.packages.values()
                if not config.environment(root) and root.is_relative_to(self.root)
            }
        )

    def staleness(self, config: _Config) -> str:
        """Why the test runner would resolve *config*'s packages again, or ``""``.

        The configuration is current only where the last resolution is newer
        than every file package resolution reads: the ``pubspec.yaml``,
        ``pubspec.lock`` and ``pubspec_overrides.yaml`` beside its
        ``.dart_tool``, and the ``pubspec.yaml`` of every package it places in
        the repository. A resolution that changes nothing rewrites
        ``package_graph.json`` beside the configuration and leaves the
        configuration's own bytes and time alone, so the later of the two
        files dates the last resolution.
        """
        directory = config.directory
        if not (directory / "pubspec.lock").is_file():
            return f"{self.rel(directory)} holds no pubspec.lock; {_PUB_GET} there"
        resolved = config.path.stat().st_mtime
        try:
            resolved = max(resolved, (config.path.parent / "package_graph.json").stat().st_mtime)
        except OSError:
            pass
        compared = [directory / "pubspec.lock", directory / "pubspec_overrides.yaml"]
        compared += sorted(
            {root / "pubspec.yaml" for root in self.repository_packages(config)}
            | {directory / "pubspec.yaml"}
        )
        for path in compared:
            try:
                changed = path.stat().st_mtime
            except OSError:
                continue
            if changed > resolved:
                return (
                    f"{self.rel(config.path)} is older than {self.rel(path)}; "
                    f"{_PUB_GET} in {self.rel(directory)}"
                )
        return ""

    # -- files and their edges -----------------------------------------------

    def directives_of(self, path: Path) -> tuple[Directive, ...] | str:
        if path not in self.read:
            where = self.rel(path)
            try:
                text = path.read_text(encoding="utf-8")
            except FileNotFoundError:
                self.read[path] = f"{where} does not exist"
            except UnicodeDecodeError:
                self.read[path] = f"{where} is not UTF-8"
            except OSError as exc:
                self.read[path] = f"{where} cannot be read: {exc.strerror or exc}"
            else:
                try:
                    self.read[path] = read_directives(text, self.marker)
                except DirectivesUnreadable as exc:
                    self.read[path] = f"{where} line {exc.line}: {exc.why}"
        return self.read[path]

    def edges_of(self, path: Path, config: _Config) -> tuple[Path, ...] | str:
        """The files *path*'s directives reach, or why they are unknown."""
        key = (path, config.path)
        if key not in self.edges:
            self.edges[key] = self.resolve_all(path, config)
        return self.edges[key]

    def resolve_all(self, path: Path, config: _Config) -> tuple[Path, ...] | str:
        directives = self.directives_of(path)
        if isinstance(directives, str):
            return directives
        reached: list[Path] = []
        for directive in directives:
            for uri in directive.uris:
                target = self.resolve(uri, path, config)
                if isinstance(target, _Cause):
                    return target
                if isinstance(target, str):
                    return f"{self.rel(path)} line {directive.line}: {target}"
                if target is not None:
                    reached.append(target)
        return tuple(reached)

    def resolve(self, uri: str, importer: Path, config: _Config) -> Path | str | None:
        """The file *uri* names, ``None`` for a ``dart:`` library, or why it is unknown.

        The file lies in the repository or in the environment (the pub cache
        or the Flutter SDK); a file of the environment keeps its own path.
        """
        from urllib.parse import unquote, urlparse

        scheme = urlparse(uri).scheme if ":" in uri else ""
        if scheme == "dart":
            return None
        if scheme == "package":
            name, _, rest = uri[len("package:") :].partition("/")
            if name not in config.packages:
                return _Cause(f"package {name} is not in {self.rel(config.path)}; {_PUB_GET}")
            _root, library = config.packages[name]
            target = Path(os.path.normpath(library / unquote(rest)))
            if not rest or not target.is_relative_to(library):
                return f"{uri} names no file of package {name}"
        elif scheme == "file":
            target = _file_path(uri)
        elif scheme:
            return f"{uri} has the URI scheme {scheme!r}, which is not followed"
        else:
            target = Path(os.path.normpath(importer.parent / unquote(uri)))
        if config.environment(target):
            return target
        inside = self.in_repo(target)
        if inside is not None:
            return inside
        return f"{uri} names {target}, outside the repository, the pub cache and the Flutter SDK"

    # -- the closure ---------------------------------------------------------

    def through_environment(self, entry: Path, config: _Config) -> frozenset[Path] | str:
        """The repository files reached from *entry*, a file of the environment, through
        files of the environment alone, or why that is unknown.

        A package of the environment may import a repository package, where an
        override or a workspace places that package in the repository, so the
        environment is read as well; only the repository files it leads to are
        evidence. Files that import each other share one answer, so each file of
        the environment is answered for once per configuration.
        """
        memo = self.through
        key = config.path
        if (entry, key) in memo:
            return memo[(entry, key)]
        order: dict[Path, int] = {}
        low: dict[Path, int] = {}
        stack: list[Path] = []
        on_stack: set[Path] = set()
        frames: list[tuple[Path, Iterator[Path]]] = []

        def enter(node: Path) -> None:
            order[node] = low[node] = len(order)
            stack.append(node)
            on_stack.add(node)
            edges = self.edges_of(node, config)
            following = () if isinstance(edges, str) else edges
            frames.append((node, iter([t for t in following if config.environment(t)])))

        enter(entry)
        while frames:
            node, following = frames[-1]
            for target in following:
                if (target, key) in memo:
                    continue
                if target not in order:
                    enter(target)
                    break
                if target in on_stack:
                    low[node] = min(low[node], order[target])
            else:
                frames.pop()
                if frames:
                    parent = frames[-1][0]
                    low[parent] = min(low[parent], low[node])
                if low[node] == order[node]:
                    members = []
                    while not members or members[-1] != node:
                        members.append(stack.pop())
                        on_stack.discard(members[-1])
                    answer = self.reached_from(members, config)
                    for member in members:
                        memo[(member, key)] = answer
        return memo[(entry, key)]

    def reached_from(self, members: list[Path], config: _Config) -> frozenset[Path] | str:
        """The repository files reached from *members*, files of the environment that
        import each other, given the answer for every other file they import."""
        found: set[Path] = set()
        for member in members:
            edges = self.edges_of(member, config)
            if isinstance(edges, str):
                return edges
            for target in edges:
                if not config.environment(target):
                    found.add(target)
                    continue
                known = self.through.get((target, config.path))
                if isinstance(known, str):
                    return known
                if known is not None:
                    found |= known
        return frozenset(found)

    def implicit_roots(self, unit: Path, package: Path, config: _Config) -> list[Path]:
        """Files the test runners load for *unit* without an import."""
        roots: list[Path] = []
        for directory in self.upward(unit.parent):
            found = directory / "flutter_test_config.dart"
            if found.is_file():
                roots.append(found)
                break
            if directory == package:
                break
        if config.path not in self.implicit:
            self.implicit[config.path] = tuple(
                hook
                for root in self.repository_packages(config)
                for hook in (root / "hook" / "build.dart", root / "hook" / "link.dart")
                if hook.is_file()
            )
        return roots + list(self.implicit[config.path])

    def evidence_for(self, unit: str) -> frozenset[str] | str:
        """The repository files *unit* reaches, or why that is unknown."""
        if not unit.endswith(".dart"):
            return f"{unit} is not a Dart file"
        path = Path(os.path.normpath(self.root / unit))
        package = self.package_of(path)
        if package is None:
            return f"no pubspec.yaml above {unit} inside the repository"
        config = self.config_for(package)
        if isinstance(config, str):
            return config
        own = self.directives_of(path)
        if isinstance(own, str):
            return own
        if any(d.keyword == "part of" and not d.uris for d in own):
            return f"{unit} is a part of a library it names only by name"
        seen = {path}
        queue = [path, *self.implicit_roots(path, package, config)]
        seen.update(queue)
        index = 0
        while index < len(queue):
            edges = self.edges_of(queue[index], config)
            index += 1
            if isinstance(edges, str):
                return edges
            for target in edges:
                if config.environment(target):
                    through = self.through_environment(target, config)
                    if isinstance(through, str):
                        return through
                    reached: Iterable[Path] = through
                else:
                    reached = (target,)
                for file in reached:
                    if file not in seen:
                        seen.add(file)
                        queue.append(file)
        return frozenset(self.rel(p) for p in seen)


#: Where Dart files that a test can load only through an import lie, as
#: patterns over the path within an input directory: the libraries and build
#: hooks of each package and its integration tests. ``*`` spans directories.
_IMPORTED_ONLY = tuple(
    pattern
    for directory in ("lib", "hook", "integration_test")
    for pattern in (f"{directory}/*.dart", f"*/{directory}/*.dart")
)


class DartImportsSource:
    name: ClassVar[str] = "imports:dart"
    settings_model: ClassVar[type[BaseModel]] = NoSettings
    extra: ClassVar[str | None] = None

    def default_observes(self, frame: ObservesFrame) -> Observation | None:
        """The Dart inputs a test loads only through an import, and the test files themselves.

        A Dart file a test can run or read without importing it -- a program
        under ``bin/`` or ``tool/``, a helper or fixture under ``test/`` --
        is left unobserved, so a change to it executes every test
        file of the target.
        """
        tests = tuple(p for p in frame.test.file_patterns if p.endswith(".dart"))
        return Observation(
            directories=frame.inputs.directories,
            file_patterns=(
                *_IMPORTED_ONLY,
                "flutter_test_config.dart",
                *(tests or ("*_test.dart",)),
            ),
            skip_dirs=frame.inputs.skip_dirs,
            skip_files=frame.inputs.skip_files,
        )

    def evidence(self, request: SourceRequest) -> Evidence:
        """Each unit's import closure; a unit it cannot be sure of has its reason instead.

        Raises:
            SourceFailed: The target declares no environment probe that
                affects retention, so a change of the SDK every Dart test
                loads would go unseen.
        """
        if not request.environment_probes:
            raise SourceFailed(
                f"target {request.target_name} declares no environment probe that affects "
                f"retention, so a change of the Dart or Flutter SDK its tests load would go "
                f"unseen; declare one, such as `dart --version` or "
                f"`flutter --version --machine`"
            )
        reading = _Reading(request.repo_root)
        files: dict[str, frozenset[str]] = {}
        no_evidence: dict[str, str] = {}
        for unit in sorted(request.units):
            found = reading.evidence_for(unit)
            if isinstance(found, str):
                no_evidence[unit] = found
            else:
                files[unit] = found
        return Evidence(files=files, no_evidence=no_evidence)
