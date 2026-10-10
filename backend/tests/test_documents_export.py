"""문서 hwpx 내보내기. 종이 칸에 제대로 들어가는지 · 확정본만 나가는지 · 출처가 안 섞이는지 본다.

「한글이 실제로 연다」는 여기서 확인할 수 없다. 양식을 바꾸면 한글에서 한 번 열어본다.
"""

import io
import zipfile
from datetime import date, time

import pytest
from fastapi.testclient import TestClient
from lxml import etree

from app.features.centers.models import Center, Child, Class
from app.features.documents.export import TEMPLATE_DIR
from app.features.documents.models import Document, DocumentSection, DocumentSource
from app.features.observations.models import Observation
from app.features.routines.models import RoutineRecord
from app.main import app
from app.shared.hwpx import NS, TemplateMismatch, fill_grid

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


def test_관찰일지_일일_보육일지가_아니면_422(db_session, mine):
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


def test_근거가_바뀐_문서는_내보내지_않는다(db_session, mine):
    """영역 · 일과 이름 · 시간은 원본에서 읽는다. 근거가 바뀐 채로 나가면 확정한 것과 다르다."""
    klass, child = mine
    record = _observation(db_session, klass, child, 5, "자연탐구", "개미를 바라보았다.")
    doc = _document(db_session, klass, child, [record])
    doc.stale = True
    db_session.flush()

    response = client.get(f"/api/documents/{doc.id}/export/hwp")

    assert response.status_code == 409
    assert response.json()["error"]["fields"] == ["stale"]


# ── 일일 보육일지 ──────────────────────────────────────────


def _routine(session, klass, *, position, start, end, name, plan="", execution):
    record = RoutineRecord(
        class_id=klass.id,
        date=date(2026, 9, 22),
        position=position,
        start_time=start,
        end_time=end,
        name=name,
        plan=plan,
        execution=execution,
    )
    session.add(record)
    session.flush()
    return record


def _daily_log(session, klass, routines, *, status="CONFIRMED"):
    """`routines` 순서가 교사가 고른 순서다. 종이의 행 순서와 다를 수 있다."""
    doc = Document(
        kind="dailyLog",
        title="햇살반 일일 보육일지 (9/22)",
        class_id=klass.id,
        child_id=None,
        start_date=date(2026, 9, 22),
        end_date=date(2026, 9, 22),
        status=status,
        origin="AI",
        stale=False,
        generation_method="RULE_LLM",
        generation_rule_id="dailyLog-draft",
        generation_rule_version="v1",
        review_note="",
    )
    session.add(doc)
    session.flush()
    for r in routines:
        session.add(
            DocumentSource(
                document_id=doc.id,
                source_kind="routine",
                source_id=r.id,
                class_id=klass.id,
                child_id=None,
                date=r.date,
                text=r.fact_text(),
            )
        )
    ids = [r.id for r in routines]
    fact = "\n\n".join(r.fact_text() for r in routines)
    for heading, body in [("사실", fact), ("해석", INTERPRETATION), ("지원", SUPPORT)]:
        session.add(DocumentSection(document_id=doc.id, heading=heading, body=body, source_ids=ids))
    session.flush()
    return doc


def _grid(content: bytes) -> tuple[etree._Element, list[list[str]]]:
    """표와, 줄마다 칸 글자(칸 안 줄바꿈은 `\\n`). 순서는 한글이 적어둔 (행, 열) 주소다."""
    table = etree.fromstring(_archive(content).read("Contents/section0.xml")).find(".//hp:tbl", NS)
    rows: dict[int, dict[int, str]] = {}
    for tc in table.iterfind("hp:tr/hp:tc", NS):
        addr = tc.find("hp:cellAddr", NS)
        text = "\n".join("".join(p.itertext()) for p in tc.iterfind("hp:subList/hp:p", NS))
        rows.setdefault(int(addr.get("rowAddr")), {})[int(addr.get("colAddr"))] = text
    return table, [[row[c] for c in sorted(row)] for _, row in sorted(rows.items())]


