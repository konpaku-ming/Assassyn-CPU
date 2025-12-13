.PHONY: help install test test-all test-fetch test-decoder test-execute test-memory test-wb test-hazard clean format lint build run

# Default target
help:
	@echo "Assassyn-CPU Makefile Commands"
	@echo "================================"
	@echo "Setup:"
	@echo "  make install       - Install Python dependencies"
	@echo "  make venv          - Create Python virtual environment"
	@echo ""
	@echo "Testing:"
	@echo "  make test          - Run all tests"
	@echo "  make test-fetch    - Run IF stage tests"
	@echo "  make test-decoder  - Run ID stage tests"
	@echo "  make test-execute  - Run EX stage tests"
	@echo "  make test-memory   - Run MEM stage tests"
	@echo "  make test-wb       - Run WB stage tests"
	@echo "  make test-hazard   - Run data hazard tests"
	@echo "  make test-verbose  - Run tests with verbose output"
	@echo ""
	@echo "Code Quality:"
	@echo "  make format        - Format code with black"
	@echo "  make lint          - Run flake8 linter"
	@echo "  make typecheck     - Run mypy type checker"
	@echo ""
	@echo "Build & Run:"
	@echo "  make build         - Build the CPU system"
	@echo "  make run           - Run the CPU main program"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean         - Remove build artifacts and cache"
	@echo "  make clean-all     - Remove all generated files including venv"

# Setup
venv:
	python3 -m venv .venv
	@echo "Virtual environment created. Activate with: source .venv/bin/activate"

install:
	pip install --upgrade pip
	pip install -r requirements.txt
	@echo "Dependencies installed successfully"

# Testing
test:
	pytest tests/ -v

test-all:
	pytest tests/ -v --cov=src --cov-report=html --cov-report=term

test-fetch:
	pytest tests/test_fetch.py -v

test-decoder:
	pytest tests/test_decoder.py tests/test_decoder_impl.py -v

test-execute:
	pytest tests/test_execute_part1.py tests/test_execute_part2.py tests/test_execute_part3.py -v

test-memory:
	pytest tests/test_memory.py -v

test-wb:
	pytest tests/test_writeback.py -v

test-hazard:
	pytest tests/test_datahazard.py -v

test-verbose:
	pytest tests/ -vv -s

# Code quality
format:
	black src/ tests/

lint:
	flake8 src/ tests/ --max-line-length=120 --extend-ignore=E203,W503

typecheck:
	mypy src/

# Build and run
build:
	python -m src.main

run: build

# Cleanup
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.py,cover" -delete
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf htmlcov/
	rm -rf .coverage
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf .workspace/*.exe
	rm -rf .workspace/*.init
	@echo "Cleaned build artifacts and cache"

clean-all: clean
	rm -rf .venv/
	@echo "Cleaned all generated files including virtual environment"
