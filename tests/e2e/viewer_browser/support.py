"""Viewer processes, pages and helpers shared by the viewer browser tests.

Each viewer serves a project of its own under pytest's temp directory, on a
port it bound itself, so the test modules run in parallel.
"""

import contextlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from tests.embedded_page import embedded_data

from ..conftest import REPO_ROOT, private_tree
from ..helpers import resolve_elspais

# A viewer serving this repository builds the whole elspais graph before it
# binds, which is ~17s on a warm developer machine. The 30s this replaced left
# no room for a cold CI container, where the same fixture timed out while a
# viewer over a small tmp_path project in the SAME container came up fine. A
# server that dies is now noticed the moment it dies, so the only thing a
# generous deadline costs is the wait on a genuine hang.
_STARTUP_TIMEOUT = 120.0


# Binding the port is not the end of the work: the first page over this
# repository's own graph renders a tree of every requirement in it, and a cold
# CI container exceeded 30s reaching DOMContentLoaded alone. Milliseconds, the
# unit Playwright takes.
_PAGE_LOAD_TIMEOUT = 90_000


def _spawn_viewer(argv: list[str], **popen_kwargs) -> tuple[subprocess.Popen, Path]:
    """Start a viewer, capturing its output to a file, and return both.

    A FILE rather than a pipe, for two reasons. Nothing reads the pipe while
    the server runs, so a child that filled the 64KB buffer during startup
    would block there forever. And on failure the pipe's contents went
    unread, which is why a viewer that never came up could report only that
    it never came up.
    """
    fd, name = tempfile.mkstemp(prefix="elspais-viewer-", suffix=".log")
    os.close(fd)
    log_path = Path(name)
    with open(log_path, "wb") as sink:
        proc = subprocess.Popen(
            argv,
            stdout=sink,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            **popen_kwargs,
        )
    return proc, log_path


def _server_output(log_path: Path | None, limit: int = 4000) -> str:
    """The tail of what the server said, for a failure message."""
    if log_path is None:
        return "<not captured>"
    try:
        text = log_path.read_text(errors="replace").strip()
    except OSError as exc:
        return f"<could not read {log_path}: {exc}>"
    if not text:
        return "<no output>"
    return text[-limit:]


def _await_viewer(
    proc: subprocess.Popen,
    log_path: Path,
    root: str | Path,
    *,
    base_path: str = "",
    timeout: float = _STARTUP_TIMEOUT,
    poll: float = 0.5,
) -> str:
    """Wait for a viewer started with ``--port 0`` to serve; return its root URL.

    The viewer binds a free port before it writes its record, so the port
    the record under ``root`` names is held by that viewer and no other
    process. The record is accepted only when it names the spawned process,
    and the viewer is ready once ``/api/status`` answers under
    ``base_path`` there.
    """
    import urllib.error
    import urllib.request

    record = Path(root) / ".elspais" / "daemon.json"
    deadline = time.monotonic() + timeout
    port: int | None = None
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            pytest.fail(
                f"The viewer for {root} exited with code {proc.returncode} "
                f"before becoming ready. Its output:\n{_server_output(log_path)}"
            )
        if port is None:
            try:
                info = json.loads(record.read_text())
            except (OSError, ValueError):
                info = None
            if (
                isinstance(info, dict)
                and info.get("pid") == proc.pid
                and isinstance(info.get("port"), int)
            ):
                port = info["port"]
            else:
                time.sleep(poll)
                continue
        root_url = f"http://127.0.0.1:{port}"
        try:
            resp = urllib.request.urlopen(f"{root_url}{base_path}/api/status", timeout=2)
            if resp.status == 200:
                return root_url
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(poll)
    pytest.fail(
        f"The viewer for {root} did not become ready within {timeout}s "
        f"(still running: {proc.poll() is None}, recorded port: {port}). "
        f"Its output:\n{_server_output(log_path)}"
    )


@pytest.fixture(scope="session")
def viewer_url(tmp_path_factory):
    """Start elspais viewer server over a private copy of this repository.

    The copy is the tree under test without the checkout's daemon or
    results, so serving it stops nothing the developer is running.
    """
    elspais_bin = resolve_elspais()
    if elspais_bin is None:
        pytest.skip("elspais CLI not found on PATH")

    tree = private_tree(tmp_path_factory.mktemp("repo-tree"))
    base_url = ""

    proc, log_path = _spawn_viewer(
        [elspais_bin, "viewer", "--server", "--port", "0", "--path", str(tree)],
        cwd=tree,
    )

    try:
        base_url = _await_viewer(proc, log_path, tree)
        yield base_url
    finally:
        # Graceful shutdown via API
        try:
            import urllib.request

            req = urllib.request.Request(f"{base_url}/api/shutdown", method="POST")
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            pass

        # Wait briefly, then terminate
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                proc.wait(timeout=5)


@pytest.fixture()
def page(viewer_url):
    """Launch headless Chromium and yield a Playwright page."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        pg = context.new_page()
        pg.set_default_timeout(10_000)
        yield pg
        browser.close()


# The page's own fetch of a route, so the download is read the way the page
# reads it -- under the prefix it is served at.
_FETCH_TEXT = "(u) => fetch(prefixedUrl(u)).then(r => r.text())"


# Every status on, so a test measuring one property is not reading another:
# a retired status is hidden when the page loads, which is itself a narrowing
# the export carries.
_SHOW_EVERY_STATUS = """
() => {
    const g = filterGroups.status;
    g.restore({on: g.buttons.map(b => b.key)});
    g.render();
}
"""


@pytest.fixture(scope="session")
def viewer_url_tables(tmp_path_factory):
    """Start an elspais viewer server against the viewer-tables fixture.

    Copies tests/fixtures/viewer-tables/ to a tmp dir and runs git init
    so the viewer treats it as a standalone project (its own daemon,
    own .elspais.toml). Yields the base URL.
    """
    elspais_bin = resolve_elspais()
    if elspais_bin is None:
        pytest.skip("elspais CLI not found on PATH")

    src = REPO_ROOT / "tests" / "fixtures" / "viewer-tables"
    if not src.exists():
        pytest.skip(f"viewer-tables fixture not present at {src}")

    dest = tmp_path_factory.mktemp("viewer-tables-run")
    # Copy fixture contents (not the dir itself) into dest.
    for item in src.iterdir():
        if item.is_dir():
            shutil.copytree(item, dest / item.name)
        else:
            shutil.copy2(item, dest / item.name)

    # git init so the viewer's repo-root detection settles on `dest`.
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "test",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "test",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    subprocess.run(["git", "init"], cwd=dest, capture_output=True, env=env)
    subprocess.run(["git", "add", "."], cwd=dest, capture_output=True, env=env)
    subprocess.run(["git", "commit", "-m", "init"], cwd=dest, capture_output=True, env=env)

    base_url = ""

    proc, log_path = _spawn_viewer(
        [elspais_bin, "viewer", "--server", "--port", "0", "--path", str(dest)],
        cwd=str(dest),
    )

    try:
        base_url = _await_viewer(proc, log_path, dest)
        yield base_url
    finally:
        # Graceful shutdown via API
        try:
            import urllib.request

            req = urllib.request.Request(f"{base_url}/api/shutdown", method="POST")
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            pass

        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                proc.wait(timeout=5)


@pytest.fixture()
def page_tables(viewer_url_tables):
    """Launch headless Chromium against the tables-fixture viewer."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        pg = context.new_page()
        pg.set_default_timeout(10_000)
        yield pg
        browser.close()


