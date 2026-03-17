"""Validates REQ-p00005: Legacy sponsor/YAML system removed, new system intact."""

import importlib

import pytest

import elspais.associates as associates_mod


class TestLegacySymbolsRemoved:
    """Verify that legacy YAML-based sponsor/associate symbols are no longer present."""

    @pytest.mark.parametrize(
        "symbol",
        [
            "Sponsor",
            "SponsorsConfig",
            "AssociatesConfig",
            "load_associates_config",
            "load_sponsors_config",
            "resolve_associate_spec_dir",
            "resolve_sponsor_spec_dir",
            "load_associates_yaml",
            "load_sponsors_yaml",
            "parse_yaml",
            "get_sponsor_spec_directories",
        ],
    )
    def test_REQ_p00005_legacy_symbol_not_in_module(self, symbol: str):
        # Reload to pick up any changes made during the test session
        mod = importlib.reload(associates_mod)
        assert not hasattr(
            mod, symbol
        ), f"{symbol} should have been removed from elspais.associates"


class TestBuildGraphLegacyParamRemoved:
    """Verify that build_graph no longer accepts the scan_sponsors parameter."""

    def test_REQ_p00005_build_graph_rejects_scan_sponsors(self):
        from elspais.graph.factory import build_graph

        with pytest.raises(TypeError, match="scan_sponsors"):
            build_graph(scan_sponsors=False)


class TestKeptFunctionalityIntact:
    """Verify that the new associate system remains importable and functional."""

    def test_REQ_p00005_C_associate_dataclass_importable(self):
        from elspais.associates import Associate

        assert Associate is not None

    def test_REQ_p00005_D_discover_associate_from_path_importable(self):
        from elspais.associates import discover_associate_from_path

        assert callable(discover_associate_from_path)

    def test_REQ_p00005_F_get_associate_spec_directories_importable(self):
        from elspais.associates import get_associate_spec_directories

        assert callable(get_associate_spec_directories)
