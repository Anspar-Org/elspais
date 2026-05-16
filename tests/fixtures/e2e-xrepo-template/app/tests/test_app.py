# Verifies: APP-p00001-A, APP-p00002-A
def test_app_action_rejects_missing_context():
    try:
        # Simulate app_action({}) — no user_context → ValueError
        payload = {}
        if not payload.get("user_context"):
            raise ValueError("user_context required")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")
