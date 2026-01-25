# elspais: expected-broken-links 2
"""Test fixture demonstrating sequential suppression.

The marker says 2, so only the first 2 references are marked as expected_broken.
The 3rd and 4th references should NOT be suppressed and will produce warnings.
"""


def test_first_suppressed():
    """Validates: REQ-d92001."""
    # This is ref #1 - suppressed
    pass


def test_second_suppressed():
    """Validates: REQ-d92002."""
    # This is ref #2 - suppressed
    pass


def test_third_not_suppressed():
    """Validates: REQ-d92003."""
    # This is ref #3 - NOT suppressed, should warn
    pass


def test_fourth_not_suppressed():
    """Validates: REQ-d92004."""
    # This is ref #4 - NOT suppressed, should warn
    pass
