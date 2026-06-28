CLANG_FORMAT     ?= clang-format
CLANG_FORMAT_CFG := backend/configs/clang-format

RUFF     ?= ruff
RUFF_CFG := backend/configs/ruff.toml

FILE_CPP ?= app/src/demo.cpp
FILE_PY  ?= app/src/demo.py

# container runner — override with `make run COMPOSE="docker compose"`
COMPOSE  ?= podman compose
VENV     := backend/.venv

.DEFAULT_GOAL := help

help: ## List the available targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "} {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

fmt-cpp: ## Print formatted C++ file (FILE_CPP=path override)
	$(CLANG_FORMAT) --style=file:$(CLANG_FORMAT_CFG) $(FILE_CPP)

fmt-py: ## Print formatted Python file (FILE_PY=path override)
	$(RUFF) format --config $(RUFF_CFG) --diff $(FILE_PY)

# ── containers ────────────────────────────────────────────────────────────────
run: ## Build and (re)start the app in a container at http://localhost:3000
	$(COMPOSE) up --build --force-recreate

down: ## Stop and remove the app container
	$(COMPOSE) down

# ── tests ─────────────────────────────────────────────────────────────────────
test-deps: ## Install the backend test dependencies into backend/.venv
	test -d $(VENV) || python3 -m venv $(VENV)
	$(VENV)/bin/python -m pip install -q -r backend/requirements-dev.txt

test: ## Run the backend integration test suite
	cd backend && .venv/bin/python -m pytest

.PHONY: help fmt-cpp fmt-py run down test-deps test
