"""Tests for v3 ElspaisConfig restructuring (REQ-d00212-F through REQ-d00212-K).

These tests validate the NEW v3 shape of ElspaisConfig and sub-models.
They should FAIL against the current schema since the restructuring
hasn't been done yet.
"""

import pytest
from pydantic import ValidationError

from elspais.config import schema as _schema

ElspaisConfig = _schema.ElspaisConfig
IdPatternsConfig = _schema.IdPatternsConfig
HierarchyConfig = _schema.HierarchyConfig
ProjectConfig = _schema.ProjectConfig
AssociateEntryConfig = _schema.AssociateEntryConfig
LevelConfig = _schema.LevelConfig
ScanningConfig = _schema.ScanningConfig
OutputConfig = _schema.OutputConfig


# ---------------------------------------------------------------------------
# REQ-d00212-F: ElspaisConfig restructuring
# ---------------------------------------------------------------------------


class TestElspaisConfigRestructuring:
    """Validates REQ-d00212-F: ElspaisConfig restructuring."""

    def test_REQ_d00212_F_has_levels_field(self):
        """ElspaisConfig has a 'levels' field of type dict[str, LevelConfig]."""
        assert "levels" in ElspaisConfig.model_fields
        cfg = ElspaisConfig()
        assert isinstance(cfg.levels, dict)
        assert len(cfg.levels) == 3
        for key in ("prd", "ops", "dev"):
            assert key in cfg.levels
            assert isinstance(cfg.levels[key], LevelConfig)

    def test_REQ_d00212_F_levels_default_prd(self):
        """Default levels include prd with rank=1, letter='p'."""
        cfg = ElspaisConfig()
        prd = cfg.levels["prd"]
        assert prd.rank == 1
        assert prd.letter == "p"

    def test_REQ_d00212_F_levels_default_ops(self):
        """Default levels include ops with rank=2, letter='o'."""
        cfg = ElspaisConfig()
        ops = cfg.levels["ops"]
        assert ops.rank == 2
        assert ops.letter == "o"

    def test_REQ_d00212_F_levels_default_dev(self):
        """Default levels include dev with rank=3, letter='d'."""
        cfg = ElspaisConfig()
        dev = cfg.levels["dev"]
        assert dev.rank == 3
        assert dev.letter == "d"

    def test_REQ_d00212_F_has_scanning_field(self):
        """ElspaisConfig has a 'scanning' field of type ScanningConfig."""
        assert "scanning" in ElspaisConfig.model_fields
        cfg = ElspaisConfig()
        assert isinstance(cfg.scanning, ScanningConfig)

    def test_REQ_d00212_F_has_output_field(self):
        """ElspaisConfig has an 'output' field of type OutputConfig."""
        assert "output" in ElspaisConfig.model_fields
        cfg = ElspaisConfig()
        assert isinstance(cfg.output, OutputConfig)

    def test_REQ_d00212_F_no_directories_field(self):
        """ElspaisConfig does NOT have a 'directories' field."""
        assert "directories" not in ElspaisConfig.model_fields

    def test_REQ_d00212_F_no_spec_field(self):
        """ElspaisConfig does NOT have a 'spec' field."""
        assert "spec" not in ElspaisConfig.model_fields

    def test_REQ_d00212_F_no_testing_field(self):
        """ElspaisConfig does NOT have a 'testing' field."""
        assert "testing" not in ElspaisConfig.model_fields

    def test_REQ_d00212_F_no_ignore_field(self):
        """ElspaisConfig does NOT have an 'ignore' field."""
        assert "ignore" not in ElspaisConfig.model_fields

    def test_REQ_d00212_F_no_graph_field(self):
        """ElspaisConfig does NOT have a 'graph' field."""
        assert "graph" not in ElspaisConfig.model_fields

    def test_REQ_d00212_F_no_traceability_field(self):
        """ElspaisConfig does NOT have a 'traceability' field."""
        assert "traceability" not in ElspaisConfig.model_fields

    def test_REQ_d00212_F_no_core_field(self):
        """ElspaisConfig does NOT have a 'core' field."""
        assert "core" not in ElspaisConfig.model_fields

    def test_REQ_d00212_F_no_associated_field(self):
        """ElspaisConfig does NOT have an 'associated' field."""
        assert "associated" not in ElspaisConfig.model_fields

    def test_REQ_d00212_F_version_defaults_to_4(self):
        """ElspaisConfig.version defaults to 4."""
        cfg = ElspaisConfig()
        assert cfg.version == 4


# ---------------------------------------------------------------------------
# REQ-d00212-G: IdPatternsConfig changes
# ---------------------------------------------------------------------------


class TestIdPatternsConfigChanges:
    """Validates REQ-d00212-G: IdPatternsConfig changes."""

    def test_REQ_d00212_G_has_separators_field(self):
        """IdPatternsConfig has a 'separators' field (list[str])."""
        assert "separators" in IdPatternsConfig.model_fields
        cfg = IdPatternsConfig()
        assert cfg.separators == ["-", "_"]

    def test_REQ_d00212_G_has_prefix_optional_field(self):
        """IdPatternsConfig has a 'prefix_optional' field (bool, default False)."""
        assert "prefix_optional" in IdPatternsConfig.model_fields
        cfg = IdPatternsConfig()
        assert cfg.prefix_optional is False

    def test_REQ_d00212_G_no_types_field(self):
        """IdPatternsConfig does NOT have a 'types' field."""
        assert "types" not in IdPatternsConfig.model_fields

    def test_REQ_d00212_G_has_associated_field(self):
        """IdPatternsConfig has an 'associated' field with defaults."""
        assert "associated" in IdPatternsConfig.model_fields
        cfg = IdPatternsConfig()
        assert cfg.associated.enabled is False

    def test_REQ_d00212_G_canonical_uses_level_letter(self):
        """canonical default uses {level.letter} not {type.letter}."""
        cfg = IdPatternsConfig()
        assert "{level.letter}" in cfg.canonical
        assert "{type.letter}" not in cfg.canonical

    def test_REQ_d00212_G_aliases_short_uses_level_letter(self):
        """aliases.short default uses {level.letter} not {type.letter}."""
        cfg = IdPatternsConfig()
        assert "short" in cfg.aliases
        assert "{level.letter}" in cfg.aliases["short"]
        assert "{type.letter}" not in cfg.aliases["short"]


