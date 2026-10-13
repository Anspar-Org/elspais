"""Playwright-based browser test: a card marks only the terms its member reads.

The fixture federates APP with its associate LIB. APP defines *Role*, LIB
defines *Session*, and each assertion uses both words. APP reads both terms;
LIB reads only its own.
"""

import os
import shutil
import subprocess

import pytest

pytest.importorskip("playwright", reason="playwright not installed")
from playwright.sync_api import sync_playwright  # noqa: E402

from ..conftest import REPO_ROOT  # noqa: E402
from ..helpers import resolve_elspais  # noqa: E402
from .support import _served_viewer  # noqa: E402

pytestmark = [
    pytest.mark.browser,
    pytest.mark.skipif(
        resolve_elspais() is None,
        reason="elspais CLI not found on PATH",
    ),
]

_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "viewer-term-scope"


@pytest.fixture(scope="module")
def term_scope_viewer(tmp_path_factory):
    """A viewer serving a copy of the fixture's APP, with LIB beside it."""
    dest = tmp_path_factory.mktemp("viewer-term-scope")
    git_env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "test",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "test",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    for member in ("app", "library"):
        shutil.copytree(_FIXTURE / member, dest / member)
        for argv in (["git", "init"], ["git", "add", "."], ["git", "commit", "-m", "init"]):
            subprocess.run(argv, cwd=dest / member, capture_output=True, env=git_env, check=True)
    with _served_viewer(dest / "app") as base_url:
        yield base_url


@pytest.fixture()
def page_term_scope(term_scope_viewer):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_context().new_page()
        pg.set_default_timeout(10_000)
        yield pg
        browser.close()


def _highlighted_terms(page, req_id: str) -> list[str]:
    """Open *req_id*'s card and return the term keys its assertion marks."""
    page.evaluate(f"() => window.openCard('{req_id}')")
    selector = f"#card-{req_id} .card-assertion-text"
    page.wait_for_selector(selector, timeout=10_000)
    return page.eval_on_selector_all(
        f"{selector} .defined-term",
        "els => els.map(e => e.getAttribute('data-term-key')).sort()",
    )


class TestBrowserTermScope:
    """Validates REQ-d00239-E."""

    # Verifies: REQ-d00239-E
    @pytest.mark.browser
    @pytest.mark.e2e
    def test_REQ_d00239_E_a_card_marks_only_the_terms_its_member_reads(
        self, page_term_scope, term_scope_viewer
    ):
        page = page_term_scope
        page.goto(term_scope_viewer, wait_until="networkidle")
        page.wait_for_function(
            "() => editState.termsLookup && Object.keys(editState.termsLookup).length === 2",
            timeout=10_000,
        )

        # The library's "role" is its own plain word; its own term is marked.
        assert _highlighted_terms(page, "LIB-d00001") == ["session"]
        # The consumer marks its own term and the library's.
        assert _highlighted_terms(page, "APP-d00001") == ["role", "session"]
