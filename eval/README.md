# SafeChat-AUD 离线转写与 Prompt QA

本目录提供 **persona 包**、**批量会话 runner** 与 **评审导出**（`summary.jsonl` / `summary.csv`、`transcripts/`、`failure_log.jsonl`、逐 run 的 `artifacts/*.json`）。不走前端、不新增业务接口；聊天与 FSM 与线上一致，经 `FastAPI TestClient` 调用现有路由。

## 前置条件

- PostgreSQL，已执行 `alembic upgrade head`（与 `apps/api` 相同 `DATABASE_URL`）。
- Python 依赖：使用 `apps/api` 虚拟环境（含 `pyyaml`、`fastapi` 等）。

```bash
cd apps/api
pip install -r requirements.txt
```

## 运行批量模拟

在仓库根目录执行（Windows 下路径按本机调整）：

```bash
# 默认：清空本进程 OpenAI Key，走 YAML stub（可复现、不耗额度）
set DATABASE_URL=postgresql+psycopg://...
python eval/run_batch.py

# 每臂 3 次重复
python eval/run_batch.py --runs-per-arm 3

# 仅跑部分 persona
python eval/run_batch.py --persona-ids p01_social_short_guarded p02_stress_long_open

# 使用真实 LLM（需环境变量 OPENAI_API_KEY）
python eval/run_batch.py --no-stub-llm --prompt-bundle-version 0.2.1 --output eval/output/my_run

# 指定输出目录
python eval/run_batch.py --output eval/output/my_run
```

环境变量（可选）：

- `SAFECHAT_SIMULATION_MODE` / `SAFECHAT_SIMULATION_FORCE_ARM`：与 runner 内在 `settings` 赋值等价；随机分组在 `simulation_mode` 且 `force_arm` 为 `empathic`/`neutral` 时固定该臂（见 `apps/api/app/routers/sessions.py`）。
- **LLM 提供方**（`apps/api/app/config.py`）：
  - `LLM_PROVIDER=openai`（默认）：`OPENAI_API_KEY`、`OPENAI_MODEL`、`OPENAI_BASE_URL`（可选）。
  - `LLM_PROVIDER=gemini`：`GEMINI_API_KEY`、`GEMINI_MODEL`（默认 `gemini-2.0-flash`）、`GEMINI_BASE_URL`（默认 Google OpenAI 兼容端点）。
  - 仍支持旧写法：不设 `LLM_PROVIDER` 时，将 Gemini Key 填入 `OPENAI_API_KEY` 并把 `OPENAI_BASE_URL` 设为 `https://generativelanguage.googleapis.com/v1beta/openai/`。

### Gemini 10 session 冒烟（5 persona × 2 臂 × 每臂 1 次）

1. 在 **`apps/api/.env`**（勿提交 Git）设置：
   - `LLM_PROVIDER=gemini`
   - `GEMINI_API_KEY=<Google AI Studio>`
   - `DATABASE_URL=<已 migrate 的 Postgres>`
2. 仓库根目录 PowerShell：

```powershell
.\eval\smoke_gemini_10.ps1
```

或手动（**仓库根目录**，使用 `apps/api` 的 venv）：

```bash
apps/api/.venv/Scripts/python.exe eval/run_batch.py --no-stub-llm --runs-per-arm 1 --max-personas 5 --prompt-bundle-version 0.2.1 --output eval/output/smoke_gemini_manual
apps/api/.venv/Scripts/python.exe eval/summarize_smoke_batch.py --batch-dir eval/output/smoke_gemini_manual
```

`run_manifest.json` 含 `llm_provider`、`effective_llm_model`；`smoke_summary.md` 为聚合简报。

## 输出说明

每次运行生成目录（默认 `eval/output/<UTC时间戳>/`）：

| 路径 | 说明 |
|------|------|
| `summary.jsonl` | 每行一个 run 的完整指标（含 `final_slot_json`） |
| `summary.csv` | 同上，便于表格筛选；`final_slot_json` 为 JSON 字符串 |
| `failure_log.jsonl` | 评审字段 + 启发式标记（需人工最终判定） |
| `transcripts/*.txt` | 可读转写（USER / ASSISTANT 按轮） |
| `artifacts/*.json` | 单 run 结构化副本（含 `turns`，供自动评分 / taxonomy） |
| `run_manifest.json` | 本次运行的 prompt 环境、模型名、stub 与否等 |

单 run 核心字段：`persona_id`、`arm`、`prompt_version`、`model_version`、`completed_all_stages`、`fallback_used`（次数）、`invalid_json_count`（LLM 解析/结构类失败次数，无 Key 时为 0）、`final_slot_json`、`transcript_path`；另含 `stub_turns_count`、`llm_attempted` 便于区分 stub 与真实模型。

`failure_log.jsonl` 每行含：`style_leakage`、`repetitive_or_scripted`、`too_long_or_wordy`、`weak_stage_3_micro_plan`、`unsafe_or_boundary_issue`、`slot_fill_problem`、`reviewer_notes`（启发式辅助，**不能替代人工审读**）。

## Persona 包

`personas.yaml` 含 15 个模拟用户；每人恰好 **9 条** `user_turns`，顺序与 `chat_fsm.REQUIRED_SLOTS_BY_STAGE` 一致。修改后可直接重跑批量脚本做回归。

## 相关代码

- 评测强制分组：`apps/api/app/config.py`（`simulation_mode` / `simulation_force_arm`）、`post_randomize`
- 集成测试：`apps/api/tests/test_chat_flow_integration.py` 中 `test_simulation_forces_arm_on_randomize`

## 首轮 Prompt QA（人工评审）

- 量表：`eval/review/TRANSCRIPT_REVIEW_RUBRIC.md`
- 前 20 条转写 CSV 模板：`eval/review/review_template_first20.csv`
- 风格分离备忘 / 常见失败模式：`eval/review/style_separation_notes.md`、`eval/review/top10_likely_failure_patterns.md`

固定批次示例（15 persona × 2 臂 × 2 次）：

```bash
python eval/run_batch.py --output eval/output/qa_cycle1_fixed --runs-per-arm 2
```

## 无数据库但要用真实 LLM（离线 FSM）

与线上一致的槽位推进 + `build_turn_messages` + `call_chat_turn_structured`，不占 PostgreSQL：

```bash
# 需 OPENAI_API_KEY；默认加载 safechat-aud@0.2.1
python eval/run_llm_offline_batch.py --output eval/output/qa_real_llm_cycle1 --runs-per-arm 2

# 先试跑前 N 个 session
python eval/run_llm_offline_batch.py --output eval/out_try --limit-runs 2 --runs-per-arm 1
```

## Failure taxonomy v0.1 + 自动评分器

```bash
python eval/build_taxonomy_v01.py --batch-dir eval/output/qa_real_llm_cycle1 --first-n 20
```

三类 grader 说明见 **`eval/GRADERS.md`**。
