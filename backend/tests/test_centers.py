"""원 API 의 요청 검증과 공통 에러 봉투. DB 를 타지 않는 범위만 다룬다.

`POST /api/centers` 의 실제 저장과 `GET /api/centers/{id}/classes` 는
centers.region_sido · region_sigungu · classes.consent_confirmed_at 컬럼이
들어오는 마이그레이션 이후에 붙인다 — 아래 TODO 참고.
"""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.db import get_session
from app.features.centers.schemas import CenterCreate, ClassCreate
from app.main import app
from app.shared.school_year import school_year_of

client = TestClient(app)

VALID = {
    "name": "서충주어린이집",
    "director_name": "김원장",
    "region_sido": "충청북도",
    "region_sigungu": "충주시",
}
VALID_CLASS = {
    "name": "햇님반",
    "age_min": 3,
    "age_max": 4,
    "child_count": 18,
    "teacher_name": "김선생",
    "consent_confirmed": True,
}


def test_center_create_strips_surrounding_whitespace():
    body = CenterCreate(**{k: f"  {v}  " for k, v in VALID.items()})

    assert body.name == "서충주어린이집"
    assert body.director_name == "김원장"
    assert body.region_sido == "충청북도"
    assert body.region_sigungu == "충주시"


@pytest.mark.parametrize("blank", ["", " ", "   ", "\t", "\n"])
@pytest.mark.parametrize("field", list(VALID))
def test_center_create_rejects_blank_strings(field, blank):
    with pytest.raises(ValidationError):
        CenterCreate(**{**VALID, field: blank})


@pytest.mark.parametrize("missing", list(VALID))
def test_center_create_requires_every_field(missing):
    with pytest.raises(ValidationError):
        CenterCreate(**{k: v for k, v in VALID.items() if k != missing})


def test_center_create_applies_column_lengths():
    # 길이는 DB 컬럼에 맞춘다 — name 100 · director_name 50 · region 두 칸 각각 30.
    CenterCreate(
        **{
            **VALID,
            "name": "가" * 100,
            "director_name": "나" * 50,
            "region_sido": "다" * 30,
            "region_sigungu": "라" * 30,
        }
    )
    with pytest.raises(ValidationError):
        CenterCreate(**{**VALID, "name": "가" * 101})
    with pytest.raises(ValidationError):
        CenterCreate(**{**VALID, "director_name": "나" * 51})
    with pytest.raises(ValidationError):
        CenterCreate(**{**VALID, "region_sido": "다" * 31})
    with pytest.raises(ValidationError):
        CenterCreate(**{**VALID, "region_sigungu": "라" * 31})


def test_too_long_regions_are_reported_together_in_the_envelope():
    # 길이 초과도 첫 항목에서 멈추지 않고 전부 모은다.
    response = client.post(
        "/api/centers",
        json={**VALID, "region_sido": "다" * 31, "region_sigungu": "라" * 31},
    )

    assert response.status_code == 422
    assert response.json()["error"]["fields"] == ["region_sido", "region_sigungu"]


def test_center_create_rejects_legacy_region_field():
    # 구형 FE 가 보내는 region 이 조용히 버려지면 목요일 전환에서 원인을 못 찾는다.
    with pytest.raises(ValidationError):
        CenterCreate(**VALID, region="충청북도 충주시")


def test_invalid_body_returns_contract_error_envelope():
    response = client.post("/api/centers", json={**VALID, "name": "  "})

    assert response.status_code == 422
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == "VALIDATION_FAILED"
    assert isinstance(body["error"]["message"], str) and body["error"]["message"]
    # fields 는 하나여도 배열이다.
    assert body["error"]["fields"] == ["name"]
    assert "detail" not in body


def test_every_invalid_field_is_collected():
    response = client.post("/api/centers", json={"region_sigungu": "충주시"})

    assert response.status_code == 422
    fields = response.json()["error"]["fields"]
    assert fields == ["name", "director_name", "region_sido"]


def test_unknown_field_is_reported_not_ignored():
    response = client.post("/api/centers", json={**VALID, "region": "충청북도 충주시"})

    assert response.status_code == 422
    assert response.json()["error"]["fields"] == ["region"]


class _MissingCenterSession:
    """`session.get(Center, id)` 가 None 을 주는 최소 스텁. DB 없이 404 경로만 본다."""

    def get(self, model, pk):
        return None


def test_missing_center_returns_not_found_envelope():
    app.dependency_overrides[get_session] = lambda: _MissingCenterSession()
    try:
        response = client.get("/api/centers/999/classes")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "NOT_FOUND",
            "message": "원을 찾을 수 없습니다.",
            "fields": ["center_id"],
        }
    }


def test_center_id_path_param_is_validated():
    response = client.get("/api/centers/not-a-number/classes")

    assert response.status_code == 422
    # loc 의 "path" 접두사가 사용자 field 명으로 새지 않는다.
    assert response.json()["error"]["fields"] == ["center_id"]


# --- 반 생성 (docs/api-spec.md §2) ---


def test_class_create_accepts_the_contract_body():
    body = ClassCreate(**VALID_CLASS)

    assert (body.name, body.teacher_name) == ("햇님반", "김선생")
    assert (body.age_min, body.age_max) == (3, 4)
    assert body.child_count == 18
    assert body.consent_confirmed is True


