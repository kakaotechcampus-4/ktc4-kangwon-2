/* Monthly Plan Document View — 문서형 Presentation.
 *
 * 저장된 `MonthlyPlan`을 어린이집 실무에서 익숙한 월간계획안 형태로 그린다.
 * **Preview이지 편집 화면이 아니다.** 여기서는 input·textarea·contenteditable을
 * 만들지 않고 재생성 버튼도 붙이지 않는다. 수정은 편집 화면에서만 한다.
 *
 * 이것은 공식 양식이 아니다. Template A는 sample-derived / non-normative이며
 * 이 View는 그 의미를 바꾸지 않는다.
 *
 * 판단을 하지 않는다. Backend가 돌려준 canonical state만 읽는다.
 *
 *     주차 목록 · 주차 날짜   Domain의 canonical WeekPeriod
 *     행 구성 · 행 순서       Backend view의 rows (활성 Section만)
 *     기간                    Backend view의 month_start / month_end
 *
 * 날짜를 여기서 계산하거나 Cell 값을 다듬지 않는다. focus 문장이 길다고 잘라
 * 쓰지 않는다 — 문장 품질은 Planner 영역이고 문서는 있는 그대로 렌더링한다.
 */
(function (global) {
  "use strict";

  /** 배치 근거가 없는 Cell의 문서 표기.
   *
   * 편집 화면의 "근거가 없어 비워 두었습니다"와 **같은 의미**를 문서 문구로
   * 줄인 것이다. 법적 충족을 주장하지 않고, AI가 임의 내용을 채우지도 않는다.
   */
  var UNRESOLVED_TEXT = "미확정";

  var SECTION_TITLE_FALLBACK = "구분";

  function dotted(iso) {
    return typeof iso === "string" ? iso.replace(/-/g, ".") : "";
  }

  function shortRange(startIso, endIso) {
    function md(iso) {
      return String(Number(iso.slice(5, 7))) + "/" + String(Number(iso.slice(8, 10)));
    }
    return md(startIso) + " ~ " + md(endIso);
  }

  /** 만 4세 / 만 3·4세 혼합. 기존 age semantics를 바꾸지 않는다. */
  function ageLabel(monthly) {
    var ages = (monthly.ages || []).slice().sort(function (a, b) { return a - b; });
    if (!ages.length) return null;
    if (ages.length === 1) return "만 " + ages[0] + "세";
    return "만 " + ages.join("·") + "세 혼합";
  }

  /** 값이 실제로 있을 때만 돌려준다. 없는 이름을 지어내지 않는다. */
  function present(value) {
    if (value === null || value === undefined) return null;
    var text = String(value).trim();
    return text ? text : null;
  }

  /** 문서 본문에 들어갈 Cell 하나. 기술 용어·Provenance를 담지 않는다. */
  function documentCell(cell) {
    if (!cell) return { text: "", unresolved: false };
    var value = present(cell.value);
    if (value) return { text: value, unresolved: false };
    return {
      text: cell.cell_state === "EMPTY_UNRESOLVED" ? UNRESOLVED_TEXT : "",
      unresolved: cell.cell_state === "EMPTY_UNRESOLVED",
    };
  }

  /**
   * 저장된 Monthly view state → 문서 model.
   *
   * 순수 함수다. DOM을 만들지 않으므로 테스트가 직접 호출할 수 있다.
   */
  function buildDocumentModel(monthly) {
    if (!monthly) return null;

    // 활성 주차만 열이 된다. 주차 수를 고정하지 않는다 — 4주도 5주도 그대로다.
    var weeks = (monthly.weeks || [])
      .filter(function (w) { return w.active !== false; })
      .map(function (w) {
        return {
          week_id: w.week_id,
          label: w.label,
          range: shortRange(w.start, w.end),
        };
      });

    // Backend가 준 rows를 그대로 쓴다. 활성 Section만 들어 있고 순서도 정해져
    // 있으므로 여기서 행을 추가하거나 재정렬하지 않는다. 비활성 Section의 빈
    // 행을 미리 만들지도 않는다.
    var rows = (monthly.rows || []).map(function (row) {
      var byWeek = {};
      (row.cells || []).forEach(function (c) { byWeek[c.week_id] = c; });
      return {
        section_key: row.section_key,
        label: row.label || SECTION_TITLE_FALLBACK,
        cells: weeks.map(function (w) { return documentCell(byWeek[w.week_id]); }),
      };
    });

    var meta = [];
    var classroom = present(monthly.classroom_ref);
    var daycare = present(monthly.daycare_ref);
    var age = ageLabel(monthly);
    // 값이 없는 항목은 자리만 남기지 않고 아예 뺀다.
    if (classroom) meta.push({ key: "반", value: classroom });
    if (age) meta.push({ key: "연령", value: age });
    if (monthly.month_start && monthly.month_end) {
      meta.push({
        key: "기간",
        value: dotted(monthly.month_start) + " ~ " + dotted(monthly.month_end),
      });
    }
    if (daycare) meta.push({ key: "기관", value: daycare });

    return {
      title: monthly.calendar_year + "년 " + monthly.calendar_month + "월 월간계획안",
      meta: meta,
      // 생활주제는 표 안에서 매주 반복하지 않고 머리말에 한 번 쓴다.
      theme: monthly.theme ? present(monthly.theme.value) : null,
      weeks: weeks,
      rows: rows,
      has_unresolved: rows.some(function (r) {
        return r.cells.some(function (c) { return c.unresolved; });
      }),
    };
  }

  /* ------------------------------------------------------------- 렌더링 */

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined && text !== null) n.textContent = String(text);
    return n;
  }

  function clear(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  function renderHeader(model) {
    var head = el("header", "paper__head");
    head.appendChild(el("h1", "paper__title", model.title));

    if (model.meta.length) {
      var line = el("div", "paper__meta");
      model.meta.forEach(function (item) {
        var box = el("div", "paper__meta-item");
        box.appendChild(el("span", "paper__meta-key", item.key));
        box.appendChild(el("span", "paper__meta-value", item.value));
        line.appendChild(box);
      });
      head.appendChild(line);
    }

    if (model.theme) {
      var theme = el("div", "paper__theme");
      theme.appendChild(el("span", "paper__meta-key", "생활주제"));
      theme.appendChild(el("span", "paper__theme-value", model.theme));
      head.appendChild(theme);
    }
    return head;
  }

  function renderGrid(model) {
    var table = el("table", "paper__grid");
    table.setAttribute("data-week-count", String(model.weeks.length));

    var colgroup = el("colgroup");
    colgroup.appendChild(el("col", "paper__col-head"));
    model.weeks.forEach(function () { colgroup.appendChild(el("col")); });
    table.appendChild(colgroup);

    var thead = el("thead");
    var hr = el("tr");
    var corner = el("th", "paper__corner", "구분");
    corner.setAttribute("scope", "col");
    hr.appendChild(corner);
    model.weeks.forEach(function (w) {
      var th = el("th");
      th.setAttribute("scope", "col");
      th.appendChild(el("span", "paper__week-label", w.label));
      th.appendChild(el("span", "paper__week-range", w.range));
      hr.appendChild(th);
    });
    thead.appendChild(hr);
    table.appendChild(thead);

    var tbody = el("tbody");
    model.rows.forEach(function (row) {
      var tr = el("tr");
      var rowHead = el("th", "paper__row-head", row.label);
      rowHead.setAttribute("scope", "row");
      tr.appendChild(rowHead);
      row.cells.forEach(function (cell) {
        var td = el("td", cell.unresolved ? "paper__cell is-unresolved" : "paper__cell");
        td.appendChild(el("span", "paper__cell-text", cell.text));
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    return table;
  }

  function renderFooter(model) {
    var footer = el("footer", "paper__footer");
    if (model.has_unresolved) {
      footer.appendChild(
        el(
          "p",
          "paper__footnote",
          "안전교육은 배치 근거가 확정되지 않아 " + UNRESOLVED_TEXT + "으로 두었습니다."
        )
      );
    }
    footer.appendChild(
      el("p", "paper__disclaimer", "쓱싹요정 Demo 출력물입니다. 제출용 공식 문서가 아닙니다.")
    );
    return footer;
  }

  /** 문서를 `root` 안에 다시 그린다. 기존 내용은 지운다. */
  function renderMonthlyDocument(root, monthly) {
    clear(root);
    var model = buildDocumentModel(monthly);
    if (!model) return null;

    var paper = el("article", "paper");
    paper.appendChild(renderHeader(model));
    paper.appendChild(renderGrid(model));
    paper.appendChild(renderFooter(model));
    root.appendChild(paper);
    return model;
  }

  global.MonthlyDocument = {
    UNRESOLVED_TEXT: UNRESOLVED_TEXT,
    buildDocumentModel: buildDocumentModel,
    render: renderMonthlyDocument,
  };
})(typeof globalThis !== "undefined" ? globalThis : this);
