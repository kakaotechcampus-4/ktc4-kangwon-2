"""등록 양식 모델. 계약은 docs/api-spec.md §8, 결정은 ADR-020 이다."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Form(Base):
    """원이 등록한 양식의 파싱 결과. 원의 자산이라 만료가 없다.

    **원본 파일은 남기지 않는다**(ADR-020). 수정이 없어 `updated_at` 도 없다 — 삭제 후 재등록이다.
    `tables` · `labels` · `label_map` 은 `ParseResponse` 를 그대로 담는다(schemas.py).
    """

    __tablename__ = "forms"

    id: Mapped[int] = mapped_column(primary_key=True)
    center_id: Mapped[int] = mapped_column(ForeignKey("centers.id"), index=True)
    name: Mapped[str] = mapped_column(
        String(255), comment="화면에 보일 이름. 지금은 filename 과 같다 (ADR-020 결정 3)"
    )
    filename: Mapped[str] = mapped_column(String(255))
    tables: Mapped[list] = mapped_column(JSONB, comment="표 → 행 → 셀 {text, rowspan, colspan}")
    labels: Mapped[list] = mapped_column(JSONB)
    label_map: Mapped[dict] = mapped_column(JSONB, comment="라벨 → 표준 키 또는 null (ADR-009)")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