def test_class_create_trims_and_rejects_blank_names():
    body = ClassCreate(**{**VALID_CLASS, "name": "  햇님반  ", "teacher_name": " 김선생 "})
    assert (body.name, body.teacher_name) == ("햇님반", "김선생")

    for field in ("name", "teacher_name"):
        for blank in ("", "   "):
            with pytest.raises(ValidationError):
                ClassCreate(**{**VALID_CLASS, field: blank})
    with pytest.raises(ValidationError):
        ClassCreate(**{**VALID_CLASS, "name": "반" * 51})


@pytest.mark.parametrize("ages", [(2, 4), (3, 6), (0, 0), (5, 3), (4, 3)])
def test_class_create_rejects_ages_outside_three_to_five_or_inverted(ages):
    with pytest.raises(ValidationError):
        ClassCreate(**{**VALID_CLASS, "age_min": ages[0], "age_max": ages[1]})


@pytest.mark.parametrize("ages", [(3, 3), (3, 4), (3, 5), (4, 5), (5, 5)])
def test_class_create_accepts_every_valid_range_including_mixed(ages):
    # 만3·만5 만 고른 반도 배열이 아니라 3 · 5 범위로 온다 (§2).
    body = ClassCreate(**{**VALID_CLASS, "age_min": ages[0], "age_max": ages[1]})
    assert (body.age_min, body.age_max) == ages


def test_class_create_treats_child_count_as_optional_positive():
    assert ClassCreate(**{**VALID_CLASS, "child_count": None}).child_count is None
    assert (
        ClassCreate(**{k: v for k, v in VALID_CLASS.items() if k != "child_count"}).child_count
        is None
    )
    for invalid in (0, -1):
        with pytest.raises(ValidationError):
            ClassCreate(**{**VALID_CLASS, "child_count": invalid})


def test_class_create_defaults_consent_to_false_and_rejects_unknown_fields():
    body = ClassCreate(**{k: v for k, v in VALID_CLASS.items() if k != "consent_confirmed"})
    assert body.consent_confirmed is False
    # 구형 FE 의 selected_ages 가 조용히 버려지지 않는다.
    with pytest.raises(ValidationError):
        ClassCreate(**VALID_CLASS, selected_ages=[3, 5])
    with pytest.raises(ValidationError):
        ClassCreate(**VALID_CLASS, school_year=2026)


@pytest.mark.parametrize(
    ("moment", "expected"),
    [
        ("2026-02-28T23:59:59+09:00", 2025),
        ("2026-03-01T00:00:00+09:00", 2026),
        ("2027-01-31T12:00:00+09:00", 2026),
        ("2027-02-28T23:59:59+09:00", 2026),
        ("2027-03-01T00:00:00+09:00", 2027),
    ],
)
def test_school_year_follows_the_march_boundary_in_kst(moment, expected):
    assert school_year_of(datetime.fromisoformat(moment)) == expected


@pytest.mark.parametrize(
    ("moment", "expected"),
    [
        # UTC 로는 둘 다 2월인데 KST 로는 경계를 넘는다 — month 를 그대로 보면 둘 다 전년도가 된다.
        ("2026-02-28T14:59:59+00:00", 2025),  # KST 2026-02-28 23:59:59
        ("2026-02-28T15:00:00+00:00", 2026),  # KST 2026-03-01 00:00:00
        # 윤년도 같다. 2028-02-29 15:00Z 는 KST 로 3월 1일이다.
        ("2028-02-29T14:00:00+00:00", 2027),  # KST 2028-02-29 23:00
        ("2028-02-29T15:00:00+00:00", 2028),  # KST 2028-03-01 00:00
        # 반대쪽 경계 — UTC 로는 3월인데 KST 로도 3월이다(변환이 날짜를 앞으로만 민다).
        ("2027-03-01T00:00:00+00:00", 2027),
    ],
)
def test_school_year_converts_to_kst_before_checking_march(moment, expected):
    assert school_year_of(datetime.fromisoformat(moment)) == expected


def test_creating_a_class_under_a_missing_center_returns_not_found():
    app.dependency_overrides[get_session] = lambda: _MissingCenterSession()
    try:
        response = client.post("/api/centers/999/classes", json=VALID_CLASS)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "NOT_FOUND",
            "message": "원을 찾을 수 없습니다.",
            "fields": ["center_id"],
        }
    }


def test_invalid_class_body_collects_every_field_in_the_contract_envelope():
    response = client.post("/api/centers/1/classes", json={"age_min": 2, "child_count": 0})

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_FAILED"
    assert body["error"]["fields"] == ["name", "age_min", "age_max", "child_count", "teacher_name"]
    assert "detail" not in body


# TODO(마이그레이션 A 이후): DB 를 타는 검증을 붙인다.
#   - POST /api/centers → 201 + centers 행 저장, 응답에 region_sido · region_sigungu
#   - GET /api/centers/{id}/classes → 200 {"items": []}
#   - center A 조회에 center B 의 반이 섞이지 않는다
#   - 없는 center → 404 {"error": {"code": "NOT_FOUND", "fields": ["center_id"]}}
#   - ClassResponse.consent_confirmed_at 직렬화(null 과 값 모두)
#   - POST /api/centers/{id}/classes → 201 + classes 행 저장, school_year 서버 계산값
#   - consent_confirmed=true → consent_confirmed_at 이 timezone-aware, false → None
#   - 같은 center·name·school_year 로 두 번 만들면? (계약에 중복 에러 코드가 없다 — 확인 필요)
#   이때 tests/conftest.py 에 function 스코프 트랜잭션 롤백 fixture 를 도입한다.
