# Implements: REQ-int-d00002-C (Review server requires flask)
"""
elspais.trace_view.review - Collaborative review system.

Requires: pip install elspais[trace-review]
"""

# Models are always available (no flask dependency)
from elspais.trace_view.review.models import (
    Approval,
    ApprovalDecision,
    Comment,
    CommentPosition,
    PositionType,
    RequestState,
    ReviewConfig,
    ReviewFlag,
    ReviewPackage,
    ReviewSession,
    StatusRequest,
    Thread,
)


def _check_flask():
    try:
        import flask  # noqa: F401

        return True
    except ImportError:
        return False


FLASK_AVAILABLE = _check_flask()

__all__ = [
    "FLASK_AVAILABLE",
    # Models (always available)
    "Comment",
    "CommentPosition",
    "Thread",
    "ReviewFlag",
    "StatusRequest",
    "Approval",
    "ReviewSession",
    "ReviewConfig",
    "ReviewPackage",
    "PositionType",
    "RequestState",
    "ApprovalDecision",
]

if FLASK_AVAILABLE:
    from elspais.trace_view.review.server import create_app

    __all__.append("create_app")
else:

    def create_app(*args, **kwargs):
        """Placeholder when flask is not installed."""
        raise ImportError(
            "Review server requires Flask. " "Install with: pip install elspais[trace-review]"
        )
