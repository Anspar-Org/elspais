"""
Tests for hash calculation bugs reported in BUG.md

Bug 1: False positive hash mismatches - elspais reads incorrect hash values
Bug 2: Duplicate hash calculation - identical hashes for different requirements
"""

import pytest
from pathlib import Path
from textwrap import dedent

from elspais.core.parser import RequirementParser
from elspais.core.patterns import PatternConfig
from elspais.core.hasher import calculate_hash
from elspais.config.defaults import DEFAULT_CONFIG


@pytest.fixture
def parser():
    """Create a parser with HHT-style config (REQ-d00001, REQ-p00001, etc.)."""
    config = PatternConfig.from_dict(DEFAULT_CONFIG["patterns"])
    return RequirementParser(config)


class TestMultipleRequirementsInFile:
    """Tests for parsing multiple requirements from a single file."""

    MULTI_REQ_FILE = dedent("""\
        # REQ-d00001: First Requirement

        **Level**: Dev | **Status**: Active | **Implements**: REQ-p00001

        The first requirement has unique content about authentication.
        It describes how users should log in securely.

        ## Assertions

        A. The system SHALL authenticate users with passwords.
        B. The system SHALL hash passwords using bcrypt.

        *End* *First Requirement* | **Hash**: 11111111
        ---

        # REQ-d00002: Second Requirement

        **Level**: Dev | **Status**: Active | **Implements**: REQ-p00002

        The second requirement describes data validation rules.
        All input must be sanitized before processing.

        ## Assertions

        A. The system SHALL validate all user input.
        B. The system SHALL reject malformed data.

        *End* *Second Requirement* | **Hash**: 22222222
        ---

        # REQ-d00003: Third Requirement

        **Level**: Dev | **Status**: Active | **Implements**: REQ-p00003

        The third requirement covers logging and audit trails.
        Every action must be recorded for compliance.

        ## Assertions

        A. The system SHALL log all user actions.
        B. The system SHALL retain logs for 7 years.

        *End* *Third Requirement* | **Hash**: 33333333
        ---
    """)

    def test_each_requirement_has_unique_body(self, parser):
        """Bug 2: Different requirements must have different body content."""
        requirements = parser.parse_text(self.MULTI_REQ_FILE)

        assert len(requirements) == 3, "Should parse all three requirements"

        bodies = {req_id: req.body for req_id, req in requirements.items()}

        # Each body should be unique
        unique_bodies = set(bodies.values())
        assert len(unique_bodies) == 3, (
            f"Each requirement should have unique body content, "
            f"but found only {len(unique_bodies)} unique bodies.\n"
            f"Bodies:\n"
            + "\n---\n".join(f"{k}:\n{v[:100]}..." for k, v in bodies.items())
        )

    def test_each_requirement_has_unique_hash_calculated(self, parser):
        """Bug 2: Different body content must produce different hashes."""
        requirements = parser.parse_text(self.MULTI_REQ_FILE)

        calculated_hashes = {}
        for req_id, req in requirements.items():
            calculated_hashes[req_id] = calculate_hash(req.body)

        unique_hashes = set(calculated_hashes.values())
        assert len(unique_hashes) == 3, (
            f"Each requirement should have unique calculated hash, "
            f"but found only {len(unique_hashes)} unique hashes.\n"
            f"Hashes: {calculated_hashes}"
        )

    def test_correct_hash_read_from_file(self, parser):
        """Bug 1: Hash read from file should match what's actually in the file."""
        requirements = parser.parse_text(self.MULTI_REQ_FILE)

        expected_hashes = {
            "REQ-d00001": "11111111",
            "REQ-d00002": "22222222",
            "REQ-d00003": "33333333",
        }

        for req_id, expected_hash in expected_hashes.items():
            actual_hash = requirements[req_id].hash
            assert actual_hash == expected_hash, (
                f"Hash for {req_id} should be '{expected_hash}' but got '{actual_hash}'"
            )

    def test_body_boundaries_correct(self, parser):
        """Verify body content doesn't leak between requirements."""
        requirements = parser.parse_text(self.MULTI_REQ_FILE)

        # First requirement body should contain "authentication" but not "validation"
        d00001_body = requirements["REQ-d00001"].body
        assert "authentication" in d00001_body.lower(), (
            f"REQ-d00001 body should contain 'authentication': {d00001_body}"
        )
        assert "validation" not in d00001_body.lower(), (
            f"REQ-d00001 body should NOT contain 'validation' (from REQ-d00002): {d00001_body}"
        )
        assert "logging" not in d00001_body.lower(), (
            f"REQ-d00001 body should NOT contain 'logging' (from REQ-d00003): {d00001_body}"
        )

        # Second requirement body should contain "validation" but not others
        d00002_body = requirements["REQ-d00002"].body
        assert "validation" in d00002_body.lower(), (
            f"REQ-d00002 body should contain 'validation': {d00002_body}"
        )
        assert "authentication" not in d00002_body.lower(), (
            f"REQ-d00002 body should NOT contain 'authentication' (from REQ-d00001): {d00002_body}"
        )

        # Third requirement body should contain "logging" but not others
        d00003_body = requirements["REQ-d00003"].body
        assert "logging" in d00003_body.lower(), (
            f"REQ-d00003 body should contain 'logging': {d00003_body}"
        )
        assert "validation" not in d00003_body.lower(), (
            f"REQ-d00003 body should NOT contain 'validation' (from REQ-d00002): {d00003_body}"
        )


