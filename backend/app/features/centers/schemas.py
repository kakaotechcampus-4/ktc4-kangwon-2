"""원·반 API 의 요청·응답 모델. 계약은 docs/api-spec.md §1 · §2 다."""

from datetime import datetime
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ModelWrapValidatorHandler,
    StringConstraints,
    TypeAdapter,
    ValidationError,
    model_validator,
)

# 빈 문자열과 공백만 있는 입력을 막는다. FE 가 trim 하지 않아도 서버에서 같은 값이 된다.
# max_length 는 DB 컬럼 길이에 맞춘 것만 건다 — models.py 에 근거가 없는 값을 지어내지 않는다.
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
PersonName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
# 지역 두 칸은 마이그레이션 A 가 centers.region_sido · region_sigungu 를 각각 String(30) 으로
# 확정했다. DB 가 자르기 전에 계약 형식 422 로 돌려준다.
RegionPart = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)]
# 학년도 기준 연 나이. 계약도 DB CHECK 도 3~5 뿐이다.
SelectedAge = Annotated[int, Field(ge=3, le=5)]


class CenterCreate(BaseModel):
    """`POST /api/centers` 요청. 지역은 두 값으로 받는다 (docs/api-spec.md §1)."""

    # 계약에 없는 필드를 조용히 버리면 구형 FE 가 보내는 region 이 무시된 채 201 이 나간다.
    # 422 로 드러내는 편이 목요일 FE 전환에서 빠진 곳을 찾기 쉽다.
    model_config = ConfigDict(extra="forbid")

    name: Name
    director_name: PersonName
    region_sido: RegionPart
    region_sigungu: RegionPart


class ClassCreate(BaseModel):
    """`POST /api/centers/{center_id}/classes` 요청 (docs/api-spec.md §2).

    `school_year` 는 받지 않는다 — 화면에 고르는 칸이 없고, FE 가 계산하면 브라우저 시계에 의존한다.
    연령은 `age_min` · `age_max` 범위다. 만3·만5 만 고른 반도 `3 · 5` 로 온다 — 배열로 받지 않는다.
    """

    model_config = ConfigDict(extra="forbid")

    name: PersonName
    age_min: SelectedAge
    age_max: SelectedAge
    # 목표 원아 수. 아직 모르는 반이 있어 선택이다(0 은 「아직 없음」이 아니라 잘못된 입력이다).
    child_count: Annotated[int, Field(ge=1)] | None = None
    teacher_name: PersonName
    # 동의 확인 체크박스. true 면 서버가 consent_confirmed_at 에 현재 시각을 넣는다.
    # false·미전송은 검증 실패가 아니다 — 아동 명단을 건너뛰는 경로가 정상이다(§2-1).
    consent_confirmed: bool = False

    @model_validator(mode="wrap")
    @classmethod
    def check_age_range(
        cls, data: Any, handler: ModelWrapValidatorHandler["ClassCreate"]
    ) -> "ClassCreate":
        errors = []
        try:
            result = handler(data)
        except ValidationError as exc:
            errors = exc.errors(include_url=False)
            # 다른 필드가 실패해도 유효한 두 연령의 관계 오류는 함께 수집한다.
            if not isinstance(data, dict):
                raise
            try:
                age_min, age_max = TypeAdapter(tuple[SelectedAge, SelectedAge]).validate_python(
                    (data.get("age_min"), data.get("age_max"))
                )
            except ValidationError:
                raise exc from None
        else:
            age_min, age_max = result.age_min, result.age_max

        if age_min > age_max:
            errors.extend(
                {
                    "type": "value_error",
                    "loc": (field,),
                    "input": value,
                    "ctx": {"error": ValueError("age_min 은 age_max 보다 클 수 없습니다.")},
                }
                for field, value in (("age_min", age_min), ("age_max", age_max))
            )
        if errors:
            raise ValidationError.from_exception_data(cls.__name__, errors)
        return result


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
