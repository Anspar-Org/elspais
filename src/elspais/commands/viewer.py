# Implements: REQ-d00010-A
"""
elspais.commands.viewer - Interactive traceability viewer server.

Starts a Flask-based server for browsing and editing the traceability graph.
Extracted from trace.py to separate the interactive viewer from static report
generation.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _is_port_in_use(port: int) -> bool:
    """Check if something is listening on 127.0.0.1:port."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _is_elspais_server(port: int) -> bool:
    """Check if an elspais server is running on the given port."""
    import json
    from urllib.request import urlopen

    try:
        with urlopen(f"http://127.0.0.1:{port}/api/status", timeout=2) as resp:
            data = json.loads(resp.read())
            return "node_counts" in data
    except Exception:
        return False


def _shutdown_server(port: int) -> bool:
    """Shut down an elspais server, preferring the API then falling back to OS kill."""
    import time
    from urllib.request import Request, urlopen

    # Try clean shutdown via API
    try:
        req = Request(f"http://127.0.0.1:{port}/api/shutdown", method="POST", data=b"")
        urlopen(req, timeout=3)
    except Exception:
        pass  # Server may drop connection as it exits — that's fine

    # Wait for the port to free up
    for _ in range(10):
        time.sleep(0.5)
        if not _is_port_in_use(port):
            return True

    # Fall back to OS-level kill
    import os
    import signal
    import subprocess

    try:
        result = subprocess.run(
            ["lsof", "-ti", f":{port}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        pids = [int(p) for p in result.stdout.strip().split() if p.isdigit()]
        for pid in pids:
            os.kill(pid, signal.SIGTERM)

        time.sleep(2)
        if not _is_port_in_use(port):
            return True

        # Force kill
        for pid in pids:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        time.sleep(1)
    except Exception:
        pass

    return not _is_port_in_use(port)


def _find_free_port(start: int) -> int:
    """Find the next free port starting from start+1."""
    for port in range(start + 1, start + 51):
        if not _is_port_in_use(port):
            return port
    raise RuntimeError(f"No free port found in range {start + 1}-{start + 50}")


def _run_server(args: argparse.Namespace, open_browser: bool = False) -> int:
    """Start the Flask trace-edit server.

    Builds the graph, creates the Flask app, and runs the dev server.

    Args:
        args: Parsed CLI arguments.
        open_browser: If True, open the browser automatically (--edit-mode).

    Returns:
        Exit code (0 = success).
    """
    try:
        from elspais.server import create_app
    except ImportError:
        print(
            "Error: Flask server requires the trace-review extra.\n"
            "Install with: pip install elspais[trace-review]",
            file=sys.stderr,
        )
        return 1

    from elspais.config import get_config
    from elspais.graph.factory import build_graph

    spec_dir = getattr(args, "spec_dir", None)
    config_path = getattr(args, "config", None)
    explicit_path = getattr(args, "path", None)
    repo_root = Path(explicit_path).resolve() if explicit_path else Path.cwd().resolve()

    config = get_config(start_path=repo_root, quiet=True)
    canonical_root = getattr(args, "canonical_root", None)
    graph = build_graph(
        spec_dirs=[spec_dir] if spec_dir else None,
        config_path=config_path,
        repo_root=repo_root,
        canonical_root=canonical_root,
    )

    app = create_app(repo_root=repo_root, graph=graph, config=config)
    app.config["ELSPAIS_DEBUG"] = getattr(args, "verbose", False)

    port = getattr(args, "port", None) or 5000
    quiet = getattr(args, "quiet", False)

    if _is_port_in_use(port) and not getattr(args, "port", None):
        is_elspais = _is_elspais_server(port)

        if sys.stdin.isatty():
            if is_elspais:
                print(
                    f"An elspais server is already running on port {port}.",
                    file=sys.stderr,
                )
            else:
                print(
                    f"Port {port} is already in use by another process.",
                    file=sys.stderr,
                )
            print(
                "  [R]eplace - stop existing and take over (default)",
                file=sys.stderr,
            )
            print(
                "  [N]ew port - start alongside on next free port",
                file=sys.stderr,
            )
            print("  [A]bort - cancel", file=sys.stderr)
            choice = input("Choice [R/n/a]: ").strip().lower() or "r"
        else:
            choice = "n"

        if choice.startswith("a"):
            return 0
        elif choice.startswith("n"):
            port = _find_free_port(port)
        else:
            # Replace
            if is_elspais:
                if not quiet:
                    print(
                        f"Shutting down existing server on port {port}...",
                        file=sys.stderr,
                    )
                if not _shutdown_server(port):
                    print(
                        "Could not stop existing server. Using new port.",
                        file=sys.stderr,
                    )
                    port = _find_free_port(port)
            else:
                print(
                    "Cannot replace non-elspais process. Using new port.",
                    file=sys.stderr,
                )
                port = _find_free_port(port)

    url = f"http://127.0.0.1:{port}"
    verbose = getattr(args, "verbose", False)

    if not quiet:
        print(f"Starting trace-edit server at {url}", file=sys.stderr)

    if open_browser:
        import subprocess
        import webbrowser

        # Suppress GTK/Chrome stderr noise from browser launch
        try:
            subprocess.Popen(
                ["xdg-open", url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            webbrowser.open(url)

    # Suppress Flask/Werkzeug noise unless verbose
    if not verbose:
        import logging

        logging.getLogger("werkzeug").setLevel(logging.ERROR)

    try:
        app.run(host="127.0.0.1", port=port, debug=False)
    except KeyboardInterrupt:
        if not quiet:
            print("\nServer stopped.", file=sys.stderr)

    return 0


def _run_static(args: argparse.Namespace) -> int:
    """Generate a static interactive HTML file."""
    from pathlib import Path

    from elspais.graph.factory import build_graph

    spec_dir = getattr(args, "spec_dir", None)
    config_path = getattr(args, "config", None)
    explicit_path = getattr(args, "path", None)
    repo_root = Path(explicit_path).resolve() if explicit_path else Path.cwd().resolve()
    canonical_root = getattr(args, "canonical_root", None)

    graph = build_graph(
        spec_dirs=[spec_dir] if spec_dir else None,
        config_path=config_path,
        repo_root=repo_root,
        canonical_root=canonical_root,
    )

    try:
        from elspais.commands.trace import format_view

        content = format_view(
            graph,
            getattr(args, "embed_content", False),
            base_path=str(repo_root),
        )
    except ImportError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    print(content)
    return 0


def run(args: argparse.Namespace) -> int:
    """Run the viewer command.

    Generates static HTML (--static) or starts the Flask server.
    """
    if getattr(args, "static", False):
        return _run_static(args)
    open_browser = not getattr(args, "server", False)
    return _run_server(args, open_browser=open_browser)
