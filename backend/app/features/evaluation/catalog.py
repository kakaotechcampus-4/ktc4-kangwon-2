"""승인된 평가 지표 원문과 제품 판정 규칙을 읽고 검사한다.

CLAUDE.md 「부가 기능이 죽어도 본 기능은 돌아간다」에 따라 서버 기동 때 검사하지 않는다.
처음 쓸 때만 읽는다. 원문 고정 · 규칙 분리는 ADR-019 결정 6 · 7, 분류는 ADR-022다.
"""

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType
from typing import Any

_ROOT = Path(__file__).resolve().parents[3] / "resources" / "evaluation"
_INDICATORS_PATH = _ROOT / "daycare_evaluation_indicators_v1.json"
_RULES_PATH = _ROOT / "checklist_rules_v1.json"


class CatalogError(ValueError):
    """평가제 자료가 계약에 맞지 않는다."""


@dataclass(frozen=True)
class Element:
    element: str
    text: str


@dataclass(frozen=True)
class Indicator:
    indicator: str
    area: int
    area_title: str
    title: str
    content: str
    kind: str
    rule: Mapping[str, Any] | None
    elements: tuple[Element, ...]


@dataclass(frozen=True)
class Catalog:
    checklist_version: str
    rules_version: str
    indicators: tuple[Indicator, ...]

    def get(self, indicator: str) -> Indicator:
        for item in self.indicators:
            if item.indicator == indicator:
                return item
        raise CatalogError(f"없는 지표: {indicator}")


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _has_text(value: Any) -> bool:
    """빈 문자열 · 공백뿐인 문자열은 값이 없는 것과 같다."""
    return isinstance(value, str) and bool(value.strip())


def _validate_auto(number: str, rule: Mapping[str, Any]) -> None:
    if rule.get("unit") not in ("CLASS", "CHILD") or rule.get("window") not in (
        "PREVIOUS_MONTH_START",
        "TWELVE_MONTHS_START",
    ):
        raise CatalogError(f"{number}: AUTO unit · window가 잘못됐다")
    if rule["unit"] == "CLASS":
        plan, daily_log = rule.get("plan"), rule.get("daily_log")
        if not isinstance(plan, Mapping) or not isinstance(daily_log, Mapping):
            raise CatalogError(f"{number}: plan · daily_log가 필요하다")
        minimum = plan.get("min_per_class")
        valid = (
            _has_text(plan.get("plan_kind"))
            and _has_text(daily_log.get("document_kind"))
            and daily_log.get("every_weekday") is True
        )
    else:
        minimum = rule.get("min_per_child")
        valid = _has_text(rule.get("document_kind"))
    if not valid or type(minimum) is not int or minimum < 1:
        raise CatalogError(f"{number}: AUTO 조절값이 잘못됐거나 빠졌다")


def _elements(source: Mapping[str, Any], version: str) -> tuple[Element, ...]:
    number = source["indicator"]
    raw = source.get("elements", [])
    if not isinstance(raw, list):
        raise CatalogError(f"{number}: elements는 배열이어야 한다")
    # ponytail: v1 은 평가요소가 나뉘어 있지 않아 0개를 허용한다(임시).
    #           v2(승석 — 평가요소 19개)가 오면 이 허용은 판 번호로 저절로 꺼진다.
    #           v2 의 `elements` 모양({element, text})은 승석과 합의 전 가정이다.
    if version != "daycare-evaluation-indicators-v1" and not raw:
        raise CatalogError(f"{number}: SELF_CHECK 평가요소가 없다")
    elements, seen = [], set()
    for item in raw:
        if not isinstance(item, Mapping):
            raise CatalogError(f"{number}: 평가요소 항목은 객체여야 한다")
        key, text = item.get("element"), item.get("text")
        if (
            not isinstance(key, str)
            or re.fullmatch(rf"{re.escape(number)}-[1-9][0-9]*", key) is None
            or not _has_text(text)
        ):
            raise CatalogError(f"{number}: 평가요소 element · text가 잘못됐다")
        if key in seen:
            raise CatalogError(f"{number}: 평가요소 중복: {key}")
        seen.add(key)
        elements.append(Element(key, text))
    return tuple(elements)


def build_catalog(indicators_doc: Mapping, rules_doc: Mapping) -> Catalog:
    """파일을 읽지 않고 원문과 규칙을 검사해 불변 카탈로그를 만든다."""
    try:
        areas = indicators_doc["areas"]
        digest = sha256(
            json.dumps(areas, ensure_ascii=False, sort_keys=True, separators=(", ", ": ")).encode(
                "utf-8"
            )
        ).hexdigest()
        if digest != indicators_doc.get("content_sha256"):
            raise CatalogError("승인 뒤 원문이 바뀌었다: content_sha256 불일치")
        rows = [(area, item) for area in areas for item in area["indicators"]]
        numbers = [item["indicator"] for _, item in rows]
        if len(numbers) != len(set(numbers)):
            raise CatalogError("지표 번호가 겹친다")
        rules = rules_doc["indicators"]
        missing, unknown = set(numbers) - set(rules), set(rules) - set(numbers)
        if missing or unknown:
            raise CatalogError(
                f"규칙 지표 불일치: 빠진 번호 {sorted(missing)}, 없는 번호 {sorted(unknown)}"
            )
        version = indicators_doc["checklist_version"]
        indicators = []
        for area, source in rows:
            number = source["indicator"]
            rule = rules[number]
            kind = rule.get("kind")
            if kind not in ("AUTO", "SELF_CHECK", "EXCLUDED"):
                raise CatalogError(f"{number}: 알 수 없는 kind: {kind}")
            if kind == "AUTO":
                _validate_auto(number, rule)
            indicators.append(
                Indicator(
                    number,
                    area["area"],
                    area["area_title"],
                    source["title"],
                    source["content"],
                    kind,
                    _freeze(rule) if kind == "AUTO" else None,
                    _elements(source, version) if kind == "SELF_CHECK" else (),
                )
            )
        return Catalog(version, rules_doc["rules_version"], tuple(indicators))
    except (KeyError, TypeError, AttributeError) as exc:
        raise CatalogError(f"평가제 자료 형식이 잘못됐다: {exc}") from exc


@lru_cache(maxsize=1)
def load_catalog() -> Catalog:
    return build_catalog(
        json.loads(_INDICATORS_PATH.read_text(encoding="utf-8")),
        json.loads(_RULES_PATH.read_text(encoding="utf-8")),
    )
