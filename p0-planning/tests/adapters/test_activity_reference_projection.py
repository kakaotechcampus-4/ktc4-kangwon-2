"""Runtime Projection 검증 (HD-I, 선택지 B).

검증 축:
- allowlist에 선언된 review metadata만 제거한다
- **알 수 없는 field는 제거하지 않으므로 strict schema가 그대로 거부한다**
- projection은 Approval Override가 아니다 (승인 상태를 읽지도 바꾸지도 않음)
- projection 후에도 Activity 의미가 바뀌지 않는다
- Production 기본 path는 여전히 v0.1.0이다
"""

from __future__ import annotations

import copy
import json
import pathlib

import pytest

from ssuksak.adapters.activity_reference_projection import (
    REVIEW_ONLY_ACTIVITY_FIELDS,
    REVIEW_ONLY_CATALOG_FIELDS,
    REVIEW_ONLY_EVIDENCE_FIELDS,
    RUNTIME_REQUIRED_CATALOG_FIELDS,
    project_runtime_payload,
)
from ssuksak.adapters.activity_reference_schema import (
    ActivityReferenceSchemaError,
    parse_activity_reference_payload,
)
from ssuksak.adapters.json_activity_reference_repository import (
    DEFAULT_ACTIVITY_CATALOG_PATH,
    LEGACY_ACTIVITY_CATALOG_PATH,
    JsonActivityReferenceRepository,
    load_activity_catalog_from_dict,
)
from ssuksak.planning.domain.activity_reference import ActivationStatus

DATA = pathlib.Path(__file__).resolve().parents[2] / "data" / "activities"
V1_PATH = DATA / "activity_reference_v0.json"
APPROVED_PATH = DATA / "activity_reference_v0_2.json"

CATALOG_ID = "ssuksak.outdoor-activity-reference"
V1_VERSION = "activity-reference-v0.1.0"
V2_VERSION = "activity-reference-v0.2.0"
OUTDOOR = "outdoor_play"


@pytest.fixture(scope="module")
def approved_raw() -> dict:
    return json.loads(APPROVED_PATH.read_text(encoding="utf-8"))


@pytest.fixture()
def payload(approved_raw) -> dict:
    return copy.deepcopy(approved_raw)


@pytest.fixture(scope="module")
def catalog():
    return JsonActivityReferenceRepository(APPROVED_PATH).get_catalog(
        CATALOG_ID, V2_VERSION
    )


# ------------------------------------------- allowlist가 실제 파일과 일치


CORRECTION_FIELDS = {
    "correction_type",
    "correction_note",
    "supersedes_activity_ids",
    "source_reference",
}
"""v0.2.1 Draft에서 도입된 correction 기록. v0.2.0에는 없다.

allowlist에 미리 넣어 두어야 v0.2.1이 strict schema를 통과한다. 승인본 v0.2.0
기준으로는 "죽은 항목"처럼 보이지만 의도된 forward-looking 항목이다.
"""


def test_activity_allowlist_covers_the_approved_artifact(approved_raw):
    """allowlist가 승인 artifact v0.2.0의 extra field를 빠짐없이 덮는다.

    적으면 파싱이 실패한다. 많은 것은 v0.2.1 correction 필드에 한해 허용한다.
    """
    from ssuksak.adapters import activity_reference_schema as schema

    known = set(schema._Activity.model_fields)
    actual = {k for a in approved_raw["activities"] for k in a if k not in known}
    allow = set(REVIEW_ONLY_ACTIVITY_FIELDS)
    assert actual <= allow, f"allowlist에 없는 필드: {actual - allow}"
    assert allow - actual == CORRECTION_FIELDS, (
        f"의도하지 않은 죽은 항목: {allow - actual - CORRECTION_FIELDS}"
    )


