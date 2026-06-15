"""Alembic 환경 — target_metadata 를 schema SSOT 에 배선.

DB URL 은 환경변수 ``IPE_DB_URL`` 에서 읽는다 (자격증명을 alembic.ini 에 안 둠).
autogenerate 는 ``ipe.v2.db.schema.metadata`` 와 실제 DB 를 비교한다.
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from ipe.v2.db.schema import metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

_url = os.environ.get("IPE_DB_URL")
if _url:
    config.set_main_option("sqlalchemy.url", _url)

target_metadata = metadata


def run_migrations_offline() -> None:
    """URL 만으로 SQL 스크립트 생성 (DB 연결 없이)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """실제 DB 연결로 마이그레이션 적용."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
