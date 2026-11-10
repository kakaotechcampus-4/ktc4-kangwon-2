"""해석형 문서의 3층 규격 검사 — 3단 게이트의 1·2단 (CLAUDE.md 「3단 게이트」).

    1  스키마      사실·해석·지원 셋뿐인가, 비지 않았나, 짧지 않나
    2  추출 대조   사실이 근거 원문을 이어붙인 것과 글자 하나까지 같은가
                   해석에 나온 숫자(횟수 · 날짜 · 인원)가 사실 · 상황에 있는가.
                   날짜 표현(「11월」 「4일」 「11/4」)의 숫자만 근거 날짜와도 대조한다.
                   기간(「3일 동안」)은 날짜가 아니라 사실과만 견준다

모델을 부르지 않는다. 문서를 만들 때·고칠 때·확정할 때 모두 이 함수 하나를 지난다.
- 기능마다 따로 만들면 한쪽만 느슨해진다.
"""

import datetime
import logging
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

# 2단이 실제로 몇 건을 잡는지 세려고 남긴다. 걸린 초안은 저장되지 않아서 로그 말고는 흔적이 없다.
logger = logging.getLogger("app.server")

HEADINGS = frozenset({"사실", "해석", "지원"})

# docs/api-spec.md §11 「거절 규칙」의 "해석 · 지원이 20자 미만이다".
# 같은 절의 "상투어로만 돼 있다" 는 여기서 막지 않는다.
# - 무엇이 상투어인지는 근거 없이 목록을 박으면 안 되는 판단이라 팀이 정할 때까지 길이만 본다.
MIN_BODY_LENGTH = 20

# 「3회」 · 「9월 22일」 · 「1.5」 에서 숫자만 뽑는다.
# 소수는 한 숫자다 — 「1.5일」은 1 과 5 가 아니다.
_NUM = r"\d+(?:\.\d+)?"
_NUMBER = re.compile(_NUM)
# 날짜 표현 — 「2026년」 「11월」 「4일」 「11/4」. 이 안의 숫자만 근거 날짜로 받는다.
# 기간은 날짜가 아니다 — 「3일 동안」 「3일간」 「3일째」 「3일 만에」의 3 은 사실과만 견준다.
# 근거 날짜가 3일이라고 지어낸 「3일 동안」이 통과하면 안 된다.
_DATE_EXPR = re.compile(
    rf"{_NUM}\s*(?:년|월|일)(?!\s*(?:동안|째|만에|간(?:의|에)?(?![가-힣])))|\d+\s*/\s*\d+"
)
# 문서 바깥에서 오는 값(#85). 사실에 없어도 되지만 **이 표현 안의 이 값만** 받는다.
# 「만 4세」 「4세반」 「4세」의 4 는 반 연령, 「5개 영역」 「5영역」의 5 는 누리과정 영역 수다.
# 개수 · 횟수는 여전히 사실과 견준다.
# 「3세트」 「3세대」는 나이가 아니다.
_AGE_EXPR = re.compile(r"(?:만\s*)?(\d+)\s*세(?!트|대)")
_DOMAIN_COUNT_EXPR = re.compile(r"(\d+)\s*(?:개\s*(?:의\s*)?)?영역")
NURI_DOMAIN_COUNT = 5


class SectionLike(Protocol):
    heading: str
    body: str
    source_ids: Sequence[int]


def join_facts(source_texts: Iterable[str]) -> str:
    """근거 원문을 `사실` 로 잇는다. 만들 때와 대조할 때 같은 함수를 써야 어긋나지 않는다."""
    return "\n\n".join(source_texts)


class SourceLike(Protocol):
    date: datetime.date | None
    context: str | None


@dataclass(frozen=True)
class InputExtras:
    """사실 말고 모델이 함께 받는 교사 입력 (ADR-088).

    texts  상황 글. 교사가 적은 글이라 숫자를 사실과 똑같이 친다
    dates  근거 날짜. **날짜 표현의 숫자만** 받는다 — 4일의 「4」가 「4개」를 통과시키면 안 된다
    ages   반 연령(age_min ~ age_max). **「만 N세」 「N세반」 「N세」 안의 숫자만** 받는다 (#85)
    """

    texts: tuple[str, ...] = ()
    dates: tuple[datetime.date, ...] = ()
    ages: tuple[int, ...] = ()


def input_extras(sources: Iterable[SourceLike], ages: Iterable[int] = ()) -> InputExtras:
    """근거 사본에서 상황과 날짜를 모은다. 만들 때 · 고칠 때 · 확정할 때 같은 함수를 쓴다.

    `ages` 는 그 반의 연령이다(`review.class_ages`). 사본에는 없어서 부르는 쪽이 넣는다.
    """
    texts, dates = [], []
    for source in sources:
        if source.date is not None:
            dates.append(source.date)
        if source.context:
            texts.append(source.context)
    return InputExtras(tuple(texts), tuple(dates), tuple(ages))


