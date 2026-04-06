# SafeChat-AUD 安全路由与研究边界说明（v1）

本文件描述 **v1 规则型** 安全层行为，供研究者、工程师与伦理沟通使用。**对策文案与规则阈值在 IRB 批准前均为占位**，可在不改动 FSM 阶段定义的前提下迭代。

## 1. 设计原则

- **确定性**：仅关键词 / 正则 / 静态规则；**不由**对话模型决定路由。
- **研究仪器**：系统提供结构化流程与低风险支持性文本，**不是**治疗产品、急诊服务或持续监护渠道。
- **可审计**：严重度、路由动作、命中规则代码写入 `sessions.safety_*`、`chat_turns.stub_meta` 与 `audit_events`。

## 2. 严重度（0–3）

| 级别 | 含义（操作性） |
|------|----------------|
| 0 | 未命中关心规则 |
| 1 | 显著痛苦/适应困难提示，无明确自伤他害表述 |
| 2 | 自伤/物质相关等 **中度** 风险表述（规则表见 `app/services/safety_routing.py`） |
| 3 | **紧迫** 安全事件表述（含部分自杀意图 + 手段/时间邻近等模式） |

## 3. 路由动作

| 动作 | 典型用途 |
|------|-----------|
| `CONTINUE` | 正常继续 |
| `SHOW_RESOURCES_AND_CONTINUE` | 提示查看帮助与资源，流程继续 |
| `SHOW_RESOURCES_AND_END_CHAT` | 以政策话术结束聊天；会话进入 `post_survey_pending`（若协议允许后测） |
| `EMERGENCY_STOP` | 紧急停聊；会话 `abandoned`，`dropout_stage` 标记为安全相关 |

### 严重度 → 默认动作（v1）

| 严重度 | 默认动作 |
|--------|-----------|
| 0 | `CONTINUE` |
| 1 | `SHOW_RESOURCES_AND_CONTINUE` |
| 2 | `SHOW_RESOURCES_AND_END_CHAT`（**聊前闸**：阻止进入聊天，等同终止路径） |
| 3 | `EMERGENCY_STOP`（**聊前闸**：阻止进入聊天） |

> **聊前 vs 聊中**：聊前扫描合并资格与基线问卷中的开放文本；聊中对每条用户消息扫描。严重度→动作映射相同，但 `SHOW_RESOURCES_AND_END_CHAT` 在聊前表现为 **不分配实验臂、不进入聊天**。

## 4. 参与者界面要点（占位文案）

- **非持续监控**：页面须说明对话不会被人持续监看。
- **非治疗 / 非急诊**：须区别于临床服务。
- **风险触发结束语**：使用后端政策模板（`ASSISTANT_SAFE_END_CHAT` / `ASSISTANT_EMERGENCY_STOP`），IRB 定稿前为占位。

## 5. 审计事件类型（摘录）

- `safety_routing_transition`：`payload` 含 `phase`（`pre_chat` / `in_chat`）、`routing_action`、`severity`、`codes`。
- `safety_pre_chat_block`：聊前拦截。
- `safety_emergency_stop`：聊中紧急停止。
- `safety_scan_baseline`：基线字段扫描。
- `chat_completed_safety`：因严重度 2 规则结束聊天。

## 6. 与 LLM 输出的关系

- `prompt_version`（提示词包引用）与 `model_version`（见 `llm_calls` 表）的写入逻辑**不因**安全层而改变。
- LLM 若返回 `safety_level` 等字段，仅作为 **记录/评估**，**不**参与 v1 路由决策。

## 7. 后续可扩展项（非 v1 范围）

- 经批准的分类器或人工复核队列。
- 英文/方言规则表、校准集与假阳性/假阴性监测仪表盘。
