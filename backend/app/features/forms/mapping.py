"""양식 라벨(hwp_form.labels() 결과) -> 표준 행 이름 매핑.

어린이집마다 hwp 양식에서 같은 개념을 다른 문구로 쓴다("주제"/"놀이주제"/"테마"
전부 같은 뜻). 이 모듈은 그 문구들을 표준 개념 키(topic, activity 등) 하나로
정규화한다. 규칙은 코드에 박아두지 않고 resources/forms/label_mapping.json 에서
읽는다 (docs/structure.md 의 "데이터를 코드에 하드코딩하지 않는다" 규칙).

DB 를 쓰지 않는다 — plans 등 다른 기능이 표준 키를 받아 자기 컬럼에 어떻게
넣을지는 그쪽 몫이다. 여기는 "라벨 문구 -> 표준 키" 변환까지만 한다.
"""

import json
import re
from functools import lru_cache
from pathlib import Path

_MAPPING_PATH = Path(__file__).resolve().parents[3] / "resources" / "forms" / "label_mapping.json"


def _normalize(label: str) -> str:
    """공백 차이(예: "활동 목표" vs "활동목표")를 흡수하기 위해 공백을 전부 없앤다."""
    return re.sub(r"\s+", "", label)


@lru_cache(maxsize=1)
def _alias_table() -> dict[str, str]:
    """정규화된 alias 문자열 -> 표준 키. 파일은 한 번만 읽고 캐시한다."""
    data = json.loads(_MAPPING_PATH.read_text(encoding="utf-8"))
    table: dict[str, str] = {}
    for concept_key, concept in data["concepts"].items():
        for alias in concept["aliases"]:
            norm = _normalize(alias)
            if norm in table and table[norm] != concept_key:
                raise ValueError(
                    f"alias 충돌: '{alias}' 가 '{table[norm]}' 과 '{concept_key}' 양쪽에 있다"
                )
            table[norm] = concept_key
    return table


def to_standard(label: str) -> str | None:
    """라벨 하나를 표준 키로 변환한다. 매핑에 없으면 None (미지원 라벨)."""
    return _alias_table().get(_normalize(label))


def map_labels(labels: list[str]) -> dict[str, str | None]:
    """라벨 리스트를 {원본 라벨: 표준 키 | None} 으로 변환한다.

    표준 키가 None 인 항목은 "월별 주제" 같은 헤더가 아니라 "3", "우리 반" 같은
    실제 데이터 값이거나, 아직 매핑표에 없는 새로운 표현이라는 뜻이다.
    """
    return {label: to_standard(label) for label in labels}


def _selfcheck():
    assert to_standard("주제") == "topic"
    assert to_standard("놀이주제") == "topic"
    assert to_standard("예상놀이") == "activity"
    assert to_standard("활동 목표") == "activity_goal"  # 공백 있어도 매칭
    assert to_standard("3") is None  # 데이터 값은 매핑 안 됨
    assert to_standard("존재하지않는라벨") is None
    print("self-check OK")


if __name__ == "__main__":
    _selfcheck()
