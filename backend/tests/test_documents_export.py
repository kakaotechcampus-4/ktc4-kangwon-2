"""문서 hwpx 내보내기. 종이 칸에 제대로 들어가는지 · 확정본만 나가는지 · 출처가 안 섞이는지 본다.

「한글이 실제로 연다」는 여기서 확인할 수 없다. 양식을 바꾸면 한글에서 한 번 열어본다.
`?format=hwp` 로 바꾼 `.hwp` 도 마찬가지다 — 여기서는 pyhwp 로 다시 읽히는지까지만 본다.
변환 실패 · 형식 검사는 두 내보내기가 같은 `download()` 를 써서 test_plans_export 에서 본다.
"""

import io
import re
import zipfile
from datetime import date, time

import olefile
import pytest
from fastapi.testclient import TestClient
from hwpx.hwp5.summary import AUTHOR, LAST_AUTHOR, read_summary
from lxml import etree
from sqlalchemy import select

from app.features.centers.models import Center, Child, Class
from app.features.documents import export as document_export
from app.features.documents.export import TEMPLATE_DIR
from app.features.documents.models import Document, DocumentSection, DocumentSource
from app.features.forms import hwp_form
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
    # 해석과 지원은 문서마다 다른 머리말을 달고 빈 줄 하나를 사이에 두고 한 칸에 들어간다.
    assert table["평가"] == [f"▸ 배움) {INTERPRETATION}", "", f"▸ 지원) {SUPPORT}"]


def test_2축_원은_두_줄짜리_양식으로_나간다(db_session, mine):
    """교사 문서 3건 중 2건이 2축이었다 (관찰일지-서술-기준.md).

    5영역 양식 하나로는 `fill_table` 이 줄 수가 안 맞아 거절한다 — 축마다 양식이 다르다.
    """
    klass, child = mine
    db_session.get(Center, klass.center_id).observation_axis = "DAILY_PLAY_2"
    db_session.flush()
    play = _observation(db_session, klass, child, 5, "놀이활동", "블록으로 길을 만들었다.")
    doc = _document(db_session, klass, child, [play])

    response = client.get(f"/api/documents/{doc.id}/export/hwp")

    assert response.status_code == 200, response.text
    table = _table(response.content)
    assert list(table) == ["영역", "일상생활", "놀이활동", "평가"]
    assert table["놀이활동"] == ["(9/5) 블록으로 길을 만들었다."]
    assert table["일상생활"] == [""]
    assert table["평가"] == [f"▸ 배움) {INTERPRETATION}", "", f"▸ 지원) {SUPPORT}"]


def test_축을_바꾼_뒤_옛_축_기록을_내보내면_이유를_말한다(db_session, mine):
    """조용히 버리면 교사가 고른 근거가 종이에서 사라진다."""
    klass, child = mine
    old = _observation(db_session, klass, child, 5, "자연탐구", "지렁이를 찾았다.")
    doc = _document(db_session, klass, child, [old])
    db_session.get(Center, klass.center_id).observation_axis = "DAILY_PLAY_2"
    db_session.flush()

    response = client.get(f"/api/documents/{doc.id}/export/hwp")

    assert response.status_code == 422
    body = response.json()["error"]
    assert body["code"] == "VALIDATION_FAILED"
    assert "자연탐구" in body["message"]
    assert body["fields"] == [f"sources.{old.id}"]


def _hwp_rows(content: bytes, tmp_path) -> list[list[str]]:
    """`.hwp` 를 양식 등록이 쓰는 pyhwp(hwp5html)로 다시 읽은 표의 칸 글자."""
    path = tmp_path / "export.hwp"
    path.write_bytes(content)
    [table] = hwp_form.from_hwp(path)
    return [[cell["text"] for cell in row] for row in table]


def _as_read(text: str) -> str:
    # pyhwp 로 읽으면 칸 안 줄바꿈 · 연속 공백이 한 칸이 된다(hwp_form._clean).
    return re.sub(r"\s+", " ", text).strip()


def test_관찰일지를_hwp_로_바꿔_내려준다(db_session, mine, tmp_path):
    klass, child = mine
    late = _observation(db_session, klass, child, 22, "자연탐구", "개미를 3분 동안 바라보았다.")
    early = _observation(db_session, klass, child, 5, "자연탐구", "화단에서 지렁이를 찾았다.")
    doc = _document(db_session, klass, child, [late, early])

    response = client.get(f"/api/documents/{doc.id}/export/hwp?format=hwp")

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/x-hwp"
    assert f'filename="document-{doc.id}.hwp"' in response.headers["content-disposition"]
    expected = [
        ["영역", "관찰내용"],
        ["신체운동·건강", ""],
        ["의사소통", ""],
        ["사회관계", ""],
        ["예술경험", ""],
        ["자연탐구", "(9/5) 화단에서 지렁이를 찾았다.\n(9/22) 개미를 3분 동안 바라보았다."],
        ["평가", f"▸ 배움) {INTERPRETATION}\n\n▸ 지원) {SUPPORT}"],
    ]
    assert _hwp_rows(response.content, tmp_path) == [
        [_as_read(text) for text in row] for row in expected
    ]


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


