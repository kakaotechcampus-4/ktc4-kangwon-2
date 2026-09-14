"""Monthly Template / Safety Legal Rule JSON Adapter 검증.

실제 승인 파일을 **읽기만** 하고 수정하지 않는다. 변형 케이스는 로드한 payload의
복사본을 메모리에서 바꿔 쓴다.
"""

from __future__ import annotations

import copy
import json

import pytest

from ssuksak.adapters.monthly_repositories import (
    DEFAULT_SAFETY_RULE_PATH,
    DEFAULT_TEMPLATE_PATH,
    InMemoryMonthlyPlanRepository,
    JsonMonthlyTemplateRepository,
    JsonSafetyLegalRuleRepository,
    MonthlyTemplateSchemaError,
    SafetyLegalRuleSchemaError,
    load_safety_legal_rule_from_dict,
    load_template_from_dict,
)
from ssuksak.planning.domain.monthly_template import DisplayMode, SectionRole

TEMPLATE_ID = "ssuksak.monthly-template-a"
TEMPLATE_VERSION = "monthly-template-a-v0.1.0"
SAFETY_VERSION = "child-welfare-act-decree-annex6-2022-06-21"


def template_payload() -> dict:
    return json.loads(DEFAULT_TEMPLATE_PATH.read_text(encoding="utf-8"))


def safety_payload() -> dict:
    return json.loads(DEFAULT_SAFETY_RULE_PATH.read_text(encoding="utf-8"))


# =================================================== Template Adapter


def test_loads_real_approved_template_file():
    template = JsonMonthlyTemplateRepository().get_template(
        TEMPLATE_ID, TEMPLATE_VERSION
    )
    assert template is not None
    assert template.template_ref.template_version == TEMPLATE_VERSION
    assert template.normative_status == "SAMPLE_DERIVED_NON_NORMATIVE"
    assert template.is_active is True
    assert [s.section_key for s in template.activated_sections] == [
        "theme",
        "week_axis",
        "outdoor_play",
        "safety_education",
    ]
    assert len(template.inactive_sections) == 8


def test_template_display_modes_are_preserved_from_file():
    template = load_template_from_dict(template_payload())
    by_key = {s.section_key: s for s in template.sections}
    assert by_key["theme"].display_mode is DisplayMode.MONTHLY_MERGED_SUMMARY
    assert by_key["outdoor_play"].display_mode is DisplayMode.WEEKLY_CELLS
    assert by_key["safety_education"].display_mode is DisplayMode.WEEKLY_CELLS
    assert by_key["week_axis"].role is SectionRole.AXIS
    assert by_key["week_axis"].display_mode is None
    assert by_key["emergency_response"].display_mode is None


def test_template_source_and_version_are_preserved():
    template = load_template_from_dict(template_payload())
    assert template.template_ref.template_id == TEMPLATE_ID
    assert template.hierarchy_max_depth == 2
    child = [s for s in template.sections if s.depth == 2]
    assert child and child[0].parent_section_key == "outdoor_play"


def test_unknown_template_version_returns_none():
    repo = JsonMonthlyTemplateRepository()
    assert repo.get_template(TEMPLATE_ID, "v9.9.9") is None
    assert repo.get_template("other.template", TEMPLATE_VERSION) is None


def test_pending_template_is_loaded_as_inactive():
    payload = template_payload()
    payload["review"]["domain_owner_approval"] = "PENDING_HUMAN_REVIEW"
    payload["review"]["runtime_active"] = False
    template = load_template_from_dict(payload)
    assert template.is_active is False


def test_runtime_active_mismatch_is_rejected():
    """수동 activation 우회를 차단한다."""
    payload = template_payload()
    payload["review"]["domain_owner_approval"] = "PENDING_HUMAN_REVIEW"
    payload["review"]["runtime_active"] = True  # 승인 없이 강제 활성화 시도
    with pytest.raises(MonthlyTemplateSchemaError, match="runtime_active"):
        load_template_from_dict(payload)