_JOURNEY_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "journey-uat" / "one-step-fails"


_FAILING_JOURNEY_ID = "JNY-OQ-Login-01"


@pytest.fixture(scope="module")
def failing_journey_viewer_url(tmp_path_factory):
    """Start an elspais viewer server against the journey-uat/one-step-fails fixture.

    Uses the current worktree's Python (via PYTHONPATH) so that the version
    with verdict/failing_steps support is used, not the installed pipx binary.
    Yields the base URL.
    """
    if not _JOURNEY_FIXTURE.exists():
        pytest.skip(f"journey-uat fixture not present at {_JOURNEY_FIXTURE}")

    # A copy, because the viewer writes its record into the tree it serves.
    dest = tmp_path_factory.mktemp("journey-one-step-fails")
    shutil.copytree(
        _JOURNEY_FIXTURE, dest, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".elspais")
    )
    base_url = ""

    # Inject the worktree src so we get the version that includes
    # journey verdict/failing_steps in the /api/node/ response.
    worktree_src = str(REPO_ROOT / "src")
    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{worktree_src}:{existing}" if existing else worktree_src

    proc, log_path = _spawn_viewer(
        [
            sys.executable,
            "-m",
            "elspais",
            "viewer",
            "--server",
            "--port",
            "0",
            "--path",
            str(dest),
        ],
        env=env,
    )

    try:
        base_url = _await_viewer(proc, log_path, dest)
        yield base_url
    finally:
        try:
            import urllib.request

            req = urllib.request.Request(f"{base_url}/api/shutdown", method="POST")
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            pass

        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                proc.wait(timeout=5)


@pytest.fixture()
def page_journey(failing_journey_viewer_url):
    """Launch headless Chromium against the journey-uat-fixture viewer."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        pg = context.new_page()
        pg.set_default_timeout(10_000)
        yield pg
        browser.close()


_STEP_BINDING_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "journey-uat" / "junit-step-binding"


_STEP_BINDING_JOURNEY_ID = "JNY-OQ-Login-01"


@pytest.fixture(scope="module")
def step_binding_viewer_url(tmp_path_factory):
    """Start a viewer server against the journey-uat/junit-step-binding fixture.

    Mirrors ``failing_journey_viewer_url`` (worktree src via PYTHONPATH) but
    serves the fixture whose junit results bind at STEP scope: one test
    source file with per-step Verifies tests, and results.xml testcases that
    carry ``file=`` but no ``line=`` and embed ``<journey>/N`` step ids.
    """
    if not _STEP_BINDING_FIXTURE.exists():
        pytest.skip(f"junit-step-binding fixture not present at {_STEP_BINDING_FIXTURE}")

    # A copy, because the viewer writes its record into the tree it serves.
    dest = tmp_path_factory.mktemp("journey-step-binding")
    shutil.copytree(
        _STEP_BINDING_FIXTURE, dest, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".elspais")
    )
    base_url = ""

    worktree_src = str(REPO_ROOT / "src")
    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{worktree_src}:{existing}" if existing else worktree_src

    proc, log_path = _spawn_viewer(
        [
            sys.executable,
            "-m",
            "elspais",
            "viewer",
            "--server",
            "--port",
            "0",
            "--path",
            str(dest),
        ],
        env=env,
    )

    try:
        base_url = _await_viewer(proc, log_path, dest)
        yield base_url
    finally:
        try:
            import urllib.request

            req = urllib.request.Request(f"{base_url}/api/shutdown", method="POST")
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            pass

        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                proc.wait(timeout=5)


@pytest.fixture()
def page_step_binding(step_binding_viewer_url):
    """Launch headless Chromium against the junit-step-binding viewer."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        pg = context.new_page()
        pg.set_default_timeout(10_000)
        yield pg
        browser.close()


_CONCURRENCY_REQ_ID = "REQ-p00001"


@pytest.fixture(scope="module")
def concurrency_viewer_url(tmp_path_factory):
    """Start a viewer against a private copy of the viewer-tables fixture.

    A private copy (module scope, own server) because the test mutates the
    server's in-memory graph behind the browser's back — sharing the
    session-scoped tables server would poison its state for other tests.
    The repo is put on a working branch so the edit toggle activates
    without the create-a-branch modal that guards main.
    """
    elspais_bin = resolve_elspais()
    if elspais_bin is None:
        pytest.skip("elspais CLI not found on PATH")

    src = REPO_ROOT / "tests" / "fixtures" / "viewer-tables"
    if not src.exists():
        pytest.skip(f"viewer-tables fixture not present at {src}")

    dest = tmp_path_factory.mktemp("viewer-concurrency-run")
    for item in src.iterdir():
        if item.is_dir():
            shutil.copytree(item, dest / item.name)
        else:
            shutil.copy2(item, dest / item.name)

    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "test",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "test",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    subprocess.run(["git", "init"], cwd=dest, capture_output=True, env=env)
    subprocess.run(["git", "add", "."], cwd=dest, capture_output=True, env=env)
    subprocess.run(["git", "commit", "-m", "init"], cwd=dest, capture_output=True, env=env)
    # A non-main working branch: toggleEditMode() activates directly instead
    # of raising the "create a working branch" modal.
    subprocess.run(
        ["git", "checkout", "-b", "concurrent-edit"], cwd=dest, capture_output=True, env=env
    )

    base_url = ""

    proc, log_path = _spawn_viewer(
        [elspais_bin, "viewer", "--server", "--port", "0", "--path", str(dest)],
        cwd=str(dest),
    )

    try:
        base_url = _await_viewer(proc, log_path, dest)
        yield base_url
    finally:
        try:
            import urllib.request

            req = urllib.request.Request(f"{base_url}/api/shutdown", method="POST")
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            pass

        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                proc.wait(timeout=5)


