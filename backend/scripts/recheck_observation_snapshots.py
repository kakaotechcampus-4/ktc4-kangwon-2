"""되감았다가 다시 올라온 뒤 한 번 돌린다 — 관찰 근거 사본과 원본을 다시 대조한다 (ADR-088 결과).

옛 코드는 관찰 기록의 사실 · 날짜만 사본과 비교한다. 되감은 동안 교사가 영역 · 상황만 고치면
옛 코드는 `stale` 을 붙이지 않는다. 다시 올라와도 사본(`document_sources.domain` · `context`)은
그대로라, 바뀐 기록을 쓴 문서가 `stale=false` 로 남는다.

새 코드가 고칠 때 쓰는 비교(`stale.observation_changed`)를 사본이 있는 관찰 기록마다 다시 돌린다.
다른 문서를 근거로 쓴 문서까지 따라가 `stale` 로 바꾼다. 다시 돌려도 된다 — `stale` 이면 그대로다.

    docker compose exec backend python scripts/recheck_observation_snapshots.py           # 셈만
    docker compose exec backend python scripts/recheck_observation_snapshots.py --apply   # 저장
"""

import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.features.documents.models import Document, DocumentSource
from app.features.documents.stale import observation_changed
from app.features.observations.models import Observation


def _fresh(session: Session) -> set[int]:
    return set(session.scalars(select(Document.id).where(Document.stale.is_(False))))


def recheck(session: Session) -> list[int]:
    """새로 `stale` 이 된 문서 id. 커밋은 부르는 쪽이 한다."""
    before = _fresh(session)
    # 사본이 없는(NULL) 옛 행은 종이가 원본을 따른다 — 옛 코드의 비교로 충분해 보지 않는다.
    observation_ids = session.scalars(
        select(DocumentSource.source_id)
        .where(DocumentSource.source_kind == "observation", DocumentSource.domain.is_not(None))
        .distinct()
    )
    for observation_id in observation_ids.all():
        observation_changed(session, observation_id, session.get(Observation, observation_id))
    session.flush()
    return sorted(before - _fresh(session))


def main() -> None:
    apply = "--apply" in sys.argv[1:]
    with SessionLocal() as session:
        ids = recheck(session)
        # 글은 찍지 않는다(ADR-004). 문서 번호만.
        print(f"새로 stale: {len(ids)}건 {ids}")
        if apply:
            session.commit()
            print("저장했습니다.")
        else:
            session.rollback()
            print("저장하지 않았습니다. 저장하려면 --apply")


if __name__ == "__main__":
    main()
