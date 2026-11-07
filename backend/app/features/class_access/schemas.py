"""열람 요청 · 요약 API 의 요청·응답 모델. 계약은 docs/api-spec.md §2-2 다."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class ArchiveItem(BaseModel):
    """제목 · 아이 이름 · id 는 일부러 없다 — 열람 권한이 없는 교사에게도 나가는 요약이다."""

    kind: str
    start: date
    end: date
    status: Literal["DRAFT", "CONFIRMED"]


class ArchiveSummary(BaseModel):
    items: list[ArchiveItem]


class AccessRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    class_id: int
    status: Literal["PENDING", "APPROVED", "REJECTED", "REVOKED"]
    created_at: datetime
    updated_at: datetime


class ReceivedRequest(AccessRequestOut):
    class_name: str
    requester_name: str


class ReceivedList(BaseModel):
    items: list[ReceivedRequest]


class AccessRequestPatch(BaseModel):
    """주인이 내리는 결정만 받는다. PENDING 으로 되돌리는 길은 요청하는 쪽의 POST 뿐이다."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["APPROVED", "REJECTED", "REVOKED"]
