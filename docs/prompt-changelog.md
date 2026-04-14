# Prompt 版本留痕（对齐 answer 文档要求）

answer 文档要求：每次修改 prompt 记录 **prompt_version**、**改了什么**、**为什么改**；必要时附 **改前后示例 transcript**。本文件做仓库级摘要。

## 当前默认版本

- **清单**：`prompts/manifest.yaml` → `default_version: "0.2.1"`（bundle `safechat-aud@0.2.1`）。
- **运行时**：由 `PROMPT_BUNDLE_VERSION` 或会话字段 `prompt_bundle_version` 锁定；冻结说明见 `docs/v1-pilot-freeze.md`（若存在）。

## 版本线摘要

| Bundle | 说明（摘自 manifest） |
|--------|------------------------|
| **0.1** | v0.1 冻结快照（首轮 QA 前） |
| **0.2** | 首轮 QA 冻结（含 transition 与槽位双问号问题；见 `failure_taxonomy_v01`） |
| **0.2.1** | QA cycle 1：去重 transition 问句、强化单问句、自动评分对齐 |

## 日后追加一条记录的模板

```text
## YYYY-MM-DD — safechat-aud@x.y.z
- 改了什么：（文件列表 + 一两句）
- 为什么改：（假设 / 评审发现 / 伦理批件）
- 示例：（可选）附一段对话样例或截图链接
```
