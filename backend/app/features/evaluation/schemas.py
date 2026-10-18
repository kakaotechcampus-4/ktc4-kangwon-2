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
            errors = exc.errors(include_url=False)
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


class EvaluationChecklist(BaseModel):
    school_year: int
    items: list[Annotated[AutoItem | SelfCheckItem, Field(discriminator="kind")]]
