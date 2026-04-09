# Jenkins CI（Windows + Docker）运行项目测试

本项目仓库根目录包含 `Jenkinsfile`，可用于 Jenkins Pipeline 自动执行：

- 后端：单元测试（pytest）
- 验收/集成：`scripts/acceptance-local.ps1`（启动 docker compose 的 `db`、执行 `alembic upgrade head`、运行 DB 集成测试）
- 前端：`npm run build`

## 推荐方式：先本地确认一键验收脚本可跑通

在仓库根目录：

```powershell
cd E:\ADU
.\scripts\acceptance-local.ps1
```

若此脚本通过，Jenkins 上通常也能稳定通过。

## Jenkins（Pipeline from SCM）最小配置

1. 安装 Jenkins（推荐 Jenkins LTS）。
2. 创建 Job：New Item → Pipeline。
3. Pipeline → Definition：选择 “Pipeline script from SCM”，SCM 选 Git，填仓库 URL 与凭据。
4. Script Path：填写 `Jenkinsfile`。
5. 运行 Build，查看控制台输出。

## 常见问题

- **Jenkins 机器跑不了 Docker**：`acceptance-local.ps1` 依赖 `docker compose`。请确保 Jenkins Agent 运行在已安装并可用 Docker 的环境中。
- **数据库连接失败**：检查 `.env.acceptance`（或 `.env.acceptance.example`）中的 `DATABASE_URL` 是否与 `docker-compose.yml` 的 db 端口一致。
- **Python 依赖问题**：建议 Jenkins 使用 `apps/api/.venv` 或在 pipeline 中创建并激活虚拟环境后再执行 pytest。

# Jenkins（Windows + Docker）一键跑测试

本项目已提供 `Jenkinsfile`，可直接创建 Jenkins Pipeline，自动执行：

- 后端：`pytest -q`
- 验收/集成：`scripts/acceptance-local.ps1`（会启动 docker compose 的 `db`，执行 `alembic upgrade head`，再跑 DB 集成测试）
- 前端：`npm run build`

## 1) 安装 Jenkins（推荐 Docker）

前置：

- 已安装 Docker Desktop（并能运行 `docker`）
- 已安装 Node.js（用于前端构建）
- 已安装 Python 3.12（用于后端）

在 PowerShell（管理员/普通均可）运行：

```powershell
docker pull jenkins/jenkins:lts
docker run --name adu-jenkins -p 8080:8080 -p 50000:50000 -v jenkins_home:/var/jenkins_home jenkins/jenkins:lts
```

打开 Jenkins：`http://127.0.0.1:8080`

首次解锁密码（在容器日志里能看到，也可进入容器读取）：

```powershell
docker logs adu-jenkins
```

安装插件：选择 “Install suggested plugins” 即可。

## 2) 让 Jenkins 能运行 docker compose（关键）

`scripts/acceptance-local.ps1` 需要 Jenkins Agent 能执行 `docker compose ...`。

最简单做法（建议）：**不要在 Jenkins 容器内直接跑 docker**，而是在你的 Windows 主机上安装 Jenkins（MSI）并用本机作为 agent。

如果你坚持用 Jenkins 容器跑，需要把 Docker Engine 暴露给容器（绑定 docker socket），这在 Windows 上配置复杂且有安全风险，不建议。

## 3) 创建 Pipeline Job（从仓库读 Jenkinsfile）

在 Jenkins 新建：

- New Item → Pipeline
- Pipeline → Definition 选择 “Pipeline script from SCM”
- SCM 选择 Git，填你的仓库地址/凭据
- Script Path 填：`Jenkinsfile`

保存后直接 Build 即可。

## 4) 验收脚本依赖的配置

`scripts/acceptance-local.ps1` 会读取仓库根目录：

- `.env.acceptance`（优先）
- 或 `.env.acceptance.example`

至少需要包含 `DATABASE_URL`（可选 `TEST_DATABASE_URL`）。

## 5) 你将看到的结果

如果全部通过：Pipeline 会显示每个 stage 成功，并输出类似：

- `27 passed, ...`
- `Acceptance OK (migrations applied + integration tests passed).`

如果失败：把 Jenkins 控制台中**第一条失败的完整 traceback**贴出来（通常足够定位）。

