"""연령 · Section · Setting 분류 (L1).

전부 **원문에 적힌 글자만** 본다. 의미 추론을 하지 않는다.

Setting 판정은 `docs/analysis/activity-v0-2-1-setting-audit.md`에서 196개 Activity /
288개 Evidence를 전수 재검증하며 확정한 5신호 우선순위를 그대로 옮긴 것이다.
그 감사에서 10종의 오탐을 잡아 고친 규칙이므로 임의로 단순화하지 않는다.
"""

from __future__ import annotations

import re

from .models import AgeEvidenceType, SourceSection, Setting

__all__ = [
    "SECTION_RULES",
    "extract_position_tag",
    "is_outdoor_row_label",
    "split_alternatives",
    "classify_age_page",
    "classify_section",
    "classify_setting",
    "row_label_setting",
]

# =========================================================== 연령

_AGE_RANGE = re.compile(r"만?\s*([0-5])\s*[-~∼]\s*([0-5])\s*세")
_AGE_LIST = re.compile(r"만?\s*([0-5])\s*[,·.]\s*([0-5])\s*(?:[,·.]\s*([0-5])\s*)?세")
_AGE_SINGLE = re.compile(r"만?\s*([0-5])\s*세")
_MIXED_WORD = re.compile(r"혼합\s*연?령?")


def classify_age_page(text: str) -> tuple[tuple[int, ...], AgeEvidenceType]:
    """한 **면**의 연령 집합과 단일연령 여부.

    범위(`만3~5세`) · 열거(`만4,5세`) · `혼합` 표기가 하나라도 있으면 단일연령이
    아니다. 남은 단일 표기만 모아도 마찬가지다 — 같은 면에 `3세`와 `5세`가 따로
    적혀 있으면 그것도 단일연령이 아니다.

    한 PDF 안에 만3세 면 / 만4세 면이 따로 있는 자료가 실제로 존재하므로
    **문서가 아니라 면 단위로** 판정한다.
    """
    multi = bool(_MIXED_WORD.search(text))
    ages: set[int] = set()

    t = text
    for m in _AGE_RANGE.finditer(t):
        a, b = int(m.group(1)), int(m.group(2))
        ages |= set(range(min(a, b), max(a, b) + 1))
        multi = True
    t = _AGE_RANGE.sub(" ", t)

    for m in _AGE_LIST.finditer(t):
        ages |= {int(g) for g in m.groups() if g}
        multi = True
    t = _AGE_LIST.sub(" ", t)

    for m in _AGE_SINGLE.finditer(t):
        ages.add(int(m.group(1)))

    target = tuple(sorted(a for a in ages if 3 <= a <= 5))
    if not target:
        return (), AgeEvidenceType.AGE_UNKNOWN
    if len(target) == 1 and not multi:
        return target, AgeEvidenceType.SINGLE_AGE_PAGE
    return target, AgeEvidenceType.MIXED_AGE_PAGE


# =========================================================== Section

SECTION_RULES: tuple[tuple[SourceSection, re.Pattern[str]], ...] = (
    # 바깥놀이를 **먼저** 본다. `바깥놀이 (대체활동)`은 두 줄짜리 병합 행 label이고
    # 윗줄이 바깥놀이 행이다. 대체 어휘가 섞였다는 이유로 행 전체를 실내대체로
    # 보면 바깥놀이 항목이 통째로 사라진다(서진어린이집 5개 월간계획안에서 확인).
    # 어느 항목이 대체안인지는 항목 단위로 `classify_setting`이 판정한다.
    (SourceSection.OUTDOOR_PLAY,
     re.compile(r"(바\s*깥\s*놀?\s*이?|실\s*외\s*놀?\s*이?|바\s*깥|실\s*외)")),
    (SourceSection.INDOOR_ALTERNATIVE,
     re.compile(r"(대\s*체\s*활\s*동|대\s*체\s*놀\s*이|실\s*내\s*대\s*체)")),
    (SourceSection.THEME,
     re.compile(r"(생\s*활\s*주\s*제|놀\s*이\s*주\s*제|예\s*상\s*놀\s*이\s*주\s*제|월\s*주\s*제|^\s*주\s*제\s*$|주\s*제\s*명)")),
    (SourceSection.WEEK_EXPERIENCE,
     re.compile(r"(소\s*주\s*제|예\s*상\s*놀\s*이|기\s*대\s*되\s*는|주\s*제\s*선\s*정|"
                r"교\s*사\s*의\s*기\s*대|함\s*께\s*하\s*는\s*놀\s*이|놀\s*이\s*이\s*야\s*기|"
                r"놀\s*이\s*흐\s*름|관\s*심|흥\s*미|주\s*별|주\s*차)")),
    (SourceSection.SAFETY_EDUCATION,
     re.compile(r"(안\s*전\s*교\s*육|비\s*상\s*대\s*응|소\s*방|재\s*난|훈\s*련)")),
    (SourceSection.INDOOR_PLAY,
     re.compile(r"(실\s*내\s*놀?\s*이?|실\s*내|쌓\s*기|역\s*할|미\s*술|언\s*어|음\s*률|과\s*학|"
                r"수\s*조\s*작|대\s*소\s*집\s*단)")),
    (SourceSection.DAILY_ROUTINE,
     re.compile(r"(기\s*본\s*생\s*활|일\s*상\s*생\s*활|등\s*원|전\s*이|휴\s*식|건\s*강\s*영\s*양|"
                r"급\s*간\s*식|점\s*심|낮\s*잠)")),
    (SourceSection.EVENT,
     re.compile(r"(행\s*사|가\s*정\s*과\s*의|체\s*험|견\s*학|특\s*별\s*활\s*동)")),
)
"""원문 label → canonical section. **먼저 일치하는 것이 이긴다.**

`source_label`(원문)은 언제나 따로 보존한다. canonical이 원문을 대체하지 않는다.
"""


