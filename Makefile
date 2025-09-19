.PHONY: dev
dev: ## Install dev dependencies
	uv sync --dev

check: test lint fix types
	echo "check"

types:
	uv run pyright 

.PHONY: test
test:  ## Run tests
	uv run pytest $(ARGS)

.PHONY: test-dev
test-dev:  ## Run tests
	uv run pytest -vv -s $(ARGS)


.PHONY: lint
lint:  ## Run linters
	uv run ruff check

.PHONY: fix
fix:  ## Fix lint errors
	uv run ruff format
	uv run ruff check --fix