@pytest.fixture()
def page_concurrency(concurrency_viewer_url):
    """Launch headless Chromium against the concurrency-fixture viewer."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        pg = context.new_page()
        pg.set_default_timeout(10_000)
        yield pg
        browser.close()


_BADGE_REQ_ID = "REQ-p00001"


# The badge fixture's announcement interval, in seconds; a cycle wait allows
# for a full interval plus the probe it triggers.
_BADGE_HEARTBEAT_SECONDS = 2


_CYCLE_TIMEOUT = _BADGE_HEARTBEAT_SECONDS * 3 + 2.0


# How long the page's adopting count probe is held in the own-edit tests:
# past the server's wake (half the interval, at most a second), so the
# announcement of the page's own edit reaches it before the page has
# adopted the tip, and short of the settle window the page allows its own
# write, so the held adoption still lands inside it.
_ADOPTION_DELAY_SECONDS = 1.4


# The page holds an announced tip back while one of its own writes is in
# flight or just finished (OWN_WRITE_SETTLE_MS); a deferral can chain once,
# so a verdict lands within two windows of the last write.
_JUDGEMENT_TIMEOUT = 2.0 * 2 + 1.5


@pytest.fixture(scope="module")
def badge_viewer_url(tmp_path_factory):
    """Start a viewer against a private copy of the viewer-tables fixture.

    A private copy (module scope, own server, own port) because these tests
    push real pending mutations into the server's in-memory graph — sharing
    the session-scoped tables server would leave unsaved work behind for
    every other test. The repo is put on a non-main working branch so the
    edit surfaces are usable without the create-a-branch modal.
    """
    elspais_bin = resolve_elspais()
    if elspais_bin is None:
        pytest.skip("elspais CLI not found on PATH")

    src = REPO_ROOT / "tests" / "fixtures" / "viewer-tables"
    if not src.exists():
        pytest.skip(f"viewer-tables fixture not present at {src}")

    dest = tmp_path_factory.mktemp("viewer-badge-run")
    for item in src.iterdir():
        if item.is_dir():
            shutil.copytree(item, dest / item.name)
        else:
            shutil.copy2(item, dest / item.name)

    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "test",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "test",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    subprocess.run(["git", "init"], cwd=dest, capture_output=True, env=env)
    subprocess.run(["git", "add", "."], cwd=dest, capture_output=True, env=env)
    subprocess.run(["git", "commit", "-m", "init"], cwd=dest, capture_output=True, env=env)
    subprocess.run(["git", "checkout", "-b", "badge-truth"], cwd=dest, capture_output=True, env=env)

    base_url = ""

    # The server announces itself every few seconds rather than every half
    # minute, so a stream cycle -- the page's count heartbeat -- can be
    # observed within a test's patience. Seconds, not a fraction of one: a
    # probe every few hundred milliseconds would race tests that set page
    # state by hand.
    proc, log_path = _spawn_viewer(
        [elspais_bin, "viewer", "--server", "--port", "0", "--path", str(dest)],
        cwd=str(dest),
        env={**os.environ, "_ELSPAIS_EVENTS_HEARTBEAT": str(_BADGE_HEARTBEAT_SECONDS)},
    )

    try:
        base_url = _await_viewer(proc, log_path, dest)
        yield base_url
    finally:
        try:
            import urllib.request

            req = urllib.request.Request(f"{base_url}/api/shutdown", method="POST")
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            pass

        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                proc.wait(timeout=5)


@pytest.fixture()
def page_badge(badge_viewer_url):
    """Launch headless Chromium against the badge-fixture viewer."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        pg = context.new_page()
        pg.set_default_timeout(10_000)
        yield pg
        browser.close()


def _badge_state(page) -> dict:
    """Snapshot everything the pending-work indicator presents."""
    return page.evaluate(
        """() => {
            const b = document.getElementById('unsaved-badge');
            return {
                text: b ? b.textContent.trim() : null,
                classes: b ? Array.from(b.classList) : null,
                title: b ? (b.getAttribute('title') || '') : null,
                count: editState.mutationCount,
                count_type: typeof editState.mutationCount,
                tip: editState.lastSeenTip,
            };
        }"""
    )


def _refresh_dirty(page) -> None:
    """Drive the count refresh explicitly instead of waiting on the stream."""
    page.evaluate("() => refreshDirtyCount()")


def _create_pending_mutation(page, base: str, new_title: str) -> int:
    """Make real server-side pending work; return the server's pending count."""
    node = page.request.get(f"{base}/api/node/{_BADGE_REQ_ID}").json()
    token = node.get("version")
    assert token, f"/api/node must report a version token, got: {node}"
    resp = page.request.post(
        f"{base}/api/mutate/title",
        data={"node_id": _BADGE_REQ_ID, "new_title": new_title, "if_version": token},
    )
    assert resp.status == 200, f"pending-work setup mutation failed: {resp.status} {resp.text()}"
    dirty = page.request.get(f"{base}/api/dirty").json()
    count = dirty.get("mutation_count")
    assert isinstance(count, int) and count > 0, f"server must report pending work, got: {dirty}"
    return count


def _go_unknown(page) -> None:
    """Make /api/dirty unreachable and refresh, leaving the count unknown."""
    page.route("**/api/dirty", lambda route: route.abort())
    _refresh_dirty(page)


def _close_observing_beforeunload(page, timeout: float = 5.0) -> list[str]:
    """Close the page for real and report any beforeunload dialog it raised.

    Chromium suppresses beforeunload dialogs on pages the user has never
    interacted with, so a genuine click comes first. The wait is on the
    BROWSER CONTEXT, not the page: Chromium delivers the dialog after the
    page target is already gone, so a page-scoped waiter would be torn down
    before it ever saw it. A dialog left unanswered would hang the close, so
    it is accepted as soon as it is observed.
    """
    context = page.context
    dialogs: list[str] = []

    page.click(".header-title")  # real user gesture
    try:
        with context.expect_event("dialog", timeout=timeout * 1000) as info:
            page.close(run_before_unload=True)
        dialog = info.value
        dialogs.append(dialog.type)
        try:
            dialog.accept()
        except Exception:
            # The target can already be gone by the time we answer; the
            # observation is what the test cares about.
            pass
    except PlaywrightTimeoutError:
        pass

    if not page.is_closed():
        page.close()
    return dialogs


_UNLOAD_STATE_KEYS = {
    "willWarnOnClose",
    "pendingCount",
    "countKnown",
    "countEstablishedAt",
    "countSource",
    "lastSeenTip",
}


def _has_unload_state(page) -> bool:
    """Is the on-demand inspection hook present at all?"""
    return page.evaluate("() => typeof window.unloadWarningState === 'function'")


