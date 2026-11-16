PY ?= python
DAYS ?= 365

.DEFAULT_GOAL := help

.PHONY: help install ingest load transform dashboard build demo test lint quality freshness clean

help: ## Show the available commands
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Create .venv and install the project (Python 3.10+)
	python3 -m venv .venv
	.venv/bin/python -m pip install -U pip
	.venv/bin/python -m pip install -r requirements.txt

ingest: ## Pull the last $(DAYS) days of USGS events into data/lake
	$(PY) -m pipeline ingest --days $(DAYS)

load: ## Load the bronze JSON lake into DuckDB
	$(PY) -m pipeline load

transform: ## Run the dbt project
	$(PY) -m pipeline transform

dashboard: ## Re-render dashboard/index.html from the gold marts
	$(PY) -m pipeline dashboard

build: ## Load, run dbt, run quality checks, render the dashboard
	$(PY) -m pipeline build

demo: ## Offline build from the committed sample partition (no network)
	$(PY) -m pipeline demo

test: ## Run the pytest suite
	$(PY) -m pytest

lint: ## Lint the Python pipeline
	$(PY) -m ruff check .

quality: ## Re-run the data-quality gate
	$(PY) -m pipeline quality

freshness: ## Ask dbt how old the bronze source is
	dbt source freshness --profiles-dir . --project-dir .

clean: ## Remove generated artefacts (keeps data/sample)
	rm -rf target logs build .pytest_cache .ruff_cache data/warehouse data/lake reports
