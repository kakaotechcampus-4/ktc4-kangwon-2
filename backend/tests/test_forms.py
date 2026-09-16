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
    response = client.post("/forms/parse", files={"file": (filename, b"data")})

    assert response.status_code == 400


def test_parse_reports_422_for_invalid_hwpx():
    response = client.post("/forms/parse", files={"file": ("form.hwpx", b"not a zip")})

    assert response.status_code == 422


def test_parse_reports_500_for_runtime_error(monkeypatch):
    def fail(_path):
        raise RuntimeError("변환기 없음")

    monkeypatch.setattr(hwp_form, "extract", fail)

    response = client.post("/forms/parse", files={"file": ("form.hwp", b"data")})

    assert response.status_code == 500


def test_parse_hwpx_returns_mapped_labels(tmp_path):
    path = tmp_path / "form.hwpx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "Contents/section0.xml",
            "<hp:tbl><hp:tr><hp:tc><hp:t>주제</hp:t></hp:tc>"
            "<hp:tc><hp:t>우리 반</hp:t></hp:tc></hp:tr></hp:tbl>",
        )

    response = client.post(
        "/forms/parse",
        files={"file": (path.name, path.read_bytes(), "application/octet-stream")},
    )

    assert response.status_code == 200
    assert response.json()["label_map"] == {"주제": "topic", "우리 반": None}
