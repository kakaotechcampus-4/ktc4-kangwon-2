"""Monthly **LLM Planner** Golden (L9).

`test_monthly_cases.py`(Rule-only)를 대체하지 않는다. 두 Golden은 서로 다른
것을 지킨다.

    monthly_cases.json       Rule 경로의 기존 동작 — legacy regression anchor
    monthly_llm_cases.json   LLM 경로의 **Application 계약**

여기서 고정하는 것은 "GPT가 무슨 문장을 쓰는가"가 아니라 **"주어진 Proposal에
대해 Application이 무엇을 하는가"**다. 실제 모델 문장을 expected로 박으면
모델이 정상적인 다른 문장을 만들었을 때 회귀 실패가 되고, Golden이 품질
장치가 아니라 방해물이 된다. 자연어 품질은 Live Quality Smoke가 사람 관찰로
다룬다.

각 test는 `monthly_llm_cases.json`의 case를 참조한다. **새 결과가 나왔다는
이유로 expected를 갱신하지 않는다** — 계약이 바뀐 것인지 회귀인지 먼저
판단하고, 계약 변경이면 보고서에 남긴다.
"""

from __future__ import annotations

import pytest

from ssuksak.planning.domain.constraint import CellState, ConstraintVerification
from ssuksak.planning.domain.errors import (
    FailureCategory,
    PlanningError,
    Outcome,
)
from ssuksak.planning.domain.plan import PlanStatus
from ssuksak.planning.domain.provenance import (
    AuditEventType,
    EvidenceSourceType,
    GenerationMethod,
)
from ssuksak.shared.llm.fake import FakeLLMMode
from ssuksak.shared.llm.port import LLMUnavailableError

from . import monthly_llm_harness as H

FROZEN = H.FROZEN


# =============================================================== Suite 자체


def test_suite_declares_its_scope_and_does_not_replace_the_rule_only_golden():
    assert H.SUITE["contract_stage"] == "L9_FINAL_FREEZE"
    assert "monthly_cases.json" in H.SUITE["scope_note"]
    # 실제 모델 문장을 exact match하지 않는다는 정책을 suite가 명시한다.
    forbidden = H.SUITE["assertion_policy"]["exact_text_forbidden"]
    assert any("GPT" in f for f in forbidden)


def test_every_case_is_covered_by_a_test():
    """JSON에 case를 추가하고 test를 잊는 것을 막는다."""
    declared = {c["case_id"] for c in H.SUITE["cases"]}
    source = (H.SUITE_PATH.parent / "test_monthly_llm_cases.py").read_text("utf-8")
    missing = {cid for cid in declared if f'case("{cid}")' not in source}
    assert not missing, f"case는 선언됐지만 test가 없다: {sorted(missing)}"


def test_the_rule_only_golden_suite_is_untouched():
    """L9 §2 — 기존 Golden expected를 LLM 결과로 덮어쓰지 않았다."""
    import hashlib

    here = H.SUITE_PATH.parent
    frozen = {
        "monthly_cases.json": "cbe8571269480a80",
        "yearly_cases.json": "94668b90613e798b",
    }
    for name, prefix in frozen.items():
        digest = hashlib.sha256((here / name).read_bytes()).hexdigest()
        assert digest.startswith(prefix), (
            f"{name}의 SHA가 바뀌었다. LLM 작업이 Rule-only Golden을 건드렸는지 "
            f"확인하라. 의도한 변경이면 보고서에 남기고 이 값을 갱신한다."
        )


# =============================================================== Generate


def test_llm_generate_reference_only():
    expected = H.case("llm_generate_reference_only")["expected"]
    h = H.LlmGoldenHarness()

    result = H.generate(h)

    assert result.plan.status is PlanStatus[expected["status"]]
    assert result.run.generation_mode == expected["generation_mode"]
    assert result.plan.template_ref.template_version == expected["template_version"]
    assert h.monthly_plan_persisted is expected["monthly_plan_persisted"]
    assert h.save_count == expected["save_count"]
    assert result.run.llm_call_count == expected["llm_call_count"]
    assert (
        result.run.planner_validation_repair_count
        == expected["validation_repair_count"]
    )

    weeks = [w for w in result.plan.week_periods if w.active]
    assert len(weeks) == expected["week_count"]
    focus = H.section_items(result.plan, H.FOCUS)
    assert len(focus) == len(weeks)
    assert all(i.cell_state is CellState.FILLED for i in focus)

    outdoor = H.section_items(result.plan, H.OUTDOOR)
    origins = [
        "REFERENCE"
        if i.evidence_of_type(EvidenceSourceType.ACTIVITY_REFERENCE)
        else "LLM_SYNTHESIZED"
        for i in outdoor
    ]
    assert origins == expected["outdoor_origins"]


