// 일일 보육일지 칠판 편집기(DailyJournalBoard) — 사실 쪽지 · 근거 몇 건 · 지우기 하나 · AI 검증 끝 표시.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import test from "node:test";

const require = createRequire(import.meta.url);
const { serverIssues } = await import("../components/workspace/document-selection.ts");

const code = require("next/dist/compiled/babel/core").transformSync(
  readFileSync(new URL("../components/workspace/DailyJournalBoard.tsx", import.meta.url), "utf8"),
  {
    filename: "DailyJournalBoard.tsx",
    babelrc: false,
    configFile: false,
    presets: [
      [require("next/dist/compiled/babel/preset-env"), { targets: { node: "current" } }],
      [require("next/dist/compiled/babel/preset-react"), { runtime: "automatic" }],
      require("next/dist/compiled/babel/preset-typescript"),
    ],
  },
).code;

/** 훅 자리를 차례로 기억하는 아주 작은 React. 다시 그리면 같은 자리의 값을 돌려준다. */
function harness(props) {
  const slots = [];
  let cursor = 0;
  const state = (initial) => {
    const slot = cursor++;
    if (!(slot in slots)) slots[slot] = typeof initial === "function" ? initial() : initial;
    return [
      slots[slot],
      (next) => (slots[slot] = typeof next === "function" ? next(slots[slot]) : next),
    ];
  };
  const jsx = (type, p, key) => ({ type, props: p, key });
  const modules = {
    react: {
      useState: state,
      useRef: (initial) => state(() => ({ current: initial }))[0],
      useEffect: () => {},
    },
    "react/jsx-runtime": { jsx, jsxs: jsx, Fragment: "fragment" },
    "@/lib/api/documents": { downloadDocumentHwpx: async () => {}, isStaleWrite: () => false },
    "@/lib/api/client": { invalidFields: () => [] },
    "@/lib/hooks/use-hwpx-download": {
      useHwpxDownload: () => ({ exporting: false, download: async () => {} }),
    },
    "@/components/app/icons": { Icon: "icon" },
    "@/components/app/Posty": { Posty: "posty" },
    "./WorkspaceUI": { Message: "message", ws: {} },
    "./document-selection": { serverIssues },
    "./WorkspaceViewState": { FieldError: "field-error", fieldErrorProps: () => ({}) },
    "./RoutineClock": { clockText: (s, e) => `${s} ~ ${e}` },
    "./SourceReview": { __esModule: true, default: "source-review" },
    "./DailyJournal.module.css": { __esModule: true, default: {} },
  };
  const mod = { exports: {} };
  new Function("require", "module", "exports", code)(
    (name) => {
      assert.ok(name in modules, `unhandled import: ${name}`);
      return modules[name];
    },
    mod,
    mod.exports,
  );
  // 함수 컴포넌트(VerifyBox · Flags …)는 그 자리에서 펼친다 — 화면 글자를 끝까지 본다.
  const expand = (node) => {
    if (Array.isArray(node)) return node.map(expand);
    if (!node || typeof node !== "object") return node;
    if (typeof node.type === "function") return expand(node.type(node.props));
    return { ...node, props: { ...node.props, children: expand(node.props?.children) } };
  };
  let tree;
  const render = () => {
    cursor = 0;
    tree = expand(mod.exports.default(props));
  };
  const all = (node) => {
    if (!node || typeof node !== "object") return [];
    if (Array.isArray(node)) return node.flatMap(all);
    return [node, ...all(node.props?.children)];
  };
  const text = (node) => {
    if (Array.isArray(node)) return node.map(text).join("");
    if (node && typeof node === "object") return text(node.props?.children);
    return typeof node === "string" || typeof node === "number" ? String(node) : "";
  };
  render();
  return {
    factNotes: mod.exports.factNotes,
    render,
    text: () => text(tree),
    buttons: (label) => all(tree).filter((n) => n.type === "button" && text(n).trim() === label),
    button: (label) => all(tree).find((n) => n.type === "button" && text(n).trim() === label),
    checkbox: () => all(tree).find((n) => n.type === "input" && n.props.type === "checkbox"),
    notes: () => all(tree).filter((n) => n.type === "li" && "data-tone" in n.props),
  };
}

const FACT = [
  "[등원 및 자유놀이 09:00~09:30] 블록 바구니를 꺼내 탑을 쌓았다.",
  "[오전 실내놀이 09:30~10:40] 긴 다리를 만들었다.",
  "자유롭게 적은 한 줄",
].join("\n");
const DOC = {
  id: "document:9",
  kind: "dailyLog",
  title: "햇살반 보육일지 (11/10)",
  className: "햇살반",
  status: "draft",
  origin: "ai",
  start: "2026-11-10",
  end: "2026-11-10",
  classNote: "",
  sources: [{ id: "routine:1" }, { id: "routine:2" }, { id: "routine:3" }],
  sections: [
    { heading: "사실", body: FACT, sourceIds: [] },
    {
      heading: "해석",
      body: "친구와 함께 만들기를 제안하며 놀이를 넓혔다. 매일 블록을 쌓는다.",
      sourceIds: [],
    },
    {
      heading: "지원",
      body: "큰 블록을 더 두어 함께 쌓을 자리를 넓게 만들어 준다.",
      sourceIds: [],
    },
  ],
};
const tick = () => new Promise((r) => setImmediate(r));

