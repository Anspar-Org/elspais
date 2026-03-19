"""Tests for Config Schema v3 models (REQ-d00212).

These tests validate new Pydantic models for the v3 config schema.
Models under test: LevelConfig, ScanningKindConfig (+ subclasses),
ScanningConfig, OutputConfig, ChangelogRequireConfig, updated ChangelogConfig.
"""

import pytest
from pydantic import ValidationError

from elspais.config import schema as _schema

ChangelogConfig = _schema.ChangelogConfig
ChangelogRequireConfig = _schema.ChangelogRequireConfig
CodeScanningConfig = _schema.CodeScanningConfig
DocsScanningConfig = _schema.DocsScanningConfig
JourneyScanningConfig = _schema.JourneyScanningConfig
LevelConfig = _schema.LevelConfig
OutputConfig = _schema.OutputConfig
ResultScanningConfig = _schema.ResultScanningConfig
ScanningConfig = _schema.ScanningConfig
ScanningKindConfig = _schema.ScanningKindConfig
SpecScanningConfig = _schema.SpecScanningConfig
TestScanningCfg = _schema.TestScanningConfig  # Alias to avoid pytest class name collision


# ---------------------------------------------------------------------------
# REQ-d00212-A: LevelConfig
# ---------------------------------------------------------------------------


class TestLevelConfig:
    """Validates REQ-d00212-A: LevelConfig model."""

    def test_REQ_d00212_A_level_config_fields(self):
        """All required fields are accepted and stored."""
        lc = LevelConfig(rank=1, letter="p", display_name="Product", implements=["ops"])
        assert lc.rank == 1
        assert lc.letter == "p"
        assert lc.display_name == "Product"
        assert lc.implements == ["ops"]

    def test_REQ_d00212_A_level_config_rejects_unknown(self):
        """Strict mode rejects extra fields."""
        with pytest.raises(ValidationError, match="extra"):
            LevelConfig(rank=1, letter="p", implements=[], bogus="nope")

    def test_REQ_d00212_A_level_config_display_name_optional(self):
        """display_name defaults to None when omitted."""
        lc = LevelConfig(rank=2, letter="o", implements=["prd"])
        assert lc.display_name is None

    def test_REQ_d00212_A_level_config_rank_required(self):
        """rank is required."""
        with pytest.raises(ValidationError):
            LevelConfig(letter="p", implements=[])  # type: ignore[call-arg]

    def test_REQ_d00212_A_level_config_letter_required(self):
        """letter is required."""
        with pytest.raises(ValidationError):
            LevelConfig(rank=1, implements=[])  # type: ignore[call-arg]

    def test_REQ_d00212_A_level_config_implements_required(self):
        """implements is required."""
        with pytest.raises(ValidationError):
            LevelConfig(rank=1, letter="d")  # type: ignore[call-arg]

    def test_REQ_d00212_A_level_config_frozen(self):
        """Model is frozen (immutable)."""
        lc = LevelConfig(rank=1, letter="p", implements=[])
        with pytest.raises(ValidationError):
            lc.rank = 99  # type: ignore[misc]

    def test_REQ_d00212_A_level_config_implements_empty_list(self):
        """implements can be an empty list (top-level requirement)."""
        lc = LevelConfig(rank=1, letter="p", implements=[])
        assert lc.implements == []


# ---------------------------------------------------------------------------
# REQ-d00212-B: ScanningKindConfig base + subclasses
# ---------------------------------------------------------------------------


