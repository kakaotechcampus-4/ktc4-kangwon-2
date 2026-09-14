"""실제 Evidence Store + 승인 Catalog로 조립한 Packet의 품질 회귀 (L3).

Artifact가 없으면 skip한다. 있으면 §33~§37이 지정한 Case를 고정한다.
**없는 값을 만들어 테스트하지 않는다** — Store에 실제로 있는 문자열만 확인한다.
"""

from __future__ import annotations

import datetime
import json
import pathlib

import pytest

from ssuksak.adapters.json_activity_reference_repository import (
    production_activity_reference_repository,
)
from ssuksak.planning.context import (
    MonthlyContextPacketBuilder,
    MonthlyContextRequest,
    PackedBlock,
    measure,
    packet_fingerprint,
    validate_packet,
)
from ssuksak.planning.domain.identifiers import PeriodKey
from ssuksak.planning.domain.parent_lineage import ParentYearlyLineage
from ssuksak.planning.retrieval import (
    DEFAULT_EVIDENCE_STORE_PATH,
    JsonInstitutionEvidenceRepository,
    MonthlyEvidenceRetriever,
)

ROOT = pathlib.Path(__file__).resolve().parents[2]
CATALOG_ID = "ssuksak.outdoor-activity-reference"
CATALOG_VERSION = "activity-reference-v0.2.1"
L1_CONTENT_SHA = "52b409557d3503422aa0109664298976bd7f831ed18304b818aaad936916e5ea"

pytestmark = pytest.mark.skipif(
    not DEFAULT_EVIDENCE_STORE_PATH.exists(), reason="Evidence Store 미빌드"
)

_THEMES = json.loads(
    (ROOT / "data" / "themes" / "theme_reference_v0.json").read_text("utf-8")
)
THEME_BY_MONTH: dict[int, tuple[str, str]] = {}
for _t in _THEMES["themes"]:
    for _m in _t.get("applicable_months", []):
        THEME_BY_MONTH.setdefault(_m, (_t["theme_id"], _t["label"]))

CASES = [
    ("2026-03", (3,)),
    ("2026-06", (4,)),
    ("2026-07", (4,)),
    ("2026-08", (4,)),
    ("2027-02", (5,)),
]


@pytest.fixture(scope="module")
def catalog():
    return production_activity_reference_repository().get_catalog(
        CATALOG_ID, CATALOG_VERSION
    )


@pytest.fixture(scope="module")
def builder(catalog):
    store = JsonInstitutionEvidenceRepository().get_store()
    return MonthlyContextPacketBuilder(
        MonthlyEvidenceRetriever(store, activity_catalog=catalog),
        store,
        activity_catalog=catalog,
    )


def request(target_month: str, ages: tuple[int, ...]) -> MonthlyContextRequest:
    key = PeriodKey(target_month)
    theme_id, label = THEME_BY_MONTH[key.calendar_month]
    return MonthlyContextRequest(
        school_year="2026",
        target_month=key,
        classroom_ages=ages,
        age_mode="SINGLE" if len(ages) == 1 else "MIXED",
        parent_lineage=ParentYearlyLineage(
            parent_yearly_plan_id="yp_quality_001",
            parent_yearly_period_key=target_month,
            parent_yearly_theme_id=theme_id,
            parent_yearly_value=label,
            reference_catalog_id=_THEMES["catalog_id"],
            reference_version=_THEMES["catalog_version"],
            confirmed_at=datetime.datetime(2026, 2, 20, 9, 0, tzinfo=datetime.UTC),
            confirmed_by="actor_quality_001",
        ),
        daycare_ref="dc_q",
        classroom_ref="cr_q",
    )


def grounding_texts(packet) -> set[str]:
    out = {i.text for i in packet.institution_evidence}
    out |= {i.text for i in packet.other_outdoor_evidence}
    out |= {
        i.text
        for g in packet.age_contrast_evidence
        for o in g.observations
        for i in o.items
    }
    return out


# ============================================== 전 Case 기본 성질


@pytest.mark.parametrize("tm,ages", CASES)
def test_packet_validates(builder, catalog, tm, ages):
    validate_packet(
        builder.build(request(tm, ages)),
        catalog=catalog,
        expected_store_sha256=L1_CONTENT_SHA,
    )


