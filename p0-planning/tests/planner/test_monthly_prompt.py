"""Monthly Planner Prompt / Context Rendering (L4).

Prompt가 **무엇을 반드시 담고 무엇을 절대 담지 않는지**를 고정한다.
Prompt 문구를 통째로 exact match하지 않는다(CLAUDE.md §20) — 계약 요소만 본다.
"""

from __future__ import annotations

import datetime

import pytest

from ssuksak.ingestion.models import (
    AgeEvidenceType,
    EvidenceRecord,
    EvidenceSourceType,
    ExtractionQuality,
    MachineReadability,
    ReusePolicy,
    Setting,
    SourceSection,
)
from ssuksak.planning.context import (
    MonthlyContextPacketBuilder,
    MonthlyContextRequest,
    packet_fingerprint,
)
from ssuksak.planning.domain.identifiers import PeriodKey
from ssuksak.planning.domain.parent_lineage import ParentYearlyLineage
from ssuksak.planning.planner import (
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    build_monthly_planner_request,
    render_planning_input,
)
from ssuksak.planning.retrieval import (
    InMemoryInstitutionEvidenceRepository,
    MonthlyEvidenceRetriever,
)

SUMMER = "여름"


def rec(
    rid: str,
    *,
    institution: str = "가어린이집",
    text: str = "모래놀이",
    section: SourceSection = SourceSection.OUTDOOR_PLAY,
    setting: Setting = Setting.OUTDOOR,
    ages: tuple[int, ...] = (4,),
    sha: str | None = None,
    page: int = 1,
) -> EvidenceRecord:
    is_exp = section is SourceSection.WEEK_EXPERIENCE
    return EvidenceRecord(
        record_id=rid,
        source_type=EvidenceSourceType.INSTITUTION_SAMPLE,
        source_path=f"references/samples/monthly/{institution}.pdf",
        source_sha256=(sha or institution.encode().hex().ljust(64, "0"))[:64],
        page=page,
        institution_id=institution,
        month=7,
        age_scope=ages,
        age_evidence_type=AgeEvidenceType.SINGLE_AGE_PAGE,
        monthly_theme=SUMMER,
        source_section=section,
        source_label="바깥놀이",
        experience_text=text if is_exp else None,
        activity_text=None if is_exp else text,
        setting=setting,
        machine_readability=MachineReadability.TEXT_LAYER,
        reuse_policy=ReusePolicy.CONTEXT_ONLY,
        extraction_quality=ExtractionQuality.VALID,
        extraction_method="table_line_geometry_v1",
    )


@pytest.fixture
def packet():
    records = [
        rec("ev_1", institution="가어린이집", text="여름 물놀이 하기"),
        rec("ev_2", institution="나어린이집", text="여름 곤충 찾기"),
        rec("ev_3", institution="다어린이집", text="그늘에서 쉬기",
            section=SourceSection.WEEK_EXPERIENCE),
        rec("ev_4", ages=(3,), institution="가어린이집", page=2, text="여름 꽃 보기"),
    ]
    store = InMemoryInstitutionEvidenceRepository(records).get_store()
    builder = MonthlyContextPacketBuilder(MonthlyEvidenceRetriever(store), store)
    return builder.build(
        MonthlyContextRequest(
            school_year="2026",
            target_month=PeriodKey("2026-07"),
            classroom_ages=(4,),
            age_mode="SINGLE",
            parent_lineage=ParentYearlyLineage(
                parent_yearly_plan_id="yp_1",
                parent_yearly_period_key="2026-07",
                parent_yearly_theme_id="yr_theme_summer",
                parent_yearly_value=SUMMER,
                reference_catalog_id="ssuksak.theme-reference",
                reference_version="theme-reference-v0",
                confirmed_at=datetime.datetime(2026, 2, 1, tzinfo=datetime.UTC),
                confirmed_by="actor_1",
            ),
            daycare_ref="dc_secret_1",
            classroom_ref="cr_secret_1",
        )
    )


# ============================================== 반드시 담는 것


def test_theme_is_in_the_prompt(packet):
    text = render_planning_input(packet)
    assert "yr_theme_summer" in text
    assert SUMMER in text


def test_every_week_id_is_in_the_prompt(packet):
    text = render_planning_input(packet)
    for slot in packet.week_slots:
        assert slot.week_id in text