class TestScanningKindConfig:
    """Validates REQ-d00212-B: ScanningKindConfig base and subclasses."""

    def test_REQ_d00212_B_base_common_fields(self):
        """Base model has directories, file_patterns, skip_files, skip_dirs."""
        sc = ScanningKindConfig(
            directories=["src"],
            file_patterns=["*.py"],
            skip_files=["setup.py"],
            skip_dirs=["__pycache__"],
        )
        assert sc.directories == ["src"]
        assert sc.file_patterns == ["*.py"]
        assert sc.skip_files == ["setup.py"]
        assert sc.skip_dirs == ["__pycache__"]

    def test_REQ_d00212_B_base_rejects_unknown(self):
        """Base model rejects extra fields."""
        with pytest.raises(ValidationError, match="extra"):
            ScanningKindConfig(
                directories=[], file_patterns=[], skip_files=[], skip_dirs=[], unknown="x"
            )


class TestSpecScanningConfig:
    """Validates REQ-d00212-B: SpecScanningConfig subclass."""

    def test_REQ_d00212_B_spec_index_file_default_none(self):
        """SpecScanningConfig.index_file defaults to None."""
        sc = SpecScanningConfig(
            directories=["spec"], file_patterns=["*.md"], skip_files=[], skip_dirs=[]
        )
        assert sc.index_file is None

    def test_REQ_d00212_B_spec_index_file_set(self):
        """SpecScanningConfig.index_file can be set."""
        sc = SpecScanningConfig(
            directories=["spec"],
            file_patterns=["*.md"],
            skip_files=[],
            skip_dirs=[],
            index_file="INDEX.md",
        )
        assert sc.index_file == "INDEX.md"

    def test_REQ_d00212_B_spec_inherits_base_fields(self):
        """SpecScanningConfig inherits all base fields."""
        sc = SpecScanningConfig(
            directories=["spec"],
            file_patterns=["*.md"],
            skip_files=["README.md"],
            skip_dirs=["archive"],
        )
        assert sc.directories == ["spec"]
        assert sc.skip_files == ["README.md"]


class TestCodeScanningConfig:
    """Validates REQ-d00212-B: CodeScanningConfig subclass."""

    def test_REQ_d00212_B_code_source_roots_default_none(self):
        """CodeScanningConfig.source_roots defaults to None."""
        cc = CodeScanningConfig(
            directories=["src"], file_patterns=["*.py"], skip_files=[], skip_dirs=[]
        )
        assert cc.source_roots is None

    def test_REQ_d00212_B_code_source_roots_set(self):
        """CodeScanningConfig.source_roots can be set."""
        cc = CodeScanningConfig(
            directories=["src"],
            file_patterns=["*.py"],
            skip_files=[],
            skip_dirs=[],
            source_roots=["src/elspais"],
        )
        assert cc.source_roots == ["src/elspais"]


class TestTestScanningConfig:
    """Validates REQ-d00212-B: TestScanningConfig subclass."""

    def test_REQ_d00212_B_test_defaults(self):
        """TestScanningConfig has correct defaults for extra fields."""
        tc = TestScanningCfg(
            directories=["tests"], file_patterns=["test_*.py"], skip_files=[], skip_dirs=[]
        )
        assert tc.enabled is False
        assert tc.prescan_command == ""
        assert tc.reference_keyword == "Verifies"
        assert tc.reference_patterns == []

    def test_REQ_d00212_B_test_custom_values(self):
        """TestScanningConfig extra fields accept custom values."""
        tc = TestScanningCfg(
            directories=["tests"],
            file_patterns=["test_*.py"],
            skip_files=[],
            skip_dirs=[],
            enabled=True,
            prescan_command="python -m pytest --collect-only",
            reference_keyword="Validates",
            reference_patterns=[r"REQ-\w+"],
        )
        assert tc.enabled is True
        assert tc.prescan_command == "python -m pytest --collect-only"
        assert tc.reference_keyword == "Validates"
        assert tc.reference_patterns == [r"REQ-\w+"]