def test_llm_generate_mixed_origins():
    expected = H.case("llm_generate_mixed_origins")["expected"]
    h = H.LlmGoldenHarness()
    packet = h.packet(H.CASE_B_MONTH)
    h.llm.set_monthly_proposal(H.mixed_proposal(packet))

    result = h.generate.execute(H.generate_command(target_month=H.CASE_B_MONTH))

    assert result.plan.status is PlanStatus[expected["status"]]
    assert h.monthly_plan_persisted is expected["monthly_plan_persisted"]
    assert h.save_count == expected["save_count"]
    assert result.run.llm_call_count == expected["llm_call_count"]

    outdoor = H.section_items(result.plan, H.OUTDOOR)
    assert len(outdoor) == expected["week_count"]

    origins = []
    for item in outdoor:
        reference = item.evidence_of_type(EvidenceSourceType.ACTIVITY_REFERENCE)
        grounding = item.evidence_of_type(EvidenceSourceType.INSTITUTION_SAMPLE)
        assert bool(reference) != bool(grounding), (
            "한 Cell이 승인 Catalog 출처와 기관 Corpus 근거를 동시에 주장하지 "
            "않는다 — 두 축은 다른 의미다"
        )
        origins.append("REFERENCE" if reference else "LLM_SYNTHESIZED")
        assert item.generation.method is GenerationMethod.RULE_LLM
    assert origins == expected["outdoor_origins"]

    # 새로 쓴 활동은 **실제 Evidence record**를 근거로 남기고, source_version은
    # Evidence Store의 content SHA다. 임의 문자열이 아니다.
    store_sha = result.run.evidence_store_sha256
    assert store_sha
    for item in outdoor:
        for source in item.evidence_of_type(EvidenceSourceType.INSTITUTION_SAMPLE):
            assert source.source_id in {r.record_id for r in H.GOLDEN_RECORDS}
            assert source.source_version == store_sha


def test_llm_generate_requires_focus_template():
    expected = H.case("llm_generate_requires_focus_template")["expected"]
    h = H.LlmGoldenHarness()

    with pytest.raises(PlanningError) as exc:
        H.generate(h, template_version=H.RULE_ONLY_TEMPLATE_VERSION)

    assert exc.value.violated_rule == expected["violated_rule"]
    assert exc.value.outcome is Outcome[expected["outcome"]]
    assert exc.value.failure_category is FailureCategory.PREREQUISITE_GATE
    assert h.monthly_plan_persisted is expected["monthly_plan_persisted"]
    # Template이 안 맞으면 **호출 전에** 막는다. 비용을 쓰고 버리지 않는다.
    assert (h.llm.monthly_call_count > 0) is expected["llm_called"]


def test_llm_generate_requires_planner_dependency():
    expected = H.case("llm_generate_requires_planner_dependency")["expected"]
    h = H.LlmGoldenHarness(with_planner=False)

    with pytest.raises(PlanningError) as exc:
        h.generate.execute(H.generate_command())

    assert exc.value.violated_rule == expected["violated_rule"]
    assert exc.value.outcome is Outcome[expected["outcome"]]
    assert h.monthly_plan_persisted is expected["monthly_plan_persisted"]


def test_llm_generate_unavailable_saves_nothing():
    expected = H.case("llm_generate_unavailable_saves_nothing")["expected"]
    h = H.LlmGoldenHarness(llm=H.SequencedFakeLLM(mode=FakeLLMMode.UNAVAILABLE))

    with pytest.raises(LLMUnavailableError):
        H.generate(h)

    assert h.monthly_plan_persisted is expected["monthly_plan_persisted"]
    assert h.save_count == expected["save_count"]


