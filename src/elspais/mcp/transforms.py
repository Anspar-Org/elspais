"""
elspais.mcp.transforms - AI-assisted transformation of graph nodes.

Provides the AITransformer class for calling Claude to transform
requirement content with git safety and dry-run support.
"""

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from elspais.mcp.git_safety import GitSafetyManager, SafetyBranchResult
from elspais.mcp.mutator import SpecFileMutator
from elspais.mcp.serializers import serialize_node_full

if TYPE_CHECKING:
    from elspais.mcp.context import WorkspaceContext


class OutputMode:
    """Output modes for AI transformation."""

    REPLACE = "replace"  # Claude returns new requirement markdown
    PATCH = "patch"  # Claude returns diff/changes
    OPERATIONS = "operations"  # Claude returns operation list


@dataclass
class TransformResult:
    """
    Result of an AI transformation operation.

    Attributes:
        success: Whether the transformation succeeded
        node_id: The ID of the transformed node
        safety_branch: Git branch created for safety (if any)
        before_text: Original requirement text
        after_text: New requirement text (if success)
        operations: List of operations (if output_mode="operations")
        claude_output: Raw output from Claude
        error: Error message (if failed)
        dry_run: Whether this was a dry-run (no changes applied)
        file_path: Path to the modified file (if changes applied)
    """

    success: bool
    node_id: str
    safety_branch: Optional[str] = None
    before_text: Optional[str] = None
    after_text: Optional[str] = None
    operations: List[Dict[str, Any]] = field(default_factory=list)
    claude_output: Optional[str] = None
    error: Optional[str] = None
    dry_run: bool = False
    file_path: Optional[str] = None


class ClaudeInvoker:
    """
    Handles invocation of Claude CLI for AI transformations.

    Encapsulates the subprocess call to `claude -p` and response parsing.
    """

    DEFAULT_TIMEOUT = 120  # seconds

    def __init__(self, timeout: int = DEFAULT_TIMEOUT):
        """
        Initialize the Claude invoker.

        Args:
            timeout: Timeout in seconds for Claude invocations
        """
        self.timeout = timeout

    def invoke(
        self,
        prompt: str,
        input_data: Dict[str, Any],
        output_format: str = "json",
    ) -> tuple[bool, str, Optional[str]]:
        """
        Invoke Claude with a prompt and input data.

        Args:
            prompt: The prompt to send to Claude
            input_data: JSON-serializable data to pass as stdin
            output_format: Output format ("json" or "text")

        Returns:
            Tuple of (success, output, error)
        """
        try:
            # Build command
            cmd = ["claude", "-p", prompt, "--output-format", output_format]

            # Serialize input
            input_json = json.dumps(input_data, indent=2)

            # Run Claude
            result = subprocess.run(
                cmd,
                input=input_json,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )

            if result.returncode != 0:
                error_msg = result.stderr.strip() or f"Exit code: {result.returncode}"
                return False, "", error_msg

            return True, result.stdout, None

        except subprocess.TimeoutExpired:
            return False, "", f"Claude invocation timed out after {self.timeout}s"
        except FileNotFoundError:
            return False, "", "Claude CLI not found. Install with: npm install -g @anthropic-ai/claude-code"
        except Exception as e:
            return False, "", str(e)


