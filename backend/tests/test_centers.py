"""원 API 의 요청 검증과 공통 에러 봉투. DB 를 타지 않는 범위만 다룬다.

`POST /api/centers` 의 실제 저장과 `GET /api/centers/{id}/classes` 는
centers.region_sido · region_sigungu · classes.consent_confirmed_at 컬럼이
들어오는 마이그레이션 이후에 붙인다 — 아래 TODO 참고.
"""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.db import get_session
from app.features.centers.schemas import CenterCreate
from app.main import app

client = TestClient(app)

VALID = {
    "name": "서충주어린이집",
    "director_name": "김원장",
    "region_sido": "충청북도",
    "region_sigungu": "충주시",
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


# TODO(마이그레이션 A 이후): DB 를 타는 검증을 붙인다.
#   - POST /api/centers → 201 + centers 행 저장, 응답에 region_sido · region_sigungu
#   - GET /api/centers/{id}/classes → 200 {"items": []}
#   - center A 조회에 center B 의 반이 섞이지 않는다
#   - 없는 center → 404 {"error": {"code": "NOT_FOUND", "fields": ["center_id"]}}
#   - ClassResponse.consent_confirmed_at 직렬화(null 과 값 모두)
#   이때 tests/conftest.py 에 function 스코프 트랜잭션 롤백 fixture 를 도입한다.
