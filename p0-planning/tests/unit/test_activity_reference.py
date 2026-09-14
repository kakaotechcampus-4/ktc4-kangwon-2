"""Activity Reference Domain 테스트 (M2-A).

검증 축:
- Catalog id/version 불변식과 중복 activity_id 거부
- 연령·월 근거를 넘겨 주장하지 못함 (추론 금지)
- 혼합연령이 Activity 복제 없이 동작
- placement_slots 통제 어휘와 safety_education 거부
- setting / theme relation / curriculum domain 어휘 강제
- 승인 Gate 파생 (runtime_active는 독립 필드가 아니다)
- 기관 고유 항목 runtime 제외 Contract
"""

from __future__ import annotations

import pytest

from ssuksak.planning.domain.activity_reference import (
    FORBIDDEN_PLACEMENT_SLOTS,
    OUTDOOR_PLAY_SLOT,
    SUPPORTED_PLACEMENT_SLOTS,
    THEME_RELATION_OBSERVED_TOGETHER,
    ActivationStatus,
    ActivityCandidate,
    ActivityCatalog,
    ActivityEvidence,
    ActivitySetting,
    ActivityThemeLink,
    CurriculumLink,
)

CATALOG_ID = "ssuksak.outdoor-activity-reference"
VERSION = "activity-reference-v0.1.0"
THEME_VERSION = "theme-reference-v0.1.2"


def evidence(
    *,
    origin_id="sample.monthly.test.2026.09",
    page=1,
    age_scope=(3, 4),
    month=9,
    label="무궁화 꽃이 피었습니다",
    section=OUTDOOR_PLAY_SLOT,
    source_label="바깥놀이",
    **kw,
):
    return ActivityEvidence(
        origin_id=origin_id,
        page=page,
        age_scope=tuple(age_scope),
        observed_month=month,
        observed_label=label,
        observed_section=section,
        observed_source_label=source_label,
        **kw,
    )


def candidate(**kw):
    base = dict(
        activity_id="act_outdoor_test",
        label="테스트 바깥놀이",
        supported_ages=(3, 4),
        allow_mixed_age=True,
        mixed_age_requires_all_supported=True,
        applicable_months=(9,),
        placement_slots=(OUTDOOR_PLAY_SLOT,),
        setting=ActivitySetting.OUTDOOR,
        source_version=VERSION,
        evidence=(evidence(),),
    )
    base.update(kw)
    return ActivityCandidate(**base)


def catalog(activities=None, **kw):
    base = dict(
        catalog_id=CATALOG_ID,
        catalog_version=VERSION,
        activation_status=ActivationStatus.HUMAN_APPROVED,
        activities=tuple(activities if activities is not None else (candidate(),)),
    )
    base.update(kw)
    return ActivityCatalog(**base)


# -------------------------------------------------- catalog id / version


def test_catalog_requires_id_and_version():
    with pytest.raises(ValueError, match="catalog_id"):
        catalog(catalog_id="  ")
    with pytest.raises(ValueError, match="catalog_version"):
        catalog(catalog_version="")


def test_duplicate_activity_id_is_rejected():
    with pytest.raises(ValueError, match="중복된 activity_id"):
        catalog([candidate(activity_id="dup"), candidate(activity_id="dup")])


def test_activity_source_version_must_match_catalog_version():
    with pytest.raises(ValueError, match="source_version"):
        catalog([candidate(source_version="activity-reference-v9.9.9")])


def test_month_coverage_must_match_actual_candidate_months():
    with pytest.raises(ValueError, match="month_coverage"):
        catalog([candidate(applicable_months=(9,))], month_coverage=(3, 9))


def test_month_coverage_accepts_exact_match():
    c = catalog(
        [
            candidate(activity_id="a", applicable_months=(9,)),
            candidate(
                activity_id="b",
                applicable_months=(3,),
                evidence=(evidence(month=3),),
            ),
        ],
        month_coverage=(3, 9),
    )
    assert c.month_coverage == (3, 9)


