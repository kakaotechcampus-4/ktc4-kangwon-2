"""계획안 hwpx 내보내기. 한글이 열 수 있는 모양인지 · 확정본만 나가는지 · 출처가 안 섞이는지 본다.

「한글이 실제로 연다」는 여기서 확인할 수 없다. 양식을 바꾸면 한글에서 한 번 열어본다.
"""

import io
import zipfile

import pytest
from fastapi.testclient import TestClient
from lxml import etree

from app.features.centers.models import Center, Class
from app.features.plans.export import TEMPLATE_DIR
from app.main import app
from app.shared.hwpx import NS, TemplateMismatch, fill_table

client = TestClient(app)

TEMPLATE = (TEMPLATE_DIR / "annual.hwpx").read_bytes()
MONTHS = [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2]


def _rows(march: list[str] | None = None) -> list[list[str]]:
    """12개월치. `march` 를 주면 첫 줄(3월)만 그걸로 바꾼다."""
    rows = [[f"{m}월", f"{m}월 주제", "", ""] for m in MONTHS]
    if march is not None:
        rows[0] = march
    return rows


def _section(content: bytes) -> etree._Element:
    return etree.fromstring(zipfile.ZipFile(io.BytesIO(content)).read("Contents/section0.xml"))


def _cell(section: etree._Element, row: int, col: int) -> etree._Element:
    for tc in section.find(".//hp:tbl", NS).iterfind("hp:tr/hp:tc", NS):
        addr = tc.find("hp:cellAddr", NS)
        if (int(addr.get("rowAddr")), int(addr.get("colAddr"))) == (row, col):
            return tc
    raise AssertionError((row, col))


def _lines(tc: etree._Element) -> list[str]:
    return ["".join(p.itertext()) for p in tc.iterfind("hp:subList/hp:p", NS)]


# ── 파일 모양 ─────────────────────────────────────────────


def test_mimetype_이_맨_앞에_압축_없이_들어간다():
    """이게 틀리면 한글이 안 연다."""
    out = zipfile.ZipFile(io.BytesIO(fill_table(TEMPLATE, "제목줄", 1, _rows())))

    first = out.infolist()[0]
    assert first.filename == "mimetype"
    assert first.compress_type == zipfile.ZIP_STORED
    assert out.read("mimetype") == b"application/hwp+zip"
    # 나머지도 양식과 같은 순서 · 같은 압축 방식이다.
    template = zipfile.ZipFile(io.BytesIO(TEMPLATE)).infolist()
    assert [(i.filename, i.compress_type) for i in out.infolist()] == [
        (i.filename, i.compress_type) for i in template
    ]


def test_제목과_칸이_채워지고_머리행은_그대로다():
    section = _section(fill_table(TEMPLATE, "햇님반 2026학년도 연간 보육계획안", 1, _rows()))

    texts = ["".join(t.itertext()) for t in section.iter(f"{{{NS['hp']}}}t")]
    assert "햇님반 2026학년도 연간 보육계획안" in texts
    assert "제목" not in texts
    assert [_lines(_cell(section, 0, c)) for c in range(4)] == [
        ["월"],
        ["주제"],
        ["소주제"],
        ["안전교육"],
    ]
    assert _lines(_cell(section, 1, 0)) == ["3월"]
    assert _lines(_cell(section, 12, 1)) == ["2월 주제"]


def test_칸_안_줄바꿈은_문단으로_나뉘고_특수문자는_그대로_보인다():
    rows = _rows(["3월", "A & B <C>", "첫째\n둘째", ""])
    section = _section(fill_table(TEMPLATE, "제목줄", 1, rows))

    assert _lines(_cell(section, 1, 1)) == ["A & B <C>"]
    assert _lines(_cell(section, 1, 2)) == ["첫째", "둘째"]
    # 줄 배치 캐시가 남아 있으면 한글이 바뀐 글자를 예전 칸 폭으로 그린다.
    assert _cell(section, 1, 2).find(".//hp:linesegarray", NS) is None


def test_XML_에_못_담는_제어문자는_빼고_탭은_띄어쓰기로_바꾼다():
    rows = _rows(["3월", "가\x00나\t다", "", ""])
    section = _section(fill_table(TEMPLATE, "제목줄", 1, rows))

    assert _lines(_cell(section, 1, 1)) == ["가나 다"]


