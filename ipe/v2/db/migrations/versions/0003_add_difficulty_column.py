"""add problems.difficulty — BOJ 티어 1급 컬럼 + 기존 행 백필

Revision ID: 0003_add_difficulty
Revises: 0002_add_algorithm
Create Date: 2026-06-17

사후 난이도 calibration(RFC R4)이 산출한 BOJ 티어 라벨을 ``internal_meta.difficulty.
label`` JSON 에서 쿼리·필터·집계 편의를 위해 1급 컬럼으로 승격(계약 §3 보강,
``algorithm`` 컬럼과 동형). 기존 행은 jsonb 에서 백필(난이도 미주석 행은 NULL 유지).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_add_difficulty"
down_revision: str | None = "0002_add_algorithm"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("problems", sa.Column("difficulty", sa.String(64), nullable=True))
    op.create_index("ix_problems_difficulty", "problems", ["difficulty"])
    # 기존 행 백필 — internal_meta(jsonb).difficulty.label (PostgreSQL).
    op.execute(
        "UPDATE problems SET difficulty = internal_meta->'difficulty'->>'label' "
        "WHERE difficulty IS NULL"
    )


def downgrade() -> None:
    op.drop_index("ix_problems_difficulty", table_name="problems")
    op.drop_column("problems", "difficulty")