def _named_copy(name: str, directory) -> None:
    """양식을 저장한 사람의 이름이 남은 양식 사본. 지금 양식은 비어 있어 지우는지 볼 수 없다."""
    with (
        zipfile.ZipFile(TEMPLATE_DIR / name) as src,
        zipfile.ZipFile(directory / name, "w") as dst,
    ):
        for info in src.infolist():
            data = src.read(info.filename)
            if info.filename == "Contents/content.hpf":
                package = etree.fromstring(data)
                for meta in package.iterfind(".//opf:meta", NS):
                    if meta.get("name") in ("creator", "lastsaveby"):
                        meta.text = "박가명"
                data = etree.tostring(package, xml_declaration=True, encoding="UTF-8")
            dst.writestr(info, data, compress_type=info.compress_type)


def test_hwp_도_미리보기가_이_문서로_바뀌고_작성자가_지워진다(
    db_session, mine, monkeypatch, tmp_path
):
    """변환기가 hwpx 의 미리보기 · 문서 정보를 옮긴다. 변환기를 올려도 그래야 한다(ADR-004)."""
    klass, child = mine
    record = _observation(db_session, klass, child, 5, "자연탐구", "개미를 바라보았다.")
    doc = _document(db_session, klass, child, [record])
    _named_copy("observation.hwpx", tmp_path)
    monkeypatch.setattr(document_export, "TEMPLATE_DIR", tmp_path)

    ole = olefile.OleFileIO(client.get(f"/api/documents/{doc.id}/export/hwp?format=hwp").content)

    preview = ole.openstream("PrvText").read().decode("utf-16-le")
    assert preview.splitlines()[0] == "이가명 관찰일지 (9월)"
    assert "개미를 바라보았다." in preview
    summary = read_summary(ole.openstream("\x05HwpSummaryInformation").read())
    assert summary.get(AUTHOR, "") == ""
    assert summary.get(LAST_AUTHOR, "") == ""


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
    assert rows[4:] == [
        [
            "놀이 평가 및 다음날 지원계획",
            f"▸ 놀이 평가) {INTERPRETATION}\n\n▸ 다음날 지원계획) {SUPPORT}",
        ],
        ["반 운영 특이사항", ""],
    ]
    # 줄을 끼워 넣은 만큼 표의 줄 수도 늘어야 한글이 연다.
    assert table.get("rowCnt") == "6"
    assert len(table.findall("hp:tr", NS)) == 6


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

    assert table.get("rowCnt") == "4"
    assert rows[1] == ["09:00~10:00", "실내놀이", "", "블록으로 다리를 만들었다."]


def test_줄을_늘린_일일_보육일지도_hwp_로_바꿔_내려준다(db_session, mine, tmp_path):
    """일과 줄은 양식의 원형 한 줄을 복제한다(fill_grid). 늘린 표가 hwp 에서도 그대로여야 한다."""
    klass, _ = mine
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
    outdoor = _routine(
        db_session,
        klass,
        position=1,
        start=time(11, 0),
        end=time(11, 40),
        name="바깥놀이",
        plan="낙엽 모으기\n낙엽 세기",
        execution="산책길에서 낙엽을 모았다.",
    )
    lunch = _routine(
        db_session,
        klass,
        position=2,
        start=time(11, 40),
        end=time(12, 30),
        name="점심",
        execution="스스로 수저를 챙겼다.",
    )
    doc = _daily_log(db_session, klass, [arrival, outdoor, lunch])

    response = client.get(f"/api/documents/{doc.id}/export/hwp?format=hwp")

    assert response.status_code == 200, response.text
    expected = [
        ["시간", "일과", "활동계획", "활동실행"],
        ["07:30~09:00", "등원", "웃으며 맞이하기", "교사와 인사하고 가방을 정리했다."],
        ["11:00~11:40", "바깥놀이", "낙엽 모으기\n낙엽 세기", "산책길에서 낙엽을 모았다."],
        ["11:40~12:30", "점심", "", "스스로 수저를 챙겼다."],
        [
            "놀이 평가 및 다음날 지원계획",
            f"▸ 놀이 평가) {INTERPRETATION}\n\n▸ 다음날 지원계획) {SUPPORT}",
        ],
        ["반 운영 특이사항", ""],
    ]
    assert _hwp_rows(response.content, tmp_path) == [
        [_as_read(text) for text in row] for row in expected
    ]


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


