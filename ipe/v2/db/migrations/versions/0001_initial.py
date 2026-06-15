"""initial — problems / test_cases / generation_requests (계약 §3)

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-15

스키마 SSOT 는 ``ipe.v2.db.schema.metadata`` 다. 초기 마이그레이션은 그 metadata 로
테이블을 생성한다 (DRY — 컬럼 재기술 없음). 이후 변경은 autogenerate 로 델타 생성.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from ipe.v2.db.schema import metadata

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    metadata.create_all(op.get_bind())


def downgrade() -> None:
    metadata.drop_all(op.get_bind())
