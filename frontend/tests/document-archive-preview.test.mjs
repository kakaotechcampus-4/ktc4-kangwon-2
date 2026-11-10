import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";

const require = createRequire(import.meta.url);
const model = await import("../lib/workspace/model.ts");
const { archivePlanEntry } = await import("../lib/workspace/document-archive.ts");
const source = readFileSync(
  new URL("../components/workspace/DocumentArchivePreview.tsx", import.meta.url),
  "utf8",
);
const code = require("next/dist/compiled/babel/core").transformSync(source, {
  filename: "DocumentArchivePreview.tsx",
  babelrc: false,
  configFile: false,
  presets: [
    [require("next/dist/compiled/babel/preset-env"), { targets: { node: "current" } }],
    [require("next/dist/compiled/babel/preset-react"), { runtime: "automatic" }],
    require("next/dist/compiled/babel/preset-typescript"),
  ],
}).code;
const jsx = (type, props) => ({ type, props });
function flatten(node) {
  if (node == null || typeof node === "boolean") return [];
  if (Array.isArray(node)) return node.flatMap(flatten);
  if (typeof node !== "object") return [node];
  if (typeof node.type === "function") return flatten(node.type(node.props));
  return [node, ...flatten(node.props?.children)];
}
const text = (node) =>
  flatten(node)
    .filter((v) => typeof v === "string" || typeof v === "number")
    .join(" ");
const nodes = (node) => flatten(node).filter((v) => typeof v === "object");
const settle = async () => {
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
};
function harness(
  gateway = async () => {
    throw new Error("Unexpected API call");
  },
  remove = async () => {
    throw new Error("Unexpected delete");
  },
  unconfirm = async () => {
    throw new Error("Unexpected unconfirm");
  },
  pushed = [],
) {
  const values = [];
  let cursor = 0;
  let previous;
  let cleanup;
  let tree;
  const imports = {
    "react/jsx-runtime": { jsx, jsxs: jsx, Fragment: "fragment" },
    react: {
      useState(initial) {
        const n = cursor++;
        if (!(n in values)) values[n] = typeof initial === "function" ? initial() : initial;
        return [
          values[n],
          (next) => {
            values[n] = typeof next === "function" ? next(values[n]) : next;
          },
        ];
      },
      useEffect(fn, deps) {
        if (!previous || deps.some((x, i) => x !== previous[i])) {
          cleanup?.();
          previous = deps;
          cleanup = fn();
        }
      },
    },
    "next/link": { __esModule: true, default: "link" },
    "next/navigation": { useRouter: () => ({ push: (href) => pushed.push(href) }) },
    "@/lib/workspace/model": model,
    "@/lib/api/plans": {
      getAnnualPlan: (id, signal) => gateway("annual", id, signal),
      deleteAnnualPlan: (id) => remove("annual", id),
      unconfirmAnnualPlan: (id, revision) => unconfirm("annual", id, revision),
    },
    "@/lib/api/monthly": {
      getMonthlyPlan: (id, signal) => gateway("monthly", id, signal),
      deleteMonthlyPlan: (id) => remove("monthly", id),
      unconfirmMonthlyPlan: (id, revision) => unconfirm("monthly", id, revision),
    },
    "@/lib/api/playMonthly": {
      getPlayMonthly: (id, signal) => gateway("play", id, signal),
      deletePlayMonthly: (id) => remove("play", id),
      unconfirmPlayMonthly: (id, revision) => unconfirm("play", id, revision),
    },
    "@/lib/api/weekly": {
      getWeeklyPlan: (id, signal) => gateway("weekly", id, signal),
      deleteWeeklyPlan: (id) => remove("weekly", id),
      unconfirmWeeklyPlan: (id, revision) => unconfirm("weekly", id, revision),
    },
    "@/lib/api/client": { errorCode: (e) => e?.code ?? null },
    "@/components/plan-generator/PlayMonthlyConfirm": { __esModule: true, default: "ask" },
    "./WorkspaceUI": { ws: {} },
    "./CircleMark": { CircleMark: "circle-mark" },
    "./DocumentArchive.module.css": {
      __esModule: true,
      default: new Proxy({}, { get: (_, key) => (typeof key === "string" ? key : undefined) }),
    },
  };
  const m = { exports: {} };
  new Function("require", "module", "exports", code)(
    (name) => {
      assert.ok(name in imports, name);
      return imports[name];
    },
    m,
    m.exports,
  );
  return {
    ...m.exports,
    render(target, onDeleted) {
      cursor = 0;
      tree = m.exports.PlanArchivePreview({ target, onDeleted });
      return tree;
    },
    tree: () => tree,
    unmount: () => cleanup?.(),
  };
}
const doc = {
  id: "doc:1",
  kind: "observation",
  title: "관찰 실제 제목",
  className: "햇살반",
  childName: "가나다",
  start: "2026-10-19",
  end: "2026-10-20",
  status: "confirmed",
  createdAt: "2026-10-19T00:00:00Z",
  sections: [
    { heading: "사실", body: "블록을 쌓았다." },
    { heading: "해석", body: "기록의 해석" },
    { heading: "지원", body: "블록을 준비한다." },
  ],
  classNote: "반 운영 실제 내용",
  reviewNote: "교사 검토 메모",
  stale: true,
};
const props = (overrides = {}) => ({
  document: doc,
  status: "ready",
  error: "",
  onRetry() {},
  onEdit() {},
  ...overrides,
});