def test_context_only_rule_is_in_the_prompt(packet):
    """재사용 정책이 Prompt에서 사라지면 Contract가 사라진다."""
    text = render_planning_input(packet) + SYSTEM_PROMPT
    assert "그대로 옮겨 적" in text
    assert "참고 전용" in text


def test_safety_generation_is_forbidden_in_the_prompt(packet):
    text = render_planning_input(packet) + SYSTEM_PROMPT
    assert "안전교육" in text
    assert "배치하지" in text


def test_official_claim_is_forbidden_in_the_prompt(packet):
    text = render_planning_input(packet) + SYSTEM_PROMPT
    assert "법령" in text or "법적" in text
    assert "공식" in text


def test_allowed_origins_are_in_the_prompt(packet):
    text = render_planning_input(packet)
    assert "REFERENCE" in text
    assert "LLM_SYNTHESIZED" in text
    assert "CORPUS_EVIDENCE" not in text


def test_evidence_refs_are_in_the_prompt(packet):
    text = render_planning_input(packet)
    refs = build_monthly_planner_request(packet).valid_grounding_refs
    assert refs
    for ref in refs:
        assert f"[{ref}]" in text


def test_age_context_is_in_the_prompt(packet):
    text = render_planning_input(packet)
    assert packet.age_context.overall_strength.value in text
    assert "단일연령 근거" in text


def test_low_single_age_grounding_adds_an_explicit_caution(packet):
    assert packet.age_context.single_age_grounding_count <= 2
    assert "크게 말하지 마세요" in render_planning_input(packet)


def test_system_prompt_asks_for_a_whole_month_flow():
    assert "한 달 전체의 흐름" in SYSTEM_PROMPT
    assert "하나씩 따로 뽑지 마세요" in SYSTEM_PROMPT


def test_system_prompt_forbids_copying_at_the_decision_point():
    """v0.1.1에서 옮긴 지점. 금지 문구가 판단하는 자리에 있어야 한다."""
    synthesized_section = SYSTEM_PROMPT.split("**LLM_SYNTHESIZED**")[1]
    assert "그대로 옮겨 적으면 안 됩니다" in synthesized_section


# ============================================== 절대 담지 않는 것


@pytest.mark.parametrize(
    "token",
    ["source_sha256", "rank_score", "retrieval_tier", "source_diversity_group",
     "source_path", "references/samples"],
)
def test_audit_only_fields_never_reach_the_prompt(packet, token):
    assert token not in render_planning_input(packet)


def test_institution_names_never_reach_the_prompt(packet):
    text = render_planning_input(packet)
    for name in ("가어린이집", "나어린이집", "다어린이집"):
        assert name not in text


def test_internal_refs_never_reach_the_prompt(packet):
    text = render_planning_input(packet)
    assert "dc_secret_1" not in text
    assert "cr_secret_1" not in text
    assert "ev_1" not in text


def test_packet_fingerprint_is_not_in_the_prompt(packet):
    """감사용 값이다. 모델에게 줄 이유가 없다."""
    assert packet_fingerprint(packet) not in render_planning_input(packet)


# ============================================== Request 조립


def test_request_carries_the_packet_anchors(packet):
    request = build_monthly_planner_request(packet)
    assert request.prompt_version == PROMPT_VERSION
    assert request.expected_theme_id == packet.parent_theme.theme_id
    assert request.expected_week_ids == tuple(w.week_id for w in packet.week_slots)
    assert request.packet_fingerprint == packet_fingerprint(packet)


def test_request_collects_every_ref_from_every_block(packet):
    request = build_monthly_planner_request(packet)
    expected = {i.ref for i in packet.institution_evidence}
    expected |= {i.ref for i in packet.other_outdoor_evidence}
    expected |= {c.ref for c in packet.week_experience_candidates}
    expected |= {
        i.ref
        for g in packet.age_contrast_evidence
        for o in g.observations
        for i in o.items
    }
    assert request.valid_grounding_refs == frozenset(expected)


def test_reference_labels_come_from_the_packet(packet):
    request = build_monthly_planner_request(packet)
    assert request.reference_labels == {
        a.activity_id: a.label for a in packet.reference_activities
    }


def test_rendering_is_deterministic(packet):
    assert render_planning_input(packet) == render_planning_input(packet)


def test_rendering_is_much_smaller_than_the_canonical_json(packet):
    """JSON을 그대로 붓지 않는 이유를 수치로 고정한다."""
    from ssuksak.planning.context import measure

    assert len(render_planning_input(packet)) < measure(packet).planner_visible_chars
