"""
elspais - Requirements validation and traceability tools

L-Space is the ultimate library, connecting all libraries everywhere
through the sheer weight of accumulated knowledge.
    — Terry Pratchett

elspais validates requirement formats, generates traceability matrices,
and supports multi-repository requirement management with configurable
ID patterns and validation rules.
"""

from importlib.metadata import PackageNotFoundError, version


def _resolve_version() -> str:
    """Get version, preferring pyproject.toml for editable installs."""
    from pathlib import Path

    # Check for pyproject.toml relative to this package (editable install)
    pyproject = Path(__file__).resolve().parent.parent.parent / "pyproject.toml"
    if pyproject.is_file():
        try:
            import tomllib
        except ModuleNotFoundError:
            import tomli as tomllib  # type: ignore[no-redef]
        try:
            data = tomllib.loads(pyproject.read_text())
            v = data.get("project", {}).get("version")
            if v:
                return v
        except Exception:
            pass
    # Fallback to installed metadata
    try:
        return version("elspais")
    except PackageNotFoundError:
        return "0.0.0+unknown"


__version__ = _resolve_version()
__author__ = "Anspar"
__license__ = "MIT"

from elspais.utilities.patterns import IdPatternConfig, IdResolver  # noqa: E402

__all__ = [
    "__version__",
    "IdPatternConfig",
    "IdResolver",
]