def test_evidence_allowlist_exactly_covers_the_artifact(approved_raw):
    from ssuksak.adapters import activity_reference_schema as schema

    known = set(schema._Evidence.model_fields)
    actual = {
        k
        for a in approved_raw["activities"]
        for e in a["evidence"]
        for k in e
        if k not in known
    }
    assert actual == set(REVIEW_ONLY_EVIDENCE_FIELDS)


def test_theme_and_curriculum_links_need_no_projection(approved_raw):
    from ssuksak.adapters import activity_reference_schema as schema

    tk = set(schema._ThemeLink.model_fields)
    ck = set(schema._CurriculumLink.model_fields)
    for a in approved_raw["activities"]:
        for t in a["theme_links"]:
            assert set(t) <= tk
        for c in a["curriculum_links"]:
            assert set(c) <= ck


def test_allowlists_do_not_overlap_runtime_required_fields():
    assert not REVIEW_ONLY_CATALOG_FIELDS & RUNTIME_REQUIRED_CATALOG_FIELDS


# ---------------------------------------------------- projection 동작


def test_projection_removes_only_allowlisted_activity_fields(payload):
    out = project_runtime_payload(payload)
    for a in out["activities"]:
        assert not set(a) & REVIEW_ONLY_ACTIVITY_FIELDS
        for e in a["evidence"]:
            assert not set(e) & REVIEW_ONLY_EVIDENCE_FIELDS


def test_projection_removes_catalog_review_bookkeeping(payload):
    out = project_runtime_payload(payload)
    assert not set(out) & REVIEW_ONLY_CATALOG_FIELDS


def test_projection_keeps_runtime_required_fields(payload):
    out = project_runtime_payload(payload)
    for key in RUNTIME_REQUIRED_CATALOG_FIELDS:
        assert key in out, key


def test_projection_keeps_interpretive_catalog_sections(payload):
    """해석 규정은 제거하지 않는다. `_Catalog`가 extra를 허용한다."""
    out = project_runtime_payload(payload)
    for key in ("supersedes", "disclaimer", "age_semantics", "exclusion_policy",
                "taxonomy_scope", "safety_exclusion_statement",
                "theme_link_semantics", "curriculum_link_semantics"):
        assert key in out, key


def test_projection_does_not_mutate_input(approved_raw):
    before = json.dumps(approved_raw, ensure_ascii=False, sort_keys=True)
    project_runtime_payload(approved_raw)
    after = json.dumps(approved_raw, ensure_ascii=False, sort_keys=True)
    assert before == after


def test_projection_passes_non_object_through_unchanged():
    """형식 검증은 strict schema의 몫이다. projection이 오류 타입을 바꾸지 않는다."""
    assert project_runtime_payload([1, 2, 3]) == [1, 2, 3]
    with pytest.raises(ActivityReferenceSchemaError, match="object여야"):
        load_activity_catalog_from_dict([1, 2, 3])


def test_projection_is_deterministic(payload):
    a = project_runtime_payload(payload)
    b = project_runtime_payload(payload)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


# ---------------------------------- unknown field는 여전히 실패 (§3)


@pytest.mark.parametrize(
    "where",
    ["activity", "evidence", "theme_link", "curriculum_link"],
)
def test_unknown_extra_field_still_fails(payload, where):
    if where == "activity":
        payload["activities"][0]["brand_new_field"] = 1
    elif where == "evidence":
        payload["activities"][0]["evidence"][0]["weird"] = 1
    elif where == "theme_link":
        target = next(a for a in payload["activities"] if a["theme_links"])
        target["theme_links"][0]["score"] = 0.9
    else:
        payload["activities"][0]["curriculum_links"] = [
            {"source_id": "s", "domain": "자연탐구", "source_page": 1, "weight": 1}
        ]
    with pytest.raises(ActivityReferenceSchemaError):
        load_activity_catalog_from_dict(payload)


def test_projection_does_not_strip_unknown_fields(payload):
    payload["activities"][0]["totally_unknown"] = 1
    out = project_runtime_payload(payload)
    assert "totally_unknown" in out["activities"][0]


