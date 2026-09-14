"""셀 → EvidenceRecord (L1).

줄 기반 추출이 잃던 내용을 여기서 되찾는다.

    줄 기반   `바깥` 행의 내용이 **다음 visual line**에 있으면 그 줄은 비어 보인다.
              2026-09-13 실측에서 바깥놀이 행 253건 중 41건(16%)이 이렇게 사라졌다.

    셀 기반   행 label과 내용은 **서로 다른 셀**이다. 같은 row band의 다른 열을
              읽으면 되므로 줄바꿈 위치와 무관하다.

`record_id`는 원문 좌표에서 만든다. 파서의 순회 순서가 아니라 **셀의 위치**에서
나오므로 같은 입력이면 언제나 같다.
"""

from __future__ import annotations

import re

from .cells import CELL_EXTRACTION_METHOD, Cell, PageCells
from .classifiers import (
    classify_section,
    classify_setting,
    extract_position_tag,
    has_hangul,
    is_outdoor_row_label,
    split_alternatives,
    row_label_setting,
)
from .models import (
    AgeEvidenceType,
    CellCoordinates,
    EvidenceRecord,
    EvidenceSourceType,
    ExtractionQuality,
    MachineReadability,
    ReusePolicy,
    Setting,
    SourceSection,
)

__all__ = ["PageContext", "build_page_records", "make_record_id"]

MIN_BODY_CHARS = 3
"""이보다 짧으면 활동명으로 쓸 수 없다. `등`, `외` 같은 잔여 토큰이다."""

MAX_BODY_CHARS = 80

MAX_OUTDOOR_BODY_CHARS = 40
"""바깥놀이 항목 하나가 이보다 길면 여러 항목이 한 줄에 붙었을 가능성이 크다.

전체 Corpus의 outdoor 항목 길이 중앙값은 12자다. 40자를 넘는 것은 원문 자체가
`텃밭 돌보기. 곤충 탐색, 모래놀이, …`처럼 열거형이거나 wrap 병합이 잘못된 경우다.
NEEDS_REVIEW로 두어 Grounding에서 빼고 사람이 보게 한다.
"""

_SPLIT = re.compile(r"[/·•⦁▸▶]")
_INLINE_TAG_SPLIT = re.compile(r"(?=<[^<>]{1,16}>)")
"""`<태그> 항목 <태그> 항목` 형태를 태그 앞에서 나눈다.

한 셀에 여러 활동이 `<자랑스런우리나라> 동대문놀이(대체활동: …) <추석> 명절전통놀이…`
처럼 이어 적힌 표가 있다(큰빛어린이집). 나누지 않으면 100자짜리 record 하나가 되어
Grounding에 쓸 수 없다.
"""
_BULLET = re.compile(r"^[-–—*·•⦁▸▶♥※\s]+")
_WS = re.compile(r"\s+")

_SECTION_ECHO = re.compile(
    r"^(바깥\s*놀이|실외\s*놀이|실내\s*놀이|대체\s*활동|안전\s*교육|기본\s*생활|"
    r"소주제|주제|활동|놀이|영역)\s*$"
)
"""행 label이 내용 칸에 그대로 메아리친 경우. 활동이 아니다."""

_FRAGMENT_TAIL = re.compile(r"(고|며|면서|서|으로|로|와|과|에|을|를|은|는|의)\s*$")
"""연결어미·조사로 끝나면 뒤가 잘렸을 가능성이 크다."""

_TOO_GENERIC_STANDALONE = re.compile(
    r"^(놀\s*이\s*를?\s*해\s*요[.]?|놀\s*이\s*해\s*요[.]?|해\s*요[.]?|"
    r"만\s*들\s*기|찾\s*기|하\s*기|가\s*기)$"
)
"""그 자체로는 활동명이 될 수 없는 꼬리말.

`친척집에 왜 왔니?` / `놀이를 해요.`처럼 한 활동이 두 줄로 나뉘었는데 앞줄이
물음표로 끝나 종결로 보이는 경우가 있다. 물음표를 무조건 비종결로 바꾸면
`우리집에 왜 왔니?`가 단독 활동명인 다른 Source가 깨진다.

그래서 합치지 않고 **꼬리말 쪽을 NEEDS_REVIEW로 내린다.** Grounding에서 빠지고
사람이 확인한다. 추측으로 붙이지 않는다.
"""


