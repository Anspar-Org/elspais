"""
Tests for elspais.mcp.transforms module.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock


class TestClaudeInvoker:
    """Tests for ClaudeInvoker."""

    def test_invoke_success(self):
        """Test successful Claude invocation."""
        from elspais.mcp.transforms import ClaudeInvoker

        invoker = ClaudeInvoker()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="# REQ-p00001: Updated Title\n\nNew content",
                stderr="",
            )

            success, output, error = invoker.invoke(
                prompt="Add a risk section",
                input_data={"id": "REQ-p00001"},
                output_format="text",
            )

            assert success is True
            assert "Updated Title" in output
            assert error is None

    def test_invoke_failure(self):
        """Test failed Claude invocation."""
        from elspais.mcp.transforms import ClaudeInvoker

        invoker = ClaudeInvoker()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=1,
                stdout="",
                stderr="API error",
            )

            success, output, error = invoker.invoke(
                prompt="test",
                input_data={},
            )

            assert success is False
            assert error == "API error"

    def test_invoke_timeout(self):
        """Test Claude invocation timeout."""
        from elspais.mcp.transforms import ClaudeInvoker
        import subprocess

        invoker = ClaudeInvoker(timeout=1)

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="claude", timeout=1)

            success, output, error = invoker.invoke(
                prompt="test",
                input_data={},
            )

            assert success is False
            assert "timed out" in error

    def test_invoke_not_found(self):
        """Test Claude CLI not found."""
        from elspais.mcp.transforms import ClaudeInvoker

        invoker = ClaudeInvoker()

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError()

            success, output, error = invoker.invoke(
                prompt="test",
                input_data={},
            )

            assert success is False
            assert "not found" in error


class TestOutputMode:
    """Tests for OutputMode constants."""

    def test_output_modes(self):
        """Test output mode values."""
        from elspais.mcp.transforms import OutputMode

        assert OutputMode.REPLACE == "replace"
        assert OutputMode.PATCH == "patch"
        assert OutputMode.OPERATIONS == "operations"


class TestTransformResult:
    """Tests for TransformResult dataclass."""

    def test_create_success_result(self):
        """Test creating a success result."""
        from elspais.mcp.transforms import TransformResult

        result = TransformResult(
            success=True,
            node_id="REQ-p00001",
            safety_branch="elspais-safety/ai-transform-20240125",
            before_text="# REQ-p00001: Old",
            after_text="# REQ-p00001: New",
            dry_run=False,
        )

        assert result.success is True
        assert result.node_id == "REQ-p00001"
        assert result.safety_branch is not None
        assert result.error is None

    def test_create_error_result(self):
        """Test creating an error result."""
        from elspais.mcp.transforms import TransformResult

        result = TransformResult(
            success=False,
            node_id="REQ-p00001",
            error="Requirement not found",
        )

        assert result.success is False
        assert result.error == "Requirement not found"


class TestAITransformer:
    """Tests for AITransformer."""

    @pytest.fixture
    def mock_context(self, tmp_path):
        """Create a mock WorkspaceContext."""
        context = Mock()
        context.working_dir = tmp_path
        context.get_graph.return_value = (Mock(), Mock())
        context.invalidate_cache = Mock()
        return context

    @pytest.fixture
    def mock_invoker(self):
        """Create a mock ClaudeInvoker."""
        invoker = Mock()
        invoker.invoke.return_value = (True, "# REQ-p00001: Updated\n\n**Level**: PRD", None)
        return invoker

    def test_transform_requirement_not_found(self, mock_context):
        """Test transform with non-existent requirement."""
        from elspais.mcp.transforms import AITransformer

        mock_context.get_requirement.return_value = None

        transformer = AITransformer(mock_context.working_dir)
        result = transformer.transform(
            node_id="REQ-p99999",
            prompt="Add risk section",
            output_mode="replace",
            save_branch=False,
            dry_run=True,
            context=mock_context,
        )

        assert result.success is False
        assert "not found" in result.error

    def test_transform_invalid_output_mode(self, mock_context):
        """Test transform with invalid output mode."""
        from elspais.mcp.transforms import AITransformer

        transformer = AITransformer(mock_context.working_dir)
        result = transformer.transform(
            node_id="REQ-p00001",
            prompt="test",
            output_mode="invalid",
            save_branch=False,
            dry_run=True,
            context=mock_context,
        )

        assert result.success is False
        assert "Invalid output_mode" in result.error

    def test_transform_dry_run(self, mock_context, mock_invoker, tmp_path):
        """Test transform in dry run mode."""
        from elspais.mcp.transforms import AITransformer
        from elspais.core.models import Requirement

        # Create a test requirement
        req = Requirement(
            id="REQ-p00001",
            title="Test Requirement",
            level="PRD",
            status="Active",
            body="Original body",
            file_path=tmp_path / "spec" / "test.md",
            line_number=1,
        )
        mock_context.get_requirement.return_value = req

        # Mock the graph node
        mock_node = Mock()
        mock_node.source = None
        mock_node.metrics = {}
        mock_node.children = []
        mock_graph = Mock()
        mock_graph.find_by_id.return_value = mock_node
        mock_context.get_graph.return_value = (mock_graph, Mock())

        transformer = AITransformer(
            mock_context.working_dir,
            invoker=mock_invoker,
        )

        result = transformer.transform(
            node_id="REQ-p00001",
            prompt="Add risk section",
            output_mode="replace",
            save_branch=False,
            dry_run=True,
            context=mock_context,
        )

        assert result.success is True
        assert result.dry_run is True
        assert result.after_text is not None
        # File should not be modified in dry run
        mock_context.invalidate_cache.assert_not_called()

    def test_transform_operations_mode(self, mock_context, tmp_path):
        """Test transform with operations output mode."""
        from elspais.mcp.transforms import AITransformer
        from elspais.core.models import Requirement

        # Create a test requirement
        req = Requirement(
            id="REQ-p00001",
            title="Test Requirement",
            level="PRD",
            status="Active",
            body="Original body",
        )
        mock_context.get_requirement.return_value = req

        # Mock the graph
        mock_node = Mock()
        mock_node.source = None
        mock_node.metrics = {}
        mock_node.children = []
        mock_graph = Mock()
        mock_graph.find_by_id.return_value = mock_node
        mock_context.get_graph.return_value = (mock_graph, Mock())

        # Mock Claude to return operations JSON
        mock_invoker = Mock()
        operations = [
            {"type": "add_section", "target": "Risk", "value": "## Risk\n\nRisk content"},
        ]
        mock_invoker.invoke.return_value = (True, json.dumps(operations), None)

        transformer = AITransformer(
            mock_context.working_dir,
            invoker=mock_invoker,
        )

        result = transformer.transform(
            node_id="REQ-p00001",
            prompt="Add risk section",
            output_mode="operations",
            save_branch=False,
            dry_run=True,
            context=mock_context,
        )

        assert result.success is True
        assert len(result.operations) == 1
        assert result.operations[0]["type"] == "add_section"

    def test_extract_markdown_raw(self):
        """Test extracting raw markdown."""
        from elspais.mcp.transforms import AITransformer

        transformer = AITransformer(Path("."))

        md = transformer._extract_markdown("# REQ-p00001: Title\n\nBody")
        assert md.startswith("# REQ-p00001")

    def test_extract_markdown_code_block(self):
        """Test extracting markdown from code block."""
        from elspais.mcp.transforms import AITransformer

        transformer = AITransformer(Path("."))

        output = "```markdown\n# REQ-p00001: Title\n\nBody\n```"
        md = transformer._extract_markdown(output)
        assert md.startswith("# REQ-p00001")

    def test_extract_markdown_json(self):
        """Test extracting markdown from JSON."""
        from elspais.mcp.transforms import AITransformer

        transformer = AITransformer(Path("."))

        output = json.dumps({"content": "# REQ-p00001: Title"})
        md = transformer._extract_markdown(output)
        assert md.startswith("# REQ-p00001")


class TestRestoreFromSafetyBranch:
    """Tests for restore_from_safety_branch function."""

    def test_restore_function(self, tmp_path):
        """Test the restore convenience function."""
        from elspais.mcp.transforms import restore_from_safety_branch

        with patch("elspais.mcp.transforms.GitSafetyManager") as MockManager:
            mock_manager = MockManager.return_value
            mock_manager.restore_from_branch.return_value = (True, "Restored")

            success, message = restore_from_safety_branch(
                tmp_path,
                "elspais-safety/test-branch",
            )

            assert success is True
            assert message == "Restored"