def _unload_state(page) -> dict:
    """Read the inspection hook, failing with a diagnosis if it is absent.

    Going through a helper keeps every downstream test's failure a plain
    assertion about missing behaviour rather than a raw ReferenceError out of
    page.evaluate, which reads like a broken harness.
    """
    assert _has_unload_state(page), (
        "window.unloadWarningState() is not defined: the state behind the "
        "navigation warning is not inspectable from the console"
    )
    return page.evaluate("() => window.unloadWarningState()")


def _server_dirty(page, base: str) -> dict:
    """Ask the server directly what it considers pending."""
    return page.request.get(f"{base}/api/dirty").json()


def _revert_to_zero(page, base: str) -> None:
    """Discard every pending mutation so the server truthfully reports zero.

    The badge fixture's server is module-scoped and earlier tests leave real
    pending work in it, so "nothing pending" cannot be assumed — it has to be
    established. /api/revert rebuilds the graph from disk, which empties the
    mutation log outright; it is guarded on the mutation-log tip, so the
    current tip is read from /api/dirty and echoed back ("" when the log is
    already empty).
    """
    tip = _server_dirty(page, base).get("tip") or ""
    resp = page.request.post(f"{base}/api/revert", data={"if_tip_mutation_id": tip})
    assert resp.status == 200, f"revert setup failed: {resp.status} {resp.text()}"
    after = _server_dirty(page, base)
    assert after.get("mutation_count") == 0, f"revert must leave nothing pending, got: {after}"


def _console_sink(page) -> list[str]:
    """Collect console message text emitted by the page from now on."""
    messages: list[str] = []
    page.on("console", lambda msg: messages.append(msg.text))
    return messages


# The armed branch's own phrasing. The not-armed branch's known-zero wording
# ("no pending changes") deliberately does not contain the parenthesised form,
# so this one literal discriminates against BOTH not-armed variants.
_ARMED_PHRASE = "pending change(s)"


def _beforeunload_messages(messages: list[str]) -> list[str]:
    """The subset of console output reporting the navigation decision."""
    return [m for m in messages if "[elspais]" in m and "beforeunload" in m.lower()]


def _has_stream_cycle(page) -> bool:
    """Is the change stream's cycle a named function a test can reason about?"""
    return page.evaluate("() => typeof window.applyServerEvent === 'function'")


def _await_cycle(page, timeout: float = _CYCLE_TIMEOUT) -> None:
    """Wait for the next stream cycle and for its count probe to land.

    The server announces itself at the fixture's interval, and every
    announcement runs one cycle, so a cycle is observed rather than driven:
    `dirtyCountAt` is cleared first and the wait is for something to set it
    again. Both count outcomes stamp it -- a server answer and a failed read
    alike -- so this is a true "a probe happened" signal, not a "the probe
    succeeded" one. That is what makes an absence assertion (`the badge
    never went to ?`) strict instead of racy.
    """
    assert _has_stream_cycle(page), (
        "window.applyServerEvent() is not defined: the change stream's cycle "
        "is not a named function, so the page's only count heartbeat cannot "
        "be observed"
    )
    page.evaluate("() => { editState.dirtyCountAt = null; }")
    _wait_for_js(
        page,
        "() => editState.dirtyCountAt !== null",
        "a stream cycle must probe the pending count, but nothing re-established it",
        timeout=timeout,
    )


def _wait_for_js(page, expression: str, message: str, timeout: float = 5.0) -> None:
    """Wait for a page-side condition, failing as an assertion rather than a
    raw Playwright timeout so the report reads as missing behaviour."""
    try:
        page.wait_for_function(expression, timeout=timeout * 1000)
    except PlaywrightTimeoutError:
        raise AssertionError(f"{message} (waiting on: {expression})") from None


def _dom_present(page, selector: str) -> bool:
    return page.evaluate(f"() => document.querySelector({selector!r}) !== null")


def _error_modal_text(page) -> str:
    return page.evaluate(
        """() => {
            const el = document.getElementById('error-modal-overlay');
            return el ? el.textContent : '';
        }"""
    )


def _attempt_title_mutation(page, new_title: str) -> None:
    """Drive the page's own mutate() path for the badge fixture's requirement.

    mutate() is the unit under test here, and it is a global, so it is invoked
    directly rather than through a card's edit UI: opening a card and typing
    would exercise a great deal of unrelated machinery for no extra coverage
    of the failed-POST branch, and would be far less deterministic.
    """
    page.evaluate(
        """async (payload) => {
            await mutate('/api/mutate/title', payload);
        }""",
        {"node_id": _BADGE_REQ_ID, "new_title": new_title},
    )


_FILE_MUT_REQ_ID = "REQ-p00001"


_FILE_MUT_NAMESPACE = "REQ"  # tests/fixtures/viewer-tables project namespace


@pytest.fixture(scope="module")
def file_mutation_viewer_url(tmp_path_factory):
    """Start a viewer against a private copy of the viewer-tables fixture.

    A private copy (module scope, own server) because these tests rename and
    create spec files. Launched through the worktree's own source (``python
    -m elspais`` with ``PYTHONPATH``, as the journey fixtures do) rather than
    whatever ``elspais`` is on PATH, since the JS under test ships inside the
    package being served. The repo is put on a non-main working branch so the
    edit toggle activates without the create-a-branch modal.
    """
    src = REPO_ROOT / "tests" / "fixtures" / "viewer-tables"
    if not src.exists():
        pytest.skip(f"viewer-tables fixture not present at {src}")

    dest = tmp_path_factory.mktemp("viewer-file-mutations-run")
    for item in src.iterdir():
        if item.is_dir():
            shutil.copytree(item, dest / item.name)
        else:
            shutil.copy2(item, dest / item.name)

    git_env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "test",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "test",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    subprocess.run(["git", "init"], cwd=dest, capture_output=True, env=git_env)
    subprocess.run(["git", "add", "."], cwd=dest, capture_output=True, env=git_env)
    subprocess.run(["git", "commit", "-m", "init"], cwd=dest, capture_output=True, env=git_env)
    subprocess.run(
        ["git", "checkout", "-b", "file-edits"], cwd=dest, capture_output=True, env=git_env
    )

    base_url = ""

    worktree_src = str(REPO_ROOT / "src")
    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{worktree_src}:{existing}" if existing else worktree_src

    proc, log_path = _spawn_viewer(
        [
            sys.executable,
            "-m",
            "elspais",
            "viewer",
            "--server",
            "--port",
            "0",
            "--path",
            str(dest),
        ],
        cwd=str(dest),
        env=env,
    )

    try:
        base_url = _await_viewer(proc, log_path, dest)
        yield base_url
    finally:
        try:
            import urllib.request

            req = urllib.request.Request(f"{base_url}/api/shutdown", method="POST")
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            pass

        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                proc.wait(timeout=5)


