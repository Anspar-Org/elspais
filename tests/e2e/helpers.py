# Verifies: REQ-p00013
"""Shared helpers for building temporary elspais projects in e2e tests.

Every e2e test builds its own project from scratch in tmp_path.
These helpers make that concise and readable.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

import tomlkit

# ---------------------------------------------------------------------------
# Hash computation (mirrors elspais internals)
# ---------------------------------------------------------------------------


def _normalize_assertion_text(label: str, text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\n", " ")
    text = re.sub(r" {2,}", " ", text)
    text = text.strip()
    return f"{label}. {text}"


def compute_hash(assertions: list[tuple[str, str]], length: int = 8) -> str:
    """Compute requirement hash from (label, text) assertion pairs.

    Order-independent: assertions are sorted by individual hash.
    """
    if not assertions:
        return hashlib.sha256(b"").hexdigest()[:length]
    individual: list[str] = []
    for label, text in assertions:
        norm = _normalize_assertion_text(label, text)
        individual.append(hashlib.sha256(norm.encode("utf-8")).hexdigest())
    individual.sort()
    combined = "\n".join(individual)
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()[:length]


# ---------------------------------------------------------------------------
# Assertion label generators
# ---------------------------------------------------------------------------


def labels_uppercase(n: int) -> list[str]:
    """Generate uppercase assertion labels: A, B, C, ..."""
    return [chr(ord("A") + i) for i in range(n)]


def labels_numeric(n: int, zero_pad: bool = False) -> list[str]:
    """Generate numeric assertion labels: 0, 1, 2, ... or 00, 01, 02, ..."""
    if zero_pad:
        width = len(str(n - 1)) if n > 1 else 1
        return [str(i).zfill(width) for i in range(n)]
    return [str(i) for i in range(n)]


def labels_numeric_1based(n: int, zero_pad: bool = False) -> list[str]:
    """Generate 1-based numeric labels: 1, 2, 3, ... or 01, 02, 03, ..."""
    if zero_pad:
        width = len(str(n)) if n > 0 else 1
        return [str(i).zfill(width) for i in range(1, n + 1)]
    return [str(i) for i in range(1, n + 1)]


# ---------------------------------------------------------------------------
# Requirement builder
# ---------------------------------------------------------------------------


class Requirement:
    """Builder for a single requirement markdown block."""

    def __init__(
        self,
        req_id: str,
        title: str,
        level: str,
        status: str = "Active",
        implements: str | None = None,
        refines: str | None = None,
        satisfies: str | None = None,
        body: str = "",
        assertions: list[tuple[str, str]] | None = None,
        rationale: str | None = None,
        use_acceptance_criteria: bool = False,
        heading_level: int = 1,
    ):
        self.req_id = req_id
        self.title = title
        self.level = level
        self.status = status
        self.implements = implements
        self.refines = refines
        self.satisfies = satisfies
        self.body = body
        self.assertions = assertions or []
        self.rationale = rationale
        self.use_acceptance_criteria = use_acceptance_criteria
        self.heading_level = heading_level

    def render(self) -> str:
        """Render this requirement as markdown text with correct hash."""
        hashes = "#" * self.heading_level
        lines = [f"{hashes} {self.req_id}: {self.title}", ""]

        # Metadata line
        meta = f"**Level**: {self.level} | **Status**: {self.status}"
        if self.implements:
            meta += f" | **Implements**: {self.implements}"
        if self.refines:
            meta += f" | **Refines**: {self.refines}"
        if self.satisfies:
            meta += f" | **Satisfies**: {self.satisfies}"
        lines.append(meta)
        lines.append("")

        if self.body:
            lines.append(self.body)
            lines.append("")

        # Assertions section
        if self.assertions:
            if self.use_acceptance_criteria:
                lines.append("**Acceptance Criteria**:")
                for _label, text in self.assertions:
                    lines.append(f"- {text}")
            else:
                lines.append("## Assertions")
                lines.append("")
                for label, text in self.assertions:
                    lines.append(f"{label}. {text}")
            lines.append("")

        if self.rationale:
            lines.append("## Rationale")
            lines.append("")
            lines.append(self.rationale)
            lines.append("")

        # Compute hash
        hash_val = compute_hash(self.assertions)

        lines.append(f"*End* *{self.title}* | **Hash**: {hash_val}")
        lines.append("---")
        lines.append("")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Spec file builder
# ---------------------------------------------------------------------------


def write_spec_file(
    path: Path,
    requirements: list[Requirement],
    preamble: str = "",
) -> Path:
    """Write a spec file containing multiple requirements."""
    path.parent.mkdir(parents=True, exist_ok=True)
    content = ""
    if preamble:
        content += preamble + "\n\n---\n\n"
    content += "\n".join(r.render() for r in requirements)
    path.write_text(content)
    return path


# ---------------------------------------------------------------------------
# Code file builders (for Implements/Refines references)
# ---------------------------------------------------------------------------


def write_python_code(
    path: Path,
    implements: list[str] | None = None,
    refines: list[str] | None = None,
    content: str = "",
) -> Path:
    """Write a Python source file with optional Implements/Refines comments."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    if implements:
        for ref in implements:
            lines.append(f"# Implements: {ref}")
    if refines:
        for ref in refines:
            lines.append(f"# Refines: {ref}")
    lines.append("")
    if content:
        lines.append(content)
    else:
        lines.append("def placeholder():")
        lines.append("    pass")
    lines.append("")
    path.write_text("\n".join(lines))
    return path


