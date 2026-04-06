# Prompt 版本留痕（对齐 answer 文档要求）

answer 文档要求：每次修改 prompt 记录 **prompt_version**、**改了什么**、**为什么改**；必要时附 **改前后示例 transcript**。本文件做仓库级摘要；详细批次产物见 `eval/output/*/run_manifest.json` 与 `eval/review/`。

## 当前默认版本

- **清单**：`prompts/manifest.yaml` → `default_version: "0.2.1"`（bundle `safechat-aud@0.2.1`）。
- **运行时**：由 `PROMPT_BUNDLE_VERSION` 或会话字段 `prompt_bundle_version` 锁定；冻结说明见 `docs/v1-pilot-freeze.md`（若存在）。

## 版本线摘要

| Bundle | 说明（摘自 manifest） |
|--------|------------------------|
| **0.1** | v0.1 冻结快照（首轮 QA 前） |
| **0.2** | 首轮 QA 冻结（含 transition 与槽位双问号问题；见 `failure_taxonomy_v01`） |
| **0.2.1** | QA cycle 1：去重 transition 问句、强化单问句、自动评分对齐 |

## 任务 4 相关产物（不依赖付费 LLM 也可维护）

| 产物 | 路径 / 用途 |
|------|-------------|
| 风格分离评审备忘 | `eval/review/style_separation_notes.md` |
| 转写评审量表 | `eval/review/TRANSCRIPT_REVIEW_RUBRIC.md` |
| 每批启发式 failure 行 | `eval/output/<run>/failure_log.jsonl` |
| 失败模式备忘 | `eval/review/top10_likely_failure_patterns.md` |
| 人工+自动列表示例 | `eval/review/qa_cycle1_first20_human_plus_auto.csv` |

**说明**：在 API 配额不足时，批次可能大量 **stub 回退**，transcript 仍可用于流程与长度检查，但 **不宜** 作为「真实模型relational 质量」的最终依据；配额恢复后应重跑 `eval/run_batch.py` 并更新本 changelog 的一行记录。

## 日后追加一条记录的模板

```text
## YYYY-MM-DD — safechat-aud@x.y.z
- 改了什么：（文件列表 + 一两句）
- 为什么改：（假设 / 评审发现 / 伦理批件）
- 示例：（可选）指向 eval/output/.../transcripts/...
```
