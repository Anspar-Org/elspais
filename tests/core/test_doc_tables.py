"""The documentation tables the program renders from its own definitions.

Validates REQ-d00286-E: a set the program defines and the documentation
presents is presented from that definition, so the two cannot disagree.

Each test here regenerates one fragment and asserts nothing moved. A failure
means the definition gained, lost or changed an entry and the published table
did not follow -- which is the drift the requirement exists to remove, so the
message names the command that resolves it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from elspais.utilities.doc_tables import (
    check_categories,
    command_entries,
    documents,
    renderers,
    splice,
)
from elspais.utilities.findings import REGISTRY
from elspais.utilities.md_renderer import render_markdown

REGENERATE = "python -m elspais.utilities.doc_tables"

_REPO_ROOT = Path(__file__).resolve().parents[2]
COMMANDS_DOC = _REPO_ROOT / "src" / "elspais" / "docs" / "cli" / "commands.md"


def _presentations() -> list[tuple[str, Path]]:
    """Every (fragment, document) pair the shipped documentation presents."""
    return [(name, document.path) for document in documents() for name in document.names]


def _presentation_ids() -> list[str]:
    return [f"{name}@{path.name}" for name, path in _presentations()]


class TestFragmentsMatchTheirDefinitions:
    """Validates REQ-d00286-E: regenerating a published table changes nothing."""

    # Verifies: REQ-d00286-E
    @pytest.mark.parametrize(("name", "path"), _presentations(), ids=_presentation_ids())
    def test_REQ_d00286_E_regeneration_is_a_no_op(self, name: str, path: Path) -> None:
        """Every presented fragment already says what the program defines."""
        render = renderers().get(name)
        assert render is not None, (
            f"{path} presents a fragment named {name!r} that nothing renders. "
            f"Known fragments: {', '.join(sorted(renderers()))}."
        )
        original = path.read_text(encoding="utf-8")
        assert splice(original, name, render()) == original, (
            f"The {name!r} table in {path} no longer matches the definition it is "
            f"rendered from -- the program's set has moved and the published table "
            f"has not. Regenerate with: {REGENERATE}"
        )

    # Verifies: REQ-d00286-E
    def test_REQ_d00286_E_every_set_is_presented_somewhere(self) -> None:
        """A table the program can render that no topic shows is a set with no
        published answer, which is the same failure seen from the other side."""
        presented = {name for name, _ in _presentations()}
        assert set(renderers()) == presented, (
            f"These sets are rendered by nothing the documentation presents: "
            f"{', '.join(sorted(set(renderers()) - presented))}. Add the marker pair "
            f"to the topic that should present each, then run: {REGENERATE}"
        )


class TestCheckCatalogCoversTheRegistry:
    """Validates REQ-d00286-E for the catalog of health checks."""

    # Verifies: REQ-d00286-E
    def test_REQ_d00286_E_every_registered_check_is_catalogued(self) -> None:
        """The catalog is grouped by category, so every category the registry
        holds must be presented -- otherwise a check the tool runs appears in
        no published table at all."""
        catalogued: set[str] = set()
        for document in documents():
            text = document.path.read_text(encoding="utf-8")
            for name in document.names:
                if not name.startswith("check-catalog:"):
                    continue
                category = name.split(":", 1)[1]
                for rule in REGISTRY.values():
                    if rule.category != category:
                        continue
                    assert f"| `{rule.name}` |" in text, (
                        f"{rule.name} reports under the {category!r} category, which "
                        f"{document.path} presents, but no row names it. "
                        f"Regenerate with: {REGENERATE}"
                    )
                    catalogued.add(rule.name)

        missing = sorted(set(REGISTRY) - catalogued)
        assert not missing, (
            f"These registered checks appear in no published catalog: "
            f"{', '.join(missing)}. Their categories "
            f"({', '.join(sorted({REGISTRY[m].category for m in missing}))}) need a "
            f"section in checks.md holding the matching marker pair, then: {REGENERATE}"
        )

    # Verifies: REQ-d00286-E
    def test_REQ_d00286_E_each_check_is_catalogued_once(self) -> None:
        """One category, one table: a check listed twice is a check whose two
        entries can disagree."""
        presented = [
            name.split(":", 1)[1]
            for _, names in ((d.path, d.names) for d in documents())
            for name in names
            if name.startswith("check-catalog:")
        ]
        assert len(presented) == len(set(presented)), (
            f"A check category is presented more than once: {sorted(presented)}"
        )
        assert set(presented) == set(check_categories()), (
            f"The categories presented ({sorted(set(presented))}) are not the "
            f"categories the registry holds ({check_categories()})."
        )

    # Verifies: REQ-d00286-E
    def test_REQ_d00286_E_every_check_carries_a_description_and_a_remedy(self) -> None:
        """The catalog is rendered from these fields, so an empty one reaches a
        reader as an empty cell."""
        for rule in REGISTRY.values():
            assert rule.description, f"{rule.name} is registered without a description"
            assert rule.remedy, f"{rule.name} is registered without a remedy"


class TestCommandIndex:
    """Validates REQ-d00286-C+E: every command is indexed and documented."""

    # Verifies: REQ-d00286-E
    def test_REQ_d00286_E_index_names_every_command(self) -> None:
        """The index is rendered from the command union, so it names what the
        CLI dispatches on rather than what someone remembered to add."""
        text = COMMANDS_DOC.read_text(encoding="utf-8")
        for name, _group, _description in command_entries():
            assert f"| `{name}` |" in text, (
                f"The command index does not name {name!r}. Regenerate with: {REGENERATE}"
            )

    # Verifies: REQ-d00286-C
    def test_REQ_d00286_C_every_command_has_a_section(self) -> None:
        """A command a user can run and cannot read about is, to them,
        indistinguishable from one that does not work."""
        headings: set[str] = set()
        for line in COMMANDS_DOC.read_text(encoding="utf-8").splitlines():
            if line.startswith("## "):
                headings.update(token.strip() for token in line[3:].split("/"))
        missing = [name for name, _, _ in command_entries() if name not in headings]
        assert not missing, (
            f"These commands have no section in commands.md: {', '.join(missing)}. "
            f"Write one for each -- the index alone says a command exists without "
            f"saying how to use it."
        )


class TestMarkersAreInvisibleToAReader:
    """Validates REQ-d00286-B: the marked-up source renders as the reader's text."""

    # Verifies: REQ-d00286-B
    def test_REQ_d00286_B_marker_lines_do_not_reach_the_terminal(self) -> None:
        """A whole-line HTML comment renders as nothing, as it does on the web."""
        rendered = render_markdown(
            "before\n<!-- generated: comment-patterns -->\nafter", use_color=False
        )
        assert "<!--" not in rendered
        assert "before" in rendered and "after" in rendered

    # Verifies: REQ-d00286-B
    def test_REQ_d00286_B_a_comment_inside_a_fence_is_content(self) -> None:
        """An example showing a block comment is the thing being explained."""
        rendered = render_markdown(
            "```html\n<!-- Implements: REQ-d00001-A -->\n```", use_color=False
        )
        assert "<!-- Implements: REQ-d00001-A -->" in rendered

    # Verifies: REQ-d00286-B
    def test_REQ_d00286_B_a_mid_line_comment_is_left_alone(self) -> None:
        """Only a whole line is a marker; text around one is prose."""
        rendered = render_markdown("text <!-- note --> more", use_color=False)
        assert "text <!-- note --> more" in rendered
