"""평가제 체크리스트 요청·응답 계약 (api-spec.md §12)."""

from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    ValidatorFunctionWrapHandler,
    field_validator,
    model_validator,
)

from app.features.evaluation.judge import Ratio


class CheckInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    element: str
    checked: Annotated[bool, Field(strict=True)]


class ChecksRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checks: list[CheckInput]

    @field_validator("checks", mode="wrap")
    @classmethod
    def element_error_keys(
        cls, value: Any, handler: ValidatorFunctionWrapHandler
    ) -> list[CheckInput]:
        try:
            return handler(value)
        except ValidationError as exc:
            errors: list[Any] = exc.errors(include_url=False)
            for error in errors:
                loc = error["loc"]
                if loc and isinstance(loc[0], int):
                    item = value[loc[0]]
                    element = item.get("element") if isinstance(item, dict) else None
                    key = (
                        (element, *loc[1:]) if isinstance(element, str) and element.strip() else ()
                    )
                    # 공통 오류 처리기가 body 같은 키를 접두사로 지우지 않도록 한 토큰으로 묶는다.
                    error["loc"] = (".".join(map(str, key)),) if key else ()
            raise ValidationError.from_exception_data(cls.__name__, errors) from None


class Period(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_: date = Field(alias="from")
    to: date


class IndicatorItem(BaseModel):
    indicator: str
    area: str
    title: str
    content: str


class AutoItem(IndicatorItem):
    kind: Literal["AUTO"] = "AUTO"
    verdict: Literal["SUPPORTED", "INSUFFICIENT", "NONE"]
    required: int | None
    count: int
    children: Ratio | None
    classes: Ratio | None
    plan_ids: list[int]
    document_ids: list[int]
    period: Period
    # 4-1 만 값이 있다 — 보육일지 · 계획안 조건을 따로 채운 반 수(ADR-074 결정 2). 4-2 는 null.
    journal_classes: Ratio | None
    plan_classes: Ratio | None


class CheckedElement(BaseModel):
    element: str
    text: str
    checked: bool
    checked_at: datetime | None


class Progress(BaseModel):
    checked: int
    total: int


class SelfCheckItem(IndicatorItem):
    kind: Literal["SELF_CHECK"] = "SELF_CHECK"
    elements: list[CheckedElement]
    progress: Progress
    complete: bool


# ── 평가 서류 도장 근거 (ADR-074) ────────────────────────────────────────
# 키는 화면 frontend/lib/workspace/evaluation-files.ts 의 TEACHER_DOCS · DIRECTOR_ITEMS id 와 같다.
# 목록에 없는 키는 스키마가 422 로 막는다.
DocKey = Literal["journal", "plan", "assessment", "parent", "training", "iep"]
# Literal 별칭의 __args__ 를 mypy 가 모른다. 실행 때는 값 튜플이다.
DOC_KEYS: tuple[str, ...] = DocKey.__args__  # type: ignore[attr-defined]
# 직접확인은 쌤플이 만들지 않는 서류만 받는다 — 쌤플 서류는 확정 문서로만 찍힌다(ADR-074 결정 3).
TeacherDocKey = Literal["parent", "training", "iep"]
DirectorKey = Literal[
    "operation-plan", "annual-plan", "interaction-record", "duty-training", "day-papers"
]
# Literal 별칭의 __args__ 를 mypy 가 모른다. 실행 때는 값 튜플이다.
DIRECTOR_KEYS: tuple[str, ...] = DirectorKey.__args__  # type: ignore[attr-defined]
FolderStatus = Literal["found", "partial", "missing"]
# 건수 칸은 Integer 다. 그 상한(2^31 - 1)만 막는다 — 교사 폴더 크기에 지어낸 상한을 두지 않는다.
Count = Annotated[int, Field(strict=True, ge=0, le=2_147_483_647)]


def _no_repeats(keys: list[str], what: str) -> None:
    if len(set(keys)) != len(keys):
        raise ValueError(f"같은 {what}이 두 번 들어 있습니다.")


class PeriodInput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    from_: date = Field(alias="from")
    to: date

    @model_validator(mode="after")
    def not_reversed(self) -> "PeriodInput":
        if self.from_ > self.to:
            raise ValueError("기간의 첫날이 마지막 날보다 늦습니다.")
        return self


class DocCheckInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doc: TeacherDocKey
    checked: Annotated[bool, Field(strict=True)]


class FolderResultInput(BaseModel):
    """폴더 검사 결과 한 줄. **파일 이름 칸이 없다**.

    이름은 화면 메모리에만 있다(ADR-045 · ADR-074 결정 5).
    """

    model_config = ConfigDict(extra="forbid")

    doc: DocKey
    status: FolderStatus
    period: PeriodInput
    files: Count
    gaps: Count

    @model_validator(mode="after")
    def counts_match_status(self) -> "FolderResultInput":
        # 화면 checkDoc 의 판정과 같은 관계 — 어긋나면 근거 줄이 서로 다른 말을 한다.
        if self.status == "missing" and self.files:
            raise ValueError("못 찾은 서류에 센 파일이 있습니다.")
        if self.status != "missing" and not self.files:
            raise ValueError("찾은 서류에 센 파일이 없습니다.")
        if (self.status == "partial") != (self.gaps > 0):
            raise ValueError("일부 빠짐일 때만 빈 날이 있습니다.")
        return self


class FolderScanInput(BaseModel):
    """새 폴더 검사. 이 교사의 폴더 결과를 통째로 바꾼다 — 빠진 서류의 옛 결과는 지운다."""

    model_config = ConfigDict(extra="forbid")

    results: Annotated[list[FolderResultInput], Field(min_length=1, max_length=len(DOC_KEYS))]

    @model_validator(mode="after")
    def one_per_doc(self) -> "FolderScanInput":
        _no_repeats([r.doc for r in self.results], "서류")
        return self


class DocumentsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checks: list[DocCheckInput] = []
    folder_scan: FolderScanInput | None = None

    @model_validator(mode="after")
    def something_to_save(self) -> "DocumentsRequest":
        if not self.checks and self.folder_scan is None:
            raise ValueError("저장할 체크나 폴더 검사 결과가 없습니다.")
        _no_repeats([c.doc for c in self.checks], "서류")
        return self


class DirectorCheckInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item: DirectorKey
    checked: Annotated[bool, Field(strict=True)]


class DirectorRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checks: Annotated[list[DirectorCheckInput], Field(min_length=1)]

    @model_validator(mode="after")
    def one_per_item(self) -> "DirectorRequest":
        _no_repeats([c.item for c in self.checks], "항목")
        return self


class FolderResult(BaseModel):
    status: FolderStatus
    scanned_at: datetime
    period: Period
    files: int
    gaps: int


class DocumentMark(BaseModel):
    """로그인한 교사의 서류 한 줄. 쌤플확정은 저장하지 않는다 — 화면이 AUTO 항목에서 센다."""

    doc: DocKey
    checked: bool
    checked_at: datetime | None
    folder: FolderResult | None


class DirectorCheck(BaseModel):
    item: DirectorKey
    checked: bool
    checked_at: datetime | None


class EvaluationChecklist(BaseModel):
    school_year: int
    items: list[Annotated[AutoItem | SelfCheckItem, Field(discriminator="kind")]]
    # 서류 6종은 로그인한 교사 것만(교사 단위), 원장 서류 5종은 원 전체(원 단위) — ADR-074 결정 4.
    # 늘 6줄 · 5줄을 같은 순서로 준다. 줄이 없으면 체크도 폴더 결과도 없는 것이다.
    documents: list[DocumentMark]
    director: list[DirectorCheck]
