"""Pytest 共享：验收数据库 URL 与简要报告头。"""

from __future__ import annotations

import os


def pytest_configure(config) -> None:
    """
    若已设置 TEST_DATABASE_URL，则同步为 DATABASE_URL，确保：

    - 本进程中 `app.config.settings.database_url` 与集成测试使用同一库；
    - 与「仅设 TEST_DATABASE_URL、不设 DATABASE_URL」的验收习惯一致。

    Alembic CLI 仍读取环境变量 DATABASE_URL；验收脚本会同时设置两者。
    """
    test_url = (os.environ.get("TEST_DATABASE_URL") or "").strip()
    if test_url:
        os.environ["DATABASE_URL"] = test_url


def pytest_report_header(config, start_path) -> list[str]:
    raw = (os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL") or "").strip()
    if not raw:
        return [
            "integration DB: not configured (integration tests skipped unless URL set — see docs/acceptance-checklist.md)",
        ]
    # 避免在日志里打印密码：仅展示 host 段
    try:
        tail = raw.split("@", 1)[-1] if "@" in raw else raw
        return [f"integration DB: ...@{tail}"]
    except Exception:
        return ["integration DB: configured (URL hidden)"]
