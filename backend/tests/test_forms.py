import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.features.forms import hwp_form, mapping
from app.main import app

client = TestClient(app)


def test_from_html_separates_nested_tables():
    tables = hwp_form.from_html(
        "<table><tr><td><table><tr><td>중첩</td></tr></table></td></tr></table>"
    )

    assert len(tables) == 2
    assert "중첩" in hwp_form.labels(tables)


def test_from_html_preserves_rowspan_and_colspan():
    tables = hwp_form.from_html(
        '<table><tr><td rowspan="2">출결</td><td colspan="3">월요일</td></tr></table>'
    )

    assert tables[0][0][0]["rowspan"] == 2
    assert tables[0][0][1]["colspan"] == 3


def test_from_html_converts_br_to_space():
    tables = hwp_form.from_html("<table><tr><td>출결<br/>사항</td></tr></table>")

    assert tables[0][0][0]["text"] == "출결 사항"


def test_from_html_normalizes_whitespace():
    tables = hwp_form.from_html("<table><tr><td>  활동\n\t 목표  </td></tr></table>")

    assert tables[0][0][0]["text"] == "활동 목표"


def test_labels_skips_empty_cells():
    tables = hwp_form.from_html("<table><tr><td></td><td>   </td><td>주제</td></tr></table>")

    assert hwp_form.labels(tables) == ["주제"]


def test_from_hwpx_reads_tables(tmp_path):
    path = tmp_path / "form.hwpx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "Contents/section0.xml",
            "<hp:tbl><hp:tr><hp:tc><hp:t>주제</hp:t></hp:tc>"
            "<hp:tc><hp:t>우리 반</hp:t></hp:tc></hp:tr></hp:tbl>",
        )

    assert hwp_form.from_hwpx(path) == [
        [
            [
                {"text": "주제", "rowspan": 1, "colspan": 1},
                {"text": "우리 반", "rowspan": 1, "colspan": 1},
            ]
        ]
    ]


@pytest.mark.parametrize(
    ("filename", "expected"),
    [("form.HWPX", "hwpx"), ("form.hwp", "hwp")],
)
def test_extract_uses_file_extension(monkeypatch, filename, expected):
    monkeypatch.setattr(hwp_form, "from_hwpx", lambda path: "hwpx")
    monkeypatch.setattr(hwp_form, "from_hwp", lambda path: "hwp")

    assert hwp_form.extract(filename) == expected


def test_to_standard_ignores_whitespace():
    assert mapping.to_standard("활동 목표") == mapping.to_standard("활동목표") == "activity_goal"


@pytest.mark.parametrize(
    ("label", "expected"),
    [("주제", "topic"), ("놀이주제", "topic"), ("예상놀이", "activity")],
)
def test_to_standard_maps_aliases(label, expected):
    assert mapping.to_standard(label) == expected


def test_to_standard_returns_none_for_unknown_label():
    assert mapping.to_standard("존재하지않는라벨") is None


def test_map_labels_keeps_original_labels():
    assert mapping.map_labels(["활동 목표", "3"]) == {"활동 목표": "activity_goal", "3": None}


def test_alias_table_rejects_normalized_collision(clean_alias_cache, monkeypatch, tmp_path):
    path = tmp_path / "label_mapping.json"
    path.write_text(
        json.dumps(
            {
                "concepts": {
                    "topic": {"aliases": ["주제"]},
                    "activity": {"aliases": ["주 제"]},
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(mapping, "_MAPPING_PATH", path)

    with pytest.raises(ValueError, match="alias 충돌"):
        mapping._alias_table()


@pytest.mark.parametrize("filename", ["form.pdf", "form"])
def test_parse_rejects_unsupported_extension(filename):
    response = client.post("/api/forms/parse", files={"file": (filename, b"data")})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"
    assert response.json()["error"]["fields"] == ["file"]


def test_parse_reports_422_for_invalid_hwpx():
    response = client.post("/api/forms/parse", files={"file": ("form.hwpx", b"not a zip")})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"
    assert response.json()["error"]["fields"] == ["file"]


def test_parse_errors_use_the_contract_envelope():
    """봉투는 error 하나뿐이고 fields 는 하나여도 배열이다 (docs/api-spec.md 「공통」)."""
    response = client.post("/api/forms/parse", files={"file": ("form.pdf", b"data")})

    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "fields"}
    assert isinstance(body["error"]["fields"], list)
    assert isinstance(body["error"]["message"], str) and body["error"]["message"]


def test_parse_reports_503_when_converter_is_missing(monkeypatch):
    """hwp5html 이 없는 것은 교사가 고칠 수 없다 — 503 이고 재시도 대상이 아니다."""

    def fail(_path):
        raise RuntimeError("hwp5html 없음 — pip install pyhwp six")

    monkeypatch.setattr(hwp_form, "extract", fail)

    response = client.post("/api/forms/parse", files={"file": ("form.hwp", b"data")})

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DEPENDENCY_UNAVAILABLE"


def test_parse_does_not_leak_internal_message(monkeypatch):
    """설치 안내가 교사 화면에 뜨면 안 된다."""

    def fail(_path):
        raise RuntimeError("hwp5html 없음 — pip install pyhwp six")

    monkeypatch.setattr(hwp_form, "extract", fail)

    response = client.post("/api/forms/parse", files={"file": ("form.hwp", b"data")})

    assert "pip install" not in response.text
    assert "hwp5html" not in response.text


def test_parse_hwpx_returns_mapped_labels(tmp_path):
    path = tmp_path / "form.hwpx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "Contents/section0.xml",
            "<hp:tbl><hp:tr><hp:tc><hp:t>주제</hp:t></hp:tc>"
            "<hp:tc><hp:t>우리 반</hp:t></hp:tc></hp:tr></hp:tbl>",
        )

    response = client.post(
        "/api/forms/parse",
        files={"file": (path.name, path.read_bytes(), "application/octet-stream")},
    )

    assert response.status_code == 200
    assert response.json()["label_map"] == {"주제": "topic", "우리 반": None}