def test_양식을_저장한_사람_이름이_남지_않는다():
    out = zipfile.ZipFile(io.BytesIO(fill_table(TEMPLATE, "제목줄", 1, _rows())))
    package = etree.fromstring(out.read("Contents/content.hpf"))

    metas = {m.get("name"): m.text for m in package.iterfind(".//opf:meta", NS)}
    assert metas["creator"] is None
    assert metas["lastsaveby"] is None
    assert package.find(".//opf:title", NS).text == "제목줄"


def test_미리보기_글자도_채운_내용으로_바뀐다():
    """양식의 것을 두면 탐색기 미리보기에 빈 표가 보인다."""
    out = zipfile.ZipFile(io.BytesIO(fill_table(TEMPLATE, "제목줄", 1, _rows())))

    preview = out.read("Preview/PrvText.txt").decode("utf-8").splitlines()
    assert preview[0] == "제목줄"
    assert preview[1] == "<월><주제><소주제><안전교육>"
    assert preview[2] == "<3월><3월 주제><><>"


@pytest.mark.parametrize(
    "rows",
    [
        _rows()[:11],
        [row + [""] for row in _rows()],
    ],
    ids=["줄이 모자람", "칸이 많음"],
)
def test_양식_표와_모양이_다르면_만들지_않는다(rows):
    with pytest.raises(TemplateMismatch):
        fill_table(TEMPLATE, "제목줄", 1, rows)


# ── API ───────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _logged_in(teacher):
    return teacher


@pytest.fixture
def mine(db_session, teacher):
    center = Center(
        name="테스트어린이집",
        director_name="김원장",
        region_sido="강원특별자치도",
        region_sigungu="춘천시",
    )
    db_session.add(center)
    db_session.flush()
    klass = Class(
        center_id=center.id,
        name="햇살반",
        school_year=2026,
        age_min=3,
        age_max=3,
        teacher_name="김선생",
    )
    db_session.add(klass)
    db_session.flush()
    teacher.center_id = center.id
    return klass


def _confirmed_plan(klass) -> dict:
    created = client.post("/api/plans/annual", json={"class_id": klass.id, "form_id": None})
    assert created.status_code == 201, created.text
    plan_id = created.json()["id"]
    edited = client.put(
        f"/api/plans/annual/{plan_id}/months/3", json={"theme": "새 친구", "sub_themes": ["인사"]}
    )
    assert edited.status_code == 200, edited.text
    assert client.post(f"/api/plans/annual/{plan_id}/confirm").status_code == 200
    return client.get(f"/api/plans/annual/{plan_id}").json()


def test_확정된_계획안을_hwpx_로_내려준다(db_session, mine):
    plan = _confirmed_plan(mine)

    response = client.get(f"/api/plans/{plan['id']}/export/hwp")

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/hwp+zip"
    assert "filename*=UTF-8''" in response.headers["content-disposition"]
    section = _section(response.content)
    texts = ["".join(t.itertext()) for t in section.iter(f"{{{NS['hp']}}}t")]
    assert "햇살반 2026학년도 연간 보육계획안" in texts
    assert _lines(_cell(section, 1, 0)) == ["3월"]
    assert _lines(_cell(section, 1, 1)) == ["새 친구"]
    assert _lines(_cell(section, 1, 2)) == ["인사"]
    assert _lines(_cell(section, 12, 0)) == ["2월"]


def test_제출_문서에_출처가_섞이지_않는다(db_session, mine):
    plan = _confirmed_plan(mine)

    content = client.get(f"/api/plans/{plan['id']}/export/hwp").content

    # 본문만이 아니라 zip 안의 파일 전부를 본다 — 미리보기 · 문서 정보에 새도 제출 파일이다.
    archive = zipfile.ZipFile(io.BytesIO(content))
    everything = b"".join(archive.read(name) for name in archive.namelist()).decode(
        "utf-8", "replace"
    )
    for month in plan["months"]:
        for evidence in month["evidence"]:
            assert evidence["source_id"] not in everything
        assert month["generation"]["method"] not in everything


def test_DRAFT_는_내보내지_않는다(db_session, mine):
    created = client.post("/api/plans/annual", json={"class_id": mine.id, "form_id": None})

    response = client.get(f"/api/plans/{created.json()['id']}/export/hwp")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "GATE_BLOCKED"


def test_남의_원_계획안은_404(db_session, mine, teacher):
    plan = _confirmed_plan(mine)
    other = Center(
        name="다른어린이집",
        director_name="박원장",
        region_sido="강원특별자치도",
        region_sigungu="원주시",
    )
    db_session.add(other)
    db_session.flush()
    teacher.center_id = other.id

    assert client.get(f"/api/plans/{plan['id']}/export/hwp").status_code == 404