class TestHashReadingFromFooter:
    """Tests for correctly reading hashes from requirement footers."""

    def test_hash_read_from_correct_footer_line(self, parser):
        """Ensure the hash is read from THIS requirement's footer, not another's."""
        text = dedent("""\
            # REQ-d00010: Alpha Feature

            **Level**: Dev | **Status**: Active

            Alpha content here.

            *End* *Alpha Feature* | **Hash**: aaaaaaaa
            ---

            # REQ-d00011: Beta Feature

            **Level**: Dev | **Status**: Active

            Beta content here.

            *End* *Beta Feature* | **Hash**: bbbbbbbb
            ---
        """)

        requirements = parser.parse_text(text)

        assert requirements["REQ-d00010"].hash == "aaaaaaaa", (
            f"REQ-d00010 should have hash 'aaaaaaaa', got '{requirements['REQ-d00010'].hash}'"
        )
        assert requirements["REQ-d00011"].hash == "bbbbbbbb", (
            f"REQ-d00011 should have hash 'bbbbbbbb', got '{requirements['REQ-d00011'].hash}'"
        )


class TestBodyExtractionBoundaries:
    """Tests for body content extraction boundaries."""

    def test_body_starts_after_status_line(self, parser):
        """Body should start after the Level/Status line."""
        text = dedent("""\
            # REQ-d00020: Test Requirement

            **Level**: Dev | **Status**: Active | **Implements**: REQ-p00001

            This is the body content.
            More body content here.

            *End* *Test Requirement* | **Hash**: 12345678
        """)

        requirements = parser.parse_text(text)
        body = requirements["REQ-d00020"].body

        assert "This is the body content" in body
        assert "Level" not in body, f"Body should not contain status line: {body}"
        assert "REQ-d00020" not in body, f"Body should not contain header: {body}"

    def test_body_ends_before_end_marker(self, parser):
        """Body should end before the *End* marker."""
        text = dedent("""\
            # REQ-d00021: Another Test

            **Level**: Dev | **Status**: Active

            Body content only.

            *End* *Another Test* | **Hash**: 87654321
        """)

        requirements = parser.parse_text(text)
        body = requirements["REQ-d00021"].body

        assert "Body content only" in body
        assert "*End*" not in body, f"Body should not contain end marker: {body}"
        assert "Hash" not in body, f"Body should not contain hash line: {body}"


