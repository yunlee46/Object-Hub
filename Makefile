# Common tasks. Everything here is a thin wrapper: the underlying commands are short
# enough to run by hand if you prefer.

COMPOSE      := docker compose
COMPOSE_DEV  := docker compose -f docker-compose.yml -f docker-compose.dev.yml

.PHONY: help up down logs shell dev build migrate revision test lint fmt clean

help:
	@echo "up        Start the stack in the background"
	@echo "dev       Start with hot reload in the foreground"
	@echo "down      Stop the stack, keeping all data"
	@echo "logs      Follow application logs"
	@echo "shell     Open a shell in the running app container"
	@echo "migrate   Apply migrations against the running stack"
	@echo "revision  Autogenerate a migration against the dev stack (m=\"message\")"
	@echo "test      Run the test suite locally"
	@echo "lint      Run ruff"
	@echo "clean     Remove local caches"

up:
	$(COMPOSE) up -d --build
	@echo "Object Hub is on http://localhost:$${APP_PORT:-8080}"

dev:
	$(COMPOSE_DEV) up --build

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f app

shell:
	$(COMPOSE) exec app sh

build:
	$(COMPOSE) build

migrate:
	$(COMPOSE) exec app alembic upgrade head

revision:
	@test -n "$(m)" || (echo 'Usage: make revision m="add widget table"'; exit 1)
	$(COMPOSE_DEV) exec app alembic revision --autogenerate -m "$(m)"

test:
	python -m pytest

lint:
	python -m ruff check .

fmt:
	python -m ruff check . --fix

clean:
	rm -rf .pytest_cache .ruff_cache var
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