@pytest.mark.parametrize("tm,ages", CASES)
def test_every_required_block_is_populated(builder, tm, ages):
    p = builder.build(request(tm, ages))
    sizes = p.block_sizes()
    assert sizes[PackedBlock.INSTITUTION_EVIDENCE] > 0
    assert sizes[PackedBlock.WEEK_EXPERIENCE] > 0
    assert sizes[PackedBlock.REFERENCE_ACTIVITIES] > 0
    assert sizes[PackedBlock.OTHER_OUTDOOR] > 0


@pytest.mark.parametrize("tm,ages", CASES)
def test_no_record_is_duplicated_across_blocks(builder, tm, ages):
    ids = builder.build(request(tm, ages)).all_evidence_ids
    assert len(set(ids)) == len(ids)


@pytest.mark.parametrize("tm,ages", CASES)
def test_no_needs_review_or_invalid_leaks(builder, tm, ages):
    p = builder.build(request(tm, ages))
    items = list(p.institution_evidence) + list(p.other_outdoor_evidence)
    items += list(p.week_experience_candidates)
    items += [i for g in p.age_contrast_evidence for o in g.observations
              for i in o.items]
    assert items
    for item in items:
        assert item.audit.extraction_quality == "VALID"
        assert item.audit.machine_readability == "TEXT_LAYER"


@pytest.mark.parametrize("tm,ages", CASES)
def test_week_candidates_never_carry_a_week_index(builder, tm, ages):
    p = builder.build(request(tm, ages))
    assert p.week_experience_candidates
    for candidate in p.week_experience_candidates:
        assert not [f for f in type(candidate).model_fields if "week" in f]


@pytest.mark.parametrize("tm,ages", CASES)
def test_official_blocks_stay_empty(builder, tm, ages):
    p = builder.build(request(tm, ages))
    assert p.official_play_context == ()
    assert p.official_topic_context == ()


@pytest.mark.parametrize("tm,ages", CASES)
def test_packet_stays_within_the_default_budget(builder, tm, ages):
    """Budget이 평상시에 발동하면 근거가 조용히 사라진다."""
    p = builder.build(request(tm, ages))
    assert p.trimmed_blocks == ()
    assert measure(p).planner_visible_chars < 20_000


@pytest.mark.parametrize("tm,ages", CASES)
def test_lineage_is_pinned_to_the_l1_artifact(builder, tm, ages):
    lin = builder.build(request(tm, ages)).source_lineage
    assert lin.evidence_store_content_sha256 == L1_CONTENT_SHA
    assert lin.evidence_store_ingestion_version == (
        "institution-evidence-ingestion-v0.1.0"
    )
    assert lin.activity_catalog_version == CATALOG_VERSION


# ============================================== §33 2026-06 만4세


@pytest.mark.parametrize(
    "text", ["우리동네를 둘러보아요", "모래로 동네 공원만들기", "깨끗한 우리 동네 만들기"]
)
def test_june_age4_grounding_survives_into_the_packet(builder, text):
    assert text in grounding_texts(builder.build(request("2026-06", (4,))))


@pytest.mark.parametrize(
    "label", ["우리 동네 지도 보며 산책하기", "모래 위에 그리는 우리 동네"]
)
def test_june_age4_reference_candidates_survive(builder, label):
    p = builder.build(request("2026-06", (4,)))
    assert label in {a.label for a in p.reference_activities}


def test_june_age4_contrast_pairs_come_from_one_document(builder):
    """§12 — 같은 문서의 서로 다른 연령 면인지 Packet에서 확인한다."""
    p = builder.build(request("2026-06", (4,)))
    assert p.age_contrast_evidence
    for group in p.age_contrast_evidence:
        assert len(group.ages) >= 2
        shas = {
            i.audit.source_sha256
            for o in group.observations
            for i in o.items
        }
        assert shas == {group.source_sha256}
        pages = {
            (i.audit.page, o.age) for o in group.observations for i in o.items
        }
        assert len({p_ for p_, _ in pages}) >= 2, "연령이 다른데 같은 면이다"


# ============================================== §34 / §35


