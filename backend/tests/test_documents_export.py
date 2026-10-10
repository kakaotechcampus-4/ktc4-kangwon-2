"""문서 hwpx 내보내기. 종이 칸에 제대로 들어가는지 · 확정본만 나가는지 · 출처가 안 섞이는지 본다.

「한글이 실제로 연다」는 여기서 확인할 수 없다. 양식을 바꾸면 한글에서 한 번 열어본다.
"""

import io
import zipfile
from datetime import date

import pytest
from fastapi.testclient import TestClient
from lxml import etree

from app.features.centers.models import Center, Child, Class
from app.features.documents.models import Document, DocumentSection, DocumentSource
from app.features.observations.models import Observation
from app.main import app
from app.shared.hwpx import NS

client = TestClient(app)

INTERPRETATION = "개미의 움직임을 오래 지켜보며 작은 생물에 관심을 보였다."
SUPPORT = "돋보기를 바깥놀이 영역에 두고 개미가 다니는 길을 함께 찾아본다."


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
        age_min=4,
        age_max=4,
        teacher_name="김선생",
    )
    db_session.add(klass)
    db_session.flush()
    child = Child(class_id=klass.id, name="이가명", code="도담")
    db_session.add(child)
    db_session.flush()
    teacher.center_id = center.id
    return klass, child


def _observation(session, klass, child, day, domain, fact):
    observation = Observation(
        class_id=klass.id,
        child_id=child.id,
        date=date(2026, 9, day),
        domain=domain,
        context="",
        fact=fact,
    )
    session.add(observation)
    session.flush()
    return observation


def _document(session, klass, child, observations, *, kind="observation", status="CONFIRMED"):
    """근거 사본과 사실 · 해석 · 지원을 갖춘 문서. `observations` 순서가 교사가 고른 순서다."""
    doc = Document(
        kind=kind,
        title="이가명 관찰일지 (9월)",
        class_id=klass.id,
        child_id=child.id,
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 30),
        status=status,
        origin="AI",
        stale=False,
        generation_method="RULE_LLM",
        generation_rule_id="observation-draft",
        generation_rule_version="v1",
        review_note="",
    )
    session.add(doc)
    session.flush()
    for o in observations:
        session.add(
            DocumentSource(
                document_id=doc.id,
                source_kind="observation",
                source_id=o.id,
                class_id=klass.id,
                child_id=child.id,
                date=o.date,
                text=o.fact,
            )
        )
    ids = [o.id for o in observations]
    fact = "\n\n".join(o.fact for o in observations)
    for heading, body in [("사실", fact), ("해석", INTERPRETATION), ("지원", SUPPORT)]:
        session.add(DocumentSection(document_id=doc.id, heading=heading, body=body, source_ids=ids))
    session.flush()
    return doc


def _archive(content: bytes) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(content))


def _table(content: bytes) -> dict[str, list[str]]:
    """첫 번째 열(영역 · 평가) → 두 번째 열의 줄들."""
    section = etree.fromstring(_archive(content).read("Contents/section0.xml"))
    rows: dict[int, dict[int, list[str]]] = {}
    for tc in section.find(".//hp:tbl", NS).iterfind("hp:tr/hp:tc", NS):
        addr = tc.find("hp:cellAddr", NS)
        lines = ["".join(p.itertext()) for p in tc.iterfind("hp:subList/hp:p", NS)]
        rows.setdefault(int(addr.get("rowAddr")), {})[int(addr.get("colAddr"))] = lines
    return {"\n".join(row[0]): row[1] for _, row in sorted(rows.items())}


def test_확정된_관찰일지를_영역_행과_평가_칸에_나눠_담는다(db_session, mine):
    klass, child = mine
    # 교사가 고른 순서와 날짜순이 다르다 — 종이에는 영역 안에서 날짜순으로 나간다.
    late = _observation(db_session, klass, child, 22, "자연탐구", "개미를 3분 동안 바라보았다.")
    early = _observation(db_session, klass, child, 5, "자연탐구", "화단에서 지렁이를 찾았다.")
    talk = _observation(db_session, klass, child, 10, "의사소통", "개미 집 이야기를 했다.")
    doc = _document(db_session, klass, child, [late, early, talk])

    response = client.get(f"/api/documents/{doc.id}/export/hwp")

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/hwp+zip"
    assert f'filename="document-{doc.id}.hwpx"' in response.headers["content-disposition"]
    table = _table(response.content)
    assert table["자연탐구"] == [
        "(9/5) 화단에서 지렁이를 찾았다.",
        "(9/22) 개미를 3분 동안 바라보았다.",
    ]
    assert table["의사소통"] == ["(9/10) 개미 집 이야기를 했다."]
    # 기록이 없는 영역은 빈 칸으로 둔다. 막지 않는다.
    assert table["신체운동·건강"] == [""]
    # 해석과 지원은 머리말 없이 빈 줄 하나를 사이에 두고 한 칸에 들어간다.
    assert table["평가"] == [INTERPRETATION, "", SUPPORT]


