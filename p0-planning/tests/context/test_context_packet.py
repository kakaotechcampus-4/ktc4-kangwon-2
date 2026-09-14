"""Monthly Context Packet — Contract · 중복 · License · Budget · 결정론 (L3).

In-Memory Record로 규칙을 고정한다. 실제 Artifact에 의존하는 검증은
`test_context_packet_quality.py`에 따로 둔다.
"""

from __future__ import annotations

import dataclasses
import datetime

import pytest
from pydantic import ValidationError

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
from ssuksak.planning.application.generate_monthly_plan import SAFETY_SOURCE_KINDS
from ssuksak.planning.context import (
    PACKET_VERSION,
    SAFETY_REQUIRED_SOURCE_KINDS,
    ActivityOrigin,
    AgeEvidenceStrength,
    ContextPacketError,
    MonthlyContextPacketBuilder,
    MonthlyContextRequest,
    PackedBlock,
    age_evidence_summary,
    measure,
    packet_fingerprint,
    planner_visible_payload,
    render_debug_packet,
    trim_to_budget,
    validate_packet,
)
from ssuksak.planning.domain.identifiers import PeriodKey
from ssuksak.planning.domain.parent_lineage import ParentYearlyLineage
from ssuksak.planning.retrieval import (
    InMemoryInstitutionEvidenceRepository,
    MonthlyEvidenceRetriever,
)

SUMMER = "여름"


def rec(
    rid: str,
    *,
    month: int = 7,
    ages: tuple[int, ...] = (4,),
    age_kind: AgeEvidenceType = AgeEvidenceType.SINGLE_AGE_PAGE,
    section: SourceSection = SourceSection.OUTDOOR_PLAY,
    setting: Setting = Setting.OUTDOOR,
    quality: ExtractionQuality = ExtractionQuality.VALID,
    readability: MachineReadability = MachineReadability.TEXT_LAYER,
    institution: str | None = "가어린이집",
    text: str = "모래놀이",
    theme: str | None = None,
    sha: str | None = None,
    page: int = 1,
) -> EvidenceRecord:
    is_exp = section is SourceSection.WEEK_EXPERIENCE
    return EvidenceRecord(
        record_id=rid,
        source_type=EvidenceSourceType.INSTITUTION_SAMPLE,
        source_path=f"references/samples/monthly/{institution or 'unknown'}.pdf",
        source_sha256=(sha or (institution or "?").encode().hex().ljust(64, "0"))[:64],
        page=page,
        institution_id=institution,
        month=month,
        age_scope=ages,
        age_evidence_type=age_kind,
        monthly_theme=theme,
        source_section=section,
        source_label="바깥놀이",
        experience_text=text if is_exp else None,
        activity_text=None if is_exp else text,
        setting=setting,
        machine_readability=readability,
        reuse_policy=ReusePolicy.CONTEXT_ONLY,
        extraction_quality=quality,
        extraction_method="table_line_geometry_v1",
    )


def lineage() -> ParentYearlyLineage:
    return ParentYearlyLineage(
        parent_yearly_plan_id="yp_001",
        parent_yearly_period_key="2026-07",
        parent_yearly_theme_id="yr_theme_summer",
        parent_yearly_value=SUMMER,
        reference_catalog_id="ssuksak.theme-reference",
        reference_version="theme-reference-v0",
        confirmed_at=datetime.datetime(2026, 2, 20, 9, 0, tzinfo=datetime.UTC),
        confirmed_by="actor_001",
    )


def request(
    *, target_month: str = "2026-07", ages: tuple[int, ...] = (4,)
) -> MonthlyContextRequest:
    return MonthlyContextRequest(
        school_year="2026",
        target_month=PeriodKey(target_month),
        classroom_ages=ages,
        age_mode="SINGLE" if len(ages) == 1 else "MIXED",
        parent_lineage=lineage(),
        daycare_ref="dc_1",
        classroom_ref="cr_1",
    )


def builder(records: list[EvidenceRecord], **kwargs) -> MonthlyContextPacketBuilder:
    store = InMemoryInstitutionEvidenceRepository(records).get_store()
    return MonthlyContextPacketBuilder(
        MonthlyEvidenceRetriever(store), store, **kwargs
    )


def packet_of(records: list[EvidenceRecord], **kwargs):
    return builder(records, **kwargs).build(request(**kwargs.pop("req", {})))


# ============================================== Contract


