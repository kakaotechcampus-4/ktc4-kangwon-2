"""놀이 프로젝트형 연간계획안 내려받기 (api-spec §9, ADR-048 §5 · §7)."""

# ruff: noqa: F811 — 다른 테스트 파일의 픽스처를 가져와 쓰면 인자 이름이 import 와 겹친다

import io
import zipfile

from fastapi.testclient import TestClient
from lxml import etree
from test_plans_export import _confirmed_plan, mine  # noqa: F401
from test_plans_play_project import _blocked, saved, world  # noqa: F401
from test_play_project_confirm_audit_api import _confirm, _select_all  # noqa: F401
from test_play_project_save_api import KEYS, _put_selection  # noqa: F401

from app.features.centers.models import Center
from app.features.forms import hwp_form
from app.main import app
from app.shared.hwpx import NS

client = TestClient(app)
DRAFT_MESSAGE = "놀이 프로젝트형 연간계획안은 확정한 뒤 내려받을 수 있습니다."
ORDER = ["cand5", "cand3", "cand1", "cand2", "cand4"]  # 후보 순서와 다르게 고른다


def _confirmed(row):
    assert _put_selection(row, {key: ORDER for key in KEYS}, 1).status_code == 200
    assert _confirm(row, 2).status_code == 200


def _get(row, query=""):
    return client.get(f"/api/plans/{row.id}/export/hwp{query}")


def _cells(content: bytes) -> dict[tuple[int, int, int], list[str]]:
    """(표, 줄, 칸) -> 문단 글자들. 칸 밖 글자(제목)는 (표, -1, -1)."""
    section = etree.fromstring(zipfile.ZipFile(io.BytesIO(content)).read("Contents/section0.xml"))
    out = {}
    for t, table in enumerate(section.iterfind(".//hp:tbl", NS)):
        for tc in table.iterfind("hp:tr/hp:tc", NS):
            addr = tc.find("hp:cellAddr", NS)
            out[(t, int(addr.get("rowAddr")), int(addr.get("colAddr")))] = [
                "".join(p.itertext()) for p in tc.iterfind("hp:subList/hp:p", NS)
            ]
    return out


def test_초안은_409(world, saved):
    _, row = saved

    _blocked(_get(row), DRAFT_MESSAGE)


def test_남의_원은_404(world, saved, teacher, db_session):
    _, row = saved
    _confirmed(row)
    other = Center(
        name="다른어린이집",
        director_name="박원장",
        region_sido="강원특별자치도",
        region_sigungu="원주시",
    )
    db_session.add(other)
    db_session.flush()
    teacher.center_id = other.id

    assert _get(row).status_code == 404


def test_확정본_hwpx_는_고른_5개를_고른_순서로_담는다(world, saved):
    _, row = saved
    _confirmed(row)

    response = _get(row)

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/hwp+zip"
    assert f'filename="plan-{row.id}.hwpx"' in response.headers["content-disposition"]
    cells = _cells(response.content)
    labels = ["3~5월\n봄", "6~8월\n여름", "9~11월\n가을", "12~2월\n겨울"]
    for index, (key, label) in enumerate(zip(KEYS, labels, strict=True)):
        table, top = divmod(index, 2)
        top = 1 + top * 5
        assert cells[(table, top, 0)] == label.split("\n")  # 시기 칸 두 줄
        names = [cells[(table, r, 1)] for r in range(top, top + 5)]
        assert names == [[f"{key} 놀이 {n[-1]}"] for n in ORDER]
        assert cells[(table, top, 2)] == ["종이"]
        assert cells[(table, top, 3)] == ["지켜본다"]
        assert cells[(table, top, 4)] == [  # 세 조각 · 영역만 따로 굵게 들어간 줄
            "[자연탐구] 자연과 더불어 살기 - 자연을 탐구하며",
            "[신체운동·건강] 몸 - 움직임",
        ]


def test_파일에_제목이_들어가고_미선택_후보와_출처_마커는_없다(world, saved):
    _, row = saved
    _confirmed(row)

    content = _get(row).content

    zf = zipfile.ZipFile(io.BytesIO(content))
    everything = "".join(zf.read(n).decode("utf-8", "ignore") for n in zf.namelist())
    assert "2026 연간놀이계획안 - 놀이반" in everything
    for n in ("6", "7", "8", "9", "10"):  # 고른 건 1~5 뿐이다
        assert f"m03_m05 놀이 {n}<" not in everything
    for marker in ("CURRICULUM", "nuri2019", "RULE_LLM", "evidence", "generation", "AI"):
        assert marker not in everything


def test_hwp_도_내려준다(world, saved, tmp_path):
    _, row = saved
    _confirmed(row)

    response = _get(row, "?format=hwp")

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/x-hwp"
    path = tmp_path / "play.hwp"
    path.write_bytes(response.content)
    text = " ".join(cell["text"] for table in hwp_form.from_hwp(path) for r in table for cell in r)
    assert "m03_m05 놀이 5" in text and "m03_m05 놀이 6" not in text


def test_잘못된_format_은_422(world, saved):
    _, row = saved
    _confirmed(row)

    assert _get(row, "?format=pdf").status_code == 422


def test_월별_주제형은_그대로_내려간다(db_session, mine):
    plan = _confirmed_plan(mine)

    response = client.get(f"/api/plans/{plan['id']}/export/hwp")

    assert response.status_code == 200
    assert f'filename="plan-{plan["id"]}.hwpx"' in response.headers["content-disposition"]
