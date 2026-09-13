"""Tests that the configuration schema admits the settings it defines (REQ-d00212-Y).

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
# REQ-d00212-Y: ElspaisConfig restructuring
# ---------------------------------------------------------------------------


class TestElspaisConfigRestructuring:
    """Validates REQ-d00212-Y: ElspaisConfig restructuring."""

    # Verifies: REQ-d00212-Y
    def test_REQ_d00212_F_has_levels_field(self):
        """ElspaisConfig has a 'levels' field of type dict[str, LevelConfig]."""
        assert "levels" in ElspaisConfig.model_fields
        cfg = ElspaisConfig()
        assert isinstance(cfg.levels, dict)
        assert len(cfg.levels) == 3
        for key in ("prd", "ops", "dev"):
            assert key in cfg.levels
            assert isinstance(cfg.levels[key], LevelConfig)

    # Verifies: REQ-d00212-Y
    def test_REQ_d00212_F_levels_default_prd(self):
        """Default levels include prd with rank=1, letter='p'."""
        cfg = ElspaisConfig()
        prd = cfg.levels["prd"]
        assert prd.rank == 1
        assert prd.letter == "p"

    # Verifies: REQ-d00212-Y
    def test_REQ_d00212_F_levels_default_ops(self):
        """Default levels include ops with rank=2, letter='o'."""
        cfg = ElspaisConfig()
        ops = cfg.levels["ops"]
        assert ops.rank == 2
        assert ops.letter == "o"

    # Verifies: REQ-d00212-Y
    def test_REQ_d00212_F_levels_default_dev(self):
        """Default levels include dev with rank=3, letter='d'."""
        cfg = ElspaisConfig()
        dev = cfg.levels["dev"]
        assert dev.rank == 3
        assert dev.letter == "d"

    # Verifies: REQ-d00212-Y
    def test_REQ_d00212_F_has_scanning_field(self):
        """ElspaisConfig has a 'scanning' field of type ScanningConfig."""
        assert "scanning" in ElspaisConfig.model_fields
        cfg = ElspaisConfig()
        assert isinstance(cfg.scanning, ScanningConfig)

    # Verifies: REQ-d00212-Y
    def test_REQ_d00212_F_has_output_field(self):
        """ElspaisConfig has an 'output' field of type OutputConfig."""
        assert "output" in ElspaisConfig.model_fields
        cfg = ElspaisConfig()
        assert isinstance(cfg.output, OutputConfig)

    # Verifies: REQ-d00212-Y
    def test_REQ_d00212_F_no_directories_field(self):
        """ElspaisConfig does NOT have a 'directories' field."""
        assert "directories" not in ElspaisConfig.model_fields

    # Verifies: REQ-d00212-Y
    def test_REQ_d00212_F_no_spec_field(self):
        """ElspaisConfig does NOT have a 'spec' field."""
        assert "spec" not in ElspaisConfig.model_fields

    # Verifies: REQ-d00212-Y
    def test_REQ_d00212_F_no_testing_field(self):
        """ElspaisConfig does NOT have a 'testing' field."""
        assert "testing" not in ElspaisConfig.model_fields

    # Verifies: REQ-d00212-Y
    def test_REQ_d00212_F_no_ignore_field(self):
        """ElspaisConfig does NOT have an 'ignore' field."""
        assert "ignore" not in ElspaisConfig.model_fields

    # Verifies: REQ-d00212-Y
    def test_REQ_d00212_F_no_graph_field(self):
        """ElspaisConfig does NOT have a 'graph' field."""
        assert "graph" not in ElspaisConfig.model_fields

    # Verifies: REQ-d00212-Y
    def test_REQ_d00212_F_no_traceability_field(self):
        """ElspaisConfig does NOT have a 'traceability' field."""
        assert "traceability" not in ElspaisConfig.model_fields

    # Verifies: REQ-d00212-Y
    def test_REQ_d00212_F_no_core_field(self):
        """ElspaisConfig does NOT have a 'core' field."""
        assert "core" not in ElspaisConfig.model_fields

    # Verifies: REQ-d00212-Y
    def test_REQ_d00212_F_no_associated_field(self):
        """ElspaisConfig does NOT have an 'associated' field."""
        assert "associated" not in ElspaisConfig.model_fields

    # Verifies: REQ-d00212-Y
    def test_REQ_d00212_F_version_defaults_to_the_current_schema_version(self):
        """A config built from the schema's own defaults is already current.

        The default is what `elspais init` writes and what `config_defaults()`
        merges under a user's TOML, so a default lagging behind
        `CURRENT_CONFIG_VERSION` would send every fresh project through a
        migration on its first load.
        """
        from elspais.config import CURRENT_CONFIG_VERSION

        cfg = ElspaisConfig()
        assert cfg.version == CURRENT_CONFIG_VERSION


# ---------------------------------------------------------------------------
# REQ-d00212-G: one admitted spelling per identifier
# ---------------------------------------------------------------------------


class TestIdPatternsConfigChanges:
    """Validates REQ-d00212-G: no configuration surface offers a second spelling."""

    # Verifies: REQ-d00212-G
    def test_REQ_d00212_G_no_alternate_separator_fields(self):
        """The accepted-alternates list and the optional-prefix switch are gone.

        Neither governed anything: one separator is accepted, the one each
        repository configures for itself.
        """
        assert "separators" not in IdPatternsConfig.model_fields
        assert "prefix_optional" not in IdPatternsConfig.model_fields

    # Verifies: REQ-d00212-G
    def test_REQ_d00212_G_no_types_field(self):
        """IdPatternsConfig does NOT have a 'types' field."""
        assert "types" not in IdPatternsConfig.model_fields

    # Verifies: REQ-d00212-G
    def test_REQ_d00212_G_has_associated_field(self):
        """IdPatternsConfig has an 'associated' field with defaults."""
        assert "associated" in IdPatternsConfig.model_fields
        cfg = IdPatternsConfig()
        assert cfg.associated.enabled is False

    # Verifies: REQ-d00212-G
    def test_REQ_d00212_G_canonical_uses_level_letter(self):
        """canonical default uses {level.letter} not {type.letter}."""
        cfg = IdPatternsConfig()
        assert "{level.letter}" in cfg.canonical
        assert "{type.letter}" not in cfg.canonical

    # Verifies: REQ-d00212-G
    def test_REQ_d00212_G_aliases_short_uses_level_letter(self):
        """aliases.short default uses {level.letter} not {type.letter}."""
        cfg = IdPatternsConfig()
        assert "short" in cfg.aliases
        assert "{level.letter}" in cfg.aliases["short"]
        assert "{type.letter}" not in cfg.aliases["short"]

    # Verifies: REQ-d00212-G
    def test_REQ_d00212_G_level_letters_colliding_only_by_case_rejected(self):
        """A configuration naming two levels whose letter differs only in
        case is refused: matching an identifier's level code is
        case-insensitive (REQ-d00212-R), so such a pair would make that
        tolerance ambiguous."""
        with pytest.raises(ValidationError) as excinfo:
            ElspaisConfig(
                levels={
                    "prd": LevelConfig(rank=1, letter="p", implements=["prd"]),
                    "product": LevelConfig(rank=2, letter="P", implements=["prd"]),
                }
            )
        message = str(excinfo.value)
        assert "prd" in message
        assert "product" in message

    # Verifies: REQ-d00212-G
    def test_REQ_d00212_G_level_letters_distinct_case_accepted(self):
        """Two levels with genuinely distinct letters load without complaint,
        including a level letter that happens to repeat across a rebuilt
        config (not a collision -- the same spelling, not two of them)."""
        cfg = ElspaisConfig(
            levels={
                "prd": LevelConfig(rank=1, letter="p", implements=["prd"]),
                "ops": LevelConfig(rank=2, letter="o", implements=["prd", "ops"]),
            }
        )
        assert cfg.levels["prd"].letter == "p"
        assert cfg.levels["ops"].letter == "o"


# ---------------------------------------------------------------------------
# REQ-d00212-Y: HierarchyConfig is booleans only
# ---------------------------------------------------------------------------


class TestHierarchyConfigBooleansOnly:
    """Validates REQ-d00212-Y: HierarchyConfig is booleans only."""

    # Verifies: REQ-d00212-Y
    def test_REQ_d00212_H_has_allow_circular(self):
        """HierarchyConfig has allow_circular (bool, default False)."""
        assert "allow_circular" in HierarchyConfig.model_fields
        cfg = HierarchyConfig()
        assert cfg.allow_circular is False

    # Verifies: REQ-d00212-Y
    def test_REQ_d00212_H_has_allow_structural_orphans(self):
        """HierarchyConfig has allow_structural_orphans (bool, default False)."""
        assert "allow_structural_orphans" in HierarchyConfig.model_fields
        cfg = HierarchyConfig()
        assert cfg.allow_structural_orphans is False

    # Verifies: REQ-d00212-Y
    def test_REQ_d00212_H_has_allow_orphans(self):
        """HierarchyConfig has allow_orphans (bool, default False)."""
        assert "allow_orphans" in HierarchyConfig.model_fields
        cfg = HierarchyConfig()
        assert cfg.allow_orphans is False

    # Verifies: REQ-d00212-Y
    def test_REQ_d00212_H_has_cross_repo_implements(self):
        """HierarchyConfig has cross_repo_implements (bool, default False)."""
        assert "cross_repo_implements" in HierarchyConfig.model_fields
        cfg = HierarchyConfig()
        assert cfg.cross_repo_implements is False

    # Verifies: REQ-d00212-Y
    def test_REQ_d00212_H_no_dev_field(self):
        """HierarchyConfig does NOT have a 'dev' field."""
        assert "dev" not in HierarchyConfig.model_fields

    # Verifies: REQ-d00212-Y
    def test_REQ_d00212_H_no_ops_field(self):
        """HierarchyConfig does NOT have an 'ops' field."""
        assert "ops" not in HierarchyConfig.model_fields

    # Verifies: REQ-d00212-Y
    def test_REQ_d00212_H_no_prd_field(self):
        """HierarchyConfig does NOT have a 'prd' field."""
        assert "prd" not in HierarchyConfig.model_fields

    # Verifies: REQ-d00212-Y
    def test_REQ_d00212_H_strict_rejects_unknown(self):
        """HierarchyConfig rejects unknown fields (strict mode)."""
        with pytest.raises(ValidationError, match="extra"):
            HierarchyConfig(unknown_field="x")


# ---------------------------------------------------------------------------
# REQ-d00212-Y: ProjectConfig simplified
# ---------------------------------------------------------------------------


class TestProjectConfigSimplified:
    """Validates REQ-d00212-Y: ProjectConfig simplified."""

    # Verifies: REQ-d00212-Y
    def test_REQ_d00212_J_has_namespace(self):
        """ProjectConfig has 'namespace' field (str)."""
        assert "namespace" in ProjectConfig.model_fields
        cfg = ProjectConfig()
        assert isinstance(cfg.namespace, str)

    # Verifies: REQ-d00212-Y
    def test_REQ_d00212_J_has_name(self):
        """ProjectConfig has 'name' field (str, non-empty default).

        Default is the placeholder used by ``config_defaults()`` for the
        no-config-file path (e.g., MCP server invoked outside any project).
        ``load_config()``'s pre-merge boundary check rejects a user TOML
        that omits ``[project].name`` regardless of the schema default.
        """
        assert "name" in ProjectConfig.model_fields
        cfg = ProjectConfig()
        assert isinstance(cfg.name, str)
        assert cfg.name.strip() != ""

    # Verifies: REQ-d00212-Y
    def test_REQ_d00212_J_no_version_field(self):
        """ProjectConfig does NOT have a 'version' field."""
        assert "version" not in ProjectConfig.model_fields

    # Verifies: REQ-d00212-Y
    def test_REQ_d00212_J_no_type_field(self):
        """ProjectConfig does NOT have a 'type' field."""
        assert "type" not in ProjectConfig.model_fields


# ---------------------------------------------------------------------------
# REQ-d00212-Y: AssociateEntryConfig simplified
# ---------------------------------------------------------------------------


class TestAssociateEntryConfigSimplified:
    """Validates REQ-d00212-Y: AssociateEntryConfig simplified."""

    # Verifies: REQ-d00212-Y
    def test_REQ_d00212_K_has_path_required(self):
        """AssociateEntryConfig has 'path' field (str, required)."""
        assert "path" in AssociateEntryConfig.model_fields
        # path is required -- omitting it should raise
        with pytest.raises(ValidationError):
            AssociateEntryConfig(namespace="NS")  # type: ignore[call-arg]

    # Verifies: REQ-d00212-Y
    def test_REQ_d00212_K_has_namespace_required(self):
        """AssociateEntryConfig has 'namespace' field (str, required)."""
        assert "namespace" in AssociateEntryConfig.model_fields
        # namespace is required -- omitting it should raise
        with pytest.raises(ValidationError):
            AssociateEntryConfig(path="/some/path")  # type: ignore[call-arg]

    # Verifies: REQ-d00212-Y
    def test_REQ_d00212_K_valid_construction(self):
        """AssociateEntryConfig can be constructed with path and namespace."""
        cfg = AssociateEntryConfig(path="/some/path", namespace="NS")
        assert cfg.path == "/some/path"
        assert cfg.namespace == "NS"

    # Verifies: REQ-d00212-Y
    def test_REQ_d00212_K_git_field_is_optional(self):
        """AssociateEntryConfig carries an optional 'git' remote."""
        assert "git" in AssociateEntryConfig.model_fields
        # Optional: a declaration without a remote is complete, and the
        # remote is never what identifies the repository.
        assert AssociateEntryConfig(path="/some/path", namespace="NS").git is None
        remote = "https://example.com/lib.git"
        assert AssociateEntryConfig(path="/p", namespace="NS", git=remote).git == remote

    # Verifies: REQ-d00212-Y
    def test_REQ_d00212_K_no_spec_field(self):
        """AssociateEntryConfig does NOT have a 'spec' field."""
        assert "spec" not in AssociateEntryConfig.model_fields