def test_packet_is_frozen_and_rejects_unknown_fields():
    p = packet_of([rec("ev_a")])
    with pytest.raises(ValidationError):
        p.planning_request.school_year = "2027"
    with pytest.raises(ValidationError):
        type(p.constraints)(
            expected_week_ids=("2026-07-W1",),
            expected_week_count=1,
            allowed_activity_origins=(ActivityOrigin.REFERENCE,),
            activity_origin_priority=(ActivityOrigin.REFERENCE,),
            surprise_field=1,
        )


def test_packet_carries_its_version_in_both_places():
    p = packet_of([rec("ev_a")])
    assert p.packet_version == PACKET_VERSION
    assert p.source_lineage.packet_version == PACKET_VERSION


def test_request_rejects_ages_outside_p0_target():
    with pytest.raises(ValueError, match="만3~5세"):
        MonthlyContextRequest(
            school_year="2026",
            target_month=PeriodKey("2026-07"),
            classroom_ages=(2,),
            age_mode="SINGLE",
            parent_lineage=lineage(),
        )


def test_request_rejects_empty_ages_and_blank_school_year():
    with pytest.raises(ValueError, match="classroom_ages"):
        MonthlyContextRequest(
            school_year="2026",
            target_month=PeriodKey("2026-07"),
            classroom_ages=(),
            age_mode="SINGLE",
            parent_lineage=lineage(),
        )
    with pytest.raises(ValueError, match="school_year"):
        MonthlyContextRequest(
            school_year="  ",
            target_month=PeriodKey("2026-07"),
            classroom_ages=(4,),
            age_mode="SINGLE",
            parent_lineage=lineage(),
        )


# ============================================== 필수 요소


def test_theme_is_carried_verbatim_from_confirmed_yearly():
    p = packet_of([rec("ev_a")])
    assert p.parent_theme.theme_id == "yr_theme_summer"
    assert p.parent_theme.theme_value == SUMMER
    assert p.parent_theme.parent_yearly_plan_id == "yp_001"


def test_week_slots_come_from_the_canonical_week_rule():
    p = packet_of([rec("ev_a")])
    assert [w.week_id for w in p.week_slots] == [
        "2026-07-W1", "2026-07-W2", "2026-07-W3", "2026-07-W4", "2026-07-W5",
    ]
    assert p.constraints.expected_week_count == 5
    assert p.constraints.expected_week_ids == tuple(
        w.week_id for w in p.week_slots
    )


def test_lineage_records_every_artifact_the_packet_used():
    p = packet_of([rec("ev_a")])
    lin = p.source_lineage
    assert lin.evidence_store_id == "ssuksak.institution-evidence"
    assert lin.evidence_store_content_sha256
    assert lin.theme_reference_version == "theme-reference-v0"
    assert lin.week_policy_name == "SSUKSAK_P0_CANONICAL_WEEK_POLICY"
    assert lin.selection_rule_version


def test_validator_rejects_a_packet_whose_week_count_disagrees():
    p = packet_of([rec("ev_a")])
    broken = p.model_copy(
        update={"constraints": p.constraints.model_copy(
            update={"expected_week_count": 99}
        )}
    )
    with pytest.raises(ContextPacketError, match="expected_week_count"):
        validate_packet(broken)


def test_validator_rejects_duplicate_week_ids():
    p = packet_of([rec("ev_a")])
    dupe = p.week_slots[:1] * 2
    broken = p.model_copy(
        update={
            "week_slots": dupe,
            "constraints": p.constraints.model_copy(
                update={
                    "expected_week_ids": tuple(w.week_id for w in dupe),
                    "expected_week_count": 2,
                }
            ),
        }
    )
    with pytest.raises(ContextPacketError, match="중복"):
        validate_packet(broken)


# ============================================== 빈 Optional Block


def test_official_blocks_are_structurally_empty_not_filled_with_prose():
    p = packet_of([rec("ev_a")])
    assert p.official_play_context == ()
    assert p.official_topic_context == ()
    validate_packet(p)


def test_a_packet_with_no_contrast_is_still_valid():
    p = packet_of([rec("ev_a"), rec("ev_b", institution="나어린이집")])
    assert p.age_contrast_evidence == ()
    assert p.age_context.age_contrast_count == 0
    validate_packet(p)


def test_a_packet_with_no_evidence_at_all_is_still_valid():
    p = packet_of([rec("ev_other", month=11)])
    assert p.institution_evidence == ()
    assert p.week_experience_candidates == ()
    assert p.reference_activities == ()
    validate_packet(p)


# ============================================== Eligibility


