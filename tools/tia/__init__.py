"""Deterministic Test Impact Analysis (TIA) for the elspais unit tier.

Development tooling, not part of the shipped `elspais` package. See
docs/test-impact-analysis.md for how selection works.

Layout -- the language-neutral core is kept apart from the Python/pytest
adapters so the approach can be ported to another repository:

    model.py      the data model: changes, impact regions, selections (neutral)
    selector.py   the rules engine turning changes into a selection (neutral)
    gitio.py      baseline-vs-current file contents through git (neutral)
    config.py     the rule file (tools/tia/config.toml) (neutral)
    baseline.py   the baseline artifact: build, load, validate (neutral + coverage.py)
    pyimpact.py   Python adapter: AST unit diff, import graph
    recorder.py   pytest adapter: records per-test facts coverage cannot see
    runner.py     pytest adapter: runs a selection, writes the manifest
    calibrate.py  empirical evaluation: TIA vs full suite, mutation probes
"""

SCHEMA_VERSION = 1