function board(verifyResult = { issues: [], judged: true }) {
  const calls = [];
  const server = {
    stale: false,
    pending: false,
    verify: async (sections) => {
      calls.push(["verify", sections.length]);
      return verifyResult;
    },
    saveAndConfirm: async (sections) => {
      calls.push(["confirm"]);
      return { ...DOC, sections, status: "confirmed" };
    },
    remove: async () => calls.push(["remove"]),
  };
  return { view: harness({ initial: DOC, server }), calls };
}

test("사실 한 줄을 이름 · 시간 · 글로 가르고, 모양이 다른 줄은 글로 남긴다", () => {
  const { view } = board();
  assert.deepEqual(view.factNotes(FACT), [
    {
      name: "등원 및 자유놀이",
      start: "09:00",
      end: "09:30",
      text: "블록 바구니를 꺼내 탑을 쌓았다.",
    },
    { name: "오전 실내놀이", start: "09:30", end: "10:40", text: "긴 다리를 만들었다." },
    { name: "", start: "", end: "", text: "자유롭게 적은 한 줄" },
  ]);
  assert.deepEqual(view.factNotes("[점심 12:00~] 먹었다")[0], {
    name: "점심",
    start: "12:00",
    end: "",
    text: "먹었다",
  });
});

test("초안은 일과마다 쪽지 한 장, 근거는 「근거 3건」 한 번, 지우기 단추는 하나다", () => {
  const { view } = board();
  assert.equal(view.notes().length, 3);
  assert.match(view.text(), /근거 3건/);
  assert.doesNotMatch(view.text(), /근거:/, "날짜를 줄마다 되풀이하지 않는다");
  assert.equal(view.buttons("일지 삭제").length, 1);
});

test("AI 검증이 끝나면 「AI 검증 끝」과 걸린 문장 수를, 없으면 「문제 없음」을 보인다", async () => {
  const flagged = board({
    issues: [
      {
        heading: "해석",
        sentence: "매일 블록을 쌓는다.",
        reason: "기록에 없어요.",
        fix: "",
        sourceText: null,
      },
    ],
    judged: true,
  });
  assert.doesNotMatch(flagged.view.text(), /AI 검증 끝/);
  flagged.view.button("AI 검증하기").props.onClick();
  await tick();
  flagged.view.render();
  assert.match(flagged.view.text(), /AI 검증 끝/);
  assert.match(flagged.view.text(), /확인할 문장 1개/);
  assert.match(flagged.view.text(), /매일 블록을 쌓는다\./, "걸린 문장을 공책 아래에 짚는다");
  assert.ok(flagged.view.button("다시 검증하기"));

  const clean = board();
  clean.view.button("AI 검증하기").props.onClick();
  await tick();
  clean.view.render();
  assert.match(clean.view.text(), /AI 검증 끝/);
  assert.match(clean.view.text(), /문제 없음/);
});

test("확정 도장은 대조 체크 뒤에만 눌리고, 누르면 저장과 확정을 한 번에 보낸다", async () => {
  const { view, calls } = board();
  const stamp = () => view.button("확정");
  assert.equal(stamp().props.disabled, true);
  view.checkbox().props.onChange({ target: { checked: true } });
  view.render();
  assert.equal(stamp().props.disabled, false);
  await stamp().props.onClick();
  view.render();
  assert.deepEqual(calls, [["confirm"]]);
  assert.match(view.text(), /검토한 문서를 확정했어요/);
  assert.ok(view.button("다시 수정"));
  assert.equal(view.buttons("일지 삭제").length, 0, "확정본은 지울 수 없다 — 확정 취소가 먼저다");
});

test("휴대폰 한 장은 안쪽 대화상자(근거 반영 확인)의 닫힘 · 취소를 제 것으로 받지 않는다", () => {
  const card = readFileSync(
    new URL("../components/workspace/DailyJournalCard.tsx", import.meta.url),
    "utf8",
  );
  const sheet = card.slice(card.indexOf("function JournalSheet"));
  // React 는 안쪽 <dialog> 의 cancel · close 를 바깥 <dialog> 처리기까지 올린다.
  // 거르지 않으면 「취소」만 눌러도 한 장이 닫히고 저장 안 한 글이 사라졌다.
  assert.match(sheet, /onCancel=\{\(e\) => \{\s*if \(e\.target !== e\.currentTarget\) return;/);
  assert.match(sheet, /onClose=\{\(e\) => \{\s*if \(e\.target !== e\.currentTarget\) return;/);
});
