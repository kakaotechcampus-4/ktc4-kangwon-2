"""Monthly Template Domain / Resolver 검증.

OD-M01이 확정한 것:
- 활성화·표시·계층·빈 값 정책의 결정 주체는 Template instance data다
- global display_mode default = 없음
- 활성 Section에 display_mode가 없으면 조용히 추정하지 않고 Gate 실패
- hierarchy max_depth = 2
- Template A는 SAMPLE_DERIVED_NON_NORMATIVE product adapter다

이 계층은 파일을 읽지 않는다. JSON Adapter는 후속 Slice다.
마지막 §drift 테스트만 승인된 JSON과의 어긋남을 감시한다.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from ssuksak.planning.domain.errors import FailureCategory, PlanningError
from ssuksak.planning.domain.monthly_template import (
    MAX_HIERARCHY_DEPTH,
    DisplayMode,
    EmptyValuePolicy,
    MonthlyTemplate,
    SectionRole,
    TemplateRef,
    TemplateSection,
)
from ssuksak.planning.rules import monthly_template_resolver as R

APPROVED_JSON = (
    pathlib.Path(__file__).resolve().parents[2]
    / "data" / "templates" / "monthly_template_a.json"
)

ACTIVE_KEYS = ("theme", "week_axis", "outdoor_play", "safety_education")
INACTIVE_KEYS = (
    "focus", "goals", "habits", "emergency_response",
    "drill", "indoor_alternative", "special_program", "event_schedule",
)
APPROVED_DISPLAY_MODES = {
    "theme": DisplayMode.MONTHLY_MERGED_SUMMARY,
    "outdoor_play": DisplayMode.WEEKLY_CELLS,
    "safety_education": DisplayMode.WEEKLY_CELLS,
    "focus": DisplayMode.WEEKLY_CELLS,
    "goals": DisplayMode.MONTHLY_MERGED_SUMMARY,
    "habits": DisplayMode.WEEKLY_CELLS,
}


def section(key: str, **over) -> TemplateSection:
    base = dict(
        section_key=key,
        role=SectionRole.CONTENT,
        activated=key in ACTIVE_KEYS,
        display_mode=APPROVED_DISPLAY_MODES.get(key),
        empty_value_policy=EmptyValuePolicy.RENDER_EMPTY_CELL,
    )
    base.update(over)
    return TemplateSection(**base)


def template_a(*, runtime_active: bool = True, sections=None) -> MonthlyTemplate:
    """승인된 monthly-template-a-v0.1.0과 동일한 구조를 Domain으로 구성한다."""
    if sections is None:
        sections = [
            section("theme"),
            section("week_axis", role=SectionRole.AXIS, display_mode=None),
            section("outdoor_play"),
            section("safety_education"),
            section("focus"),
            section("goals"),
            section("habits"),
            section("emergency_response", display_mode=None),
            section("drill", display_mode=None),
            section(
                "indoor_alternative",
                display_mode=None,
                parent_section_key="outdoor_play",
                depth=2,
            ),
            section("special_program", display_mode=None),
            section("event_schedule", display_mode=None),
        ]
    return MonthlyTemplate(
        template_ref=TemplateRef(
            "ssuksak.monthly-template-a", "monthly-template-a-v0.1.0"
        ),
        normative_status="SAMPLE_DERIVED_NON_NORMATIVE",
        sections=tuple(sections),
        runtime_active=runtime_active,
    )


# ------------------------------------------------ 전역 기본값 부재


def test_resolver_module_has_no_global_display_mode_default():
    """전역 기본값 상수가 존재하지 않는 것이 계약이다."""
    names = [n for n in dir(R) if "DEFAULT" in n.upper()]
    assert names == []
    src = pathlib.Path(R.__file__).read_text(encoding="utf-8")
    assert "DEFAULT_DISPLAY_MODE" not in src


def test_template_module_has_no_global_display_mode_default():
    import ssuksak.planning.domain.monthly_template as T

    assert not hasattr(T, "DEFAULT_DISPLAY_MODE")
    assert [n for n in dir(T) if "DEFAULT_DISPLAY" in n.upper()] == []


def test_active_section_without_display_mode_is_blocked():
    """조용히 추정하지 않는다."""
    tpl = template_a(
        sections=[
            section("theme"),
            section("outdoor_play", display_mode=None),
        ]
    )
    with pytest.raises(PlanningError) as exc:
        R.resolve_sections(tpl)
    assert exc.value.failure_category is FailureCategory.PREREQUISITE_GATE
    assert exc.value.violated_rule == "active_section_requires_explicit_display_mode"
    assert "outdoor_play" in str(exc.value)


def test_inactive_section_without_display_mode_is_allowed():
    """비활성 PENDING Section은 Gate를 막지 않는다."""
    resolved = R.resolve_sections(template_a())
    assert len(resolved) == 4


# --------------------------------------------------------- Resolver


def test_resolves_exactly_four_active_sections():
    resolved = R.resolve_sections(template_a())
    assert tuple(r.section_key for r in resolved) == ACTIVE_KEYS


def test_inactive_sections_are_excluded():
    resolved = R.resolve_sections(template_a())
    keys = {r.section_key for r in resolved}
    for key in INACTIVE_KEYS:
        assert key not in keys


def test_resolver_uses_template_display_mode_as_is():
    resolved = {r.section_key: r.display_mode for r in R.resolve_sections(template_a())}
    assert resolved["theme"] is DisplayMode.MONTHLY_MERGED_SUMMARY
    assert resolved["outdoor_play"] is DisplayMode.WEEKLY_CELLS
    assert resolved["safety_education"] is DisplayMode.WEEKLY_CELLS
    assert resolved["week_axis"] is None


def test_semantic_key_is_derived_without_week_position():
    resolved = R.resolve_sections(template_a())
    keys = [r.semantic_key.value for r in resolved]
    assert keys == [f"monthly.section.{k}" for k in ACTIVE_KEYS]
    assert all("week." not in k for k in keys)


def test_inactive_template_is_blocked():
    with pytest.raises(PlanningError) as exc:
        R.resolve_sections(template_a(runtime_active=False))
    assert exc.value.failure_category is FailureCategory.PREREQUISITE_GATE
    assert exc.value.violated_rule == "only_human_approved_template_instance_is_eligible"


# ----------------------------------------------------- Cell 개수 계산


def test_cell_count_by_display_mode():
    resolved = {r.section_key: r for r in R.resolve_sections(template_a())}
    assert resolved["theme"].cell_count_for(5) == 1
    assert resolved["week_axis"].cell_count_for(5) == 0
    assert resolved["outdoor_play"].cell_count_for(5) == 5
    assert resolved["safety_education"].cell_count_for(5) == 5


def test_expected_cell_count_for_september_2026():
    """theme 1 + week_axis 0 + outdoor 5 + safety 5 = 11"""
    resolved = R.resolve_sections(template_a())
    assert R.expected_cell_count(resolved, 5) == 11


def test_expected_cell_count_for_march_2026():
    """4주짜리 달에서는 theme 1 + outdoor 4 + safety 4 = 9"""
    resolved = R.resolve_sections(template_a())
    assert R.expected_cell_count(resolved, 4) == 9


# ---------------------------------------------------------- 계층


def test_max_depth_is_two():
    assert MAX_HIERARCHY_DEPTH == 2


def test_depth_three_is_rejected():
    with pytest.raises(ValueError, match="depth"):
        TemplateSection(
            section_key="deep",
            role=SectionRole.CONTENT,
            activated=False,
            depth=3,
            parent_section_key="indoor_alternative",
        )


def test_depth_two_requires_parent():
    with pytest.raises(ValueError, match="parent_section_key"):
        TemplateSection(
            section_key="child", role=SectionRole.CONTENT, activated=False, depth=2
        )


def test_depth_one_cannot_have_parent():
    with pytest.raises(ValueError, match="parent"):
        TemplateSection(
            section_key="root",
            role=SectionRole.CONTENT,
            activated=False,
            depth=1,
            parent_section_key="theme",
        )


def test_template_rejects_unknown_parent_reference():
    with pytest.raises(ValueError, match="parent_section_key가 Template에 없다"):
        template_a(
            sections=[
                section("theme"),
                section("orphan", display_mode=None, parent_section_key="nope", depth=2),
            ]
        )


def test_template_rejects_hierarchy_depth_over_two():
    with pytest.raises(ValueError, match="단 계층까지만"):
        MonthlyTemplate(
            template_ref=TemplateRef("t", "v"),
            normative_status="SAMPLE_DERIVED_NON_NORMATIVE",
            sections=(section("theme"),),
            hierarchy_max_depth=3,
        )


def test_parent_section_key_is_preserved_in_skeleton():
    tpl = template_a(
        sections=[
            section("outdoor_play"),
            section(
                "indoor_alternative",
                activated=True,
                display_mode=DisplayMode.WEEKLY_CELLS,
                parent_section_key="outdoor_play",
                depth=2,
            ),
        ]
    )
    skeleton = R.build_section_skeleton(tpl, R.resolve_sections(tpl))
    child = [s for s in skeleton if s.section_key == "indoor_alternative"][0]
    assert child.parent_section_key == "outdoor_play"


# ------------------------------------------------------ Section 골격


def test_skeleton_has_no_items():
    """Resolver는 구조만 만든다. Cell 채우기는 Generate의 몫이다."""
    tpl = template_a()
    skeleton = R.build_section_skeleton(tpl, R.resolve_sections(tpl))
    assert len(skeleton) == 4
    assert all(s.items == [] for s in skeleton)


def test_skeleton_carries_display_mode_and_empty_policy():
    tpl = template_a()
    skeleton = {s.section_key: s for s in R.build_section_skeleton(tpl, R.resolve_sections(tpl))}
    assert skeleton["theme"].display_mode is DisplayMode.MONTHLY_MERGED_SUMMARY
    assert (
        skeleton["safety_education"].empty_value_policy
        is EmptyValuePolicy.RENDER_EMPTY_CELL
    )


def test_axis_section_skeleton_has_no_display_mode():
    tpl = template_a()
    skeleton = {s.section_key: s for s in R.build_section_skeleton(tpl, R.resolve_sections(tpl))}
    assert skeleton["week_axis"].role is SectionRole.AXIS
    assert skeleton["week_axis"].display_mode is None


# --------------------------------------------------------- 기타 VO


def test_axis_section_cannot_declare_display_mode():
    with pytest.raises(ValueError, match="AXIS"):
        TemplateSection(
            section_key="week_axis",
            role=SectionRole.AXIS,
            activated=True,
            display_mode=DisplayMode.WEEKLY_CELLS,
        )


def test_duplicate_section_key_is_rejected():
    with pytest.raises(ValueError, match="중복"):
        template_a(sections=[section("theme"), section("theme")])


def test_empty_section_list_is_rejected():
    with pytest.raises(ValueError, match="하나 이상"):
        MonthlyTemplate(
            template_ref=TemplateRef("t", "v"),
            normative_status="SAMPLE_DERIVED_NON_NORMATIVE",
            sections=(),
        )


def test_display_mode_enum_is_extensible_not_closed():
    """두 값만이 영구적으로 전부라고 못 박지 않는다는 주석이 유지되는지."""
    import ssuksak.planning.domain.monthly_template as T

    src = pathlib.Path(T.__file__).read_text(encoding="utf-8")
    assert "영구적으로 전부라고 가정하지 않는다" in src
    assert {m.value for m in DisplayMode} == {
        "WEEKLY_CELLS",
        "MONTHLY_MERGED_SUMMARY",
    }


def test_template_ref_rejects_blank():
    with pytest.raises(ValueError):
        TemplateRef("", "v")


# ------------------------------------------- 승인 JSON drift 감시


def test_approved_template_json_matches_resolver_expectations():
    """승인된 monthly-template-a-v0.1.0과 Domain 기대가 어긋나면 실패한다.

    Adapter 테스트가 아니라 drift 감시다. JSON Adapter는 후속 Slice에서 만든다.
    """
    doc = json.loads(APPROVED_JSON.read_text(encoding="utf-8"))

    assert doc["template_version"] == "monthly-template-a-v0.1.0"
    assert doc["normative_status"] == "SAMPLE_DERIVED_NON_NORMATIVE"
    assert doc["review"]["domain_owner_approval"] == "HUMAN_APPROVED"
    assert doc["review"]["runtime_active"] is True
    assert doc["structure_rules"]["global_display_mode_default"] is None
    assert doc["structure_rules"]["hierarchy_max_depth"] == MAX_HIERARCHY_DEPTH
    assert doc["structure_rules"]["default_empty_value_policy"] == "RENDER_EMPTY_CELL"

    active = tuple(s["semantic_key"] for s in doc["sections"] if s["activated"])
    assert active == ACTIVE_KEYS

    inactive = {s["semantic_key"] for s in doc["sections"] if not s["activated"]}
    assert inactive == set(INACTIVE_KEYS)

    for s in doc["sections"]:
        expected = APPROVED_DISPLAY_MODES.get(s["semantic_key"])
        actual = s.get("display_mode")
        if expected is None:
            assert actual is None, s["semantic_key"]
        else:
            assert actual == expected.value, s["semantic_key"]

    assert "character_greeting" not in {s["semantic_key"] for s in doc["sections"]}
    assert max(s["depth"] for s in doc["sections"]) <= MAX_HIERARCHY_DEPTH


def test_approved_template_pending_sections_are_all_inactive():
    doc = json.loads(APPROVED_JSON.read_text(encoding="utf-8"))
    pending = set(doc["pending_decisions"][0]["sections"])
    inactive = {s["semantic_key"] for s in doc["sections"] if not s["activated"]}
    assert pending <= inactive, "PENDING Section이 활성이면 M1 blocker가 된다"
