# Problem Catalog — 영속화 schema + workflow

**Date**: 2026-05-20
**Related**: `ipe/catalog/store.py`, `ipe/catalog/__main__.py`, CHANGES §30

---

## 1. 목적

IPE가 생성한 문제는 `outputs/<run_id>/` 에 1 run 1 문제로 저장된다. 이를:
1. **사람이 review** (approve / reject) 한 후
2. **웹 백엔드** 가 활용 (DB seed, REST API, 문제 풀이 사이트 등)

할 수 있도록 **별도 catalog 레이어**로 indexing.

### 비목적

- 백엔드 자체를 구현하지 않는다 — catalog는 백엔드가 mount하면 되는 파일 시스템 레이아웃.
- 자동 review 안 함 — Reviewer 노드 (M4) 와는 별개. 사람 review는 quality 최종 게이트.

---

## 2. 파일 시스템 레이아웃

```
outputs/
├── <run_id>/                       ← 기존 run 산출물 (그대로 보존)
│   ├── problem.json
│   ├── problem.md
│   ├── solution.py
│   ├── tests/
│   └── ...
└── catalog/
    ├── problems.jsonl              ← 1 row/problem (index, JSON-Lines)
    └── problems/
        └── <id>/                   ← symlink → ../../<run_id>/
            (storage 중복 회피)
```

- **JSONL**: 1 line / problem. line-oriented append + 부분 rewrite 쉬움. SQL DB
  ingest도 line-by-line bulk insert로 단순.
- **Symlink farm**: `<id>/` 가 실제 run 디렉토리로 향함. 백엔드는 catalog/ 만
  mount하면 problem.md / solution.py / tests/ 모두 접근 가능.

---

## 3. JSONL row schema (CatalogEntry)

```json
{
  "id": "p_a1b2c3d4e5f6",
  "run_id": "abc12345",
  "algorithm": "BFS",
  "language": "python",
  "title": "거울의 방 탈출",
  "difficulty_label": "Silver IV",
  "time_limit_ms": 2000,
  "memory_limit_mb": 256,
  "sample_count": 5,
  "testcase_count": 30,
  "created_at": "2026-05-20T05:12:00Z",
  "status": "draft",
  "reviewed_by": null,
  "reviewed_at": null,
  "review_note": null,
  "tags": []
}
```

| 필드 | 타입 | 의미 |
|---|---|---|
| `id` | str (`p_<12hex>`) | run_id + title의 deterministic SHA-1 hash 앞 12자. 같은 run + title은 같은 id (idempotent). |
| `run_id` | str | `outputs/<run_id>/` 와 매핑. |
| `algorithm` | str | `--algorithm` 인자. |
| `language` | str | `python` / `java`. |
| `title` | str | Architect 응답의 `problem_title`. |
| `difficulty_label` | str \| null | Evaluator 노드의 라벨 (e.g. "Bronze V", "Silver IV"). 미평가 시 null. |
| `time_limit_ms` | int | `constraints_structured.time_limit_ms`. |
| `memory_limit_mb` | int | `constraints_structured.memory_limit_mb`. |
| `sample_count` | int | `sample_testcases` 개수. |
| `testcase_count` | int | Phase B/C로 생성된 전체 testcase 개수. |
| `created_at` | str | ISO-8601 UTC `Z` 종료. catalog promote 시점. |
| `status` | `"draft"` \| `"approved"` \| `"rejected"` | review 상태. |
| `reviewed_by` | str \| null | review CLI의 `--by` 인자. |
| `reviewed_at` | str \| null | status 변경 시각. |
| `review_note` | str \| null | review CLI의 `--note` 인자. |
| `tags` | list[str] | 자유 태그. 현재 비어 있음. 후속 PR에서 활용 가능. |

---

## 4. Promote workflow

### 자동 promote (권장)

```bash
python main.py --algorithm BFS --promote-to-catalog
```

`save_result()` 가 `final_status == "success"` 일 때만 `promote_run` 호출.
실패 (`budget_exhausted`, `max_iterations`, `cost_exceeded`) 는 promote 안 함 —
quality bar.

### 수동 promote

기존 run을 catalog에 넣기:
```bash
python -m ipe.catalog promote <run_id>
```

`outputs/<run_id>/problem.json` 이 있어야 함 (없으면 exit 3).

### Idempotency

같은 `run_id` 를 두 번 promote → 새 row 추가 안 함. 기존 entry 반환 + symlink만
보장. **status 보존** (이미 approved면 그대로).

---

## 5. Review workflow

```bash
# 목록 확인
python -m ipe.catalog list                           # 전체
python -m ipe.catalog list --status draft            # 미검토만
python -m ipe.catalog list --json                    # 백엔드 ingest용 JSONL

# 한 문제 검토
python -m ipe.catalog show p_abc123                  # problem.md 출력
python -m ipe.catalog show p_abc123 --meta           # entry JSON 출력

# 판정
python -m ipe.catalog approve p_abc123 --by minsu
python -m ipe.catalog reject p_abc123 --note "ambiguous statement"
```

---

## 6. 백엔드 활용 가이드

### 옵션 A — JSONL을 그대로 사용

백엔드가 작아도 됨 (정적 사이트 + 검색):
```python
# pseudo-FastAPI handler
import json
from pathlib import Path

CATALOG_ROOT = Path("/var/data/outputs/catalog")

def list_problems(status: str = "approved"):
    rows = []
    for line in (CATALOG_ROOT / "problems.jsonl").read_text().splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        if entry.get("status") == status:
            rows.append(entry)
    return rows

def get_problem_md(problem_id: str) -> str:
    return (CATALOG_ROOT / "problems" / problem_id / "problem.md").read_text()
```

### 옵션 B — JSONL → DB seed

PostgreSQL / SQLite / MongoDB 등. JSONL 한 줄 = 1 row. line-by-line bulk insert.
스키마 그대로 ORM model 매핑 (`id` PK, status enum, 나머지 column).

CI/CD에서:
```bash
# nightly sync
psql ipe -c "TRUNCATE problems"
jq -c '.' outputs/catalog/problems.jsonl | psql ipe -c "COPY problems FROM STDIN ..."
```

### 옵션 C — Hybrid

- 메타데이터 (이 JSONL) 는 DB에
- 본문 (problem.md / solution.py / tests/) 은 파일 시스템 그대로 (symlink 경유)

storage 크기 효율 + 검색 성능 둘 다 좋음.

---

## 7. 후속 개선

- **tags 활용**: algorithm 외 추가 카테고리 (e.g. `["graph", "shortest-path"]`).
- **search index**: 본문 full-text search (현재 catalog는 metadata만). 후속 PR.
- **export to formats**: Polygon / Codeforces export. 후속 PR.
- **observability gap fix**: M3 `architect_consensus` / M4 `review_status` 가
  problem.json에 직렬화 안 됨. catalog row에 추가하면 백엔드가 quality signal로
  활용 가능. 후속 작은 PR.