test("실제 본문·아동·반·기간·메모를 읽기 전용으로 표시하고 confirmed+stale를 보존한다", () => {
  const before = JSON.stringify(doc);
  const { default: Preview } = harness();
  const tree = Preview(props());
  for (const value of [
    doc.title,
    doc.childName,
    doc.className,
    "블록을 쌓았다.",
    "기록의 해석",
    "블록을 준비한다.",
    doc.classNote,
    doc.reviewNote,
    "확정",
    "재검토",
  ])
    assert.ok(text(tree).includes(value), value);
  assert.equal(
    nodes(tree).some((n) => ["input", "textarea", "select", "editor"].includes(n.type)),
    false,
  );
  assert.equal(JSON.stringify(doc), before);
});
test("미리보기의 유일한 문서 동작은 명시적인 기존 편집기 진입이다", () => {
  let edits = 0;
  const { default: Preview } = harness();
  const tree = Preview(props({ onEdit: () => edits++ }));
  const buttons = nodes(tree).filter((n) => n.type === "button");
  assert.equal(buttons.length, 1);
  assert.match(text(buttons[0]), /문서 열기/);
  assert.equal(edits, 0);
  buttons[0].props.onClick();
  assert.equal(edits, 1);
});
test("로딩·조회 오류는 이전 본문이나 편집 버튼을 표시하지 않고 오류 재시도만 제공한다", () => {
  const { default: Preview } = harness();
  const loading = Preview(props({ status: "loading" }));
  assert.ok(text(loading).includes("불러오고"));
  assert.equal(text(loading).includes(doc.title), false);
  let retry = 0;
  const error = Preview(
    props({ status: "error", error: "접근할 수 없어요", onRetry: () => retry++ }),
  );
  assert.match(text(error), /접근할 수 없어요/);
  assert.equal(text(error).includes(doc.title), false);
  nodes(error)
    .find((n) => n.type === "button")
    .props.onClick();
  assert.equal(retry, 1);
});
test("본문 없는 초안과 삭제/누락된 문서를 구별한다", () => {
  const { default: Preview } = harness();
  const empty = Preview(props({ document: { ...doc, status: "draft", sections: [] } }));
  assert.match(text(empty), /아직 작성된 본문이 없어요/);
  assert.match(text(empty), /검토 중/);
  const missing = Preview(props({ document: null }));
  assert.match(text(missing), /삭제되었거나/);
  assert.equal(text(missing).includes("편집하기"), false);
});
const target = (kind, id = 1) => ({
  kind,
  id,
  classId: 3,
  className: "햇살반",
  title: `${kind} 실제 제목`,
  period: "2026-10",
  createdAt: "2026-10-19T00:00:00Z",
  href: `/plans/${kind}/${id}`,
});
const annual = (id = 1) => ({
  id,
  class_id: 3,
  status: "DRAFT",
  months: [{ month: 10, theme: `실제 주제 ${id}`, sub_themes: ["실제 소주제"] }],
});
test("연간 계획안은 기존 GET의 실제 월·주제·소주제를 표시하고 기존 ID 링크를 유지한다", async () => {
  const calls = [];
  const h = harness(async (kind, id) => {
    calls.push([kind, id]);
    return annual(id);
  });
  const t = target("annual");
  h.render(t);
  await settle();
  const tree = h.render(t);
  assert.match(text(tree), /실제 주제 1/);
  assert.match(text(tree), /실제 소주제/);
  assert.equal(nodes(tree).find((n) => n.type === "link").props.href, t.href);
  assert.deepEqual(calls, [["annual", 1]]);
  h.unmount();
});
test("놀이 프로젝트형 연간 미리보기는 선택된 후보만 표시하고 기존 문서 링크를 유지한다", async () => {
  const h = harness(async () => ({
    id: 1,
    class_id: 3,
    format: "PLAY_PROJECT",
    status: "CONFIRMED",
    periods: [
      {
        label: "가을 놀이",
        selected: ["chosen"],
        candidates: [
          {
            row_key: "chosen",
            play_name: { value: "낙엽 놀이" },
            materials: { value: "낙엽" },
            support_direction: { value: "자료를 준비한다" },
            learning: { value: "모양을 비교한다" },
          },
          { row_key: "unselected", play_name: { value: "선택하지 않은 놀이" } },
        ],
      },
    ],
  }));
  const t = target("annual");
  h.render(t);
  await settle();
  const tree = h.render(t);
  assert.match(text(tree), /가을 놀이 · 낙엽 놀이/);
  assert.match(text(tree), /자료를 준비한다/);
  assert.match(text(tree), /모양을 비교한다/);
  assert.equal(text(tree).includes("선택하지 않은 놀이"), false);
  assert.equal(nodes(tree).find((n) => n.type === "link").props.href, t.href);
  h.unmount();
});

