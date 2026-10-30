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
    "@/lib/workspace/model": model,
    "@/lib/api/plans": { getAnnualPlan: (id, signal) => gateway("annual", id, signal) },
    "@/lib/api/monthly": { getMonthlyPlan: (id, signal) => gateway("monthly", id, signal) },
    "@/lib/api/weekly": { getWeeklyPlan: (id, signal) => gateway("weekly", id, signal) },
    "./WorkspaceUI": { ws: {} },
    "./DocumentArchive.module.css": { __esModule: true, default: {} },
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
    render(target) {
      cursor = 0;
      tree = m.exports.PlanArchivePreview({ target });
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