class TestResultScanningConfig:
    """Validates REQ-d00212-B: ResultScanningConfig subclass."""

    def test_REQ_d00212_B_result_run_meta_file_default(self):
        """ResultScanningConfig.run_meta_file defaults to empty string."""
        rc = ResultScanningConfig(
            directories=["results"], file_patterns=["*.xml"], skip_files=[], skip_dirs=[]
        )
        assert rc.run_meta_file == ""

    def test_REQ_d00212_B_result_run_meta_file_set(self):
        """ResultScanningConfig.run_meta_file can be set."""
        rc = ResultScanningConfig(
            directories=["results"],
            file_patterns=["*.xml"],
            skip_files=[],
            skip_dirs=[],
            run_meta_file="run_meta.json",
        )
        assert rc.run_meta_file == "run_meta.json"


class TestJourneyScanningConfig:
    """Validates REQ-d00212-B: JourneyScanningConfig subclass (no extras)."""

    def test_REQ_d00212_B_journey_no_extras(self):
        """JourneyScanningConfig has no extra fields beyond base."""
        jc = JourneyScanningConfig(
            directories=["journeys"], file_patterns=["*.md"], skip_files=[], skip_dirs=[]
        )
        assert jc.directories == ["journeys"]

    def test_REQ_d00212_B_journey_rejects_unknown(self):
        """JourneyScanningConfig rejects unknown fields."""
        with pytest.raises(ValidationError, match="extra"):
            JourneyScanningConfig(
                directories=[], file_patterns=[], skip_files=[], skip_dirs=[], extra_field="x"
            )


class TestDocsScanningConfig:
    """Validates REQ-d00212-B: DocsScanningConfig subclass (no extras)."""

    def test_REQ_d00212_B_docs_no_extras(self):
        """DocsScanningConfig has no extra fields beyond base."""
        dc = DocsScanningConfig(
            directories=["docs"], file_patterns=["*.md"], skip_files=[], skip_dirs=[]
        )
        assert dc.directories == ["docs"]

    def test_REQ_d00212_B_docs_rejects_unknown(self):
        """DocsScanningConfig rejects unknown fields."""
        with pytest.raises(ValidationError, match="extra"):
            DocsScanningConfig(
                directories=[], file_patterns=[], skip_files=[], skip_dirs=[], nope="x"
            )


# ---------------------------------------------------------------------------
# REQ-d00212-C: ScanningConfig composite
# ---------------------------------------------------------------------------


class TestScanningConfig:
    """Validates REQ-d00212-C: ScanningConfig composite model."""

    def test_REQ_d00212_C_scanning_config_has_all_kinds(self):
        """ScanningConfig exposes spec, code, test, result, journey, docs fields."""
        sc = ScanningConfig()
        assert isinstance(sc.spec, SpecScanningConfig)
        assert isinstance(sc.code, CodeScanningConfig)
        assert isinstance(sc.test, TestScanningCfg)
        assert isinstance(sc.result, ResultScanningConfig)
        assert isinstance(sc.journey, JourneyScanningConfig)
        assert isinstance(sc.docs, DocsScanningConfig)

    def test_REQ_d00212_C_scanning_config_skip_default(self):
        """ScanningConfig.skip defaults to empty list."""
        sc = ScanningConfig()
        assert sc.skip == []

    def test_REQ_d00212_C_scanning_config_skip_custom(self):
        """ScanningConfig.skip accepts custom patterns."""
        sc = ScanningConfig(skip=["*.bak", "tmp/"])
        assert sc.skip == ["*.bak", "tmp/"]

    def test_REQ_d00212_C_scanning_config_rejects_unknown(self):
        """ScanningConfig rejects unknown fields."""
        with pytest.raises(ValidationError, match="extra"):
            ScanningConfig(unknown_kind="x")

    def test_REQ_d00212_C_scanning_config_frozen(self):
        """ScanningConfig is frozen."""
        sc = ScanningConfig()
        with pytest.raises(ValidationError):
            sc.skip = ["new"]  # type: ignore[misc]


# ---------------------------------------------------------------------------
# REQ-d00212-D: OutputConfig
# ---------------------------------------------------------------------------


