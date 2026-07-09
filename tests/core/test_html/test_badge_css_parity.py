"""Guard: requirement-level coverage badges must have a CSS fill rule for every
unified standing color.

Regression test for the bug where `.status-badge.active.val-grey` was missing, so
a `missing`/N-A requirement dimension badge fell through to the base
`.status-badge.active` green instead of rendering grey. Server-side the color
string was correct ("grey"); only the rendered CSS was wrong — which no
color-string test could catch (REQ-d00258-H).

The per-assertion badges (`.assertion-*-btn.val-*`) already had all four rules;
this asserts the requirement header badges (`.status-badge.active.val-*`) do too.
"""

from pathlib import Path

import pytest

_CSS_DIR = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "elspais"
    / "html"
    / "templates"
    / "partials"
    / "css"
)

# The unified coverage standing -> val color-key mapping badges can render
# (full=green, partial=yellow, failing=red, missing=grey). Every one of these
# MUST have a `.status-badge.active.val-<key>` fill rule or the badge silently
# falls back to the active-status green.
_STANDING_VAL_COLORS = ["green", "yellow", "red", "grey"]


@pytest.mark.parametrize("val_color", _STANDING_VAL_COLORS)
def test_REQ_d00258_H_status_badge_has_fill_rule_for_each_standing_color(val_color):
    css = (_CSS_DIR / "_status-badges.css.j2").read_text()
    selector = f".status-badge.active.val-{val_color}"
    assert selector in css, (
        f"missing CSS fill rule '{selector} {{...}}' — a requirement dimension "
        f"badge with class val-{val_color} would fall back to the base "
        f".status-badge.active green instead of its standing color"
    )


@pytest.mark.parametrize("val_color", _STANDING_VAL_COLORS)
def test_REQ_d00258_H_assertion_badge_has_fill_rule_for_each_standing_color(val_color):
    # The per-assertion badges must stay in parity with the requirement badges so
    # an assertion badge reads identically to the requirement badge it projects.
    css = (_CSS_DIR / "_card-stack.css.j2").read_text()
    assert (
        f".assertion-tested-btn.val-{val_color}" in css
    ), f"missing per-assertion CSS fill rule for val-{val_color}"