class AITransformer:
    """
    AI-powered transformation of graph nodes.

    Provides the `transform` method which:
    1. Serializes a node to JSON
    2. Optionally creates a git safety branch
    3. Calls Claude with the prompt and node data
    4. Parses the response based on output_mode
    5. Applies changes (or returns dry_run preview)

    Example usage:
        transformer = AITransformer(working_dir, mutator)
        result = transformer.transform(
            node_id="REQ-p00001",
            prompt="Add a ## Risk section analyzing potential failure modes",
            output_mode="replace",
            save_branch=True,
            dry_run=False,
            context=context,
        )
    """

    # System prompt for transformation operations
    SYSTEM_PROMPT_REPLACE = """You are transforming a requirement specification.
You will receive a JSON object containing the full requirement data.
Return ONLY the new requirement markdown text, nothing else.
Preserve the existing format including:
- The requirement header (# REQ-xxx: Title)
- The metadata line (**Level**: ... | **Status**: ...)
- The ## Assertions section with labeled assertions (A., B., etc.)
- The *End* marker line with hash

Make the requested changes while preserving the overall structure."""

    SYSTEM_PROMPT_OPERATIONS = """You are analyzing a requirement for changes.
You will receive a JSON object containing the full requirement data.
Return a JSON array of operations to perform on this requirement.

Each operation should be an object with:
- "type": The operation type (e.g., "add_assertion", "modify_assertion", "add_section", "update_field")
- "target": What to modify (e.g., assertion label, section name, field name)
- "value": The new value or content

Example response:
[
  {"type": "add_section", "target": "Risk", "value": "## Risk\\n\\nPotential failure modes include..."},
  {"type": "modify_assertion", "target": "A", "value": "Updated assertion text..."}
]"""

    def __init__(
        self,
        working_dir: Path,
        mutator: Optional[SpecFileMutator] = None,
        invoker: Optional[ClaudeInvoker] = None,
    ):
        """
        Initialize the AI transformer.

        Args:
            working_dir: Root directory of the workspace
            mutator: SpecFileMutator for file operations (created if not provided)
            invoker: ClaudeInvoker for Claude calls (created if not provided)
        """
        self.working_dir = working_dir
        self.mutator = mutator or SpecFileMutator(working_dir)
        self.invoker = invoker or ClaudeInvoker()
        self.git_safety = GitSafetyManager(working_dir)

    def transform(
        self,
        node_id: str,
        prompt: str,
        output_mode: str,
        save_branch: bool,
        dry_run: bool,
        context: "WorkspaceContext",
    ) -> TransformResult:
        """
        Transform a node using AI.

        Args:
            node_id: ID of the node to transform
            prompt: What transformation to perform
            output_mode: How Claude should return results:
                - "replace": Return new requirement markdown
                - "patch": Return diff/changes (not yet implemented)
                - "operations": Return list of operations
            save_branch: Create a git safety branch before changes
            dry_run: Preview without applying changes
            context: WorkspaceContext for accessing requirements and graph

        Returns:
            TransformResult with the operation outcome
        """
        # Validate output_mode
        if output_mode not in (OutputMode.REPLACE, OutputMode.PATCH, OutputMode.OPERATIONS):
            return TransformResult(
                success=False,
                node_id=node_id,
                error=f"Invalid output_mode: {output_mode}. Must be 'replace', 'patch', or 'operations'",
            )

        # Get the requirement
        req = context.get_requirement(node_id)
        if req is None:
            return TransformResult(
                success=False,
                node_id=node_id,
                error=f"Requirement {node_id} not found",
            )

        # Serialize node to JSON
        node_json = serialize_node_full(req, context, include_full_text=True)

        # Get the original text
        before_text = node_json.get("full_text")

        # Create safety branch if requested (and not dry_run)
        safety_branch = None
        if save_branch and not dry_run:
            branch_result = self._create_safety_branch(node_id)
            if not branch_result.success:
                return TransformResult(
                    success=False,
                    node_id=node_id,
                    error=f"Failed to create safety branch: {branch_result.message}",
                )
            safety_branch = branch_result.branch_name

        # Invoke Claude
        full_prompt = self._build_prompt(prompt, output_mode)
        success, output, error = self.invoker.invoke(
            prompt=full_prompt,
            input_data=node_json,
            output_format="json" if output_mode == OutputMode.OPERATIONS else "text",
        )

        if not success:
            return TransformResult(
                success=False,
                node_id=node_id,
                safety_branch=safety_branch,
                before_text=before_text,
                error=error or "Claude invocation failed",
            )

        # Parse and apply based on output_mode
        if output_mode == OutputMode.REPLACE:
            return self._apply_replacement(
                node_id=node_id,
                req=req,
                before_text=before_text,
                claude_output=output,
                safety_branch=safety_branch,
                dry_run=dry_run,
                context=context,
            )
        elif output_mode == OutputMode.OPERATIONS:
            return self._apply_operations(
                node_id=node_id,
                req=req,
                before_text=before_text,
                claude_output=output,
                safety_branch=safety_branch,
                dry_run=dry_run,
                context=context,
            )
        else:  # PATCH
            return TransformResult(
                success=False,
                node_id=node_id,
                safety_branch=safety_branch,
                before_text=before_text,
                claude_output=output,
                error="Patch mode not yet implemented",
                dry_run=dry_run,
            )

    def _build_prompt(self, user_prompt: str, output_mode: str) -> str:
        """Build the full prompt including system instructions."""
        if output_mode == OutputMode.OPERATIONS:
            system = self.SYSTEM_PROMPT_OPERATIONS
        else:
            system = self.SYSTEM_PROMPT_REPLACE

        return f"{system}\n\nUser request: {user_prompt}"

    def _create_safety_branch(self, node_id: str) -> SafetyBranchResult:
        """Create a git safety branch for the operation."""
        return self.git_safety.create_safety_branch(
            operation_name="ai-transform",
            node_ids=[node_id],
        )

    def _apply_replacement(
        self,
        node_id: str,
        req: Any,
        before_text: Optional[str],
        claude_output: str,
        safety_branch: Optional[str],
        dry_run: bool,
        context: "WorkspaceContext",
    ) -> TransformResult:
        """Apply a replacement transformation."""
        # Parse Claude's output - extract just the markdown content
        after_text = self._extract_markdown(claude_output)

        if not after_text:
            return TransformResult(
                success=False,
                node_id=node_id,
                safety_branch=safety_branch,
                before_text=before_text,
                claude_output=claude_output,
                error="Could not extract markdown from Claude's response",
                dry_run=dry_run,
            )

        if dry_run:
            return TransformResult(
                success=True,
                node_id=node_id,
                safety_branch=safety_branch,
                before_text=before_text,
                after_text=after_text,
                claude_output=claude_output,
                dry_run=True,
            )

        # Apply the change
        if not req.file_path:
            return TransformResult(
                success=False,
                node_id=node_id,
                safety_branch=safety_branch,
                before_text=before_text,
                after_text=after_text,
                claude_output=claude_output,
                error=f"Requirement {node_id} has no file path",
            )

        try:
            # Read the file
            content = self.mutator._read_spec_file(Path(req.file_path))
            location = self.mutator._find_requirement_lines(content, node_id)

            if location is None:
                return TransformResult(
                    success=False,
                    node_id=node_id,
                    safety_branch=safety_branch,
                    before_text=before_text,
                    after_text=after_text,
                    claude_output=claude_output,
                    error=f"Could not find {node_id} in {req.file_path}",
                )

            # Replace the requirement text
            new_content = self.mutator.replace_requirement_text(
                content, location, after_text
            )

            # Write back to file
            self.mutator._write_spec_file(Path(req.file_path), new_content)

            # Invalidate caches
            context.invalidate_cache()

            return TransformResult(
                success=True,
                node_id=node_id,
                safety_branch=safety_branch,
                before_text=before_text,
                after_text=after_text,
                claude_output=claude_output,
                dry_run=False,
                file_path=str(req.file_path),
            )

        except Exception as e:
            return TransformResult(
                success=False,
                node_id=node_id,
                safety_branch=safety_branch,
                before_text=before_text,
                after_text=after_text,
                claude_output=claude_output,
                error=f"Failed to apply changes: {str(e)}",
            )

    def _apply_operations(
        self,
        node_id: str,
        req: Any,
        before_text: Optional[str],
        claude_output: str,
        safety_branch: Optional[str],
        dry_run: bool,
        context: "WorkspaceContext",
    ) -> TransformResult:
        """Parse and optionally apply an operations list."""
        try:
            # Parse the JSON output
            # Handle potential markdown code blocks in response
            output = claude_output.strip()
            if output.startswith("```"):
                # Extract content from code block
                lines = output.split("\n")
                start = 1  # Skip first ``` line
                end = len(lines) - 1  # Skip last ``` line
                if lines[-1].strip() == "```":
                    output = "\n".join(lines[start:end])
                else:
                    output = "\n".join(lines[start:])

            operations = json.loads(output)

            if not isinstance(operations, list):
                operations = [operations]

            return TransformResult(
                success=True,
                node_id=node_id,
                safety_branch=safety_branch,
                before_text=before_text,
                operations=operations,
                claude_output=claude_output,
                dry_run=dry_run,  # Operations mode is always informational
            )

        except json.JSONDecodeError as e:
            return TransformResult(
                success=False,
                node_id=node_id,
                safety_branch=safety_branch,
                before_text=before_text,
                claude_output=claude_output,
                error=f"Failed to parse operations JSON: {str(e)}",
                dry_run=dry_run,
            )

    def _extract_markdown(self, claude_output: str) -> Optional[str]:
        """
        Extract markdown content from Claude's response.

        Handles various response formats including:
        - Raw markdown
        - Markdown wrapped in code blocks
        - JSON with content field
        """
        output = claude_output.strip()

        # If it starts with a requirement header, it's raw markdown
        if output.startswith("#"):
            return output

        # If wrapped in markdown code block
        if output.startswith("```markdown") or output.startswith("```md"):
            lines = output.split("\n")
            start = 1
            end = len(lines)
            for i in range(len(lines) - 1, 0, -1):
                if lines[i].strip() == "```":
                    end = i
                    break
            return "\n".join(lines[start:end])

        # If wrapped in generic code block
        if output.startswith("```"):
            lines = output.split("\n")
            start = 1
            end = len(lines)
            for i in range(len(lines) - 1, 0, -1):
                if lines[i].strip() == "```":
                    end = i
                    break
            content = "\n".join(lines[start:end])
            # Check if this looks like markdown
            if content.strip().startswith("#"):
                return content

        # Try parsing as JSON with content field
        try:
            data = json.loads(output)
            if isinstance(data, dict):
                if "content" in data:
                    return data["content"]
                if "markdown" in data:
                    return data["markdown"]
                if "text" in data:
                    return data["text"]
        except json.JSONDecodeError:
            pass

        # Return as-is if nothing else matches
        return output if output else None


def restore_from_safety_branch(
    working_dir: Path,
    branch_name: str,
) -> tuple[bool, str]:
    """
    Restore the repository from a safety branch.

    Convenience function for restoring after a failed transformation.

    Args:
        working_dir: Root directory of the workspace
        branch_name: Name of the safety branch to restore from

    Returns:
        Tuple of (success, message)
    """
    manager = GitSafetyManager(working_dir)
    return manager.restore_from_branch(branch_name)