def test_llm_generate_rejected_proposal_saves_nothing():
    expected = H.case("llm_generate_rejected_proposal_saves_nothing")["expected"]
    h = H.LlmGoldenHarness()
    packet = h.packet(H.CASE_B_MONTH)
    copies = H.mixed_proposal(packet, synthesized_value=H.COPYABLE_SOURCE_TEXT)
    h.llm.queue_monthly(copies, copies)  # repair 후에도 고치지 못한다

    with pytest.raises(PlanningError) as exc:
        h.generate.execute(H.generate_command(target_month=H.CASE_B_MONTH))

    assert exc.value.violated_rule == expected["violated_rule"]
    assert exc.value.failure_category is FailureCategory.LLM_OUTPUT_VALIDATION
    assert h.monthly_plan_persisted is expected["monthly_plan_persisted"]
    assert h.llm.monthly_call_count == expected["llm_call_count"]
    # 위반 **식별자**만 나가고 Source 원문은 나가지 않는다 (L5 §24).
    assert H.COPYABLE_SOURCE_TEXT not in str(exc.value)


def test_llm_generate_repair_then_success():
    expected = H.case("llm_generate_repair_then_success")["expected"]
    h = H.LlmGoldenHarness()
    packet = h.packet(H.CASE_B_MONTH)
    h.llm.queue_monthly(
        H.mixed_proposal(packet, synthesized_value=H.COPYABLE_SOURCE_TEXT),
        H.mixed_proposal(packet),
    )

    result = h.generate.execute(H.generate_command(target_month=H.CASE_B_MONTH))

    assert result.plan.status is PlanStatus[expected["status"]]
    assert h.save_count == expected["save_count"]
    assert result.run.llm_call_count == expected["llm_call_count"]
    assert (
        result.run.planner_validation_repair_count
        == expected["validation_repair_count"]
    )
    assert result.run.planner_repaired_violations, (
        "무엇을 고쳤는지 남지 않으면 repair가 조용한 재시도가 된다"
    )


def test_llm_generate_configuration_missing():
    """설정 부재는 일시 장애와 **다른** 실패다 (L9 §13)."""
    from ssuksak.shared.llm.port import LLMConfigurationError

    expected = H.case("llm_generate_configuration_missing")["expected"]
    h = H.LlmGoldenHarness(llm=H.MisconfiguredLLM())

    with pytest.raises(LLMConfigurationError):
        H.generate(h)

    assert h.monthly_plan_persisted is expected["monthly_plan_persisted"]
    assert h.save_count == expected["save_count"]


# ================================================= 실패 의미 (L9 §13)


def test_failure_semantics_table_is_complete():
    kinds = H.SUITE["failure_semantics"]["kinds"]
    assert len(kinds) == 7
    declared = {c["case_id"] for c in H.SUITE["cases"]}
    for entry in kinds:
        assert entry["case_id"] in declared
        assert entry["saved"] is False, "어떤 실패도 Plan을 저장하지 않는다"


def test_no_failure_path_falls_back_to_rule_only():
    """L9 §13 · OD-N15 — 실패가 조용히 Rule 결과로 바뀌지 않는다."""
    from ssuksak.shared.llm.port import LLMConfigurationError

    failures = (
        (H.LlmGoldenHarness(llm=H.SequencedFakeLLM(mode=FakeLLMMode.UNAVAILABLE)),
         LLMUnavailableError),
        (H.LlmGoldenHarness(llm=H.MisconfiguredLLM()), LLMConfigurationError),
        (H.LlmGoldenHarness(with_planner=False), PlanningError),
    )
    for harness, error in failures:
        with pytest.raises(error):
            if harness.cell_regenerator is None:
                harness.generate.execute(H.generate_command())
            else:
                H.generate(harness)
        assert harness.save_count == 0


# ============================================================ 고정 불변


def test_theme_provenance_is_frozen():
    """Theme은 확정 Yearly에서 Rule이 파생한다. LLM이 만들지 않는다."""
    spec = FROZEN["theme_provenance"]
    h = H.LlmGoldenHarness()
    plan = H.generate(h).plan

    theme = H.section_items(plan, "theme")[0]
    assert theme.generation.method is GenerationMethod[spec["generation_method"]]
    for source_type in spec["evidence_types"]:
        assert theme.evidence_of_type(EvidenceSourceType[source_type])


def test_focus_provenance_is_frozen():
    spec = FROZEN["focus_provenance"]
    h = H.LlmGoldenHarness()
    plan = H.generate(h).plan

    for item in H.section_items(plan, H.FOCUS):
        assert item.cell_state is CellState[spec["cell_state"]]
        assert item.generation.method is GenerationMethod[spec["generation_method"]]
        # 특정 EvidenceRecord를 직접 근거로 주장하지 않는다 (OD-N18).
        assert list(item.evidence) == spec["evidence"]


