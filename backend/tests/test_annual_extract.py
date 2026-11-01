"""연간 가져오기 — 파일 추출(계약 I-B). 합성 파일만 쓴다. 진짜 LLM 은 부르지 않는다."""

import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter

from app.config import settings
from app.features.centers.models import Center, Class
from app.features.plans import annual_extract
from app.main import app

client = TestClient(app)

HP = 'xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" '
HP += 'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph"'


def _cell(text: str) -> str:
    paragraph = f"<hp:p><hp:run><hp:t>{text}</hp:t></hp:run></hp:p>"
    return f"<hp:tc><hp:subList>{paragraph}</hp:subList></hp:tc>"


def _hwpx(rows) -> bytes:
    table = "".join("<hp:tr>" + "".join(map(_cell, row)) + "</hp:tr>" for row in rows)
    xml = (
        f"<hs:sec {HP}><hp:p><hp:run><hp:t>담임: 홍길동</hp:t></hp:run></hp:p>"
        f"<hp:p><hp:run><hp:tbl>{table}</hp:tbl></hp:run></hp:p></hs:sec>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as package:
        package.writestr("mimetype", "application/hwp+zip")
        package.writestr("Contents/section0.xml", xml)
    return buffer.getvalue()


def _docx(rows) -> bytes:
    ns = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    cells = "".join(
        "<w:tr>"
        + "".join(f"<w:tc><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:tc>" for text in row)
        + "</w:tr>"
        for row in rows
    )
    xml = f"<w:document {ns}><w:body><w:tbl>{cells}</w:tbl></w:body></w:document>"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as package:
        package.writestr("word/document.xml", xml)
    return buffer.getvalue()


def _pdf(text: bytes) -> bytes:
    """글자층이 있는 한 쪽짜리 PDF. 한글 글꼴을 넣기 번거로워 ASCII 로 쓴다."""
    stream = b"BT /F1 12 Tf 20 100 Td (" + text + b") Tj ET"
    objects = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 200]"
        b"/Resources<</Font<</F1<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>>>>>"
        b"/Contents 4 0 R>>",
        b"<</Length %d>>stream\n" % len(stream) + stream + b"\nendstream",
    ]
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj" % number + body + b"endobj\n"
    xref = len(out)
    out += b"xref\n0 5\n0000000000 65535 f \n"
    out += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    out += b"trailer<</Size 5/Root 1 0 R>>\nstartxref\n%d\n%%%%EOF" % xref
    return bytes(out)


def test_형식은_확장자와_내용을_같이_보고_표_칸은_한_줄이다():
    hwpx = _hwpx([["3월", "우리 반 친구"]])
    assert annual_extract.detect_format("a.hwpx", hwpx) == "HWPX"
    assert annual_extract.detect_format("a.docx", hwpx) is None
    assert annual_extract.detect_format("a.pdf", hwpx) is None
    assert annual_extract.extract_lines("HWPX", hwpx) == ["담임: 홍길동", "3월", "우리 반 친구"]

    docx = _docx([["4월", "봄과 동식물"]])
    assert annual_extract.detect_format("a.docx", docx) == "DOCX"
    assert annual_extract.extract_lines("DOCX", docx) == ["4월", "봄과 동식물"]

    pdf = _pdf(b"Spring Garden")
    assert annual_extract.detect_format("a.pdf", pdf) == "PDF"
    assert annual_extract.extract_lines("PDF", pdf) == ["Spring Garden"]


def test_이름과_기관명만_가린다():
    text = "담임 교사: 홍길동\n원장\n김영희\n햇살어린이집 연간계획\n우리 반 친구\n우리 유치원"
    assert annual_extract.mask_personal(text) == (
        "담임 교사: ○○\n원장\n○○\n○○어린이집 연간계획\n우리 반 친구\n우리 유치원"
    )
    # 직함 앞 이름 · 「명」 표기 · 여러 명(PUI-01)
    text = "가나다 교사\n담임교사명: 가나다\n담임: 가나다, 라마바\n담임\n가나다 · 라마바"
    assert annual_extract.mask_personal(text) == (
        "○○ 교사\n담임교사명: ○○\n담임: ○○, ○○\n담임\n○○ · ○○"
    )


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
        age_max=4,
        teacher_name="김선생",
    )
    db_session.add(klass)
    db_session.flush()
    teacher.center_id = center.id
    return klass


def _post(klass, name: str, data: bytes):
    return client.post(
        "/api/plans/annual/import/extract",
        data={"class_id": str(klass.id)},
        files={"file": (name, data, "application/octet-stream")},
    )


def test_hwp_는_400_글자_없는_PDF_는_422(mine):
    response = _post(mine, "연간.hwp", b"\xd0\xcf\x11\xe0hwp")
    assert response.status_code == 400
    assert response.json()["error"] == {
        "code": "UNSUPPORTED_FILE_TYPE",
        "message": "한글에서 HWPX나 PDF로 저장해서 올려 주세요",
        "fields": ["file"],
    }

    blank = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.write(blank)
    response = _post(mine, "빈.pdf", blank.getvalue())
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


def test_mock_은_결정적으로_원문의_칸만_옮긴다(mine, monkeypatch):
    monkeypatch.setattr(settings, "llm_mode", "mock")
    response = _post(mine, "연간.hwpx", _hwpx([["3월", "우리 반 친구"], ["4월", "봄"]]))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["file"]["format"] == "HWPX" and len(body["file"]["sha256"]) == 64
    assert [m["month"] for m in body["months"]] == [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2]
    assert body["months"][0] == {
        "month": 3,
        "theme": "우리 반 친구",
        "sub_themes": [],
        "missing": False,
    }
    assert body["months"][2]["missing"] is True and body["months"][2]["theme"] is None
    assert "5월 생활주제를 찾지 못했어요" in body["notices"]


@pytest.mark.parametrize(
    "teacher_row",
    [["담임", "홍길동"], ["홍길동 교사"], ["담임교사명: 홍길동"], ["담임: 김하늘, 홍길동"]],
)
def test_원문에_없는_글자는_버리고_가린_원문만_보낸다(mine, monkeypatch, teacher_row):
    sent = {}

    def fake(system, user, **kwargs):
        sent.update(user=user, **kwargs)
        months = [
            {"month": 3, "theme": "우리  반 친구", "sub_themes": ["친구 이름", "지어낸 소주제"]},
            {"month": 4, "theme": "모델이 지은 주제", "sub_themes": []},
        ]
        return json.dumps({"months": months}, ensure_ascii=False)

    monkeypatch.setattr(settings, "llm_mode", "real")
    monkeypatch.setattr(annual_extract, "complete_json", fake)
    data = _docx([teacher_row, ["3월", "우리 반 친구", "친구 이름"], ["4월", "봄"]])
    response = _post(mine, "연간.docx", data)

    assert response.status_code == 200, response.text
    months = response.json()["months"]
    assert months[0]["theme"] == "우리 반 친구"
    assert months[0]["sub_themes"] == ["친구 이름"]
    assert months[1] == {"month": 4, "theme": None, "sub_themes": [], "missing": True}
    assert sent["max_completion_tokens"] == 2000
    assert "홍길동" not in sent["user"]
    assert "김하늘" not in sent["user"]
