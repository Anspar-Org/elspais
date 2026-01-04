"""
tests/test_doc_sync.py - Documentation-Implementation Synchronization Tests

These tests verify that documentation matches the actual implementation,
preventing drift between docs and code.
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest

# Project root
PROJECT_ROOT = Path(__file__).parent.parent
README = PROJECT_ROOT / "README.md"
DOCS_DIR = PROJECT_ROOT / "docs"
CONFIG_DOCS = DOCS_DIR / "configuration.md"
RULES_DOCS = DOCS_DIR / "rules.md"


class TestCLIDocumentation:
    """Tests that CLI commands and options are documented."""

    def test_all_cli_commands_in_readme(self):
        """Verify all CLI subcommands are listed in README."""
        # Get commands from CLI
        result = subprocess.run(
            [sys.executable, "-m", "elspais", "--help"],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
        )
        assert result.returncode == 0, f"CLI help failed: {result.stderr}"

        # Parse commands from help output (after "Commands:" section)
        help_text = result.stdout
        commands_section = help_text.split("Commands:")[1] if "Commands:" in help_text else ""

        # Extract command names (first word on each line in commands section)
        cli_commands = set()
        for line in commands_section.split("\n"):
            line = line.strip()
            if line and not line.startswith("-"):
                cmd = line.split()[0] if line.split() else ""
                if cmd and cmd.isalpha():
                    cli_commands.add(cmd)

        # Check README contains each command
        readme_text = README.read_text()

        missing = []
        for cmd in cli_commands:
            # Look for command in the CLI reference section
            if f"  {cmd}" not in readme_text and f" {cmd} " not in readme_text:
                missing.append(cmd)

        assert not missing, f"Commands missing from README: {missing}"

    def test_edit_command_documented(self):
        """Verify the edit command is documented in README."""
        readme_text = README.read_text()
        assert "edit" in readme_text.lower(), "edit command should be documented in README"

    def test_global_options_documented(self):
        """Verify global CLI options are documented."""
        readme_text = README.read_text()

        expected_options = ["--config", "--spec-dir", "--verbose", "--quiet", "--version"]
        for opt in expected_options:
            assert opt in readme_text, f"Global option {opt} not documented in README"


class TestConfigurationDocumentation:
    """Tests that configuration options are documented."""

    def test_no_deprecated_require_acceptance_in_docs(self):
        """Verify deprecated require_acceptance is not in docs."""
        for doc_file in DOCS_DIR.glob("*.md"):
            content = doc_file.read_text()
            # Allow it only in historical context or explicit deprecation notice
            occurrences = content.count("require_acceptance")
            if occurrences > 0:
                # Check if it's in a deprecation context
                assert "deprecated" in content.lower() or "legacy" in content.lower(), \
                    f"Found require_acceptance in {doc_file.name} without deprecation context"

    def test_no_deprecated_require_acceptance_in_code(self):
        """Verify deprecated require_acceptance is not used in production code."""
        from elspais.config.defaults import DEFAULT_CONFIG

        # Flatten config to string for easy search
        config_str = str(DEFAULT_CONFIG)
        assert "require_acceptance" not in config_str, \
            "require_acceptance should not be in DEFAULT_CONFIG"

    def test_require_assertions_in_defaults(self):
        """Verify require_assertions is the current config option."""
        from elspais.config.defaults import DEFAULT_CONFIG

        format_rules = DEFAULT_CONFIG.get("rules", {}).get("format", {})
        assert "require_assertions" in format_rules, \
            "require_assertions should be in DEFAULT_CONFIG"

    def test_id_template_default_matches_docs(self):
        """Verify id_template default in docs matches defaults.py."""
        from elspais.config.defaults import DEFAULT_CONFIG

        actual_default = DEFAULT_CONFIG.get("patterns", {}).get("id_template", "")
        doc_content = CONFIG_DOCS.read_text()

        # The documented default should match actual
        assert actual_default in doc_content, \
            f"Default id_template '{actual_default}' not found in docs/configuration.md"


class TestRulesDocumentation:
    """Tests that validation rules are documented."""

    def test_core_rules_documented(self):
        """Verify core rule concepts are documented in rules.md."""
        rules_content = RULES_DOCS.read_text()

        # Check that key rule concepts are documented
        # The actual rule names may appear in different formats in docs
        required_concepts = [
            ("hierarchy", "implements"),  # hierarchy.implements - allowed relationships
            ("hierarchy", "circular"),    # hierarchy.circular - cycle detection
            ("hierarchy", "orphan"),      # hierarchy.orphan - orphaned requirements
            ("hash", "mismatch"),         # hash.mismatch - hash verification
            ("link", "broken"),           # link.broken - broken references
            ("format", "require_assertions"),  # format.require_assertions
            ("format", "labels_unique"),  # format.labels_unique
            ("format", "labels_sequential"),  # format.labels_sequential
        ]

        missing = []
        for category, concept in required_concepts:
            # Check if both category and concept appear in docs
            # They may be in different formats: [category.concept], category.concept, etc.
            if category not in rules_content.lower() or concept not in rules_content.lower():
                missing.append(f"{category}.{concept}")

        assert not missing, f"Rule concepts not documented in rules.md: {missing}"

    def test_format_status_valid_documented(self):
        """Verify format.status_valid rule is documented."""
        rules_content = RULES_DOCS.read_text()
        assert "status_valid" in rules_content, \
            "format.status_valid rule should be documented"


class TestInitCommand:
    """Tests for init command documentation."""

    def test_init_associated_syntax_correct(self):
        """Verify init command syntax for associated repos is correct."""
        readme_text = README.read_text()

        # The correct syntax uses --associated-prefix flag
        assert "--associated-prefix" in readme_text, \
            "README should show --associated-prefix flag for init command"

        # Should NOT have the incorrect "init --type associated CAL" syntax
        incorrect_pattern = r"init\s+--type\s+associated\s+[A-Z]{2,4}\s"
        assert not re.search(incorrect_pattern, readme_text), \
            "README has incorrect init syntax (CAL should be --associated-prefix CAL)"

    def test_init_templates_use_current_config(self):
        """Verify init command templates use current config options."""
        from elspais.commands.init import generate_config

        core_config = generate_config("core")
        associated_config = generate_config("associated", "TEST")

        # Should use require_assertions, not require_acceptance
        assert "require_assertions" in core_config, \
            "Core template should use require_assertions"
        assert "require_acceptance" not in core_config, \
            "Core template should not use deprecated require_acceptance"

        assert "require_assertions" in associated_config, \
            "Associated template should use require_assertions"


class TestUnimplementedFeatures:
    """Tests that unimplemented features are marked as such."""

    def test_combined_flag_marked_as_planned(self):
        """Verify --combined flag is marked as planned/unimplemented."""
        multi_repo_docs = DOCS_DIR / "multi-repo.md"
        content = multi_repo_docs.read_text()

        # If --combined is mentioned, it should be marked as planned
        if "--combined" in content:
            assert "planned" in content.lower() or "not yet" in content.lower(), \
                "--combined flag should be marked as planned/not yet implemented"


# Run verification as standalone script too
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
