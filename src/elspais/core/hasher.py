"""
elspais.core.hasher - Hash calculation for requirement change detection.

Provides functions for calculating and verifying SHA-256 based content hashes.
"""

import hashlib
import re
from typing import Optional


def clean_requirement_body(content: str, normalize_whitespace: bool = False) -> str:
    """
    Clean requirement body text for consistent hashing.

    Args:
        content: Raw requirement body text
        normalize_whitespace: If True, aggressively normalize whitespace.
                             If False (default), only remove trailing blank lines
                             (matches hht-diary tools behavior).

    Returns:
        Cleaned text suitable for hashing
    """
    if normalize_whitespace:
        # Aggressive normalization mode
        lines = content.split("\n")

        # Remove leading blank lines
        while lines and not lines[0].strip():
            lines.pop(0)

        # Remove trailing blank lines
        while lines and not lines[-1].strip():
            lines.pop()

        # Strip trailing whitespace from each line
        lines = [line.rstrip() for line in lines]

        # Collapse multiple consecutive blank lines to single blank line
        result_lines = []
        prev_blank = False
        for line in lines:
            is_blank = not line.strip()
            if is_blank and prev_blank:
                continue
            result_lines.append(line)
            prev_blank = is_blank

        return "\n".join(result_lines)
    else:
        # Default: hht-diary compatible mode (only remove trailing blank lines)
        lines = content.split("\n")

        # Remove trailing blank lines (matches hht-diary behavior)
        while lines and not lines[-1].strip():
            lines.pop()

        return "\n".join(lines)


def calculate_hash(
    content: str,
    length: int = 8,
    algorithm: str = "sha256",
    normalize_whitespace: bool = False,
) -> str:
    """
    Calculate a content hash for change detection.

    Args:
        content: Text content to hash
        length: Number of characters in the hash (default 8)
        algorithm: Hash algorithm to use (default "sha256")
        normalize_whitespace: If True, aggressively normalize whitespace.
                             If False (default), only remove trailing blank lines.

    Returns:
        Hexadecimal hash string of specified length
    """
    # Clean the content first
    cleaned = clean_requirement_body(content, normalize_whitespace=normalize_whitespace)

    # Calculate hash
    if algorithm == "sha256":
        hash_obj = hashlib.sha256(cleaned.encode("utf-8"))
    elif algorithm == "sha1":
        hash_obj = hashlib.sha1(cleaned.encode("utf-8"))
    elif algorithm == "md5":
        hash_obj = hashlib.md5(cleaned.encode("utf-8"))
    else:
        raise ValueError(f"Unsupported hash algorithm: {algorithm}")

    # Return first `length` characters of hex digest
    return hash_obj.hexdigest()[:length]


def verify_hash(
    content: str,
    expected_hash: str,
    length: int = 8,
    algorithm: str = "sha256",
    normalize_whitespace: bool = False,
) -> bool:
    """
    Verify that content matches an expected hash.

    Args:
        content: Text content to verify
        expected_hash: Expected hash value
        length: Hash length used (default 8)
        algorithm: Hash algorithm used (default "sha256")
        normalize_whitespace: If True, aggressively normalize whitespace.
                             If False (default), only remove trailing blank lines.

    Returns:
        True if hash matches, False otherwise
    """
    actual_hash = calculate_hash(
        content,
        length=length,
        algorithm=algorithm,
        normalize_whitespace=normalize_whitespace,
    )
    return actual_hash.lower() == expected_hash.lower()


def extract_hash_from_footer(footer_text: str) -> Optional[str]:
    """
    Extract hash value from requirement footer line.

    Looks for pattern: **Hash**: XXXXXXXX

    Args:
        footer_text: The footer line text

    Returns:
        Hash string if found, None otherwise
    """
    match = re.search(r"\*\*Hash\*\*:\s*([a-fA-F0-9]+)", footer_text)
    if match:
        return match.group(1)
    return None