@pytest.mark.parametrize(
    "kwargs",
    [
        {"quality": ExtractionQuality.NEEDS_REVIEW},
        {"quality": ExtractionQuality.INVALID},
        {"readability": MachineReadability.IMAGE_ONLY},
        {"setting": Setting.INDOOR_ALTERNATIVE},
        {"section": SourceSection.INDOOR_PLAY},
    ],
)
def test_ineligible_records_never_reach_the_packet(kwargs):
    p = packet_of([rec("ev_bad", **kwargs), rec("ev_ok", institution="나어린이집")])
    assert "ev_bad" not in p.all_evidence_ids


def test_every_packet_item_is_valid_and_text_layer():
    p = packet_of([rec(f"ev_{i}", institution=f"{i}어린이집") for i in range(6)])
    for item in p.institution_evidence + p.other_outdoor_evidence:
        assert item.audit.extraction_quality == "VALID"
        assert item.audit.machine_readability == "TEXT_LAYER"


# ============================================== 중복 제거


def contrast_records() -> list[EvidenceRecord]:
    """같은 문서에 만3세·만4세 면이 함께 있는 기관 하나 + 다른 기관들."""
    sha = "a" * 64
    return [
        rec("ev_c4a", ages=(4,), sha=sha, page=1, text="물총놀이", institution="가어린이집"),
        rec("ev_c4b", ages=(4,), sha=sha, page=1, text="물놀이 공원", institution="가어린이집"),
        rec("ev_c3a", ages=(3,), sha=sha, page=2, text="여름 꽃 찾기", institution="가어린이집"),
        rec("ev_x1", institution="나어린이집", text="모래놀이 하기"),
        rec("ev_x2", institution="다어린이집", text="물놀이 하기"),
    ]


def test_a_record_never_appears_in_two_blocks():
    p = packet_of(contrast_records())
    ids = p.all_evidence_ids
    assert len(set(ids)) == len(ids)
    validate_packet(p)


def test_contrast_wins_over_the_flat_institution_list():
    """정보가 더 많은 쪽(어느 연령 면인지까지 보이는 쪽)을 남긴다."""
    p = packet_of(contrast_records())
    contrast_ids = {
        i.evidence_id
        for g in p.age_contrast_evidence
        for o in g.observations
        for i in o.items
    }
    assert "ev_c4a" in contrast_ids
    assert contrast_ids
    assert not contrast_ids & {i.evidence_id for i in p.institution_evidence}


def test_validator_catches_a_record_duplicated_across_blocks():
    p = packet_of(contrast_records())
    if not p.institution_evidence:
        pytest.skip("institution block이 비어 중복을 만들 수 없다")
    broken = p.model_copy(
        update={"other_outdoor_evidence": p.institution_evidence[:1]}
    )
    with pytest.raises(ContextPacketError, match="중복"):
        validate_packet(broken)


# ============================================== Age Contrast 관계


def test_contrast_keeps_the_pair_relationship():
    p = packet_of(contrast_records())
    assert len(p.age_contrast_evidence) == 1
    group = p.age_contrast_evidence[0]
    assert group.ages == (3, 4)
    assert {i.text for o in group.observations if o.age == 4 for i in o.items} == {
        "물총놀이", "물놀이 공원"
    }
    assert group.source_sha256 == "a" * 64


def test_contrast_never_mixes_two_documents():
    p = packet_of(contrast_records())
    for group in p.age_contrast_evidence:
        for obs in group.observations:
            for item in obs.items:
                assert item.audit.source_sha256 == group.source_sha256


def test_validator_rejects_a_contrast_group_with_one_age():
    p = packet_of(contrast_records())
    group = p.age_contrast_evidence[0]
    broken = p.model_copy(
        update={
            "age_contrast_evidence": (
                group.model_copy(update={"observations": group.observations[:1]}),
            )
        }
    )
    with pytest.raises(ContextPacketError, match="2개 미만"):
        validate_packet(broken)


# ============================================== Week Experience


def test_week_experience_candidate_has_no_week_field_at_all():
    """값이 None인 것이 아니라 **자리 자체가 없다.**"""
    candidate = packet_of(
        [rec("ev_w", section=SourceSection.WEEK_EXPERIENCE)]
    ).week_experience_candidates[0]
    assert not {f for f in type(candidate).model_fields if "week" in f}


