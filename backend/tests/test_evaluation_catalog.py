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
    assert loaded.checklist_version == "daycare-evaluation-indicators-v1"
    assert loaded.rules_version == "checklist-rules-v1"
    assert [item.indicator for item in loaded.indicators] == [
        item["indicator"] for area in documents[0]["areas"] for item in area["indicators"]
    ]
    assert {item.indicator for item in loaded.indicators if item.kind == "AUTO"} == {"4-1", "4-2"}
    assert sum(item.kind == "SELF_CHECK" for item in loaded.indicators) == 7
    assert sum(item.kind == "EXCLUDED" for item in loaded.indicators) == 6
    assert loaded.get("4-2").rule["min_per_child"] == 2
    assert loaded.get("4-1").rule["plan"]["min_per_class"] == 1
    assert all(item.elements == () for item in loaded.indicators if item.kind == "SELF_CHECK")
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


def test_v3_requires_elements_for_self_check(documents):
    documents[0]["checklist_version"] = "daycare-evaluation-indicators-v3"
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