_WEAK_OUTDOOR = re.compile(r"(산\s*책|나\s*들\s*이|텃\s*밭|숲)")
"""`산책` `텃밭` `나들이`는 바깥놀이 행 label이기도 하지만 다른 행 안에도 흔히 나온다.

실제 오탐 사례: 경상남도청어린이집 연간계획안의 행사 행 label이 여러 줄 병합으로
`4월 m식목일 기념 모종심기/가족 과 함께 하는 텃밭…`이 되어 그 행 전체가
바깥놀이로 분류됐다. 연간계획의 목표 문장이 outdoor Activity 후보가 되면 안 된다.

따라서 이 약한 토큰은 **label이 짧을 때만** 바깥놀이 행으로 본다. 실제 바깥놀이 행
label은 `텃밭` · `나들이` · `산책`처럼 짧다.
"""
_WEAK_OUTDOOR_MAX_CHARS = 8


def classify_section(label: str) -> SourceSection:
    t = (label or "").strip()
    if not t:
        return SourceSection.UNKNOWN
    for section, pattern in SECTION_RULES:
        if pattern.search(t):
            return section
    if _WEAK_OUTDOOR.search(t) and len(_nrm(t)) <= _WEAK_OUTDOOR_MAX_CHARS:
        return SourceSection.OUTDOOR_PLAY
    return SourceSection.UNKNOWN


# =========================================================== Setting

_OUTDOOR_WORDS = ("바깥놀이", "바깥 놀이", "실외놀이", "실외 놀이", "실외",
                  "야외놀이", "바깥", "실외활동", "산책", "나들이", "텃밭")
_INDOOR_WORDS = ("실내놀이", "실내 놀이", "실내활동", "실내대체활동", "실내대체",
                 "실내 대체", "실내")
_AMBIGUOUS_WORDS = ("실내외", "실내·외", "실내 외", "내외")
"""`실내외 놀이`는 실내와 실외를 **함께** 가리킨다. 어느 쪽 근거도 되지 못한다."""

_TAG = re.compile(r"[<\[【［]([^>\]】］]{1,14})[>\]】］]")
_LEADING_ALT = re.compile(
    r"^[-–—♥•◆▶⦁*\s]*"
    r"(?:[\[【(［]\s*(?:실내\s*)?대체"          # [대체] 【실내대체】 （대체
    r"|(?:실내\s*)?대체\s*(?:활동|놀이)?\s*[)\]】］:：\-–—])"  # 대체) 대체활동: 대체-
)
"""항목이 대체 표시로 **시작**하면 그 항목이 대체안이다.

여는 괄호가 잘려 `대체) 부채로 휴지떼기`처럼 닫는 괄호만 남는 표가 실제로 있다
(연제구연산더샵 7월). 그 형태도 대체안으로 본다.
"""