NO_EXTRAS = InputExtras()


def check_sections(
    sections: Sequence[SectionLike],
    source_texts: Sequence[str],
    valid_source_ids: set[int],
    *,
    stage: Literal["generate", "edit", "confirm", "reconfirm", "verify", "rewrite"],
    extras: InputExtras = NO_EXTRAS,
) -> list[str]:
    """틀린 칸을 전부 모아 `fields` 로 돌려준다. 비어 있으면 통과다.

    `sections` 모양 자체가 틀리면(칸 이름·개수) `["sections"]` 하나만 준다.
    - 칸이 어긋난 채로 칸별 검사를 하면 엉뚱한 칸 이름이 섞여 나온다.

    `stage` 는 로그에만 쓴다. 모델 출력이 걸린 것(generate)과 교사가 고친 글이 걸린 것(edit)은
    따로 세야 2단이 모델 오류를 몇 건 잡았는지 나온다.
    reconfirm 은 「다시 검토」 뒤 교사가 보낸 글이다 (documents/review.py).
    rewrite 는 모델이 고쳐 쓴 문장을 넣은 글이다 (documents/rewrite.py).

    `extras` 는 `input_extras` 가 만든 근거 상황 · 날짜다. 숫자 대조에만 쓴다.
    """
    fields, numbers = _check(sections, source_texts, valid_source_ids, extras)
    # 글은 찍지 않는다 (ADR-004). 숫자만으로는 아이를 알아볼 수 없고,
    # 걸린 것이 진짜 오류인지 오탐(「만 4세」 등)인지 가려내는 데 필요하다.
    logger.info(
        "gate_sections stage=%s result=%s fields=%s numbers=%s",
        stage,
        "fail" if fields else "pass",
        ",".join(fields) or "-",
        ",".join(sorted(numbers)) or "-",
    )
    return fields


def _check(
    sections: Sequence[SectionLike],
    source_texts: Sequence[str],
    valid_source_ids: set[int],
    extras: InputExtras = NO_EXTRAS,
) -> tuple[list[str], set[str]]:
    if len(sections) != len(HEADINGS) or {s.heading for s in sections} != HEADINGS:
        return ["sections"], set()

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
    numbers: set[str] = set()
    if "sections.해석" not in fields:
        numbers = _unsupported_numbers(
            by_heading["해석"].body, "\n".join([facts, *extras.texts]), extras.dates, extras.ages
        )
        if numbers:
            fields.append("sections.해석")
    for section in sections:
        # 비어 있으면 근거 연결이 끊긴 칸이다 — 부분집합 검사만으로는 [] 가 통과한다.
        if not section.source_ids or not set(section.source_ids) <= valid_source_ids:
            fields.append(f"sections.{section.heading}.source_ids")
    return fields, numbers


def _unsupported_numbers(
    interpretation: str,
    facts: str,
    dates: Iterable[datetime.date] = (),
    ages: Iterable[int] = (),
) -> set[str]:
    """해석에는 있는데 사실에는 없는 숫자. 비면 통과다.

    지원은 보지 않는다. 「다음 주 2회」처럼 앞으로의 계획이라 새 숫자가 나오는 게 정상이다.
    - 글자가 아니라 숫자 단위로 비교한다. 사실의 「10」 이 해석의 「1」 을 통과시키면 안 된다.
    - 근거 날짜의 연 · 월 · 일은 날짜 표현 안의 숫자에만 쓴다. 개수 · 횟수는 사실과만 견준다.
    - 고유명사는 보지 않는다. 형태소 분석 없이 고르면 오탐이 많아 3단 Judge 에 맡긴다.
    - 반 연령(「만 4세」 「4세반」) · 누리과정 영역 수(「5개 영역」 「5영역」)는
      그 표현 안의 그 값만 지운다(#85).
    """
    allowed = {str(a) for a in ages}

    def outside(m: re.Match[str], ok: set[str]) -> str:
        return " " if m.group(1) in ok else m.group(0)

    interpretation = _AGE_EXPR.sub(lambda m: outside(m, allowed), interpretation)
    interpretation = _DOMAIN_COUNT_EXPR.sub(
        lambda m: outside(m, {str(NURI_DOMAIN_COUNT)}), interpretation
    )
    known = set(_NUMBER.findall(facts))
    day_parts = {str(n) for d in dates for n in (d.year, d.month, d.day)}
    in_dates = {n for m in _DATE_EXPR.findall(interpretation) for n in _NUMBER.findall(m)}
    rest = set(_NUMBER.findall(_DATE_EXPR.sub(" ", interpretation)))
    return (rest - known) | (in_dates - known - day_parts)