def test_runtime_active_false_while_approved_is_rejected():
    payload = template_payload()
    payload["review"]["runtime_active"] = False
    with pytest.raises(MonthlyTemplateSchemaError, match="runtime_active"):
        load_template_from_dict(payload)


@pytest.mark.parametrize(
    "path", [("template_version",), ("normative_status",), ("review",), ("sections",)]
)
def test_missing_required_template_field_is_rejected(path):
    payload = template_payload()
    del payload[path[0]]
    with pytest.raises(MonthlyTemplateSchemaError):
        load_template_from_dict(payload)


def test_active_content_section_without_display_mode_is_rejected():
    payload = template_payload()
    for s in payload["sections"]:
        if s["semantic_key"] == "outdoor_play":
            s["display_mode"] = None
    with pytest.raises(MonthlyTemplateSchemaError, match="display_mode"):
        load_template_from_dict(payload)


def test_unknown_display_mode_is_rejected():
    payload = template_payload()
    for s in payload["sections"]:
        if s["semantic_key"] == "outdoor_play":
            s["display_mode"] = "INLINE_OR_TAGGED"
    with pytest.raises(MonthlyTemplateSchemaError):
        load_template_from_dict(payload)


def test_global_display_mode_default_must_stay_null():
    payload = template_payload()
    payload["structure_rules"]["global_display_mode_default"] = "WEEKLY_CELLS"
    with pytest.raises(MonthlyTemplateSchemaError):
        load_template_from_dict(payload)


def test_pending_section_activation_is_not_silently_accepted():
    """PENDING Section을 활성화하면 display_mode가 없어 차단된다."""
    payload = template_payload()
    for s in payload["sections"]:
        if s["semantic_key"] == "drill":
            s["activated"] = True
    with pytest.raises(MonthlyTemplateSchemaError, match="drill"):
        load_template_from_dict(payload)


def test_depth_three_is_rejected():
    payload = template_payload()
    for s in payload["sections"]:
        if s["semantic_key"] == "drill":
            s["depth"] = 3
    with pytest.raises(MonthlyTemplateSchemaError):
        load_template_from_dict(payload)


def test_blank_template_version_is_rejected():
    payload = template_payload()
    payload["template_version"] = "   "
    with pytest.raises(MonthlyTemplateSchemaError):
        load_template_from_dict(payload)


# ===================================================== Safety Adapter


def test_loads_real_approved_safety_rule_file():
    rule = JsonSafetyLegalRuleRepository().get_legal_rule(SAFETY_VERSION)
    assert rule is not None
    assert rule.normative_status == "STATUTORY"
    assert rule.is_active is True
    assert rule.age_tier_label == "초등학교 취학 전"
    assert rule.placement_policy_version is None
    assert rule.has_placement_policy is False


def test_safety_rule_has_exactly_six_official_categories():
    rule = load_safety_legal_rule_from_dict(safety_payload())
    assert len(rule.categories) == 6
    assert [c.interval_months for c in rule.categories] == [6, 6, 3, 3, 6, 2]
    assert [c.annual_hours_min for c in rule.categories] == [4, 4, 10, 10, 6, 10]
    assert rule.annual_hours_min_total == 44


def test_safety_category_lookup():
    rule = load_safety_legal_rule_from_dict(safety_payload())
    traffic = rule.category("traffic_safety")
    assert traffic is not None
    assert traffic.official_label == "교통안전 교육"
    assert rule.category("생활안전") is None


def test_unknown_safety_rule_version_returns_none():
    assert JsonSafetyLegalRuleRepository().get_legal_rule("nope-v0") is None


def test_pending_safety_rule_is_loaded_as_inactive():
    payload = safety_payload()
    payload["review"]["domain_owner_approval"] = "PENDING_HUMAN_REVIEW"
    payload["review"]["runtime_active"] = False
    rule = load_safety_legal_rule_from_dict(payload)
    assert rule.is_active is False


def test_safety_runtime_active_mismatch_is_rejected():
    payload = safety_payload()
    payload["review"]["domain_owner_approval"] = "PENDING_HUMAN_REVIEW"
    payload["review"]["runtime_active"] = True
    with pytest.raises(SafetyLegalRuleSchemaError, match="runtime_active"):
        load_safety_legal_rule_from_dict(payload)


