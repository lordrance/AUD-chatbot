"""协议常量：同意书版本号、各问卷 schema 版本、默认提示词包版本号（与 manifest 配合）。"""

# 参与者须在请求体中提交相同版本号，表示已阅读当前版本说明
CONSENT_DOCUMENT_VERSION = "2026-04-04-v1"

# 各 instrument 对应的问卷 schema 版本（写入 survey_responses.schema_version）
SURVEY_SCHEMA_CONSENT = "1"
SURVEY_SCHEMA_ELIGIBILITY = "1"
SURVEY_SCHEMA_BASELINE = "1"
SURVEY_SCHEMA_POST = "2"
SURVEY_SCHEMA_FOLLOWUP_7D = "1"

# 默认提示词包版本（仅版本号；完整引用由 manifest.bundle_id 拼接）
DEFAULT_PROMPT_BUNDLE_VERSION = "0.2.1"
