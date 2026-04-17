# Makefile for Onshape MCP Server

.PHONY: help install test test-unit test-cov test-watch clean lint format check-all

# Default target
help:
	@echo "Onshape MCP Server - Available commands:"
	@echo ""
	@echo "  make install      - Install dependencies including dev dependencies"
	@echo "  make test         - Run all tests"
	@echo "  make test-unit    - Run unit tests only"
	@echo "  make test-cov     - Run tests with detailed coverage report"
	@echo "  make test-watch   - Run tests in watch mode"
	@echo "  make lint         - Run code linters (ruff)"
	@echo "  make format       - Format code with black"
	@echo "  make type-check   - Run type checking with mypy"
	@echo "  make check-all    - Run all checks (lint, type-check, test)"
	@echo "  make clean        - Remove build artifacts and cache files"
	@echo "  make coverage-html - Generate HTML coverage report"
	@echo ""

# Installation
install:
	pip install -e ".[dev]"

# Testing
test:
	pytest

test-unit:
	pytest -m "not integration" -v

test-cov:
	pytest --cov=onshape_mcp --cov-report=term-missing --cov-report=html -v

test-watch:
	pytest-watch

# Code quality
lint:
	ruff check onshape_mcp tests

format:
	black onshape_mcp tests
	ruff check --fix onshape_mcp tests

type-check:
	mypy onshape_mcp

check-all: lint type-check test

# Coverage
coverage-html:
	pytest --cov=onshape_mcp --cov-report=html
	@echo "Coverage report generated in htmlcov/index.html"

coverage-xml:
	pytest --cov=onshape_mcp --cov-report=xml

# Cleaning
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -rf htmlcov
	rm -rf .coverage
	rm -rf coverage.xml
	rm -rf dist
	rm -rf build

# Development server
run:
	python -m onshape_mcp.server