for (const kind of ["monthly", "weekly"])
  test(`${kind} 계획안은 서버의 보이는 CONTENT 값만 표시한다`, async () => {
    const h = harness(async () => ({
      id: 1,
      class_id: 3,
      status: "CONFIRMED",
      sections: [
        {
          label: "실제 항목",
          visible: true,
          role: "CONTENT",
          cells: [{ value: "교사가 저장한 실제 값", week_id: "2026-10-W1" }],
        },
        { label: "숨긴 항목", visible: false, role: "CONTENT", cells: [{ value: "숨긴 값" }] },
        { label: "축", visible: true, role: "AXIS", cells: [{ value: "축 값" }] },
      ],
    }));
    const t = target(kind);
    h.render(t);
    await settle();
    const tree = h.render(t);
    assert.match(text(tree), /교사가 저장한 실제 값/);
    assert.equal(text(tree).includes("숨긴 값"), false);
    assert.equal(text(tree).includes("축 값"), false);
    h.unmount();
  });
test("선택 변경 뒤 늦게 끝난 이전 계획안 GET은 새 미리보기를 덮지 않는다", async () => {
  const pending = new Map();
  const h = harness(
    (kind, id, signal) => new Promise((resolve) => pending.set(id, { resolve, signal })),
  );
  const a = target("annual", 1),
    b = target("annual", 2);
  h.render(a);
  h.render(b);
  assert.equal(pending.get(1).signal.aborted, true);
  pending.get(2).resolve(annual(2));
  await settle();
  assert.match(text(h.render(b)), /실제 주제 2/);
  pending.get(1).resolve(annual(1));
  await settle();
  const rendered = text(h.render(b));
  assert.match(rendered, /실제 주제 2/);
  assert.equal(rendered.includes("실제 주제 1"), false);
  h.unmount();
});
test("다른 반의 계획안 응답은 본문으로 표시하지 않으며 오류 재시도로 다시 GET한다", async () => {
  let calls = 0;
  const h = harness(async () => {
    calls++;
    return { ...annual(), class_id: calls === 1 ? 9 : 3 };
  });
  const t = target("annual");
  h.render(t);
  await settle();
  let tree = h.render(t);
  assert.match(text(tree), /선택한 반의 문서가 아니에요/);
  assert.equal(text(tree).includes("실제 주제"), false);
  nodes(tree)
    .find((n) => n.type === "button")
    .props.onClick();
  h.render(t);
  await settle();
  tree = h.render(t);
  assert.match(text(tree), /실제 주제 1/);
  assert.equal(calls, 2);
  h.unmount();
});
test("계획안 진입 주소는 문서 ID·반·달/서버 주차를 검증하고 잘못된 주소는 무시한다", () => {
  assert.deepEqual(archivePlanEntry("?plan_id=9&class_id=3&month=2"), {
    id: 9,
    classId: 3,
    month: 2,
    weekId: "",
  });
  assert.deepEqual(archivePlanEntry("?plan_id=8&class_id=4&week_id=2027-01-W2"), {
    id: 8,
    classId: 4,
    month: 1,
    weekId: "2027-01-W2",
  });
  for (const q of [
    "",
    "?plan_id=-1&class_id=3&month=2",
    "?plan_id=2&class_id=4&month=13",
    "?plan_id=2&class_id=4&week_id=wrong",
  ])
    assert.equal(archivePlanEntry(q), null, q);
});
test("삭제는 onDeleted 가 있을 때만 · 확인을 거쳐 지우고 · 하위가 있으면 409 IN_USE 안내", async () => {
  const removed = [];
  let fail = null;
  const h = harness(
    async () => ({ ...annual(), status: "CONFIRMED" }),
    async (kind, id) => {
      removed.push([kind, id]);
      if (fail) throw fail;
    },
  );
  const t = target("annual");
  h.render(t);
  await settle();
  // 남의 반(보기 전용)은 onDeleted 를 넘기지 않는다 — 단추가 없다.
  assert.equal(
    nodes(h.render(t)).some((n) => n.type === "button" && text(n) === "삭제"),
    false,
  );
  let deleted = 0;
  const del = () =>
    nodes(h.render(t, () => deleted++)).find((n) => n.type === "button" && text(n) === "삭제");
  del().props.onClick();
  const ask = nodes(h.render(t, () => deleted++)).find((n) => n.type === "ask");
  assert.equal(ask.props.message, "이 계획안을 지울까요? 되돌릴 수 없어요.");
  fail = Object.assign(new Error("server"), { code: "IN_USE" });
  await ask.props.onYes();
  assert.match(text(h.render(t, () => deleted++)), /만든 월간계획안이 있어요/);
  assert.equal(deleted, 0);
  fail = null;
  del().props.onClick();
  await nodes(h.render(t, () => deleted++))
    .find((n) => n.type === "ask")
    .props.onYes();
  assert.equal(deleted, 1);
  assert.deepEqual(removed, [
    ["annual", 1],
    ["annual", 1],
  ]);
  h.unmount();
});
test("놀이 중심 월간은 놀이 월간 경로로 읽고 지운다", async () => {
  const removed = [];
  const h = harness(
    async (kind, id) => ({
      id,
      class_id: 3,
      status: "CONFIRMED",
      kind,
      theme: { value: "가을 숲 놀이" },
      rationale: { value: "낙엽에 관심" },
      together: [{ name: { value: "낙엽 모으기" }, description: { value: "함께 모은다" } }],
      free_play: [],
    }),
    async (kind, id) => removed.push([kind, id]),
  );
  const t = { ...target("monthly"), play: true };
  h.render(t);
  await settle();
  let deleted = 0;
  const tree = h.render(t, () => deleted++);
  assert.match(text(tree), /가을 숲 놀이/);
  assert.match(text(tree), /함께 하는 활동 · 낙엽 모으기/);
  nodes(tree)
    .find((n) => n.type === "button" && text(n) === "삭제")
    .props.onClick();
  await nodes(h.render(t, () => deleted++))
    .find((n) => n.type === "ask")
    .props.onYes();
  assert.deepEqual([removed, deleted], [[["play", 1]], 1]);
  h.unmount();
});
test("확정본은 내 반 미리보기에서 확정을 풀고 편집 화면으로 간다 · 초안 · 남의 반은 단추가 없다", async () => {
  const calls = [];
  const pushed = [];
  let status = "CONFIRMED";
  const h = harness(
    async (kind, id) => ({ id, class_id: 3, status, revision: 7, sections: [] }),
    async () => {},
    async (...args) => calls.push(args),
    pushed,
  );
  const t = target("weekly");
  h.render(t);
  await settle();
  const button = (onDeleted) =>
    nodes(h.render(t, onDeleted)).find((n) => n.type === "button" && text(n) === "수정하기");
  assert.equal(button(), undefined);
  await button(() => {}).props.onClick();
  assert.deepEqual([calls, pushed], [[["weekly", 1, 7]], ["/plans/weekly/1"]]);
  h.unmount();
  status = "DRAFT";
  const d = harness(async (kind, id) => ({ id, class_id: 3, status, revision: 7, sections: [] }));
  d.render(t);
  await settle();
  assert.equal(
    nodes(d.render(t, () => {})).some((n) => text(n) === "수정하기"),
    false,
  );
  d.unmount();
});
test("보육일지 사실은 왼쪽 시각 칸 · 세로줄을 따라 일과 이름 딱지와 함께 그리고, 이름표 없는 사실은 그대로 둔다", () => {
  const { default: Preview, factRows, phrases } = harness();
  const body =
    "[등원 및 자유놀이 09:00~09:30] 친구에게 같이 만들자고 말하며 블록을 나눠 주었다.\n" +
    "블록 세 개를 쌓은 뒤 “더 높이 만들래”라고 말했다.\n\n[바깥놀이] 모래를 팠다.";
  assert.deepEqual(factRows(body), [
    {
      name: "등원 및 자유놀이",
      time: "09:00 ~ 09:30",
      lines: [
        "친구에게 같이 만들자고 말하며 블록을 나눠 주었다.",
        "블록 세 개를 쌓은 뒤 “더 높이 만들래”라고 말했다.",
      ],
    },
    { name: "바깥놀이", time: "", lines: ["모래를 팠다."] },
  ]);
  assert.equal(factRows("블록을 쌓았다.\n\n[바깥놀이] 모래"), null);
  // 마디 안에서는 안 끊긴다 · 짧은 끝마디는 앞에 붙는다 · 「~라고 말했다」는 한 마디다.
  assert.deepEqual(phrases("모래에 물길을 파고 물이 어디로 가는지 따라가며 보았다."), [
    "모래에 물길을 파고",
    "물이 어디로 가는지 따라가며 보았다.",
  ]);
  assert.deepEqual(phrases("블록 세 개를 쌓은 뒤 “더 높이 만들래”라고 말했다."), [
    "블록 세 개를 쌓은 뒤",
    "“더 높이 만들래”라고 말했다.",
  ]);
  const tree = Preview(
    props({ document: { ...doc, kind: "dailyLog", sections: [{ heading: "사실", body }] } }),
  );
  assert.ok(text(tree).includes("09:00 ~ 09:30"));
  assert.equal(text(tree).includes("["), false);
  // 시간 줄 한 가지뿐 — 왼쪽 칸에 시각, 일과 이름은 딱지. 시안 고르던 주소(?factopt)는 없다.
  const name = nodes(tree).find((n) => n.props?.className === "factName");
  assert.equal(text(name), "등원 및 자유놀이");
  const clocks = nodes(tree).filter((n) => n.props?.className === "factClock");
  assert.deepEqual(clocks.map(text), ["09:00 ~ 09:30", ""]);
  assert.equal(source.includes("factopt"), false);
});

