# Verifies: REQ-d00215-C
"""The test-results docs topic is registered and loadable (CUR-1533)."""

from elspais.utilities.docs_loader import TOPIC_ORDER, get_available_topics, load_topic


def test_test_results_topic_registered():
    assert "test-results" in TOPIC_ORDER


def test_test_results_topic_loads():
    assert "test-results" in get_available_topics()
    content = load_topic("test-results")
    assert content is not None
    assert "lcov_tested" in content
    assert "unmatched_credit" in content
