# wikigame-agent — developer commands. Run `make help` for the list.

.PHONY: help install lint format format-check fix test check clean

help: ## Show available targets
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install dependencies (with dev extras) and pre-commit hooks
	uv sync --all-extras
	uv run pre-commit install

lint: ## Run ruff linter
	uv run ruff check .

format: ## Format code with ruff (writes changes)
	uv run ruff format .

format-check: ## Check formatting without writing
	uv run ruff format --check .

fix: ## Auto-fix lint issues and reformat
	uv run ruff check --fix .
	uv run ruff format .

test: ## Run the test suite
	uv run pytest

check: lint format-check test ## Run lint + format-check + tests (matches CI)

clean: ## Remove caches and build artifacts
	rm -rf .pytest_cache .ruff_cache .mypy_cache dist build
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