def test_empty_month_coverage_skips_the_cross_check():
    assert catalog().month_coverage == ()


def test_get_by_id():
    c = catalog([candidate(activity_id="act_outdoor_x")])
    assert c.get("act_outdoor_x") is not None
    assert c.get("missing") is None


def test_covers_month():
    c = catalog()
    assert c.covers_month(9)
    assert not c.covers_month(4)


# ------------------------------------------------------- supported_ages


def test_supported_ages_is_required():
    with pytest.raises(ValueError, match="supported_ages가 비어 있다"):
        candidate(supported_ages=())


@pytest.mark.parametrize("ages", [(2, 3), (5, 6), (0,), (6,)])
def test_supported_ages_rejects_out_of_range(ages):
    with pytest.raises(ValueError, match="만 3~5세"):
        candidate(supported_ages=ages, evidence=())


def test_supported_ages_rejects_duplicates():
    with pytest.raises(ValueError, match="supported_ages에 중복"):
        candidate(supported_ages=(3, 3), evidence=())


def test_supported_ages_cannot_exceed_observed_age_scope():
    """근거보다 넓게 주장하는 것을 값 수준에서 막는다."""
    with pytest.raises(ValueError, match="관찰된 age_scope"):
        candidate(supported_ages=(3, 4, 5), evidence=(evidence(age_scope=(3, 4)),))


def test_supported_ages_may_be_narrower_than_observed():
    c = candidate(supported_ages=(3,), evidence=(evidence(age_scope=(3, 4)),))
    assert c.supported_ages == (3,)


def test_evidence_with_empty_age_scope_does_not_widen_support():
    """본문에 연령 표기가 없는 문서는 supported_ages를 넓히지 못한다."""
    with pytest.raises(ValueError, match="관찰된 age_scope"):
        candidate(
            supported_ages=(3,),
            evidence=(evidence(age_scope=()),),
        )


def test_age_gap_is_representable():
    """3세와 5세만 관찰된 활동은 4세를 주장하지 않는다."""
    c = candidate(
        supported_ages=(3, 5),
        evidence=(evidence(age_scope=(3,)), evidence(age_scope=(5,), page=2)),
    )
    assert c.supported_ages == (3, 5)
    assert not c.supports_age_set(frozenset({4}))
    assert not c.supports_age_set(frozenset({3, 4}))
    assert c.supports_age_set(frozenset({3, 5}))


# ------------------------------------------------------------ mixed age


def test_single_age_is_supported_when_in_set():
    c = candidate(supported_ages=(3, 4))
    assert c.supports_age_set(frozenset({3}))
    assert c.supports_age_set(frozenset({4}))
    assert not c.supports_age_set(frozenset({5}))


def test_mixed_age_requires_all_selected_ages():
    c = candidate(supported_ages=(3, 4))
    assert c.supports_age_set(frozenset({3, 4}))
    assert not c.supports_age_set(frozenset({4, 5}))


def test_mixed_age_can_be_disallowed():
    c = candidate(
        supported_ages=(3, 4),
        allow_mixed_age=False,
        mixed_age_requires_all_supported=False,
    )
    assert c.supports_age_set(frozenset({3}))
    assert not c.supports_age_set(frozenset({3, 4}))


def test_disallowing_mixed_age_while_requiring_all_is_contradictory():
    with pytest.raises(ValueError, match="혼합연령을 허용하지 않으면서"):
        candidate(allow_mixed_age=False, mixed_age_requires_all_supported=True)


def test_empty_age_set_is_never_supported():
    assert not candidate().supports_age_set(frozenset())