@pytest.fixture()
def page_file_mutation(file_mutation_viewer_url):
    """Launch headless Chromium against the file-mutation-fixture viewer."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        pg = context.new_page()
        pg.set_default_timeout(10_000)
        yield pg
        browser.close()


def _spec_files(page, base: str) -> dict[str, str]:
    """Map relative_path -> FILE node id, as the SERVER currently sees it."""
    resp = page.request.get(f"{base}/api/spec-files")
    assert resp.ok, f"GET /api/spec-files returned {resp.status}"
    return {f["relative_path"]: f["id"] for f in resp.json().get("files", [])}


def _wait_for_spec_file(page, base: str, relative_path: str, timeout: float = 10.0) -> dict:
    """Poll /api/spec-files until `relative_path` is listed, else return the
    last listing seen so the assertion can report what the server did have."""
    deadline = time.monotonic() + timeout
    files: dict[str, str] = {}
    while time.monotonic() < deadline:
        files = _spec_files(page, base)
        if relative_path in files:
            return files
        time.sleep(0.3)
    return files


def _enter_edit_mode(page) -> None:
    """Turn on the real edit toggle (the fixture repo is on a working branch,
    so this activates directly instead of raising the branch modal)."""
    page.click("#edit-toggle")
    page.wait_for_selector("body.edit-mode", timeout=10_000)


_FILTERS_READY = """
() => typeof filterGroups !== 'undefined'
      && !!filterGroups.level
      && !!filterGroups.repo
      && typeof editState !== 'undefined'
      && Array.isArray(editState.treeData)
      && editState.treeData.length > 0
"""


_VOCABULARY = """
() => ({
    levels: filterGroups.level.buttons.map(b => b.key),
    statuses: filterGroups.status.buttons.map(b => b.key),
    carriedLevels: Array.from(new Set(
        editState.treeData.filter(r => r.level).map(r => r.level))),
    carriedStatuses: Array.from(new Set(
        editState.treeData.filter(r => r.level).map(r => (r.status || '').toLowerCase()))),
})
"""


# Every group is put in its unconstrained state first, because the status group
# starts with the default-hidden statuses off and a scope naming only a level
# would otherwise be compared against a narrowing the reader never wrote.
_CLIENT_MEMBERSHIP = """
(narrowing) => {
    for (const name in filterGroups) {
        const g = filterGroups[name];
        g._on = new Set(g.buttons.map(b => b.key));
    }
    for (const name in narrowing) {
        if (narrowing[name] !== null) filterGroups[name]._on = new Set(narrowing[name]);
    }
    const seen = new Set();
    const selected = [];
    for (const row of editState.treeData) {
        if (seen.has(row.id)) continue;
        seen.add(row.id);
        if (!row.level) continue;   // the requirement tab shows requirements
        let match = true;
        for (const name in filterGroups) {
            if (!filterGroups[name].matches(row)) { match = false; break; }
        }
        if (match) selected.push(row.id);
    }
    return selected.sort();
}
"""


def _client_scope_membership(page, **narrowing) -> list[str]:
    """What the viewer shows, evaluated by the viewer's own filter groups."""
    return page.evaluate(_CLIENT_MEMBERSHIP, dict(narrowing))


def _authority_scope_membership(page, viewer_url: str, params: str = "") -> list[str]:
    """What ``scoped_requirements`` yields, asked over the wire."""
    resp = page.request.get(f"{viewer_url}/api/scope{('?' + params) if params else ''}")
    assert resp.status == 200, f"/api/scope returned {resp.status}"
    return sorted(resp.json()["ids"])


@pytest.fixture(scope="session")
def viewer_url_environments(tmp_path_factory):
    """Start a viewer against the viewer-environments fixture.

    The fixture holds one test reported once for each of two browser
    projects, in one artifact, with the project in each suite's `hostname`.
    Yields the base URL.
    """
    elspais_bin = resolve_elspais()
    if elspais_bin is None:
        pytest.skip("elspais CLI not found on PATH")

    src = REPO_ROOT / "tests" / "fixtures" / "viewer-environments"
    if not src.exists():
        pytest.skip(f"viewer-environments fixture not present at {src}")

    dest = tmp_path_factory.mktemp("viewer-environments-run")
    for item in src.iterdir():
        if item.is_dir():
            shutil.copytree(item, dest / item.name)
        else:
            shutil.copy2(item, dest / item.name)

    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "test",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "test",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    subprocess.run(["git", "init"], cwd=dest, capture_output=True, env=env)
    subprocess.run(["git", "add", "."], cwd=dest, capture_output=True, env=env)
    subprocess.run(["git", "commit", "-m", "init"], cwd=dest, capture_output=True, env=env)

    base_url = ""

    proc, log_path = _spawn_viewer(
        [elspais_bin, "viewer", "--server", "--port", "0", "--path", str(dest)],
        cwd=str(dest),
    )

    try:
        base_url = _await_viewer(proc, log_path, dest)
        yield base_url
    finally:
        try:
            import urllib.request

            req = urllib.request.Request(f"{base_url}/api/shutdown", method="POST")
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            pass

        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                proc.wait(timeout=5)


