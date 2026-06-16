"""add problems.algorithm — 알고리즘 분류 1급 컬럼 + 기존 행 백필

Revision ID: 0002_add_algorithm
Revises: 0001_initial
Create Date: 2026-06-16

문제의 알고리즘 분류(은닉 코어 = 시드)를 ``internal_meta.hidden_algorithm`` JSON 에서
쿼리·필터·집계 편의를 위해 1급 컬럼으로 승격(계약 §3 보강). 기존 행은 jsonb 에서 백필.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_add_algorithm"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("problems", sa.Column("algorithm", sa.String(64), nullable=True))
    op.create_index("ix_problems_algorithm", "problems", ["algorithm"])
    # 기존 행 백필 — internal_meta(jsonb).hidden_algorithm (PostgreSQL).
    op.execute(
        "UPDATE problems SET algorithm = internal_meta->>'hidden_algorithm' "
        "WHERE algorithm IS NULL"
    )


def downgrade() -> None:
    op.drop_index("ix_problems_algorithm", table_name="problems")
    op.drop_column("problems", "algorithm")
