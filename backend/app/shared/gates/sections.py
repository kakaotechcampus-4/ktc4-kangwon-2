"""해석형 문서의 3층 규격 검사 — 3단 게이트의 1·2단 (CLAUDE.md 「3단 게이트」).

    1  스키마      사실·해석·지원 셋뿐인가, 비지 않았나, 짧지 않나
    2  추출 대조   사실이 근거 원문을 이어붙인 것과 글자 하나까지 같은가
                   해석에 나온 숫자(횟수 · 날짜 · 인원)가 사실에도 있는가

모델을 부르지 않는다. 문서를 만들 때·고칠 때·확정할 때 모두 이 함수 하나를 지난다.
- 기능마다 따로 만들면 한쪽만 느슨해진다.
"""

import re
from collections.abc import Iterable, Sequence
from typing import Protocol

HEADINGS = frozenset({"사실", "해석", "지원"})

# docs/api-spec.md §11 「거절 규칙」의 "해석 · 지원이 20자 미만이다".
# 같은 절의 "상투어로만 돼 있다" 는 여기서 막지 않는다.
# - 무엇이 상투어인지는 근거 없이 목록을 박으면 안 되는 판단이라 팀이 정할 때까지 길이만 본다.
MIN_BODY_LENGTH = 20

# 「3회」 · 「9월 22일」 · 「1.5」 에서 숫자만 뽑는다.
_NUMBER = re.compile(r"\d+(?:\.\d+)?")


class SectionLike(Protocol):
    heading: str
    body: str
    source_ids: Sequence[int]


def join_facts(source_texts: Iterable[str]) -> str:
    """근거 원문을 `사실` 로 잇는다. 만들 때와 대조할 때 같은 함수를 써야 어긋나지 않는다."""
    return "\n\n".join(source_texts)


def check_sections(
    sections: Sequence[SectionLike],
    source_texts: Sequence[str],
    valid_source_ids: set[int],
) -> list[str]:
    """틀린 칸을 전부 모아 `fields` 로 돌려준다. 비어 있으면 통과다.

    `sections` 모양 자체가 틀리면(칸 이름·개수) `["sections"]` 하나만 준다.
    - 칸이 어긋난 채로 칸별 검사를 하면 엉뚱한 칸 이름이 섞여 나온다.
    """
    if len(sections) != len(HEADINGS) or {s.heading for s in sections} != HEADINGS:
        return ["sections"]

    by_heading = {s.heading: s for s in sections}
    facts = join_facts(source_texts)
    fields: list[str] = []

    # 근거가 하나도 없으면 해석 · 지원이 기댈 사실이 없다. 근거 기록으로 만든 문서는 늘 사실이 있어
    # 여기 걸리지 않는다 — 교사가 칸을 하나도 안 채운 일일 보육일지를 막는 길이다.
    if by_heading["사실"].body != facts or not facts.strip():
        fields.append("sections.사실")
    for heading in ("해석", "지원"):
        if len(by_heading[heading].body.strip()) < MIN_BODY_LENGTH:
            fields.append(f"sections.{heading}")
    if "sections.해석" not in fields and _unsupported_numbers(by_heading["해석"].body, facts):
        fields.append("sections.해석")
    for section in sections:
        if not set(section.source_ids) <= valid_source_ids:
            fields.append(f"sections.{section.heading}.source_ids")
    return fields


def _unsupported_numbers(interpretation: str, facts: str) -> set[str]:
    """해석에는 있는데 사실에는 없는 숫자. 비면 통과다.

    지원은 보지 않는다. 「다음 주 2회」처럼 앞으로의 계획이라 새 숫자가 나오는 게 정상이다.
    - 글자가 아니라 숫자 단위로 비교한다. 사실의 「10」 이 해석의 「1」 을 통과시키면 안 된다.
    - 고유명사는 보지 않는다. 형태소 분석 없이 고르면 오탐이 많아 3단 Judge 에 맡긴다.
    """
    return set(_NUMBER.findall(interpretation)) - set(_NUMBER.findall(facts))
