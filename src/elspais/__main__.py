"""
Allow running elspais as a module: python -m elspais
"""

import sys

from elspais.cli import main

if __name__ == "__main__":
    sys.exit(main())