def test_week_experience_is_a_candidate_not_a_plan():
    p = packet_of(
        [
            rec(f"ev_w{i}", section=SourceSection.WEEK_EXPERIENCE,
                institution=f"{i}어린이집", text=f"경험 {i}")
            for i in range(3)
        ]
    )
    assert len(p.week_experience_candidates) == 3
    assert type(p.week_experience_candidates[0]).__name__ == "WeekExperienceCandidate"


# ============================================== License / Constraint


def test_reuse_policy_survives_into_every_item():
    p = packet_of(contrast_records())
    for item in p.institution_evidence + p.other_outdoor_evidence:
        assert item.reuse_policy is ReusePolicy.CONTEXT_ONLY


def test_reuse_policy_is_never_stripped_from_the_planner_payload():
    payload = planner_visible_payload(packet_of(contrast_records()))
    items = payload["institution_evidence"] + payload["other_outdoor_evidence"]
    assert items
    for item in items:
        assert item["reuse_policy"] == "CONTEXT_ONLY"


def test_corpus_direct_output_is_disabled_and_origin_list_agrees():
    c = packet_of([rec("ev_a")]).constraints
    assert c.corpus_direct_output_enabled is False
    assert ActivityOrigin.CORPUS_EVIDENCE not in c.allowed_activity_origins
    assert c.allowed_activity_origins == (
        ActivityOrigin.REFERENCE,
        ActivityOrigin.LLM_SYNTHESIZED,
    )


def test_corpus_evidence_stays_in_the_priority_order():
    """개념을 삭제하지 않는다. 현재 비활성일 뿐이다."""
    c = packet_of([rec("ev_a")]).constraints
    assert c.activity_origin_priority == (
        ActivityOrigin.REFERENCE,
        ActivityOrigin.CORPUS_EVIDENCE,
        ActivityOrigin.LLM_SYNTHESIZED,
    )


def test_validator_rejects_enabling_corpus_output_while_context_only_exists():
    p = packet_of(contrast_records())
    broken = p.model_copy(
        update={"constraints": p.constraints.model_copy(
            update={"corpus_direct_output_enabled": True}
        )}
    )
    with pytest.raises(ContextPacketError, match="CONTEXT_ONLY"):
        validate_packet(broken)


def test_validator_rejects_allowing_source_text_copy():
    p = packet_of([rec("ev_a")])
    broken = p.model_copy(
        update={"constraints": p.constraints.model_copy(
            update={"source_text_copy_allowed": True}
        )}
    )
    with pytest.raises(ContextPacketError, match="source_text_copy_allowed"):
        validate_packet(broken)


# ============================================== Safety


def test_safety_context_carries_no_content_candidates():
    safety = packet_of([rec("ev_a")]).safety_context
    assert safety.safety_generation_allowed is False
    assert safety.verification == "NOT_VERIFIED_SOURCE_REQUIRED"
    assert safety.cell_state == "EMPTY_UNRESOLVED"
    assert not hasattr(safety, "candidates")


def test_safety_source_kinds_match_the_production_use_case():
    """L3가 값을 복제했으므로 어긋나면 즉시 드러나야 한다."""
    assert SAFETY_REQUIRED_SOURCE_KINDS == SAFETY_SOURCE_KINDS


def test_validator_rejects_enabling_safety_generation():
    p = packet_of([rec("ev_a")])
    broken = p.model_copy(
        update={"constraints": p.constraints.model_copy(
            update={"safety_generation_allowed": True}
        )}
    )
    with pytest.raises(ContextPacketError, match="safety_generation_allowed"):
        validate_packet(broken)


# ============================================== Age Context


def test_age_strength_follows_the_confirmed_thresholds():
    store = InMemoryInstitutionEvidenceRepository(
        [rec(f"ev_{i}", institution=f"{i}어린이집") for i in range(3)]
    ).get_store()
    s = age_evidence_summary(store, calendar_month=7, age=4)
    assert s.single_age_institution_count == 3
    assert s.strength is AgeEvidenceStrength.STRONG


@pytest.mark.parametrize(
    "institutions,setting,expected",
    [
        (2, Setting.OUTDOOR, AgeEvidenceStrength.MODERATE),
        (1, Setting.OUTDOOR, AgeEvidenceStrength.MODERATE),
        (1, Setting.INDOOR, AgeEvidenceStrength.WEAK),
    ],
)
def test_age_strength_lower_tiers(institutions, setting, expected):
    section = (
        SourceSection.OUTDOOR_PLAY
        if setting is Setting.OUTDOOR
        else SourceSection.INDOOR_PLAY
    )
    store = InMemoryInstitutionEvidenceRepository(
        [
            rec(f"ev_{i}", institution=f"{i}어린이집", setting=setting, section=section)
            for i in range(institutions)
        ]
    ).get_store()
    assert age_evidence_summary(store, calendar_month=7, age=4).strength is expected


