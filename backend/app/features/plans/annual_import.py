"""연간 가져오기 — 교사가 확인한 12개월 표를 월별 주제형 DRAFT 로 저장한다(2026-11-01 I-A).

주제를 고르는 Rule 이 없으므로 Theme Reference 근거가 없다. 표에 직접 쓴 값은 `MANUAL`,
파일에서 뽑아 교사가 확인한 값은 `IMPORTED` 다. 원본 파일은 어디에도 저장하지 않고
형식 · sha256 만 본문 메타(`import_source`)에 남긴다.
"""

from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from ssuksak.planning import ActorId, YearlyApplicationError
from ssuksak.planning.application.import_yearly_plan import (
    ImportYearlyPlan,
    ImportYearlyPlanCommand,
)
from ssuksak.planning.domain.provenance import GenerationMethod

from app.features.plans.models import Plan
from app.features.plans.router import (
    _ALREADY_EXISTS,
    ANNUAL_UNIQUE,
    DbSession,
    _detail,
    _repo,
)
from app.features.plans.runtime import SystemClock, UuidGenerator
from app.features.plans.schemas import AnnualPlanOut
from app.shared.auth.dependency import CurrentUser
from app.shared.auth.ownership import require_own_class

router = APIRouter(prefix="/plans/annual", tags=["plans"])


class ImportFileIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: Literal["HWP", "HWPX", "DOCX", "PDF"]
    sha256: Annotated[str, Field(pattern=r"^[0-9a-fA-F]{64}$")]


class ImportMonthIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    month: int = Field(ge=1, le=12)
    theme: str
    sub_themes: list[str] = []

    @field_validator("sub_themes")
    @classmethod
    def drop_blank(cls, value: list[str]) -> list[str]:
        # 개수는 저장 때 제한하지 않는다. 주차 배치는 다듬기 화면에서 교사가 한다.
        return [item.strip() for item in value if item.strip()]


class ImportAnnualPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    class_id: int
    source: Literal["MANUAL", "FILE"]
    file: ImportFileIn | None = None
    months: list[ImportMonthIn]

    @model_validator(mode="after")
    def file_only_for_file_source(self):
        if (self.source == "FILE") != (self.file is not None):
            raise ValueError("FILE 출처에만 파일 정보를 넣습니다")
        return self


@router.post("/import", response_model=AnnualPlanOut, status_code=status.HTTP_201_CREATED)
def import_annual_plan(body: ImportAnnualPlan, session: DbSession, user: CurrentUser):
    klass = require_own_class(session, user, body.class_id)
    # 반 하나에 연간 하나 — 생성과 같은 409 다. 동시 요청은 아래 IntegrityError 가 받는다.
    duplicate = session.scalar(
        select(Plan.id).where(
            Plan.center_id == user.center_id,
            Plan.kind == "annual",
            Plan.classroom_ref == str(klass.id),
        )
    )
    if duplicate is not None:
        raise _ALREADY_EXISTS
    try:
        plan = ImportYearlyPlan(
            plan_repository=_repo(session, user), clock=SystemClock(), id_generator=UuidGenerator()
        ).execute(
            ImportYearlyPlanCommand(
                school_year=klass.school_year,
                classroom_ref=str(klass.id),
                target_ages=frozenset(range(klass.age_min, klass.age_max + 1)),
                method=(
                    GenerationMethod.MANUAL
                    if body.source == "MANUAL"
                    else GenerationMethod.IMPORTED
                ),
                themes=tuple((month.month, month.theme) for month in body.months),
                actor_id=ActorId(f"user_{user.id}"),
            )
        )
    except YearlyApplicationError as error:
        # 12개월 · 3월→2월 순서 · 중복/누락 · 빈 주제는 Core 가 가른다.
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "VALIDATION_FAILED",
                "message": "3월부터 다음 해 2월까지 열두 달의 주제를 빠짐없이 넣어주세요.",
                "fields": ["months"],
            },
        ) from error
    except IntegrityError as error:
        session.rollback()
        if getattr(getattr(error.orig, "diag", None), "constraint_name", None) == ANNUAL_UNIQUE:
            raise _ALREADY_EXISTS from error
        raise
    row = session.scalar(select(Plan).where(Plan.plan_ref == plan.plan_id.value))
    row.sub_themes = {str(month.month): month.sub_themes for month in body.months}  # type: ignore[union-attr]
    row.body = {  # type: ignore[union-attr]
        **row.body,  # type: ignore[union-attr]
        "import_source": {
            "source": body.source,
            "file": None if body.file is None else body.file.model_dump(),
        },
    }
    detail = _detail(row, plan)  # type: ignore[arg-type]
    session.commit()
    return detail
