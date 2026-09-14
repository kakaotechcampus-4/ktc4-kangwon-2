"""L5 핵심 Acceptance — L4 Live Smoke에서 실제로 나온 결함 (§29).

여기 쓰인 Proposal 값은 **GPT-4.1 mini가 실제로 반환한 문자열**이다
(`analysis/tmp/l4_live_smoke.txt` · L4 보고서 §14.3). 지어낸 값이 아니다.

    v0.1.0  2027-02 만5세 W4  "내 키만큼 멀리 뛰기"        = E14 (institution)
    v0.1.1  2026-07 만4세 W3  "여름 과일 신체 놀이하기"    = E06 (age contrast)

둘 다 `CONTEXT_ONLY` 근거 문장의 글자 그대로 복사이며 승인 Catalog에 없는
문자열이다. Prompt 강화로 사라지지 않았으므로 Validator가 반드시 잡아야 한다.

**실제 API를 호출하지 않는다.** 관찰된 출력을 Fixture로 재구성해 검증한다.
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
)
from ssuksak.planning.domain.identifiers import PeriodKey
from ssuksak.planning.domain.parent_lineage import ParentYearlyLineage
from ssuksak.planning.planner import build_monthly_planner_request
from ssuksak.planning.retrieval import (
    DEFAULT_EVIDENCE_STORE_PATH,
    JsonInstitutionEvidenceRepository,
    MonthlyEvidenceRetriever,
)
from ssuksak.planning.rules.monthly_llm_validation import (
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

ROOT = pathlib.Path(__file__).resolve().parents[2]
CATALOG_ID = "ssuksak.outdoor-activity-reference"
CATALOG_VERSION = "activity-reference-v0.2.1"
MODEL = "openai/gpt-4.1-mini"

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
def builder():
    store = JsonInstitutionEvidenceRepository().get_store()
    catalog = production_activity_reference_repository().get_catalog(
        CATALOG_ID, CATALOG_VERSION
    )
    return MonthlyContextPacketBuilder(
        MonthlyEvidenceRetriever(store, activity_catalog=catalog),
        store,
        activity_catalog=catalog,
    )


def packet_of(builder, target_month: str, ages: tuple[int, ...]):
    key = PeriodKey(target_month)
    theme_id, label = THEME_BY_MONTH[key.calendar_month]
    return builder.build(
        MonthlyContextRequest(
            school_year="2026",
            target_month=key,
            classroom_ages=ages,
            age_mode="SINGLE",
            parent_lineage=ParentYearlyLineage(
                parent_yearly_plan_id="yp_l5_fixture",
                parent_yearly_period_key=target_month,
                parent_yearly_theme_id=theme_id,
                parent_yearly_value=label,
                reference_catalog_id=_THEMES["catalog_id"],
                reference_version=_THEMES["catalog_version"],
                confirmed_at=datetime.datetime(2026, 2, 20, 9, 0, tzinfo=datetime.UTC),
                confirmed_by="actor_l5",
            ),
        )
    )


def reference(packet, label: str) -> ProposedActivity:
    activity_id = next(
        a.activity_id for a in packet.reference_activities if a.label == label
    )
    return ProposedActivity(
        value=label,
        origin=ProposedActivityOrigin.REFERENCE,
        reference_activity_id=activity_id,
        grounding_refs=[],
    )


def synthesized(value: str, refs: list[str]) -> ProposedActivity:
    return ProposedActivity(
        value=value,
        origin=ProposedActivityOrigin.LLM_SYNTHESIZED,
        reference_activity_id=None,
        grounding_refs=refs,
    )


def validate(packet, proposal):
    return validate_monthly_proposal(
        proposal, packet, build_monthly_planner_request(packet), planner_model=MODEL
    )


# ============================================== v0.1.1 실측 결함


@pytest.fixture
def july_packet(builder):
    return packet_of(builder, "2026-07", (4,))


def july_proposal(packet, w3_activity) -> MonthlyPlanProposal:
    """GPT-4.1 mini가 실제로 반환한 2026-07 만4세 계획 (prompt v0.1.1)."""
    ids = [w.week_id for w in packet.week_slots]
    return MonthlyPlanProposal(
        theme_id=packet.parent_theme.theme_id,
        month_flow_rationale=(
            "여름이라는 주제를 중심으로 자연과 날씨, 물의 특징을 차례로 탐색하며 "
            "아이들이 여름의 다양한 모습을 온몸으로 느끼고 표현할 수 있도록 구성했습니다."
        ),
        weeks=[
            ProposedWeek(
                week_id=ids[0],
                experience="산책하며 여름 곤충과 자연 풍경을 탐색하며 여름의 특징에 관심을 가져요.",
                activity=reference(packet, "산책하며 여름 곤충 찾기"),
            ),
            ProposedWeek(
                week_id=ids[1],
                experience="맑은 여름 하늘을 셀로판지로 관찰하며 날씨의 변화를 이해해요.",
                activity=reference(packet, "셀로판지로 여름 하늘 바라보기"),
            ),
            ProposedWeek(
                week_id=ids[2],
                experience="여름 제철 과일을 몸으로 표현하며 즐겨요.",
                activity=w3_activity,
            ),
            ProposedWeek(
                week_id=ids[3],
                experience="물총놀이로 여름의 시원함을 경험해요.",
                activity=reference(packet, "물총을 쏴 종이컵 무너뜨리기"),
            ),
            ProposedWeek(
                week_id=ids[4],
                experience="그늘에서 쉬며 여름 더위를 건강하게 보내요.",
                activity=reference(packet, "그늘에서 휴식하기"),
            ),
        ],
    )


def test_the_july_source_copy_is_rejected(july_packet):
    """L5 핵심 Acceptance. 실제로 나온 복사를 잡지 못하면 L5는 의미가 없다."""
    result = validate(
        july_packet,
        july_proposal(july_packet, synthesized("여름 과일 신체 놀이하기", ["E06"])),
    )
    assert not result.is_valid
    assert ProposalViolationCode.SYNTHESIZED_EXACT_SOURCE_COPY in result.codes

    copy = next(
        v for v in result.violations
        if v.code is ProposalViolationCode.SYNTHESIZED_EXACT_SOURCE_COPY
    )
    assert copy.week_id == july_packet.week_slots[2].week_id
    assert copy.field == "activity.value"
    assert "E06" in copy.detail


def test_the_july_copy_is_repairable(july_packet):
    result = validate(
        july_packet,
        july_proposal(july_packet, synthesized("여름 과일 신체 놀이하기", ["E06"])),
    )
    assert result.is_repairable
    assert result.repair_summary


def test_the_july_copy_detail_does_not_repeat_the_source_text(july_packet):
    result = validate(
        july_packet,
        july_proposal(july_packet, synthesized("여름 과일 신체 놀이하기", ["E06"])),
    )
    for violation in result.violations:
        assert "여름 과일 신체 놀이하기" not in violation.detail
    for hint in result.repair_summary:
        assert "여름 과일 신체 놀이하기" not in hint


def test_the_same_july_plan_with_new_wording_passes(july_packet):
    """Detector가 Synthesized를 통째로 막는 Guard가 되면 안 된다 (§30)."""
    result = validate(
        july_packet,
        july_proposal(
            july_packet, synthesized("제철 과일 흉내 내며 몸으로 표현하기", ["E06"])
        ),
    )
    assert result.is_valid, [str(v) for v in result.violations]


def test_the_july_reference_weeks_are_not_flagged_as_copies(july_packet):
    """승인 label 그대로 사용은 정상이다 (§8)."""
    result = validate(
        july_packet,
        july_proposal(
            july_packet, synthesized("제철 과일 흉내 내며 몸으로 표현하기", ["E06"])
        ),
    )
    assert ProposalViolationCode.SYNTHESIZED_EXACT_SOURCE_COPY not in result.codes
    assert ProposalViolationCode.DUPLICATE_ACTIVITY not in result.codes


def test_e06_really_is_a_context_only_source(july_packet):
    """Fixture가 실제 Packet 구조에 근거하는지 확인한다."""
    index = build_packet_index(july_packet)
    assert "E06" in index.by_ref
    grounded = index.by_ref["E06"]
    assert grounded.reuse_policy == "CONTEXT_ONLY"
    assert grounded.text == "여름 과일 신체 놀이하기"
    assert "여름 과일 신체 놀이하기" not in {
        a.label for a in july_packet.reference_activities
    }


# ============================================== v0.1.0 실측 결함


@pytest.fixture
def february_packet(builder):
    return packet_of(builder, "2027-02", (5,))


def february_proposal(packet, w4_activity) -> MonthlyPlanProposal:
    """GPT-4.1 mini가 실제로 반환한 2027-02 만5세 계획 (prompt v0.1.0)."""
    ids = [w.week_id for w in packet.week_slots]
    return MonthlyPlanProposal(
        theme_id=packet.parent_theme.theme_id,
        month_flow_rationale=(
            "이번 2월은 만 5세 아이들이 한 해 동안의 성장과 변화를 돌아보고, "
            "앞으로의 새로운 시작을 준비하는 흐름으로 구성했습니다."
        ),
        weeks=[
            ProposedWeek(
                week_id=ids[0],
                experience="지난 시간을 돌아보며 자신과 친구들의 변화를 느껴요.",
                activity=reference(packet, "우리가 좋아했던 장소 산책하기"),
            ),
            ProposedWeek(
                week_id=ids[1],
                experience="우리나라 전통 명절인 설날의 의미와 풍습을 경험해요.",
                activity=reference(packet, "산책하며 동네 이웃에게 설날 인사드리기"),
            ),
            ProposedWeek(
                week_id=ids[2],
                experience="우리 반의 소중한 추억과 자신이 많이 자란 모습을 돌아봐요.",
                activity=reference(packet, "모래 위에 형님이 된 내 모습 그리기"),
            ),
            ProposedWeek(
                week_id=ids[3],
                experience="높아진 키와 몸의 변화에 맞춰 뛰고 점프하며 건강한 성장에 기뻐해요.",
                activity=w4_activity,
            ),
        ],
    )


def test_the_february_source_copy_is_rejected(february_packet):
    result = validate(
        february_packet,
        february_proposal(
            february_packet, synthesized("내 키만큼 멀리 뛰기", ["E04", "E14"])
        ),
    )
    assert not result.is_valid
    assert ProposalViolationCode.SYNTHESIZED_EXACT_SOURCE_COPY in result.codes

    copy = next(
        v for v in result.violations
        if v.code is ProposalViolationCode.SYNTHESIZED_EXACT_SOURCE_COPY
    )
    assert copy.week_id == february_packet.week_slots[3].week_id
    assert "E14" in copy.detail


def test_e14_really_is_a_context_only_source(february_packet):
    index = build_packet_index(february_packet)
    assert "E14" in index.by_ref
    assert index.by_ref["E14"].text == "내 키만큼 멀리 뛰기"
    assert index.by_ref["E14"].reuse_policy == "CONTEXT_ONLY"


def test_the_february_v011_plan_passes(february_packet):
    """prompt v0.1.1의 2027-02 결과는 전부 REFERENCE였고 통과해야 한다."""
    ids = [w.week_id for w in february_packet.week_slots]
    proposal = MonthlyPlanProposal(
        theme_id=february_packet.parent_theme.theme_id,
        month_flow_rationale=(
            "한 해의 성장을 돌아보고 새로운 시작을 준비하는 흐름으로 구성했습니다."
        ),
        weeks=[
            ProposedWeek(
                week_id=ids[0],
                experience="많이 자란 내 모습을 모래 위에 그리며 성장을 느껴요.",
                activity=reference(february_packet, "모래 위에 형님이 된 내 모습 그리기"),
            ),
            ProposedWeek(
                week_id=ids[1],
                experience="좋아했던 장소를 다시 걸으며 한 해를 회상해요.",
                activity=reference(february_packet, "우리가 좋아했던 장소 산책하기"),
            ),
            ProposedWeek(
                week_id=ids[2],
                experience="설날의 의미와 풍습을 이웃과 나누며 경험해요.",
                activity=reference(
                    february_packet, "산책하며 동네 이웃에게 설날 인사드리기"
                ),
            ),
            ProposedWeek(
                week_id=ids[3],
                experience="전통놀이로 몸을 움직이며 친구와 즐거움을 나눠요.",
                activity=reference(february_packet, "사방치기"),
            ),
        ],
    )
    result = validate(february_packet, proposal)
    assert result.is_valid, [str(v) for v in result.violations]
    assert all(d.is_complete for d in result.provenance)


# ============================================== 실제 Packet 위생


@pytest.mark.parametrize("target_month,ages", [("2026-07", (4,)), ("2027-02", (5,))])
def test_real_packets_contain_only_eligible_grounding(builder, target_month, ages):
    """`INELIGIBLE_GROUNDING`이 평상시에 발동하지 않아야 한다."""
    index = build_packet_index(packet_of(builder, target_month, ages))
    assert index.by_ref
    for grounded in index.by_ref.values():
        assert grounded.is_eligible
        assert grounded.reuse_policy == "CONTEXT_ONLY"


@pytest.mark.parametrize("target_month,ages", [("2026-07", (4,)), ("2027-02", (5,))])
def test_reference_candidates_support_the_requested_ages(builder, target_month, ages):
    """L2 hard filter가 이미 보장하지만 저장 직전에 다시 본다."""
    packet = packet_of(builder, target_month, ages)
    for candidate in packet.reference_activities:
        assert set(ages) <= set(candidate.supported_ages)
