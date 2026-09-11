import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile

from app.features.forms import hwp_form, mapping
from app.features.forms.schemas import ParseResponse

router = APIRouter(prefix="/forms", tags=["forms"])

_ALLOWED_SUFFIXES = {".hwp", ".hwpx"}


@router.post("/parse", response_model=ParseResponse)
def parse_form(file: UploadFile) -> ParseResponse:
    """hwp/hwpx 양식 파일을 받아 표 구조와 라벨 후보를 반환한다.

    DB 를 쓰지 않는다 — 요청·응답만으로 끝나는 순수 변환 엔드포인트.
    """
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in _ALLOWED_SUFFIXES:
        shown = suffix or "(확장자 없음)"
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 파일 형식입니다: {shown} (.hwp, .hwpx만 허용)",
        )

    # hwp_form.extract() 가 경로를 요구하므로 업로드 내용을 임시 파일에 쓴다.
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir) / (file.filename or f"upload{suffix}")
        tmp_path.write_bytes(file.file.read())

        try:
            tables = hwp_form.extract(tmp_path)
        except RuntimeError as e:
            # 서버에 hwp5html 이 설치돼 있지 않은 경우 등 환경 문제
            raise HTTPException(status_code=500, detail=str(e)) from e
        except Exception as e:
            # 손상된 파일, 변환 실패 등 요청 자체의 문제
            raise HTTPException(status_code=422, detail=f"양식 파싱에 실패했습니다: {e}") from e

    labels = hwp_form.labels(tables)
    return ParseResponse(
        filename=file.filename or "",
        tables=tables,
        labels=labels,
        label_map=mapping.map_labels(labels),
    )
