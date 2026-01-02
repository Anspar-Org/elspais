"""
Tests for elspais.core.content_rules module.
"""

import pytest
from pathlib import Path


class TestFrontmatterParsing:
    """Tests for YAML frontmatter parsing."""

    def test_parse_frontmatter_with_metadata(self):
        """Test parsing markdown with YAML frontmatter."""
        from elspais.core.content_rules import parse_frontmatter

        text = """---
title: AI Agent Guidelines
type: guidance
applies_to:
  - requirements
  - assertions
---

# AI Agent Guidelines

This is the content.
"""
        metadata, content = parse_frontmatter(text)

        assert metadata["title"] == "AI Agent Guidelines"
        assert metadata["type"] == "guidance"
        assert "requirements" in metadata["applies_to"]
        assert "# AI Agent Guidelines" in content

    def test_parse_frontmatter_without_metadata(self):
        """Test parsing markdown without frontmatter."""
        from elspais.core.content_rules import parse_frontmatter

        text = """# Just Content

No frontmatter here.
"""
        metadata, content = parse_frontmatter(text)

        assert metadata == {}
        assert "# Just Content" in content

    def test_parse_frontmatter_empty_frontmatter(self):
        """Test parsing markdown with empty frontmatter."""
        from elspais.core.content_rules import parse_frontmatter

        text = """---
---

# Content after empty frontmatter
"""
        metadata, content = parse_frontmatter(text)

        assert metadata == {}
        assert "# Content after empty frontmatter" in content


class TestContentRuleLoading:
    """Tests for loading content rule files."""

    def test_load_content_rule(self, tmp_path):
        """Test loading a single content rule file."""
        from elspais.core.content_rules import load_content_rule

        rule_file = tmp_path / "AI-AGENT.md"
        rule_file.write_text("""---
title: AI Agent Guidelines
type: guidance
---

# AI Agent Guidelines

Follow these rules.
""")

        rule = load_content_rule(rule_file)

        assert rule.title == "AI Agent Guidelines"
        assert rule.type == "guidance"
        assert rule.file_path == rule_file
        assert "Follow these rules" in rule.content

    def test_load_content_rule_without_frontmatter(self, tmp_path):
        """Test loading content rule without frontmatter uses filename as title."""
        from elspais.core.content_rules import load_content_rule

        rule_file = tmp_path / "requirements-spec.md"
        rule_file.write_text("# Requirements Spec\n\nContent here.")

        rule = load_content_rule(rule_file)

        assert rule.title == "requirements-spec.md"
        assert rule.type == "guidance"  # default
        assert "Content here" in rule.content

    def test_load_content_rule_missing_file(self, tmp_path):
        """Test loading missing file raises error."""
        from elspais.core.content_rules import load_content_rule

        with pytest.raises(FileNotFoundError):
            load_content_rule(tmp_path / "nonexistent.md")


class TestContentRulesFromConfig:
    """Tests for loading content rules from configuration."""

    def test_load_content_rules_from_config(self, tmp_path):
        """Test loading multiple content rules from config."""
        from elspais.core.content_rules import load_content_rules

        # Create content rule files
        (tmp_path / "spec").mkdir()
        (tmp_path / "spec" / "AI-AGENT.md").write_text("""---
title: AI Agent Guidelines
---
# Guidelines
""")
        (tmp_path / "spec" / "requirements-spec.md").write_text("""---
title: Requirements Specification
---
# Spec
""")

        config = {
            "rules": {
                "content_rules": ["spec/AI-AGENT.md", "spec/requirements-spec.md"]
            }
        }

        rules = load_content_rules(config, tmp_path)

        assert len(rules) == 2
        assert rules[0].title == "AI Agent Guidelines"
        assert rules[1].title == "Requirements Specification"

    def test_load_content_rules_empty_config(self, tmp_path):
        """Test loading with no content rules configured."""
        from elspais.core.content_rules import load_content_rules

        config = {"rules": {}}
        rules = load_content_rules(config, tmp_path)

        assert rules == []

    def test_load_content_rules_missing_file_skipped(self, tmp_path):
        """Test that missing files are skipped with warning."""
        from elspais.core.content_rules import load_content_rules

        # Create only one of two configured files
        (tmp_path / "exists.md").write_text("# Exists")

        config = {
            "rules": {
                "content_rules": ["exists.md", "missing.md"]
            }
        }

        rules = load_content_rules(config, tmp_path)

        assert len(rules) == 1
        assert rules[0].file_path.name == "exists.md"