_BARE_POSITION_TAG = re.compile(
    r"[\[【［]\s*(바깥|실외|실내|대체|실내\s*대체|바깥\s*놀이|실외\s*놀이|실내\s*놀이)\s*[\]】］]"
)
"""괄호 안에 태그 낱말**만** 있는 표시.

`[바깥] / [대체]`가 별도 열에 찍히고 항목 label이 두 줄로 wrap되는 표가 있다
(예일어린이집). 줄을 재결합하면 태그가 항목 **가운데**로 들어간다.

    우리 동네 마트 [바깥] 방문하기   →  text `우리 동네 마트 방문하기` + setting OUTDOOR
    장바구니에 공 [대체] 넣기        →  text `장바구니에 공 넣기` + setting INDOOR_ALTERNATIVE

내용이 들어 있는 괄호(`(대체활동: 팽이가움직여요.)`)는 여기 걸리지 않는다.
그 안의 글자는 대체안 자체이므로 지우면 안 된다.
"""
_ALT_TAG = re.compile(r"[\[【(［]\s*(?:실내\s*)?대체[^\]】)］]*[\]】)］]")
_BARE_ALT_TAG = re.compile(r"^[\[【(［]\s*(?:실내\s*)?대체\s*(?:활동|놀이)?\s*[\]】)］]$")
_PREFIX_LABEL = re.compile(
    r"^[♥•◆▶⦁*\-–—\s]*"
    r"(바깥\s*놀이|실외\s*놀이|실내\s*놀이|실외\s*활동|실내\s*활동|실외|실내)"
    r"\s*[-–—:·]?"
)
_HANGUL = re.compile(r"[가-힣]")
_WS_MULTI = re.compile(r"\s+")


def _nrm(s: str) -> str:
    return re.sub(r"[\s.,·…~!?\"'()\[\]<>【】［］♥•◆▶⦁\-/]+", "", s or "")


def _classify_word(text: str) -> Setting | None:
    """단일 태그/라벨 어휘 판정. 실내가 더 구체적이므로 먼저 본다."""
    t = _nrm(text)
    if any(_nrm(w) in t for w in _AMBIGUOUS_WORDS):
        return None
    for w in _INDOOR_WORDS:
        if _nrm(w) in t:
            return Setting.INDOOR
    for w in _OUTDOOR_WORDS:
        if _nrm(w) in t:
            return Setting.OUTDOOR
    return None


_STRONG_OUTDOOR_ROW = re.compile(r"(바\s*깥\s*놀?\s*이?|실\s*외\s*놀?\s*이?|바\s*깥|실\s*외)")


def is_outdoor_row_label(label: str) -> bool:
    """이 행 label이 **바깥놀이 행**인가.

    Outdoor Loss의 분모를 정의한다. 2026-09-13 줄 기반 baseline(16%)이 센 것과
    같은 어휘 — `바깥` · `실외` 계열 — 만 본다. `산책` · `텃밭` · `나들이`는
    baseline 분모에 없었고 다른 행 label 안에도 흔히 나타나므로 넣지 않는다.

    실내 어휘가 단독으로 있으면 바깥놀이 행이 아니다.
    """
    t = (label or "").strip()
    if not t or not _STRONG_OUTDOOR_ROW.search(t):
        return False
    return row_label_setting(t) is Setting.OUTDOOR


def row_label_setting(label: str) -> Setting | None:
    """행 label 판정.

    바깥놀이와 대체가 함께 있으면 **바깥놀이 행**이다. 표에서
    `바깥놀이 / [대체활동]`은 두 줄짜리 병합 행 label이고 윗줄이 바깥놀이 행이다.
    `대체`가 섞였다는 이유만으로 뒤집으면 바깥놀이 행 전체가 잘못된다.
    """
    t = _nrm(label)
    if any(_nrm(w) in t for w in _AMBIGUOUS_WORDS) and not any(
        _nrm(w) in t for w in ("바깥놀이", "바깥", "산책")
    ):
        return None
    if any(_nrm(w) in t for w in _OUTDOOR_WORDS):
        return Setting.OUTDOOR
    if any(_nrm(w) in t for w in _INDOOR_WORDS):
        return Setting.INDOOR
    return None


def extract_position_tag(item: str) -> tuple[str, Setting | None]:
    """항목 안에 박힌 **낱말뿐인 위치 태그**를 떼어내고 그 의미를 돌려준다.

    태그가 항목 가운데로 들어간 표(태그 전용 열 + wrap)를 바로잡는다.
    태그가 없으면 원문과 None을 그대로 돌려준다.
    """
    text = item or ""
    found = _BARE_POSITION_TAG.findall(text)
    if not found:
        return text.strip(), None
    cleaned = _WS_MULTI.sub(" ", _BARE_POSITION_TAG.sub(" ", text)).strip()
    # 여러 태그가 섞이면 대체가 이긴다 — 대체안으로 표시된 부분이 있으면
    # 그 항목을 outdoor 후보로 쓰지 않는다.
    for raw in found:
        if "대체" in raw:
            return cleaned, Setting.INDOOR_ALTERNATIVE
    got = _classify_word(found[0])
    return cleaned, got


