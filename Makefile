.PHONY: install lint test ci selftest selftest-all clean help

help:
	@echo "IPE 빌드 타겟:"
	@echo "  make install       — 패키지 + dev deps 설치 (editable)"
	@echo "  make lint          — ruff + mypy --strict"
	@echo "  make test          — pytest (e2e 제외, with coverage)"
	@echo "  make ci            — lint + test (CI 통합 타겟, P12.4 DoD)"
	@echo "  make selftest      — sandbox isolation self-test (auto tier)"
	@echo "  make selftest-all  — 모든 sandbox tier (rlimit/sandboxexec/docker)"
	@echo "  make clean         — build/cache 정리"

install:
	pip install -e ".[dev]"

lint:
	ruff check ipe tests main.py
	mypy --strict ipe main.py

test:
	pytest -q -m "not e2e" --cov=ipe --cov-report=term

ci: lint test

selftest:
	python -m ipe.sandbox --tier auto

selftest-all:
	@for tier in rlimit sandboxexec docker; do \
	  echo "=== sandbox selftest tier=$$tier ==="; \
	  python -m ipe.sandbox --tier $$tier || echo "(tier=$$tier unavailable, skipped)"; \
	done

clean:
	rm -rf build/ dist/ *.egg-info/ .pytest_cache/ .mypy_cache/ .ruff_cache/ .coverage htmlcov/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
