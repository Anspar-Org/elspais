"""Validates REQ-p00005: Legacy sponsor/YAML system removed, new system intact."""

import pytest

import elspais.associates as associates_mod


class TestLegacySymbolsRemoved:
    """Verify that legacy YAML-based sponsor/associate symbols are no longer present."""

    # Verifies: REQ-p00005
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
        # The module as imported, never reloaded: a reload replaces its class
        # objects, and every test holding the ones imported earlier then
        # fails to match what the code raises or returns.
        assert not hasattr(associates_mod, symbol), (
            f"{symbol} should have been removed from elspais.associates"
        )


class TestBuildGraphLegacyParamRemoved:
    """Verify that build_graph no longer accepts the scan_sponsors parameter."""

    # Verifies: REQ-p00005
    def test_REQ_p00005_build_graph_rejects_scan_sponsors(self):
        from elspais.graph.factory import build_graph

        with pytest.raises(TypeError, match="scan_sponsors"):
            build_graph(scan_sponsors=False)


class TestKeptFunctionalityIntact:
    """Verify that the new associate system remains importable and functional."""

    # Verifies: REQ-p00005-C
    def test_REQ_p00005_C_associate_dataclass_importable(self):
        from elspais.associates import Associate

        assert Associate is not None

    # Verifies: REQ-p00005-D
    def test_REQ_p00005_D_discover_associate_from_path_importable(self):
        from elspais.associates import discover_associate_from_path

        assert callable(discover_associate_from_path)

    # Verifies: REQ-d00202-D
    def test_REQ_d00202_D_get_associate_spec_directories_importable(self):
        from elspais.associates import get_associate_spec_directories

        assert callable(get_associate_spec_directories)
