"""Monthly Plan Document View v1 — 문서형 Presentation 검증.

이 화면은 **Presentation Layer**다. Planner v1(Domain / Rule / LLM / Retrieval /
Validator / Provenance)은 한 줄도 바뀌지 않으며, 여기서 검증하는 것은 "저장된
Plan이 문서로 어떻게 보이는가"뿐이다.

두 축으로 확인한다.

    Python   Backend view가 문서에 필요한 값을 실제로 주는가
    Node     순수 model 변환이 4주·5주에서 올바른가

Node가 없는 환경에서는 model test만 skip되고 나머지는 그대로 돈다. Node가 있는
환경(개발·CI)에서는 실제 저장된 MonthlyPlan으로 문서 model을 만들어 확인한다.
"""

from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "demo-planning" / "frontend"
DEMO_BACKEND = ROOT / "demo-planning" / "backend"
if str(DEMO_BACKEND) not in sys.path:
    sys.path.insert(0, str(DEMO_BACKEND))

import views as demo_views  # noqa: E402

from tests.golden import monthly_llm_harness as H  # noqa: E402

DOCUMENT_JS = FRONTEND / "document_view.js"
APP_JS = FRONTEND / "app.js"
INDEX_HTML = FRONTEND / "index.html"
STYLES_CSS = FRONTEND / "styles.css"


# ------------------------------------------------------------------ fixture


def _stored_monthly_view(target_month: str) -> dict:
    """실제로 저장된 MonthlyPlan을 Demo view로 바꾼다.

    Fixture 문자열이 아니라 **Use Case가 만들어 Repository에 저장한 Plan**이다.
    결정론 FakeLLM을 쓰므로 실제 API를 호출하지 않는다.
    """
    harness = H.LlmGoldenHarness()
    packet = harness.packet(target_month)
    harness.llm.set_monthly_proposal(
        H.reference_only_proposal(packet)
        if target_month == H.CASE_A_MONTH
        else H.mixed_proposal(packet)
    )
    result = harness.generate.execute(
        H.generate_command(target_month=target_month)
    )
    assert harness.monthly_plan_persisted
    return demo_views.monthly_view(result.plan, result.run)


@pytest.fixture(scope="module")
def four_week_view() -> dict:
    return _stored_monthly_view(H.CASE_A_MONTH)


@pytest.fixture(scope="module")
def five_week_view() -> dict:
    return _stored_monthly_view(H.CASE_B_MONTH)


# ------------------------------------------------------- Node model driver

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node를 찾지 못했다")

_DRIVER = """
const fs = require("fs");
require(process.argv[2]);
const input = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
const out = {};
for (const [key, view] of Object.entries(input)) {
  out[key] = globalThis.MonthlyDocument.buildDocumentModel(view);
}
out.__constants = { UNRESOLVED_TEXT: globalThis.MonthlyDocument.UNRESOLVED_TEXT };
process.stdout.write(JSON.stringify(out));
"""


