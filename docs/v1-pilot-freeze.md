# Pilot v1 研究包冻结说明

以下为 **SafeChat-AUD 试点 v1** 的**版本化组件**快照（仅文档冻结，不自动改代码）。代码中的权威来源仍以仓库内常量/清单为准。

## Pilot v1 验收执行状态

| 项目 | 说明 |
|------|------|
| **冻结快照本文** | 下列版本号与路径以当前仓库内容为准，**不等同于**「已在目标环境跑通 checklist」。 |
| **须由你方完成** | 在 PostgreSQL 可用时按 `docs/acceptance-checklist.md` 执行 `alembic upgrade head` 与集成 pytest **全部 passed** 后，试点部署方可记为 **v1 验收通过**。 |
| **无库冒烟（参考）** | `pytest tests/test_chat_fsm.py tests/test_safety_routing.py` 可在无数据库时用于快速回归；**不可替代**集成验收。 |

## 数据库 schema 冻结（Alembic）

- **当前 head revision**：**`007_summary_fu`**（迁移脚本 `alembic/versions/007_chat_summary_and_followup.py`，父修订 `006_safety`）。
- 验收时须 `alembic heads` 仅显示上述 head，且 `upgrade head` 退出码为 0。

## 冻结项一览

| 组件 | 冻结值 / 定位 | 备注 |
|------|----------------|------|
| **知情同意书版本** | `CONSENT_DOCUMENT_VERSION = 2026-04-04-v1`（`apps/api/app/constants.py`） | 正文：`docs/consent/body_2026-04-04-v1.md` 与 `apps/api/consent_documents/body_2026-04-04-v1.md`（部署镜像用副本，须与之一致） |
| **提示词包** | `PROMPT_BUNDLE_VERSION` 默认 **`0.2.1`**；完整引用 **`safechat-aud@0.2.1`**（`prompts/manifest.yaml` → `bundle_id` + 版本） | 随机分组写入 `sessions.prompt_bundle_version`；聊天与 `llm_calls.prompt_version` 对齐 |
| **后测问卷 schema** | **`SURVEY_SCHEMA_POST = "2"`** | 写入 `survey_responses.schema_version`（`instrument=post`） |
| **随访问卷 schema** | **`SURVEY_SCHEMA_FOLLOWUP_7D = "1"`** | 写入 `session_followups.response_schema_version` |
| **基线/资格/同意 schema** | consent `1`、eligibility `1`、baseline `1` | 见 `app/constants.py` |
| **摘要卡 schema** | **`chat_summary_json.schema_version = "1"`** | 见 `app/services/chat_summary.py` |
| **安全与资源（规则 + 文案 v1）** | 规则：`app/services/safety_routing.py`；研究/工程说明：`docs/safety-playbook.md`；**被试弹层资源占位文案**：`apps/web/src/components/HelpResourcesModal.tsx`；危机固定回复（聊中策略）：`safety_routing.py` 内 `ASSISTANT_EMERGENCY_STOP` / `ASSISTANT_SAFE_END_CHAT` | **IRB 终稿前均为工程占位**；冻结指「试点期间不改规则逻辑与安全动作语义」；同意/伦理正文仍以 consent 文档与批件为准 |

## 不包含在「冻结」内的内容

- 数据条目中的**自由文本**（槽位、开放题、转写）。
- 运行环境密钥、数据库连接串。
- 前端构建版本号（仅当与 API 契约绑定变更时再记录）。

## 试点期间变更流程（简要）

1. **必须变更**（如新伦理批件同意书）：更新正文文件 + `CONSENT_DOCUMENT_VERSION` + 两处 consent md 副本；记录于研究变更日志。  
2. **提示词包**：升 `manifest` / `DEFAULT_PROMPT_BUNDLE_VERSION`，新会话使用新引用；**旧会话**保留历史 `prompt_bundle_version`。  
3. **后测/随访 schema**：升 `SURVEY_SCHEMA_*` 与 Pydantic 模型，**新数据**用新 `schema_version`；分析脚本按版本分列。

## 相关文档

- 验收命令：`docs/acceptance-checklist.md`  
- 导出/分析字段：`docs/data-dictionary-export-spec.md`  
- 同意书维护：`docs/consent-versioning.md`  
