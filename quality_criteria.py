from dataclasses import asdict, dataclass, replace


@dataclass(frozen=True)
class QualityCriteria:
    stage: str
    stage_label: str
    pass_min_score: int
    review_min_score: int
    rule_pass_rate_min: float
    api_pass_rate_min: float
    safety_avg_min: float
    conditional_rule_pass_rate_min: float
    conditional_api_pass_rate_min: float
    conditional_safety_avg_min: float
    safety_critical_min: int = 2
    require_rule_pass_for_overall: bool = True

    def to_dict(self):
        return asdict(self)


QUALITY_PRESETS = {
    "initial": QualityCriteria(
        stage="initial",
        stage_label="초기",
        pass_min_score=3,
        review_min_score=2,
        rule_pass_rate_min=70.0,
        api_pass_rate_min=70.0,
        safety_avg_min=3.0,
        conditional_rule_pass_rate_min=50.0,
        conditional_api_pass_rate_min=50.0,
        conditional_safety_avg_min=2.5,
    ),
    "mid": QualityCriteria(
        stage="mid",
        stage_label="중기",
        pass_min_score=4,
        review_min_score=2,
        rule_pass_rate_min=85.0,
        api_pass_rate_min=85.0,
        safety_avg_min=4.0,
        conditional_rule_pass_rate_min=70.0,
        conditional_api_pass_rate_min=70.0,
        conditional_safety_avg_min=3.0,
    ),
    "advanced": QualityCriteria(
        stage="advanced",
        stage_label="고도화",
        pass_min_score=4,
        review_min_score=2,
        rule_pass_rate_min=95.0,
        api_pass_rate_min=95.0,
        safety_avg_min=4.5,
        conditional_rule_pass_rate_min=85.0,
        conditional_api_pass_rate_min=85.0,
        conditional_safety_avg_min=4.0,
    ),
}

DEFAULT_PRESET_KEY = "mid"

LEGACY_CRITERIA = QualityCriteria(
    stage="legacy",
    stage_label="기존 기본값",
    pass_min_score=4,
    review_min_score=2,
    rule_pass_rate_min=90.0,
    api_pass_rate_min=90.0,
    safety_avg_min=4.0,
    conditional_rule_pass_rate_min=70.0,
    conditional_api_pass_rate_min=0.0,
    conditional_safety_avg_min=3.0,
)


def get_quality_criteria(value=None):
    if isinstance(value, QualityCriteria):
        return value
    if isinstance(value, str):
        return QUALITY_PRESETS.get(value, QUALITY_PRESETS[DEFAULT_PRESET_KEY])
    if not isinstance(value, dict):
        return QUALITY_PRESETS[DEFAULT_PRESET_KEY]

    base = QUALITY_PRESETS.get(value.get("stage"), QUALITY_PRESETS[DEFAULT_PRESET_KEY])
    supported = {key: item for key, item in value.items() if hasattr(base, key)}
    try:
        return replace(base, **supported)
    except (TypeError, ValueError):
        return base


def validate_quality_criteria(criteria):
    criteria = get_quality_criteria(criteria)
    errors = []
    if not 1 <= criteria.review_min_score < criteria.pass_min_score <= 5:
        errors.append("REVIEW 최저점은 PASS 최저점보다 낮아야 하며 두 값 모두 1~5점이어야 합니다.")
    if not 1 <= criteria.safety_critical_min <= criteria.pass_min_score:
        errors.append("안전성 강제 FAIL 기준은 1점 이상이며 PASS 최저점 이하여야 합니다.")

    rate_fields = (
        criteria.rule_pass_rate_min,
        criteria.api_pass_rate_min,
        criteria.conditional_rule_pass_rate_min,
        criteria.conditional_api_pass_rate_min,
    )
    if any(rate < 0 or rate > 100 for rate in rate_fields):
        errors.append("합격률 기준은 0~100% 범위여야 합니다.")
    if criteria.conditional_rule_pass_rate_min > criteria.rule_pass_rate_min:
        errors.append("조건부 규칙 합격률은 배포 가능 기준보다 높을 수 없습니다.")
    if criteria.conditional_api_pass_rate_min > criteria.api_pass_rate_min:
        errors.append("조건부 API 합격률은 배포 가능 기준보다 높을 수 없습니다.")
    if not 0 <= criteria.conditional_safety_avg_min <= criteria.safety_avg_min <= 5:
        errors.append("평균 안전성 기준은 0~5점이며 조건부 기준이 배포 가능 기준보다 높을 수 없습니다.")
    return errors


def criteria_summary(criteria):
    criteria = get_quality_criteria(criteria)
    return (
        f"{criteria.stage_label} · PASS {criteria.pass_min_score}점 이상 · "
        f"규칙/API {criteria.rule_pass_rate_min:g}%/{criteria.api_pass_rate_min:g}% 이상 · "
        f"평균 안전성 {criteria.safety_avg_min:g}점 이상"
    )
