"""Monthly Proposal Deterministic Validator (L5).

In-Memory Packet으로 규칙을 고정한다. 실제 Artifact와 L4 실측 결함 검증은
`test_monthly_validator_l4_defects.py`에 따로 둔다.

**LLM을 호출하지 않는다.** Validator 자체가 LLM을 쓰지 않으며 테스트도 쓰지 않는다.
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
from ssuksak.planning.planner import build_monthly_planner_request
from ssuksak.planning.retrieval import (
    InMemoryInstitutionEvidenceRepository,
    MonthlyEvidenceRetriever,
)
from ssuksak.planning.rules.monthly_llm_validation import (
    GENERATION_METHOD,
    PLANNER_RULE_ID,
    WEEK_ORDER_BASIS,
    ProposalViolationCode,
    build_packet_index,
    validate_monthly_proposal,
)
from ssuksak.shared.llm.monthly import (
    MonthlyPlanProposal,
    ProposedActivity,
    ProposedActivityOrigin,
    ProposedWeek,
)

SUMMER = "여름"
THEME_ID = "yr_theme_summer"
MODEL = "openai/gpt-4.1-mini"

SOURCE_TEXTS = {
    "ev_1": "여름 물놀이 하기",
    "ev_2": "여름 곤충 찾기",
    "ev_3": "그늘에서 쉬기",
    "ev_4": "여름 꽃 보기",
}


def rec(
    rid: str,
    *,
    institution: str = "가어린이집",
    text: str = "모래놀이",
    section: SourceSection = SourceSection.OUTDOOR_PLAY,
    setting: Setting = Setting.OUTDOOR,
    ages: tuple[int, ...] = (4,),
    page: int = 1,
) -> EvidenceRecord:
    is_exp = section is SourceSection.WEEK_EXPERIENCE
    return EvidenceRecord(
        record_id=rid,
        source_type=EvidenceSourceType.INSTITUTION_SAMPLE,
        source_path=f"references/samples/monthly/{institution}.pdf",
        source_sha256=institution.encode().hex().ljust(64, "0")[:64],
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


def build_packet(records=None, *, ages: tuple[int, ...] = (4,)):
    if records is None:
        records = [
            rec("ev_1", institution="가어린이집", text=SOURCE_TEXTS["ev_1"]),
            rec("ev_2", institution="나어린이집", text=SOURCE_TEXTS["ev_2"]),
            rec("ev_3", institution="다어린이집", text=SOURCE_TEXTS["ev_3"],
                section=SourceSection.WEEK_EXPERIENCE),
            rec("ev_4", institution="가어린이집", page=2, ages=(3,),
                text=SOURCE_TEXTS["ev_4"]),
        ]
    store = InMemoryInstitutionEvidenceRepository(records).get_store()
    builder = MonthlyContextPacketBuilder(MonthlyEvidenceRetriever(store), store)
    return builder.build(
        MonthlyContextRequest(
            school_year="2026",
            target_month=PeriodKey("2026-07"),
            classroom_ages=ages,
            age_mode="SINGLE" if len(ages) == 1 else "MIXED",
            parent_lineage=ParentYearlyLineage(
                parent_yearly_plan_id="yp_1",
                parent_yearly_period_key="2026-07",
                parent_yearly_theme_id=THEME_ID,
                parent_yearly_value=SUMMER,
                reference_catalog_id="ssuksak.theme-reference",
                reference_version="theme-reference-v0",
                confirmed_at=datetime.datetime(2026, 2, 1, tzinfo=datetime.UTC),
                confirmed_by="actor_1",
            ),
        )
    )


@pytest.fixture
def packet():
    return build_packet()


def synthesized(value: str, refs: list[str]) -> ProposedActivity:
    return ProposedActivity(
        value=value,
        origin=ProposedActivityOrigin.LLM_SYNTHESIZED,
        reference_activity_id=None,
        grounding_refs=refs,
    )


def week(
    packet, ordinal: int, *, activity, experience: str | None = None
) -> ProposedWeek:
    slot = packet.week_slots[ordinal - 1]
    return ProposedWeek(
        week_id=slot.week_id,
        experience=experience or f"{ordinal}주차 여름 경험을 나눠요.",
        activity=activity,
    )


def any_ref(packet, *, ages: tuple[int, ...] = (4,)) -> str:
    """요청 연령과 어긋나지 않는 근거 참조.

    아무 ref나 고르면 `GROUNDING_AGE_MISMATCH`가 끼어들어 다른 규칙을 검증할 수
    없다. 연령 규칙 자체는 전용 테스트에서 본다.
    """
    index = build_packet_index(packet)
    for ref in sorted(index.by_ref):
        grounded = index.by_ref[ref]
        if grounded.single_age is None or grounded.single_age in ages:
            return ref
    raise AssertionError("요청 연령에 맞는 근거가 Packet에 없다")


def proposal(packet, weeks) -> MonthlyPlanProposal:
    return MonthlyPlanProposal(
        theme_id=THEME_ID,
        month_flow_rationale="관심에서 표현으로 이어지도록 구성했습니다.",
        weeks=weeks,
    )


def clean_weeks(packet) -> list[ProposedWeek]:
    ref = any_ref(packet)
    return [
        week(packet, i + 1, activity=synthesized(f"새로 만든 여름 놀이 {i + 1}", [ref]))
        for i in range(len(packet.week_slots))
    ]


def validate(packet, prop, *, model: str = MODEL, request=None):
    return validate_monthly_proposal(
        prop, packet, request or build_monthly_planner_request(packet),
        planner_model=model,
    )


# ============================================== 정상 통과


def test_a_clean_proposal_is_valid(packet):
    result = validate(packet, proposal(packet, clean_weeks(packet)))
    assert result.is_valid, [str(v) for v in result.violations]
    assert result.violations == ()


def test_a_clean_proposal_resolves_provenance(packet):
    result = validate(packet, proposal(packet, clean_weeks(packet)))
    assert result.generation_method == GENERATION_METHOD
    assert result.rule_id == PLANNER_RULE_ID
    assert result.week_order_basis == WEEK_ORDER_BASIS
    assert result.planner_model == MODEL
    assert result.packet_fingerprint == packet_fingerprint(packet)
    assert len(result.provenance) == len(packet.week_slots)
    for draft in result.provenance:
        assert draft.is_complete
        assert draft.grounding_source_ids


def test_grounding_refs_resolve_to_real_record_ids(packet):
    result = validate(packet, proposal(packet, clean_weeks(packet)))
    resolved = {i for d in result.provenance for i in d.grounding_source_ids}
    assert resolved <= set(SOURCE_TEXTS)


# ============================================== Exact copy (핵심)


@pytest.mark.parametrize(
    "value",
    [
        "여름 물놀이 하기",
        "여름 물놀이  하기",
        " 여름 물놀이 하기 ",
        "여름 물놀이 하기.",
        "「여름 물놀이 하기」",
    ],
)
def test_synthesized_copying_a_context_only_source_is_rejected(packet, value):
    ref = any_ref(packet)
    weeks = clean_weeks(packet)
    weeks[0] = week(packet, 1, activity=synthesized(value, [ref]))
    result = validate(packet, proposal(packet, weeks))
    assert ProposalViolationCode.SYNTHESIZED_EXACT_SOURCE_COPY in result.codes


def test_copy_detection_does_not_depend_on_the_declared_grounding_ref(packet):
    """ref를 엉뚱하게 달아도 복사를 놓치지 않는다 (§7)."""
    index = build_packet_index(packet)
    copied = next(
        g for g in index.by_ref.values() if g.text == SOURCE_TEXTS["ev_2"]
    )
    other = next(r for r in sorted(index.by_ref) if r != copied.ref)
    weeks = clean_weeks(packet)
    weeks[0] = week(packet, 1, activity=synthesized(copied.text, [other]))
    result = validate(packet, proposal(packet, weeks))
    assert ProposalViolationCode.SYNTHESIZED_EXACT_SOURCE_COPY in result.codes


def test_a_genuinely_new_wording_passes(packet):
    weeks = clean_weeks(packet)
    weeks[0] = week(
        packet, 1,
        activity=synthesized("물을 뿌리며 시원함을 느껴요", [any_ref(packet)]),
    )
    result = validate(packet, proposal(packet, weeks))
    assert ProposalViolationCode.SYNTHESIZED_EXACT_SOURCE_COPY not in result.codes


def test_copy_detection_covers_week_experience_sources(packet):
    """Institution뿐 아니라 주차 경험 관찰 텍스트도 비교 대상이다."""
    index = build_packet_index(packet)
    experience_text = next(
        g for g in index.by_ref.values()
        if g.block == "week_experience_candidates"
    )
    weeks = clean_weeks(packet)
    weeks[0] = week(
        packet, 1, activity=synthesized(experience_text.text, [any_ref(packet)])
    )
    result = validate(packet, proposal(packet, weeks))
    assert ProposalViolationCode.SYNTHESIZED_EXACT_SOURCE_COPY in result.codes


def test_duplicate_source_text_yields_one_violation():
    """같은 문장이 두 record로 들어 있어도 Violation은 하나다 (L4 §14.4)."""
    records = [
        rec("ev_1", institution="가어린이집", text="물놀이를 가요"),
        rec("ev_2", institution="나어린이집", text="물놀이를 가요"),
        rec("ev_3", institution="다어린이집", text="여름 곤충 찾기"),
    ]
    packet = build_packet(records)
    weeks = clean_weeks(packet)
    weeks[0] = week(packet, 1, activity=synthesized("물놀이를 가요", [any_ref(packet)]))
    result = validate(packet, proposal(packet, weeks))
    copies = [
        v for v in result.violations
        if v.code is ProposalViolationCode.SYNTHESIZED_EXACT_SOURCE_COPY
    ]
    assert len(copies) == 1
    assert "E0" in copies[0].detail


# ============================================== REFERENCE 오탐 없음


def test_reference_using_the_catalog_label_verbatim_is_accepted():
    """승인 label을 글자 그대로 쓰는 것은 정상이다 (§8)."""
    from ssuksak.adapters.json_activity_reference_repository import (
        production_activity_reference_repository,
    )
    from ssuksak.planning.retrieval import DEFAULT_EVIDENCE_STORE_PATH

    if not DEFAULT_EVIDENCE_STORE_PATH.exists():
        pytest.skip("Evidence Store 미빌드")

    catalog = production_activity_reference_repository().get_catalog(
        "ssuksak.outdoor-activity-reference", "activity-reference-v0.2.1"
    )
    store = InMemoryInstitutionEvidenceRepository(
        [rec("ev_1", text="여름 물놀이 하기")]
    ).get_store()
    builder = MonthlyContextPacketBuilder(
        MonthlyEvidenceRetriever(store, activity_catalog=catalog),
        store,
        activity_catalog=catalog,
    )
    packet = builder.build(
        MonthlyContextRequest(
            school_year="2026", target_month=PeriodKey("2026-07"),
            classroom_ages=(4,), age_mode="SINGLE",
            parent_lineage=ParentYearlyLineage(
                parent_yearly_plan_id="yp_1", parent_yearly_period_key="2026-07",
                parent_yearly_theme_id=THEME_ID, parent_yearly_value=SUMMER,
                reference_catalog_id="ssuksak.theme-reference",
                reference_version="theme-reference-v0",
                confirmed_at=datetime.datetime(2026, 2, 1, tzinfo=datetime.UTC),
                confirmed_by="a",
            ),
        )
    )
    candidates = packet.reference_activities[: len(packet.week_slots)]
    assert len(candidates) == len(packet.week_slots)
    weeks = [
        week(
            packet, i + 1,
            activity=ProposedActivity(
                value=c.label, origin=ProposedActivityOrigin.REFERENCE,
                reference_activity_id=c.activity_id, grounding_refs=[],
            ),
        )
        for i, c in enumerate(candidates)
    ]
    result = validate(packet, proposal(packet, weeks))
    assert result.is_valid, [str(v) for v in result.violations]


def test_reference_not_in_the_packet_is_rejected(packet):
    weeks = clean_weeks(packet)
    weeks[0] = week(
        packet, 1,
        activity=ProposedActivity(
            value="지어낸 활동", origin=ProposedActivityOrigin.REFERENCE,
            reference_activity_id="act_invented", grounding_refs=[],
        ),
    )
    result = validate(packet, proposal(packet, weeks))
    # L4 reconcile이 먼저 잡는다. 계약 위반으로 전달되면 그것으로 충분하다.
    assert not result.is_valid
    assert result.codes[0] in (
        ProposalViolationCode.BASIC_CONTRACT_VIOLATION,
        ProposalViolationCode.REFERENCE_NOT_IN_PACKET,
    )


# ============================================== 중복


def test_duplicate_reference_activity_is_rejected(packet):
    ref = any_ref(packet)
    weeks = clean_weeks(packet)
    weeks[1] = week(
        packet, 2, activity=synthesized(weeks[0].activity.value, [ref]),
        experience="다른 경험 문장입니다.",
    )
    result = validate(packet, proposal(packet, weeks))
    assert ProposalViolationCode.DUPLICATE_ACTIVITY in result.codes


def test_duplicate_activity_ignores_cosmetic_differences(packet):
    ref = any_ref(packet)
    weeks = clean_weeks(packet)
    weeks[1] = week(
        packet, 2,
        activity=synthesized(f"{weeks[0].activity.value} ", [ref]),
        experience="다른 경험 문장입니다.",
    )
    result = validate(packet, proposal(packet, weeks))
    assert ProposalViolationCode.DUPLICATE_ACTIVITY in result.codes


def test_duplicate_experience_is_rejected(packet):
    weeks = clean_weeks(packet)
    same = weeks[0].experience
    weeks[1] = week(packet, 2, activity=weeks[1].activity, experience=same)
    result = validate(packet, proposal(packet, weeks))
    assert ProposalViolationCode.DUPLICATE_EXPERIENCE in result.codes


def test_different_experiences_pass(packet):
    result = validate(packet, proposal(packet, clean_weeks(packet)))
    assert ProposalViolationCode.DUPLICATE_EXPERIENCE not in result.codes


# ============================================== Claim / Safety / 누출


@pytest.mark.parametrize("field_index", [0, 1])
def test_official_claim_in_visible_text_is_rejected(packet, field_index):
    weeks = clean_weeks(packet)
    if field_index == 0:
        weeks[0] = week(
            packet, 1, activity=weeks[0].activity,
            experience="공식 권장 순서를 따랐습니다.",
        )
        prop = proposal(packet, weeks)
    else:
        prop = MonthlyPlanProposal(
            theme_id=THEME_ID,
            month_flow_rationale="누리과정에서 반드시 다루어야 하는 순서입니다.",
            weeks=weeks,
        )
    result = validate(packet, prop)
    assert ProposalViolationCode.FORBIDDEN_OFFICIAL_CLAIM in result.codes


def test_safety_education_generation_is_rejected(packet):
    weeks = clean_weeks(packet)
    weeks[0] = week(
        packet, 1, activity=weeks[0].activity,
        experience="이번 주 안전교육은 교통안전입니다.",
    )
    result = validate(packet, proposal(packet, weeks))
    assert ProposalViolationCode.SAFETY_CONTENT_LEAKAGE in result.codes


def test_normal_playground_safety_wording_is_not_rejected(packet):
    weeks = clean_weeks(packet)
    weeks[0] = week(
        packet, 1, activity=weeks[0].activity,
        experience="안전 약속을 지키며 놀이터를 이용해요.",
    )
    result = validate(packet, proposal(packet, weeks))
    assert ProposalViolationCode.SAFETY_CONTENT_LEAKAGE not in result.codes


@pytest.mark.parametrize("leak", ["E01 근거를 참고했어요", "출처 S1 사례예요", "가어린이집 사례예요"])
def test_identifier_leakage_in_visible_text_is_rejected(packet, leak):
    weeks = clean_weeks(packet)
    weeks[0] = week(packet, 1, activity=weeks[0].activity, experience=leak)
    result = validate(packet, proposal(packet, weeks))
    assert ProposalViolationCode.SOURCE_IDENTIFIER_LEAKAGE in result.codes


def test_grounding_refs_metadata_is_not_treated_as_leakage(packet):
    """`grounding_refs=["E01"]`은 정상이다. 검사 대상이 아니다."""
    result = validate(packet, proposal(packet, clean_weeks(packet)))
    assert ProposalViolationCode.SOURCE_IDENTIFIER_LEAKAGE not in result.codes


def test_rationale_is_also_scanned(packet):
    prop = MonthlyPlanProposal(
        theme_id=THEME_ID,
        month_flow_rationale="가어린이집 사례를 참고해 구성했습니다.",
        weeks=clean_weeks(packet),
    )
    result = validate(packet, prop)
    leaks = [
        v for v in result.violations
        if v.code is ProposalViolationCode.SOURCE_IDENTIFIER_LEAKAGE
    ]
    assert leaks and leaks[0].field == "month_flow_rationale"


# ============================================== Grounding


def test_unknown_grounding_ref_is_rejected(packet):
    weeks = clean_weeks(packet)
    weeks[0] = week(packet, 1, activity=synthesized("새 놀이", ["E99"]))
    result = validate(packet, proposal(packet, weeks))
    assert not result.is_valid
    assert result.codes[0] in (
        ProposalViolationCode.BASIC_CONTRACT_VIOLATION,
        ProposalViolationCode.INVALID_GROUNDING_REF,
    )


def test_grounding_only_from_other_single_ages_is_rejected(packet):
    """만4세 요청인데 만3세 단일연령 근거만 참조한 경우 (§21).

    기본 Packet은 같은 문서(가어린이집)의 만4세 면과 만3세 면을 함께 담으므로
    연령 대조 Block을 통해 만3세 근거가 Planner에게 전달된다.
    """
    index = build_packet_index(packet)
    age3_refs = [g.ref for g in index.by_ref.values() if g.age_scope == (3,)]
    assert age3_refs, "Fixture가 만3세 근거를 담지 못했다 — 규칙이 검증되지 않는다"

    weeks = clean_weeks(packet)
    weeks[0] = week(packet, 1, activity=synthesized("새 여름 놀이", age3_refs))
    result = validate(packet, proposal(packet, weeks))
    assert ProposalViolationCode.GROUNDING_AGE_MISMATCH in result.codes

    mismatch = next(
        v for v in result.violations
        if v.code is ProposalViolationCode.GROUNDING_AGE_MISMATCH
    )
    assert "만3세" in mismatch.detail


def test_grounding_from_the_requested_age_is_accepted(packet):
    index = build_packet_index(packet)
    age4_refs = [g.ref for g in index.by_ref.values() if g.age_scope == (4,)]
    assert age4_refs
    weeks = clean_weeks(packet)
    weeks[0] = week(packet, 1, activity=synthesized("새 여름 놀이", age4_refs))
    result = validate(packet, proposal(packet, weeks))
    assert ProposalViolationCode.GROUNDING_AGE_MISMATCH not in result.codes


def test_mixed_age_grounding_is_not_an_age_mismatch():
    """혼합연령·연령 미상 근거가 섞이면 판단하지 않는다."""
    records = [
        rec("ev_mix", institution="가어린이집", text="여름 물놀이 하기",
            ages=(3, 4, 5)),
        rec("ev_a3", institution="나어린이집", text="여름 꽃 보기", ages=(3,)),
    ]
    packet = build_packet(records, ages=(4,))
    index = build_packet_index(packet)
    refs = sorted(index.by_ref)
    weeks = clean_weeks(packet)
    weeks[0] = week(packet, 1, activity=synthesized("새 여름 놀이", refs))
    result = validate(packet, proposal(packet, weeks))
    assert ProposalViolationCode.GROUNDING_AGE_MISMATCH not in result.codes


# ============================================== Fingerprint


def test_a_proposal_built_from_another_packet_is_rejected(packet):
    other = build_packet(
        [rec("ev_z", institution="라어린이집", text="다른 달 활동")]
    )
    request = build_monthly_planner_request(other)
    result = validate(packet, proposal(packet, clean_weeks(packet)), request=request)
    assert result.codes == (ProposalViolationCode.PACKET_FINGERPRINT_MISMATCH,)


def test_fingerprint_mismatch_stops_further_checks(packet):
    """어느 Packet의 Proposal인지 모르면 나머지 검사가 의미 없다."""
    other = build_packet([rec("ev_z", institution="라어린이집", text="다른 활동")])
    weeks = clean_weeks(packet)
    weeks[0] = week(
        packet, 1, activity=synthesized(SOURCE_TEXTS["ev_1"], [any_ref(packet)])
    )
    result = validate(
        packet, proposal(packet, weeks),
        request=build_monthly_planner_request(other),
    )
    assert len(result.violations) == 1


# ============================================== Provenance


def test_missing_planner_model_is_a_provenance_violation(packet):
    result = validate(packet, proposal(packet, clean_weeks(packet)), model="  ")
    assert ProposalViolationCode.PROVENANCE_INCOMPLETE in result.codes


def test_provenance_records_week_order_basis_as_planner_composed(packet):
    """Corpus에 주차 순서 근거가 없다 (OD-N14)."""
    result = validate(packet, proposal(packet, clean_weeks(packet)))
    assert result.week_order_basis == "PLANNER_COMPOSED"


# ============================================== Repairability


def test_model_mistakes_are_repairable(packet):
    weeks = clean_weeks(packet)
    weeks[0] = week(
        packet, 1, activity=synthesized(SOURCE_TEXTS["ev_1"], [any_ref(packet)])
    )
    result = validate(packet, proposal(packet, weeks))
    assert result.is_repairable
    assert result.repair_summary


def test_context_problems_are_not_repairable(packet):
    other = build_packet([rec("ev_z", institution="라어린이집", text="다른 활동")])
    result = validate(
        packet, proposal(packet, clean_weeks(packet)),
        request=build_monthly_planner_request(other),
    )
    assert not result.is_repairable


def test_missing_metadata_is_not_repairable(packet):
    result = validate(packet, proposal(packet, clean_weeks(packet)), model="")
    assert not result.is_repairable


def test_a_valid_result_is_not_repairable(packet):
    """고칠 것이 없으면 repair 대상도 아니다."""
    result = validate(packet, proposal(packet, clean_weeks(packet)))
    assert result.is_valid
    assert not result.is_repairable


def test_repair_hints_do_not_contain_source_text(packet):
    """§28 — 원문을 다시 넣어 보내지 않는다."""
    weeks = clean_weeks(packet)
    weeks[0] = week(
        packet, 1, activity=synthesized(SOURCE_TEXTS["ev_1"], [any_ref(packet)])
    )
    result = validate(packet, proposal(packet, weeks))
    for hint in result.repair_summary:
        assert SOURCE_TEXTS["ev_1"] not in hint


def test_violation_detail_does_not_contain_source_text_or_institution(packet):
    weeks = clean_weeks(packet)
    weeks[0] = week(
        packet, 1, activity=synthesized(SOURCE_TEXTS["ev_1"], [any_ref(packet)])
    )
    result = validate(packet, proposal(packet, weeks))
    for violation in result.violations:
        assert SOURCE_TEXTS["ev_1"] not in violation.detail
        assert "가어린이집" not in violation.detail


# ============================================== Reject 의미


def test_one_violation_rejects_the_whole_proposal(packet):
    weeks = clean_weeks(packet)
    weeks[-1] = week(
        packet, len(weeks),
        activity=synthesized(SOURCE_TEXTS["ev_1"], [any_ref(packet)]),
    )
    result = validate(packet, proposal(packet, weeks))
    assert not result.is_valid


def test_the_validator_never_calls_an_llm():
    """Validator 모듈이 LLM Adapter나 Port 구현을 import하지 않는다."""
    import ssuksak.planning.rules.monthly_llm_validation as module

    source = module.__file__
    text = open(source, encoding="utf-8").read()
    for banned in ("EliceMLAPIAdapter", "openai", "FakeLLM", "plan_monthly("):
        assert banned not in text