def test_영역_행은_누리과정_순서로_고정이다(db_session, mine):
    klass, child = mine
    record = _observation(db_session, klass, child, 5, "예술경험", "물감을 섞었다.")
    doc = _document(db_session, klass, child, [record])

    table = _table(client.get(f"/api/documents/{doc.id}/export/hwp").content)

    assert list(table)[1:] == [
        "신체운동·건강",
        "의사소통",
        "사회관계",
        "예술경험",
        "자연탐구",
        "평가",
    ]


def test_만든_뒤_고친_영역이_종이에_나간다(db_session, mine):
    """영역만 고치면 사실은 그대로라 stale 이 아니다. 고친 영역 행에 들어가야 한다."""
    klass, child = mine
    record = _observation(db_session, klass, child, 5, "자연탐구", "블록으로 탑을 쌓았다.")
    doc = _document(db_session, klass, child, [record])
    record.domain = "신체운동·건강"
    db_session.flush()

    table = _table(client.get(f"/api/documents/{doc.id}/export/hwp").content)

    assert table["신체운동·건강"] == ["(9/5) 블록으로 탑을 쌓았다."]
    assert table["자연탐구"] == [""]


def test_제출_문서에_출처가_섞이지_않는다(db_session, mine):
    klass, child = mine
    record = _observation(db_session, klass, child, 5, "자연탐구", "개미를 바라보았다.")
    doc = _document(db_session, klass, child, [record])

    content = client.get(f"/api/documents/{doc.id}/export/hwp").content

    # 본문만이 아니라 zip 안의 파일 전부를 본다 — 미리보기 · 문서 정보에 새도 제출 파일이다.
    archive = _archive(content)
    everything = b"".join(archive.read(name) for name in archive.namelist()).decode(
        "utf-8", "replace"
    )
    for leaked in ("RULE_LLM", "observation-draft", "source_id"):
        assert leaked not in everything


def test_미리보기와_문서_정보가_이_문서로_바뀐다(db_session, mine):
    klass, child = mine
    record = _observation(db_session, klass, child, 5, "자연탐구", "개미를 바라보았다.")
    doc = _document(db_session, klass, child, [record])

    archive = _archive(client.get(f"/api/documents/{doc.id}/export/hwp").content)

    preview = archive.read("Preview/PrvText.txt").decode("utf-8")
    assert preview.splitlines()[0] == "이가명 관찰일지 (9월)"
    assert "개미를 바라보았다." in preview
    package = etree.fromstring(archive.read("Contents/content.hpf"))
    metas = {m.get("name"): m.text for m in package.iterfind(".//opf:meta", NS)}
    assert metas["creator"] is None
    assert metas["lastsaveby"] is None


def test_DRAFT_는_내보내지_않는다(db_session, mine):
    klass, child = mine
    record = _observation(db_session, klass, child, 5, "자연탐구", "개미를 바라보았다.")
    doc = _document(db_session, klass, child, [record], status="DRAFT")

    response = client.get(f"/api/documents/{doc.id}/export/hwp")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "GATE_BLOCKED"


def test_관찰일지가_아니면_422(db_session, mine):
    klass, child = mine
    record = _observation(db_session, klass, child, 5, "자연탐구", "개미를 바라보았다.")
    doc = _document(db_session, klass, child, [record], kind="assessment")

    response = client.get(f"/api/documents/{doc.id}/export/hwp")

    assert response.status_code == 422
    assert response.json()["error"]["fields"] == ["kind"]


def test_근거_관찰_기록이_사라졌으면_빼고_내보내지_않는다(db_session, mine):
    klass, child = mine
    kept = _observation(db_session, klass, child, 5, "자연탐구", "개미를 바라보았다.")
    gone = _observation(db_session, klass, child, 6, "의사소통", "개미 이야기를 했다.")
    doc = _document(db_session, klass, child, [kept, gone])
    db_session.delete(gone)
    db_session.flush()

    response = client.get(f"/api/documents/{doc.id}/export/hwp")

    assert response.status_code == 409
    assert response.json()["error"]["fields"] == [f"sources.{gone.id}"]


def test_남의_원_문서는_404(db_session, mine, teacher):
    klass, child = mine
    record = _observation(db_session, klass, child, 5, "자연탐구", "개미를 바라보았다.")
    doc = _document(db_session, klass, child, [record])
    other = Center(
        name="다른어린이집",
        director_name="박원장",
        region_sido="강원특별자치도",
        region_sigungu="원주시",
    )
    db_session.add(other)
    db_session.flush()
    teacher.center_id = other.id

    assert client.get(f"/api/documents/{doc.id}/export/hwp").status_code == 404


def test_단건_조회가_관찰_기록의_영역을_같이_준다(db_session, mine):
    klass, child = mine
    record = _observation(db_session, klass, child, 5, "예술경험", "물감을 섞었다.")
    doc = _document(db_session, klass, child, [record], status="DRAFT")

    sources = client.get(f"/api/documents/{doc.id}").json()["sources"]

    assert sources[0]["domain"] == "예술경험"
