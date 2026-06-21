# Verifies: REQ-d00254-C
from elspais.utilities.docs_loader import TOPIC_ORDER, get_available_topics, load_topic


def test_test_targets_topic():
    assert "test-targets" in TOPIC_ORDER
    assert "test-targets" in get_available_topics()
    c = load_topic("test-targets")
    assert "flutter-machine" in c and "match" in c and "--concurrency=1" in c