@pytest.mark.parametrize(
    "text", ["물놀이 공원 만들기", "물총놀이", "여름 과일 신체 놀이하기"]
)
def test_july_age4_grounding_survives(builder, text):
    assert text in grounding_texts(builder.build(request("2026-07", (4,))))


@pytest.mark.parametrize(
    "text", ["움직이는 교통기관 관찰해요", "우리동네 버스 정류장을 살펴봐요"]
)
def test_august_age4_grounding_survives(builder, text):
    assert text in grounding_texts(builder.build(request("2026-08", (4,))))


def test_august_source_diversity_is_not_broken_by_assembly(builder):
    p = builder.build(request("2026-08", (4,)))
    groups = [i.audit.source_diversity_group for i in p.other_outdoor_evidence]
    for g in set(groups):
        assert groups.count(g) <= 2


# ============================================== §36 2027-02 만5세


def test_february_age5_scarcity_is_supplemented(builder):
    p = builder.build(request("2027-02", (5,)))
    sizes = p.block_sizes()
    assert sizes[PackedBlock.REFERENCE_ACTIVITIES] == 4
    assert sizes[PackedBlock.OTHER_OUTDOOR] >= 8
    assert sizes[PackedBlock.WEEK_EXPERIENCE] >= 8
    assert len({i.source_group for i in p.other_outdoor_evidence}) >= 3


# ============================================== §37 연령 차별화


def test_july_age3_and_age4_packets_differ(builder):
    a3 = builder.build(request("2026-07", (3,)))
    a4 = builder.build(request("2026-07", (4,)))
    ids3 = {i.evidence_id for i in a3.institution_evidence}
    ids4 = {i.evidence_id for i in a4.institution_evidence}
    assert ids3 and ids4
    assert not (ids3 & ids4)
    assert packet_fingerprint(a3) != packet_fingerprint(a4)


@pytest.mark.parametrize("age", [3, 4, 5])
def test_age_context_is_computed_for_each_age(builder, age):
    p = builder.build(request("2026-07", (age,)))
    assert len(p.age_context.per_age) == 1
    assert p.age_context.per_age[0].age == age
    assert p.age_context.per_age[0].single_age_institution_count > 0


def test_mixed_age_request_reports_both_ages(builder):
    p = builder.build(request("2026-07", (4, 5)))
    assert [s.age for s in p.age_context.per_age] == [4, 5]
    assert p.age_context.requested_ages == (4, 5)
    validate_packet(p)


# ============================================== 결정론


@pytest.mark.parametrize("tm,ages", CASES)
def test_same_request_gives_the_same_fingerprint(builder, tm, ages):
    req = request(tm, ages)
    assert packet_fingerprint(builder.build(req)) == packet_fingerprint(
        builder.build(req)
    )


def test_a_fresh_builder_gives_the_same_fingerprint(catalog):
    store = JsonInstitutionEvidenceRepository().get_store()
    fresh = MonthlyContextPacketBuilder(
        MonthlyEvidenceRetriever(store, activity_catalog=catalog),
        store,
        activity_catalog=catalog,
    )
    other_store = JsonInstitutionEvidenceRepository().get_store()
    other = MonthlyContextPacketBuilder(
        MonthlyEvidenceRetriever(other_store, activity_catalog=catalog),
        other_store,
        activity_catalog=catalog,
    )
    req = request("2026-07", (4,))
    assert packet_fingerprint(fresh.build(req)) == packet_fingerprint(
        other.build(req)
    )


def test_age_context_reports_actual_single_age_grounding_in_the_packet(builder):
    """등급과 Packet 내용이 어긋날 수 있다는 사실을 숨기지 않는다.

    2027-02 만5세는 단3(STRONG)이지만 Packet에 실제로 담긴 만5세 단일연령
    근거는 1건뿐이다 — 바깥놀이 행이 있는 만5세 면이 그만큼밖에 없기 때문이다.
    """
    feb = builder.build(request("2027-02", (5,)))
    assert feb.age_context.per_age[0].single_age_institution_count >= 3
    assert feb.age_context.single_age_grounding_count == 1

    july = builder.build(request("2026-07", (4,)))
    assert july.age_context.single_age_grounding_count >= 4
