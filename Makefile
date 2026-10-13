.PHONY: setup lock test test-e2e test-browser test-stress test-all test-impacted test-impacted-list tia-baseline tia-calibrate help

# The hooks and .githooks/run-target put this directory first on PATH, so the
# test targets run its pytest and its elspais. Naming it once here is what
# makes that one place.
VENV := .venv
PY := $(CURDIR)/$(VENV)/bin/python
VENV_PATH := PATH="$(CURDIR)/$(VENV)/bin:$$PATH"

# The test environment: these extras, at the versions requirements/dev.lock
# pins. CI installs the same, so a TIA baseline CI records is accepted by a
# venv on the same Python minor version (docs/test-impact-analysis.md).
LOCK := requirements/dev.lock
TEST_EXTRAS := dev all browser
comma := ,
empty :=
space := $(empty) $(empty)

setup: ## Set up development environment
	git config core.hooksPath .githooks
	python3 -m venv $(VENV)
# Install through the venv's own interpreter, never the ambient `pip`.
# An install into whatever Python happens to be active lands in a user
# site-packages, binds this worktree there for every other repository, and
# leaves the hooks with no venv to find. A system python3 here may have no
# `pip` module at all, so `pip install` cannot be assumed to run.
	$(PY) -m pip install -c $(LOCK) -e ".[$(subst $(space),$(comma),$(TEST_EXTRAS))]"
# Without the browser binaries the browser tier does not fail -- it is
# deselected, and a run that covers none of it still reports green.
	$(VENV_PATH) $(VENV)/bin/playwright install chromium
# Claude Code reaches elspais over http, at the address ELSPAIS_MCP_URL names.
# A local registration overrides .mcp.json, and one that runs another elspais
# answers from that program, so setup replaces it with the http registration.
	@if command -v claude >/dev/null 2>&1; then \
		$(VENV_PATH) $(VENV)/bin/elspais mcp install; \
	else \
		echo "claude is not on PATH: the MCP registration was skipped."; \
	fi
	@echo ""
	@echo "Development environment ready."
	@echo "  Virtualenv: $(VENV)"
	@echo "  Git hooks installed from .githooks/"
	@echo "  Run 'make test' to verify."

# Regenerates the lock from pyproject.toml, keeping every pin that still
# satisfies it; `make lock ARGS=--upgrade` moves them. One universal
# resolution covers every supported Python and platform, through environment
# markers. uv is a dev dependency, so the lock pins the release that compiles
# it. CI runs this target with PY=python and fails when the lock changes.
lock: ## Regenerate requirements/dev.lock from pyproject.toml
	$(PY) -m pip install -c $(LOCK) uv
	$(PY) -m uv pip compile pyproject.toml --universal --python-version 3.10 \
		$(foreach extra,$(TEST_EXTRAS),--extra $(extra)) \
		--custom-compile-command "make lock" --quiet -o $(LOCK) $(ARGS)

# Every test target below runs through .githooks/run-target: fingerprinted
# into its target's output area, as `elspais checks` reads it, and refused
# while a run of the same target -- a hook's or another make's -- is in
# progress in this worktree, because a second run empties the first one's
# output area as it starts.

# The run the pre-commit hook makes, in parallel on half the processors.
test: ## Run unit/integration tests in parallel, with per-test coverage
	.githooks/run-target elspais-unit .githooks/run-unit-tier

# The same two-pass run the pre-push hook makes.
test-e2e: ## Run e2e subprocess tests (parallel pass, then serial pass)
	.githooks/run-target elspais-e2e .githooks/run-e2e-tier

# Without coverage, as their targets in .elspais.toml run: the unit tier
# alone measures line coverage.
test-browser: ## Run browser tests
	.githooks/run-target elspais-browser bash -c 'pytest -m browser -q --no-cov --junitxml="$$ELSPAIS_TARGET_OUTPUT/junit.xml" -o junit_family=xunit1'

test-stress: ## Run the concurrency stress battery
	.githooks/run-target elspais-stress bash -c 'pytest tests/stress -m stress -q --no-cov --junitxml="$$ELSPAIS_TARGET_OUTPUT/junit.xml" -o junit_family=xunit1'

# Each tier the way its own target runs it, one after another: two pytest
# sessions in one worktree collide on coverage data, so this target never
# runs them side by side, even under `make -j`.
test-all: ## Run all tests (unit, e2e, browser, stress), one tier at a time
	$(MAKE) -j1 test
	$(MAKE) -j1 test-e2e
	$(MAKE) -j1 test-browser
	$(MAKE) -j1 test-stress

# Test Impact Analysis (docs/test-impact-analysis.md). Fast development
# feedback, the same selection the pre-commit hook runs; CI's full unit tier
# is the run a merge rests on.
#
# tia-baseline runs the full unit tier exactly as `make test` does, and also
# publishes the baseline that test-impacted selects from, when the run passes,
# in this worktree's .results/tia/baseline.
tia-baseline: ## Run the unit tier and record a TIA baseline (.results/tia/baseline)
	ELSPAIS_TIA_RECORD=1 .githooks/run-target elspais-unit .githooks/run-unit-tier

# Only the unit tests the change since the baseline can affect. TIA_FULL=1
# (or ARGS=--full) bypasses selection and runs the whole tier.
test-impacted: ## Run only the unit tests affected by changes since the TIA baseline
	$(VENV_PATH) $(PY) -m tools.tia run $(ARGS)

test-impacted-list: ## Show what test-impacted would run, and why, without running it
	$(VENV_PATH) $(PY) -m tools.tia select --list $(ARGS)

# TIA-selected run and full run of the same revision, compared; with
# MUTANTS=N also N seeded single-function fault probes. Slow: nightly.
tia-calibrate: ## Compare the TIA selection with a full run of this revision
	$(VENV_PATH) $(PY) -m tools.tia calibrate --mutants $(or $(MUTANTS),0) $(ARGS)

help: ## Show this help
	@grep -E '^[a-zA-Z0-9_-]+:.*## ' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
