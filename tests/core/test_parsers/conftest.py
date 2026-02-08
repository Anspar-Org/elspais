"""Pytest fixtures for MDparser tests."""

import pytest


@pytest.fixture
def sample_spec_lines():
    """Sample spec file lines as (line_number, content) tuples."""
    content = """\
# Product Requirements

<!-- This is a comment -->

## REQ-p00001: User Authentication

**Status**: Active

Users SHALL be able to authenticate.

A) Users can log in with email/password
B) Users can log in with OAuth

**Hash**: abc12345

---

Some prose between requirements.

## REQ-p00002: User Profile

**Status**: Active

Users SHALL have profiles.

**Hash**: def67890
"""
    return [(i + 1, line) for i, line in enumerate(content.split("\n"))]


@pytest.fixture
def comment_block_lines():
    """Lines containing HTML comment blocks."""
    content = """\
Some text before
<!-- Single line comment -->
More text
<!--
Multi-line
comment
block
-->
Text after
"""
    return [(i + 1, line) for i, line in enumerate(content.split("\n"))]
