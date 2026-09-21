.PHONY: sync lint format format-check typecheck test check run clean audit

sync:
	uv sync --locked

lint:
	uv run ruff check .

format:
	uv run ruff format .

format-check:
	uv run ruff format --check .

typecheck:
	uv run ty check

test:
	uv run pytest

check:
	$(MAKE) lint
	$(MAKE) format-check
	$(MAKE) typecheck
	$(MAKE) test

run:
	uv run gdis-loader

clean:
	rm -rf build dist .pytest_cache .ruff_cache .ty_cache htmlcov audit

audit:
	scripts/make_audit.sh
