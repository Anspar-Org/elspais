"""Test fixture with marker outside header area.

This file has the marker after line 20, so it should be ignored.
"""

# Line 6
# Line 7
# Line 8
# Line 9
# Line 10
# Line 11
# Line 12
# Line 13
# Line 14
# Line 15
# Line 16
# Line 17
# Line 18
# Line 19
# Line 20 - last line in header area
# elspais: expected-broken-links 5
# This marker is on line 22, should be ignored


def test_outside_header():
    """Validates: REQ-outside00001."""
    pass
