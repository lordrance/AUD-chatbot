"""资格筛查：AUDIT-C 阈值与纳入判定（无数据库访问）。"""

from app.schemas.flow import EligibilityResult, EligibilitySubmit


def audit_c_threshold_for_sex(sex_at_birth: str) -> int:
    """WHO AUDIT-C 常用切分：男性 ≥4，女性 ≥3；其他按较严一侧（3）。"""
    if sex_at_birth == "male":
        return 4
    return 3


def evaluate_eligibility(body: EligibilitySubmit) -> EligibilityResult:
    """根据年龄、AUDIT-C 总分阈值与减量意愿计算是否纳入及原因码列表。"""
    reasons: list[str] = []
    if body.age_years < 18:
        reasons.append("age_below_18")

    total = body.audit_c_frequency + body.audit_c_typical_quantity + body.audit_c_binge
    threshold = audit_c_threshold_for_sex(body.sex_at_birth)
    if total < threshold:
        reasons.append("audit_c_below_threshold")

    if not body.wants_to_reduce_drinking:
        reasons.append("no_intention_to_reduce")

    passed = len(reasons) == 0
    return EligibilityResult(
        passed=passed,
        audit_c_total=total,
        audit_c_threshold=threshold,
        reasons=reasons,
    )
