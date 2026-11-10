"""일과 임시본 정리 — 근거로 올라간 뒤 30일 지난 임시본만 지운다 (ADR-084).

올라가지 않은 임시본은 지우지 않는다. 교사가 쓴 글이 거기에만 있다.
하루 한 번 돌리면 된다. cron 연결은 서버에서 따로 한다(docs/deploy.md 에 적을 것).

    docker compose exec backend python scripts/prune_routine_drafts.py           # 셈만
    docker compose exec backend python scripts/prune_routine_drafts.py --apply   # 지움
"""

import datetime
import sys

from app.db import SessionLocal
from app.features.routines.drafts import prune_drafts


def main() -> None:
    apply = "--apply" in sys.argv[1:]
    with SessionLocal() as session:
        count = prune_drafts(session, datetime.datetime.now(datetime.UTC))
        print(f"올라간 뒤 30일 지난 임시본: {count}건")
        if apply:
            session.commit()
            print("지웠습니다.")
        else:
            session.rollback()
            print("지우지 않았습니다. 지우려면 --apply")


if __name__ == "__main__":
    main()
