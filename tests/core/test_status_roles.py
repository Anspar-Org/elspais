"""Unit tests for status role configuration and resolution."""

from elspais.config.status_roles import StatusRole, StatusRolesConfig


class TestStatusRolesConfig:
    # Implements: REQ-d00207-A
    def test_default_roles(self):
        """Default config classifies standard statuses correctly."""
        cfg = StatusRolesConfig.default()
        assert cfg.role_of("Active") == StatusRole.ACTIVE
        assert cfg.role_of("Draft") == StatusRole.PROVISIONAL
        assert cfg.role_of("Roadmap") == StatusRole.ASPIRATIONAL
        assert cfg.role_of("Deprecated") == StatusRole.RETIRED
        assert cfg.role_of("Superseded") == StatusRole.RETIRED

    # Implements: REQ-d00207-A
    def test_unknown_status_defaults_to_active(self):
        """Unclassified statuses default to active role."""
        cfg = StatusRolesConfig.default()
        assert cfg.role_of("SomethingNew") == StatusRole.ACTIVE

    # Implements: REQ-d00207-B
    def test_from_dict(self):
        """Parses status_roles from config dict."""
        cfg = StatusRolesConfig.from_dict(
            {
                "active": ["Active", "Review"],
                "provisional": ["Draft", "Proposed"],
                "aspirational": ["Future", "Idea"],
                "retired": ["Deprecated", "Archived"],
            }
        )
        assert cfg.role_of("Review") == StatusRole.ACTIVE
        assert cfg.role_of("Proposed") == StatusRole.PROVISIONAL
        assert cfg.role_of("Future") == StatusRole.ASPIRATIONAL
        assert cfg.role_of("Archived") == StatusRole.RETIRED

    # Implements: REQ-d00207-A
    def test_case_insensitive_lookup(self):
        cfg = StatusRolesConfig.default()
        assert cfg.role_of("active") == StatusRole.ACTIVE
        assert cfg.role_of("DRAFT") == StatusRole.PROVISIONAL
        assert cfg.role_of("ROADMAP") == StatusRole.ASPIRATIONAL
        assert cfg.role_of("deprecated") == StatusRole.RETIRED

    # Implements: REQ-d00086-A
    def test_is_excluded_from_coverage(self):
        """Provisional, aspirational, and retired are all excluded."""
        cfg = StatusRolesConfig.default()
        assert not cfg.is_excluded_from_coverage("Active")
        assert cfg.is_excluded_from_coverage("Draft")
        assert cfg.is_excluded_from_coverage("Roadmap")
        assert cfg.is_excluded_from_coverage("Deprecated")

    # Implements: REQ-d00086-A
    def test_is_excluded_from_analysis(self):
        """Only aspirational and retired are excluded from analysis."""
        cfg = StatusRolesConfig.default()
        assert not cfg.is_excluded_from_analysis("Active")
        assert not cfg.is_excluded_from_analysis("Draft")  # provisional: still in analysis
        assert cfg.is_excluded_from_analysis("Roadmap")  # aspirational: excluded
        assert cfg.is_excluded_from_analysis("Deprecated")  # retired: excluded

    # Implements: REQ-d00086-A
    def test_excluded_statuses_set(self):
        """Returns the set of status names excluded from coverage."""
        cfg = StatusRolesConfig.default()
        excluded = cfg.coverage_excluded_statuses()
        assert "Draft" in excluded
        assert "Roadmap" in excluded
        assert "Deprecated" in excluded
        assert "Active" not in excluded

    # Implements: REQ-d00207-A
    def test_default_hidden_statuses(self):
        """Only retired statuses are hidden by default in viewer."""
        cfg = StatusRolesConfig.default()
        hidden = cfg.default_hidden_statuses()
        assert "Deprecated" in hidden
        assert "Superseded" in hidden
        assert "Draft" not in hidden
        assert "Roadmap" not in hidden


class TestSortByRole:
    """Validates REQ-d00211-D: sort_by_role orders statuses by role priority."""

    # Implements: REQ-d00211-D
    def test_sort_by_role_orders_active_first(self):
        """Active statuses appear before provisional, aspirational, retired."""
        cfg = StatusRolesConfig(
            {
                "Active": StatusRole.ACTIVE,
                "Draft": StatusRole.PROVISIONAL,
                "Deprecated": StatusRole.RETIRED,
                "Proposed": StatusRole.PROVISIONAL,
                "Roadmap": StatusRole.ASPIRATIONAL,
            }
        )
        result = cfg.sort_by_role(["Deprecated", "Roadmap", "Draft", "Active", "Proposed"])
        assert result == ["Active", "Draft", "Proposed", "Roadmap", "Deprecated"]

    # Implements: REQ-d00211-D
    def test_sort_by_role_preserves_order_within_role(self):
        """Within a single role group, original list order is preserved."""
        cfg = StatusRolesConfig(
            {
                "Draft": StatusRole.PROVISIONAL,
                "Proposed": StatusRole.PROVISIONAL,
            }
        )
        result = cfg.sort_by_role(["Proposed", "Draft"])
        assert result == ["Proposed", "Draft"]

    # Implements: REQ-d00211-D
    def test_sort_by_role_unknown_status_treated_as_active(self):
        """Unknown statuses default to ACTIVE role, so they sort first."""
        cfg = StatusRolesConfig({"Draft": StatusRole.PROVISIONAL})
        result = cfg.sort_by_role(["Draft", "Custom"])
        assert result == ["Custom", "Draft"]