class PageContext:
    """한 면에서 모든 Record가 공유하는 값."""

    __slots__ = (
        "source_path", "source_sha256", "page", "institution_id",
        "institution_type", "year", "month", "age_scope", "age_evidence_type",
        "monthly_theme", "template_family", "machine_readability",
    )

    def __init__(
        self,
        *,
        source_path: str,
        source_sha256: str,
        page: int,
        institution_id: str | None,
        institution_type: str | None,
        year: int | None,
        month: int | None,
        age_scope: tuple[int, ...],
        age_evidence_type: AgeEvidenceType,
        monthly_theme: str | None,
        template_family: bool,
        machine_readability: MachineReadability,
    ) -> None:
        self.source_path = source_path
        self.source_sha256 = source_sha256
        self.page = page
        self.institution_id = institution_id
        self.institution_type = institution_type
        self.year = year
        self.month = month
        self.age_scope = age_scope
        self.age_evidence_type = age_evidence_type
        self.monthly_theme = monthly_theme
        self.template_family = template_family
        self.machine_readability = machine_readability


def make_record_id(
    sha256: str, page: int, row_top: float, column: int, item_index: int
) -> str:
    """결정론적 record_id.

    **순회 순번을 쓰지 않는다.** 셀의 원문 좌표에서 만들기 때문에 파서가 행·열을
    어떤 순서로 도는지 바뀌어도 같은 Evidence는 같은 id를 갖는다.
    """
    return (
        f"ev_{sha256[:12]}_p{page:02d}"
        f"_r{int(round(row_top)):05d}_c{column:02d}_i{item_index:02d}"
    )


def _normalize(raw: str) -> str:
    return _WS.sub(" ", _BULLET.sub("", raw or "")).strip()


def _quality(body: str, section: SourceSection, setting: Setting) -> ExtractionQuality:
    """추출 품질 판정. 억지로 VALID를 만들지 않는다."""
    t = body.strip()
    if not t or len(re.sub(r"\s", "", t)) < MIN_BODY_CHARS:
        return ExtractionQuality.INVALID
    if not has_hangul(t):
        return ExtractionQuality.INVALID
    if _SECTION_ECHO.match(t):
        return ExtractionQuality.INVALID
    if len(t) > MAX_BODY_CHARS:
        return ExtractionQuality.NEEDS_REVIEW
    if section is SourceSection.OUTDOOR_PLAY and len(t) > MAX_OUTDOOR_BODY_CHARS:
        return ExtractionQuality.NEEDS_REVIEW
    if _FRAGMENT_TAIL.search(t):
        return ExtractionQuality.NEEDS_REVIEW
    if _TOO_GENERIC_STANDALONE.match(t):
        return ExtractionQuality.NEEDS_REVIEW
    if section is SourceSection.UNKNOWN:
        return ExtractionQuality.NEEDS_REVIEW
    if section is SourceSection.OUTDOOR_PLAY and setting is Setting.UNKNOWN:
        return ExtractionQuality.NEEDS_REVIEW
    return ExtractionQuality.VALID


def _row_label_of(columns: dict[int, Cell]) -> tuple[str, int]:
    """행의 label과 그 열 번호.

    첫 열이 label 열이다. 다만 세로쓰기 병합 label(`바 / 깥 / 놀 / 이`)이 두 열로
    쪼개지는 표가 있으므로, 첫 열이 section으로 해석되지 않으면 두 번째 열까지
    합쳐 본다.
    """
    order = sorted(columns)
    if not order:
        return "", -1
    first = order[0]
    label = " ".join(columns[first].items)
    if classify_section(label) is SourceSection.UNKNOWN and len(order) > 1:
        merged = f"{label} {' '.join(columns[order[1]].items)}"
        if classify_section(merged) is not SourceSection.UNKNOWN:
            return merged.strip(), order[1]
    return label.strip(), first


