"""Activity Reference Adapter 테스트 (M2-A).

검증 축:
- 실제 승인 대기 JSON이 그대로 로드되고 **inactive**다
- fail-fast: 누락·오타·미지 enum·금지 필드에서 즉시 실패
- exact id/version만 반환. `latest` 자동 탐색 없음
- caller가 approval을 override하는 Application 경로가 없다
- 실제 JSON 파일을 테스트가 수정하지 않는다
"""

from __future__ import annotations

import copy
import hashlib
import json
import pathlib

import pytest

from ssuksak.adapters.json_activity_reference_repository import (
    LEGACY_ACTIVITY_CATALOG_PATH,
    ActivityReferenceSchemaError,
    InMemoryActivityReferenceRepository,
    JsonActivityReferenceRepository,
    load_activity_catalog_from_dict,
)
from ssuksak.planning.domain.activity_reference import (
    ActivationStatus,
    ActivitySetting,
)

CATALOG_ID = "ssuksak.outdoor-activity-reference"
VERSION = "activity-reference-v0.1.0"
OUTDOOR = "outdoor_play"


@pytest.fixture(scope="module")
def raw() -> dict:
    return json.loads(LEGACY_ACTIVITY_CATALOG_PATH.read_text(encoding="utf-8"))


@pytest.fixture()
def payload(raw) -> dict:
    """매 테스트가 자기 사본을 변조한다. 실제 파일은 건드리지 않는다."""
    return copy.deepcopy(raw)


def approved(payload: dict):
    """HUMAN_APPROVED **fixture payload**를 만들어 실제 parse 경로로 로드한다.

    Production에 승인 우회 입력이 없으므로 승인 상태 동작을 보려면 승인된
    payload 자체를 만들어야 한다. 실제 `activity_reference_v0.json`은 수정하지
    않는다 — 여기서 바꾸는 것은 테스트가 소유한 deepcopy 사본이다.
    """
    payload = copy.deepcopy(payload)
    payload["review"]["domain_owner_approval"] = "HUMAN_APPROVED"
    payload["review"]["approved_by"] = "reviewer_test_fixture_001"
    payload["review"]["approved_at"] = "2026-09-11T00:00:00+09:00"
    return load_activity_catalog_from_dict(payload)


def approved_catalog_file(tmp_path, payload: dict):
    """HUMAN_APPROVED JSON fixture를 tmp_path에 쓰고 실제 Adapter로 로드한다."""
    payload = copy.deepcopy(payload)
    payload["review"]["domain_owner_approval"] = "HUMAN_APPROVED"
    target = tmp_path / "approved_activity_reference.json"
    target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return JsonActivityReferenceRepository(target)


# ------------------------------------------------- 실제 파일: 승인 대기 상태


def test_real_catalog_parses():
    c = JsonActivityReferenceRepository(LEGACY_ACTIVITY_CATALOG_PATH).get_catalog(CATALOG_ID, VERSION)
    assert c is not None
    assert c.catalog_id == CATALOG_ID
    assert c.catalog_version == VERSION
    assert len(c.activities) > 0


def test_real_catalog_is_pending_and_inactive():
    """D1 결정: 표본 부족으로 HUMAN_APPROVED 하지 않는다."""
    c = JsonActivityReferenceRepository(LEGACY_ACTIVITY_CATALOG_PATH).get_catalog(CATALOG_ID, VERSION)
    assert c.activation_status is ActivationStatus.PENDING_HUMAN_REVIEW
    assert not c.is_active


def test_real_catalog_yields_no_runtime_candidates():
    c = JsonActivityReferenceRepository(LEGACY_ACTIVITY_CATALOG_PATH).get_catalog(CATALOG_ID, VERSION)
    for month in range(1, 13):
        for ages in (frozenset({3}), frozenset({4}), frozenset({5}), frozenset({3, 4, 5})):
            assert c.eligible_candidates(
                section_key=OUTDOOR, calendar_month=month, ages=ages
            ) == ()