def write_js_code(
    path: Path,
    implements: list[str] | None = None,
    content: str = "",
) -> Path:
    """Write a JS source file with // Implements: comments."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    if implements:
        for ref in implements:
            lines.append(f"// Implements: {ref}")
    lines.append("")
    lines.append(content or "function placeholder() {}")
    lines.append("")
    path.write_text("\n".join(lines))
    return path


# ---------------------------------------------------------------------------
# Test file builders (for Validates references)
# ---------------------------------------------------------------------------


def write_python_test(
    path: Path,
    verifies: list[str] | None = None,
    content: str = "",
) -> Path:
    """Write a Python test file with Verifies comments."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    if verifies:
        for ref in verifies:
            lines.append(f"# Verifies: {ref}")
    lines.append("")
    if content:
        lines.append(content)
    else:
        lines.append("def test_placeholder():")
        lines.append("    assert True")
    lines.append("")
    path.write_text("\n".join(lines))
    return path


# ---------------------------------------------------------------------------
# Config builder
# ---------------------------------------------------------------------------


def write_config(path: Path, config: dict[str, Any]) -> Path:
    """Write .elspais.toml from a dict."""
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = tomlkit.dumps(config)
    path.write_text(doc)
    return path


def base_config(
    name: str = "test-project",
    project_type: str = "core",
    namespace: str = "REQ",
    spec_dir: str | list[str] = "spec",
    code_dir: str | list[str] = "src",
    *,
    # ID pattern options
    canonical: str = "{namespace}-{level.letter}{component}",
    types: dict | None = None,
    component_style: str = "numeric",
    component_digits: int = 5,
    leading_zeros: bool = True,
    # Assertion options
    label_style: str = "uppercase",
    max_assertions: int = 26,
    zero_pad_assertions: bool = False,
    multi_assertion_separator: str = "+",
    # Format rules
    require_hash: bool = True,
    require_assertions: bool = True,
    require_shall: bool = True,
    require_status: bool = True,
    status_roles: dict[str, list[str]] | None = None,
    acceptance_criteria: str = "warn",
    labels_sequential: bool = True,
    # Hierarchy rules
    allowed_implements: list[str] | None = None,
    allow_structural_orphans: bool = False,
    # Skip/ignore
    skip_files: list[str] | None = None,
    skip_dirs: list[str] | None = None,
    # Testing
    testing_enabled: bool = False,
    test_dirs: list[str] | None = None,
    test_patterns: list[str] | None = None,
    # References
    comment_styles: list[str] | None = None,
    # Associated
    associated_enabled: bool = False,
    associated_position: str = "after_prefix",
    associated_format: str = "uppercase",
    associated_length: int = 3,
    # Changelog
    changelog_hash_current: bool = False,
) -> dict[str, Any]:
    """Build a base config dict with sensible defaults (v3 schema)."""
    # Convert old types dict to v3 levels dict
    if types is None:
        levels = {
            "prd": {"rank": 1, "letter": "p", "implements": ["prd"]},
            "ops": {"rank": 2, "letter": "o", "implements": ["ops", "prd"]},
            "dev": {"rank": 3, "letter": "d", "implements": ["dev", "ops", "prd"]},
        }
    else:
        levels = {}
        for code, tdef in types.items():
            if isinstance(tdef, dict):
                levels[code] = {
                    "rank": tdef.get("level", tdef.get("rank", 1)),
                    "letter": tdef.get("aliases", {}).get("letter", code[0]),
                    "implements": tdef.get("implements", [code]),
                }
            else:
                levels[code] = {"rank": 1, "letter": code[0], "implements": [code]}

    if status_roles is None:
        status_roles = {
            "active": ["Active"],
            "provisional": ["Draft"],
            "retired": ["Deprecated", "Superseded"],
        }

    spec_dirs = [spec_dir] if isinstance(spec_dir, str) else spec_dir
    code_dirs = [code_dir] if isinstance(code_dir, str) else code_dir

    cfg: dict[str, Any] = {
        "version": 3,
        "cli_ttl": 2,
        "project": {
            "name": name,
            "namespace": namespace,
        },
        "levels": levels,
        "scanning": {
            "spec": {"directories": spec_dirs},
            "code": {"directories": code_dirs},
        },
        "id-patterns": {
            "canonical": canonical,
            "component": {
                "style": component_style,
                "digits": component_digits,
                "leading_zeros": leading_zeros,
            },
            "assertions": {
                "label_style": label_style,
                "max_count": max_assertions,
            },
        },
        "rules": {
            "hierarchy": {
                "allow_structural_orphans": allow_structural_orphans,
            },
            "format": {
                "require_hash": require_hash,
                "require_assertions": require_assertions,
                "require_status": require_status,
                "status_roles": status_roles,
            },
        },
        "changelog": {
            "hash_current": changelog_hash_current,
        },
    }

    if zero_pad_assertions:
        cfg["id-patterns"]["assertions"]["zero_pad"] = True

    if multi_assertion_separator != "+":
        cfg["id-patterns"]["assertions"]["multi_separator"] = multi_assertion_separator

    if skip_files:
        cfg["scanning"]["spec"]["skip_files"] = skip_files

    if skip_dirs:
        cfg["scanning"]["spec"]["skip_dirs"] = skip_dirs

    if testing_enabled:
        cfg["scanning"]["test"] = {
            "enabled": True,
            "directories": test_dirs or ["tests"],
            "file_patterns": test_patterns or ["test_*.py", "*_test.py"],
        }

    if comment_styles:
        cfg.setdefault("references", {})["comment_styles"] = comment_styles

    if associated_enabled:
        cfg["id-patterns"]["associated"] = {
            "enabled": True,
            "position": associated_position,
            "format": associated_format,
            "length": associated_length,
            "separator": "-",
        }

    return cfg


