/* 쓱싹요정 Monthly 임시 시각화 Demo.
 *
 * 버려도 되는 코드다. 빌드 도구도 프레임워크도 상태관리도 쓰지 않는다.
 * 데이터는 fixtures/*.js 가 window.SSUKSAK_DEMO_FIXTURES 에 넣어 둔 스냅샷뿐이며
 * Backend를 호출하지도 import하지도 않는다.
 */
(function () {
  "use strict";

  var FIXTURES = window.SSUKSAK_DEMO_FIXTURES || {};

  var ORDER = [
    "2026-09-draft",
    "2026-09-confirmed",
    "2026-09-no-activity",
    "2026-03-draft"
  ];

  var STATE_CLASS = {
    FILLED: "cell--filled",
    EMPTY_VALID: "cell--empty-valid",
    EMPTY_UNRESOLVED: "cell--empty-unresolved"
  };

  var $ = function (id) {
    return document.getElementById(id);
  };

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function clear(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  function ageLabel(header) {
    var ages = header.ages || [];
    if (!ages.length) return "-";
    var text = ages.map(function (a) { return "만 " + a + "세"; }).join(" · ");
    return ages.length > 1 ? text + " (혼합연령)" : text;
  }

  function shortWeek(weekId) {
    // "2026-09-W3" → "3주"
    var m = /W(\d+)$/.exec(weekId || "");
    return m ? m[1] + "주" : weekId || "";
  }

  function dateRange(week) {
    var trim = function (iso) { return (iso || "").slice(5).replace("-", "/"); };
    return trim(week.start) + "~" + trim(week.end);
  }

  /* ------------------------------------------------------------- 렌더링 */

  function renderBadge(status) {
    var draft = status !== "CONFIRMED";
    return el(
      "span",
      "badge " + (draft ? "badge--draft" : "badge--confirmed"),
      draft ? "초안 DRAFT" : "확정 CONFIRMED"
    );
  }

  function renderFixtureBanner(data) {
    var box = $("fixtureBanner");
    clear(box);
    box.appendChild(el("strong", null, "FIXTURE — 임시 시각화 Demo"));
    box.appendChild(
      document.createTextNode(
        " · 이 화면은 Production Frontend가 아니며 Backend를 호출하지 않습니다. " +
          "아래 내용은 " +
          data.generated_by +
          " 로 추출한 정적 스냅샷입니다."
      )
    );
    box.appendChild(el("br"));
    box.appendChild(document.createTextNode(data.fixture_note || ""));
  }

  function renderMeta(data) {
    var h = data.header;
    $("metaMonth").textContent =
      h.calendar_year + "년 " + h.calendar_month + "월  (학년도 " + h.school_year + ")";

    var statusCell = $("metaStatus");
    clear(statusCell);
    statusCell.appendChild(renderBadge(h.status));
    statusCell.appendChild(
      el("span", "cell__note", "plan_id " + h.plan_id + " · Template " + h.template_version)
    );

    $("metaClassroom").textContent = h.classroom_ref;
    $("metaAge").textContent = ageLabel(h);

    var themeCell = $("metaTheme");
    clear(themeCell);
    if (data.theme) {
      themeCell.appendChild(el("span", "theme-value", data.theme.value || "(빈 값)"));
      themeCell.appendChild(
        el(
          "span",
          "cell__note",
          "상위 연간계획 anchor: " + data.parent_lineage.parent_yearly_theme_id
        )
      );
    } else {
      themeCell.textContent = "-";
    }

    $("docSubtitle").textContent =
      h.daycare_ref + " · " + h.classroom_ref + " · " + ageLabel(h);
  }

  function renderCell(cell, showProvenance) {
    var td = el("td", "cell " + (STATE_CLASS[cell.cell_state] || ""));
    td.setAttribute("data-cell-state", cell.cell_state);

    var value = (cell.value || "").trim();
    td.appendChild(el("span", "cell__value", value));

    if (!value) {
      td.appendChild(
        el(
          "span",
          "cell__note",
          cell.cell_state === "EMPTY_UNRESOLVED"
            ? "미검증 — " + cell.cell_state_note
            : cell.cell_state_note
        )
      );
    }

    if (cell.activity_id) {
      var prov = el("span", "cell__provenance provenance");
      prov.appendChild(document.createTextNode(cell.activity_id));
      var ref = (cell.evidence || [])[0];
      if (ref && ref.source_version) {
        prov.appendChild(el("br"));
        prov.appendChild(document.createTextNode(ref.source_type + " " + ref.source_version));
      }
      if (cell.generation && cell.generation.rule_id) {
        prov.appendChild(el("br"));
        prov.appendChild(
          document.createTextNode(
            cell.generation.method + " / " + cell.generation.rule_id + " " +
              cell.generation.rule_version
          )
        );
      }
      if (!showProvenance) prov.classList.add("is-hidden");
      td.appendChild(prov);
    }

    return td;
  }

  function renderTable(data, showProvenance) {
    var weeks = (data.weeks || []).filter(function (w) { return w.active !== false; });

    var head = $("planHead");
    clear(head);
    var headRow = el("tr");
    headRow.appendChild(el("th", "row-head", "구분"));
    weeks.forEach(function (w) {
      var th = el("th");
      th.appendChild(document.createTextNode(shortWeek(w.week_id)));
      th.appendChild(el("span", "week-range", dateRange(w)));
      headRow.appendChild(th);
    });
    head.appendChild(headRow);

    var body = $("planBody");
    clear(body);
    (data.rows || []).forEach(function (row) {
      var tr = el("tr");
      tr.appendChild(el("th", "row-head", row.label));
      var byWeek = {};
      (row.cells || []).forEach(function (c) { byWeek[c.week_id] = c; });
      weeks.forEach(function (w) {
        var cell = byWeek[w.week_id];
        tr.appendChild(
          cell
            ? renderCell(cell, showProvenance)
            : el("td", "cell cell--empty-valid")
        );
      });
      body.appendChild(tr);
    });

    $("colCount").textContent = weeks.length + "열";
  }

  function renderFooter(data) {
    var footer = $("docFooter");
    clear(footer);
    var bits = [];
    if (data.activity_catalog) {
      bits.push(
        "Activity Reference " + data.activity_catalog.catalog_version
      );
    } else {
      bits.push("Activity Reference 미연결");
    }
    bits.push("Theme Reference " + data.parent_lineage.reference_version);
    if (data.run) bits.push("LLM 호출 " + data.run.llm_call_count + "회");
    (data.constraints || []).forEach(function (c) {
      bits.push(c.kind + " = " + c.verification);
    });
    bits.forEach(function (b) { footer.appendChild(el("span", null, b)); });
  }

  /* ---------------------------------------------------------------- 구동 */

  function render(key, showProvenance) {
    var data = FIXTURES[key];
    if (!data) return;
    renderFixtureBanner(data);
    renderMeta(data);
    renderTable(data, showProvenance);
    renderFooter(data);
    document.title = "월간보육계획안 Demo — " + data.fixture_title;
  }

  function init() {
    var select = $("fixtureSelect");
    var toggle = $("provenanceToggle");

    var keys = ORDER.filter(function (k) { return FIXTURES[k]; });
    Object.keys(FIXTURES).forEach(function (k) {
      if (keys.indexOf(k) === -1) keys.push(k);
    });

    if (!keys.length) {
      $("fixtureBanner").textContent =
        "fixture를 찾지 못했습니다. `python demo-frontend/tools/export_fixtures.py` 를 먼저 실행하세요.";
      return;
    }

    keys.forEach(function (k) {
      select.appendChild(new Option(FIXTURES[k].fixture_title || k, k));
    });

    var draw = function () { render(select.value, toggle.checked); };
    select.addEventListener("change", draw);
    toggle.addEventListener("change", draw);
    $("printButton").addEventListener("click", function () { window.print(); });
    draw();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