def test_mixed_age_needs_no_activity_duplication():
    """같은 record가 단일연령 반과 혼합연령 반 모두에서 후보가 된다."""
    c = catalog([candidate(activity_id="shared", supported_ages=(3, 4))])
    for ages in ({3}, {4}, {3, 4}):
        got = c.eligible_candidates(
            section_key=OUTDOOR_PLAY_SLOT, calendar_month=9, ages=frozenset(ages)
        )
        assert [a.activity_id for a in got] == ["shared"], ages


# ---------------------------------------------------- applicable_months


def test_applicable_months_is_required():
    with pytest.raises(ValueError, match="applicable_months가 비어 있다"):
        candidate(applicable_months=())


@pytest.mark.parametrize("months", [(0,), (13,), (9, 13)])
def test_applicable_months_rejects_out_of_range(months):
    with pytest.raises(ValueError, match="1~12"):
        candidate(applicable_months=months, evidence=())


def test_applicable_months_rejects_duplicates():
    with pytest.raises(ValueError, match="applicable_months에 중복"):
        candidate(applicable_months=(9, 9), evidence=())


def test_applicable_months_cannot_exceed_observed_months():
    """9월만 관찰된 활동을 10월 후보로 확장할 수 없다."""
    with pytest.raises(ValueError, match="관찰된 월"):
        candidate(applicable_months=(9, 10), evidence=(evidence(month=9),))


def test_supports_month():
    c = candidate(applicable_months=(9,))
    assert c.supports_month(9)
    assert not c.supports_month(10)


def test_two_month_activity_is_representable():
    c = candidate(
        applicable_months=(3, 9),
        evidence=(evidence(month=3, age_scope=(3,)), evidence(month=9, page=2)),
    )
    assert c.supports_month(3) and c.supports_month(9)
    assert not c.supports_month(4)


# ----------------------------------------------------- placement_slots


def test_placement_slots_is_required():
    with pytest.raises(ValueError, match="placement_slots는 비울 수 없다"):
        candidate(placement_slots=())


def test_placement_slots_rejects_duplicates():
    with pytest.raises(ValueError, match="placement_slots에 중복"):
        candidate(placement_slots=(OUTDOOR_PLAY_SLOT, OUTDOOR_PLAY_SLOT))


def test_safety_education_placement_is_rejected():
    """법정 안전교육을 일반 Activity Catalog에서 채우는 경로를 값으로 막는다."""
    with pytest.raises(ValueError, match="법정 안전교육"):
        candidate(placement_slots=("safety_education",))


def test_safety_education_rejected_even_alongside_outdoor():
    with pytest.raises(ValueError, match="법정 안전교육"):
        candidate(placement_slots=(OUTDOOR_PLAY_SLOT, "safety_education"))


@pytest.mark.parametrize("slot", ["focus", "indoor_alternative", "goals", "theme", "made_up"])
def test_unknown_placement_slot_is_rejected(slot):
    with pytest.raises(ValueError, match="알 수 없는 placement slot"):
        candidate(placement_slots=(slot,))


def test_placement_vocabulary_is_outdoor_only_in_p0():
    assert SUPPORTED_PLACEMENT_SLOTS == frozenset({"outdoor_play"})
    assert FORBIDDEN_PLACEMENT_SLOTS == frozenset({"safety_education"})
    assert not SUPPORTED_PLACEMENT_SLOTS & FORBIDDEN_PLACEMENT_SLOTS


def test_supports_slot():
    c = candidate()
    assert c.supports_slot(OUTDOOR_PLAY_SLOT)
    assert not c.supports_slot("focus")


def test_eligible_candidates_returns_empty_for_forbidden_slot():
    assert catalog().eligible_candidates(
        section_key="safety_education", calendar_month=9, ages=frozenset({3})
    ) == ()


# -------------------------------------------------------------- setting


def test_setting_enum_values():
    assert {s.value for s in ActivitySetting} == {"OUTDOOR", "INDOOR", "EITHER"}


