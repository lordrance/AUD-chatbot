# SafeChat-AUD

## 简介

SafeChat-AUD 是一套面向**酒精相关减量研究**的**单次会话**线上流程脚手架：参与者完成知情同意、资格筛查、基线问卷后，被随机分配到一种文本对话风格（**三臂**：中立专业 / 支持性务实 / 温暖共情；配置可降为两臂 A+C），经多轮结构化聊天，再填写后测；可选 7 天极简随访。技术栈为 **PostgreSQL + FastAPI + React（Vite）**。对话提示词在 `prompts/`（YAML 与 `strategies.json`）；安全策略为服务端规则扫描（见 `apps/api/app/services/safety_routing.py`）。**参与者可见的网页与 API 提示文案当前为英文**，便于国际受试或英文论文场景；伦理正文与批件语言以机构要求为准。

**材料与 schema 版本**（论文 Methods）：见 `docs/slot-schema-and-stages.md` 末尾「材料版本化」表，以及 `docs/data-dictionary-export-spec.md`。

---

## What’s in the repo

| Area | Path | Notes |
|------|------|--------|
| API | `apps/api` | Sessions, surveys, FSM chat, optional LLM, audits |
| Web | `apps/web` | Participant flow: consent → screening → baseline → randomize → chat → summary → post-survey → thank-you |
| Prompts | `prompts/` | `manifest.yaml`, stage YAML, `strategies.json` |
| Consent text | `docs/consent/body_<version>.md` (+ mirror in `apps/api/consent_documents/`) | Must match `CONSENT_DOCUMENT_VERSION` |
| Eval / QA | `eval/` | Batch runners, `personas.yaml`, heuristics |
| Docs | `docs/` | Acceptance checklist, safety playbook, data dictionary, pilot freeze |

---

## Quick start (local)

**1. Database (Docker)**

```bash
docker compose up db
```

**2. API** (`apps/api`)

```powershell
cd apps\api
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
set DATABASE_URL=postgresql+psycopg://safechat:safechat@127.0.0.1:5432/safechat_aud
alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000/docs

**3. Web** (`apps/web`)

```bash
cd apps/web
npm install
npm run dev
```

Use the URL Vite prints (often http://127.0.0.1:5173).

**Full stack in Docker:** from repo root, `docker compose up --build` (API + DB; run the web app separately unless you add a web service).

---

## Acceptance / integration tests

From repo root (PowerShell example):

```powershell
cd E:\ADU
.\scripts\acceptance-local.ps1
```

Or manually: set `DATABASE_URL` (or `TEST_DATABASE_URL`), run `alembic upgrade head`, then:

```bash
cd apps/api
pytest tests/test_chat_fsm.py tests/test_safety_routing.py tests/test_llm_client_mocked.py -q
pytest tests/test_chat_flow_integration.py tests/test_safety_routes_integration.py -q
```

Details: `docs/acceptance-checklist.md`.

---

## Participant flow (v1)

1. `POST /api/v1/sessions` → store `session_id` + `session_token` (Bearer).
2. `GET /api/v1/consent-document` → show Markdown; `POST .../consent` with matching version.
3. `POST .../eligibility` → may return ineligible.
4. `POST .../surveys/baseline`
5. `POST .../randomize` → assigns `arm`, may **403** with safety `message` (pre-chat block).
6. `POST .../chat/turn` → FSM stages 0–4; without LLM key, deterministic stub + YAML.
7. After chat: UI shows **chat summary** from `GET .../state` → `chat_summary`.
8. `POST .../surveys/post` → completes main flow.
9. Optional: `POST .../followup/opt-in` then public `GET|POST /api/v1/follow-up/{token}`.

---

## LLM (optional)

If `OPENAI_API_KEY` (or Gemini via `LLM_PROVIDER` / `GEMINI_API_KEY`) is set, the API calls a structured JSON chat completion; failures fall back to stub. See `apps/api/app/config.py` and root README’s previous “LLM” section for env vars.

---

## Ethics placeholders

Before real enrollment: replace consent body, finalize safety copy in `safety_routing.py` and `HelpResourcesModal`, and obtain IRB/ethics approval. Versioning: `docs/consent-versioning.md`.

---

## 中文说明（语言与注释）

界面与参与者可见 API 文案为 **英文**；主要源码文件顶部有 **中文模块注释** 便于团队阅读。正式采集前须替换同意书全文、安全话术等占位内容，并取得伦理/IRB 批准。
