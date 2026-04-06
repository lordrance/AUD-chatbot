# 知情同意书版本管理

## 单一事实来源

- **版本号常量**：`apps/api/app/constants.py` 中的 `CONSENT_DOCUMENT_VERSION`（例：`2026-04-04-v1`）。
- **正文文件（双路径，内容应保持一致）**：
  - 仓库：`docs/consent/body_<版本>.md`（例：`docs/consent/body_2026-04-04-v1.md`）；
  - Docker / 仅部署 `apps/api` 时：镜像内使用 **`apps/api/consent_documents/body_<版本>.md`**（与上一路径同步更新）。
- **运行时加载**：`app/services/consent_document.py` 按 `settings.consent_document_version`（默认来自上述常量，可用环境变量覆盖）读取对应文件。
- **公开 API**：`GET /api/v1/consent-document` 返回 `{ consent_document_version, format, body }`，供前端展示全文。

## 更新流程（研究团队）

1. 取得 IRB / 伦理委员会对**新文本**的批件。
2. 在 `docs/consent/` 下新增 `body_<新版本>.md`（勿覆盖旧版文件，便于追溯）。
3. 将 `CONSENT_DOCUMENT_VERSION` 改为新版本字符串，并保留与文件名一致。
4. 部署后：已被旧版版本号接受但未完成的会话，其 `consent_document_version` 字段仍指向旧版；**新会话**必须从 `GET /state` 读取 `expected_consent_version` 并提交匹配版本（现有 `POST /consent` 校验逻辑）。
5. 在修订说明 / 研究记录中注明生效日期与批件编号。

## 开发/试点注意

- 当前正文可能含 **占位** 段落；**正式收集数据前**须替换为终稿。
- 前端 `ConsentPage` 应展示 `GET /consent-document` 的正文，而非仅摘要（摘要可作为辅助，但全文源必须一致）。