@pytest.mark.parametrize(
    "setting,expected",
    [
        (ActivitySetting.OUTDOOR, True),
        (ActivitySetting.EITHER, True),
        (ActivitySetting.INDOOR, False),
    ],
)
def test_outdoor_slot_setting_compatibility(setting, expected):
    assert candidate(setting=setting).supports_setting(OUTDOOR_PLAY_SLOT) is expected


def test_indoor_activity_is_filtered_out_of_outdoor_slot():
    c = catalog([candidate(activity_id="indoor", setting=ActivitySetting.INDOOR)])
    assert c.eligible_candidates(
        section_key=OUTDOOR_PLAY_SLOT, calendar_month=9, ages=frozenset({3})
    ) == ()


# ---------------------------------------------------------- theme_links


def test_theme_link_requires_observed_together_relation():
    with pytest.raises(ValueError, match="OBSERVED_TOGETHER"):
        ActivityThemeLink(
            theme_id="yr_theme_korea_and_world_cultures",
            relation="BELONGS_TO",
            theme_catalog_version=THEME_VERSION,
        )


def test_theme_link_requires_theme_id_and_version():
    with pytest.raises(ValueError, match="theme_id"):
        ActivityThemeLink(
            theme_id=" ",
            relation=THEME_RELATION_OBSERVED_TOGETHER,
            theme_catalog_version=THEME_VERSION,
        )
    with pytest.raises(ValueError, match="theme_catalog_version"):
        ActivityThemeLink(
            theme_id="t",
            relation=THEME_RELATION_OBSERVED_TOGETHER,
            theme_catalog_version="",
        )


def test_theme_links_are_many_to_many():
    c = candidate(
        theme_links=(
            ActivityThemeLink("yr_theme_korea_and_world_cultures", THEME_RELATION_OBSERVED_TOGETHER, THEME_VERSION),
            ActivityThemeLink("yr_theme_autumn_and_nature", THEME_RELATION_OBSERVED_TOGETHER, THEME_VERSION),
        )
    )
    assert c.links_theme("yr_theme_korea_and_world_cultures")
    assert c.links_theme("yr_theme_autumn_and_nature")
    assert not c.links_theme("yr_theme_spring")


def test_theme_link_is_not_a_hard_filter():
    """theme link가 없어도 hard filter를 통과한다. 후보 집합이 비지 않는다."""
    c = catalog([candidate(activity_id="no_theme", theme_links=())])
    got = c.eligible_candidates(
        section_key=OUTDOOR_PLAY_SLOT, calendar_month=9, ages=frozenset({3})
    )
    assert [a.activity_id for a in got] == ["no_theme"]


# ----------------------------------------------------- curriculum_links


def test_curriculum_links_may_be_empty():
    assert candidate(curriculum_links=()).curriculum_links == ()


def test_curriculum_links_allow_multiple_domains():
    c = candidate(
        curriculum_links=(
            CurriculumLink("curriculum.mohw.notice-2019-152", "사회관계", 12),
            CurriculumLink("curriculum.mohw.notice-2019-152", "자연탐구", 15),
        )
    )
    assert len(c.curriculum_links) == 2


def test_curriculum_link_has_no_primary_or_weight_field():
    fields = set(CurriculumLink.__dataclass_fields__)
    assert fields == {"source_id", "domain", "source_page", "relation"}
    assert "weight" not in fields
    assert "priority" not in fields


@pytest.mark.parametrize(
    "domain", ["신체운동·건강", "의사소통", "사회관계", "예술경험", "자연탐구"]
)
def test_curriculum_domain_accepts_the_five_official_domains(domain):
    assert CurriculumLink("s", domain, 1).domain == domain


@pytest.mark.parametrize("domain", ["신체운동", "놀이", "art", "physical", ""])
def test_curriculum_domain_rejects_invented_vocabulary(domain):
    with pytest.raises(ValueError, match="누리과정 5개 영역"):
        CurriculumLink("s", domain, 1)


