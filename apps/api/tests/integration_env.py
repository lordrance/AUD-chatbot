"""集成 / 验收测试：数据库可用性判断与统一 skip 说明（不改产品逻辑）。"""

from __future__ import annotations

import os

# 与 docker-compose 中 db 服务、.env.acceptance.example 对齐
LOCAL_ACCEPTANCE_DB_URL = (
    "postgresql+psycopg://safechat:safechat@127.0.0.1:5432/safechat_aud"
)

INTEGRATION_SKIP_REASON = (
    "需要 PostgreSQL：在仓库根目录执行 scripts/acceptance-local.ps1（或 .sh），"
    "或手动设置 TEST_DATABASE_URL / DATABASE_URL 后执行 alembic upgrade head。"
    "详见 docs/acceptance-checklist.md"
)


def is_integration_db_configured() -> bool:
    return bool((os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL") or "").strip())
