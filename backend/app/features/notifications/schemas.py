"""알림함 API 의 요청·응답 모델. 계약은 docs/api-spec.md §2-2 「알림함」 이다."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.features.notifications.models import NotificationKind

# GET 이 한 번에 주는 최대 개수. 읽음으로 보내는 id 는 그 목록에서만 나오니 같은 값으로 막는다.
MAX_ITEMS = 30
# notifications.id 는 INTEGER 라 이 위의 값은 DB 가 「integer out of range」로 500 을 낸다.
NotificationId = Annotated[int, Field(gt=0, le=2_147_483_647)]


class NotificationOut(BaseModel):
    id: int
    kind: NotificationKind
    request_id: int
    class_id: int
    class_name: str
    requester_name: str
    created_at: datetime
    read_at: datetime | None


class NotificationList(BaseModel):
    items: list[NotificationOut]


class NotificationsRead(BaseModel):
    """읽음으로 바꿀 알림 id. body 가 없거나 빈 배열이면 422 — 「전부 읽음」은 두지 않는다."""

    model_config = ConfigDict(extra="forbid")

    ids: list[NotificationId] = Field(min_length=1, max_length=MAX_ITEMS)