def test_real_catalog_is_sample_derived_non_normative():
    c = JsonActivityReferenceRepository(LEGACY_ACTIVITY_CATALOG_PATH).get_catalog(CATALOG_ID, VERSION)
    assert c.normative_status == "SAMPLE_DERIVED_NON_NORMATIVE"


def test_real_catalog_has_no_approver_before_approval(raw):
    assert raw["review"]["domain_owner_approval"] == "PENDING_HUMAN_REVIEW"
    assert raw["review"]["approved_by"] is None
    assert raw["review"]["approved_at"] is None
    assert raw["review"]["pending_reason"]


def test_real_catalog_declares_no_runtime_active_field(raw):
    assert "runtime_active" not in raw
    assert "activation_status" not in raw
    for a in raw["activities"]:
        assert "runtime_active" not in a


def test_real_catalog_month_coverage_is_honest(raw):
    c = JsonActivityReferenceRepository(LEGACY_ACTIVITY_CATALOG_PATH).get_catalog(CATALOG_ID, VERSION)
    assert set(c.month_coverage) == {3, 9}
    actual = {m for a in c.activities for m in a.applicable_months}
    assert set(c.month_coverage) == actual
    assert raw["coverage"]["month_coverage"] == [3, 9]


def test_real_catalog_never_claims_unobserved_months(raw):
    for a in raw["activities"]:
        observed = {e["observed_month"] for e in a["evidence"]}
        assert set(a["applicable_months"]) <= observed, a["activity_id"]


def test_real_catalog_never_claims_unobserved_ages(raw):
    for a in raw["activities"]:
        observed = {x for e in a["evidence"] for x in e["age_scope"]}
        assert set(a["supported_ages"]) <= observed, a["activity_id"]


def test_real_catalog_every_activity_has_evidence(raw):
    for a in raw["activities"]:
        assert a["evidence"], a["activity_id"]


def test_real_catalog_origins_are_declared_and_hashes_match(raw):
    root = LEGACY_ACTIVITY_CATALOG_PATH.parents[2]
    for o in raw["origins"]:
        path = root / pathlib.Path(o["path"])
        assert path.exists(), o["path"]
        actual = hashlib.sha256(path.read_bytes()).hexdigest().upper()
        assert actual == o["sha256"], o["origin_id"]


def test_real_catalog_evidence_origins_are_declared(raw):
    declared = {o["origin_id"] for o in raw["origins"]}
    for a in raw["activities"]:
        assert a["origin_id"] in declared, a["activity_id"]
        for e in a["evidence"]:
            assert e["origin_id"] in declared, (a["activity_id"], e["origin_id"])


def test_real_catalog_has_no_curriculum_links(raw):
    """근거가 부족하면 빈 배열이 정답이다."""
    assert sum(len(a["curriculum_links"]) for a in raw["activities"]) == 0


def test_real_catalog_theme_links_resolve_in_declared_theme_catalog(raw):
    theme_path = LEGACY_ACTIVITY_CATALOG_PATH.parents[1] / "themes" / "theme_reference_v0.json"
    themes = json.loads(theme_path.read_text(encoding="utf-8"))
    known = {t["theme_id"] for t in themes["themes"]}
    version = themes["catalog_version"]
    seen = 0
    for a in raw["activities"]:
        for link in a["theme_links"]:
            assert link["theme_id"] in known, link
            assert link["relation"] == "OBSERVED_TOGETHER"
            assert link["theme_catalog_version"] == version
            seen += 1
    assert seen > 0


def test_real_catalog_placement_is_outdoor_only(raw):
    for a in raw["activities"]:
        assert a["placement_slots"] == [OUTDOOR], a["activity_id"]


def test_real_catalog_setting_is_outdoor_only(raw):
    for a in raw["activities"]:
        assert a["setting"] == "OUTDOOR", a["activity_id"]


def test_real_catalog_has_no_safety_fields(raw):
    blob = json.dumps(raw, ensure_ascii=False)
    for a in raw["activities"]:
        assert "safety_flags" not in a
        assert "safety_education" not in a["placement_slots"]
    assert raw["placement_slot_semantics"]["forbidden"] == ["safety_education"]
    assert raw["safety_exclusion_statement"]
    # 법정 안전교육 구분명이 활동 label로 들어오지 않았다.
    for a in raw["activities"]:
        for banned in ("성폭력", "아동학대", "실종", "유괴", "약물", "재난대비", "교통안전 교육"):
            assert banned not in a["label"], (a["activity_id"], banned)
    assert "safety_education_legal" not in blob


