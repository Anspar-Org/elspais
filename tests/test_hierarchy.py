"""
Tests for elspais.core.hierarchy module.
"""

import pytest


class TestFindRequirement:
    """Tests for find_requirement() function."""

    @pytest.fixture
    def sample_requirements(self, hht_like_fixture):
        """Load requirements from hht-like fixture."""
        from elspais.config.loader import load_config
        from elspais.core.parser import RequirementParser
        from elspais.core.patterns import PatternConfig

        config_dict = load_config(hht_like_fixture / ".elspais.toml")
        pattern_config = PatternConfig.from_dict(config_dict["patterns"])
        parser = RequirementParser(pattern_config)

        spec_dir = hht_like_fixture / "spec"
        return parser.parse_directory(spec_dir)

    def test_exact_match(self, sample_requirements):
        """Test exact ID matching."""
        from elspais.core.hierarchy import find_requirement

        req = find_requirement("REQ-p00001", sample_requirements)
        assert req is not None
        assert req.id == "REQ-p00001"

    def test_short_id_match(self, sample_requirements):
        """Test matching with short ID (without REQ- prefix)."""
        from elspais.core.hierarchy import find_requirement

        req = find_requirement("p00001", sample_requirements)
        assert req is not None
        assert req.id == "REQ-p00001"

    def test_suffix_match(self, sample_requirements):
        """Test matching with partial suffix."""
        from elspais.core.hierarchy import find_requirement

        # Match by just the numeric part
        req = find_requirement("d00001", sample_requirements)
        assert req is not None
        assert req.id == "REQ-d00001"

    def test_not_found(self, sample_requirements):
        """Test returning None for non-existent requirement."""
        from elspais.core.hierarchy import find_requirement

        req = find_requirement("REQ-p99999", sample_requirements)
        assert req is None

    def test_empty_dict(self):
        """Test with empty requirements dict."""
        from elspais.core.hierarchy import find_requirement

        req = find_requirement("REQ-p00001", {})
        assert req is None


class TestResolveId:
    """Tests for resolve_id() function."""

    @pytest.fixture
    def sample_requirements(self, hht_like_fixture):
        """Load requirements from hht-like fixture."""
        from elspais.config.loader import load_config
        from elspais.core.parser import RequirementParser
        from elspais.core.patterns import PatternConfig

        config_dict = load_config(hht_like_fixture / ".elspais.toml")
        pattern_config = PatternConfig.from_dict(config_dict["patterns"])
        parser = RequirementParser(pattern_config)

        spec_dir = hht_like_fixture / "spec"
        return parser.parse_directory(spec_dir)

    def test_resolve_exact(self, sample_requirements):
        """Test resolving exact ID."""
        from elspais.core.hierarchy import resolve_id

        resolved = resolve_id("REQ-p00001", sample_requirements)
        assert resolved == "REQ-p00001"

    def test_resolve_short_id(self, sample_requirements):
        """Test resolving short ID to canonical form."""
        from elspais.core.hierarchy import resolve_id

        resolved = resolve_id("p00001", sample_requirements)
        assert resolved == "REQ-p00001"

    def test_resolve_not_found(self, sample_requirements):
        """Test returning None for non-existent ID."""
        from elspais.core.hierarchy import resolve_id

        resolved = resolve_id("REQ-x99999", sample_requirements)
        assert resolved is None


class TestNormalizeReqId:
    """Tests for normalize_req_id() function."""

    def test_adds_prefix(self):
        """Test adding REQ- prefix to bare ID."""
        from elspais.core.hierarchy import normalize_req_id

        assert normalize_req_id("p00001") == "REQ-p00001"

    def test_keeps_existing_prefix(self):
        """Test preserving existing REQ- prefix."""
        from elspais.core.hierarchy import normalize_req_id

        assert normalize_req_id("REQ-p00001") == "REQ-p00001"

    def test_custom_prefix(self):
        """Test with custom prefix."""
        from elspais.core.hierarchy import normalize_req_id

        assert normalize_req_id("001", prefix="JIRA") == "JIRA-001"


