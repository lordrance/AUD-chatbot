"""Load the full consent document body for a version string (single source of truth)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from app.constants import CONSENT_DOCUMENT_VERSION


def consent_body_file(version: str | None = None) -> Path:
    """解析同意书 Markdown 路径：优先 api 内嵌目录，否则 monorepo 的 docs/consent。"""
    v = (version or CONSENT_DOCUMENT_VERSION).strip()
    safe = v.replace("/", "_").replace("\\", "_")
    name = f"body_{safe}.md"
    api_root = Path(__file__).resolve().parents[2]
    bundled = api_root / "consent_documents" / name
    if bundled.is_file():
        return bundled
    repo_root = api_root.parent.parent
    return repo_root / "docs" / "consent" / name


@lru_cache(maxsize=8)
def load_consent_markdown(version: str | None = None) -> str:
    """读取指定版本同意书正文；文件不存在则抛 FileNotFoundError。"""
    path = consent_body_file(version)
    if not path.is_file():
        raise FileNotFoundError(f"Missing consent body file for version={version!r}: {path}")
    return path.read_text(encoding="utf-8")