def associate_config(
    name: str,
    prefix: str,
    core_path: str = "..",
    namespace: str = "REQ",
    spec_dir: str = "spec",
    *,
    types: dict | None = None,
    canonical: str = "{namespace}-{level.letter}{component}",
    component_digits: int = 5,
    label_style: str = "uppercase",
    allowed_implements: list[str] | None = None,
) -> dict[str, Any]:
    """Build config dict for an associated repo (v3 schema)."""
    if types is None:
        levels = {
            "prd": {"rank": 1, "letter": "p", "implements": ["prd"]},
            "ops": {"rank": 2, "letter": "o", "implements": ["ops", "prd"]},
            "dev": {"rank": 3, "letter": "d", "implements": ["dev", "ops", "prd"]},
        }
    else:
        levels = {}
        for code, tdef in types.items():
            if isinstance(tdef, dict):
                levels[code] = {
                    "rank": tdef.get("level", tdef.get("rank", 1)),
                    "letter": tdef.get("aliases", {}).get("letter", code[0]),
                    "implements": tdef.get("implements", [code]),
                }
            else:
                levels[code] = {"rank": 1, "letter": code[0], "implements": [code]}

    return {
        "version": 3,
        "project": {
            "name": name,
            "namespace": namespace,
        },
        "levels": levels,
        "scanning": {
            "spec": {"directories": [spec_dir]},
        },
        "id-patterns": {
            "canonical": canonical,
            "component": {
                "style": "numeric",
                "digits": component_digits,
                "leading_zeros": True,
            },
            "assertions": {
                "label_style": label_style,
            },
        },
        "rules": {
            "hierarchy": {
                "cross_repo_implements": True,
            },
        },
        "changelog": {
            "hash_current": False,
        },
    }