class TestHashUpdateBug:
    """Tests for the hash update bug where all hashes get overwritten."""

    def test_update_hash_only_affects_target_requirement(self, parser, tmp_path):
        """
        Bug: update_hash_in_file replaces ALL matching hashes in the file,
        not just the target requirement's hash.

        Scenario:
        1. Two requirements both have hash "aaa11111"
        2. We update only REQ-d00001's hash to "bbb22222"
        3. REQ-d00002 should still have "aaa11111"
        """
        from elspais.commands.hash_cmd import update_hash_in_file
        from elspais.core.models import Requirement

        # Create a file with two requirements having the same hash
        content = dedent("""\
            # REQ-d00001: First Feature

            **Level**: Dev | **Status**: Active

            Content for first feature.

            *End* *First Feature* | **Hash**: aaa11111
            ---

            # REQ-d00002: Second Feature

            **Level**: Dev | **Status**: Active

            Content for second feature.

            *End* *Second Feature* | **Hash**: aaa11111
        """)

        test_file = tmp_path / "test.md"
        test_file.write_text(content)

        # Create a requirement object for REQ-d00001
        req = Requirement(
            id="REQ-d00001",
            title="First Feature",
            level="Dev",
            status="Active",
            body="Content for first feature.",
            implements=[],
            hash="aaa11111",
            file_path=test_file,
            line_number=1,
        )

        # Update only REQ-d00001's hash
        update_hash_in_file(req, "bbb22222")

        # Read the file back
        updated_content = test_file.read_text()

        # REQ-d00001 should have new hash
        assert "**Hash**: bbb22222" in updated_content, (
            "REQ-d00001 should have updated hash"
        )

        # REQ-d00002 should STILL have original hash (this is the bug!)
        # Count occurrences of each hash
        count_old = updated_content.count("**Hash**: aaa11111")
        count_new = updated_content.count("**Hash**: bbb22222")

        assert count_old == 1, (
            f"REQ-d00002 should still have old hash 'aaa11111', "
            f"but found {count_old} occurrences (expected 1). "
            f"This indicates the bug: update replaced ALL matching hashes."
        )
        assert count_new == 1, (
            f"Only REQ-d00001 should have new hash 'bbb22222', "
            f"but found {count_new} occurrences (expected 1)."
        )

    def test_update_hash_scoped_to_requirement_end_marker(self, parser, tmp_path):
        """
        The hash update should be scoped to the specific requirement's end marker,
        not just any occurrence of the hash value in the file.
        """
        from elspais.commands.hash_cmd import update_hash_in_file
        from elspais.core.models import Requirement

        # Create a file where the hash value appears in content too
        content = dedent("""\
            # REQ-d00001: Hash Feature

            **Level**: Dev | **Status**: Active

            The old hash value was aaa11111 for reference.

            *End* *Hash Feature* | **Hash**: aaa11111
        """)

        test_file = tmp_path / "test2.md"
        test_file.write_text(content)

        req = Requirement(
            id="REQ-d00001",
            title="Hash Feature",
            level="Dev",
            status="Active",
            body="The old hash value was aaa11111 for reference.",
            implements=[],
            hash="aaa11111",
            file_path=test_file,
            line_number=1,
        )

        update_hash_in_file(req, "bbb22222")

        updated_content = test_file.read_text()

        # Only the hash in the end marker should be updated
        assert "**Hash**: bbb22222" in updated_content
        # The hash value in the body should NOT be changed
        assert "was aaa11111 for reference" in updated_content, (
            "Hash value in body content should not be changed"
        )


class TestValidateCommandHashBehavior:
    """Tests for hash behavior in the validate command flow."""

    def test_json_output_shows_stored_hash_not_calculated(self, parser):
        """
        The --json output should show the stored hash (from file),
        not the calculated hash. If this shows wrong hash, Bug 1 is confirmed.
        """
        text = dedent("""\
            # REQ-d00001: Feature One

            **Level**: Dev | **Status**: Active

            Unique content for feature one.

            *End* *Feature One* | **Hash**: stored11
            ---

            # REQ-d00002: Feature Two

            **Level**: Dev | **Status**: Active

            Different unique content for feature two.

            *End* *Feature Two* | **Hash**: stored22
        """)

        requirements = parser.parse_text(text)

        # The hash attribute should be the STORED hash from the file
        assert requirements["REQ-d00001"].hash == "stored11", (
            f"REQ-d00001 should have stored hash 'stored11', got '{requirements['REQ-d00001'].hash}'"
        )
        assert requirements["REQ-d00002"].hash == "stored22", (
            f"REQ-d00002 should have stored hash 'stored22', got '{requirements['REQ-d00002'].hash}'"
        )

    def test_calculated_hash_differs_from_stored(self, parser):
        """
        Verify that calculate_hash() on body produces different result
        than stored hash (since stored hash is just a placeholder in tests).
        """
        text = dedent("""\
            # REQ-d00005: Test Feature

            **Level**: Dev | **Status**: Active

            This is the actual body content that should be hashed.
            It has multiple lines of unique content.

            ## Assertions

            A. The system SHALL do something.

            *End* *Test Feature* | **Hash**: fakehash
        """)

        requirements = parser.parse_text(text)
        req = requirements["REQ-d00005"]

        # Stored hash from file
        stored_hash = req.hash
        assert stored_hash == "fakehash"

        # Calculated hash from body
        calculated_hash = calculate_hash(req.body)

        # These should be different (since fakehash isn't the real hash)
        assert calculated_hash != stored_hash, (
            f"Calculated hash should differ from fake stored hash"
        )


