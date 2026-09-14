"""실제 Evidence Store + 승인 Catalog로 하는 Retrieval 품질 회귀 (L2).

Artifact가 없으면 skip한다. 있으면 §26~§28이 지정한 Case를 고정한다.
**없는 값을 만들어 테스트하지 않는다** — Store에 실제로 있는 문자열만 확인한다.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from ssuksak.adapters.json_activity_reference_repository import (
    production_activity_reference_repository,
)
from ssuksak.planning.retrieval import (
    DEFAULT_EVIDENCE_STORE_PATH,
    BlockName,
    JsonInstitutionEvidenceRepository,
    MonthlyEvidenceRetriever,
    RetrievalRequest,
)

ROOT = pathlib.Path(__file__).resolve().parents[2]
CATALOG_ID = "ssuksak.outdoor-activity-reference"
CATALOG_VERSION = "activity-reference-v0.2.1"

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


@pytest.fixture(scope="module")
def retriever() -> MonthlyEvidenceRetriever:
    store = JsonInstitutionEvidenceRepository().get_store()
    catalog = production_activity_reference_repository().get_catalog(
        CATALOG_ID, CATALOG_VERSION
    )
    return MonthlyEvidenceRetriever(store, activity_catalog=catalog)


def req(target_month: str, month: int, ages: tuple[int, ...], weeks: int = 4):
    tid, label = THEME_BY_MONTH[month]
    return RetrievalRequest(
        target_month=target_month, calendar_month=month, ages=ages,
        age_mode="SINGLE" if len(ages) == 1 else "MIXED",
        confirmed_theme_id=tid, confirmed_theme_value=label, week_count=weeks,
    )


def grounding_texts(result) -> set[str]:
    return {
        i.text
        for name in (BlockName.INSTITUTION_MONTHLY_EVIDENCE,
                     BlockName.AGE_CONTRAST_EVIDENCE,
                     BlockName.OTHER_OUTDOOR_EVIDENCE)
        for i in result.blocks[name].items
    }


CASES = [
    ("2026-03", 3, (3,), 4),
    ("2026-06", 6, (4,), 4),
    ("2026-07", 7, (4,), 5),
    ("2026-08", 8, (4,), 4),
    ("2027-02", 2, (5,), 4),
]


# ============================================== 전 Case 기본 성질


@pytest.mark.parametrize("tm,month,ages,weeks", CASES)
def test_every_block_is_present(retriever, tm, month, ages, weeks):
    res = retriever.retrieve(req(tm, month, ages, weeks))
    assert set(res.blocks) == set(BlockName)


@pytest.mark.parametrize("tm,month,ages,weeks", CASES)
def test_no_invalid_or_needs_review_leaks(retriever, tm, month, ages, weeks):
    res = retriever.retrieve(req(tm, month, ages, weeks))
    for name in BlockName:
        for item in res.blocks[name].items:
            assert item.record.extraction_quality.value == "VALID"
            assert item.record.machine_readability.value == "TEXT_LAYER"


@pytest.mark.parametrize("tm,month,ages,weeks", CASES)
def test_no_indoor_alternative_in_outdoor_blocks(retriever, tm, month, ages, weeks):
    res = retriever.retrieve(req(tm, month, ages, weeks))
    for name in (BlockName.INSTITUTION_MONTHLY_EVIDENCE,
                 BlockName.AGE_CONTRAST_EVIDENCE,
                 BlockName.OTHER_OUTDOOR_EVIDENCE):
        for item in res.blocks[name].items:
            assert item.record.setting.value == "OUTDOOR"


@pytest.mark.parametrize("tm,month,ages,weeks", CASES)
def test_institution_cap_holds(retriever, tm, month, ages, weeks):
    res = retriever.retrieve(req(tm, month, ages, weeks))
    for name in (BlockName.INSTITUTION_MONTHLY_EVIDENCE,
                 BlockName.WEEK_EXPERIENCE_CANDIDATES,
                 BlockName.OTHER_OUTDOOR_EVIDENCE):
        groups = [i.trace.source_diversity_group
                  for i in res.blocks[name].items]
        for g in set(groups):
            assert groups.count(g) <= 2, f"{name.value}: {g} 초과"


@pytest.mark.parametrize("tm,month,ages,weeks", CASES)
def test_week_experience_never_carries_a_week_index(retriever, tm, month, ages, weeks):
    res = retriever.retrieve(req(tm, month, ages, weeks))
    for item in res.blocks[BlockName.WEEK_EXPERIENCE_CANDIDATES].items:
        assert item.record.week_position is None
        assert item.record.week_label is None


@pytest.mark.parametrize("tm,month,ages,weeks", CASES)
def test_result_carries_store_and_catalog_identity(retriever, tm, month, ages, weeks):
    res = retriever.retrieve(req(tm, month, ages, weeks))
    assert res.evidence_store_version == "institution-evidence-ingestion-v0.1.0"
    assert res.activity_catalog_version == CATALOG_VERSION


# ============================================== §26 2026-06 만4세


@pytest.mark.parametrize(
    "text", ["우리동네를 둘러보아요", "모래로 동네 공원만들기", "깨끗한 우리 동네 만들기"]
)
def test_june_age4_recovers_grounding_rule_only_missed(retriever, text):
    """Rule-only 최악 Case. 신규 Corpus 근거가 Retrieval에 들어와야 한다."""
    assert text in grounding_texts(retriever.retrieve(req("2026-06", 6, (4,))))


@pytest.mark.parametrize(
    "label", ["우리 동네 지도 보며 산책하기", "모래 위에 그리는 우리 동네"]
)
def test_june_age4_reference_block_includes_candidates_rule_never_selected(
    retriever, label
):
    """Rule의 최종 선택이 `activity_id` 해시 순서로 탈락시켰던 후보들이다."""
    res = retriever.retrieve(req("2026-06", 6, (4,)))
    labels = {c.label
              for c in res.blocks[BlockName.REFERENCE_ACTIVITIES].reference_items}
    assert label in labels


# ============================================== §27 2026-07 / 08 만4세


@pytest.mark.parametrize(
    "text", ["물놀이 공원 만들기", "물총놀이", "여름 과일 신체 놀이하기"]
)
def test_july_age4_recovers_new_corpus_evidence(retriever, text):
    assert text in grounding_texts(retriever.retrieve(req("2026-07", 7, (4,), 5)))


@pytest.mark.parametrize(
    "text", ["움직이는 교통기관 관찰해요", "우리동네 버스 정류장을 살펴봐요"]
)
def test_august_age4_recovers_new_corpus_evidence(retriever, text):
    assert text in grounding_texts(retriever.retrieve(req("2026-08", 8, (4,))))


# ============================================== §28 2027-02 만5세


def test_february_age5_scarcity_is_supplemented_by_corpus_evidence(retriever):
    """canonical 후보가 주차 수와 같은 Case. Corpus가 보완하는지 본다."""
    res = retriever.retrieve(req("2027-02", 2, (5,)))
    reference = res.blocks[BlockName.REFERENCE_ACTIVITIES]
    other = res.blocks[BlockName.OTHER_OUTDOOR_EVIDENCE]
    week = res.blocks[BlockName.WEEK_EXPERIENCE_CANDIDATES]

    assert reference.eligible_pool_size == 4
    assert reference.size == 4          # 억지로 12개를 채우지 않는다
    assert other.size >= 8              # Corpus가 보완한다
    assert week.size >= 8
    assert other.distinct_institutions >= 3


def test_reference_block_returns_all_when_pool_is_smaller_than_top_k(retriever):
    for tm, month, ages, weeks in CASES:
        res = retriever.retrieve(req(tm, month, ages, weeks))
        block = res.blocks[BlockName.REFERENCE_ACTIVITIES]
        assert block.size == min(block.eligible_pool_size, block.top_k)


# ============================================== §29 연령 차별화


def test_july_age3_and_age4_institution_blocks_differ(retriever):
    a3 = retriever.retrieve(req("2026-07", 7, (3,), 5))
    a4 = retriever.retrieve(req("2026-07", 7, (4,), 5))
    ids3 = {i.record_id
            for i in a3.blocks[BlockName.INSTITUTION_MONTHLY_EVIDENCE].items}
    ids4 = {i.record_id
            for i in a4.blocks[BlockName.INSTITUTION_MONTHLY_EVIDENCE].items}
    assert ids3 and ids4
    assert not (ids3 & ids4), "만3세와 만4세 Institution Block이 완전히 겹친다"


def test_age_contrast_pairs_come_from_one_document(retriever):
    res = retriever.retrieve(req("2026-07", 7, (4,), 5))
    items = res.blocks[BlockName.AGE_CONTRAST_EVIDENCE].items
    assert items
    by_source: dict[str, set[int]] = {}
    for i in items:
        by_source.setdefault(i.record.source_sha256, set()).add(i.record.single_age)
    assert any(len(v) >= 2 for v in by_source.values())


# ============================================== 결정론


@pytest.mark.parametrize("tm,month,ages,weeks", CASES)
def test_same_request_returns_identical_result(retriever, tm, month, ages, weeks):
    a = retriever.retrieve(req(tm, month, ages, weeks))
    b = retriever.retrieve(req(tm, month, ages, weeks))
    for name in BlockName:
        assert [i.record_id for i in a.blocks[name].items] == [
            i.record_id for i in b.blocks[name].items
        ]
        assert [i.activity_id for i in a.blocks[name].reference_items] == [
            i.activity_id for i in b.blocks[name].reference_items
        ]


def test_a_fresh_store_instance_gives_the_same_result(retriever):
    fresh = MonthlyEvidenceRetriever(
        JsonInstitutionEvidenceRepository().get_store(),
        activity_catalog=production_activity_reference_repository().get_catalog(
            CATALOG_ID, CATALOG_VERSION
        ),
    )
    r = req("2026-07", 7, (4,), 5)
    a, b = retriever.retrieve(r), fresh.retrieve(r)
    for name in BlockName:
        assert [i.record_id for i in a.blocks[name].items] == [
            i.record_id for i in b.blocks[name].items
        ]