class TestGetContentRules:
    """Tests for get_content_rules config helper."""

    def test_get_content_rules_paths(self, tmp_path):
        """Test getting content rule paths from config."""
        from elspais.config.loader import get_content_rules

        config = {
            "rules": {
                "content_rules": ["spec/AI-AGENT.md", "spec/rules.md"]
            }
        }

        paths = get_content_rules(config, tmp_path)

        assert len(paths) == 2
        assert paths[0] == tmp_path / "spec" / "AI-AGENT.md"
        assert paths[1] == tmp_path / "spec" / "rules.md"

    def test_get_content_rules_empty(self, tmp_path):
        """Test getting content rules when none configured."""
        from elspais.config.loader import get_content_rules

        config = {"rules": {}}
        paths = get_content_rules(config, tmp_path)

        assert paths == []


class TestContentRuleModel:
    """Tests for ContentRule dataclass."""

    def test_content_rule_creation(self):
        """Test creating a ContentRule."""
        from elspais.core.models import ContentRule
        from pathlib import Path

        rule = ContentRule(
            file_path=Path("spec/AI-AGENT.md"),
            title="AI Agent Guidelines",
            content="# Guidelines\n\nFollow these rules.",
            type="guidance",
            applies_to=["requirements"],
        )

        assert rule.title == "AI Agent Guidelines"
        assert rule.type == "guidance"
        assert "requirements" in rule.applies_to

    def test_content_rule_defaults(self):
        """Test ContentRule default values."""
        from elspais.core.models import ContentRule
        from pathlib import Path

        rule = ContentRule(
            file_path=Path("test.md"),
            title="Test",
            content="Content",
        )

        assert rule.type == "guidance"
        assert rule.applies_to == []


class TestRulesCommand:
    """Tests for the rules CLI command."""

    def test_rules_list(self, tmp_path, capsys):
        """Test rules list command."""
        import argparse
        import os
        from elspais.commands.rules_cmd import run

        # Create config and content rule
        config_file = tmp_path / ".elspais.toml"
        config_file.write_text("""
[project]
name = "test"

[rules]
content_rules = ["AI-AGENT.md"]
""")
        (tmp_path / "AI-AGENT.md").write_text("""---
title: AI Agent Guidelines
type: guidance
---
# Guidelines
""")

        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            args = argparse.Namespace(
                config=None,
                rules_action="list",
                quiet=False,
            )
            result = run(args)
            assert result == 0

            captured = capsys.readouterr()
            assert "AI-AGENT.md" in captured.out
        finally:
            os.chdir(original_cwd)

    def test_rules_show(self, tmp_path, capsys):
        """Test rules show command."""
        import argparse
        import os
        from elspais.commands.rules_cmd import run

        # Create config and content rule
        config_file = tmp_path / ".elspais.toml"
        config_file.write_text("""
[project]
name = "test"

[rules]
content_rules = ["AI-AGENT.md"]
""")
        (tmp_path / "AI-AGENT.md").write_text("""---
title: AI Agent Guidelines
---
# AI Agent Guidelines

Follow these rules when authoring requirements.
""")

        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            args = argparse.Namespace(
                config=None,
                rules_action="show",
                file="AI-AGENT.md",
                quiet=False,
            )
            result = run(args)
            assert result == 0

            captured = capsys.readouterr()
            assert "Follow these rules" in captured.out
        finally:
            os.chdir(original_cwd)