def test_safety_semantics_are_frozen():
    spec = FROZEN["safety"]
    h = H.LlmGoldenHarness()
    result = H.generate(h)

    for item in H.section_items(result.plan, "safety_education"):
        assert item.cell_state is CellState[spec["cell_state"]]
        assert list(item.evidence) == spec["evidence"]
    assert result.plan.constraint_assessments[0].verification is (
        ConstraintVerification[spec["verification"]]
    )
    assert result.run.has_unresolved_requirement


def test_forbidden_evidence_source_types_never_appear():
    """`LLM_SYNTHESIZED`는 Evidence Source가 아니다 (CLAUDE.md §13.1)."""
    h = H.LlmGoldenHarness()
    packet = h.packet(H.CASE_B_MONTH)
    h.llm.set_monthly_proposal(H.mixed_proposal(packet))
    plan = h.generate.execute(
        H.generate_command(target_month=H.CASE_B_MONTH)
    ).plan

    seen = {e.source_type.value for item in plan.items for e in item.evidence}
    assert not (seen & set(FROZEN["forbidden_evidence_source_types"]))
    # Enum 자체에도 없다 — 이름만 안 쓰는 것이 아니다.
    assert "LLM_SYNTHESIZED" not in {t.value for t in EvidenceSourceType}


def test_week_ids_are_canonical_not_taken_from_the_proposal():
    h = H.LlmGoldenHarness()
    plan = H.generate(h).plan
    canonical = [w.week_id.value for w in plan.week_periods if w.active]
    for section_key in (H.FOCUS, H.OUTDOOR):
        assert [
            i.week_id.value for i in H.section_items(plan, section_key)
        ] == canonical


# ============================================================= Regenerate


def test_llm_regenerate_focus_target_only():
    expected = H.case("llm_regenerate_focus_target_only")["expected"]
    h = H.LlmGoldenHarness()
    plan = H.generate(h).plan
    before = H.cell_snapshot(plan)
    saves_before = h.save_count

    h.llm.set_cell_proposal(H.focus_proposal(plan, "다시 구성한 중심 경험이에요."))
    result = h.regenerate_item.execute(H.regenerate_command(plan, H.FOCUS))

    after = H.cell_snapshot(result.plan)
    changed = [k for k in before if before[k] != after[k]]
    assert len(changed) == expected["changed_cells"]
    assert set(before) == set(after), "item_id는 재생성에서 유지된다"

    item = H.cell_at(result.plan, H.FOCUS)
    assert item.item_id.value == changed[0]
    assert item.generation.method is GenerationMethod[expected["generation_method"]]
    assert list(item.evidence) == expected["evidence"]
    assert [
        e.event_type.value for e in item.audit.events
    ] == expected["audit_contains"]
    assert h.save_count - saves_before == expected["save_count_delta"]


def test_llm_regenerate_outdoor_target_only():
    expected = H.case("llm_regenerate_outdoor_target_only")["expected"]
    h = H.LlmGoldenHarness()
    plan = H.generate(h).plan
    before = H.cell_snapshot(plan)
    saves_before = h.save_count

    used = {i.value for i in H.section_items(plan, H.OUTDOOR)}
    spare = next(
        a for a in h.packet(H.CASE_A_MONTH).reference_activities
        if a.label not in used
    )
    h.llm.set_cell_proposal(
        H.outdoor_reference_proposal(plan, spare.activity_id, spare.label)
    )
    result = h.regenerate_item.execute(H.regenerate_command(plan, H.OUTDOOR))

    after = H.cell_snapshot(result.plan)
    assert len([k for k in before if before[k] != after[k]]) == (
        expected["changed_cells"]
    )
    item = H.cell_at(result.plan, H.OUTDOOR)
    assert item.value == spare.label
    assert item.generation.method is GenerationMethod[expected["generation_method"]]
    assert h.save_count - saves_before == expected["save_count_delta"]

    # 짝이 되는 focus Cell은 건드리지 않는다.
    assert H.cell_at(result.plan, H.FOCUS).value == H.cell_at(plan, H.FOCUS).value


