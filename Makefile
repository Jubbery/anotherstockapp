# One place for the commands CI runs, so `make check` locally and a green CI mean
# the same thing. Every recipe here has a counterpart in .github/workflows/ci.yml.

.PHONY: help install check lint fmt types arch test leakage cov migrate-test db-up db-down clean

help:
	@grep -E '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  %-14s %s\n", $$1, $$2}'

install:  ## sync dependencies (Python 3.12)
	uv sync --all-extras --python 3.12

lint:  ## ruff check + format check
	uv run ruff check .
	uv run ruff format --check .

fmt:  ## apply formatting and safe fixes
	uv run ruff check --fix .
	uv run ruff format .

types:  ## mypy --strict on libs/ and services/ (R-5.5.c)
	uv run mypy

arch:  ## import-linter architecture contracts (R-18.6.a)
	uv run lint-imports

test:  ## unit, property, golden
	uv run pytest

leakage:  ## point-in-time guards -- these block merge (R-9.1.a)
	uv run pytest tests/leakage -v

cov:  ## risk governor branch coverage, 100% or fail (R-12.6.a)
	uv run pytest tests/ --cov=services/engine/risk --cov-branch \
		--cov-fail-under=100 --cov-report=term-missing

migrate-test:  ## migration + audit-log integrity tests (needs ATLAS_TEST_DATABASE_URL)
	uv run pytest tests/integration -v

check: lint types arch test leakage cov  ## everything CI runs, except the DB job

clean:
	rm -rf .mypy_cache .ruff_cache .pytest_cache .coverage htmlcov dist build
