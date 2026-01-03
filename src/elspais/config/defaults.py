"""
elspais.config.defaults - Default configuration values.

Provides built-in defaults matching the HHT-diary repository structure.
"""

DEFAULT_CONFIG = {
    "project": {
        "name": "",
        "type": "core",
    },
    "directories": {
        "spec": "spec",
        "docs": "docs",
        "database": "database",
        "code": ["apps", "packages", "server", "tools"],
        "ignore": [
            "node_modules",
            ".git",
            "build",
            "dist",
            ".dart_tool",
            "__pycache__",
            ".venv",
            "venv",
        ],
    },
    "patterns": {
        "id_template": "{prefix}-{associated}{type}{id}",
        "prefix": "REQ",
        "types": {
            "prd": {"id": "p", "name": "Product Requirement", "level": 1},
            "ops": {"id": "o", "name": "Operations Requirement", "level": 2},
            "dev": {"id": "d", "name": "Development Requirement", "level": 3},
        },
        "id_format": {
            "style": "numeric",
            "digits": 5,
            "leading_zeros": True,
        },
        "associated": {
            "enabled": True,
            "position": "after_prefix",
            "format": "uppercase",
            "length": 3,
            "separator": "-",
        },
        "assertions": {
            "label_style": "uppercase",  # uppercase | numeric | alphanumeric | numeric_1based
            "max_count": 26,
            "zero_pad": False,
        },
    },
    "spec": {
        "index_file": "INDEX.md",
        "readme_file": "README.md",
        "format_guide": "requirements-format.md",
        "skip_files": ["README.md", "requirements-format.md", "INDEX.md"],
        "file_patterns": {
            "prd-*.md": "prd",
            "ops-*.md": "ops",
            "dev-*.md": "dev",
        },
        # Values in Implements field that mean "no references"
        "no_reference_values": ["-", "null", "none", "x", "X", "N/A", "n/a"],
    },
    "core": {
        "path": None,
        "remote": None,
    },
    "associated": {
        "prefix": None,
        "id_range": [1, 99999],
    },
    "rules": {
        "hierarchy": {
            "allowed_implements": [
                "dev -> ops, prd",
                "ops -> prd",
                "prd -> prd",
            ],
            "allow_circular": False,
            "allow_orphans": False,
            "max_depth": 5,
            "cross_repo_implements": True,
        },
        "format": {
            "require_hash": True,
            "require_rationale": False,
            "require_status": True,
            "allowed_statuses": ["Active", "Draft", "Deprecated", "Superseded"],
            # Assertion format rules
            "require_assertions": True,
            "acceptance_criteria": "warn",  # allow | warn | error
            "require_shall": True,
            "labels_sequential": True,
            "labels_unique": True,
            "placeholder_values": [
                "obsolete", "removed", "deprecated", "N/A", "n/a", "-", "reserved"
            ],
        },
        "traceability": {
            "require_code_link": False,
            "scan_for_orphans": True,
        },
        "naming": {
            "title_min_length": 10,
            "title_max_length": 100,
            "title_pattern": "^[A-Z].*",
        },
        "content_rules": [],  # List of content rule markdown file paths
    },
    "validation": {
        "strict_hierarchy": True,
        "hash_algorithm": "sha256",
        "hash_length": 8,
        "normalize_whitespace": False,  # If True, normalize whitespace before hashing
    },
    "traceability": {
        "output_formats": ["markdown", "html"],
        "output_dir": ".",
        "scan_patterns": [
            "database/**/*.sql",
            "apps/**/*.dart",
            "packages/**/*.dart",
            "server/**/*.dart",
            "tools/**/*.py",
            ".github/workflows/**/*.yml",
        ],
        "impl_patterns": [
            r"IMPLEMENTS.*REQ-",
            r"Implements:\s*REQ-",
            r"Fixes:\s*REQ-",
        ],
    },
    "index": {
        "auto_regenerate": False,
    },
    "testing": {
        "enabled": False,
        "test_dirs": [
            "apps/**/test",
            "apps/**/tests",
            "packages/**/test",
            "packages/**/tests",
            "tools/**/tests",
            "tests",
        ],
        "patterns": [
            "*_test.dart",
            "test_*.dart",
            "test_*.py",
            "*_test.py",
            "*_test.sql",
        ],
        "result_files": [
            "build-reports/**/TEST-*.xml",
            "build-reports/pytest-results.json",
        ],
        "reference_patterns": [
            # Test function names containing requirement IDs
            r"test_.*(?:REQ[-_])?([pod]\d{5})(?:_[A-Z])?",
            # Comment/docstring patterns
            r"(?:IMPLEMENTS|Implements|implements)[:\s]+(?:REQ[-_])?([pod]\d{5})(?:-[A-Z])?",
            # Direct requirement ID mentions
            r"\bREQ[-_]([pod]\d{5})(?:-[A-Z])?\b",
        ],
    },
    "hooks": {
        "pre_commit": True,
        "commit_msg": True,
    },
}