def classify_setting(item: str, *, row_label: str) -> Setting:
    """한 셀 항목의 setting.

    우선순위는 setting audit에서 확정한 5신호를 그대로 따른다. 구체적인 쪽이 이긴다.

    ① 항목 자신이 대체 표시로 시작        `[실내대체] 몸으로 자음 …`
    ② 대체 표기가 있는 줄
         내용포함형 `【대체활동 : X】`  → 괄호 **안**이 대체안
         구분자형   `A [실내대체] B`    → 괄호 **뒤**가 대체안
    ③ 괄호 없는 접두 표기                `♥바깥놀이-비석치기`
    ④ 셀 안 인라인 태그                  `<바깥놀이> …`
    ⑤ 행 label
    """
    text = (item or "").strip()
    if not text:
        return Setting.UNKNOWN

    # ① 항목 자신이 대체안
    if _LEADING_ALT.match(text):
        return Setting.INDOOR_ALTERNATIVE

    # ② 대체 표기가 있는 줄
    spans = [
        (m.start(), m.end(), bool(_BARE_ALT_TAG.match(m.group(0))))
        for m in _ALT_TAG.finditer(text)
    ]
    if spans:
        # 항목 전체를 하나로 보므로, 내용포함형 괄호 밖이면 본 항목이다.
        # 구분자형은 태그 뒤 전체가 대체안이다.
        first_bare = next((s for s in spans if s[2]), None)
        if first_bare is not None and first_bare[0] == 0:
            return Setting.INDOOR_ALTERNATIVE
        content_alt = next((s for s in spans if not s[2]), None)
        if content_alt is not None and content_alt[0] == 0:
            return Setting.INDOOR_ALTERNATIVE
        # 태그가 항목 중간/끝에 오면 본 항목은 바깥놀이 쪽이다.
        base = row_label_setting(row_label)
        return base if base is not None else Setting.OUTDOOR

    # ③ 괄호 없는 접두 표기
    prefix = _PREFIX_LABEL.match(text)
    if prefix:
        got = _classify_word(prefix.group(1))
        if got is not None:
            return got

    # ④ 셀 안 인라인 태그 — 항목 앞쪽에 나온 마지막 section 태그
    for tag in reversed(_TAG.findall(text)):
        got = _classify_word(tag)
        if got is not None:
            return got

    # ⑤ 행 label
    got = row_label_setting(row_label)
    return got if got is not None else Setting.UNKNOWN



_ALT_BOUNDARY = re.compile(
    r"[\[【(<［]?\s*(?:실\s*내\s*)?대\s*체\s*(?:활\s*동|놀\s*이)?\s*[\]】)>］]?"
    r"\s*[:：\-–—]?\s*"
)
"""대체안이 시작되는 자리. 괄호는 있어도 없어도 된다.

실제 Corpus에 전부 나타나는 형태다.

    A 【대체활동 : B】      A (대체활동: B)      A [대체놀이] B
    A 대체활동 – B         A(대체)             <대체놀이> A
"""

_ALT_FALSE_POSITIVE = re.compile(r"대\s*체(?=로|적|재)")
"""`대체로` · `대체적` 같은 부사는 대체안 표시가 아니다."""


def split_alternatives(item: str) -> list[tuple[str, bool]]:
    """항목을 `(본 항목, 대체안?)` 조각으로 나눈다.

    `A 【대체활동 : B】`는 **두 개의 서로 다른 활동**이다. 하나의 record로 두면
    A가 outdoor 후보인데 본문에 대체안 B가 섞여 들어간다. 나눠서 각각 기록한다.

    대체 표시가 맨 앞이면 항목 전체가 대체안이다.
    대체 표시가 없으면 원문 한 조각을 그대로 돌려준다.
    """
    text = (item or "").strip()
    if not text:
        return []
    spans = [
        m.span() for m in _ALT_BOUNDARY.finditer(text)
        if not _ALT_FALSE_POSITIVE.match(text, m.start())
    ]
    if not spans:
        return [(text, False)]

    out: list[tuple[str, bool]] = []
    head = text[: spans[0][0]].strip(" .,·([【<［")
    if head:
        out.append((head, False))
    for i, (_start, end) in enumerate(spans):
        stop = spans[i + 1][0] if i + 1 < len(spans) else len(text)
        seg = text[end:stop].strip().strip(" .,·)]】>］")
        if seg:
            out.append((seg, True))
    return out


def has_hangul(text: str) -> bool:
    return bool(_HANGUL.search(text or ""))
