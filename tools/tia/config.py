"""The TIA rule file (tools/tia/config.toml)."""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from pathlib import Path

try:  # Python 3.11+
    import tomllib as _toml

    def _loads(text: str) -> dict:
        return _toml.loads(text)
except ModuleNotFoundError:  # pragma: no cover - Python 3.10: elspais depends on tomlkit
    import tomlkit

    def _loads(text: str) -> dict:
        return tomlkit.parse(text).unwrap()


DEFAULT_CONFIG = Path(__file__).with_name("config.toml")


def loads_toml(text: str) -> dict:
    return _loads(text)


def glob_to_regex(pattern: str) -> re.Pattern:
    """`**` spans directories, `*` and `?` stay inside one path segment.

    A pattern without a `/` matches the basename anywhere is NOT implied: a
    pattern names a repository-relative path, so `conftest.py` is the root one.
    """
    out = []
    i = 0
    while i < len(pattern):
        c = pattern[i]
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif c == "*":
            out.append("[^/]*")
            i += 1
        elif c == "?":
            out.append("[^/]")
            i += 1
        elif c == "[" and pattern.find("]", i + 2) != -1:
            j = pattern.find("]", i + 2)
            body = pattern[i + 1 : j]
            if body.startswith("!"):
                body = "^" + body[1:]
            out.append("[" + body.replace("\\", "\\\\") + "]")
            i = j + 1
        else:
            out.append(re.escape(c))
            i += 1
    return re.compile("".join(out) + r"\Z")


def path_matches(path: str, patterns) -> bool:
    return any(glob_to_regex(p).match(path) for p in patterns)


@dataclass(frozen=True)
class Rule:
    paths: tuple[str, ...]
    action: str
    reason: str = ""
    ignore_keys: tuple[str, ...] = ()

    def matches(self, path: str) -> bool:
        return path_matches(path, self.paths)


@dataclass
class Config:
    suite_name: str = "unit"
    test_roots: list[str] = field(default_factory=lambda: ["tests"])
    test_file_patterns: list[str] = field(default_factory=lambda: ["test_*.py", "*_test.py"])
    production_roots: list[str] = field(default_factory=lambda: ["src"])
    import_roots: list[str] = field(default_factory=lambda: ["src", "."])
    granularity: str = "file"
    full_suite_threshold: float = 0.85
    always_run: list[str] = field(default_factory=list)
    opaque_programs: list[str] = field(default_factory=lambda: ["python*"])
    memoizing_decorators: list[str] = field(default_factory=lambda: ["cache", "lru_cache"])
    max_baseline_age_days: float = 30
    on_environment_change: str = "full"
    rules: list[Rule] = field(default_factory=list)

    # -- classification helpers ------------------------------------------
    def rule_for(self, path: str) -> Rule | None:
        for rule in self.rules:
            if rule.matches(path):
                return rule
        return None

    def under(self, path: str, roots) -> bool:
        return any(
            r in ("", ".") or path == r or path.startswith(r.rstrip("/") + "/") for r in roots
        )

    def is_test_module(self, path: str) -> bool:
        if not path.endswith(".py") or not self.under(path, self.test_roots):
            return False
        name = path.rsplit("/", 1)[-1]
        return any(fnmatch.fnmatchcase(name, p) for p in self.test_file_patterns)

    def is_production(self, path: str) -> bool:
        return self.under(path, self.production_roots)

    def program_is_opaque(self, program: str) -> bool:
        return any(fnmatch.fnmatchcase(program, p) for p in self.opaque_programs)


def load_config(path: str | Path | None = None) -> Config:
    path = Path(path) if path else DEFAULT_CONFIG
    data = _loads(path.read_text(encoding="utf-8"))
    suite = data.get("suite", {})
    sel = data.get("selection", {})
    cfg = Config(
        suite_name=suite.get("name", "unit"),
        test_roots=list(suite.get("test_roots", ["tests"])),
        test_file_patterns=list(suite.get("test_file_patterns", ["test_*.py", "*_test.py"])),
        production_roots=list(suite.get("production_roots", ["src"])),
        import_roots=list(suite.get("import_roots", ["src", "."])),
        granularity=sel.get("granularity", "file"),
        full_suite_threshold=float(sel.get("full_suite_threshold", 0.85)),
        always_run=list(sel.get("always_run", [])),
        opaque_programs=list(sel.get("opaque_programs", ["python*"])),
        memoizing_decorators=list(sel.get("memoizing_decorators", ["cache", "lru_cache"])),
        max_baseline_age_days=float(sel.get("max_baseline_age_days", 30)),
        on_environment_change=sel.get("on_environment_change", "full"),
        rules=[
            Rule(
                paths=tuple(r["paths"]),
                action=r["action"],
                reason=r.get("reason", ""),
                ignore_keys=tuple(r.get("ignore_keys", ())),
            )
            for r in data.get("rule", [])
        ],
    )
    if cfg.granularity not in ("file", "test"):
        raise ValueError(f"selection.granularity must be 'file' or 'test', not {cfg.granularity!r}")
    if cfg.on_environment_change not in ("full", "warn"):
        raise ValueError("selection.on_environment_change must be 'full' or 'warn'")
    for r in cfg.rules:
        if r.action not in ("full", "ignore", "manifest"):
            raise ValueError(f"rule action must be full, ignore or manifest, not {r.action!r}")
    return cfg
