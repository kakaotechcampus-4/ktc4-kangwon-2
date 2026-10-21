"""주간계획안 hwpx 양식을 만든다.

월간 양식(`build_monthly_template.py`)과 같은 길이다 — 한글이 저장한 `annual.hwpx` 의 칸을
복제해서 행·열 수와 글자만 바꾼다. 표를 손으로 그리지 않는다.

    docker compose exec backend python scripts/build_weekly_template.py

모양 — 화면은 카드형이지만 제출 문서는 기관 표 양식을 따른다(2026-10-21 하민 결정).
  머리     반 · 기간 · 「구분 | 내용」
  본문     「칸 이름 | 내용」 한 줄. 내보낼 때 계획안의 Section 수만큼 복제한다(`hwpx.fill_grid`).
           칸 이름은 양식이 아니라 계획안이 들고 온다 — 주간 Template 이 바뀌어도 양식은 그대로다.
  뺀 것    묶음 줄(이번 주 방향 · 놀이와 활동 …). `fill_grid` 는 원형 한 줄만 복제한다.
           ponytail: 묶음 줄이 필요해지면 `fill_grid` 에 두 번째 원형(띠 줄)을 더한다.
"""

from __future__ import annotations

import pathlib

from build_monthly_template import BLANK_2, CENTER, EMPTY, LEFT, ROOT, Cell, build

TARGET = ROOT / "app/features/plans/templates/weekly.hwpx"

#: 합이 글이 들어가는 폭(41952)과 같아야 한다. 첫 칸은 칸 이름(일곱 글자까지 한 줄 — 월간과 같음).
COLUMNS = [8992, 32960]

#: 머리 3줄 · 본문 원형 1줄. 꼬리 없음.
LAYOUT: list[list[Cell]] = [
    [("반", 1, "head", "label", CENTER), (EMPTY, 1, None, "value", LEFT)],
    [("기간", 1, "head", "label", CENTER), (EMPTY, 1, None, "value", LEFT)],
    [("구분", 1, "head", "label", CENTER), ("내용", 1, "head", "label", CENTER)],
    # 내용 칸은 두 줄을 비워 둔다 — 빈 양식에서도 쓸 자리가 보이게.
    # 글자가 들어가면 한글이 칸 높이를 다시 잡는다.
    [(EMPTY, 1, "head", "label", CENTER), (BLANK_2, 1, None, "value", LEFT)],
]


def main() -> None:
    chars = build(pathlib.Path(TARGET), LAYOUT, COLUMNS)
    print(f"{TARGET} — {len(LAYOUT)}행 × {len(COLUMNS)}열, 글자 모양 {len(chars)}")


if __name__ == "__main__":
    main()