def test_curriculum_relation_rejects_direct_national_source_claim():
    with pytest.raises(ValueError, match="EDUCATIONAL_ALIGNMENT"):
        CurriculumLink("s", "사회관계", 1, relation="NATIONAL_CURRICULUM_SOURCE")


# ------------------------------------------------------------- evidence


def test_evidence_requires_origin_id():
    with pytest.raises(ValueError, match="origin_id"):
        evidence(origin_id="  ")


def test_evidence_requires_positive_page():
    with pytest.raises(ValueError, match="page"):
        evidence(page=0)


@pytest.mark.parametrize("month", [0, 13])
def test_evidence_month_range(month):
    with pytest.raises(ValueError, match="observed_month"):
        evidence(month=month)


def test_evidence_preserves_verbatim_label():
    e = evidence(label="♥바깥놀이- 강강수월래해요")
    assert e.observed_label == "♥바깥놀이- 강강수월래해요"


def test_evidence_label_cannot_be_blank():
    with pytest.raises(ValueError, match="observed_label"):
        evidence(label="   ")


def test_evidence_age_scope_may_be_empty():
    """본문에 연령 표기가 없는 문서는 빈 age_scope를 갖는다."""
    assert evidence(age_scope=()).age_scope == ()


@pytest.mark.parametrize("scope", [(2,), (6,), (3, 9)])
def test_evidence_age_scope_range(scope):
    with pytest.raises(ValueError, match="만 3~5세"):
        evidence(age_scope=scope)


def test_evidence_carries_matched_via_and_note():
    e = evidence(matched_via="RELATED_EXPRESSION", match_note="비표준 표기다")
    assert e.matched_via == "RELATED_EXPRESSION"
    assert e.match_note == "비표준 표기다"


def test_evidence_records_observed_section_and_source_label():
    e = evidence(section="outdoor_play", source_label="실외 자유 놀이")
    assert e.observed_section == "outdoor_play"
    assert e.observed_source_label == "실외 자유 놀이"


def test_evidence_strength_counts_only_matching_month():
    c = candidate(
        applicable_months=(3, 9),
        evidence=(
            evidence(month=9, page=1),
            evidence(month=9, page=2),
            evidence(month=3, page=3, age_scope=(3,)),
        ),
    )
    assert c.evidence_strength_for_month(9) == 2
    assert c.evidence_strength_for_month(3) == 1
    assert c.evidence_strength_for_month(4) == 0


def test_observed_institution_count_deduplicates_origin():
    c = candidate(
        evidence=(
            evidence(origin_id="o1", page=1),
            evidence(origin_id="o1", page=2),
            evidence(origin_id="o2", page=1),
        )
    )
    assert c.observed_institution_count == 2


def test_origin_id_is_separate_from_source_version():
    """origin_id는 upstream lineage이고 source_version은 catalog version이다."""
    c = candidate(origin_id="sample.monthly.yedam.2026.09")
    assert c.origin_id == "sample.monthly.yedam.2026.09"
    assert c.source_version == VERSION
    assert c.origin_id != c.source_version


# -------------------------------------------------------------- aliases


def test_aliases_default_empty_and_preserve_variants():
    assert candidate().aliases == ()
    c = candidate(aliases=("강강수월래해요", "대동놀이 : 강강술래"))
    assert c.aliases == ("강강수월래해요", "대동놀이 : 강강술래")


def test_aliases_do_not_replace_evidence_labels():
    """aliases는 사람이 승인한 표현 집합이고 evidence는 원문 감사 기록이다."""
    c = candidate(
        label="강강술래",
        aliases=("강강수월래해요",),
        evidence=(evidence(label="♥바깥놀이- 강강수월래해요"),),
    )
    assert c.label == "강강술래"
    assert c.evidence[0].observed_label == "♥바깥놀이- 강강수월래해요"
    assert c.evidence[0].observed_label not in c.aliases


