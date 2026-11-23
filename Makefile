SHELL := /bin/bash
P ?= services

.PHONY: install format lint typecheck imports test check

install:
	uv sync --all-packages

format:
	uv run ruff format $(P)
	uv run ruff check --fix $(P)

lint:
	uv run ruff format --check $(P)
	uv run ruff check $(P)
	uv run flake8 --config setup.cfg $(P)

typecheck:
	uv run python scripts/run_mypy.py $(P)

imports:
	uv run lint-imports

test:
	uv run pytest $(P)

check: lint typecheck imports test
