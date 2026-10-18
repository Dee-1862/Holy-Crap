SHELL := /bin/bash

PYTHON ?= python3
VENV := .venv
VENV_PY := $(VENV)/bin/python

.DEFAULT_GOAL := help

.PHONY: help bootstrap doctor dev api web test test-api test-web build-web clean-generated

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-16s %s\n", $$1, $$2}'

bootstrap: ## Create venv, editable dev install, and npm install
	$(PYTHON) -m venv $(VENV)
	$(VENV_PY) -m pip install --upgrade pip
	$(VENV_PY) -m pip install -e '.[dev]'
	npm --prefix web install

doctor: ## Read-only prerequisites report (runs with system python)
	$(PYTHON) scripts/doctor.py

dev: ## Run API + Vite together (Ctrl-C stops both)
	$(VENV_PY) scripts/dev.py

api: ## Run the API server only
	$(VENV_PY) scripts/dev.py --api-only

web: ## Run the Vite dev server only
	$(VENV_PY) scripts/dev.py --web-only

test: test-api test-web ## Full test suite (backend + frontend)

test-api: ## Backend tests via pytest
	$(VENV_PY) -m pytest tests/

test-web: build-web ## Frontend checks (build)

build-web: ## Production build of the frontend
	npm --prefix web run build

clean-generated: ## Remove known generated local artifacts (never touches .simlab/)
	rm -rf web/dist .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage coverage.xml