def test_real_catalog_declares_open_taxonomy(raw):
    scope = raw["taxonomy_scope"]
    assert scope["confirmed_in_m2a"] == ["placement_slots", "setting"]
    assert set(scope["still_open"]) == {"activity_area", "tags", "safety_flags"}
    for a in raw["activities"]:
        assert "activity_area" not in a
        assert "tags" not in a


def test_real_catalog_documents_external_source_exclusion(raw):
    """외부 site가 origin으로도 evidence로도 쓰이지 않았다.

    `exclusion_policy.external_sources` 진술문 안에는 사이트 이름이 "쓰지 않았다"는
    문맥으로 등장한다. 따라서 문서 전체 문자열이 아니라 **실제 데이터 경로**(origins /
    activities)에 외부 출처가 없는지를 검증한다.
    """
    assert raw["exclusion_policy"]["external_sources"]

    for o in raw["origins"]:
        assert o["kind"] == "MONTHLY_PLAN_SAMPLE", o["origin_id"]
        assert o["path"].startswith("references/samples/monthly/"), o["origin_id"]
        assert "url" not in o and "retrieved_at" not in o and "license" not in o
        for token in ("키드키즈", "꼬망세", "http", "www.", "blog"):
            assert token not in json.dumps(o, ensure_ascii=False), (o["origin_id"], token)

    for a in raw["activities"]:
        blob = json.dumps(a, ensure_ascii=False)
        for token in ("키드키즈", "꼬망세", "http", "www.", "blog", "source_url"):
            assert token not in blob, (a["activity_id"], token)


def test_real_catalog_records_excluded_institution_specific_items(raw):
    excluded = raw["exclusion_policy"]["excluded_items"]
    assert len(excluded) > 0
    declared = {o["origin_id"] for o in raw["origins"]}
    for item in excluded:
        assert item["origin_id"] in declared
        assert item["reason"]


def test_real_catalog_excludes_named_facilities_from_labels(raw):
    for a in raw["activities"]:
        for token in ("만수계곡", "탄금", "능암늪", "성불산", "무궁화길", "민속박물관", "롤러장", "우리 원"):
            assert token not in a["label"], (a["activity_id"], token)


def test_real_catalog_activity_ids_and_labels_are_unique(raw):
    ids = [a["activity_id"] for a in raw["activities"]]
    labels = [a["label"] for a in raw["activities"]]
    assert len(set(ids)) == len(ids)
    assert len(set(labels)) == len(labels)


def test_real_catalog_coverage_counts_match_content(raw):
    cov = raw["coverage"]
    assert cov["item_count"] == len(raw["activities"])
    assert cov["source_count"] == len(raw["origins"])
    readable = [o for o in raw["origins"] if o["readable_pages"]]
    assert cov["readable_source_count"] == len(readable)
    assert set(cov["age_coverage"]) == {
        x for a in raw["activities"] for x in a["supported_ages"]
    }


# ----------------------------------- 테스트 fixture로 승인 동작 검증 (파일 무수정)


def test_approved_fixture_becomes_active(payload):
    c = approved(payload)
    assert c.is_active
    assert c.activation_status is ActivationStatus.HUMAN_APPROVED


def test_approved_fixture_yields_candidates(payload):
    c = approved(payload)
    got = c.eligible_candidates(
        section_key=OUTDOOR, calendar_month=9, ages=frozenset({4})
    )
    assert len(got) > 0
    for a in got:
        assert a.supports_month(9)
        assert a.supports_age_set(frozenset({4}))
        assert a.setting is ActivitySetting.OUTDOOR