@pytest.mark.parametrize(
    "key", ["legal_rule_version", "normative_status", "review", "applicable_scope"]
)
def test_missing_required_legal_field_is_rejected(key: str):
    payload = safety_payload()
    del payload[key]
    with pytest.raises(SafetyLegalRuleSchemaError):
        load_safety_legal_rule_from_dict(payload)


def test_missing_interval_is_rejected():
    payload = safety_payload()
    del payload["categories"][0]["interval_months"]
    with pytest.raises(SafetyLegalRuleSchemaError):
        load_safety_legal_rule_from_dict(payload)


def test_missing_annual_hours_is_rejected():
    payload = safety_payload()
    del payload["categories"][2]["annual_hours_min"]
    with pytest.raises(SafetyLegalRuleSchemaError):
        load_safety_legal_rule_from_dict(payload)


def test_non_statutory_normative_status_is_rejected():
    payload = safety_payload()
    payload["normative_status"] = "SAMPLE_DERIVED_NON_NORMATIVE"
    with pytest.raises(SafetyLegalRuleSchemaError):
        load_safety_legal_rule_from_dict(payload)


def test_category_count_other_than_six_is_rejected():
    payload = safety_payload()
    payload["categories"] = payload["categories"][:5]
    with pytest.raises(SafetyLegalRuleSchemaError, match="6개"):
        load_safety_legal_rule_from_dict(payload)


def test_month_assignment_field_on_category_is_rejected():
    """법령 데이터에 배치성 필드가 생기면 차단한다."""
    payload = safety_payload()
    payload["categories"][0]["assigned_month"] = 4
    with pytest.raises(SafetyLegalRuleSchemaError, match="배치성 필드"):
        load_safety_legal_rule_from_dict(payload)


def test_has_month_assignment_true_is_rejected():
    payload = safety_payload()
    payload["month_assignment_policy"]["has_month_assignment"] = True
    with pytest.raises(SafetyLegalRuleSchemaError):
        load_safety_legal_rule_from_dict(payload)


def test_placement_policy_version_in_p0_is_rejected():
    """P0에서 제품 기본 배치 정책이 생기면 정책 위반으로 감지한다."""
    payload = safety_payload()
    payload["placement_policy_version"] = "placement-v1"
    with pytest.raises(SafetyLegalRuleSchemaError):
        load_safety_legal_rule_from_dict(payload)


def test_non_legal_label_in_categories_is_rejected():
    payload = safety_payload()
    payload["categories"][0]["official_label"] = "생활안전 교육"
    with pytest.raises(SafetyLegalRuleSchemaError, match="비법정"):
        load_safety_legal_rule_from_dict(payload)


def test_zero_interval_is_rejected():
    payload = safety_payload()
    payload["categories"][0]["interval_months"] = 0
    with pytest.raises(SafetyLegalRuleSchemaError):
        load_safety_legal_rule_from_dict(payload)


# =========================================== InMemory Monthly Repo


def test_in_memory_monthly_repository_tracks_save_count():
    repo = InMemoryMonthlyPlanRepository()
    assert repo.save_count == 0
    assert repo.stored_count == 0
    assert repo.get("none") is None
    assert repo.find_monthly("c", "2026-09") is None


# ============================================= 원본 파일 무수정 확인


def test_adapter_tests_do_not_modify_approved_files():
    """payload 변형은 메모리 복사본에서만 한다."""
    before_t = DEFAULT_TEMPLATE_PATH.read_bytes()
    before_s = DEFAULT_SAFETY_RULE_PATH.read_bytes()

    payload = template_payload()
    mutated = copy.deepcopy(payload)
    mutated["template_version"] = "mutated"
    load_template_from_dict(payload)

    assert DEFAULT_TEMPLATE_PATH.read_bytes() == before_t
    assert DEFAULT_SAFETY_RULE_PATH.read_bytes() == before_s
