"""Monthly LLM Planner v1 **Freeze** (L9 §14–§18, §22–§23).

Golden이 "Application이 무엇을 하는가"를 고정한다면, 이 파일은 그 계약이
**어떤 Artifact와 어떤 값 위에서** 성립했는지를 고정한다.

Artifact가 바뀌면 Golden이 여전히 통과하더라도 **같은 계약이 아니다.** 승인
Template을 새로 발행하거나 Evidence Store를 다시 빌드하면 여기서 먼저 실패해야
한다. 실패가 곧 "다시 승인받아라"는 신호다.

**여기서 SHA를 조용히 갱신하지 않는다.** 값을 고치는 것은 Artifact 재승인
결정이며, 결정 근거를 보고서에 남긴 뒤에만 한다.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
DATA = ROOT / "data"


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# =========================================================== Artifact SHA


FROZEN_ARTIFACTS = {
    # L9 §17 — 두 Template version이 **공존**한다. 하나가 다른 하나를
    # 대체하지 않는다. RULE_ONLY가 v0.1.0을, LLM_PLANNER가 v0.2.0을 쓴다.
    "templates/monthly_template_a.json": (
        "1f35322dd52f832bffc3057953ecbd64d52c2d855ada964af68472ebba1a7c34"
    ),
    "templates/monthly_template_a_v0_2_0.json": (
        "cb3fa9d15ea5ad55c961cc52588bc08e2bd31a720aa67a5dea0bb1fee644c3c5"
    ),
    # L9 §18
    "evidence/institution_evidence_v0_1_0.json": (
        "8479c0490a002d9336688c1b6cacf47f2d2c083201b15df01258336c07e0ba1a"
    ),
    "activities/activity_reference_v0_2_1.json": (
        "ddbbe43f570cf64ef86db44e7de04e127aec4e663cdb41c26a8fe3c1002dc2ac"
    ),
    # 법정 근거. LLM 작업이 이 파일을 건드리면 안 된다.
    "rules/safety_education_legal_v1.json": (
        "5831809b19a28505844cf10363c95eeb09ec4641d5fe54a26afdb1891c3ddba5"
    ),
    "themes/theme_reference_v0.json": (
        "c12999fa141d5c5fdecf39110adfb2227fc0ab98725991e8bdbca098b3ff4197"
    ),
}


@pytest.mark.parametrize("relative,expected", sorted(FROZEN_ARTIFACTS.items()))
def test_approved_artifact_is_byte_identical(relative: str, expected: str):
    path = DATA / relative
    assert path.exists(), f"승인 Artifact가 사라졌다: {relative}"
    assert sha256(path) == expected, (
        f"{relative}의 내용이 바뀌었다. Monthly LLM Planner v1은 이 byte 위에서 "
        "동결됐다. 새 version을 발행하고 재승인을 받되, 기존 version을 "
        "덮어쓰지 않는다."
    )


def test_both_template_versions_are_served_and_neither_is_a_fallback():
    """L9 §17 — exact resolve다. 최신 version으로 조용히 대체하지 않는다."""
    from ssuksak.adapters.monthly_repositories import (
        production_monthly_template_repository,
    )

    repo = production_monthly_template_repository()
    v1 = repo.get_template("ssuksak.monthly-template-a", "monthly-template-a-v0.1.0")
    v2 = repo.get_template("ssuksak.monthly-template-a", "monthly-template-a-v0.2.0")
    assert v1.template_ref.template_version == "monthly-template-a-v0.1.0"
    assert v2.template_ref.template_version == "monthly-template-a-v0.2.0"

    # 없는 version은 **None**이다. 최신 version을 대신 돌려주지 않는다.
    assert (
        repo.get_template("ssuksak.monthly-template-a", "monthly-template-a-v9.9.9")
        is None
    )


def test_only_v0_2_0_activates_the_week_experience_section():
    """OD-N18 — 승인된 v0.1.0을 수정하지 않고 새 version으로 해결했다."""
    v1 = json.loads(
        (DATA / "templates" / "monthly_template_a.json").read_text("utf-8")
    )
    v2 = json.loads(
        (DATA / "templates" / "monthly_template_a_v0_2_0.json").read_text("utf-8")
    )

    def focus(doc):
        return next(s for s in doc["sections"] if s.get("semantic_key") == "focus")

    assert focus(v1)["activated"] is False
    assert focus(v2)["activated"] is True
    assert v2["supersedes"] == v1["template_version"]

    # `focus` 외에는 아무것도 달라지지 않았다 — 다른 Section을 함께 바꾸면
    # "focus만 켰다"는 설명이 사실이 아니게 된다.
    def without_focus(doc):
        return [s for s in doc["sections"] if s.get("semantic_key") != "focus"]

    assert without_focus(v1) == without_focus(v2)
    assert v1["structure_rules"] == v2["structure_rules"]
    assert v1["excluded_sections"] == v2["excluded_sections"]


def test_week_axis_is_still_an_axis_not_a_content_section():
    """OD-N18의 전제. week_axis에 값을 저장하지 않는다."""
    v2 = json.loads(
        (DATA / "templates" / "monthly_template_a_v0_2_0.json").read_text("utf-8")
    )
    axis = next(s for s in v2["sections"] if s.get("semantic_key") == "week_axis")
    assert axis.get("role") == "AXIS" or axis.get("is_axis") is True, (
        f"week_axis의 역할 표기가 바뀌었다: {axis}"
    )


def test_evidence_store_declares_the_content_sha_used_as_source_version():
    """L9 §18 — 새로 쓴 활동의 `source_version`이 가리키는 값이다."""
    store = json.loads(
        (DATA / "evidence" / "institution_evidence_v0_1_0.json").read_text("utf-8")
    )
    assert store["ingestion_version"] == "institution-evidence-ingestion-v0.1.0"
    assert (
        store["build"]["content_sha256"]
        == "52b409557d3503422aa0109664298976bd7f831ed18304b818aaad936916e5ea"
    )
    assert store["record_count"] == 12367
    assert store["normative_status"] == "CORPUS_OBSERVATION_NON_NORMATIVE"


def test_every_evidence_record_is_still_context_only():
    """제품 출력으로 그대로 복사해도 되는 record는 0건이다 (OD-N12)."""
    store = json.loads(
        (DATA / "evidence" / "institution_evidence_v0_1_0.json").read_text("utf-8")
    )
    policies = {r["reuse_policy"] for r in store["records"]}
    assert policies == {"CONTEXT_ONLY"}


def test_activity_catalog_v0_2_1_is_the_runtime_default():
    from ssuksak.adapters.json_activity_reference_repository import (
        DEFAULT_ACTIVITY_CATALOG_PATH,
    )

    assert DEFAULT_ACTIVITY_CATALOG_PATH.name == "activity_reference_v0_2_1.json"
    catalog = json.loads(DEFAULT_ACTIVITY_CATALOG_PATH.read_text("utf-8"))
    assert catalog["catalog_version"] == "activity-reference-v0.2.1"
    assert catalog["draft"] is False
    assert len(catalog["activities"]) == 196


# ============================================== 구현 상수 (닫힌 결정 아님)


def test_repair_budgets_are_frozen_at_one_attempt():
    """L9 §22 — **구현 값**으로 동결한다. OD-N04는 닫지 않는다.

    관측 근거가 없어서 1을 고른 것이지, 1이 옳다고 증명한 것이 아니다.
    Live 관측에서 repair가 실제로 발생하는 것을 본 뒤에 다시 판단한다.
    """
    from ssuksak.adapters.elice_mlapi_adapter import MAX_REPAIR_ATTEMPTS
    from ssuksak.planning.application.monthly_llm_cell_regeneration import (
        MAX_CELL_VALIDATION_REPAIR_ATTEMPTS,
    )
    from ssuksak.planning.application.monthly_llm_planning import (
        MAX_VALIDATION_REPAIR_ATTEMPTS,
    )

    assert MAX_REPAIR_ATTEMPTS == 1
    assert MAX_VALIDATION_REPAIR_ATTEMPTS == 1
    assert MAX_CELL_VALIDATION_REPAIR_ATTEMPTS == 1


def test_od_n04_is_still_open():
    """상수를 동결했다는 이유로 Open Decision을 닫지 않는다."""
    doc = (ROOT / "docs" / "open-decisions.md").read_text("utf-8")
    block = doc[doc.index("OD-N04") :][:2000]
    assert "RESOLVED" not in block.split("OD-N05")[0], (
        "OD-N04가 닫혔다. 상수 동결은 결정 종결이 아니다."
    )


def test_age_evidence_strength_has_exactly_four_levels():
    """L9 §23 — 4단계를 동결한다. OD-N17은 열려 있다."""
    from ssuksak.planning.context.models import AgeEvidenceStrength

    assert [s.value for s in AgeEvidenceStrength] == [
        "STRONG",
        "MODERATE",
        "WEAK",
        "VERY_WEAK",
    ]
    # 임계값을 새로 만들지 않았다는 사실이 docstring에 남아 있어야 한다.
    assert "new-reference-evidence-impact-2026-09.md" in (
        AgeEvidenceStrength.__doc__ or ""
    )


def test_contract_versions_are_frozen():
    from ssuksak.planning.context.models import (
        PACKET_VERSION,
        RETRIEVAL_CONTRACT_VERSION,
    )
    from ssuksak.planning.planner.cell_prompt import CELL_PROMPT_VERSION
    from ssuksak.planning.planner.prompt import PROMPT_VERSION
    from ssuksak.planning.rules.monthly_llm_validation import (
        PLANNER_RULE_ID,
        PLANNER_RULE_VERSION,
        WEEK_ORDER_BASIS,
    )

    assert PACKET_VERSION == "monthly-context-packet-v0.1.0"
    assert RETRIEVAL_CONTRACT_VERSION == "monthly-evidence-retrieval-v0.1.0"
    assert PROMPT_VERSION == "monthly-planner-prompt-v0.1.1"
    assert CELL_PROMPT_VERSION == "monthly-cell-regeneration-prompt-v0.1.0"
    assert PLANNER_RULE_ID == "monthly.llm.evidence_grounded_planner"
    assert PLANNER_RULE_VERSION == "v1"
    assert WEEK_ORDER_BASIS == "PLANNER_COMPOSED"


# ============================================================ Secret 위생


SOURCE_ROOTS = (
    ROOT / "src",
    ROOT / "tests",
    ROOT / "demo-planning",
    ROOT / "data",
)

SKIP_DIRS = {"__pycache__", ".git", "node_modules", ".venv", ".pytest_cache"}


def _scanned_files():
    for root in SOURCE_ROOTS:
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            if path.suffix.lower() not in {".py", ".json", ".js", ".html", ".css", ".md"}:
                continue
            yield path


SECRET_PATTERNS = (
    # 실제 Key 형태. 변수 **이름**은 허용하고 **값**만 막는다.
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9_\-\.]{20,}"),
    re.compile(r"(?i)(api[_-]?key|secret|token)\s*[:=]\s*['\"][A-Za-z0-9_\-]{20,}['\"]"),
)


DECLARED_NON_SECRET_MARKERS = (
    "not-a-real",
    "must-never-appear",
    "should-never-be-logged",
    "fake",
    "dummy",
    "example",
)
"""Credential **모양**이지만 실제 값이 아님을 문자열 자체가 선언한 경우.

