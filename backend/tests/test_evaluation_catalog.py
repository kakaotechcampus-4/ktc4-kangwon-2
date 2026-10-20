import copy
import json
from dataclasses import FrozenInstanceError
from hashlib import sha256

import pytest

from app.features.evaluation import catalog


@pytest.fixture(autouse=True)
def clean_catalog_cache():
    catalog.load_catalog.cache_clear()
    yield
    catalog.load_catalog.cache_clear()


@pytest.fixture
def documents():
    return tuple(
        json.loads(path.read_text(encoding="utf-8"))
        for path in (catalog._INDICATORS_PATH, catalog._RULES_PATH)
    )


def _rehash(doc):
    doc["content_sha256"] = sha256(
        json.dumps(
            doc["areas"], ensure_ascii=False, sort_keys=True, separators=(", ", ": ")
        ).encode("utf-8")
    ).hexdigest()


def test_load_catalog_preserves_policy_and_order(documents):
    loaded = catalog.load_catalog()
    assert catalog.load_catalog() is loaded
    assert loaded.checklist_version == "daycare-evaluation-indicators-v2"
    assert loaded.rules_version == "checklist-rules-v1"
    assert [item.indicator for item in loaded.indicators] == [
        item["indicator"] for area in documents[0]["areas"] for item in area["indicators"]
    ]
    assert {item.indicator for item in loaded.indicators if item.kind == "AUTO"} == {"4-1", "4-2"}
    assert sum(item.kind == "SELF_CHECK" for item in loaded.indicators) == 7
    assert sum(item.kind == "EXCLUDED" for item in loaded.indicators) == 6
    assert loaded.get("4-2").rule["min_per_child"] == 2
    assert loaded.get("4-1").rule["plan"]["min_per_class"] == 1
    assert sum(len(item.elements) for item in loaded.indicators) == 19
    assert all(item.rule is None for item in loaded.indicators if item.kind != "AUTO")


def test_catalog_is_immutable_and_detached(documents):
    loaded = catalog.build_catalog(*documents)
    with pytest.raises(FrozenInstanceError):
        loaded.get("4-1").kind = "EXCLUDED"
    with pytest.raises(TypeError):
        loaded.get("4-1").rule["plan"]["min_per_class"] = 9
    documents[1]["indicators"]["4-1"]["plan"]["min_per_class"] = 9
    assert loaded.get("4-1").rule["plan"]["min_per_class"] == 1


@pytest.mark.parametrize("unknown", [False, True])
def test_rejects_rule_indicator_mismatch(documents, unknown):
    """메시지 이유까지 본다 — 번호만 보면 불일치 검사를 지워도 KeyError 경로로 통과한다."""
    rules = documents[1]["indicators"]
    if unknown:
        rules["9-9"] = {"kind": "EXCLUDED"}
    else:
        del rules["4-2"]
    reason = r"없는 번호 \['9-9'\]" if unknown else r"빠진 번호 \['4-2'\]"
    with pytest.raises(catalog.CatalogError, match=f"규칙 지표 불일치.*{reason}"):
        catalog.build_catalog(*documents)


_KIND, _MINIMUM, _UNIT = "알 수 없는 kind", "AUTO 조절값이", "AUTO unit · window"


@pytest.mark.parametrize(
    "path, value, reason",
    [
        (("4-2", "kind"), "UNKNOWN", _KIND),
        (("4-2", "min_per_child"), None, _MINIMUM),
        (("4-1", "daily_log"), None, "plan · daily_log가 필요하다"),
        (("4-2", "unit"), "CENTER", _UNIT),
        (("4-2", "window"), "SCHOOL_YEAR", _UNIT),
        (("4-2", "min_per_child"), True, _MINIMUM),
        (("4-2", "min_per_child"), 0, _MINIMUM),
        (("4-2", "document_kind"), " ", _MINIMUM),
        (("4-1", "plan", "min_per_class"), True, _MINIMUM),
        (("4-1", "plan", "plan_kind"), 1, _MINIMUM),
        (("4-1", "plan", "plan_kind"), "", _MINIMUM),
        (("4-1", "daily_log", "document_kind"), 1, _MINIMUM),
        (("4-1", "daily_log", "every_weekday"), False, _MINIMUM),
    ],
)
def test_rejects_invalid_rule(documents, path, value, reason):
    rule = documents[1]["indicators"]
    for key in path[:-1]:
        rule = rule[key]
    if value is None:
        del rule[path[-1]]
    else:
        rule[path[-1]] = value
    with pytest.raises(catalog.CatalogError, match=f"{path[0]}: {reason}"):
        catalog.build_catalog(*documents)


def test_rejects_changed_content(documents):
    documents[0]["areas"][0]["indicators"][0]["content"] += "가"
    with pytest.raises(catalog.CatalogError, match="승인 뒤 원문이 바뀌었다"):
        catalog.build_catalog(*documents)


def test_rejects_duplicate_indicator(documents):
    area = documents[0]["areas"][0]
    area["indicators"].append(copy.deepcopy(area["indicators"][0]))
    _rehash(documents[0])
    with pytest.raises(catalog.CatalogError, match="지표 번호가 겹친다"):
        catalog.build_catalog(*documents)


