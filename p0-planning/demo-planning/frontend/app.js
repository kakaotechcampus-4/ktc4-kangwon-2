/* Planning Integration Demo — Frontend.
 *
 * 버려도 되는 코드다. 프레임워크·빌드 도구·상태관리를 쓰지 않는다.
 *
 * 이 파일은 **판단을 하지 않는다.** 모든 버튼은 Demo Backend를 통해 실제 Use
 * Case를 호출하고, 화면은 돌아온 state를 그리기만 한다. status를 Front에서
 * 바꾸거나 Gate를 흉내 내지 않는다. 월간 생성 버튼의 disabled 표시는 편의일
 * 뿐이며, 눌러도 Backend의 실제 Gate가 다시 판정한다.
 */
(function () {
  "use strict";

  var STATE = null;

  /* 월간 화면 모드. "편집하기"가 기본이다.
   *
   * 문서 미리보기는 **이미 저장된 Plan을 다시 그리는 것**이며 Generate도
   * Regenerate도 하지 않는다. 모드를 바꿔도 Backend에 아무 요청을 보내지 않는다.
   */
  var MONTHLY_VIEW_MODE = "EDITOR";

  var $ = function (id) { return document.getElementById(id); };

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined && text !== null) n.textContent = String(text);
    return n;
  }

  function clear(n) { while (n.firstChild) n.removeChild(n.firstChild); }

  function show(node, on) { node.classList.toggle("is-hidden", !on); }

  /* ------------------------------------------------- 화면 구성 전제 확인
   *
   * 아래 두 검사는 실제로 보고된 오류에서 나왔다.
   *
   *     TypeError: Cannot read properties of null (reading 'classList')
   *     TypeError: Cannot read properties of undefined (reading 'render')
   *
   * 둘 다 원인이 하나였다 — 브라우저가 **이전 `index.html`을 캐시에서** 쓰면서
   * 새 `app.js`와 짝이 맞지 않았다. 그 HTML에는 `document_view.js` script도,
   * `#monthlyEditorView` 같은 새 element도 없다.
   *
   * 그래서 모든 DOM 접근에 `?.`를 붙이는 대신 **전제를 한 번 명시적으로
   * 확인**한다. 없으면 조용히 넘어가지 않고 무엇이 없는지 말한다.
   */

  var MONTHLY_VIEW_NODE_IDS = [
    "monthlyEditorView",
    "monthlyDocumentView",
    "tabEditor",
    "tabDocument",
    "printDocument",
  ];
  /* Document View v1이 추가한 필수 markup. 전부 있거나 전부 없다. */

  var MONTHLY_VIEW_READY = false;

  function missingMonthlyViewNodes() {
    return MONTHLY_VIEW_NODE_IDS.filter(function (id) { return !$(id); });
  }

  /** 문서 미리보기 renderer. 스크립트를 못 불러왔으면 null이다.
   *
   * 문서 View는 Presentation 부가 기능이므로 없다고 해서 편집 기능을 막지
   * 않는다. 다만 **없다는 사실은 숨기지 않는다**(init에서 보고한다).
   */
  function documentRenderer() {
    var api = globalThis.MonthlyDocument;
    return api && typeof api.render === "function" ? api : null;
  }

  function busy(on, text) {
    $("busyText").textContent = text || "실행 중…";
    show($("busy"), on);
  }

  function banner(kind, text) {
    var b = $("banner");
    b.className = "banner banner--" + kind;
    b.textContent = text;
    show(b, true);
  }

  function hideBanner() { show($("banner"), false); }

  /* ------------------------------------------------------------- 통신
   *
   * 실패를 세 단계로 **구분해서** 보고한다. 예전에는 셋 다 "Demo 서버에
   * 연결하지 못했습니다"로 나갔고, 그래서 화면을 그리다 난 TypeError까지
   * 서버 문제처럼 보였다.
   *
   *     Network   fetch 자체가 실패   → 서버에 연결하지 못했습니다
   *     HTTP      응답을 못 읽음      → 응답을 해석하지 못했습니다
   *     Render    apply가 실패        → 화면을 그리는 중 오류가 발생했습니다
   */

  var NETWORK_ERROR = "Demo 서버에 연결하지 못했습니다: ";
  var DECODE_ERROR = "서버 응답을 해석하지 못했습니다.\n";

  /** 응답 본문을 JSON으로 읽는다. 못 읽으면 그 사실을 그대로 말한다. */
  function readJson(res) {
    return res.json().then(
      function (data) { return { status: res.status, data: data }; },
      function (err) {
        banner("error", DECODE_ERROR + err);
        return null;
      }
    );
  }

  function post(path, body, label) {
    busy(true, label);
    return fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    })
      .then(readJson, function (err) {
        banner("error", NETWORK_ERROR + err);
        return null;
      })
      .then(function (r) {
        busy(false);
        // Network·decode 실패는 위에서 이미 알렸다.
        if (r === null) return null;

        if (r.status === 200) {
          hideBanner();
          return applySafely(r.data) ? r.data : null;
        }
        // 실패도 Demo의 정상 결과다. 실제 오류를 그대로 보여 준다.
        if (r.data && r.data.state && !applySafely(r.data.state)) return null;
        banner("error", describeError(r.data));
        return null;
      });
  }

  function describeError(d) {
    if (!d) return "알 수 없는 오류";
    if (d.kind === "PLANNING_ERROR") {
      var lines = [
        "[" + d.outcome + "] " + d.failure_category,
        "규칙: " + d.violated_rule,
      ];
      (d.violations || []).forEach(function (v) {
        if (v.detail) lines.push("· " + v.detail);
      });
      return lines.join("\n");
    }
    if (d.kind === "LLM_UNAVAILABLE") {
      // Rule-only 결과로 대체하지 않는다. 기존 값은 그대로 남는다.
      return d.message || "AI 생성에 실패했습니다. 다시 시도해 주세요.";
    }
    if (d.kind === "LLM_CONFIG") {
      return (
        "실제 LLM 설정을 찾지 못했습니다.\n" +
        (d.message || "") +
        "\n" +
        (d.hint || "")
      );
    }
    return "[" + (d.kind || "ERROR") + "] " + (d.message || "");
  }

  /* ------------------------------------------------------- 렌더링: 공통 */

  function badge(status) {
    var draft = status !== "CONFIRMED";
    return el(
      "span",
      "badge " + (draft ? "badge--draft" : "badge--confirmed"),
      draft ? "초안 DRAFT" : "확정 CONFIRMED"
    );
  }

  function ageText(ages) {
    if (!ages || !ages.length) return "-";
    var t = ages.map(function (a) { return "만 " + a + "세"; }).join(" · ");
    return ages.length > 1 ? t + " (혼합연령)" : t;
  }

  function kvTable(pairs) {
    var t = el("table");
    var tb = el("tbody");
    pairs.forEach(function (p) {
      if (p[1] === null || p[1] === undefined || p[1] === "") return;
      var tr = el("tr");
      tr.appendChild(el("th", null, p[0]));
      tr.appendChild(el("td", "kv", p[1]));
      tb.appendChild(tr);
    });
    t.appendChild(tb);
    return t;
  }

  /* ------------------------------------------------------- 렌더링: 연간 */

  function renderYearly(y) {
    show($("stepYearly"), !!y);
    if (!y) return;

    var head = $("yearlyBadge");
    clear(head);
    head.appendChild(badge(y.status));

    $("yearlyCaption").textContent =
      y.school_year + "학년도 · " + y.classroom_ref + " · " + ageText(y.ages) +
      " · 3월~다음 해 2월 " + y.months.length + "개월";

    var body = $("yearlyBody");
    clear(body);
    var editable = y.status !== "CONFIRMED";
    y.months.forEach(function (m) {
      var tr = el("tr");
      tr.appendChild(el("td", "col-month", m.month_label));

      var td = el("td");
      td.appendChild(el("span", null, m.value));
      var prov = el("span", "cell__prov dev-only");
      prov.textContent =
        (m.theme_id || "-") + " · " + m.generation.method + " / " +
        m.generation.rule_id + " " + m.generation.rule_version;
      td.appendChild(prov);
      tr.appendChild(td);

      var act = el("td", "col-act no-print dev-only");
      var regen = el("button", "mini", "재생성");
      regen.disabled = !editable;
      regen.addEventListener("click", function () {
        post("/api/yearly/regenerate", { item_id: m.item_id }, "연간 항목 재생성 중…");
      });
      act.appendChild(regen);
      tr.appendChild(act);

      body.appendChild(tr);
    });

    $("yearlyConfirm").disabled = y.status === "CONFIRMED";
    $("yearlyConfirm").textContent =
      y.status === "CONFIRMED" ? "확정 완료" : "연간계획 확정";

    var dev = $("yearlyDev");
    clear(dev);
    dev.appendChild(
      kvTable([
        ["plan_id", y.plan_id],
        ["status", y.status],
        ["catalog", y.run ? y.run.catalog_id + " @ " + y.run.catalog_version : null],
        ["run_id", y.run ? y.run.run_id : null],
        ["llm_invoked", y.run ? String(y.run.llm_invoked) : null],
        ["llm_call_count", y.run ? String(y.run.llm_call_count) : null],
        ["audit", y.audit.map(function (a) { return a.event_type; }).join(" → ")],
      ])
    );
  }

  /* ------------------------------------------------------- 렌더링: 월 선택 */

  function renderMonthPick(s) {
    var y = s.yearly;
    show($("stepMonthPick"), !!y);
    if (!y) return;

    var gate = $("monthlyGate");
    var enabled = s.monthly_generate_enabled;
    gate.className = "gate" + (enabled ? "" : " gate--blocked");
    gate.textContent = enabled
      ? "연간계획이 CONFIRMED입니다. 월간계획을 생성할 수 있습니다."
      : "연간계획이 " + y.status + " 상태입니다. 확정해야 월간계획을 생성할 수 " +
        "있습니다. (Backend의 실제 Gate도 동일하게 판정합니다)";

    var sel = $("targetMonth");
    var keep = sel.value;
    clear(sel);
    (s.selectable_months || []).forEach(function (m) {
      sel.appendChild(new Option(m.label, m.period_key));
    });
    if (keep) sel.value = keep;
    if (!sel.value && sel.options.length) {
      // 기본값은 9월로 둔다 (5주 구조 확인에 가장 유용하다)
      for (var i = 0; i < sel.options.length; i += 1) {
        if (/-09$/.test(sel.options[i].value)) { sel.selectedIndex = i; break; }
      }
    }
    $("monthlyGenerate").disabled = !enabled;
  }

  /* ------------------------------------------------------- 렌더링: 월간 */

  function shortWeek(id) {
    var m = /W(\d+)$/.exec(id || "");
    return m ? m[1] + "주" : id || "";
  }

  function renderMonthlyCell(cell, editable, sectionKey) {
    var cls =
      cell.cell_state === "FILLED"
        ? "cell--filled"
        : cell.cell_state === "EMPTY_VALID"
        ? "cell--empty-valid"
        : "cell--empty-unresolved";
    var td = el("td", "cell " + cls);
    td.setAttribute("data-cell-state", cell.cell_state);
    td.title = cell.cell_state + " — " + cell.cell_state_note;

    var value = (cell.value || "").trim();
    td.appendChild(el("span", null, value));
    if (!value) {
      td.appendChild(
        el(
          "span",
          "cell__note",
          cell.cell_state === "EMPTY_UNRESOLVED"
            ? "근거가 없어 비워 두었습니다"
            : "비워 두는 것이 정상입니다"
        )
      );
    }

    if (cell.activity_id) {
      var ref = (cell.evidence || [])[0] || {};
      var prov = el("span", "cell__prov dev-only");
      prov.textContent =
        cell.activity_id + "\n" +
        (ref.source_type || "") + " " + (ref.source_version || "") + "\n" +
        cell.generation.method + " / " + cell.generation.rule_id + " " +
        cell.generation.rule_version;
      td.appendChild(prov);
    }

    // 재생성은 focus와 outdoor_play 두 Cell에만 제공한다.
    // theme은 Rule이 재파생하고 safety는 배치 source가 없다.
    if (sectionKey === "outdoor_play" || sectionKey === "focus") {
      var tools = el("span", "cell__tools no-print dev-only");
      var regen = el("button", "mini", "재생성");
      // Backend Gate가 최종 방어선이지만 UI도 불가능한 액션을 누르게 하지 않는다.
      regen.disabled = !editable;
      regen.addEventListener("click", function () {
        if (regen.disabled) return;
        // 같은 Plan에 동시 mutation을 날리지 않는다. 화면의 모든 재생성 버튼을
        // 응답이 올 때까지 잠근다.
        var others = document.querySelectorAll(".cell__tools button");
        for (var i = 0; i < others.length; i += 1) others[i].disabled = true;

        var label = sectionKey === "focus" ? "중심 경험" : "바깥놀이";
        // Target Cell만 진행 표시한다. 화면 전체를 덮지 않는다.
        var busy = el("span", "cell__note", "이 항목을 다시 생성하고 있습니다…");
        td.appendChild(busy);

        post(
          "/api/monthly/regenerate",
          { section_key: sectionKey, week_id: cell.week_id },
          label + " 재생성 중…"
        ).then(function (data) {
          if (data && data.last_cell_regeneration) {
            var c = data.last_cell_regeneration;
            banner(
              "ok",
              label + " 재생성 완료 (LLM " + c.provider_call_count + "회" +
                (c.validation_repair_count
                  ? ", 재요청 " + c.validation_repair_count + "회"
                  : "") + ")"
            );
          } else if (data && data.last_activity_regeneration) {
            var o = data.last_activity_regeneration;
            banner(
              "ok",
              "재생성 완료: " + o.previous_activity_id + " → " +
                o.selected_activity_id + "  (" + o.reason + ", 후보 " +
                o.candidate_count + "개, " + o.catalog_version + ")"
            );
          }
        });
        // 실패든 성공이든 서버가 돌려준 Plan으로 화면을 다시 그린다.
        // 실패 시 이전 값이 그대로 남는 이유가 이것이다 — Client가 임의로
        // 문자열을 치환하지 않는다.
      });
      tools.appendChild(regen);
      td.appendChild(tools);
    }

    return td;
  }

  /* 편집하기 ↔ 문서 미리보기.
   *
   * **Backend에 아무 요청도 보내지 않는다.** 이미 받아 둔 state로 두 화면을
   * 모두 그려 놓았고 여기서는 어느 쪽을 보일지만 정한다. 그래서 모드를
   * 오가도 Plan이 새로 만들어지거나 LLM이 호출되지 않는다.
   */
  function setMonthlyViewMode(mode) {
    // markup이 없으면 아무것도 만지지 않는다. **없다는 사실은 init에서 이미
    // 보고했다** — 여기서 조용히 넘어가는 것이 아니라 보고된 상태를 따르는 것이다.
    if (!MONTHLY_VIEW_READY) return;

    // renderer가 없으면 문서 모드로 가지 않는다. 빈 화면을 보여 주느니
    // 편집 화면에 머무는 편이 낫다.
    var isDocument = mode === "DOCUMENT" && !!documentRenderer();
    MONTHLY_VIEW_MODE = isDocument ? "DOCUMENT" : "EDITOR";

    show($("monthlyEditorView"), !isDocument);
    show($("monthlyDocumentView"), isDocument);
    show($("printDocument"), isDocument);

    [["tabEditor", !isDocument], ["tabDocument", isDocument]].forEach(function (p) {
      var tab = $(p[0]);
      tab.classList.toggle("is-active", p[1]);
      tab.setAttribute("aria-selected", String(p[1]));
    });

    // 인쇄 시 문서만 남기기 위한 표시. 화면 상태가 곧 인쇄 대상이다.
    document.body.classList.toggle("doc-mode", isDocument);
  }

  function renderMonthly(m) {
    show($("stepMonthly"), !!m);
    if (!m) {
      // Plan이 사라지면 문서 모드에 머물러 있을 이유가 없다.
      setMonthlyViewMode("EDITOR");
      return;
    }

    $("monthlyTitle").textContent =
      m.calendar_year + "년 " + m.calendar_month + "월 월간보육계획안";
    var b = $("monthlyBadge");
    clear(b);
    b.appendChild(badge(m.status));

    $("monthlyClassroom").textContent = m.classroom_ref;
    $("monthlyAge").textContent = ageText(m.ages);

    var themeCell = $("monthlyTheme");
    clear(themeCell);
    themeCell.appendChild(el("strong", null, m.theme ? m.theme.value : "-"));
    var themeProv = el("span", "cell__prov dev-only");
    themeProv.textContent =
      "상위 anchor " + m.parent_lineage.parent_yearly_theme_id +
      " · " + m.parent_lineage.parent_yearly_plan_id;
    themeCell.appendChild(themeProv);

    var weeks = (m.weeks || []).filter(function (w) { return w.active !== false; });
    var head = $("monthlyHead");
    clear(head);
    var hr = el("tr");
    hr.appendChild(el("th", "row-head", "구분"));
    weeks.forEach(function (w) {
      var th = el("th");
      th.appendChild(document.createTextNode(shortWeek(w.week_id)));
      var range = el("span", "week-range");
      range.textContent =
        w.start.slice(5).replace("-", "/") + "~" + w.end.slice(5).replace("-", "/");
      th.appendChild(range);
      hr.appendChild(th);
    });
    head.appendChild(hr);

    var editable = m.status !== "CONFIRMED";
    var body = $("monthlyBody");
    clear(body);
    (m.rows || []).forEach(function (row) {
      var tr = el("tr");
      tr.appendChild(el("th", "row-head", row.label));
      var byWeek = {};
      (row.cells || []).forEach(function (c) { byWeek[c.week_id] = c; });
      weeks.forEach(function (w) {
        var c = byWeek[w.week_id];
        tr.appendChild(
          c ? renderMonthlyCell(c, editable, row.section_key)
            : el("td", "cell cell--empty-valid")
        );
      });
      body.appendChild(tr);
    });

    $("monthlyConfirm").disabled = m.status === "CONFIRMED";
    $("monthlyConfirm").textContent =
      m.status === "CONFIRMED" ? "확정 완료" : "월간계획 확정";
    $("monthlyConfirmHint").textContent =
      "확정(CONFIRMED)은 작성 결과를 확정했다는 뜻이며 법정 안전교육 검증 완료를 " +
      "의미하지 않습니다.";

    // 문서 미리보기도 **같은 state**로 다시 그린다. 두 화면이 서로 다른
    // 출처를 보면 화면마다 값이 달라진다.
    var doc = MONTHLY_VIEW_READY ? documentRenderer() : null;
    if (doc) doc.render($("monthlyDocumentView"), m);

    var dev = $("monthlyDev");
    clear(dev);
    dev.appendChild(
      kvTable([
        ["plan_id", m.plan_id],
        ["template", m.template_version],
        ["activity catalog", m.activity_catalog
          ? m.activity_catalog.catalog_id + " @ " + m.activity_catalog.catalog_version
          : "(미연결)"],
        ["parent yearly", m.parent_lineage.parent_yearly_plan_id + " / " +
          m.parent_lineage.parent_yearly_period_key],
        ["theme reference", m.parent_lineage.reference_version],
        ["llm_call_count", m.run ? String(m.run.llm_call_count) : null],
        ["cells", m.run
          ? "FILLED " + m.run.filled_cell_count +
            " / EMPTY_VALID " + m.run.empty_valid_cell_count +
            " / EMPTY_UNRESOLVED " + m.run.empty_unresolved_cell_count
          : null],
      ])
    );

    (m.constraints || []).forEach(function (c) {
      dev.appendChild(el("p", null, c.kind + " = " + c.verification));
      dev.appendChild(el("p", "cell__note", c.detail));
    });

    if (m.run && m.run.traces && m.run.traces.length) {
      dev.appendChild(el("h4", null, "Activity Selection Trace"));
      var t = el("table");
      var thead = el("tr");
      ["주차", "선택", "이유", "후보", "근거강도", "theme"].forEach(function (h) {
        thead.appendChild(el("th", null, h));
      });
      t.appendChild(thead);
      m.run.traces.forEach(function (tr0) {
        var tr = el("tr");
        [
          shortWeek(tr0.week_id),
          (tr0.selected_activity_id || "-") + "\n" + (tr0.selected_label || ""),
          tr0.reason,
          String(tr0.candidate_count),
          String(tr0.evidence_strength),
          String(tr0.theme_matched),
        ].forEach(function (v) { tr.appendChild(el("td", "kv", v)); });
        t.appendChild(tr);
      });
      dev.appendChild(t);
    }
  }

  /* ----------------------------------------------------- 렌더링: 기록/참조 */

  function renderLog(s) {
    var box = $("logBox");
    clear(box);
    (s.log || []).slice().reverse().forEach(function (e) {
      box.appendChild(
        el("div", e.ok ? null : "bad", (e.ok ? "OK  " : "ERR ") + e.action + "  " + e.detail)
      );
    });

    var ref = $("refBox");
    clear(ref);
    var r = s.references;
    if (!r) {
      ref.appendChild(el("p", null, s.llm_config_error || "Reference 정보 없음"));
      return;
    }
    ref.appendChild(
      kvTable([
        ["Yearly 생성 경로", r.yearly_uses_llm
          ? "실제 LLM 호출 (use_llm=True)"
          : "Rule 전용 (--yearly-rule-only · LLM 호출 없음)"],
        ["Theme Reference", r.theme_catalog_id + " @ " + r.theme_catalog_version],
        ["Monthly Template", r.template_id + " @ " + r.template_version],
        ["Safety Legal Rule", r.safety_rule_version],
        ["Activity Reference", r.activity_catalog_id + " @ " + r.activity_catalog_version],
        ["Yearly LLM", r.llm_provider + " / " + r.llm_model +
          (r.llm_api_style ? " (" + r.llm_api_style + ")" : "")],
        ["live_api", String(r.live_api)],
      ])
    );
    if (s.llm_calls && s.llm_calls.length) {
      ref.appendChild(el("h4", null, "실제 LLM 호출 기록"));
      var t = el("table");
      var h = el("tr");
      ["operation", "model", "성공", "latency(ms)", "retry", "items", "in/out tokens"].forEach(
        function (x) { h.appendChild(el("th", null, x)); }
      );
      t.appendChild(h);
      s.llm_calls.forEach(function (c) {
        var tr = el("tr");
        [
          c.operation, c.model, String(c.success), String(c.latency_ms),
          String(c.retry_count), String(c.item_count),
          (c.input_tokens === null ? "-" : c.input_tokens) + " / " +
            (c.output_tokens === null ? "-" : c.output_tokens),
        ].forEach(function (v) { tr.appendChild(el("td", "kv", v)); });
        t.appendChild(tr);
      });
      ref.appendChild(t);
    }
  }

  /* --------------------------------------------------------------- 적용 */

  /** `apply`를 감싸 렌더링 오류와 통신 오류를 **구분해서** 보고한다.
   *
   * 예전에는 둘 다 "Demo 서버에 연결하지 못했습니다"로 나갔다. 화면을 그리다
   * 난 TypeError까지 통신 문제로 보이면 엉뚱한 곳을 들여다보게 된다.
   */
  function applySafely(s) {
    try {
      apply(s);
      return true;
    } catch (err) {
      banner(
        "error",
        "서버 응답은 받았지만 화면을 그리는 중 오류가 발생했습니다." +
          "\n" + err +
          "\n브라우저를 강력 새로고침(Ctrl+Shift+R) 해 보세요."
      );
      if (globalThis.console) console.error(err);
      return false;
    }
  }

  function apply(s) {
    STATE = s;
    renderYearly(s.yearly);
    renderMonthPick(s);
    renderMonthly(s.monthly);
    renderLog(s);
    // 어떤 경로로 Yearly가 생성되는지 숨기지 않는다.
    var mode = $("yearlyMode");
    if (mode && s.references) {
      mode.textContent = s.references.yearly_uses_llm
        ? "Yearly: 실제 LLM 호출"
        : "Yearly: Rule 전용 (LLM 호출 없음)";
      mode.className =
        "topbar__mode" + (s.references.yearly_uses_llm ? "" : " topbar__mode--off");
      if (s.references.monthly_generation_mode) {
        mode.textContent +=
          "  ·  Monthly: " +
          (s.references.monthly_generation_mode === "LLM_PLANNER"
            ? "LLM Planner"
            : "Rule 전용");
      }
    }
    if (s.references === null && s.llm_config_error) {
      banner("error", "실제 LLM 설정을 찾지 못했습니다.\n" + s.llm_config_error);
    }
  }

  /* --------------------------------------------------------------- 구동 */

  function selectedAges() {
    return Array.prototype.slice
      .call($("ageBox").querySelectorAll("input[type=checkbox]"))
      .filter(function (c) { return c.checked; })
      .map(function (c) { return Number(c.value); });
  }

  function init() {
    document.body.classList.toggle("dev", false);

    $("devToggle").addEventListener("change", function (e) {
      document.body.classList.toggle("dev", e.target.checked);
    });

    $("ageMode").addEventListener("change", function (e) {
      var boxes = $("ageBox").querySelectorAll("input[type=checkbox]");
      if (e.target.value === "SINGLE") {
        var first = true;
        Array.prototype.forEach.call(boxes, function (b) {
          if (b.checked && !first) b.checked = false;
          if (b.checked) first = false;
        });
      }
    });

    $("yearlyGenerate").addEventListener("click", function () {
      var ages = selectedAges();
      if (!ages.length) {
        banner("error", "연령을 하나 이상 선택하세요.");
        return;
      }
      post(
        "/api/yearly/generate",
        {
          school_year: Number($("schoolYear").value),
          ages: ages,
          daycare_ref: $("daycareRef").value,
          classroom_ref: $("classroomRef").value,
        },
        "실제 LLM을 호출해 연간계획을 생성하는 중…"
      );
    });

    $("yearlyConfirm").addEventListener("click", function () {
      post("/api/yearly/confirm", {}, "연간계획 확정 중…");
    });

    $("monthlyGenerate").addEventListener("click", function () {
      var btn = $("monthlyGenerate");
      if (btn.disabled) return;          // 중복 클릭 방지
      btn.disabled = true;
      post(
        "/api/monthly/generate",
        { target_month: $("targetMonth").value },
        "월간계획을 생성하고 있습니다… (몇 초 걸립니다)"
      ).then(function () {
        // 성공·실패 모두 post()가 서버 state로 다시 그리므로 버튼 상태는 거기서
        // 정해진다. 네트워크 자체가 끊긴 경우만 여기서 되살린다.
        if (STATE) renderMonthPick(STATE);
        else btn.disabled = false;
      });
    });

    $("monthlyConfirm").addEventListener("click", function () {
      post("/api/monthly/confirm", {}, "월간계획 확정 중…");
    });

    // ---- 전제 1. Document View markup이 있는가 (필수)
    var missing = missingMonthlyViewNodes();
    MONTHLY_VIEW_READY = missing.length === 0;

    if (!MONTHLY_VIEW_READY) {
      // 숨기지 않고 정확히 무엇이 없는지 말한다. 이 조합이 나오는 경로는
      // 사실상 하나뿐이다 — 캐시된 옛 index.html + 새 app.js.
      if (globalThis.console) {
        console.error(
          "index.html이 app.js와 맞지 않습니다. 없는 element: " +
            missing.join(", ")
        );
      }
      banner(
        "error",
        "화면 구성 파일이 서로 맞지 않습니다.\n" +
          "브라우저를 강력 새로고침(Ctrl+Shift+R) 해 주세요."
      );
    } else {
      $("tabEditor").addEventListener("click", function () {
        setMonthlyViewMode("EDITOR");
      });

      $("tabDocument").addEventListener("click", function () {
        setMonthlyViewMode("DOCUMENT");
      });

      $("printDocument").addEventListener("click", function () {
        // 브라우저의 인쇄 → "PDF로 저장"을 쓴다. 별도 PDF Backend를 두지 않는다.
        // 인쇄가 끝나도 App state를 바꾸지 않는다.
        window.print();
      });

      // ---- 전제 2. 문서 renderer가 준비됐는가 (부가 기능)
      //
      // 없어도 편집 기능은 그대로 쓸 수 있다. 대신 왜 못 쓰는지 알린다 —
      // `undefined.render`가 아니라 "스크립트를 못 받았다"로 보이게 한다.
      if (!documentRenderer()) {
        if (globalThis.console) {
          console.error(
            "document_view.js가 로드되지 않았습니다 (globalThis.MonthlyDocument 없음)."
          );
        }
        var docTab = $("tabDocument");
        docTab.disabled = true;
        docTab.title =
          "문서 미리보기를 불러오지 못했습니다. " +
          "브라우저를 강력 새로고침(Ctrl+Shift+R) 해 보세요.";
      }
    }

    setMonthlyViewMode("EDITOR");

    $("resetButton").addEventListener("click", function () {
      post("/api/session/reset", {}, "세션 초기화 중…");
    });

    // 초기 로딩도 post()와 같은 3단계 분리를 쓴다.
    fetch("/api/state")
      .then(readJson, function (err) {
        // 여기서만 "연결 실패"다. 나머지는 각자 자기 이름으로 말한다.
        banner("error", NETWORK_ERROR + err);
        return null;
      })
      .then(function (r) {
        if (r === null) return;
        if (r.status !== 200) {
          banner("error", describeError(r.data));
          return;
        }
        applySafely(r.data);
      });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