@pytest.fixture()
def page_environments(viewer_url_environments):
    """Launch headless Chromium against the environments-fixture viewer."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        pg = context.new_page()
        pg.set_default_timeout(10_000)
        yield pg
        browser.close()


def _open_results_panel(page, req_id: str, label: str):
    """Open a requirement's card and the Passing panel for one assertion.

    The card has two panels over the same data. Tested draws one row for each
    TEST, with the verdict of that test's results rolled into it. Passing
    draws one row for each RESULT, which is where an environment belongs: it
    is a fact about one run, not about the test.
    """
    page.evaluate(f"() => window.openCard('{req_id}')")
    panel = page.locator(f"#assertion-results-{req_id}-{label}")
    panel.wait_for(state="attached", timeout=10_000)
    page.locator("[onclick*=toggleAssertionResults]").first.click()
    return panel


# The session-lifetime viewer's grace and check interval. The grace is the
# window a tab has to connect after the viewer starts, and the window a
# lost stream has to come back: it is counted from the viewer's start, so
# it is sized for a slow runner to become ready and load the page inside
# it. The check runs many times within it, so the test observes the rule
# holding the viewer open through checks that find nothing held.
_SESSION_GRACE_SECONDS = 8.0


_SESSION_CHECK_SECONDS = 0.5


def _session_lifetime_viewer(tmp_path_factory):
    """A viewer started to serve browser sessions, checking every few seconds.

    Its clients are pages and nothing else, so it is watched with no pid;
    the grace is a few seconds, so the test observes both halves of the rule
    within its patience.
    """
    elspais_bin = resolve_elspais()
    if elspais_bin is None:
        pytest.skip("elspais CLI not found on PATH")
    src = REPO_ROOT / "tests" / "fixtures" / "viewer-tables"
    if not src.exists():
        pytest.skip(f"viewer-tables fixture not present at {src}")

    dest = tmp_path_factory.mktemp("viewer-session-lifetime")
    for item in src.iterdir():
        if item.is_dir():
            shutil.copytree(item, dest / item.name)
        else:
            shutil.copy2(item, dest / item.name)

    proc, log_path = _spawn_viewer(
        [
            elspais_bin,
            "viewer",
            "--server",
            "--session-lifetime",
            "--port",
            "0",
            "--path",
            str(dest),
        ],
        cwd=str(dest),
        env={
            **os.environ,
            "_ELSPAIS_CLIENT_CHECK_INTERVAL": str(_SESSION_CHECK_SECONDS),
            "_ELSPAIS_CLIENT_GRACE": str(_SESSION_GRACE_SECONDS),
            "_ELSPAIS_EVENTS_HEARTBEAT": "2",
        },
    )
    return proc, log_path, dest


def _await_process_exit(proc: subprocess.Popen, seconds: float) -> bool:
    try:
        proc.wait(timeout=seconds)
    except subprocess.TimeoutExpired:
        return False
    return True


def _end_viewer(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            proc.wait(timeout=5)


_BASE_PATH = "/w/abc"


def _copy_project(src: Path, dest: Path) -> None:
    """Copy a fixture project into ``dest`` and make it a git repository."""
    for item in src.iterdir():
        if item.is_dir():
            shutil.copytree(item, dest / item.name)
        else:
            shutil.copy2(item, dest / item.name)
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "test",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "test",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    subprocess.run(["git", "init"], cwd=dest, capture_output=True, env=env)
    subprocess.run(["git", "add", "."], cwd=dest, capture_output=True, env=env)
    subprocess.run(["git", "commit", "-m", "init"], cwd=dest, capture_output=True, env=env)


@pytest.fixture(scope="session")
def prefixed_viewer(tmp_path_factory):
    """A viewer started with ``--base-path`` over its own copy of the
    viewer-tables project. Yields ``(root_url, prefixed_url, log_path,
    project_dir)``.

    Its own project, not this repository: a viewer serving a directory
    stops whichever daemon already serves it, and the session fixture over
    the repository would be the casualty.
    """
    elspais_bin = resolve_elspais()
    if elspais_bin is None:
        pytest.skip("elspais CLI not found on PATH")

    src = REPO_ROOT / "tests" / "fixtures" / "viewer-tables"
    if not src.exists():
        pytest.skip(f"viewer-tables fixture not present at {src}")
    dest = tmp_path_factory.mktemp("viewer-prefixed-run")
    _copy_project(src, dest)

    base_url = ""

    proc, log_path = _spawn_viewer(
        [
            elspais_bin,
            "viewer",
            "--server",
            "--port",
            "0",
            "--base-path",
            _BASE_PATH,
            "--path",
            str(dest),
        ],
        cwd=str(dest),
    )

    try:
        root_url = _await_viewer(proc, log_path, dest, base_path=_BASE_PATH)
        base_url = root_url + _BASE_PATH
        yield root_url, base_url, log_path, dest
    finally:
        try:
            import urllib.request

            req = urllib.request.Request(f"{base_url}/api/shutdown", method="POST")
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            pass

        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                proc.wait(timeout=5)


@pytest.fixture()
def page_prefixed(prefixed_viewer):
    """Launch headless Chromium against the prefixed viewer."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        pg = context.new_page()
        pg.set_default_timeout(10_000)
        yield pg
        browser.close()


# A second prefix, for a second viewer the browser sees at the same origin as
# the ``prefixed_viewer`` one -- the layout of a hub serving workspaces.
_SECOND_BASE_PATH = "/w/xyz"


# A fake origin the browser loads both prefixed viewers from. Requests to it
# are answered in the test (``_route_hub``), so it needs no resolver.
_HUB_ORIGIN = "http://hub.test"


# The filter typed and the card opened as the Project State under test.
_REMEMBERED_FILTER = "Rendering"


_REMEMBERED_CARD = "REQ-p00001"


_REMEMBERED_CARD_TITLE = "Table Rendering Example"


# A save follows a change: the filter's is behind a debounce and a search
# round-trip, so a page is held this long before the reader moves on.
_SAVE_SETTLE_MS = 1_000


# How long a reopened page is given to restore cards, which it fetches.
_RESTORE_SETTLE_MS = 1_500


