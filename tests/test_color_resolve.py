"""Tests for utilities.color.resolve_color()."""

# Verifies: REQ-d00212-A, REQ-d00212-J, REQ-d00212-K

from __future__ import annotations

import pytest

from elspais.utilities.color import ResolvedColor, resolve_color


def test_configured_hex_returned_verbatim():
    rc = resolve_color("prd", "#1b3a5c")
    assert rc.bg == "#1b3a5c"


def test_uppercase_hex_accepted():
    rc = resolve_color("prd", "#1B3A5C")
    assert rc.bg == "#1B3A5C"


def test_fallback_is_deterministic():
    a = resolve_color("gui", None)
    b = resolve_color("gui", None)
    assert a == b
    assert isinstance(a, ResolvedColor)


def test_fallback_distinct_keys_get_distinct_colors():
    keys = [f"key{i:02d}" for i in range(20)]
    bgs = {resolve_color(k, None).bg for k in keys}
    # Allow a tiny collision tolerance since the hue space is mod 360.
    assert len(bgs) >= 19


def test_text_color_white_on_dark_bg():
    rc = resolve_color("dark", "#000000")
    assert rc.text == "#ffffff"


def test_text_color_dark_on_light_bg():
    rc = resolve_color("light", "#ffffff")
    assert rc.text == "#1a1a1a"


def test_fallback_uses_dark_bg_with_white_text():
    # The bounded HSL range (L=42%) keeps fallback backgrounds dark enough that
    # luminance < 0.5 holds for every hue; #ffffff is always the chosen text.
    for k in ("alpha", "beta", "gamma", "delta", "epsilon"):
        rc = resolve_color(k, None)
        assert rc.text == "#ffffff", f"unexpected text color for fallback bg of {k}: {rc}"


@pytest.mark.parametrize("bad", ["red", "#abc", "#abcdefg", "", "#GGHHII", "123abc"])
def test_invalid_configured_color_raises(bad):
    with pytest.raises(ValueError):
        resolve_color("prd", bad)


def test_none_configured_falls_back():
    # Explicit None is the documented fallback path; should not raise.
    rc = resolve_color("prd", None)
    assert rc.bg.startswith("#")
    assert len(rc.bg) == 7


def test_resolved_color_is_frozen():
    from dataclasses import FrozenInstanceError

    rc = resolve_color("prd", None)
    with pytest.raises(FrozenInstanceError):
        rc.bg = "#000000"  # type: ignore[misc]


def test_hex_with_alpha_basic():
    from elspais.utilities.color import hex_with_alpha

    assert hex_with_alpha("#1b3a5c", 0.12) == "rgba(27, 58, 92, 0.12)"


def test_hex_with_alpha_uppercase_input():
    from elspais.utilities.color import hex_with_alpha

    assert hex_with_alpha("#1B3A5C", 0.5) == "rgba(27, 58, 92, 0.5)"


def test_hex_with_alpha_rounds_alpha_to_3_decimals():
    from elspais.utilities.color import hex_with_alpha

    assert hex_with_alpha("#000000", 0.123456) == "rgba(0, 0, 0, 0.123)"


def test_hex_with_alpha_clamps_alpha_to_unit_interval():
    from elspais.utilities.color import hex_with_alpha

    assert hex_with_alpha("#000000", -0.5) == "rgba(0, 0, 0, 0.0)"
    assert hex_with_alpha("#000000", 1.5) == "rgba(0, 0, 0, 1.0)"


@pytest.mark.parametrize("bad", ["red", "#abc", "#abcdefg", ""])
def test_hex_with_alpha_rejects_bad_hex(bad):
    from elspais.utilities.color import hex_with_alpha

    with pytest.raises(ValueError):
        hex_with_alpha(bad, 0.5)
