# elspais: expected-broken-links 3
"""Test fixture with expected broken links marker.

This file intentionally references requirement IDs that don't exist
in the actual spec files, to test the expected-broken-links feature.
"""


def test_with_mock_requirements():
    """Test referencing mock requirements. Validates: REQ-d90001-A."""
    pass


def test_with_another_mock():
    """Another test. Validates: REQ-d90002."""
    pass


# Validates: REQ-d90003
def test_third_mock():
    """Third test with mock requirement."""
    pass