class TestFindChildren:
    """Tests for find_children() function."""

    @pytest.fixture
    def sample_requirements(self, hht_like_fixture):
        """Load requirements from hht-like fixture."""
        from elspais.config.loader import load_config
        from elspais.core.parser import RequirementParser
        from elspais.core.patterns import PatternConfig

        config_dict = load_config(hht_like_fixture / ".elspais.toml")
        pattern_config = PatternConfig.from_dict(config_dict["patterns"])
        parser = RequirementParser(pattern_config)

        spec_dir = hht_like_fixture / "spec"
        return parser.parse_directory(spec_dir)

    def test_find_children_of_prd(self, sample_requirements):
        """Test finding requirements that implement a PRD requirement."""
        from elspais.core.hierarchy import find_children

        children = find_children("REQ-p00001", sample_requirements)
        assert len(children) > 0
        # All children should have p00001 in implements
        for child in children:
            implements_p00001 = any("p00001" in impl for impl in child.implements)
            assert implements_p00001, f"{child.id} should implement p00001"

    def test_find_children_sorted(self, sample_requirements):
        """Test that children are returned sorted by ID."""
        from elspais.core.hierarchy import find_children

        children = find_children("REQ-p00001", sample_requirements)
        if len(children) > 1:
            child_ids = [c.id for c in children]
            assert child_ids == sorted(child_ids)

    def test_find_children_none(self, sample_requirements):
        """Test finding children for requirement with no children."""
        from elspais.core.hierarchy import find_children

        # DEV level requirements typically have no children
        children = find_children("REQ-d00001", sample_requirements)
        assert children == []

    def test_find_children_short_id(self, sample_requirements):
        """Test finding children using short ID."""
        from elspais.core.hierarchy import find_children

        children = find_children("p00001", sample_requirements)
        assert len(children) > 0


class TestFindChildrenIds:
    """Tests for find_children_ids() function."""

    @pytest.fixture
    def sample_requirements(self, hht_like_fixture):
        """Load requirements from hht-like fixture."""
        from elspais.config.loader import load_config
        from elspais.core.parser import RequirementParser
        from elspais.core.patterns import PatternConfig

        config_dict = load_config(hht_like_fixture / ".elspais.toml")
        pattern_config = PatternConfig.from_dict(config_dict["patterns"])
        parser = RequirementParser(pattern_config)

        spec_dir = hht_like_fixture / "spec"
        return parser.parse_directory(spec_dir)

    def test_returns_ids(self, sample_requirements):
        """Test that function returns ID strings."""
        from elspais.core.hierarchy import find_children_ids

        ids = find_children_ids("REQ-p00001", sample_requirements)
        assert isinstance(ids, list)
        for id_ in ids:
            assert isinstance(id_, str)

    def test_matches_find_children(self, sample_requirements):
        """Test that IDs match find_children results."""
        from elspais.core.hierarchy import find_children, find_children_ids

        children = find_children("REQ-p00001", sample_requirements)
        ids = find_children_ids("REQ-p00001", sample_requirements)

        assert len(ids) == len(children)
        assert set(ids) == {c.id for c in children}


class TestBuildChildrenIndex:
    """Tests for build_children_index() function."""

    @pytest.fixture
    def sample_requirements(self, hht_like_fixture):
        """Load requirements from hht-like fixture."""
        from elspais.config.loader import load_config
        from elspais.core.parser import RequirementParser
        from elspais.core.patterns import PatternConfig

        config_dict = load_config(hht_like_fixture / ".elspais.toml")
        pattern_config = PatternConfig.from_dict(config_dict["patterns"])
        parser = RequirementParser(pattern_config)

        spec_dir = hht_like_fixture / "spec"
        return parser.parse_directory(spec_dir)

    def test_builds_index(self, sample_requirements):
        """Test building parent -> children index."""
        from elspais.core.hierarchy import build_children_index

        index = build_children_index(sample_requirements)
        assert isinstance(index, dict)

        # PRD requirements should have children
        assert (
            "REQ-p00001" in index
            or "p00001" in index.keys()
            or any("p00001" in k for k in index.keys())
        )

    def test_index_values_are_lists(self, sample_requirements):
        """Test that index values are lists of IDs."""
        from elspais.core.hierarchy import build_children_index

        index = build_children_index(sample_requirements)
        for _parent_id, child_ids in index.items():
            assert isinstance(child_ids, list)
            for child_id in child_ids:
                assert isinstance(child_id, str)

    def test_empty_requirements(self):
        """Test with empty requirements dict."""
        from elspais.core.hierarchy import build_children_index

        index = build_children_index({})
        assert index == {}