def test_age_strength_is_very_weak_when_nothing_matches():
    store = InMemoryInstitutionEvidenceRepository([]).get_store()
    s = age_evidence_summary(store, calendar_month=7, age=4)
    assert s.strength is AgeEvidenceStrength.VERY_WEAK
    assert s.single_age_institution_count == 0


def test_mixed_request_reports_the_weakest_age():
    records = [
        rec(f"ev_a4_{i}", ages=(4,), institution=f"{i}어린이집") for i in range(3)
    ] + [rec("ev_a5", ages=(5,), institution="단독어린이집", setting=Setting.INDOOR,
             section=SourceSection.INDOOR_PLAY)]
    p = builder(records).build(request(ages=(4, 5)))
    by_age = {s.age: s.strength for s in p.age_context.per_age}
    assert by_age[4] is AgeEvidenceStrength.STRONG
    assert by_age[5] is AgeEvidenceStrength.WEAK
    assert p.age_context.overall_strength is AgeEvidenceStrength.WEAK


def test_age_context_records_the_criteria_source():
    p = packet_of([rec("ev_a")])
    assert p.age_context.criteria_id == "new-reference-evidence-impact-2026-09#4.1"


@pytest.mark.parametrize("age", [3, 4, 5])
def test_single_age_requests_are_accepted(age):
    p = builder([rec("ev_a", ages=(age,))]).build(request(ages=(age,)))
    assert p.age_context.requested_ages == (age,)
    validate_packet(p)


def test_validator_rejects_age_context_disagreeing_with_the_request():
    p = packet_of([rec("ev_a")])
    broken = p.model_copy(
        update={"age_context": p.age_context.model_copy(
            update={"requested_ages": (5,)}
        )}
    )
    with pytest.raises(ContextPacketError, match="requested_ages"):
        validate_packet(broken)


# ============================================== 익명화


def test_institution_names_stay_out_of_the_planner_payload():
    p = packet_of(contrast_records())
    payload = planner_visible_payload(p)
    assert "가어린이집" not in str(payload)
    assert p.institution_evidence or p.other_outdoor_evidence


def test_real_institution_id_is_kept_in_audit():
    p = packet_of(contrast_records())
    items = p.institution_evidence + p.other_outdoor_evidence
    names = {i.audit.institution_id for i in items}
    assert names and None not in names


def test_source_groups_are_stable_labels():
    p = packet_of(contrast_records())
    for item in p.institution_evidence + p.other_outdoor_evidence:
        assert item.source_group.startswith("S")


def test_evidence_refs_are_short_and_unique():
    p = packet_of(contrast_records())
    refs = [i.ref for i in p.institution_evidence + p.other_outdoor_evidence]
    refs += [
        i.ref for g in p.age_contrast_evidence for o in g.observations for i in o.items
    ]
    assert refs
    assert len(set(refs)) == len(refs)
    assert all(len(r) <= 4 for r in refs)


def test_raw_record_ids_are_not_in_the_planner_payload():
    p = packet_of(contrast_records())
    payload = str(planner_visible_payload(p))
    assert "ev_c4a" not in payload


# ============================================== Budget


def many_records(n: int = 40) -> list[EvidenceRecord]:
    return [
        rec(f"ev_{i:02d}", institution=f"{i:02d}어린이집", text=f"여름 물놀이 활동 {i:02d}")
        for i in range(n)
    ]


def test_a_packet_within_budget_is_returned_unchanged():
    p = packet_of(many_records(), char_budget=10**6)
    assert p.trimmed_blocks == ()
    assert trim_to_budget(p, char_budget=10**6) is p


def test_over_budget_trims_other_outdoor_first():
    big = packet_of(many_records(), char_budget=10**6)
    small = trim_to_budget(big, char_budget=3_000)
    assert small.trimmed_blocks
    assert small.trimmed_blocks[0] == PackedBlock.OTHER_OUTDOOR.value
    assert len(small.other_outdoor_evidence) < len(big.other_outdoor_evidence)


def test_trimming_never_touches_reference_or_weeks_or_constraints():
    big = packet_of(many_records(), char_budget=10**6)
    small = trim_to_budget(big, char_budget=1_500)
    assert small.reference_activities == big.reference_activities
    assert small.week_slots == big.week_slots
    assert small.constraints == big.constraints
    assert small.age_context == big.age_context
    assert small.safety_context == big.safety_context