# ---------------------------------------------------------------------------
# REQ-d00212-H: HierarchyConfig is booleans only
# ---------------------------------------------------------------------------


class TestHierarchyConfigBooleansOnly:
    """Validates REQ-d00212-H: HierarchyConfig is booleans only."""

    def test_REQ_d00212_H_has_allow_circular(self):
        """HierarchyConfig has allow_circular (bool|None)."""
        assert "allow_circular" in HierarchyConfig.model_fields
        cfg = HierarchyConfig()
        assert cfg.allow_circular is None

    def test_REQ_d00212_H_has_allow_structural_orphans(self):
        """HierarchyConfig has allow_structural_orphans (bool|None)."""
        assert "allow_structural_orphans" in HierarchyConfig.model_fields
        cfg = HierarchyConfig()
        assert cfg.allow_structural_orphans is None

    def test_REQ_d00212_H_has_allow_orphans(self):
        """HierarchyConfig has allow_orphans (bool|None)."""
        assert "allow_orphans" in HierarchyConfig.model_fields
        cfg = HierarchyConfig()
        assert cfg.allow_orphans is None

    def test_REQ_d00212_H_has_cross_repo_implements(self):
        """HierarchyConfig has cross_repo_implements (bool|None)."""
        assert "cross_repo_implements" in HierarchyConfig.model_fields
        cfg = HierarchyConfig()
        assert cfg.cross_repo_implements is None

    def test_REQ_d00212_H_no_dev_field(self):
        """HierarchyConfig does NOT have a 'dev' field."""
        assert "dev" not in HierarchyConfig.model_fields

    def test_REQ_d00212_H_no_ops_field(self):
        """HierarchyConfig does NOT have an 'ops' field."""
        assert "ops" not in HierarchyConfig.model_fields

    def test_REQ_d00212_H_no_prd_field(self):
        """HierarchyConfig does NOT have a 'prd' field."""
        assert "prd" not in HierarchyConfig.model_fields

    def test_REQ_d00212_H_strict_rejects_unknown(self):
        """HierarchyConfig rejects unknown fields (strict mode)."""
        with pytest.raises(ValidationError, match="extra"):
            HierarchyConfig(unknown_field="x")


# ---------------------------------------------------------------------------
# REQ-d00212-J: ProjectConfig simplified
# ---------------------------------------------------------------------------


class TestProjectConfigSimplified:
    """Validates REQ-d00212-J: ProjectConfig simplified."""

    def test_REQ_d00212_J_has_namespace(self):
        """ProjectConfig has 'namespace' field (str)."""
        assert "namespace" in ProjectConfig.model_fields
        cfg = ProjectConfig()
        assert isinstance(cfg.namespace, str)

    def test_REQ_d00212_J_has_name(self):
        """ProjectConfig has 'name' field (str|None)."""
        assert "name" in ProjectConfig.model_fields
        cfg = ProjectConfig()
        assert cfg.name is None

    def test_REQ_d00212_J_no_version_field(self):
        """ProjectConfig does NOT have a 'version' field."""
        assert "version" not in ProjectConfig.model_fields

    def test_REQ_d00212_J_no_type_field(self):
        """ProjectConfig does NOT have a 'type' field."""
        assert "type" not in ProjectConfig.model_fields


# ---------------------------------------------------------------------------
# REQ-d00212-K: AssociateEntryConfig simplified
# ---------------------------------------------------------------------------


class TestAssociateEntryConfigSimplified:
    """Validates REQ-d00212-K: AssociateEntryConfig simplified."""

    def test_REQ_d00212_K_has_path_required(self):
        """AssociateEntryConfig has 'path' field (str, required)."""
        assert "path" in AssociateEntryConfig.model_fields
        # path is required -- omitting it should raise
        with pytest.raises(ValidationError):
            AssociateEntryConfig(namespace="NS")  # type: ignore[call-arg]

    def test_REQ_d00212_K_has_namespace_required(self):
        """AssociateEntryConfig has 'namespace' field (str, required)."""
        assert "namespace" in AssociateEntryConfig.model_fields
        # namespace is required -- omitting it should raise
        with pytest.raises(ValidationError):
            AssociateEntryConfig(path="/some/path")  # type: ignore[call-arg]

    def test_REQ_d00212_K_valid_construction(self):
        """AssociateEntryConfig can be constructed with path and namespace."""
        cfg = AssociateEntryConfig(path="/some/path", namespace="NS")
        assert cfg.path == "/some/path"
        assert cfg.namespace == "NS"

    def test_REQ_d00212_K_no_git_field(self):
        """AssociateEntryConfig does NOT have a 'git' field."""
        assert "git" not in AssociateEntryConfig.model_fields

    def test_REQ_d00212_K_no_spec_field(self):
        """AssociateEntryConfig does NOT have a 'spec' field."""
        assert "spec" not in AssociateEntryConfig.model_fields
