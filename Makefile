.PHONY: install lint test ci selftest selftest-all clean clean-workdir clean-outputs help

help:
	@echo "IPE 빌드 타겟:"
	@echo "  make install       — 패키지 + dev deps 설치 (editable)"
	@echo "  make lint          — ruff + mypy --strict"
	@echo "  make test          — pytest (e2e 제외, with coverage)"
	@echo "  make ci            — lint + test (CI 통합 타겟, P12.4 DoD)"
	@echo "  make selftest      — sandbox isolation self-test (auto tier)"
	@echo "  make selftest-all  — 모든 sandbox tier (rlimit/sandboxexec/docker)"
	@echo "  make clean         — build/cache 정리"
	@echo "  make clean-workdir — sandbox temp (workdir/*) 전체 삭제"
	@echo "  make clean-outputs — outputs/<run_id>/ 중 catalog 미promote + 7일 이상 stale 삭제"

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

clean-workdir:
	@echo "Cleaning workdir/* (sandbox temp data)..."
	@find workdir -mindepth 1 -delete 2>/dev/null || true
	@du -sh workdir 2>/dev/null || echo "workdir/ empty"

# 7일 이상 stale 한 run 디렉토리 삭제. catalog 에 promote 된 run (symlink target 인)
# 은 보존. dry-run 권장: make clean-outputs-dry-run.
clean-outputs:
	@echo "Cleaning outputs/<run_id>/ (catalog 미promote + >7d stale)..."
	@catalog_dir="outputs/catalog/problems"; \
	if [ -d "$$catalog_dir" ]; then \
	  promoted=$$(find "$$catalog_dir" -maxdepth 1 -mindepth 1 -type l -exec readlink {} \; \
	    | xargs -I{} basename {} 2>/dev/null | sort -u); \
	else promoted=""; fi; \
	for d in outputs/*/; do \
	  name=$$(basename "$$d"); \
	  case "$$name" in catalog|by-name) continue;; esac; \
	  if echo "$$promoted" | grep -Fxq "$$name"; then \
	    echo "  KEEP (promoted): $$name"; \
	  elif test -n "$$(find "$$d" -maxdepth 0 -mtime -7 2>/dev/null)"; then \
	    echo "  KEEP (recent):   $$name"; \
	  else \
	    echo "  DELETE:          $$name"; \
	    rm -rf "$$d"; \
	  fi; \
	done
	@du -sh outputs 2>/dev/null || echo "outputs/ size unknown"
