"""양식 API. 계약은 docs/api-spec.md §8, 저장 결정은 ADR-020 · ADR-026 이다.

**라우터가 둘이다.** `router` 의 parse 는 저장하지 않아 토큰 없이 열고,
`center_router` 의 등록 · 목록 · 삭제는 원의 자산이라 `main.py` 가 인증을 건다(ADR-017).
"""

import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_session
from app.features.forms import hwp_form, mapping
from app.features.forms.models import Form
from app.features.forms.schemas import FormListResponse, FormResponse, ParseResponse, Table
from app.features.forms.service import find_own_form
from app.shared.auth.dependency import CurrentUser
from app.shared.auth.ownership import require_own_center

router = APIRouter(prefix="/forms", tags=["forms"])
center_router = APIRouter(tags=["forms"])

DbSession = Annotated[Session, Depends(get_session)]

_ALLOWED_SUFFIXES = {".hwp", ".hwpx"}
# PR #89 의 마이그레이션 c1d4e7a92f31 에서 정한 제약 이름이다.
PLANS_FORM_FK = "fk_plans_form_id_forms"


def _unreadable(message: str) -> HTTPException:
    return HTTPException(
        status_code=422,
        detail={"code": "VALIDATION_FAILED", "message": message, "fields": ["file"]},
    )


def _extract(file: UploadFile) -> list[Table]:
    """업로드한 hwp/hwpx 에서 표를 뽑는다. parse 와 등록이 같이 쓴다 — 에러가 같아야 한다."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in _ALLOWED_SUFFIXES:
        shown = suffix or "(확장자 없음)"
        raise HTTPException(
            status_code=400,
            detail={
                "code": "UNSUPPORTED_FILE_TYPE",
                "message": f"지원하지 않는 파일 형식입니다: {shown} (.hwp, .hwpx만 허용)",
                "fields": ["file"],
            },
        )

    # hwp_form.extract() 가 경로를 요구하므로 업로드 내용을 임시 파일에 쓴다.
    # 이름은 고정한다 — 긴 한글 파일명은 리눅스 파일명 한도(255바이트)를 넘는다.
    # 확장자는 남긴다. extract() 가 그걸로 hwp · hwpx 를 가른다.
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir) / f"upload{suffix}"
        tmp_path.write_bytes(file.file.read())

        try:
            return hwp_form.extract(tmp_path)
        except RuntimeError as e:
            # 서버에 hwp5html 이 없는 등 환경 문제. 교사가 고칠 수 없으므로 503 이고
            # FE 는 재시도 버튼을 띄우지 않는다 (docs/api-spec.md §8).
            # str(e) 를 싣지 않는다 — "pip install pyhwp six" 가 교사 화면에 뜬다.
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "DEPENDENCY_UNAVAILABLE",
                    "message": "지금 양식을 읽을 수 없습니다. 운영 담당자에게 문의해주세요.",
                    "fields": [],
                },
            ) from e
        except Exception as e:
            # 손상된 파일, 변환 실패 등 요청 자체의 문제.
            # hwp5html 이 0 이 아닌 코드로 끝난 것도 여기다 —
            # CalledProcessError 는 RuntimeError 가 아니라서 이쪽으로 떨어진다.
            # str(e) 를 싣지 않는다 — 명령줄 · 임시 경로가 교사 화면에 뜬다 (§8).
            raise _unreadable(
                "양식을 읽지 못했습니다. "
                "파일이 비어 있거나 손상되었거나 암호가 걸려 있는지 확인해주세요."
            ) from e


@router.post("/parse", response_model=ParseResponse)
def parse_form(file: UploadFile) -> ParseResponse:
    """hwp/hwpx 양식 파일을 받아 표 구조와 라벨 후보를 반환한다.

    DB 를 쓰지 않는다 — 요청·응답만으로 끝나는 순수 변환 엔드포인트.
    """
    tables = _extract(file)
    labels = hwp_form.labels(tables)
    return ParseResponse(
        filename=file.filename or "",
        tables=tables,
        labels=labels,
        label_map=mapping.map_labels(labels),
    )


@center_router.post(
    "/centers/{center_id}/forms", response_model=FormResponse, status_code=status.HTTP_201_CREATED
)
def register_form(
    center_id: int, file: UploadFile, session: DbSession, user: CurrentUser
) -> FormResponse:
    """parse 와 같이 읽고, 이 원의 양식으로 남긴다. 읽지 못하면 행이 생기지 않는다."""
    require_own_center(user, center_id)
    filename = file.filename or ""
    if len(filename) > Form.filename.type.length:
        # 컬럼 길이를 넘기면 커밋에서 DB 오류(500)가 난다.
        # 자르지 않는다 — 교사 모르게 이름이 바뀐다.
        raise _unreadable("파일 이름이 너무 깁니다. 이름을 줄여서 다시 올려주세요.")
    tables = _extract(file)
    if not tables:
        # parse 는 빈 결과를 돌려주지만 저장은 막는다 — 계획안 양식은 표다 (§8 · ADR-020).
        raise _unreadable("양식에서 표를 찾지 못했습니다. 계획안 양식 파일인지 확인해주세요.")

    # 추출이 스트림을 다 읽었으므로 되감아 원본을 그대로 남긴다(ADR-026).
    file.file.seek(0)
    labels = hwp_form.labels(tables)
    form = Form(
        center_id=center_id,
        name=filename,  # 이름 입력을 받기 전까지는 파일명이다 (ADR-020 결정 3)
        filename=filename,
        tables=tables,
        labels=labels,
        label_map=mapping.map_labels(labels),
        content=file.file.read(),
    )
    session.add(form)
    session.commit()
    session.refresh(form)
    return FormResponse.model_validate(form)


@center_router.get("/centers/{center_id}/forms", response_model=FormListResponse)
def list_forms(center_id: int, session: DbSession, user: CurrentUser) -> FormListResponse:
    """최신순. 같은 시각이면 id 로 고정한다 — 새로고침마다 순서가 흔들리면 안 된다."""
    require_own_center(user, center_id)
    query = (
        select(Form)
        .where(Form.center_id == center_id, Form.hidden_at.is_(None))
        .order_by(Form.created_at.desc(), Form.id.desc())
    )
    return FormListResponse(
        items=[FormResponse.model_validate(form) for form in session.scalars(query)]
    )


@center_router.delete("/forms/{form_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_form(form_id: int, session: DbSession, user: CurrentUser) -> None:
    """이 원의 양식을 지운다. 계획안이 걸렸으면 숨기고, 남의 것·감춘 것은 404 다."""
    form = find_own_form(session, user.center_id, form_id)
    if form is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={
                "code": "NOT_FOUND",
                "message": "양식을 찾을 수 없습니다.",
                "fields": ["form_id"],
            },
        )
    session.delete(form)
    try:
        session.commit()
    except IntegrityError as error:
        # 실패한 트랜잭션을 되돌려야 같은 세션에서 숨김을 저장할 수 있다.
        session.rollback()
        # 다른 제약 위반은 숨기지 않고 그대로 올린다 — 원인을 가리지 않는다.
        if getattr(getattr(error.orig, "diag", None), "constraint_name", None) != PLANS_FORM_FK:
            raise
        # 계획안은 양식 번호만 들고 있어 DB FK 가 삭제를 막는다 — 대신 숨긴다(ADR-026).
        form.hidden_at = datetime.now(UTC)
        session.commit()
