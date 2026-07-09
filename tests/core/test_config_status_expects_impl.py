# Verifies: REQ-d00258-L
"""Tests for the status_expects_implementation resolver (config layer)."""

from elspais.config import config_defaults, status_expects_implementation


class TestStatusExpectsImplementationRoleDefault:
    """With no explicit per-status flag, the status ROLE decides."""

    def test_default_config_active_expects_implementation(self):
        cfg = config_defaults()
        assert status_expects_implementation(cfg, "Active") is True

    def test_default_config_draft_does_not_expect(self):
        cfg = config_defaults()
        assert status_expects_implementation(cfg, "Draft") is False

    def test_default_config_deprecated_does_not_expect(self):
        cfg = config_defaults()
        assert status_expects_implementation(cfg, "Deprecated") is False

    def test_hht_style_active_role_makes_draft_expect(self):
        """[rules.format.status_roles] active=[Active,Draft] -> Draft is
        active-role, so it derives expects_implementation=True."""
        cfg = {"rules": {"format": {"status_roles": {"active": ["Active", "Draft"]}}}}
        assert status_expects_implementation(cfg, "Draft") is True

    def test_unknown_status_expects_implementation(self):
        """role_of defaults unknown statuses to ACTIVE, so an unknown status
        derives expects_implementation=True."""
        assert status_expects_implementation({}, "Wibble") is True


class TestStatusExpectsImplementationExplicitFlag:
    """An explicit [statuses.<Name>].expects_implementation wins over role."""

    def test_explicit_true_overrides_provisional_role(self):
        cfg = {"statuses": {"Draft": {"expects_implementation": True}}}
        assert status_expects_implementation(cfg, "Draft") is True

    def test_explicit_false_overrides_active_role(self):
        """Explicit wins even against an active-role status."""
        cfg = {"statuses": {"Active": {"expects_implementation": False}}}
        assert status_expects_implementation(cfg, "Active") is False

    def test_explicit_flag_case_insensitive_on_status_name(self):
        cfg = {"statuses": {"Draft": {"expects_implementation": True}}}
        assert status_expects_implementation(cfg, "draft") is True

    def test_none_flag_falls_through_to_role(self):
        """Explicit None does not win; role default applies (Draft -> False)."""
        cfg = {"statuses": {"Draft": {"expects_implementation": None}}}
        assert status_expects_implementation(cfg, "Draft") is False
