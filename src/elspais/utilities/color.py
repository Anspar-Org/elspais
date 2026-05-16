"""Resolve display colors for configurable category keys (levels, namespaces, statuses).

Categories (level/namespace/status) are user-defined keys whose colors may be
specified in `.elspais.toml` or derived deterministically from a SHA-256 hash of
the key. The deterministic fallback keeps badge colors stable across sessions
and machines without any user configuration.
"""

from __future__ import annotations

import colorsys
import hashlib
import re
from dataclasses import dataclass

_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

# Bounded HSL ranges keep fallback backgrounds dark enough for #ffffff text
# while still producing visually distinct hues across keys.
_FALLBACK_L = 0.42
_FALLBACK_S = 0.55

_LIGHT_TEXT = "#ffffff"
_DARK_TEXT = "#1a1a1a"


@dataclass(frozen=True)
class ResolvedColor:
    bg: str
    text: str


def resolve_color(key: str, configured: str | None = None) -> ResolvedColor:
    """Return a {bg, text} pair for a category key.

    If `configured` is a 6-digit hex string, it is used as the background and
    the text color is chosen to contrast (white on dark, dark on light).
    Otherwise, a deterministic HSL color is derived from sha256(key).
    """
    if configured is not None:
        if not _HEX_RE.match(configured):
            raise ValueError(
                f'configured color must be a 6-digit hex string like "#1b3a5c"; got {configured!r}'
            )
        return ResolvedColor(bg=configured, text=_contrast_text(configured))
    bg = _hash_to_hex(key, _FALLBACK_L, _FALLBACK_S)
    return ResolvedColor(bg=bg, text=_contrast_text(bg))


def _hash_to_hex(key: str, lightness: float, saturation: float) -> str:
    """Deterministically map a key to a hex color using HSL."""
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    hue = (int.from_bytes(digest[:4], "big") % 360) / 360.0
    r, g, b = colorsys.hls_to_rgb(hue, lightness, saturation)
    return f"#{int(round(r * 255)):02x}{int(round(g * 255)):02x}{int(round(b * 255)):02x}"


def _contrast_text(bg_hex: str) -> str:
    """Pick a readable text color (white or near-black) for a background."""
    r = int(bg_hex[1:3], 16) / 255.0
    g = int(bg_hex[3:5], 16) / 255.0
    b = int(bg_hex[5:7], 16) / 255.0
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    return _LIGHT_TEXT if luminance < 0.5 else _DARK_TEXT
