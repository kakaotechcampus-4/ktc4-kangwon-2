"""DB 의 원 열쇠를 지금 정부 어린이집 목록 사본에 맞춘다 (ADR-068 · #415 · #416).

열쇠는 「시도|시군구|이름|주소」 글자 그대로라, 목록을 다시 받을 때 이름이나 주소 표기가 바뀌면
DB 에 저장된 열쇠가 새 사본에 없다. 그 뒤 들어오는 교사는 같은 어린이집을 골라도 **새 원**을 만든다.
#415 전에 가입한 교사의 원은 열쇠가 아예 없어, 같은 어린이집 교사가 그 원으로 들어올 길이 없다.

두 가지를 맞춘다. **원 이름 · 원장 · 지역은 건드리지 않는다**(ADR-068 §4) — 열쇠 칸만 쓴다.

1. 열쇠가 사본에 없는 원 — 같은 시도 · 시군구에서 이름이 같거나 주소가 같은 곳이
   **하나뿐**이면 그 열쇠로 옮긴다.
2. 열쇠 없는 옛 원 — 같은 시도 · 시군구에서 이름이 같은 곳이 **하나뿐**이면
   그 열쇠를 채운다.

옮길 열쇠를 이미 다른 원이 쓰면(두 원을 합쳐야 한다) 옮기지 않고 적기만 한다.
후보가 없거나 여럿이어도 같다.
기본은 보기만 한다. 사본을 새로 받은 배포 뒤 서버에서 돌린다:

    docker compose exec -T backend python - < backend/scripts/registry_keys.py            # 보기만
    docker compose exec -T backend python - --apply < backend/scripts/registry_keys.py    # 쓴다
"""

import sys
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.features.centers import registry
from app.features.centers.models import Center
from app.features.centers.registry import Daycare


@dataclass(frozen=True)
class Row:
    id: int
    registry_key: str | None
    name: str
    sido: str
    sigungu: str


def _plain(text: str) -> str:
    return "".join(text.split())


def plan(rows: list[Row], daycares: dict[str, Daycare]) -> tuple[dict[int, str], list[str]]:
    """(원 id -> 새 열쇠, 사람이 볼 메모). DB 를 읽지도 쓰지도 않는다."""
    by_name: dict[tuple[str, str, str], list[Daycare]] = defaultdict(list)
    by_address: dict[tuple[str, str, str], list[Daycare]] = defaultdict(list)
    for d in daycares.values():
        by_name[(d.sido, d.sigungu, _plain(d.name))].append(d)
        by_address[(d.sido, d.sigungu, _plain(d.address))].append(d)

    taken = {row.registry_key for row in rows if row.registry_key}
    wanted: dict[str, list[Row]] = defaultdict(list)
    notes: list[str] = []
    for row in rows:
        if row.registry_key in daycares:
            continue
        if row.registry_key:
            sido, sigungu, name, address = (row.registry_key.split("|") + ["", "", "", ""])[:4]
            found = {
                d.key: d
                for d in by_name[(sido, sigungu, _plain(name))]
                + by_address[(sido, sigungu, _plain(address))]
            }
            what = f"원 {row.id} 의 열쇠가 사본에 없다 ({row.registry_key})"
        else:
            found = {d.key: d for d in by_name[(row.sido, row.sigungu, _plain(row.name))]}
            if not found:
                continue  # 「목록에 없어요」로 직접 적은 원이다 — 맞출 곳이 없다
            what = f"원 {row.id}({row.name}) 에 열쇠가 없다"
        if len(found) != 1:
            notes.append(f"{what} — 후보 {len(found)}곳이라 손으로 고른다")
            continue
        key = next(iter(found))
        if key in taken:
            notes.append(f"{what} — {key} 를 이미 다른 원이 쓴다. 두 원을 합쳐야 한다")
            continue
        wanted[key].append(row)

    moves: dict[int, str] = {}
    for key, claimants in wanted.items():
        if len(claimants) > 1:
            ids = ", ".join(str(row.id) for row in claimants)
            notes.append(f"원 {ids} 가 모두 {key} 로 가려 한다 — 두 원을 합쳐야 한다")
            continue
        moves[claimants[0].id] = key
    return moves, notes


def run(session: Session, *, apply: bool) -> tuple[dict[int, str], list[str]]:
    rows = [
        Row(*r)
        for r in session.execute(
            select(
                Center.id,
                Center.registry_key,
                Center.name,
                Center.region_sido,
                Center.region_sigungu,
            ).order_by(Center.id)
        )
    ]
    moves, notes = plan(rows, registry._all())
    if apply:
        for center_id, key in moves.items():
            session.execute(update(Center).where(Center.id == center_id).values(registry_key=key))
        session.commit()
    return moves, notes


def main() -> None:
    from app.db import engine

    apply = "--apply" in sys.argv
    with Session(engine) as session:
        moves, notes = run(session, apply=apply)
    for center_id, key in moves.items():
        print(f"{'옮김' if apply else '옮길 것'}: 원 {center_id} -> {key}")
    for note in notes:
        print(f"손으로: {note}")
    print(
        f"{len(moves)}곳 {'옮겼다' if apply else '옮길 수 있다 (--apply 로 쓴다)'}, "
        f"손으로 {len(notes)}건"
    )


if __name__ == "__main__":
    main()