@pytest.mark.parametrize("key", ["runtime_active", "activation_status"])
def test_forbidden_activation_keys_still_rejected(payload, key):
    payload[key] = True
    with pytest.raises(ActivityReferenceSchemaError):
        load_activity_catalog_from_dict(payload)


@pytest.mark.parametrize("key", ["safety_flags", "activity_area", "tags"])
def test_forbidden_activity_keys_still_rejected(payload, key):
    payload["activities"][0][key] = ["x"]
    with pytest.raises(ActivityReferenceSchemaError):
        load_activity_catalog_from_dict(payload)


def test_strict_parser_itself_is_unchanged(approved_raw):
    """projection 없이 직접 넘기면 기존처럼 거부된다."""
    with pytest.raises(ActivityReferenceSchemaError):
        parse_activity_reference_payload(approved_raw)


# ------------------------------- Approval Contract 보존 (§4 §5)


def test_projection_preserves_approval_state(payload):
    out = project_runtime_payload(payload)
    for key in ("domain_owner_approval", "approved_by", "approved_at"):
        assert out["review"][key] == payload["review"][key]
    assert out["review"]["domain_owner_approval"] == "HUMAN_APPROVED"
    assert out["review"]["approved_by"] == "reviewer_ai_lead_001"


def test_projection_preserves_catalog_version_and_origins(payload):
    out = project_runtime_payload(payload)
    assert out["catalog_version"] == payload["catalog_version"]
    assert out["origins"] == payload["origins"]


def test_is_active_derives_only_from_approval(payload):
    approved = load_activity_catalog_from_dict(payload)
    assert approved.activation_status is ActivationStatus.HUMAN_APPROVED
    assert approved.is_active is True

    pending = copy.deepcopy(payload)
    pending["review"]["domain_owner_approval"] = "PENDING_HUMAN_REVIEW"
    cat = load_activity_catalog_from_dict(pending)
    assert not cat.is_active
    assert cat.eligible_candidates(
        section_key=OUTDOOR, calendar_month=9, ages=frozenset({4})
    ) == ()


def test_projection_is_not_an_approval_override():
    """projection API에 승인 우회 입력이 없다."""
    import inspect

    banned = {"activation_override", "approval_override", "force_active",
              "runtime_active", "approve", "activate"}
    for fn in (project_runtime_payload, load_activity_catalog_from_dict,
               parse_activity_reference_payload,
               JsonActivityReferenceRepository.__init__,
               JsonActivityReferenceRepository.get_catalog):
        assert not set(inspect.signature(fn).parameters) & banned, fn


def test_projection_module_has_no_bypass_identifier():
    import ast

    src = pathlib.Path(
        "src/ssuksak/adapters/activity_reference_projection.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(src)
    names = {
        n.id if isinstance(n, ast.Name) else n.attr
        for n in ast.walk(tree)
        if isinstance(n, (ast.Name, ast.Attribute))
    }
    names |= {
        a.arg
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef)
        for a in list(n.args.args) + list(n.args.kwonlyargs)
    }
    for banned in ("activation_override", "approval_override", "force_active"):
        assert banned not in names, banned


# ------------------------------------ Projection 정합성 (§6)


def test_repository_loads_approved_v0_2(catalog):
    assert catalog is not None
    assert catalog.catalog_version == V2_VERSION
    assert catalog.is_active is True


@pytest.mark.parametrize(
    "name,getter,expected",
    [
        ("activities", lambda c: len(c.activities), 198),
        ("evidence", lambda c: sum(len(a.evidence) for a in c.activities), 288),
        ("month coverage", lambda c: len(set(c.month_coverage)), 12),
    ],
)
def test_projection_preserves_counts(catalog, name, getter, expected):
    assert getter(catalog) == expected


def test_projection_preserves_existing_49(catalog):
    v1 = json.loads(V1_PATH.read_text(encoding="utf-8"))
    base = {a["activity_id"] for a in v1["activities"]}
    assert base <= {a.activity_id for a in catalog.activities}