def test_label_and_source_version_are_required():
    with pytest.raises(ValueError, match="label"):
        candidate(label="  ")
    with pytest.raises(ValueError, match="source_version"):
        candidate(source_version=" ")


def test_activity_id_is_required():
    with pytest.raises(ValueError, match="activity_id"):
        candidate(activity_id="")


# ------------------------------------------------------- activation Gate


def test_activation_status_values():
    assert {s.value for s in ActivationStatus} == {
        "HUMAN_APPROVED",
        "PENDING_HUMAN_REVIEW",
    }


def test_pending_catalog_is_inactive():
    c = catalog(activation_status=ActivationStatus.PENDING_HUMAN_REVIEW)
    assert not c.is_active


def test_approved_catalog_is_active():
    assert catalog(activation_status=ActivationStatus.HUMAN_APPROVED).is_active


def test_pending_catalog_yields_no_candidates():
    """승인 Gate를 우회해 후보를 얻는 경로가 없다."""
    c = catalog(activation_status=ActivationStatus.PENDING_HUMAN_REVIEW)
    assert c.eligible_candidates(
        section_key=OUTDOOR_PLAY_SLOT, calendar_month=9, ages=frozenset({3})
    ) == ()


def test_runtime_active_is_not_a_writable_field():
    assert "runtime_active" not in ActivityCatalog.__dataclass_fields__
    assert "is_active" not in ActivityCatalog.__dataclass_fields__


def test_catalog_is_frozen():
    c = catalog()
    with pytest.raises(Exception):
        c.activation_status = ActivationStatus.HUMAN_APPROVED  # type: ignore[misc]


def test_candidate_is_frozen():
    c = candidate()
    with pytest.raises(Exception):
        c.supported_ages = (5,)  # type: ignore[misc]


# ------------------------------------------------- eligible_candidates


def test_eligible_candidates_applies_all_hard_filters():
    good = candidate(activity_id="good", supported_ages=(3, 4), applicable_months=(9,))
    wrong_month = candidate(
        activity_id="wrong_month",
        applicable_months=(3,),
        evidence=(evidence(month=3),),
    )
    wrong_age = candidate(
        activity_id="wrong_age",
        supported_ages=(5,),
        evidence=(evidence(age_scope=(5,)),),
    )
    indoor = candidate(activity_id="indoor", setting=ActivitySetting.INDOOR)
    c = catalog([good, wrong_month, wrong_age, indoor], month_coverage=(3, 9))

    got = c.eligible_candidates(
        section_key=OUTDOOR_PLAY_SLOT, calendar_month=9, ages=frozenset({3})
    )
    assert [a.activity_id for a in got] == ["good"]


def test_eligible_candidates_is_deterministic_by_activity_id():
    ids = ["act_z", "act_a", "act_m"]
    c = catalog([candidate(activity_id=i) for i in ids])
    got = c.eligible_candidates(
        section_key=OUTDOOR_PLAY_SLOT, calendar_month=9, ages=frozenset({3})
    )
    assert [a.activity_id for a in got] == sorted(ids)


def test_eligible_candidates_may_be_empty_without_raising():
    """후보 0개는 예외가 아니다. outdoor_play는 필수값 Section이 아니다."""
    c = catalog()
    assert c.eligible_candidates(
        section_key=OUTDOOR_PLAY_SLOT, calendar_month=5, ages=frozenset({3})
    ) == ()


# ------------------------------------------- Domain에 ranking이 없다 (M2-B)


def test_domain_has_no_ranking_api():
    for name in ("select", "rank", "best", "choose", "pick", "score"):
        assert not hasattr(ActivityCatalog, name), name
        assert not hasattr(ActivityCandidate, name), name


def test_domain_module_has_no_rule_id_constant():
    import ssuksak.planning.domain.activity_reference as mod

    assert not hasattr(mod, "RULE_ID")
    assert not hasattr(mod, "RULE_VERSION")