class TestRealWorldScenario:
    """Tests simulating the actual bug scenario from BUG.md."""

    def test_requirements_at_different_positions(self, parser):
        """
        Simulate the bug: REQ-d00014, d00015, d00018 at different line positions
        in the same file should have different hashes.
        """
        # Simulate a file with multiple requirements spread out
        text = dedent("""\
            # Development Requirements

            This document contains development requirements.

            ---

            # REQ-d00014: Requirement Validation Tooling

            **Level**: Dev | **Status**: Draft | **Implements**: REQ-o00013

            The system SHALL implement automated requirement validation
            including format checking and hierarchy verification.

            ## Assertions

            A. The tool SHALL parse markdown requirement files.
            B. The tool SHALL validate requirement IDs match patterns.

            *End* *Requirement Validation Tooling* | **Hash**: hash0014
            ---

            # REQ-d00015: Hash-Based Change Detection

            **Level**: Dev | **Status**: Active | **Implements**: REQ-o00013

            The system SHALL implement hash-based change detection
            to identify when requirement content has been modified.

            ## Assertions

            A. SHA-256 SHALL be used for content hashing.
            B. Hash length SHALL be configurable (default 8 chars).

            *End* *Hash-Based Change Detection* | **Hash**: hash0015
            ---

            # REQ-d00016: Unique Requirement

            **Level**: Dev | **Status**: Active

            This requirement has completely different content.

            *End* *Unique Requirement* | **Hash**: hash0016
            ---

            # REQ-d00017: Another Unique One

            **Level**: Dev | **Status**: Active

            Yet another different requirement with unique text.

            *End* *Another Unique One* | **Hash**: hash0017
            ---

            # REQ-d00018: Traceability Matrix Generation

            **Level**: Dev | **Status**: Draft | **Implements**: REQ-o00014

            The system SHALL generate traceability matrices showing
            requirement relationships and implementation coverage.

            ## Assertions

            A. Output formats SHALL include Markdown, HTML, and CSV.
            B. Matrix SHALL show parent-child relationships.

            *End* *Traceability Matrix Generation* | **Hash**: hash0018
            ---
        """)

        requirements = parser.parse_text(text)

        # Verify we got all requirements
        assert "REQ-d00014" in requirements
        assert "REQ-d00015" in requirements
        assert "REQ-d00016" in requirements
        assert "REQ-d00017" in requirements
        assert "REQ-d00018" in requirements

        # Verify each has correct hash from file
        assert requirements["REQ-d00014"].hash == "hash0014"
        assert requirements["REQ-d00015"].hash == "hash0015"
        assert requirements["REQ-d00018"].hash == "hash0018"

        # Verify bodies are unique (the core bug check)
        bodies = {
            "d00014": requirements["REQ-d00014"].body,
            "d00015": requirements["REQ-d00015"].body,
            "d00018": requirements["REQ-d00018"].body,
        }

        # Calculate hashes
        calc_hashes = {k: calculate_hash(v) for k, v in bodies.items()}

        # Each calculated hash should be unique
        unique_calc = set(calc_hashes.values())
        assert len(unique_calc) == 3, (
            f"All three requirements should have unique calculated hashes.\n"
            f"Calculated hashes: {calc_hashes}\n"
            f"Bodies:\n" +
            "\n---\n".join(f"{k}:\n{v}" for k, v in bodies.items())
        )

        # Verify content separation
        assert "validation" in bodies["d00014"].lower()
        assert "hash-based" in bodies["d00015"].lower() or "change detection" in bodies["d00015"].lower()
        assert "traceability" in bodies["d00018"].lower()