def _weekly_log(session, klass, days, *, status="CONFIRMED"):
    """확정한 일일 보육일지들을 근거로 둔 주간 보육일지.

    `days` 는 (날짜, 일과 이름, 활동실행, 반 운영 특이사항) 이다. 주간은 일일 문서를 근거로
    삼으므로 일일 문서도 같이 만든다.
    """
    sources = []
    for day, name, execution, class_note in days:
        routine = RoutineRecord(
            class_id=klass.id,
            date=day,
            position=0,
            start_time=None,
            end_time=None,
            name=name,
            plan="",
            execution=execution,
        )
        session.add(routine)
        session.flush()
        daily = _daily_log(session, klass, [routine])
        daily.start_date = daily.end_date = day
        daily.class_note = class_note
        session.flush()
        sources.append((daily, day))

    doc = Document(
        kind="weeklyLog",
        title="햇살반 주간 보육일지 (9/21~9/25)",
        class_id=klass.id,
        child_id=None,
        start_date=date(2026, 9, 21),
        end_date=date(2026, 9, 25),
        status=status,
        origin="AI",
        stale=False,
        generation_method="RULE_LLM",
        generation_rule_id="weeklyLog-draft",
        generation_rule_version="v1",
        review_note="",
    )
    session.add(doc)
    session.flush()
    for daily, day in sources:
        fact = session.scalar(
            select(DocumentSection.body).where(
                DocumentSection.document_id == daily.id, DocumentSection.heading == "사실"
            )
        )
        session.add(
            DocumentSource(
                document_id=doc.id,
                source_kind="document",
                source_id=daily.id,
                class_id=klass.id,
                child_id=None,
                date=day,
                text=fact,
                source_status="CONFIRMED",
            )
        )
    fact = "\n\n".join(f"[{name}] {execution}" for _, name, execution, _ in days)
    for heading, body in [("사실", fact), ("해석", INTERPRETATION), ("지원", SUPPORT)]:
        session.add(DocumentSection(document_id=doc.id, heading=heading, body=body, source_ids=[]))
    session.flush()
    return doc


def test_주간_보육일지는_날짜마다_한_줄씩_담고_꼬리에_주간_총평을_넣는다(db_session, mine):
    klass, _ = mine
    # 교사가 고른 순서가 날짜순이 아니어도 종이는 날짜순이다.
    doc = _weekly_log(
        db_session,
        klass,
        [
            (date(2026, 9, 23), "실내놀이", "낙엽으로 왕관을 만들었다.", ""),
            (date(2026, 9, 21), "쌓기놀이", "블록으로 성을 쌓았다.", "-결석 : 이가명"),
        ],
    )

    response = client.get(f"/api/documents/{doc.id}/export/hwp")

    assert response.status_code == 200
    _, rows = _grid(response.content)
    assert rows == [
        ["날짜", "우리반 놀이", "놀이 이해 및 분석", "앞으로의 지원방향", "반 운영 특이사항"],
        ["9/21(월)", "쌓기놀이", INTERPRETATION, SUPPORT, "-결석 : 이가명"],
        ["9/23(수)", "실내놀이", INTERPRETATION, SUPPORT, ""],
        [
            "주간 총평",
            f"▸ 놀이 평가) {INTERPRETATION}\n\n▸ 다음 주 지원계획) {SUPPORT}",
        ],
    ]


def test_주간_보육일지도_확정본만_내보낸다(db_session, mine):
    klass, _ = mine
    doc = _weekly_log(
        db_session,
        klass,
        [(date(2026, 9, 21), "쌓기놀이", "블록으로 성을 쌓았다.", "")],
        status="DRAFT",
    )

    response = client.get(f"/api/documents/{doc.id}/export/hwp")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "GATE_BLOCKED"


def test_일일_보육일지_꼬리에_반_운영_특이사항_줄이_있다(db_session, mine):
    klass, _ = mine
    routine = _routine(
        db_session,
        klass,
        position=0,
        start=time(9, 20),
        end=time(10, 40),
        name="오전 실내놀이",
        execution="블록으로 성을 쌓았다.",
    )
    doc = _daily_log(db_session, klass, [routine])
    doc.class_note = "-결석 : 이가명\n-부모 개별면담 진행"
    db_session.flush()

    response = client.get(f"/api/documents/{doc.id}/export/hwp")

    assert response.status_code == 200
    _, rows = _grid(response.content)
    assert rows[-1] == ["반 운영 특이사항", "-결석 : 이가명\n-부모 개별면담 진행"]
    # 교사가 안 적어도 칸은 남는다 — 종이에서 칸이 사라지면 손으로 그려 넣어야 한다.
    doc.class_note = ""
    db_session.flush()
    _, rows = _grid(client.get(f"/api/documents/{doc.id}/export/hwp").content)
    assert rows[-1] == ["반 운영 특이사항", ""]
