# Implements: REQ-p00006-A
"""Unified theme and help catalog -- single source of truth for UI visual semantics.

Reads theme.toml (colors, symbols, CSS classes) and help.toml (labels, descriptions)
and exposes a LegendCatalog that generates CSS custom properties and legend content.
"""
from __future__ import annotations

import functools
from dataclasses import dataclass, field
from importlib import resources
from typing import Any

import tomlkit


@dataclass
class ThemeInfo:
    name: str
    label: str
    icon: str
    tokens: dict[str, str] = field(default_factory=dict)


@dataclass
class CatalogEntry:
    key: str
    category: str
    symbol: str = ""
    css_class: str = ""
    label: str = ""
    description: str = ""
    long_description: str = ""
    color_key: str = ""  # for validation_tiers: suffix used in CSS class


# Category display names for legend grouping
_CATEGORY_LABELS: dict[str, str] = {
    "icons.coverage": "Coverage Status",
    "icons.change": "Change Indicators",
    "badges.status": "Status Badges",
    "badges.level": "Requirement Levels",
    "badges.kind": "Node Types",
    "badges.edge": "Relationship Types",
    "badges.result": "Test Results",
    "buttons.implemented": "Implementation Status",
    "buttons.validation": "Validation Status",
    "validation_tiers": "Active Badge Quality",
}


class LegendCatalog:
    def __init__(
        self,
        themes: list[ThemeInfo],
        entries: list[CatalogEntry],
    ) -> None:
        self.themes = themes
        self.entries = entries
        self._index: dict[str, CatalogEntry] = {e.key: e for e in entries}

    def theme_names(self) -> list[str]:
        return [t.name for t in self.themes]

    def by_key(self, key: str) -> CatalogEntry:
        return self._index[key]  # raises KeyError if missing

    def by_category(self, prefix: str) -> list[CatalogEntry]:
        return [e for e in self.entries if e.category == prefix]

    def grouped_entries(self) -> list[tuple[str, list[CatalogEntry]]]:
        groups: dict[str, list[CatalogEntry]] = {}
        for e in self.entries:
            groups.setdefault(e.category, []).append(e)
        return [(_CATEGORY_LABELS.get(cat, cat), entries) for cat, entries in groups.items()]

    def css_variables(self) -> str:
        lines: list[str] = []
        for i, theme in enumerate(self.themes):
            if i == 0:
                selector = f":root, .theme-{theme.name}"
            else:
                selector = f".theme-{theme.name}"
            lines.append(f"{selector} {{")
            for token, value in sorted(theme.tokens.items()):
                lines.append(f"    --{token}: {value};")
            lines.append("}")
            lines.append("")
        return "\n".join(lines)


def _load_toml(filename: str) -> dict[str, Any]:
    """Load a TOML file from the elspais.html package."""
    ref = resources.files("elspais.html").joinpath(filename)
    return tomlkit.loads(ref.read_text(encoding="utf-8"))


def _build_catalog(theme_data: dict, help_data: dict) -> LegendCatalog:
    """Join theme.toml and help.toml into a LegendCatalog."""
    # Build themes
    themes: list[ThemeInfo] = []
    for name, tdata in theme_data.get("themes", {}).items():
        themes.append(
            ThemeInfo(
                name=name,
                label=tdata.get("label", name.title()),
                icon=tdata.get("icon", ""),
                tokens=dict(tdata.get("tokens", {})),
            )
        )

    # Build entries from categorical sections in theme.toml, joined with help.toml
    entries: list[CatalogEntry] = []
    skip = {"themes", "palette"}

    def _walk(theme_section: dict, help_section: dict, prefix: str) -> None:
        for key, val in theme_section.items():
            full_key = f"{prefix}.{key}" if prefix else key
            if isinstance(val, dict) and "css_class" not in val and "symbol" not in val:
                # Nested category -- recurse
                _walk(
                    val,
                    help_section.get(key, {}) if isinstance(help_section, dict) else {},
                    full_key,
                )
            elif isinstance(val, dict):
                # Leaf entry
                h = help_section.get(key, {}) if isinstance(help_section, dict) else {}
                entries.append(
                    CatalogEntry(
                        key=full_key,
                        category=prefix,
                        symbol=val.get("symbol", ""),
                        css_class=val.get("css_class", ""),
                        color_key=val.get("color_key", ""),
                        label=h.get("label", ""),
                        description=h.get("description", ""),
                        long_description=h.get("long_description", "").strip(),
                    )
                )

    for section_key in theme_data:
        if section_key in skip:
            continue
        _walk(
            {section_key: theme_data[section_key]},
            {section_key: help_data.get(section_key, {})},
            "",
        )

    return LegendCatalog(themes=themes, entries=entries)


@functools.cache
def get_catalog() -> LegendCatalog:
    """Load and cache the LegendCatalog. Lazy -- loaded on first call."""
    theme_data = _load_toml("theme.toml")
    help_data = _load_toml("help.toml")
    return _build_catalog(theme_data, help_data)
