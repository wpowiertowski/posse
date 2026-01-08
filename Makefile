.PHONY: help build up down run test test-verbose test-mastodon test-unit shell clean install update

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Available targets:'
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

build: ## Build the Docker images
	docker compose build

up: ## Start the application
	docker compose up app

down: ## Stop and remove containers
	docker compose down

run: ## Run the application once
	docker compose run --rm app

test: ## Run all tests (unit and integration)
	docker compose run --rm test

test-unit: ## Run unit tests only (excluding integration tests)
	docker compose run --rm test pytest tests/ --ignore=tests/test_mastodon_integration.py -v

test-mastodon: ## Run Mastodon integration tests with test instance
	./scripts/run-mastodon-tests.sh

test-verbose: ## Run tests with verbose output
	docker compose run --rm app poetry run pytest -v

shell: ## Open a shell in the container
	docker compose run --rm app bash

clean: ## Clean up containers, volumes, and coverage reports
	docker compose down -v
	rm -rf htmlcov .coverage .pytest_cache __pycache__

clean-mastodon: ## Clean up Mastodon test containers and volumes
	docker compose --profile test down -v

install: ## Install/update dependencies
	docker compose run --rm app poetry install

update: ## Update dependencies
	docker compose run --rm app poetry update

lock: ## Generate poetry.lock file
	docker compose run --rm app poetry lock

add: ## Add a new dependency (usage: make add PACKAGE=package-name)
	docker compose run --rm app poetry add $(PACKAGE)

add-dev: ## Add a new dev dependency (usage: make add-dev PACKAGE=package-name)
	docker compose run --rm app poetry add --group dev $(PACKAGE)
