"""Fake requirement IDs and test data for unit tests.

This module lives in tests/fixtures/ which is excluded from the elspais
test scanner, preventing these fake REQ IDs from creating broken references.
"""

# Fake requirement IDs
FAKE_REQ_ID = "REQ-t00001"
FAKE_REQ_ID_2 = "REQ-t00002"
FAKE_REQ_ASSERTION_A = "REQ-t00001-A"
FAKE_REQ_ASSERTION_B = "REQ-t00001-B"
FAKE_NONEXISTENT_REQ = "REQ-NONEXISTENT"

# Raw text for code reference nodes
CODE_RAW_TEXT = "# Implements: REQ-t00001"
CODE_RAW_TEXT_NONEXISTENT = "# Implements: REQ-NONEXISTENT"
CODE_RAW_TEXT_MULTI = "# Implements: REQ-t00001\n# Implements: REQ-t00002"

# Raw text for test reference nodes
TEST_RAW_TEXT = "# Tests: REQ-t00001"
TEST_RAW_TEXT_VALIDATES_A = "# Validates: REQ-t00001-A"
TEST_RAW_TEXT_NONEXISTENT = "# Validates: REQ-NONEXISTENT"

# Test parser input: simulated function definition with multi-assertion ref
PARSER_INPUT_MULTI_ASSERTION = (1, "def test_REQ_d00060_A_B_combined_test():")