test("주간 보육일지 — 제목 옆에 주를 동그라미 치고 꼬리 기간을 떼며, 사실은 날짜별로 묶는다", () => {
  const { default: Preview, weekLabel, dayLabel, bareTitle, factDays, factRows } = harness();
  assert.equal(weekLabel("2026-11-09", "2026-11-15"), "11월 9일 ~ 15일");
  assert.equal(weekLabel("2026-11-30", "2026-12-06"), "11월 30일 ~ 12월 6일");
  assert.equal(weekLabel("2026-11-09", "2026-11-09"), "11월 9일");
  assert.equal(weekLabel("", "2026-11-15"), "");
  assert.equal(dayLabel("2026-11-09"), "11월 9일 (월)");
  assert.equal(dayLabel("2026-11-15"), "11월 15일 (일)");
  assert.equal(bareTitle("햇살반 주간 보육일지 (11월)"), "햇살반 주간 보육일지");
  assert.equal(bareTitle("햇살반 주간 보육일지 (11/30~12/6)"), "햇살반 주간 보육일지");
  assert.equal(bareTitle("우리 반 한 주 (놀이)"), "우리 반 한 주 (놀이)");

  // 근거 원문을 이은 사실 — 화요일 근거가 먼저 와도 날짜순. 같은 글의 줄은 근거 순서대로 하나씩 쓴다.
  const tue = "[점심 11:30~12:30] 골고루 먹었다.\n\n[바깥놀이 10:00~11:00] 모래를 팠다.";
  const mon = "[점심 11:30~12:30] 골고루 먹었다.";
  const body = `${tue}\n\n${mon}\n\n[낮잠] 고친 줄`;
  const sources = [
    { date: "2026-11-10", text: tue },
    { date: "2026-11-09", text: mon },
  ];
  const days = factDays(factRows(body), sources);
  assert.deepEqual(
    days.map((d) => [d.date, d.rows.map((r) => r.name)]),
    [
      ["2026-11-09", ["점심"]],
      ["2026-11-10", ["점심", "바깥놀이"]],
      ["", ["낮잠"]],
    ],
  );
  // 하루치뿐이면 머리글 없이 그대로.
  assert.equal(factDays(factRows(mon), [sources[1]]), null);
  assert.equal(factDays(factRows(mon), []), null);

  const weekly = {
    ...doc,
    kind: "weeklyLog",
    title: "햇살반 주간 보육일지 (11월)",
    start: "2026-11-09",
    end: "2026-11-15",
    sections: [{ heading: "사실", body, sourceIds: [] }],
    sources,
  };
  const tree = Preview(props({ document: weekly }));
  const title = nodes(tree).find((n) => n.type === "h2");
  assert.equal(text(title).replace(/\s+/g, " ").trim(), "햇살반 주간 보육일지 11월 9일 ~ 15일");
  assert.ok(nodes(title).some((n) => n.type === "circle-mark"));
  assert.deepEqual(
    nodes(tree)
      .filter((n) => n.props?.className === "factDayHead")
      .map(text),
    ["11월 9일 (월)", "11월 10일 (화)", "날짜 없음"],
  );
  // 일일 보육일지는 근거 날짜를 보지 않는다 — 머리글 없음.
  const daily = Preview(props({ document: { ...weekly, kind: "dailyLog" } }));
  assert.equal(
    nodes(daily).some((n) => n.props?.className === "factDayHead"),
    false,
  );
  assert.equal(text(nodes(daily).find((n) => n.type === "h2")), weekly.title);
});
