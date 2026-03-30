.PHONY: setup test test-e2e test-all

setup: ## Set up development environment
	git config core.hooksPath .githooks
	pip install -e ".[dev,all]"
	@echo ""
	@echo "Development environment ready."
	@echo "  Git hooks installed from .githooks/"
	@echo "  Run 'make test' to verify."

test: ## Run unit/integration tests (~26s)
	pytest

test-e2e: ## Run e2e subprocess tests (~143s)
	pytest -m e2e

test-all: ## Run all tests (~182s)
	pytest -m ""

help: ## Show this help
	@grep -E '^[a-zA-Z0-9_-]+:.*## ' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
