# SafeChat-AUD v1 验收清单（PostgreSQL）

本清单用于试点前**冻结版**的自动化验收，不引入新功能，仅验证迁移与既定集成测试。

## 推荐：一键本地验收（数据库 + 迁移 + 集成测）

### Windows（PowerShell）

在仓库根目录执行（**可直接复制**，将盘符/路径换成你的克隆目录）：

```powershell
cd E:\ADU
# 1. 首次：创建 venv 并安装依赖（若尚未做）
cd apps\api; python -m venv .venv; .\.venv\Scripts\pip install -r requirements.txt; cd ..\..

# 2. 启动 Docker Desktop 后：
.\scripts\acceptance-local.ps1
```

**脚本会**：检查 Docker（**以 `docker info` 的退出码为准**；stderr 上的 WARNING 不会当作引擎未启动）→ 读取仓库根目录 **`.env.acceptance`**（优先）若不存在则读取 **`.env.acceptance.example`** → `docker compose up -d db` → 等待 `pg_isready` → 将文件中的 `DATABASE_URL` / `TEST_DATABASE_URL` 注入当前进程 → `alembic heads` / `upgrade head` → 运行 `tests/test_safety_routes_integration.py` 与 `tests/test_chat_flow_integration.py`。

**若失败**，脚本会退出非零；请根据红色提示排查：

| 现象 | 处理 |
|------|------|
| 缺少 `.env.acceptance` / `.env.acceptance.example` | 从模板恢复：`Copy-Item .env.acceptance.example .env.acceptance`（仓库根目录） |
| Docker CLI / daemon 不可用 | 安装并启动 **Docker Desktop**，终端重开后再试 |
| 数据库迟迟 not ready | `docker compose ps`、`docker compose logs db`；确认 **5432** 未被其它实例占用 |
| `alembic upgrade head` 失败 | 确认 env 文件中 URL 指向本机 `127.0.0.1:5432` 且与 compose 中 `POSTGRES_*` 一致（用户 `safechat`、库 `safechat_aud`） |
| 缺 `.venv` | 按上文在 `apps/api` 创建 venv 并 `pip install -r requirements.txt` |

### Linux / macOS（Bash）

```bash
chmod +x scripts/acceptance-local.sh   # 首次
./scripts/acceptance-local.sh
```

（同样需要 `apps/api/.venv` 与 `pip install -r requirements.txt`。）

---

## 环境变量模板（与 Docker Compose 对齐）

**位置**：仓库根目录（与 `docker-compose.yml` 同级）。

- **推荐**：`Copy-Item -Path .env.acceptance.example -Destination .env.acceptance`（PowerShell，仓库根目录）。验收脚本**优先**读 `.env.acceptance`，否则读 committed 的 `.env.acceptance.example`。
- 也可不复制：脚本会直接使用 `.env.acceptance.example` 中的变量。

| 变量 | 推荐本地值（与 `docker-compose.yml` 中 `db` 一致） |
|------|-----------------------------------------------------|
| `DATABASE_URL` | `postgresql+psycopg://safechat:safechat@127.0.0.1:5432/safechat_aud` |
| `TEST_DATABASE_URL` | 与上相同（pytest 会优先将此项同步到进程内 `DATABASE_URL`，见 `apps/api/tests/conftest.py`） |

`apps/api/.env.example` 含面向 API 开发的相同说明。**非生产密钥**，仅本地开发/验收。

### `TEST_DATABASE_URL` 与集成测试

- 设置 **`TEST_DATABASE_URL`** 时，pytest 会在 `pytest_configure` 阶段将其**同步为**本进程的 `DATABASE_URL`，保证 FastAPI `settings.database_url` 与测试使用同一连接串。
- 仅设置 `DATABASE_URL` 也可以运行集成测试；两者都设时以 **`TEST_DATABASE_URL`** 为准写入 `DATABASE_URL` 供应用使用。
- 两者皆未设置时，DB 集成用例 **skip**，原因见 `tests/integration_env.py` 中的 `INTEGRATION_SKIP_REASON`；pytest 头部会提示 `integration DB: not configured`。

---

## 手动逐步验收（与脚本等价）

### 1. 启动 PostgreSQL

仓库根目录：

```bash
docker compose up -d db
```

等待 healthy（`docker compose ps` 中 `db` 为 healthy，或 `docker compose exec db pg_isready -U safechat -d safechat_aud` 返回 0）。

### 2. 设置环境变量并迁移

```bash
# Windows CMD
set DATABASE_URL=postgresql+psycopg://safechat:safechat@127.0.0.1:5432/safechat_aud
set TEST_DATABASE_URL=%DATABASE_URL%

cd apps\api
.venv\Scripts\alembic.exe heads
.venv\Scripts\alembic.exe upgrade head
```

**通过标准**：

- `alembic upgrade head` 退出码 `0`。
- `alembic heads` **仅一行** head（当前仓库应为 **`007_summary_fu (head)`**）。

### 3. DB 集成测试

仍须在 `apps/api` 且上述环境变量已设置：

```bash
.venv\Scripts\python.exe -m pytest tests/test_safety_routes_integration.py tests/test_chat_flow_integration.py -v
```

**通过标准**：全部 **passed**（未配置 DB URL 时为 **skipped**，不算验收通过）。

### 测试与验收项对应关系

| 验收项 | 测试文件与用例 |
|--------|----------------|
| 安全路由（聊前 403、聊中 2→后测、聊中 3→abandoned） | `test_safety_routes_integration.py`（3 条） |
| 端到端主路径至 `completed` | `test_chat_flow_integration.py::test_acceptance_e2e_linear_to_completed` |
| 摘要卡持久化 / 导出键 | `test_chat_summary_persistence_has_export_keys`；`test_stage_progression_and_chat_close` |
| 随访 token GET/POST / 重复 409 | `test_followup_public_token_open_and_submit` |
| 聊天阶段推进与关闭 | `test_stage_progression_and_chat_close` |
| 后测门禁 | `test_post_survey_only_after_chat_completed` |

---

## 不访问数据库时的快速冒烟（可选）

**不能替代**上文集成验收：

```bash
cd apps/api
.venv\Scripts\python.exe -m pytest tests/test_chat_fsm.py tests/test_safety_routing.py -q
```

---

## 手工补充（可选）

- 打开 `GET /docs`，确认文档与冻结版本一致（见 **`docs/v1-pilot-freeze.md`**）。
- 前端：`npm run dev`，走通摘要页 → 后测 → 致谢 → 随访（若需）。

---

## Sign-off

- [ ] `docker compose` 中 `db` healthy（或等价 Postgres）
- [ ] `alembic upgrade head` 成功  
- [ ] `alembic heads` 单 head  
- [ ] `test_safety_routes_integration.py` 全绿  
- [ ] `test_chat_flow_integration.py` 全绿  
- [ ] 已阅读 `docs/data-dictionary-export-spec.md` 与 `docs/v1-pilot-freeze.md`  