def build_models(tmp_path: pathlib.Path, views_by_key: dict) -> dict:
    """`document_view.js`의 순수 변환을 실제로 실행한다."""
    driver = tmp_path / "driver.js"
    driver.write_text(_DRIVER, encoding="utf-8")
    payload = tmp_path / "views.json"
    payload.write_text(
        json.dumps(views_by_key, ensure_ascii=False), encoding="utf-8"
    )
    proc = subprocess.run(
        [NODE, str(driver), str(DOCUMENT_JS), str(payload)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


# ============================================= Backend가 주는 문서용 데이터


def test_view_provides_the_month_date_range(four_week_view, five_week_view):
    """머리말의 `기간`. **주차 날짜가 아니라 달의 경계다.**"""
    assert four_week_view["month_start"] == "2026-06-01"
    assert four_week_view["month_end"] == "2026-06-30"
    assert five_week_view["month_start"] == "2026-07-01"
    assert five_week_view["month_end"] == "2026-07-31"


def test_week_dates_come_from_canonical_periods_not_the_month_range(
    five_week_view,
):
    """7월 1주는 6/29에 시작한다 (OD-M02).

    문서가 달 경계로 주차를 계산했다면 이 값이 7/1이 됐을 것이다. Frontend가
    날짜를 스스로 만들지 않는다는 증거다.
    """
    first = five_week_view["weeks"][0]
    assert first["start"] == "2026-06-29"
    assert first["start"] < five_week_view["month_start"]


def test_view_rows_contain_only_activated_sections(four_week_view):
    keys = [r["section_key"] for r in four_week_view["rows"]]
    assert keys == ["focus", "outdoor_play", "safety_education"]
    for inactive in (
        "goals",
        "habits",
        "emergency_response",
        "drill",
        "indoor_alternative",
        "special_program",
        "event_schedule",
    ):
        assert inactive not in keys


def test_week_axis_is_not_a_content_row(four_week_view, five_week_view):
    for view in (four_week_view, five_week_view):
        assert "week_axis" not in [r["section_key"] for r in view["rows"]]


# =================================================== 문서 model (Node 실행)


@needs_node
def test_document_model_matches_the_stored_plan(
    tmp_path, four_week_view, five_week_view
):
    models = build_models(
        tmp_path, {"four": four_week_view, "five": five_week_view}
    )

    four = models["four"]
    assert four["title"] == "2026년 6월 월간계획안"
    assert four["theme"] == four_week_view["theme"]["value"]
    assert len(four["weeks"]) == 4

    five = models["five"]
    assert five["title"] == "2026년 7월 월간계획안"
    assert len(five["weeks"]) == 5


@needs_node
@pytest.mark.parametrize("key,expected_weeks", [("four", 4), ("five", 5)])
def test_every_row_has_one_cell_per_week(
    tmp_path, four_week_view, five_week_view, key, expected_weeks
):
    """4주든 5주든 주차 수를 하드코딩하지 않는다."""
    models = build_models(
        tmp_path, {"four": four_week_view, "five": five_week_view}
    )
    model = models[key]
    assert len(model["weeks"]) == expected_weeks
    assert model["rows"]
    for row in model["rows"]:
        assert len(row["cells"]) == expected_weeks


@needs_node
def test_cells_land_in_the_week_they_belong_to(tmp_path, five_week_view):
    """Cell이 다른 주차 칸으로 밀려 들어가지 않는다."""
    models = build_models(tmp_path, {"five": five_week_view})
    model = models["five"]

    by_key = {r["section_key"]: r for r in five_week_view["rows"]}
    order = [w["week_id"] for w in model["weeks"]]
    assert order == [w["week_id"] for w in five_week_view["weeks"]]

    for row in model["rows"]:
        source = {c["week_id"]: c for c in by_key[row["section_key"]]["cells"]}
        for index, week_id in enumerate(order):
            value = (source[week_id]["value"] or "").strip()
            if value:
                assert row["cells"][index]["text"] == value


@needs_node
def test_row_order_is_focus_outdoor_safety(tmp_path, four_week_view):
    models = build_models(tmp_path, {"four": four_week_view})
    labels = [r["label"] for r in models["four"]["rows"]]
    assert labels == ["중심 경험", "바깥놀이", "안전교육"]


@needs_node
def test_unresolved_safety_cells_say_so_without_inventing_content(
    tmp_path, four_week_view
):
    """AI가 임의 내용을 채우지 않는다. 법적 충족도 주장하지 않는다."""
    models = build_models(tmp_path, {"four": four_week_view})
    unresolved = models["__constants"]["UNRESOLVED_TEXT"]
    safety = next(
        r for r in models["four"]["rows"] if r["section_key"] == "safety_education"
    )
    assert all(c["text"] == unresolved for c in safety["cells"])
    assert all(c["unresolved"] is True for c in safety["cells"])
    assert models["four"]["has_unresolved"] is True


@needs_node
def test_document_model_carries_no_internal_or_technical_terms(
    tmp_path, four_week_view, five_week_view
):
    """교사용 문서에 내부 이름·Provenance·상태가 나가지 않는다."""
    models = build_models(
        tmp_path, {"four": four_week_view, "five": five_week_view}
    )
    for key in ("four", "five"):
        model = dict(models[key])
        # section_key는 CSS·테스트가 쓰는 내부 식별자이며 화면 문자열이 아니다.
        for row in model["rows"]:
            row.pop("section_key", None)
        blob = json.dumps(model, ensure_ascii=False)
        for banned in (
            "focus",
            "outdoor_play",
            "safety_education",
            "week_axis",
            "DRAFT",
            "CONFIRMED",
            "RULE_LLM",
            "RULE_ONLY",
            "LLM_PLANNER",
            "INSTITUTION_SAMPLE",
            "ACTIVITY_REFERENCE",
            "LLM_SYNTHESIZED",
            "EMPTY_UNRESOLVED",
            "NOT_VERIFIED_SOURCE_REQUIRED",
            "packet_fingerprint",
            "gpt-4.1",
            "plan_id",
            "template_version",
            "evidence",
            "generation",
        ):
            assert banned not in blob, f"{key} 문서 model에 {banned}가 들어갔다"


@needs_node
def test_document_model_never_truncates_long_sentences(
    tmp_path, four_week_view
):
    """긴 focus 문장을 `…`으로 잘라 쓰지 않는다 (§29)."""
    models = build_models(tmp_path, {"four": four_week_view})
    focus = next(
        r for r in models["four"]["rows"] if r["section_key"] == "focus"
    )
    source = next(
        r for r in four_week_view["rows"] if r["section_key"] == "focus"
    )
    assert [c["text"] for c in focus["cells"]] == [
        c["value"].strip() for c in source["cells"]
    ]
    for cell in focus["cells"]:
        assert "…" not in cell["text"]
        assert not cell["text"].endswith("...")


@needs_node
def test_missing_values_are_omitted_not_invented(tmp_path, four_week_view):
    """없는 반 이름을 지어내지 않는다 (§11)."""
    stripped = dict(four_week_view)
    stripped["classroom_ref"] = ""
    stripped["daycare_ref"] = None
    models = build_models(tmp_path, {"bare": stripped})

    keys = [item["key"] for item in models["bare"]["meta"]]
    assert "반" not in keys
    assert "기관" not in keys
    assert "연령" in keys and "기간" in keys
    blob = json.dumps(models["bare"], ensure_ascii=False)
    for invented in ("○○반", "○○어린이집", "-반"):
        assert invented not in blob


@needs_node
@pytest.mark.parametrize("ages,expected", [([4], "만 4세"), ([3, 4], "만 3·4세 혼합")])
def test_age_label_follows_existing_semantics(
    tmp_path, four_week_view, ages, expected
):
    view = dict(four_week_view)
    view["ages"] = ages
    models = build_models(tmp_path, {"x": view})
    age = next(i for i in models["x"]["meta"] if i["key"] == "연령")
    assert age["value"] == expected


# ================================================ Document View는 Preview다


def _code_only(source: str) -> str:
    """주석을 뺀 실행 코드만 남긴다.

    "input을 만들지 않는다"라고 **적어 둔 주석**이 "input을 만든다"로 읽히면
    검사가 자기 설명에 걸려 넘어진다. 확인하려는 것은 코드가 무엇을 하는가다.
    """
    return re.sub(r"/\*.*?\*/", "", source, flags=re.S)


def test_document_renderer_creates_no_editable_control():
    """문서 화면에는 input·textarea·contenteditable·재생성 버튼이 없다 (§15)."""
    code = _code_only(DOCUMENT_JS.read_text("utf-8"))
    for banned in (
        "contenteditable",
        'createElement("input")',
        'createElement("textarea")',
        'el("input"',
        'el("textarea"',
        'el("button"',
        "addEventListener",
    ):
        assert banned not in code, f"문서 renderer에 {banned}가 있다"


def test_document_renderer_calls_no_backend_api():
    """문서 미리보기는 Generate도 Regenerate도 하지 않는다 (§1·§5)."""
    code = _code_only(DOCUMENT_JS.read_text("utf-8"))
    for banned in ("fetch(", "/api/", "XMLHttpRequest", "post("):
        assert banned not in code


def test_document_uses_semantic_table_markup():
    """DIV Grid로 표를 흉내 내지 않는다 (§33)."""
    source = DOCUMENT_JS.read_text("utf-8")
    for tag in ('"table"', '"thead"', '"tbody"', '"th"', '"td"', '"colgroup"'):
        assert tag in source
    assert 'setAttribute("scope", "col")' in source
    assert 'setAttribute("scope", "row")' in source


def test_document_does_not_claim_to_be_an_official_form():
    """공식 양식이라고 주장하지 않는다 (§3)."""
    source = DOCUMENT_JS.read_text("utf-8")
    for banned in ("표준 월간계획안", "정부 공식", "누리과정 공식", "법정 양식"):
        assert banned not in source
    # 법적 충족 주장도 하지 않는다.
    for banned in ("법적 기준 충족", "안전교육 완료", "평가제"):
        assert banned not in source


# ================================================================= 화면 전환


def test_index_has_the_view_toggle_and_print_button():
    html = INDEX_HTML.read_text("utf-8")
    assert 'id="tabEditor"' in html
    assert 'id="tabDocument"' in html
    assert 'id="printDocument"' in html
    assert 'id="monthlyEditorView"' in html
    assert 'id="monthlyDocumentView"' in html
    assert 'src="document_view.js"' in html
    # toggle 자체는 인쇄되지 않는다.
    assert 'class="viewtabs no-print"' in html


def test_toggle_sends_no_request_and_calls_no_generation():
    """모드 전환이 Backend를 부르지 않는다 — 이미 받은 state로만 그린다."""
    source = APP_JS.read_text("utf-8")
    body = source.split("function setMonthlyViewMode(")[1].split("\n  }")[0]
    for banned in ("post(", "fetch(", "/api/"):
        assert banned not in body

    for tab in ('$("tabEditor").addEventListener', '$("tabDocument").addEventListener'):
        handler = source.split(tab)[1][:200]
        assert "setMonthlyViewMode" in handler
        assert "post(" not in handler
        assert "/api/" not in handler


def test_both_views_are_drawn_from_the_same_state():
    source = APP_JS.read_text("utf-8")
    render = source.split("function renderMonthly(m)")[1].split(
        "function renderLog"
    )[0]
    # 편집 표와 문서를 **같은 `m`**으로 그린다. 서로 다른 출처를 보면 화면마다
    # 값이 달라진다.
    assert "doc.render($(\"monthlyDocumentView\"), m)" in render


def test_print_button_uses_the_browser_print_dialog():
    """별도 PDF Backend를 만들지 않는다 (§18)."""
    source = APP_JS.read_text("utf-8")
    # handler 하나만 잘라 본다. 범위를 넓게 잡으면 옆 handler가 걸린다.
    handler = source.split('$("printDocument").addEventListener')[1].split("});")[0]
    assert "window.print()" in handler
    # 인쇄가 끝나도 state를 바꾸지 않는다.
    for banned in ("post(", "apply(", "setMonthlyViewMode("):
        assert banned not in handler


def test_editor_controls_are_untouched():
    """기존 편집 화면 기능이 그대로 남아 있다 (§14)."""
    html = INDEX_HTML.read_text("utf-8")
    js = APP_JS.read_text("utf-8")
    for keep in ('id="monthlyConfirm"', 'id="monthlyHead"', 'id="monthlyBody"'):
        assert keep in html
    assert 'sectionKey === "outdoor_play" || sectionKey === "focus"' in js
    assert "regen.disabled = !editable" in js


# ==================================================================== 인쇄


def test_print_css_uses_a4_landscape():
    css = STYLES_CSS.read_text("utf-8")
    page = css.split("@page")[1][:120]
    assert "A4 landscape" in page


def test_print_css_hides_controls_in_document_mode():
    css = STYLES_CSS.read_text("utf-8")
    block = css.split("@media print")[1]
    for hidden in (
        "body.doc-mode #monthlyEditorView",
        "body.doc-mode .viewtabs",
        "body.doc-mode #stepYearly",
        "body.doc-mode #stepMonthPick",
    ):
        assert hidden in block
    # 기존 규칙도 남아 있다.
    for hidden in (".topbar", "#stepInput", "#stepLog", ".no-print", ".dev-block"):
        assert hidden in block


def test_document_avoids_splitting_the_grid_across_pages():
    css = STYLES_CSS.read_text("utf-8")
    grid = css.split(".paper__grid {")[1].split("}")[0]
    assert "break-inside: avoid" in grid
    assert "page-break-inside: avoid" in grid


def test_document_does_not_truncate_cell_text_in_css():
    css = STYLES_CSS.read_text("utf-8")
    for banned in ("text-overflow: ellipsis", "-webkit-line-clamp"):
        assert banned not in css


def test_paper_has_a_bounded_width():
    """화면이 넓어도 문서 폭이 무한정 늘어나지 않는다 (§16)."""
    css = STYLES_CSS.read_text("utf-8")
    paper = css.split(".paper {")[1].split("\n}")[0]
    assert "297mm" in paper
    assert "210mm" in paper


# ================================ Frontend 초기화 / 모듈 / lifecycle 회귀
#
# 이 절은 실제로 보고된 두 오류에서 나왔다.
#
#     TypeError: Cannot read properties of null (reading 'classList')
#     TypeError: Cannot read properties of undefined (reading 'render')
#
# 둘은 **같은 원인**이었다. 브라우저가 이전 `index.html`을 캐시에서 쓰면서 새
# `app.js`와 짝이 맞지 않았고, 그 HTML에는 `document_view.js` script도
# `#monthlyEditorView`도 없다. 서버는 정상이었다.
#
#     null 이었던 것        #monthlyEditorView / #monthlyDocumentView / #printDocument
#     undefined 였던 것     globalThis.MonthlyDocument
#
# 게다가 그 Frontend 오류가 "Demo 서버에 연결하지 못했습니다"로 표시돼 원인을
# 서버에서 찾게 만들었다.


# ---------------------------------------------------------- script graph


def test_script_dependency_is_explicit_and_ordered():
    """app.js는 document_view.js에 의존한다. 순서를 우연에 맡기지 않는다."""
    html = INDEX_HTML.read_text("utf-8")
    doc_at = html.index('src="document_view.js"')
    app_at = html.index('src="app.js"')
    assert doc_at < app_at, "document_view.js가 app.js보다 먼저 와야 한다"

    # defer/async를 섞으면 순서 보장이 깨진다. 둘 다 쓰지 않는다.
    for tag in re.findall(r"<script[^>]*>", html):
        assert "defer" not in tag
        assert "async" not in tag
        assert 'type="module"' not in tag


def test_frontend_is_plain_script_not_es_module():
    """module/non-module 혼용을 만들지 않는다 (기존 Vanilla JS convention)."""
    for path in (APP_JS, DOCUMENT_JS):
        code = _code_only(path.read_text("utf-8"))
        assert not re.search(r"^\s*export\s", code, re.M)
        assert not re.search(r"^\s*import\s", code, re.M)


def test_renderer_name_matches_exactly_between_definition_and_use():
    """이름 불일치(대소문자 포함)를 막는다."""
    defined = re.findall(
        r"global\.(\w+)\s*=", _code_only(DOCUMENT_JS.read_text("utf-8"))
    )
    assert defined == ["MonthlyDocument"]
    used = set(
        re.findall(r"globalThis\.(\w+)", _code_only(APP_JS.read_text("utf-8")))
    )
    assert used == {"MonthlyDocument", "console"}


def test_renderer_is_registered_on_the_global_object():
    """module scope에만 두면 app.js가 접근할 수 없다."""
    code = _code_only(DOCUMENT_JS.read_text("utf-8"))
    assert "global.MonthlyDocument = {" in code
    assert "render: renderMonthlyDocument" in code
    assert "globalThis" in code


# --------------------------------------------- 필수 DOM vs Optional DOM


def _required_node_ids() -> list[str]:
    source = APP_JS.read_text("utf-8")
    block = source.split("var MONTHLY_VIEW_NODE_IDS = [")[1].split("]")[0]
    return re.findall(r'"(\w+)"', block)


def test_required_monthly_view_nodes_are_declared_and_checked():
    """필수 DOM 누락을 optional chaining으로 숨기지 않고 한 번 명시 확인한다."""
    source = APP_JS.read_text("utf-8")
    assert "function missingMonthlyViewNodes()" in source
    declared = _required_node_ids()
    for required in (
        "monthlyEditorView",
        "monthlyDocumentView",
        "tabEditor",
        "tabDocument",
        "printDocument",
    ):
        assert required in declared

    # 없으면 무엇이 없는지 말한다.
    assert "index.html이 app.js와 맞지 않습니다" in source
    assert "console.error" in source


def test_declared_required_nodes_all_exist_in_the_markup():
    """선언과 markup이 어긋나면 정상 페이지에서도 초기화가 막힌다."""
    html = INDEX_HTML.read_text("utf-8")
    declared = _required_node_ids()
    assert declared
    for node_id in declared:
        assert 'id="%s"' % node_id in html, "%s가 index.html에 없다" % node_id


def test_show_does_not_swallow_missing_required_nodes():
    """`show()`에 무조건 null 가드를 붙여 문제를 숨기지 않는다 (§6)."""
    source = APP_JS.read_text("utf-8")
    show = source.split("function show(node, on)")[1].split("\n")[0]
    assert "if (node)" not in show
    assert "node.classList.toggle" in show


def test_view_mode_switch_respects_the_readiness_flag():
    source = APP_JS.read_text("utf-8")
    mode = source.split("function setMonthlyViewMode(")[1].split("\n  }")[0]
    assert "if (!MONTHLY_VIEW_READY) return;" in mode
    # 준비된 뒤에는 노드가 있다고 보고 그대로 쓴다 — 가드를 흩뿌리지 않는다.
    assert "if (!tab) return;" not in mode


# ------------------------------------------- renderer dependency 진단


def test_missing_renderer_is_diagnosed_not_silently_ignored():
    """`undefined.render` 대신 "스크립트를 못 받았다"로 보이게 한다 (§8)."""
    source = APP_JS.read_text("utf-8")
    assert "function documentRenderer()" in source
    assert "globalThis.MonthlyDocument.render(" not in source

    init = source.split("  function init()")[1]
    assert "document_view.js가 로드되지 않았습니다" in init
    assert "docTab.disabled = true" in init

    # 이 진단은 init에서 한 번 한다. renderMonthly 안에 두면 Plan이 이미 있는
    # 상태로 들어왔을 때 영영 실행되지 않는다.
    render = source.split("function renderMonthly(m)")[1].split(
        "function renderLog"
    )[0]
    assert "docTab" not in render


def test_document_failure_does_not_disable_the_editor():
    """Presentation 부가 기능의 실패 범위를 문서 화면으로 제한한다 (§21)."""
    source = APP_JS.read_text("utf-8")
    init = source.split("  function init()")[1]
    before_guard = init.split("if (!documentRenderer())")[0]
    for editor_handler in (
        'yearlyGenerate").addEventListener',
        'monthlyGenerate").addEventListener',
        'monthlyConfirm").addEventListener',
    ):
        assert editor_handler in before_guard


# ------------------------------------------------------- Error UX 분리


def test_error_ux_separates_network_decode_and_render():
    """§9 — 세 단계를 각자 자기 이름으로 보고한다."""
    source = APP_JS.read_text("utf-8")
    assert "var NETWORK_ERROR" in source
    assert "var DECODE_ERROR" in source
    assert "function readJson(res)" in source
    assert "function applySafely(s)" in source

    safe = source.split("function applySafely(s)")[1].split("\n  }")[0]
    assert "화면을 그리는 중 오류" in safe
    assert "연결하지 못했습니다" not in safe

    # "연결하지 못했습니다"는 **코드에서 한 번만** 정의되고, fetch 거부
    # handler 두 곳(post · 초기 로딩)에서만 쓰인다. 주석은 세지 않는다.
    code = _code_only(source)
    assert code.count("연결하지 못했습니다") == 1
    assert code.count("NETWORK_ERROR + err") == 2

    # apply()를 날것으로 부르는 자리가 없다.
    assert ".then(apply)" not in source
    assert re.search(r"^\s*apply\(r\.data\);", source, re.M) is None


def test_render_failure_is_not_caught_by_a_network_catch():
    """fetch 체인의 포괄 `.catch`가 렌더링 오류를 삼키지 않는다."""
    source = APP_JS.read_text("utf-8")
    post = source.split("function post(path, body, label)")[1].split(
        "function describeError"
    )[0]
    assert ".catch(" not in post


# --------------------------------------------------------- Static asset


def test_document_view_js_is_served_as_javascript():
    """§11 — JS URL에 index.html이 돌아오는 fallback이 없어야 한다."""
    import threading
    import urllib.request
    from http.server import ThreadingHTTPServer

    import app as demo_app

    server = ThreadingHTTPServer(("127.0.0.1", 0), demo_app.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d" % server.server_address[1]
    try:
        with urllib.request.urlopen(base + "/document_view.js", timeout=10) as res:
            body = res.read().decode("utf-8")
            assert res.status == 200
            assert "javascript" in res.headers.get("Content-Type", "")
            assert "<!DOCTYPE" not in body  # index.html fallback이 아니다
            assert "MonthlyDocument" in body
            assert "no-store" in res.headers.get("Cache-Control", "")
    finally:
        server.shutdown()
        server.server_close()


def test_static_files_are_served_without_caching():
    """캐시된 HTML + 새 JS 조합이 다시 생기지 않게 한다."""
    source = (DEMO_BACKEND / "app.py").read_text("utf-8")
    block = source.split("def end_headers(self):")[1].split("\n    def ")[0]
    assert "no-store" in block
    assert 'self.path.startswith("/api/")' in block


# ------------------------------------------------- DOM reference 수명


def test_no_module_level_dom_caching():
    """재렌더링 뒤 stale reference를 만지지 않는다 (§19)."""
    source = APP_JS.read_text("utf-8")
    cached = re.findall(r"^  var \w+ *= *(?:document\.|\$\()", source, re.M)
    assert not cached, "module 수준에 DOM을 캐싱했다: %s" % cached


def test_document_is_rebuilt_from_scratch_on_every_render():
    """문서 container를 비우고 다시 만든다 — 이전 DOM을 재사용하지 않는다."""
    code = _code_only(DOCUMENT_JS.read_text("utf-8"))
    render = code.split("function renderMonthlyDocument(root, monthly)")[1]
    assert "clear(root)" in render
