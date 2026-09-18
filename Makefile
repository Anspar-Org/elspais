.PHONY: setup test test-e2e test-all

# The hooks resolve this tree's elspais through this directory, and the test
# targets run its pytest. Naming it once here is what makes that one place.
VENV := .venv

setup: ## Set up development environment
	git config core.hooksPath .githooks
	python3 -m venv $(VENV)
# Install through the venv's own interpreter, never the ambient `pip`.
# An install into whatever Python happens to be active lands in a user
# site-packages, binds this worktree there for every other repository, and
# leaves the hooks with no venv to find.
	$(VENV)/bin/python -m pip install -e ".[dev,all,browser]"
# Without the browser binaries the browser tier does not fail -- it is
# deselected, and a run that covers none of it still reports green.
	$(VENV)/bin/playwright install chromium
	@echo ""
	@echo "Development environment ready."
	@echo "  Virtualenv: $(VENV)"
	@echo "  Git hooks installed from .githooks/"
	@echo "  Run 'make test' to verify."

test: ## Run unit/integration tests (~26s)
	$(VENV)/bin/pytest

test-e2e: ## Run e2e subprocess tests (~143s)
	$(VENV)/bin/pytest -m e2e

test-all: ## Run all tests (~182s)
	$(VENV)/bin/pytest -m ""

help: ## Show this help
	@grep -E '^[a-zA-Z0-9_-]+:.*## ' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