class TestOutputConfig:
    """Validates REQ-d00212-D: OutputConfig model."""

    def test_REQ_d00212_D_output_config_defaults(self):
        """OutputConfig defaults: formats=[], dir=''."""
        oc = OutputConfig()
        assert oc.formats == []
        assert oc.dir == ""

    def test_REQ_d00212_D_output_config_custom(self):
        """OutputConfig accepts custom values."""
        oc = OutputConfig(formats=["html", "json"], dir="output/")
        assert oc.formats == ["html", "json"]
        assert oc.dir == "output/"

    def test_REQ_d00212_D_output_config_rejects_unknown(self):
        """OutputConfig rejects unknown fields."""
        with pytest.raises(ValidationError, match="extra"):
            OutputConfig(formats=[], dir="", extra="x")

    def test_REQ_d00212_D_output_config_frozen(self):
        """OutputConfig is frozen."""
        oc = OutputConfig()
        with pytest.raises(ValidationError):
            oc.dir = "new"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# REQ-d00212-E: ChangelogRequireConfig + updated ChangelogConfig
# ---------------------------------------------------------------------------


class TestChangelogRequireConfig:
    """Validates REQ-d00212-E: ChangelogRequireConfig sub-model."""

    def test_REQ_d00212_E_changelog_require_defaults(self):
        """ChangelogRequireConfig has correct boolean defaults."""
        cr = ChangelogRequireConfig()
        assert cr.reason is True
        assert cr.author_name is True
        assert cr.author_id is True
        assert cr.change_order is False

    def test_REQ_d00212_E_changelog_require_custom(self):
        """ChangelogRequireConfig accepts custom boolean values."""
        cr = ChangelogRequireConfig(
            reason=False, author_name=False, author_id=False, change_order=True
        )
        assert cr.reason is False
        assert cr.author_name is False
        assert cr.author_id is False
        assert cr.change_order is True

    def test_REQ_d00212_E_changelog_require_rejects_unknown(self):
        """ChangelogRequireConfig rejects unknown fields."""
        with pytest.raises(ValidationError, match="extra"):
            ChangelogRequireConfig(bogus=True)

    def test_REQ_d00212_E_changelog_require_frozen(self):
        """ChangelogRequireConfig is frozen."""
        cr = ChangelogRequireConfig()
        with pytest.raises(ValidationError):
            cr.reason = False  # type: ignore[misc]


class TestChangelogConfigV3:
    """Validates REQ-d00212-E: Updated ChangelogConfig with renamed fields and require sub-model."""

    def test_REQ_d00212_E_changelog_hash_current_default(self):
        """hash_current defaults to True."""
        cc = ChangelogConfig()
        assert cc.hash_current is True

    def test_REQ_d00212_E_changelog_present_default(self):
        """present defaults to False."""
        cc = ChangelogConfig()
        assert cc.present is False

    def test_REQ_d00212_E_changelog_require_sub_model(self):
        """ChangelogConfig has a require sub-model of type ChangelogRequireConfig."""
        cc = ChangelogConfig()
        assert isinstance(cc.require, ChangelogRequireConfig)

    def test_REQ_d00212_E_changelog_rejects_old_field_names(self):
        """Old field names (enforce, require_present) are rejected — no backward compat."""
        with pytest.raises(ValidationError, match="extra"):
            ChangelogConfig(enforce=False)
        with pytest.raises(ValidationError, match="extra"):
            ChangelogConfig(require_present=True)

    def test_REQ_d00212_E_changelog_require_sub_model_override(self):
        """ChangelogConfig.require sub-model can be customized."""
        cc = ChangelogConfig(require=ChangelogRequireConfig(reason=False, change_order=True))
        assert cc.require.reason is False
        assert cc.require.change_order is True
        # Defaults preserved for unset fields
        assert cc.require.author_name is True
        assert cc.require.author_id is True