# ---------------------------------------------------------------------------
# Project scaffold
# ---------------------------------------------------------------------------


def init_git_repo(path: Path) -> None:
    """Initialize a git repo with an initial commit."""
    subprocess.run(["git", "init", "-b", "main"], cwd=path, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=path,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=path,
        capture_output=True,
    )
    subprocess.run(["git", "add", "."], cwd=path, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial", "--allow-empty"],
        cwd=path,
        capture_output=True,
    )


def build_project(
    root: Path,
    config: dict[str, Any],
    spec_files: dict[str, list[Requirement]] | None = None,
    code_files: dict[str, dict] | None = None,
    test_files: dict[str, dict] | None = None,
    extra_files: dict[str, str] | None = None,
    init_git: bool = True,
) -> Path:
    """Build a complete project directory.

    Args:
        root: Project root directory.
        config: Config dict (written as .elspais.toml).
        spec_files: Map of relative path -> list of Requirements.
        code_files: Map of relative path -> {"implements": [...], "content": "..."}.
        test_files: Map of relative path -> {"verifies": [...], "content": "..."}.
        extra_files: Map of relative path -> raw text content.
        init_git: Whether to git init the project.

    Returns:
        The root path.
    """
    root.mkdir(parents=True, exist_ok=True)
    write_config(root / ".elspais.toml", config)

    if spec_files:
        for rel_path, reqs in spec_files.items():
            write_spec_file(root / rel_path, reqs)

    if code_files:
        for rel_path, info in code_files.items():
            write_python_code(
                root / rel_path,
                implements=info.get("implements"),
                refines=info.get("refines"),
                content=info.get("content", ""),
            )

    if test_files:
        for rel_path, info in test_files.items():
            write_python_test(
                root / rel_path,
                verifies=info.get("verifies"),
                content=info.get("content", ""),
            )

    if extra_files:
        for rel_path, content in extra_files.items():
            p = root / rel_path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)

    if init_git:
        init_git_repo(root)

    return root


def build_associate(
    root: Path,
    name: str,
    prefix: str,
    core_path: str,
    spec_files: dict[str, list[Requirement]] | None = None,
    config_overrides: dict | None = None,
    init_git: bool = False,
) -> Path:
    """Build an associated repo directory alongside the core."""
    cfg = associate_config(name, prefix, core_path)
    if config_overrides:
        _deep_merge(cfg, config_overrides)

    root.mkdir(parents=True, exist_ok=True)
    write_config(root / ".elspais.toml", cfg)

    if spec_files:
        for rel_path, reqs in spec_files.items():
            write_spec_file(root / rel_path, reqs)

    if init_git:
        init_git_repo(root)

    return root


def _deep_merge(base: dict, overlay: dict) -> dict:
    """Recursively merge overlay into base (mutates base)."""
    for k, v in overlay.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
    return base