@pytest.fixture(scope="module")
def static_viewer_site(tmp_path_factory):
    """One static viewer page served at ``/``, ``/a/`` and ``/b/`` of two
    origins. Yields ``(first_origin, second_origin)``, each without a
    trailing slash.

    The page is generated with ``--embed-content``: without it a static page
    carries no tree and no nodes, so there would be no card to open. Both
    servers serve the same directory, so the same page stands at the same
    paths on two ports of one host.
    """
    import functools
    import http.server
    import threading

    elspais_bin = resolve_elspais()
    if elspais_bin is None:
        pytest.skip("elspais CLI not found on PATH")

    src = REPO_ROOT / "tests" / "fixtures" / "viewer-tables"
    if not src.exists():
        pytest.skip(f"viewer-tables fixture not present at {src}")
    project = tmp_path_factory.mktemp("remembered-static-project")
    _copy_project(src, project)

    site = tmp_path_factory.mktemp("remembered-static-site")
    page_file = site / "index.html"
    result = subprocess.run(
        [
            elspais_bin,
            "viewer",
            "--static",
            "--embed-content",
            "-o",
            str(page_file),
            "--path",
            str(project),
        ],
        cwd=str(project),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert _REMEMBERED_CARD in embedded_data(page_file.read_text(encoding="utf-8"))["nodes"], (
        "the static page embedded no nodes"
    )
    for sub in ("a", "b"):
        (site / sub).mkdir()
        shutil.copy2(page_file, site / sub / "index.html")

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    handler = functools.partial(Quiet, directory=str(site))
    servers = []
    try:
        for _ in range(2):
            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            servers.append(server)
        yield tuple(f"http://127.0.0.1:{s.server_address[1]}" for s in servers)
    finally:
        for server in servers:
            server.shutdown()
            server.server_close()


@pytest.fixture(scope="module")
def second_prefixed_viewer(tmp_path_factory):
    """A second viewer started with ``--base-path``, under a prefix other
    than ``prefixed_viewer``'s, over its own copy of the same project.
    Yields ``(root_url, prefixed_url)``.

    Its own copy for the reason ``prefixed_viewer`` gives. The same project
    name is kept on purpose: two workspaces of one project under one hub is
    the case in which a name-keyed memory is shared.
    """
    elspais_bin = resolve_elspais()
    if elspais_bin is None:
        pytest.skip("elspais CLI not found on PATH")

    src = REPO_ROOT / "tests" / "fixtures" / "viewer-tables"
    if not src.exists():
        pytest.skip(f"viewer-tables fixture not present at {src}")
    dest = tmp_path_factory.mktemp("viewer-second-prefixed-run")
    _copy_project(src, dest)

    base_url = ""

    proc, log_path = _spawn_viewer(
        [
            elspais_bin,
            "viewer",
            "--server",
            "--port",
            "0",
            "--base-path",
            _SECOND_BASE_PATH,
            "--path",
            str(dest),
        ],
        cwd=str(dest),
    )

    try:
        root_url = _await_viewer(proc, log_path, dest, base_path=_SECOND_BASE_PATH)
        base_url = root_url + _SECOND_BASE_PATH
        yield root_url, base_url
    finally:
        try:
            import urllib.request

            req = urllib.request.Request(f"{base_url}/api/shutdown", method="POST")
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            pass

        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                proc.wait(timeout=5)


@pytest.fixture()
def remembering_context():
    """One fresh browser context: one reader's browser, shared by every page
    a test opens in it, and by nothing another test opened."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        context.set_default_timeout(10_000)
        yield context
        browser.close()


def _route_hub(context, backends: dict[str, str]) -> None:
    """Answer ``_HUB_ORIGIN`` by forwarding each request to the viewer whose
    prefix it starts with -- one origin in front of several prefixed viewers,
    as a hub presents them.

    The event stream is refused rather than forwarded: a forwarded request
    is answered only once its whole body has arrived, and that stream's
    body never ends.
    """
    prefixes = sorted(backends, key=len, reverse=True)

    def handle(route):
        path = route.request.url[len(_HUB_ORIGIN) :]
        if "/api/events" in path:
            route.abort()
            return
        for prefix in prefixes:
            if path == prefix or path.startswith(prefix + "/"):
                response = route.fetch(url=backends[prefix] + path)
                route.fulfill(response=response)
                return
        route.fulfill(status=404, body="")

    context.route(f"{_HUB_ORIGIN}/**", handle)


def _open_viewer(context, url: str):
    """Open ``url`` in a new page of ``context`` once the page has settled."""
    page = context.new_page()
    page.goto(url, wait_until="networkidle", timeout=_PAGE_LOAD_TIMEOUT)
    page.locator("#edit-filter-text").wait_for(state="attached")
    page.wait_for_timeout(_RESTORE_SETTLE_MS)
    return page


def _leave_project_state(page) -> None:
    """Type a filter and open a card, as a reader would, and let it save."""
    page.fill("#edit-filter-text", _REMEMBERED_FILTER)
    page.evaluate("(id) => window.openCard(id)", _REMEMBERED_CARD)
    page.locator("#card-stack-body").filter(has_text=_REMEMBERED_CARD_TITLE).wait_for(
        state="visible"
    )
    page.wait_for_timeout(_SAVE_SETTLE_MS)


def _project_state(page) -> dict:
    """What of the Project State under test the page is showing."""
    return {
        "filter": page.input_value("#edit-filter-text"),
        "card_open": _REMEMBERED_CARD_TITLE in page.locator("#card-stack-body").inner_text(),
    }


_NO_PROJECT_STATE = {"filter": "", "card_open": False}


_LEFT_PROJECT_STATE = {"filter": _REMEMBERED_FILTER, "card_open": True}


def _leave_reader_preferences(page) -> None:
    """Choose the dark theme and a larger font, and let it save."""
    page.evaluate("() => { setTheme('dark'); adjustFontSize(2); }")
    page.wait_for_timeout(_SAVE_SETTLE_MS)


def _reader_preferences(page) -> dict:
    """The theme and the font size the page is applying."""
    return page.evaluate(
        """() => ({
            dark: document.documentElement.classList.contains('theme-dark'),
            fontSize: document.documentElement.style.fontSize || null,
        })"""
    )


_LEFT_READER_PREFERENCES = {"dark": True, "fontSize": "16px"}


def _pr_route_recorder(page, answer: dict, status: int = 200) -> list[dict]:
    """Answer the pull-request route from here, recording what the page sent.

    The route itself is exercised by its own tests; what is under test here
    is what the page puts into it and what it does with the answer.
    """
    sent: list[dict] = []

    def handle(route):
        request = route.request
        sent.append(json.loads(request.post_data or "{}"))
        route.fulfill(
            status=status,
            content_type="application/json",
            body=json.dumps(answer),
        )

    page.route("**/api/git/pr", handle)
    return sent


def _offer(page, result: dict) -> None:
    """Offer the proposal for a push that answered with ``result``."""
    page.evaluate("(result) => offerPullRequest(result)", result)


_EDIT_CONTROLS_CITED = "REQ-p00001"


_EDIT_CONTROLS_CITING = "REQ-d00001"


_EDIT_CONTROLS_TOML = """version = 5

[project]
name = "edit-controls-fixture"
namespace = "REQ"

[rules.format]
require_hash = false
"""


_EDIT_CONTROLS_PRD = f"""# Product

## {_EDIT_CONTROLS_CITED}: Cited Requirement

**Level**: prd | **Status**: Active

The cited requirement.

### Assertions

A. The tool SHALL be cited.

*End* *Cited Requirement*
"""


# The file opens with a blank line: a highlighter that drops it moves every
# line number after it (REQ-d00321-A).
_EDIT_CONTROLS_DEV = f"""
# Dev

## {_EDIT_CONTROLS_CITING}: Citing Requirement

**Level**: dev | **Status**: Active | **Implements**: {_EDIT_CONTROLS_CITED}

The citing requirement.

### Assertions

A. The tool SHALL cite.

*End* *Citing Requirement*
"""


def _worktree_env() -> dict:
    """The environment that runs this worktree's own elspais package."""
    env = dict(os.environ)
    worktree_src = str(REPO_ROOT / "src")
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{worktree_src}:{existing}" if existing else worktree_src
    return env


def _write_edit_controls_project(dest: Path) -> None:
    """A project holding one relationship, as a git repository on a working branch."""
    (dest / "spec").mkdir()
    (dest / ".elspais.toml").write_text(_EDIT_CONTROLS_TOML, encoding="utf-8")
    (dest / "spec" / "prd.md").write_text(_EDIT_CONTROLS_PRD, encoding="utf-8")
    (dest / "spec" / "dev.md").write_text(_EDIT_CONTROLS_DEV, encoding="utf-8")
    _commit_on_working_branch(dest, "edit-controls")


def _commit_on_working_branch(dest: Path, branch: str) -> None:
    """Make ``dest`` a git repository with its files committed, on ``branch``."""
    git_env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "test",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "test",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    for argv in (
        ["git", "init"],
        ["git", "add", "."],
        ["git", "commit", "-m", "init"],
        ["git", "checkout", "-b", branch],
    ):
        subprocess.run(argv, cwd=dest, capture_output=True, env=git_env, check=True)


@contextlib.contextmanager
def _served_viewer(dest: Path):
    """Serve ``dest`` with a viewer run from this worktree's source; yield its URL."""
    base_url = ""
    proc, log_path = _spawn_viewer(
        [
            sys.executable,
            "-m",
            "elspais",
            "viewer",
            "--server",
            "--port",
            "0",
            "--path",
            str(dest),
        ],
        cwd=str(dest),
        env=_worktree_env(),
    )
    try:
        base_url = _await_viewer(proc, log_path, dest)
        yield base_url
    finally:
        try:
            import urllib.request

            req = urllib.request.Request(f"{base_url}/api/shutdown", method="POST")
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                proc.wait(timeout=5)


@pytest.fixture(scope="module")
def edit_controls_viewer_url(tmp_path_factory):
    """A viewer, run from this worktree's source, over a private project.

    Private because the relationship-type test changes a relationship. The
    project is on a working branch so the edit toggle activates directly.
    """
    dest = tmp_path_factory.mktemp("viewer-edit-controls")
    _write_edit_controls_project(dest)
    with _served_viewer(dest) as base_url:
        yield base_url


@pytest.fixture()
def page_edit_controls(edit_controls_viewer_url):
    """Launch headless Chromium against the edit-controls viewer."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        pg = context.new_page()
        pg.set_default_timeout(10_000)
        yield pg
        browser.close()


def _requests_to(page, path: str) -> list:
    """Record every request the page makes whose URL path ends with ``path``."""
    seen: list = []
    page.on(
        "request", lambda req: seen.append(req) if req.url.split("?")[0].endswith(path) else None
    )
    return seen


@pytest.fixture(scope="module")
def save_disclosure_viewer_url(tmp_path_factory):
    """A viewer over a canonical project whose one file holds an untidy neighbour.

    The neighbour requirement and the file-level prose beside the requirement
    the test edits are out of canonical form, so a save of that edit rewrites
    them. Private because the test saves to disk.
    """
    from tests.core.graph_test_helpers import (
        MARKED_PROSE,
        TIDY_NEIGHBOUR,
        UNMARKED_PROSE,
        UNTIDY_NEIGHBOUR,
        replace_in_file,
        write_canonical_repo,
    )

    dest = tmp_path_factory.mktemp("viewer-save-disclosure")
    spec = write_canonical_repo(dest)
    replace_in_file(spec / "dev.md", TIDY_NEIGHBOUR, UNTIDY_NEIGHBOUR)
    replace_in_file(spec / "dev.md", MARKED_PROSE, UNMARKED_PROSE)
    # The edited requirement is a Draft: the page's own save sends no changelog
    # reason, which a change to an Active requirement needs.
    replace_in_file(
        spec / "dev.md",
        "**Status**: Active | **Implements**: -\n\nBeta body.",
        "**Status**: Draft | **Implements**: -\n\nBeta body.",
    )
    _commit_on_working_branch(dest, "save-disclosure")
    with _served_viewer(dest) as base_url:
        yield base_url


@pytest.fixture()
def page_save_disclosure(save_disclosure_viewer_url):
    """Launch headless Chromium against the save-disclosure viewer."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_context().new_page()
        pg.set_default_timeout(10_000)
        yield pg
        browser.close()


@pytest.fixture(scope="module")
def refused_save_viewer(tmp_path_factory):
    """A viewer over a project whose Active requirement a page save cannot write.

    The page's save sends no changelog reason, which a change to an Active
    requirement needs. Private because the test edits the graph. Yields the
    viewer's URL and the project directory.
    """
    dest = tmp_path_factory.mktemp("viewer-refused-save")
    _write_edit_controls_project(dest)
    with _served_viewer(dest) as base_url:
        yield base_url, dest


@pytest.fixture()
def page_refused_save(refused_save_viewer):
    """Launch headless Chromium against the refused-save viewer."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_context().new_page()
        pg.set_default_timeout(10_000)
        yield pg
        browser.close()


# A requirement whose text holds non-ASCII characters, and a file whose text
# holds a script closer and a comment opener, so the restored content is
# checked against text that compression and its decoding could mangle.
_EMBEDDED_NOTES_REQ = "REQ-d00002"


_EMBEDDED_NOTES_ASSERTION = "The tool SHALL keep na\u00efve caf\u00e9 notes \u2014 \u2713."


_EMBEDDED_NOTES_SPEC = f"""# Notes

## {_EMBEDDED_NOTES_REQ}: Notes Requirement

**Level**: dev | **Status**: Active

The notes requirement.

### Assertions

A. {_EMBEDDED_NOTES_ASSERTION}

*End* *Notes Requirement*

Trailing note: </script><!-- not a comment --> \u2713
"""


def _restored_source_panel(page, req_id: str, file_name: str) -> list[str]:
    """Open ``req_id``'s card, open its file in the source panel, and return
    the text of each numbered line the panel shows."""
    page.evaluate(f"() => window.openCard('{req_id}')")
    card = page.locator(f"#card-{req_id}")
    card.wait_for(state="visible", timeout=10_000)
    card.locator("a", has_text=f"{file_name}:").first.click()
    page.wait_for_selector("#fv-body .source-line")
    source_mode = page.locator(".file-viewer-mode-btn[data-mode='source']")
    if source_mode.is_visible():
        source_mode.click()
    page.wait_for_selector("#fv-body code.line-content")
    return page.locator("#fv-body .line-content").all_text_contents()


def _file_lines(path: Path) -> list[str]:
    """A file's text line by line, without the empty line after a final newline."""
    lines = path.read_text(encoding="utf-8").split("\n")
    if lines[-1] == "":
        lines.pop()
    return lines


@pytest.fixture(scope="module")
def embedded_static_page(tmp_path_factory) -> tuple[str, Path]:
    """A static page with embedded content, generated by this worktree's source.

    Yields the page's ``file://`` URL and the project it was generated from.
    """
    project = tmp_path_factory.mktemp("embedded-static-project")
    _write_edit_controls_project(project)
    (project / "spec" / "notes.md").write_text(_EMBEDDED_NOTES_SPEC, encoding="utf-8")
    page_file = tmp_path_factory.mktemp("embedded-static-site") / "index.html"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "elspais",
            "viewer",
            "--static",
            "--embed-content",
            "-o",
            str(page_file),
            "--path",
            str(project),
        ],
        cwd=str(project),
        env=_worktree_env(),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return page_file.as_uri(), project
