"""DB 스키마 SSOT — 정규화 3 테이블 (계약 §3, 파이프라인 소유 DDL).

JSON 컬럼은 ``JSON().with_variant(JSONB, "postgresql")`` 로 포터블: 운영 PostgreSQL
에서는 jsonb, 단위테스트 sqlite 에서는 일반 JSON(TEXT) 로 매핑된다.

- ``problems``: 출하 문제 1건 (지문+io+제약+샘플+정해+내부메타+TL). status 는
  ``draft``/``review``/``published`` — 파이프라인은 ``draft`` 로 적재, 승격은 백엔드.
- ``test_cases``: 채점셋 케이스 (problem_id FK, 줄단위 exact-match 채점용).
- ``generation_requests``: 생성 요청 감사 로그 (idempotency_key PK, raw_package 원문).
"""

from __future__ import annotations

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON

# PG=jsonb / sqlite 등=JSON — 단위테스트(sqlite)와 운영(PG) 양쪽 동작.
_JSON = JSON().with_variant(JSONB, "postgresql")

metadata = MetaData()

problems = Table(
    "problems",
    metadata,
    Column("id", String(36), primary_key=True),  # uuid4 hex-dash
    Column("title", Text, nullable=False),
    Column("description", Text, nullable=False),
    Column("input_format", Text, nullable=False),
    Column("output_format", Text, nullable=False),
    Column("constraints", _JSON, nullable=False),  # [{name,min_value,max_value,...}]
    Column("samples", _JSON, nullable=False),  # [{input_text,expected_output,...}]
    # internal_meta: hidden_algorithm/composition/qa 등 — 응시자 비노출 (계약 §2.5)
    Column("internal_meta", _JSON, nullable=False),
    # algorithm: 문제의 알고리즘 분류(은닉 코어 = 시드, 예: 'dijkstra'). internal_meta.
    # hidden_algorithm 과 동일값을 쿼리·필터·집계 편의를 위해 1급 컬럼으로 승격(응시자
    # 비노출 — 내부 운영 DB). 적재 시 필수 기록.
    Column("algorithm", String(64), nullable=True, index=True),
    # difficulty: BOJ 티어 라벨(예: 'Gold IV'). meta.difficulty.label 에서 승격 — 쿼리·
    # 필터·집계 편의로 1급 컬럼(algorithm 과 동형). 사후 calibration(RFC R4) 산출,
    # 응시자 비노출(internal). 전체 report 는 internal_meta.difficulty 에 보존.
    Column("difficulty", String(64), nullable=True, index=True),
    Column("solution_code", Text, nullable=True),  # 내부 정해 (응시자 비노출)
    Column("solution_language", String(16), nullable=True),
    Column("status", String(16), nullable=False, default="draft"),
    Column("time_limit_ms", Integer, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

test_cases = Table(
    "test_cases",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column(
        "problem_id",
        String(36),
        ForeignKey("problems.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("seq", Integer, nullable=False),
    Column("input", Text, nullable=False),
    Column("expected", Text, nullable=False),  # "" 가능(퇴화 케이스 — 정해 출력 자체가 빈값)
    Column("category", String(64), nullable=True),
)

generation_requests = Table(
    "generation_requests",
    metadata,
    Column("idempotency_key", String(64), primary_key=True),
    Column("seed", String(64), nullable=False),
    Column("mode", String(16), nullable=False),
    Column("job_id", String(64), nullable=True),
    Column("final_status", String(32), nullable=False),
    Column("attempts", Integer, nullable=False, default=1),
    Column("raw_package", _JSON, nullable=True),  # 수신 패키지 원문(감사/재적재)
    Column(
        "problem_id",
        String(36),
        ForeignKey("problems.id", ondelete="SET NULL"),
        nullable=True,
    ),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
