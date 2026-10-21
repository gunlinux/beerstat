.PHONY: dev run release test lint fmt fix check docker

IMAGE ?= beerstat:latest

dev: ## Build the consumer
	cargo build

run: ## Run the consumer
	cargo run

release: ## Build optimized binary
	cargo build --release

test: ## Run tests
	cargo test $(ARGS)

lint: ## Run clippy
	cargo clippy --all-targets -- -D warnings

fmt: ## Check formatting
	cargo fmt --check

fix: ## Auto-format and apply clippy suggestions
	cargo fmt
	cargo clippy --all-targets --fix --allow-dirty --allow-staged

check: fmt lint test ## Full CI check

docker: ## Build container image
	docker build -t $(IMAGE) .
