"""원·반 API 의 요청·응답 모델. 계약은 docs/api-spec.md §1 · §2 다."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

# 빈 문자열과 공백만 있는 입력을 막는다. FE 가 trim 하지 않아도 서버에서 같은 값이 된다.
# max_length 는 DB 컬럼 길이에 맞춘 것만 건다 — models.py 에 근거가 없는 값을 지어내지 않는다.
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
PersonName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
# region_sido · region_sigungu 는 마이그레이션 A 가 오기 전이라 컬럼 길이가 없다.
# 기존 region String(50) 을 근거로 길이를 확정하지 않는다 — 컬럼이 생기면 그때 맞춘다.
RegionPart = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class CenterCreate(BaseModel):
    """`POST /api/centers` 요청. 지역은 두 값으로 받는다 (docs/api-spec.md §1)."""

    # 계약에 없는 필드를 조용히 버리면 구형 FE 가 보내는 region 이 무시된 채 201 이 나간다.
    # 422 로 드러내는 편이 목요일 FE 전환에서 빠진 곳을 찾기 쉽다.
    model_config = ConfigDict(extra="forbid")

    name: Name
    director_name: PersonName
    region_sido: RegionPart
    region_sigungu: RegionPart


class CenterResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    director_name: str
    region_sido: str
    region_sigungu: str
    created_at: datetime


class ClassResponse(BaseModel):
    """`GET /api/centers/{center_id}/classes` 의 항목.

    teacher_id 는 인증(8주차) 전까지 항상 비어 있고 계약에도 없어 내보내지 않는다.
    updated_at 도 화면이 쓰지 않으므로 넣지 않는다.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    center_id: int
    name: str
    school_year: int
    age_min: int
    age_max: int
    child_count: int | None
    teacher_name: str
    consent_confirmed_at: datetime | None
    created_at: datetime


class ClassListResponse(BaseModel):
    """목록 봉투는 `{ items }` 하나로 통일한다 (docs/api-spec.md §2-1)."""

    items: list[ClassResponse]