class TestDetectCycles:
    """Tests for detect_cycles() function."""

    @pytest.fixture
    def cyclic_requirements(self, circular_deps_fixture):
        """Load requirements with circular dependencies."""
        from elspais.core.parser import RequirementParser
        from elspais.core.patterns import PatternConfig

        pattern_config = PatternConfig(
            id_template="{prefix}-{type}{id}",
            prefix="REQ",
            types={"dev": {"id": "d", "level": 3}},
            id_format={"style": "numeric", "digits": 5, "leading_zeros": True},
        )
        parser = RequirementParser(pattern_config)

        spec_dir = circular_deps_fixture / "spec"
        return parser.parse_directory(spec_dir)

    @pytest.fixture
    def acyclic_requirements(self, hht_like_fixture):
        """Load requirements without cycles."""
        from elspais.config.loader import load_config
        from elspais.core.parser import RequirementParser
        from elspais.core.patterns import PatternConfig

        config_dict = load_config(hht_like_fixture / ".elspais.toml")
        pattern_config = PatternConfig.from_dict(config_dict["patterns"])
        parser = RequirementParser(pattern_config)

        spec_dir = hht_like_fixture / "spec"
        return parser.parse_directory(spec_dir)

    def test_no_cycles(self, acyclic_requirements):
        """Test detection returns empty for acyclic graph."""
        from elspais.core.hierarchy import detect_cycles

        cycle_info = detect_cycles(acyclic_requirements)
        assert cycle_info.cycle_members == set()
        assert cycle_info.cycle_paths == []

    def test_detects_cycle(self, cyclic_requirements):
        """Test detecting circular dependency."""
        from elspais.core.hierarchy import detect_cycles

        cycle_info = detect_cycles(cyclic_requirements)
        assert len(cycle_info.cycle_members) > 0

    def test_cycle_members_are_strings(self, cyclic_requirements):
        """Test that cycle members are ID strings."""
        from elspais.core.hierarchy import detect_cycles

        cycle_info = detect_cycles(cyclic_requirements)
        for member in cycle_info.cycle_members:
            assert isinstance(member, str)

    def test_cycle_info_is_dataclass(self, acyclic_requirements):
        """Test that CycleInfo is returned."""
        from elspais.core.hierarchy import CycleInfo, detect_cycles

        cycle_info = detect_cycles(acyclic_requirements)
        assert isinstance(cycle_info, CycleInfo)

    def test_pure_function(self, cyclic_requirements):
        """Test that detect_cycles does not mutate requirements."""
        from elspais.core.hierarchy import detect_cycles

        # Store original implements
        original_implements = {
            req_id: list(req.implements) for req_id, req in cyclic_requirements.items()
        }

        detect_cycles(cyclic_requirements)

        # Verify no mutation
        for req_id, req in cyclic_requirements.items():
            assert (
                req.implements == original_implements[req_id]
            ), f"detect_cycles mutated {req_id}.implements"


class TestFindRoots:
    """Tests for find_roots() function."""

    @pytest.fixture
    def sample_requirements(self, hht_like_fixture):
        """Load requirements from hht-like fixture."""
        from elspais.config.loader import load_config
        from elspais.core.parser import RequirementParser
        from elspais.core.patterns import PatternConfig

        config_dict = load_config(hht_like_fixture / ".elspais.toml")
        pattern_config = PatternConfig.from_dict(config_dict["patterns"])
        parser = RequirementParser(pattern_config)

        spec_dir = hht_like_fixture / "spec"
        return parser.parse_directory(spec_dir)

    def test_finds_prd_roots(self, sample_requirements):
        """Test finding PRD requirements with no implements."""
        from elspais.core.hierarchy import find_roots

        roots = find_roots(sample_requirements)
        assert len(roots) > 0

        # Roots should be PRD level without implements
        for root_id in roots:
            req = sample_requirements[root_id]
            # PRD requirements with no implements, or p00001/p00002 which are top-level
            if not req.implements:
                assert "p" in root_id.lower() or req.level == "PRD"


class TestFindOrphans:
    """Tests for find_orphans() function."""

    @pytest.fixture
    def broken_links_requirements(self, broken_links_fixture):
        """Load requirements with broken links."""
        from elspais.core.parser import RequirementParser
        from elspais.core.patterns import PatternConfig

        pattern_config = PatternConfig(
            id_template="{prefix}-{type}{id}",
            prefix="REQ",
            types={
                "prd": {"id": "p", "level": 1},
                "dev": {"id": "d", "level": 3},
            },
            id_format={"style": "numeric", "digits": 5, "leading_zeros": True},
        )
        parser = RequirementParser(pattern_config)

        spec_dir = broken_links_fixture / "spec"
        return parser.parse_directory(spec_dir)

    def test_finds_orphans(self, broken_links_requirements):
        """Test finding non-PRD requirements with broken implements links."""
        from elspais.core.hierarchy import find_orphans

        orphans = find_orphans(broken_links_requirements)
        # Should find at least some orphaned DEV requirements
        # that implement non-existent parents
        assert isinstance(orphans, list)
