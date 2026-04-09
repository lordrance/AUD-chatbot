"""协议常量：同意书版本号、各问卷 schema 版本、默认提示词包版本号（与 manifest 配合）。"""

# 参与者须在请求体中提交相同版本号，表示已阅读当前版本说明
CONSENT_DOCUMENT_VERSION = "2026-04-04-v1"

# 各 instrument 对应的问卷 schema 版本（写入 survey_responses.schema_version）
SURVEY_SCHEMA_CONSENT = "1"
SURVEY_SCHEMA_ELIGIBILITY = "2"
SURVEY_SCHEMA_BASELINE = "2"
SURVEY_SCHEMA_POST = "4"
SURVEY_SCHEMA_FOLLOWUP_7D = "1"

# 默认提示词包版本（仅版本号；完整引用由 manifest.bundle_id 拼接）
DEFAULT_PROMPT_BUNDLE_VERSION = "0.2.1"

# answer2.pdf：汇报用目标助手轮次区间（不等同于当前 FSM 用户轮数上限）
STUDY_TARGET_ASSISTANT_TURNS_MIN = 12
STUDY_TARGET_ASSISTANT_TURNS_MAX = 16

# 默认 LLM 通道标签（真实值以每次调用写入 llm_calls.api_type 为准）
LLM_API_TYPE_LABEL = "responses_primary"
