"""提示词包注册表：按 manifest 加载 YAML，不调用模型。"""

from __future__ import annotations

import functools
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from app.config import settings


def _read_yaml(path: Path) -> dict[str, Any]:
    """读取 YAML 为 dict；文件不存在或非法则返回空 dict。"""
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data if isinstance(data, dict) else {}


def _load_manifest(prompts_dir: Path) -> dict[str, Any]:
    """加载 prompts 目录下的 manifest.yaml。"""
    return _read_yaml(prompts_dir / "manifest.yaml")


def _stage_key_to_index(key: str) -> int:
    """将 manifest 中的 stage_N 键转为整数阶段号。"""
    if key.startswith("stage_") and key[6:].isdigit():
        return int(key[6:])
    raise ValueError(f"Invalid stage key in manifest: {key}")


def _normalize_ref(version_ref: str, manifest: dict[str, Any]) -> tuple[str, str]:
    """解析 bundle_id@version 或仅 version，返回 (bundle_id, version)。"""
    bundle_id = str(manifest.get("bundle_id") or "safechat-aud")
    if "@" in version_ref:
        bid, ver = version_ref.split("@", 1)
        return bid.strip() or bundle_id, ver.strip()
    return bundle_id, version_ref.strip()


@dataclass(frozen=True)
class PromptBundle:
    """内存中的提示词包：全局/两臂风格与各阶段 YAML 内容。"""

    bundle_id: str
    version: str
    global_data: dict[str, Any]
    warm: dict[str, Any]
    neutral: dict[str, Any]
    stages: dict[int, dict[str, Any]]

    @property
    def version_ref(self) -> str:
        return f"{self.bundle_id}@{self.version}"


def _build_bundle(prompts_dir: Path, bundle_id: str, version: str, manifest: dict[str, Any]) -> PromptBundle:
    """按 manifest 中某版本条目加载所有 YAML 并组装 PromptBundle。"""
    bundles = manifest.get("bundles") or {}
    spec = bundles.get(version)
    if not isinstance(spec, dict):
        raise ValueError(f"Unknown prompt bundle version: {version!r}")

    files = spec.get("files") or {}
    if not isinstance(files, dict):
        raise ValueError("Invalid manifest: bundles[].files")

    global_name = str(files.get("global") or "global.yaml")
    warm_name = str(files.get("warm") or "warm.yaml")
    neutral_name = str(files.get("neutral") or "neutral.yaml")

    global_data = _read_yaml(prompts_dir / global_name)
    warm_data = _read_yaml(prompts_dir / warm_name)
    neutral_data = _read_yaml(prompts_dir / neutral_name)

    stages: dict[int, dict[str, Any]] = {}
    for k, fname in files.items():
        if not isinstance(k, str) or not k.startswith("stage_"):
            continue
        idx = _stage_key_to_index(k)
        stages[idx] = _read_yaml(prompts_dir / str(fname))

    return PromptBundle(
        bundle_id=bundle_id,
        version=version,
        global_data=global_data,
        warm=warm_data,
        neutral=neutral_data,
        stages=stages,
    )


@functools.lru_cache(maxsize=8)
def _cached_bundle(prompts_dir_str: str, version_ref: str) -> PromptBundle:
    """LRU 缓存的 bundle 加载实现（键为目录绝对路径 + 版本引用字符串）。"""
    prompts_dir = Path(prompts_dir_str)
    manifest = _load_manifest(prompts_dir)
    bundle_id, version = _normalize_ref(version_ref, manifest)
    mid = str(manifest.get("bundle_id") or "safechat-aud")
    if bundle_id != mid:
        # v0.1：仅支持清单中的 bundle_id
        bundle_id = mid
    return _build_bundle(prompts_dir, bundle_id, version, manifest)


def clear_bundle_cache() -> None:
    """清空提示词包缓存（测试或热更 manifest 时可调用）。"""
    _cached_bundle.cache_clear()


def load_bundle(version_ref: str | None = None) -> PromptBundle:
    """
    加载提示词包。
    version_ref: `bundle_id@version` 或仅 `version`（将套用 manifest.bundle_id）。
    若为 None，使用 settings.prompt_bundle_version（仅版本号）拼 manifest.bundle_id。
    """
    prompts_dir = Path(settings.prompts_dir)
    manifest = _load_manifest(prompts_dir)
    bid = str(manifest.get("bundle_id") or "safechat-aud")
    default_ver = str(manifest.get("default_version") or settings.prompt_bundle_version)

    if version_ref is None or version_ref == "":
        ver = str(settings.prompt_bundle_version or default_ver)
        ref = f"{bid}@{ver}"
    else:
        ref = version_ref if "@" in version_ref else f"{bid}@{version_ref}"

    return _cached_bundle(str(prompts_dir.resolve()), ref)


def resolve_version_ref_for_session(stored: str | None) -> str:
    """会话已冻结的版本引用；若为空则用当前默认包。"""
    if stored and stored.strip():
        return stored.strip()
    b = load_bundle(None)
    return b.version_ref
