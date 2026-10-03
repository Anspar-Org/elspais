.PHONY: setup test test-e2e test-browser test-stress test-all help

# The hooks resolve this tree's elspais through this directory, and the test
# targets run its pytest. Naming it once here is what makes that one place.
VENV := .venv
PY := $(CURDIR)/$(VENV)/bin/python

# The git hooks resolve `elspais` and `pytest` by name and warn (or decline the
# destructive `elspais fix` stage) when PATH resolves them outside this tree.
# The e2e tier needs it for a second reason: the `stub` test target in
# tests/fixtures/e2e-standard/.elspais.toml shells out to a bare `python`, and
# without the venv on PATH it fails with exit 127.
VENV_PATH := PATH="$(CURDIR)/$(VENV)/bin:$$PATH"
PYTEST := $(VENV_PATH) $(PY) -m pytest

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

# The run the pre-commit hook makes, in parallel on half the processors and
# fingerprinted into the `elspais-unit` target's output area.
test: ## Run unit/integration tests in parallel, with per-test coverage
	$(VENV_PATH) .githooks/with-fingerprint elspais-unit .githooks/run-unit-tier

# The same two-pass run the pre-push hook makes, fingerprinted into the
# `elspais-e2e` target's output area so `elspais checks` reads its results.
test-e2e: ## Run e2e subprocess tests (parallel pass, then serial pass)
	$(VENV_PATH) .githooks/with-fingerprint elspais-e2e .githooks/run-e2e-tier

# Without coverage, as their targets in .elspais.toml run: the unit tier
# alone measures line coverage.
test-browser: ## Run browser tests
	$(PYTEST) -m browser --no-cov

test-stress: ## Run the concurrency stress battery
	$(PYTEST) -m stress --no-cov

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
