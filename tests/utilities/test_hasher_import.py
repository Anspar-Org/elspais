"""The hash utility loads on its own, as the first elspais module a process imports."""

from __future__ import annotations

import subprocess
import sys


# Verifies: REQ-p00004-A
def test_the_hasher_is_importable_before_any_other_elspais_module():
    done = subprocess.run(
        [sys.executable, "-c", "import elspais.utilities.hasher"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stderr
