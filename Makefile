.PHONY: install lint test ci selftest clean help

help:
	@echo "IPE 빌드 타겟:"
	@echo "  make install   — 패키지 + dev deps 설치 (editable)"
	@echo "  make lint      — ruff + mypy"
	@echo "  make test      — pytest (with coverage)"
	@echo "  make ci        — lint + test (CI 통합 타겟)"
	@echo "  make selftest  — sandbox isolation self-test (P1 이후 사용)"
	@echo "  make clean     — build/cache 정리"

install:
	pip install -e ".[dev]"

lint:
	ruff check ipe/ tests/
	mypy ipe/

test:
	pytest -v --cov=ipe --cov-report=term

ci: lint test

selftest:
	python -m ipe.sandbox --tier auto

clean:
	rm -rf build/ dist/ *.egg-info/ .pytest_cache/ .mypy_cache/ .ruff_cache/ .coverage htmlcov/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