def test_일과마다_한_줄씩_늘려_담고_꼬리_칸에_평가를_넣는다(db_session, mine):
    klass, _ = mine
    outdoor = _routine(
        db_session,
        klass,
        position=1,
        start=time(11, 0),
        end=time(11, 40),
        name="바깥놀이",
        execution="산책길에서 낙엽을 모았다.",
    )
    arrival = _routine(
        db_session,
        klass,
        position=0,
        start=time(7, 30),
        end=time(9, 0),
        name="등원",
        plan="웃으며 맞이하기",
        execution="교사와 인사하고 가방을 정리했다.",
    )
    special = _routine(
        db_session,
        klass,
        position=1,
        start=None,
        end=None,
        name="특별활동",
        execution="음악 수업에 참여했다.",
    )
    # 교사가 고른 순서가 종이 순서와 다르다 — 종이에는 일과 기록 화면 순서로 나간다.
    doc = _daily_log(db_session, klass, [special, outdoor, arrival])

    response = client.get(f"/api/documents/{doc.id}/export/hwp")

    assert response.status_code == 200, response.text
    table, rows = _grid(response.content)
    assert rows[0] == ["시간", "일과", "활동계획", "활동실행"]
    assert rows[1:4] == [
        ["07:30~09:00", "등원", "웃으며 맞이하기", "교사와 인사하고 가방을 정리했다."],
        ["11:00~11:40", "바깥놀이", "", "산책길에서 낙엽을 모았다."],
        # 시간이 없는 일과는 같은 순서 안에서 뒤로 간다.
        ["", "특별활동", "", "음악 수업에 참여했다."],
    ]
    assert rows[4] == ["놀이 평가 및 다음날 지원계획", f"{INTERPRETATION}\n\n{SUPPORT}"]
    # 줄을 끼워 넣은 만큼 표의 줄 수도 늘어야 한글이 연다.
    assert table.get("rowCnt") == "5"
    assert len(table.findall("hp:tr", NS)) == 5


def test_일과가_하나면_원형_줄만_채운다(db_session, mine):
    klass, _ = mine
    only = _routine(
        db_session,
        klass,
        position=0,
        start=time(9, 0),
        end=time(10, 0),
        name="실내놀이",
        execution="블록으로 다리를 만들었다.",
    )
    doc = _daily_log(db_session, klass, [only])

    table, rows = _grid(client.get(f"/api/documents/{doc.id}/export/hwp").content)

    assert table.get("rowCnt") == "3"
    assert rows[1] == ["09:00~10:00", "실내놀이", "", "블록으로 다리를 만들었다."]


def test_일일_보육일지도_근거_기록이_사라졌으면_내보내지_않는다(db_session, mine):
    klass, _ = mine
    kept = _routine(
        db_session, klass, position=0, start=None, end=None, name="등원", execution="인사했다."
    )
    gone = _routine(
        db_session, klass, position=1, start=None, end=None, name="간식", execution="먹었다."
    )
    doc = _daily_log(db_session, klass, [kept, gone])
    db_session.delete(gone)
    db_session.flush()

    response = client.get(f"/api/documents/{doc.id}/export/hwp")

    assert response.status_code == 409
    assert response.json()["error"]["fields"] == [f"sources.{gone.id}"]


def test_양식_표_줄_수가_머리_원형_꼬리와_다르면_만들지_않는다():
    """관찰일지 양식(7줄)은 머리 1 · 원형 1 · 꼬리 1 모양이 아니다."""
    with pytest.raises(TemplateMismatch):
        fill_grid(
            (TEMPLATE_DIR / "observation.hwpx").read_bytes(),
            "제목줄",
            1,
            [["a", "b"]],
            [["평가", "c"]],
        )