def build_page_records(
    ctx: PageContext, page_cells: PageCells
) -> list[EvidenceRecord]:
    """한 면의 셀 전체를 Evidence Record로 만든다.

    표 선이 없으면 빈 목록이다. 이때도 추측으로 record를 만들지 않는다.
    """
    records: list[EvidenceRecord] = []

    for (row_top, row_bottom), columns in page_cells.rows():
        row_label, label_col = _row_label_of(columns)
        section = classify_section(row_label)
        if section in (SourceSection.UNKNOWN, SourceSection.THEME):
            # 주제 행은 면 context(`monthly_theme`)로 이미 쓰였고, 알 수 없는 행은
            # 기록하지 않는다.
            continue

        for column in sorted(columns):
            if column <= label_col:
                continue
            item_index = 0
            for raw_item in columns[column].items:
                for chunk in _INLINE_TAG_SPLIT.split(raw_item):
                    for piece in _SPLIT.split(chunk):
                        normalized = _normalize(piece)
                        if not normalized:
                            continue
                        cleaned, tag_setting = extract_position_tag(normalized)
                        if not cleaned:
                            continue
                        # `A 【대체활동 : B】`는 서로 다른 활동 둘이다. 나눠 기록한다.
                        for body, is_alt in split_alternatives(cleaned):
                            item_index += 1
                            if is_alt:
                                setting = Setting.INDOOR_ALTERNATIVE
                            elif tag_setting is not None:
                                setting = tag_setting
                            else:
                                setting = classify_setting(body, row_label=row_label)
                            eff_section = section
                            if setting is Setting.INDOOR_ALTERNATIVE:
                                eff_section = SourceSection.INDOOR_ALTERNATIVE
                            elif section is SourceSection.OUTDOOR_PLAY and (
                                setting is Setting.INDOOR
                            ):
                                eff_section = SourceSection.INDOOR_PLAY

                            quality = _quality(body, eff_section, setting)
                            is_experience = eff_section is SourceSection.WEEK_EXPERIENCE
                            records.append(
                                EvidenceRecord(
                                    record_id=make_record_id(
                                        ctx.source_sha256, ctx.page, row_top, column,
                                        item_index,
                                    ),
                                    source_type=EvidenceSourceType.INSTITUTION_SAMPLE,
                                    source_path=ctx.source_path,
                                    source_sha256=ctx.source_sha256,
                                    page=ctx.page,
                                    institution_id=ctx.institution_id,
                                    institution_type=ctx.institution_type,
                                    year=ctx.year,
                                    month=ctx.month,
                                    age_scope=ctx.age_scope,
                                    age_evidence_type=ctx.age_evidence_type,
                                    monthly_theme=ctx.monthly_theme,
                                    source_section=eff_section,
                                    source_label=row_label or "(label 없음)",
                                    week_position=None,   # 추정하지 않는다
                                    week_label=None,
                                    experience_text=body if is_experience else None,
                                    activity_text=None if is_experience else body,
                                    setting=setting,
                                    template_family=ctx.template_family,
                                    machine_readability=ctx.machine_readability,
                                    reuse_policy=ReusePolicy.CONTEXT_ONLY,
                                    extraction_quality=quality,
                                    extraction_method=CELL_EXTRACTION_METHOD,
                                    source_cell=CellCoordinates(
                                        row_top=row_top, row_bottom=row_bottom,
                                        column=column, item_index=item_index,
                                    ),
                                )
                            )
    return records


def outdoor_rows_of(page_cells: PageCells) -> list[tuple[float, str, list[str]]]:
    """바깥놀이 행과 그 내용 칸. Outdoor Loss 측정의 **분모**다.

    행 label 어휘는 줄 기반 baseline(16%)이 쓴 것과 같다 — `바깥` · `실외` 계열.
    분모를 바꿔 손실률을 낮추지 않기 위해서다.

    Returns:
        `(row_top, row_label, 내용 칸의 원문 항목들)` 목록.
    """
    out: list[tuple[float, str, list[str]]] = []
    for (row_top, _row_bottom), columns in page_cells.rows():
        row_label, label_col = _row_label_of(columns)
        if not is_outdoor_row_label(row_label):
            continue
        bodies: list[str] = []
        for column in sorted(columns):
            if column <= label_col:
                continue
            bodies.extend(columns[column].items)
        out.append((row_top, row_label, bodies))
    return out
