# Verifies: REQ-p00013-A
from elspais.utilities.docs_loader import TOPIC_ORDER, get_available_topics, load_topic


def test_authoring_topic():
    assert "authoring" in TOPIC_ORDER
    assert "authoring" in get_available_topics()
    c = load_topic("authoring")
    assert (
        "INVARIANT TEST" in c
        and "GOLDILOCKS" in c
        and "Verifiability Distance" in c
        and "leaf" in c
    )