def test_llm_regenerate_theme_uses_rule_not_llm():
    expected = H.case("llm_regenerate_theme_uses_rule_not_llm")["expected"]
    h = H.LlmGoldenHarness()
    plan = H.generate(h).plan
    calls_before = h.llm.cell_call_count

    result = h.regenerate_item.execute(H.regenerate_command(plan, "theme"))

    theme = H.section_items(result.plan, "theme")[0]
    assert theme.generation.method is GenerationMethod[expected["generation_method"]]
    assert theme.evidence_of_type(EvidenceSourceType.THEME_REFERENCE)
    assert h.llm.cell_call_count - calls_before == expected["cell_llm_call_count"]


def test_llm_regenerate_safety_still_blocked():
    """LLM Plan이어도 안전교육은 배치 source가 없다 (OD-M04)."""
    expected = H.case("llm_regenerate_safety_still_blocked")["expected"]
    h = H.LlmGoldenHarness()
    plan = H.generate(h).plan
    calls_before = h.llm.cell_call_count

    with pytest.raises(PlanningError) as exc:
        h.regenerate_item.execute(H.regenerate_command(plan, "safety_education"))

    assert exc.value.violated_rule == expected["violated_rule"]
    assert exc.value.outcome is Outcome[expected["outcome"]]
    assert h.llm.cell_call_count - calls_before == expected["cell_llm_call_count"]


def test_llm_regenerate_mode_must_match_the_plan():
    """LLM Plan을 RULE_ONLY로 재생성해 달라는 요청은 조합 오류다 (§26)."""
    from ssuksak.planning.application.monthly_dto import MonthlyGenerationMode

    expected = H.case("llm_regenerate_mode_must_match_the_plan")["expected"]
    h = H.LlmGoldenHarness()
    plan = H.generate(h).plan
    calls_before = h.llm.cell_call_count
    saves_before = h.save_count

    with pytest.raises(PlanningError) as exc:
        h.regenerate_item.execute(
            H.regenerate_command(
                plan, H.FOCUS, generation_mode=MonthlyGenerationMode.RULE_ONLY
            )
        )

    assert exc.value.violated_rule == expected["violated_rule"]
    assert exc.value.outcome is Outcome[expected["outcome"]]
    assert h.llm.cell_call_count - calls_before == expected["cell_llm_call_count"]
    assert h.save_count - saves_before == expected["save_count_delta"]


def test_llm_regenerate_rejected_cell_proposal_saves_nothing():
    """Cell 재생성도 같은 Validator를 지난다. 실패하면 Cell이 그대로 남는다."""
    expected = H.case("llm_regenerate_rejected_cell_proposal_saves_nothing")[
        "expected"
    ]
    h = H.LlmGoldenHarness()
    plan = H.generate(h).plan
    before = H.cell_snapshot(plan)
    saves_before = h.save_count

    packet = h.packet(H.CASE_A_MONTH)
    refs = sorted({i.ref for i in packet.institution_evidence})
    h.llm.set_cell_proposal(
        H.outdoor_synthesized_proposal(
            plan, H.copyable_source_text(6), [refs[0]]
        )
    )

    with pytest.raises(PlanningError) as exc:
        h.regenerate_item.execute(H.regenerate_command(plan, H.OUTDOOR))

    assert exc.value.outcome is Outcome[expected["outcome"]]
    assert H.cell_snapshot(plan) == before
    assert h.save_count - saves_before == expected["save_count_delta"]
    assert H.copyable_source_text(6) not in str(exc.value)


def test_llm_confirmed_plan_is_read_only():
    expected = H.case("llm_confirmed_plan_is_read_only")["expected"]
    h = H.LlmGoldenHarness()
    plan = H.generate(h).plan
    confirmed = h.confirm.execute(H.confirm_command(plan)).plan
    calls_before = h.llm.cell_call_count
    saves_before = h.save_count

    with pytest.raises(PlanningError) as exc:
        h.regenerate_item.execute(H.regenerate_command(confirmed, H.FOCUS))

    assert exc.value.violated_rule == expected["violated_rule"]
    assert exc.value.outcome is Outcome[expected["outcome"]]
    # provider를 부르기 **전에** 막는다.
    assert h.llm.cell_call_count - calls_before == expected["cell_llm_call_count"]
    assert h.save_count - saves_before == expected["save_count_delta"]


# =================================================================== E2E