def test_approved_fixture_has_no_candidates_in_uncovered_months(payload):
    """월 커버리지 공백이 후보 0으로 정직하게 나타난다. 예외가 아니다."""
    c = approved(payload)
    for month in (4, 5, 6, 7, 8, 10, 11, 12, 1, 2):
        assert c.eligible_candidates(
            section_key=OUTDOOR, calendar_month=month, ages=frozenset({3, 4, 5})
        ) == (), month


def test_approved_fixture_still_rejects_safety_slot(payload):
    c = approved(payload)
    assert c.eligible_candidates(
        section_key="safety_education", calendar_month=9, ages=frozenset({4})
    ) == ()


def test_approved_json_fixture_loads_through_the_real_adapter(tmp_path, payload):
    """승인 동작은 승인된 JSON fixture로만 재현한다."""
    repo = approved_catalog_file(tmp_path, payload)
    c = repo.get_catalog(CATALOG_ID, VERSION)
    assert c.is_active
    assert len(c.eligible_candidates(
        section_key=OUTDOOR, calendar_month=9, ages=frozenset({4})
    )) > 0


def test_reading_the_real_catalog_does_not_modify_it():
    before = LEGACY_ACTIVITY_CATALOG_PATH.read_bytes()
    JsonActivityReferenceRepository(LEGACY_ACTIVITY_CATALOG_PATH).get_catalog(CATALOG_ID, VERSION)
    assert LEGACY_ACTIVITY_CATALOG_PATH.read_bytes() == before
    assert (
        json.loads(LEGACY_ACTIVITY_CATALOG_PATH.read_text(encoding="utf-8"))["review"][
            "domain_owner_approval"
        ]
        == "PENDING_HUMAN_REVIEW"
    )


def test_production_api_has_no_approval_bypass_parameter():
    """어떤 public production API도 승인 우회 입력을 받지 않는다."""
    import inspect

    from ssuksak.adapters import activity_reference_schema as schema_mod
    from ssuksak.planning.application.monthly_ports import ActivityReferenceRepository
    from ssuksak.planning.domain import activity_reference as domain_mod

    banned = {"activation_override", "approval_override", "force_active", "runtime_active"}
    targets = [
        JsonActivityReferenceRepository.__init__,
        JsonActivityReferenceRepository.get_catalog,
        JsonActivityReferenceRepository._load,
        InMemoryActivityReferenceRepository.__init__,
        InMemoryActivityReferenceRepository.get_catalog,
        InMemoryActivityReferenceRepository.add,
        ActivityReferenceRepository.get_catalog,
        load_activity_catalog_from_dict,
        schema_mod.parse_activity_reference_payload,
        domain_mod.ActivityCatalog.eligible_candidates,
        domain_mod.ActivityCatalog.get,
        domain_mod.ActivityCatalog.covers_month,
    ]
    for fn in targets:
        params = set(inspect.signature(fn).parameters)
        assert not (params & banned), (fn, params & banned)

    for cls in (domain_mod.ActivityCatalog, domain_mod.ActivityCandidate):
        assert not (set(cls.__dataclass_fields__) & banned), cls


def test_production_source_contains_no_bypass_identifier():
    """문서 문장이 아니라 **코드**에 우회 식별자가 없다."""
    import ast

    for mod in (
        "src/ssuksak/adapters/activity_reference_schema.py",
        "src/ssuksak/adapters/json_activity_reference_repository.py",
        "src/ssuksak/planning/domain/activity_reference.py",
    ):
        tree = ast.parse(pathlib.Path(mod).read_text(encoding="utf-8"))
        names = {
            n.id if isinstance(n, ast.Name) else n.attr
            for n in ast.walk(tree)
            if isinstance(n, (ast.Name, ast.Attribute))
        }
        names |= {
            a.arg
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            for a in list(n.args.args) + list(n.args.kwonlyargs)
        }
        for banned in ("activation_override", "approval_override", "force_active"):
            assert banned not in names, (mod, banned)


# --------------------------------------------------- exact id / version


def test_wrong_catalog_id_returns_none():
    assert JsonActivityReferenceRepository(LEGACY_ACTIVITY_CATALOG_PATH).get_catalog("nope", VERSION) is None