# ---------------------------------------------------------------------------
# CLI runner
# ---------------------------------------------------------------------------


def run_elspais(
    *args: str,
    cwd: str | Path | None = None,
    timeout: int = 120,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    """Run elspais CLI as a subprocess."""
    import os
    import shutil

    exe = shutil.which("elspais")
    if exe is None:
        import pytest

        pytest.skip("elspais CLI not found on PATH")

    run_env = None
    if env:
        run_env = os.environ.copy()
        run_env.update(env)

    return subprocess.run(
        [exe, *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=timeout,
        env=run_env,
    )


# ---------------------------------------------------------------------------
# MCP helpers
# ---------------------------------------------------------------------------


def start_mcp(cwd: str | Path) -> subprocess.Popen:
    """Start an MCP server as a subprocess and perform handshake."""
    import shutil

    exe = shutil.which("elspais")
    if exe is None:
        import pytest

        pytest.skip("elspais CLI not found on PATH")

    proc = subprocess.Popen(
        [exe, "mcp", "serve"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        cwd=cwd,
    )
    _mcp_initialize(proc)
    return proc


def stop_mcp(proc: subprocess.Popen) -> None:
    """Gracefully stop an MCP server."""
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def _mcp_send(proc: subprocess.Popen, obj: dict) -> None:
    proc.stdin.write(json.dumps(obj) + "\n")
    proc.stdin.flush()


def _mcp_recv(proc: subprocess.Popen, timeout: float = 15.0) -> dict:
    import select

    ready, _, _ = select.select([proc.stdout], [], [], timeout)
    if not ready:
        stderr = proc.stderr.read() if proc.stderr else ""
        raise TimeoutError(f"No response from MCP server. stderr: {stderr}")
    line = proc.stdout.readline()
    if not line:
        stderr = proc.stderr.read() if proc.stderr else ""
        raise EOFError(f"MCP server closed stdout. stderr: {stderr}")
    return json.loads(line)


def _mcp_initialize(proc: subprocess.Popen) -> dict:
    _mcp_send(
        proc,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "e2e-test", "version": "0.1.0"},
            },
        },
    )
    response = _mcp_recv(proc)
    _mcp_send(proc, {"jsonrpc": "2.0", "method": "notifications/initialized"})
    return response


_MSG_COUNTER = 2  # Start at 2 since initialize used 1


def mcp_call(proc: subprocess.Popen, tool: str, args: dict, msg_id: int | None = None) -> Any:
    """Call an MCP tool and return the parsed JSON result."""
    global _MSG_COUNTER
    if msg_id is None:
        msg_id = _MSG_COUNTER
        _MSG_COUNTER += 1

    _mcp_send(
        proc,
        {
            "jsonrpc": "2.0",
            "id": msg_id,
            "method": "tools/call",
            "params": {"name": tool, "arguments": args},
        },
    )
    response = _mcp_recv(proc)
    if "error" in response:
        return {"_error": response["error"]}
    result = response["result"]
    # FastMCP wraps tool errors in isError flag
    if result.get("isError"):
        return {"_error": result["content"][0]["text"] if result.get("content") else "unknown"}
    content = result["content"]
    if not content:
        return None
    text = content[0]["text"]
    if not text:
        return None
    return json.loads(text)


def mcp_call_all(proc: subprocess.Popen, tool: str, args: dict, msg_id: int | None = None) -> list:
    """Call an MCP tool and return ALL content items as parsed dicts."""
    global _MSG_COUNTER
    if msg_id is None:
        msg_id = _MSG_COUNTER
        _MSG_COUNTER += 1

    _mcp_send(
        proc,
        {
            "jsonrpc": "2.0",
            "id": msg_id,
            "method": "tools/call",
            "params": {"name": tool, "arguments": args},
        },
    )
    response = _mcp_recv(proc)
    if "error" in response:
        return [{"_error": response["error"]}]
    content = response["result"]["content"]
    return [json.loads(item["text"]) for item in content]