def test_projection_preserves_new_canonical_count(approved_raw):
    assert sum(
        1 for a in approved_raw["activities"] if a["draft_status"] == "NEW_CANDIDATE"
    ) == 149


def test_projection_preserves_supported_ages(catalog):
    assert sorted({x for a in catalog.activities for x in a.supported_ages}) == [3, 4, 5]


def test_projection_preserves_hd_verdicts(catalog, approved_raw):
    ph = approved_raw["pending_human_review"]
    labels = {a.label for a in catalog.activities}
    assert {i["label"] for i in ph["safety_adjacent_included_hd_g"]} <= labels
    assert not {e["label"] for e in ph["safety_adjacent_excluded_hd_g"]} & labels
    assert "실외놀이" not in labels
    assert not {i["observed_label"] for i in ph["ambiguous_items"]} & labels


def test_projection_creates_no_curriculum_links(catalog):
    assert sum(len(a.curriculum_links) for a in catalog.activities) == 0


def test_projection_keeps_safety_slot_rejected(catalog):
    assert catalog.eligible_candidates(
        section_key="safety_education", calendar_month=9, ages=frozenset({4})
    ) == ()


# ---------------------------------------- Candidate Smoke (§9)


@pytest.mark.parametrize(
    "month,ages",
    [(9, {4}), (5, {3}), (11, {3, 4, 5}), (2, {5})],
)
def test_candidate_smoke(catalog, month, ages):
    got = catalog.eligible_candidates(
        section_key=OUTDOOR, calendar_month=month, ages=frozenset(ages)
    )
    assert len(got) >= 1


@pytest.mark.parametrize("month", list(range(1, 13)))
def test_every_month_has_candidates_for_some_age_combination(catalog, month):
    combos = ({3}, {4}, {5}, {3, 4}, {4, 5}, {3, 5}, {3, 4, 5})
    best = max(
        len(catalog.eligible_candidates(
            section_key=OUTDOOR, calendar_month=month, ages=frozenset(a)))
        for a in combos
    )
    assert best >= 1, month


# ------------------- Production path (2026-09-13 승인으로 v0.2.1로 전환)


def test_default_catalog_path_is_the_approved_v0_2_1():
    assert DEFAULT_ACTIVITY_CATALOG_PATH.name == "activity_reference_v0_2_1.json"


def test_legacy_path_still_loads_pending_v0_1_0():
    """v0.1.0 파일은 삭제되지 않았고 명시 경로로 여전히 로드된다."""
    repo = JsonActivityReferenceRepository(LEGACY_ACTIVITY_CATALOG_PATH)
    cat = repo.get_catalog(CATALOG_ID, V1_VERSION)
    assert cat is not None
    assert len(cat.activities) == 49
    assert not cat.is_active
    assert cat.eligible_candidates(
        section_key=OUTDOOR, calendar_month=9, ages=frozenset({4})
    ) == ()


def test_v0_1_0_is_not_reachable_from_default_path():
    assert (
        JsonActivityReferenceRepository().get_catalog(CATALOG_ID, V1_VERSION)
        is None
    )


def test_v0_2_0_is_not_reachable_from_the_bare_default_repository():
    """default 파일 하나만 읽는 Repository는 v0.2.0을 해소하지 않는다.

    과거 pin 해소는 `production_activity_reference_repository()`가 명시적으로
    superseded 경로를 붙일 때만 일어난다. 조용한 fallback이 아니다.
    """
    assert (
        JsonActivityReferenceRepository().get_catalog(CATALOG_ID, V2_VERSION) is None
    )
    explicit = JsonActivityReferenceRepository(APPROVED_PATH).get_catalog(
        CATALOG_ID, V2_VERSION
    )
    assert explicit is not None and explicit.is_active
    assert JsonActivityReferenceRepository(APPROVED_PATH).get_catalog(
        CATALOG_ID, V1_VERSION
    ) is None
