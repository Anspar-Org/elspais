.PHONY: setup test test-e2e test-browser test-stress test-all help

# The hooks and .githooks/run-target put this directory first on PATH, so the
# test targets run its pytest and its elspais. Naming it once here is what
# makes that one place.
VENV := .venv
PY := $(CURDIR)/$(VENV)/bin/python
VENV_PATH := PATH="$(CURDIR)/$(VENV)/bin:$$PATH"

setup: ## Set up development environment
	git config core.hooksPath .githooks
	python3 -m venv $(VENV)
# Install through the venv's own interpreter, never the ambient `pip`.
# An install into whatever Python happens to be active lands in a user
# site-packages, binds this worktree there for every other repository, and
# leaves the hooks with no venv to find. A system python3 here may have no
# `pip` module at all, so `pip install` cannot be assumed to run.
	$(PY) -m pip install -e ".[dev,all,browser]"
# Without the browser binaries the browser tier does not fail -- it is
# deselected, and a run that covers none of it still reports green.
	$(VENV_PATH) $(VENV)/bin/playwright install chromium
	@echo ""
	@echo "Development environment ready."
	@echo "  Virtualenv: $(VENV)"
	@echo "  Git hooks installed from .githooks/"
	@echo "  Run 'make test' to verify."

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

help: ## Show this help
	@grep -E '^[a-zA-Z0-9_-]+:.*## ' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