Key가 로그·telemetry·화면에 새지 않는지 확인하려면 테스트가 Key 자리에 무언가를
넣어야 한다. 그 값이 스스로 "이건 진짜가 아니다"라고 말하고 있으면 사람이 읽을
때도 grep이 걸릴 때도 오해가 없다. **주석으로 예외를 만들지 않는다** — 값 자체가
선언해야 한다.
"""


def test_no_credential_value_is_committed_anywhere():
    """L9 §14 — Key는 코드·Fixture·Golden 어디에도 없다."""
    offenders = []
    for path in _scanned_files():
        try:
            text = path.read_text("utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for pattern in SECRET_PATTERNS:
            for match in pattern.finditer(text):
                found = match.group(0).lower()
                if any(m in found for m in DECLARED_NON_SECRET_MARKERS):
                    continue
                # 값 자체를 assertion 메시지에 넣지 않는다.
                offenders.append(
                    f"{path.relative_to(ROOT)}:{pattern.pattern[:20]}"
                )
                break
    assert not offenders, f"Credential 형태의 값이 발견됐다: {sorted(set(offenders))}"


def test_credentials_are_read_only_from_the_environment():
    """Base URL과 Key는 env에서만 읽는다. 코드에 기본값을 두지 않는다."""
    config = (ROOT / "src" / "ssuksak" / "shared" / "llm" / "config.py").read_text(
        "utf-8"
    )
    assert "ELICE_MLAPI_API_KEY" in config
    # 이름은 있어도 값은 없다 — 위 test가 값 형태를 막고, 여기서는 하드코딩된
    # endpoint가 기본값으로 들어가지 않았는지 본다.
    assert not re.search(r"https://[^\s\"']*elice[^\s\"']*", config), (
        "Base URL이 코드에 하드코딩됐다. 환경변수로만 읽어야 한다."
    )


def test_telemetry_cannot_carry_prompt_text():
    """L9 §14 — 일반 로그에 Prompt 본문이 남지 않는다 (CLAUDE.md §21)."""
    from ssuksak.shared.llm.telemetry import LLMCallRecord

    def record(**extra):
        return LLMCallRecord(
            operation="plan_monthly",
            provider="elice",
            model="openai/gpt-4.1-mini",
            success=True,
            latency_ms=1,
            retry_count=0,
            item_count=1,
            extra=extra,
        )

    for banned in ("system_prompt", "user_prompt", "api_key", "messages", "input"):
        with pytest.raises(ValueError):
            record(**{banned: "..."})

    # 정상 telemetry에는 Prompt도 Key도 담기지 않는다.
    logged = record(template_version="monthly-template-a-v0.2.0").to_log_dict()
    assert not any("prompt" in k.lower() for k in logged)
    assert not any("key" in k.lower() for k in logged)


def test_analysis_scripts_do_not_print_credentials():
    """Live Smoke 스크립트가 Key나 Prompt 전문을 출력하지 않는다."""
    scripts = sorted(
        (ROOT / "analysis" / "experiments" / "monthly_llm_vnext").glob("*.py")
    )
    assert scripts, "Live Smoke 스크립트를 찾지 못했다"
    for path in scripts:
        text = path.read_text("utf-8")
        for banned in ("api_key)", "api_key}", "config.api_key", "print(config)"):
            assert banned not in text, f"{path.name}이 credential을 출력한다: {banned}"


def test_golden_and_fixtures_never_embed_source_document_text():
    """Evidence 원문을 Golden expected로 굳히지 않는다 (L5 §24)."""
    suite = (
        pathlib.Path(__file__).parent / "monthly_llm_cases.json"
    ).read_text("utf-8")
    store = json.loads(
        (DATA / "evidence" / "institution_evidence_v0_1_0.json").read_text("utf-8")
    )
    samples = [
        r["activity_text"]
        for r in store["records"][:500]
        if r.get("activity_text") and len(r["activity_text"]) >= 8
    ]
    leaked = [t for t in samples if t in suite]
    assert not leaked, f"Golden에 Corpus 원문이 들어갔다: {len(leaked)}건"
