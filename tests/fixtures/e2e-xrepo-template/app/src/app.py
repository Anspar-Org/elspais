# Implements: APP-p00001-A, APP-p00002-A
def app_action(payload):
    if not payload.get("user_context"):
        raise ValueError("user_context required")
    if not payload["user_context"].get("tenant_id"):
        raise ValueError("tenant_id required")
    return payload
