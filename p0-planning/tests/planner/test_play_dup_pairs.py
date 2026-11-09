"""놀이 이름 겹침 검사(ADR-077 결정 4)를 사람 눈의 짝 42개에 대 본다.

짝은 PR 2 의 `docs/evaluation/runs/2026-11-09-play-annual/dup-pairs.json` 을 그대로 읽는다.
**라벨(same · diff)은 Claude 가 붙이고 하민이 확인했다(2026-11-09).** 라벨이 바뀌면 이 테스트의 xfail 수가 바뀐다.

검사기가 맞히는 짝은 통과, 못 맞히는 짝(같은 놀이 18개를 놓침 · 다른 놀이 1개를 잘못 잡음)은 strict xfail 이다 —
0.6 선이 그만큼 놓친다는 [실측]을 고정한다. 검사를 고쳐 하나라도 맞히게 되면 XPASS 로 실패해 여기를 고치게 한다.
"""

import json
from pathlib import Path

import pytest

from ssuksak.planning.planner.play_project import similar_play_names

PAIRS = json.loads(
    (
        Path(__file__).resolve().parents[3]
        / "docs/evaluation/runs/2026-11-09-play-annual/dup-pairs.json"
    ).read_text(encoding="utf-8")
)["pairs"]


def _case(pair):
    caught = similar_play_names(pair["a"], pair["b"])
    miss = caught != (pair["label"] == "same")
    marks = [pytest.mark.xfail(strict=True, reason="0.6 글자 유사도의 한계")] if miss else []
    return pytest.param(pair, marks=marks, id=f"{pair['label']}:{pair['a']}|{pair['b']}")


def test_짝_수는_PR2_기록과_같다():
    assert [p["label"] for p in PAIRS].count("same") == 24
    assert [p["label"] for p in PAIRS].count("diff") == 18


@pytest.mark.parametrize("pair", [_case(p) for p in PAIRS])
def test_겹침_검사는_사람_라벨과_같다(pair):
    assert similar_play_names(pair["a"], pair["b"]) == (pair["label"] == "same")