def test_wrong_version_returns_none():
    assert (
        JsonActivityReferenceRepository(LEGACY_ACTIVITY_CATALOG_PATH).get_catalog(CATALOG_ID, "v0.0.1") is None
    )


@pytest.mark.parametrize("version", ["latest", "LATEST", "*", "", "activity-reference-v0"])
def test_no_latest_version_autodiscovery(version):
    assert JsonActivityReferenceRepository(LEGACY_ACTIVITY_CATALOG_PATH).get_catalog(CATALOG_ID, version) is None


def test_missing_file_raises(tmp_path):
    repo = JsonActivityReferenceRepository(tmp_path / "absent.json")
    with pytest.raises(FileNotFoundError):
        repo.get_catalog(CATALOG_ID, VERSION)


# ------------------------------------------------------------ fail-fast


def test_non_object_payload_is_rejected():
    with pytest.raises(ActivityReferenceSchemaError, match="object여야"):
        load_activity_catalog_from_dict([1, 2, 3])


def test_malformed_json_raises(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        JsonActivityReferenceRepository(p).get_catalog(CATALOG_ID, VERSION)


@pytest.mark.parametrize(
    "key",
    ["schema_version", "catalog_id", "catalog_version", "review", "coverage", "origins", "activities"],
)
def test_missing_top_level_key_is_not_defaulted(payload, key):
    del payload[key]
    with pytest.raises(ActivityReferenceSchemaError):
        load_activity_catalog_from_dict(payload)


def test_wrong_schema_version_is_rejected(payload):
    payload["schema_version"] = "activity-reference.schema.v1"
    with pytest.raises(ActivityReferenceSchemaError, match="schema_version"):
        load_activity_catalog_from_dict(payload)


def test_empty_activities_is_rejected(payload):
    payload["activities"] = []
    with pytest.raises(ActivityReferenceSchemaError, match="비어 있다"):
        load_activity_catalog_from_dict(payload)


def test_unknown_approval_value_is_rejected(payload):
    payload["review"]["domain_owner_approval"] = "APPROVED"
    with pytest.raises(ActivityReferenceSchemaError):
        load_activity_catalog_from_dict(payload)


def test_missing_approval_is_rejected(payload):
    del payload["review"]["domain_owner_approval"]
    with pytest.raises(ActivityReferenceSchemaError):
        load_activity_catalog_from_dict(payload)


def test_runtime_active_in_file_is_rejected(payload):
    payload["runtime_active"] = True
    with pytest.raises(ActivityReferenceSchemaError, match="runtime_active"):
        load_activity_catalog_from_dict(payload)


def test_activation_status_in_file_is_rejected(payload):
    payload["activation_status"] = "HUMAN_APPROVED"
    with pytest.raises(ActivityReferenceSchemaError, match="activation_status"):
        load_activity_catalog_from_dict(payload)


def test_runtime_active_on_activity_is_rejected(payload):
    payload["activities"][0]["runtime_active"] = True
    with pytest.raises(ActivityReferenceSchemaError, match="runtime_active"):
        load_activity_catalog_from_dict(payload)


def test_safety_flags_field_is_rejected(payload):
    payload["activities"][0]["safety_flags"] = ["교통안전"]
    with pytest.raises(ActivityReferenceSchemaError, match="safety_flags"):
        load_activity_catalog_from_dict(payload)


def test_activity_area_field_is_rejected(payload):
    payload["activities"][0]["activity_area"] = "physical"
    with pytest.raises(ActivityReferenceSchemaError, match="activity_area"):
        load_activity_catalog_from_dict(payload)


def test_tags_field_is_rejected(payload):
    payload["activities"][0]["tags"] = ["가을"]
    with pytest.raises(ActivityReferenceSchemaError, match="tags"):
        load_activity_catalog_from_dict(payload)


def test_safety_education_placement_slot_is_rejected(payload):
    payload["activities"][0]["placement_slots"] = ["safety_education"]
    with pytest.raises(ActivityReferenceSchemaError, match="법정 안전교육"):
        load_activity_catalog_from_dict(payload)


def test_safety_education_alongside_outdoor_is_rejected(payload):
    payload["activities"][0]["placement_slots"] = ["outdoor_play", "safety_education"]
    with pytest.raises(ActivityReferenceSchemaError, match="법정 안전교육"):
        load_activity_catalog_from_dict(payload)


@pytest.mark.parametrize("slot", ["focus", "indoor_alternative", "made_up"])
def test_unknown_placement_slot_is_rejected(payload, slot):
    payload["activities"][0]["placement_slots"] = [slot]
    with pytest.raises(ActivityReferenceSchemaError, match="placement slot"):
        load_activity_catalog_from_dict(payload)


@pytest.mark.parametrize("setting", ["outdoor", "OUT", "BOTH", ""])
def test_unknown_setting_is_rejected(payload, setting):
    payload["activities"][0]["setting"] = setting
    with pytest.raises(ActivityReferenceSchemaError, match="setting"):
        load_activity_catalog_from_dict(payload)


def test_unknown_theme_relation_is_rejected(payload):
    target = next(a for a in payload["activities"] if a["theme_links"])
    target["theme_links"][0]["relation"] = "BELONGS_TO"
    with pytest.raises(ActivityReferenceSchemaError, match="OBSERVED_TOGETHER"):
        load_activity_catalog_from_dict(payload)


def test_invented_curriculum_domain_is_rejected(payload):
    payload["activities"][0]["curriculum_links"] = [
        {"source_id": "s", "domain": "놀이영역", "source_page": 1}
    ]
    with pytest.raises(ActivityReferenceSchemaError, match="누리과정 5개 영역"):
        load_activity_catalog_from_dict(payload)


def test_valid_curriculum_domain_is_accepted(payload):
    payload["activities"][0]["curriculum_links"] = [
        {"source_id": "curriculum.mohw.notice-2019-152", "domain": "자연탐구", "source_page": 15}
    ]
    c = load_activity_catalog_from_dict(payload)
    assert c.activities[0].curriculum_links[0].domain == "자연탐구"


def test_unknown_matched_via_is_rejected(payload):
    payload["activities"][0]["evidence"][0]["matched_via"] = "FUZZY_MATCH"
    with pytest.raises(ActivityReferenceSchemaError, match="matched_via"):
        load_activity_catalog_from_dict(payload)


def test_unknown_label_derivation_type_is_rejected(payload):
    payload["activities"][0]["label_derivation_type"] = "LLM_GENERATED"
    with pytest.raises(ActivityReferenceSchemaError, match="label_derivation_type"):
        load_activity_catalog_from_dict(payload)


def test_unknown_activity_field_is_rejected(payload):
    payload["activities"][0]["difficulty"] = "easy"
    with pytest.raises(ActivityReferenceSchemaError):
        load_activity_catalog_from_dict(payload)


def test_unknown_evidence_field_is_rejected(payload):
    payload["activities"][0]["evidence"][0]["confidence"] = 0.9
    with pytest.raises(ActivityReferenceSchemaError):
        load_activity_catalog_from_dict(payload)


def test_undeclared_origin_in_evidence_is_rejected(payload):
    payload["activities"][0]["evidence"][0]["origin_id"] = "sample.monthly.ghost"
    with pytest.raises(ActivityReferenceSchemaError, match="선언되지 않은 origin_id"):
        load_activity_catalog_from_dict(payload)


def test_undeclared_activity_origin_is_rejected(payload):
    payload["activities"][0]["origin_id"] = "sample.monthly.ghost"
    with pytest.raises(ActivityReferenceSchemaError, match="선언되지 않은 origin_id"):
        load_activity_catalog_from_dict(payload)


def test_duplicate_origin_id_is_rejected(payload):
    payload["origins"].append(dict(payload["origins"][0]))
    with pytest.raises(ActivityReferenceSchemaError, match="중복된 origin_id"):
        load_activity_catalog_from_dict(payload)


def test_origin_without_id_is_rejected(payload):
    payload["origins"][0].pop("origin_id")
    with pytest.raises(ActivityReferenceSchemaError, match="origin_id"):
        load_activity_catalog_from_dict(payload)


def test_duplicate_activity_id_is_rejected(payload):
    payload["activities"].append(copy.deepcopy(payload["activities"][0]))
    with pytest.raises(ActivityReferenceSchemaError, match="중복된 activity_id"):
        load_activity_catalog_from_dict(payload)


def test_age_beyond_evidence_is_rejected(payload):
    payload["activities"][0]["supported_ages"] = [3, 4, 5]
    payload["activities"][0]["evidence"] = [payload["activities"][0]["evidence"][0]]
    payload["activities"][0]["evidence"][0]["age_scope"] = [3]
    with pytest.raises(ActivityReferenceSchemaError, match="age_scope"):
        load_activity_catalog_from_dict(payload)


def test_month_beyond_evidence_is_rejected(payload):
    payload["activities"][0]["applicable_months"] = [9, 10]
    with pytest.raises(ActivityReferenceSchemaError, match="관찰된 월"):
        load_activity_catalog_from_dict(payload)


def test_month_coverage_mismatch_is_rejected(payload):
    payload["coverage"]["month_coverage"] = [3, 9, 10]
    with pytest.raises(ActivityReferenceSchemaError, match="month_coverage"):
        load_activity_catalog_from_dict(payload)


@pytest.mark.parametrize("months", [[0], [13], [9, 9]])
def test_invalid_month_coverage_is_rejected(payload, months):
    payload["coverage"]["month_coverage"] = months
    with pytest.raises(ActivityReferenceSchemaError):
        load_activity_catalog_from_dict(payload)


def test_source_version_mismatch_is_rejected(payload):
    payload["activities"][0]["source_version"] = "activity-reference-v9.9.9"
    with pytest.raises(ActivityReferenceSchemaError, match="source_version"):
        load_activity_catalog_from_dict(payload)


def test_no_partial_load_on_a_single_bad_item(payload):
    """malformed item을 skip하고 계속 진행하지 않는다."""
    payload["activities"][-1]["supported_ages"] = []
    with pytest.raises(ActivityReferenceSchemaError):
        load_activity_catalog_from_dict(payload)


def test_blank_label_is_rejected(payload):
    payload["activities"][0]["label"] = "   "
    with pytest.raises(ActivityReferenceSchemaError, match="label"):
        load_activity_catalog_from_dict(payload)


def test_blank_observed_label_is_rejected(payload):
    payload["activities"][0]["evidence"][0]["observed_label"] = " "
    with pytest.raises(ActivityReferenceSchemaError, match="observed_label"):
        load_activity_catalog_from_dict(payload)


# ------------------------------------------------------------ InMemory


def test_in_memory_repository_exact_match(payload):
    c = approved(payload)
    repo = InMemoryActivityReferenceRepository([c])
    assert repo.get_catalog(CATALOG_ID, VERSION) is c
    assert repo.get_catalog(CATALOG_ID, "other") is None
    assert repo.get_catalog("other", VERSION) is None


def test_in_memory_repository_starts_empty():
    assert InMemoryActivityReferenceRepository().get_catalog(CATALOG_ID, VERSION) is None


def test_in_memory_repository_add(payload):
    repo = InMemoryActivityReferenceRepository()
    repo.add(approved(payload))
    assert repo.get_catalog(CATALOG_ID, VERSION) is not None


# ----------------------------------------- Adapter에 selection logic 없음


def test_repository_has_no_find_candidates():
    for cls in (JsonActivityReferenceRepository, InMemoryActivityReferenceRepository):
        assert not hasattr(cls, "find_candidates")
        assert not hasattr(cls, "select")
        assert not hasattr(cls, "rank")


def test_repository_protocol_exposes_only_get_catalog():
    from ssuksak.planning.application.monthly_ports import ActivityReferenceRepository

    public = [
        n for n in vars(ActivityReferenceRepository) if not n.startswith("_")
    ]
    assert public == ["get_catalog"]


def test_caching_returns_the_same_catalog_instance():
    repo = JsonActivityReferenceRepository(LEGACY_ACTIVITY_CATALOG_PATH)
    assert repo.get_catalog(CATALOG_ID, VERSION) is repo.get_catalog(CATALOG_ID, VERSION)
