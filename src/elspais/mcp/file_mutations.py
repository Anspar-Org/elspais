# Implements: REQ-o00063-A, REQ-o00063-B, REQ-o00063-D
"""Backward-compatibility shim — delegates to ``utilities.spec_writer``.

All spec-file I/O functions now live in ``elspais.utilities.spec_writer``.
This module re-exports them so existing imports keep working.
"""

from elspais.utilities.spec_writer import add_status_to_file, update_hash_in_file

__all__ = ["update_hash_in_file", "add_status_to_file"]