def test_llm_full_lifecycle():
    """L9 §11 — Generate → 재생성 → 교사 수정 → 재생성 → 확정 → 차단."""
    expected = H.case("llm_full_lifecycle")["expected"]
    h = H.LlmGoldenHarness()

    # 1. Generate
    plan = H.generate(h).plan
    assert plan.status is PlanStatus.DRAFT

    # 2. focus 재생성
    h.llm.set_cell_proposal(H.focus_proposal(plan, "첫 번째 재구성이에요."))
    plan = h.regenerate_item.execute(H.regenerate_command(plan, H.FOCUS)).plan

    # 3. 바깥놀이 재생성 (다른 주차)
    used = {i.value for i in H.section_items(plan, H.OUTDOOR)}
    spare = next(
        a for a in h.packet(H.CASE_A_MONTH).reference_activities
        if a.label not in used
    )
    h.llm.set_cell_proposal(
        H.outdoor_reference_proposal(
            plan, spare.activity_id, spare.label, week_index=2
        )
    )
    plan = h.regenerate_item.execute(
        H.regenerate_command(plan, H.OUTDOOR, week_index=2)
    ).plan

    # 4. 교사 수정 — 같은 focus Cell
    teacher_value = "교사가 직접 고쳐 쓴 중심 경험"
    plan = h.edit.execute(H.edit_command(plan, H.FOCUS, teacher_value)).plan
    edited = H.cell_at(plan, H.FOCUS)
    assert edited.value == teacher_value
    assert edited.generation.method is GenerationMethod.RULE_LLM, (
        "교사 수정을 이유로 Generation Method를 MANUAL로 덮어쓰지 않는다 "
        "(CLAUDE.md §13.2)"
    )

    # 5. 같은 Cell을 다시 재생성 — 교사 수정 이력이 지워지지 않는다
    h.llm.set_cell_proposal(H.focus_proposal(plan, "교사 수정 뒤 다시 생성했어요."))
    plan = h.regenerate_item.execute(H.regenerate_command(plan, H.FOCUS)).plan
    item = H.cell_at(plan, H.FOCUS)
    assert [
        e.event_type.value for e in item.audit.events
    ] == expected["audit_chain"]
    assert any(
        e.previous_value == teacher_value
        for e in item.audit.events
        if e.event_type is AuditEventType.REGENERATED
    ), "이전 교사 값이 Audit에 남아야 '무엇이 덮였는지' 답할 수 있다"

    # 6. Confirm
    plan = h.confirm.execute(H.confirm_command(plan)).plan
    assert plan.status is PlanStatus[expected["final_status"]]
    assert plan.constraint_assessments[0].verification is (
        ConstraintVerification[expected["safety_verification"]]
    ), "확정한다고 안전교육 근거가 생기지 않는다"

    # 7. 확정 뒤 모든 변경 차단
    blocked = 0
    for mutate in (
        lambda: h.edit.execute(H.edit_command(plan, H.FOCUS, "확정 뒤 수정")),
        lambda: h.regenerate_item.execute(H.regenerate_command(plan, H.FOCUS)),
        lambda: h.regenerate_item.execute(H.regenerate_command(plan, H.OUTDOOR)),
        lambda: h.regenerate_item.execute(H.regenerate_command(plan, "theme")),
    ):
        with pytest.raises(PlanningError):
            mutate()
        blocked += 1
    assert blocked == 4
    assert expected["mutations_blocked_after_confirm"] is True


# ============================================================ 제품 계약


def test_product_contracts_are_declared():
    """계약 문장이 조용히 사라지지 않게 한다."""
    contracts = H.SUITE["product_contracts"]
    assert len(contracts) >= 7
    assert any("OD-N15" in c for c in contracts)
    assert any("OD-N18" in c for c in contracts)


def test_golden_never_touches_real_credentials():
    """Golden은 환경변수도 네트워크도 쓰지 않는다."""
    source = (H.SUITE_PATH.parent / "monthly_llm_harness.py").read_text("utf-8")
    # `LLMConfigurationError`(오류 **종류**)는 써도 된다. 금지 대상은 설정을
    # 실제로 **읽는** 경로와 실제 Provider Adapter다.
    for banned in (
        "os.environ",
        "getenv",
        "LLMConfig.from_env",
        "EliceMLAPIAdapter",
        "API_KEY",
    ):
        assert banned not in source