def test_v2_reads_elements_for_every_self_check(documents):
    doc, rules = documents
    doc["checklist_version"] = "daycare-evaluation-indicators-v2"
    for area in doc["areas"]:
        for item in area["indicators"]:
            if rules["indicators"][item["indicator"]]["kind"] == "SELF_CHECK":
                item["elements"] = [{"element": f"{item['indicator']}-1", "text": "평가요소 원문"}]
    _rehash(doc)
    loaded = catalog.build_catalog(*documents)
    assert all(len(item.elements) == 1 for item in loaded.indicators if item.kind == "SELF_CHECK")
    assert loaded.get("6-3").elements == (catalog.Element("6-3-1", "평가요소 원문"),)


@pytest.mark.parametrize("indicator", ["5-1", "5-2", "5-3", "6-1", "6-2", "6-3", "6-4"])
@pytest.mark.parametrize("missing_elements", [False, True])
def test_v2_rejects_each_self_check_without_elements(documents, indicator, missing_elements):
    doc, rules = documents
    doc["checklist_version"] = "daycare-evaluation-indicators-v2"
    for area in doc["areas"]:
        for item in area["indicators"]:
            if rules["indicators"][item["indicator"]]["kind"] == "SELF_CHECK":
                item["elements"] = [{"element": f"{item['indicator']}-1", "text": "평가요소 원문"}]
            if item["indicator"] == indicator:
                if missing_elements:
                    del item["elements"]
                else:
                    item["elements"] = []
    _rehash(doc)
    with pytest.raises(catalog.CatalogError, match=f"{indicator}: SELF_CHECK 평가요소가 없다"):
        catalog.build_catalog(*documents)


def test_v1_이_아닌_판은_평가요소가_비면_거절한다(documents):
    """v1 만 빈 목록을 봐줬다. 빈 목록이 「점검할 것이 없다」로 보이면 교사가 다 한 줄 안다."""
    documents[0]["checklist_version"] = "daycare-evaluation-indicators-v2"
    for area in documents[0]["areas"]:
        for item in area["indicators"]:
            item.pop("elements", None)
    _rehash(documents[0])
    with pytest.raises(catalog.CatalogError, match="SELF_CHECK 평가요소가 없다"):
        catalog.build_catalog(*documents)


_BAD_ELEMENT = "평가요소 element · text가 잘못됐다"


@pytest.mark.parametrize(
    "elements, reason",
    [
        ([{"element": "6-3-1", "text": "잘못된 지표"}], _BAD_ELEMENT),
        ([{"element": "5-1-0", "text": "잘못된 순번"}], _BAD_ELEMENT),
        ([{"element": "5-1-1", "text": 1}], _BAD_ELEMENT),
        ([{"element": "5-1-1", "text": "  "}], _BAD_ELEMENT),
        ([{"element": "5-1-1", "text": "원문"}] * 2, "평가요소 중복"),
        (["5-1-1"], "평가요소 항목은 객체여야 한다"),
        ({}, "elements는 배열이어야 한다"),
    ],
)
def test_rejects_invalid_elements_even_in_v1(documents, elements, reason):
    documents[0]["areas"][4]["indicators"][0]["elements"] = elements
    _rehash(documents[0])
    with pytest.raises(catalog.CatalogError, match=f"5-1: {reason}"):
        catalog.build_catalog(*documents)


def test_승인되지_않은_판은_거절한다(documents):
    """「승인 안 됨」이라고 적힌 파일을 그대로 쓰면 그 칸이 장식이 된다."""
    documents[0]["review"]["domain_owner_approval"] = "PENDING_HUMAN"
    documents[0]["review"]["runtime_active"] = False
    with pytest.raises(catalog.CatalogError, match="승인되지 않은 평가 지표 파일"):
        catalog.build_catalog(*documents)


def test_승인과_runtime_active_가_어긋나면_거절한다(documents):
    documents[0]["review"]["runtime_active"] = False
    with pytest.raises(catalog.CatalogError, match="승인되지 않은 평가 지표 파일"):
        catalog.build_catalog(*documents)


def test_v2_는_승인받았고_그대로_돌아간다():
    """2026-10-20 에 PM 이 승인했다(reviewer_pm_001). 파일 그대로 돌아야 한다.

    평가요소 19개는 「2025 어린이집 평가 자체평가 보고서 서식(어린이집용)」 영역5 · 영역6
    표에서 그대로 옮긴 것이다. 숫자가 바뀌면 원문이 바뀐 것이므로 사람이 다시 대조한다.
    """
    doc = json.loads(catalog._INDICATORS_V2_PATH.read_text(encoding="utf-8"))
    assert doc["review"]["domain_owner_approval"] == "HUMAN_APPROVED"
    assert doc["review"]["runtime_active"] is True
    assert doc["review"]["approved_by"] == "reviewer_pm_001"

    rules = json.loads(catalog._RULES_PATH.read_text(encoding="utf-8"))
    loaded = catalog.build_catalog(doc, rules)

    assert loaded.checklist_version == "daycare-evaluation-indicators-v2"
    assert sum(len(item.elements) for item in loaded.indicators) == 19
    assert {i.indicator: len(i.elements) for i in loaded.indicators if i.kind == "SELF_CHECK"} == {
        "5-1": 3,
        "5-2": 3,
        "5-3": 2,
        "6-1": 2,
        "6-2": 3,
        "6-3": 3,
        "6-4": 3,
    }
    assert all(e.text.strip() for i in loaded.indicators for e in i.elements)
