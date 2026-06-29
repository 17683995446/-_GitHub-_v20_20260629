.PHONY: install dev lint typecheck test test-cov clean run migrate

install:
	pip install -e .

dev:
	pip install -e ".[dev]"
	pre-commit install

lint:
	ruff check services/ shared/ models/ tests/
	ruff format --check services/ shared/ models/ tests/

typecheck:
	mypy services/ shared/ models/

test:
	pytest tests/ -v

test-cov:
	pytest tests/ --cov=services --cov=shared --cov-report=html

run:
	uvicorn services.api.main:app --host 0.0.0.0 --port 8000 --reload

migrate:
	alembic upgrade head

clean:
	rm -rf __pycache__ .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -exec rm -rf {} +
