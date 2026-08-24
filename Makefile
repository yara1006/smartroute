.PHONY: help install dev test test-cov lint format run run-web build clean

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install:  ## Install Python dependencies
	pip install -r requirements.txt

dev:  ## Install dev dependencies
	pip install -r requirements.txt
	pip install pytest ruff mypy pytest-cov
	cd web && npm install

test:  ## Run all tests
	python -m pytest tests/ -v

test-cov:  ## Run tests with coverage
	python -m pytest tests/ --cov=. --cov-report=term-missing --cov-report=html

lint:  ## Run linters
	ruff check .
	ruff format --check .

format:  ## Auto-format code
	ruff check --fix .
	ruff format .

run:  ## Start the development server
	python -m uvicorn api:app --host 127.0.0.1 --port 8000 --reload

run-web:  ## Start the frontend dev server
	cd web && npm run dev

build:  ## Build the frontend
	cd web && npm run build

clean:  ## Clean up generated files
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name .mypy_cache -exec rm -rf {} +
	find . -type d -name .ruff_cache -exec rm -rf {} +
	rm -rf web/dist web/node_modules
