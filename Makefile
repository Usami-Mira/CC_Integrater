.PHONY: install test lint inspect run clean

install:
	python -m venv .venv && .venv/Scripts/activate && \
	pip install -U pip && pip install -e ".[dev]"

inspect:
	.venv/Scripts/python scripts/inspect_parquet.py $(FILE)

run:
	.venv/Scripts/python scripts/run_batch.py --parquet $(FILE) --K 3

test:
	.venv/Scripts/pytest -q

lint:
	.venv/Scripts/ruff check src tests && .venv/Scripts/mypy src

clean:
	rm -rf logs/*.tmp __pycache__ .pytest_cache