def test_trimming_keeps_the_institution_floor():
    big = packet_of(many_records(), char_budget=10**6)
    small = trim_to_budget(big, char_budget=200)
    assert len(small.institution_evidence) >= 4


def test_trimming_is_deterministic():
    big = packet_of(many_records(), char_budget=10**6)
    a = trim_to_budget(big, char_budget=3_000)
    b = trim_to_budget(big, char_budget=3_000)
    assert packet_fingerprint(a) == packet_fingerprint(b)


def test_trimming_keeps_the_head_of_the_ranking():
    big = packet_of(many_records(), char_budget=10**6)
    small = trim_to_budget(big, char_budget=3_000)
    kept = len(small.other_outdoor_evidence)
    assert small.other_outdoor_evidence == big.other_outdoor_evidence[:kept]


def test_contrast_is_trimmed_by_whole_groups():
    records = contrast_records() + many_records(30)
    p = builder(records, char_budget=10**6).build(request())
    small = trim_to_budget(p, char_budget=500)
    for group in small.age_contrast_evidence:
        assert len(group.ages) >= 2


def test_measurement_separates_representation_from_content():
    m = measure(packet_of(contrast_records()))
    assert m.content_chars > 0
    assert m.planner_visible_chars > m.content_chars
    assert m.full_packet_chars > m.planner_visible_chars
    assert m.serialization_overhead_ratio > 1.0


def test_audit_fields_are_excluded_from_the_planner_payload():
    payload = str(planner_visible_payload(packet_of(contrast_records())))
    for token in ("rank_score", "source_diversity_group", "retrieval_tier",
                  "source_sha256", "daycare_ref", "classroom_ref"):
        assert token not in payload


# ============================================== 결정론


def test_the_same_request_gives_the_same_packet():
    records = contrast_records()
    b = builder(records)
    assert packet_fingerprint(b.build(request())) == packet_fingerprint(
        b.build(request())
    )


def test_a_fresh_builder_gives_the_same_packet():
    records = contrast_records()
    a = builder(records).build(request())
    b = builder(list(records)).build(request())
    assert packet_fingerprint(a) == packet_fingerprint(b)


def test_record_input_order_does_not_change_the_packet():
    records = contrast_records()
    a = builder(records).build(request())
    b = builder(list(reversed(records))).build(request())
    assert packet_fingerprint(a) == packet_fingerprint(b)


def test_assemble_is_pure_given_a_retrieval_result():
    records = contrast_records()
    store = InMemoryInstitutionEvidenceRepository(records).get_store()
    retriever = MonthlyEvidenceRetriever(store)
    b = MonthlyContextPacketBuilder(retriever, store)
    req = request()
    from ssuksak.planning.retrieval import RetrievalRequest

    result = retriever.retrieve(
        RetrievalRequest(
            target_month="2026-07", calendar_month=7, ages=(4,), age_mode="SINGLE",
            confirmed_theme_id="yr_theme_summer", confirmed_theme_value=SUMMER,
            week_count=5,
        )
    )
    assert packet_fingerprint(b.assemble(req, result)) == packet_fingerprint(
        b.assemble(req, result)
    )


def test_a_different_theme_changes_the_fingerprint():
    records = contrast_records()
    b = builder(records)
    a = b.build(request())
    other = dataclasses.replace(
        request(),
        parent_lineage=dataclasses.replace(
            lineage(), parent_yearly_value="교통기관",
            parent_yearly_theme_id="yr_theme_transport",
        ),
    )
    assert packet_fingerprint(a) != packet_fingerprint(b.build(other))


def test_fingerprint_changes_when_the_evidence_store_changes():
    a = builder(contrast_records()).build(request())
    b = builder(contrast_records() + [rec("ev_new", institution="새어린이집")]).build(
        request()
    )
    assert packet_fingerprint(a) != packet_fingerprint(b)


# ============================================== Debug rendering


def test_debug_render_is_deterministic_and_not_a_prompt():
    p = packet_of(contrast_records())
    assert render_debug_packet(p) == render_debug_packet(p)
    text = render_debug_packet(p)
    assert "MONTHLY CONTEXT PACKET" in text
    assert "주차 번호 없음" in text


def test_debug_render_can_include_audit_detail():
    p = packet_of(contrast_records())
    assert len(render_debug_packet(p, audit=True)) > len(render_debug_packet(p))
