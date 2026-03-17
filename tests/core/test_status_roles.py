"""Unit tests for status role configuration and resolution."""

from elspais.config.status_roles import StatusRole, StatusRolesConfig


class TestStatusRolesConfig:
    def test_default_roles(self):
        """Default config classifies standard statuses correctly."""
        cfg = StatusRolesConfig.default()
        assert cfg.role_of("Active") == StatusRole.ACTIVE
        assert cfg.role_of("Draft") == StatusRole.PROVISIONAL
        assert cfg.role_of("Roadmap") == StatusRole.ASPIRATIONAL
        assert cfg.role_of("Deprecated") == StatusRole.RETIRED
        assert cfg.role_of("Superseded") == StatusRole.RETIRED

    def test_unknown_status_defaults_to_active(self):
        """Unclassified statuses default to active role."""
        cfg = StatusRolesConfig.default()
        assert cfg.role_of("SomethingNew") == StatusRole.ACTIVE

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

    def test_case_insensitive_lookup(self):
        cfg = StatusRolesConfig.default()
        assert cfg.role_of("active") == StatusRole.ACTIVE
        assert cfg.role_of("DRAFT") == StatusRole.PROVISIONAL
        assert cfg.role_of("ROADMAP") == StatusRole.ASPIRATIONAL
        assert cfg.role_of("deprecated") == StatusRole.RETIRED

    def test_is_excluded_from_coverage(self):
        """Provisional, aspirational, and retired are all excluded."""
        cfg = StatusRolesConfig.default()
        assert not cfg.is_excluded_from_coverage("Active")
        assert cfg.is_excluded_from_coverage("Draft")
        assert cfg.is_excluded_from_coverage("Roadmap")
        assert cfg.is_excluded_from_coverage("Deprecated")

    def test_is_excluded_from_analysis(self):
        """Only aspirational and retired are excluded from analysis."""
        cfg = StatusRolesConfig.default()
        assert not cfg.is_excluded_from_analysis("Active")
        assert not cfg.is_excluded_from_analysis("Draft")  # provisional: still in analysis
        assert cfg.is_excluded_from_analysis("Roadmap")  # aspirational: excluded
        assert cfg.is_excluded_from_analysis("Deprecated")  # retired: excluded

    def test_excluded_statuses_set(self):
        """Returns the set of status names excluded from coverage."""
        cfg = StatusRolesConfig.default()
        excluded = cfg.coverage_excluded_statuses()
        assert "Draft" in excluded
        assert "Roadmap" in excluded
        assert "Deprecated" in excluded
        assert "Active" not in excluded

    def test_default_hidden_statuses(self):
        """Only retired statuses are hidden by default in viewer."""
        cfg = StatusRolesConfig.default()
        hidden = cfg.default_hidden_statuses()
        assert "Deprecated" in hidden
        assert "Superseded" in hidden
        assert "Draft" not in hidden
        assert "Roadmap" not in hidden
