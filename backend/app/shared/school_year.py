"""학년도 계산. 3월 1일에 바뀌고 다음 해 2월 말까지 같은 값이다 (docs/api-spec.md §2).

반 생성이 이 값을 채우고, 반·계획안·일지가 모두 같은 기준으로 학년도를 읽어야 해서
feature 안이 아니라 여기에 둔다.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")


def school_year_of(moment: datetime) -> int:
    """`moment` 가 속한 학년도. 2026 은 2026-03 ~ 2027-02 다.

    **먼저 KST 로 옮기고 나서 3월 경계를 본다.** 받은 값의 `month` 를 그대로 보면
    UTC 기준 2월 28일 15:00(= KST 3월 1일 00:00)에 만든 반이 전년도로 들어가고,
    `UNIQUE(center_id, name, school_year)` 때문에 같은 반이 두 행으로 갈라진다.

    timezone-aware datetime 만 받는다 — naive 값의 해석은 계약에 정의돼 있지 않다.
    """
    local = moment.astimezone(KST)
    return local.year if local.month >= 3 else local.year - 1
