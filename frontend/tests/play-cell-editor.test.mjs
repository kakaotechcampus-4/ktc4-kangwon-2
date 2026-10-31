// 칸 입력창(ADR-044 §2): 1초 뒤 저장 · 떠날 때 즉시 저장 · 빈 칸과 600자 초과는 저장하지 않고 떠날 때 되돌림.
import assert from "node:assert/strict";
import { test } from "node:test";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const jsx = (type, props) => ({ type, props });
const path = "../components/plan-generator/PlayCellEditor.tsx";
const source = readFileSync(new URL(path, import.meta.url), "utf8");
const code = require("next/dist/compiled/babel/core").transformSync(source, {
  filename: fileURLToPath(new URL(path, import.meta.url)),
  babelrc: false,
  configFile: false,
  presets: [
    [require("next/dist/compiled/babel/preset-env"), { targets: { node: "current" } }],
    [require("next/dist/compiled/babel/preset-react"), { runtime: "automatic" }],
    require("next/dist/compiled/babel/preset-typescript"),
  ],
}).code;

function mount(value = "저장된 값", extra = {}) {
  const state = [];
  const refs = [];
  const effects = [];
  const cleanups = [];
  let cursor = 0;
  let refCursor = 0;
  const calls = { drafts: [], saves: [], reverts: 0 };
  const react = {
    useState: (initial) => {
      const index = cursor++;
      if (!(index in state)) state[index] = initial;
      return [state[index], (next) => (state[index] = next)];
    },
    useRef: (initial) => (refs[refCursor++] ??= { current: initial }),
    useEffect: (effect) => effects.push(effect),
  };
  const compiled = { exports: {} };
  new Function("require", "module", "exports", code)(
    (name) =>
      name === "react/jsx-runtime"
        ? { jsx, jsxs: jsx, Fragment: "fragment" }
        : name === "react"
          ? react
          : { __esModule: true, default: { muted: "muted" } },
    compiled,
    compiled.exports,
  );
  const props = {
    id: "cell",
    label: "놀이명",
    value,
    onDraft: (text) => calls.drafts.push(text),
    onSave: (text) => calls.saves.push(text),
    onRevert: () => calls.reverts++,
    ...extra,
  };
  const flat = (node) =>
    Array.isArray(node)
      ? node.flatMap(flat)
      : node && typeof node === "object"
        ? [node, ...flat(node.props?.children)]
        : [];
  const text = (node) =>
    Array.isArray(node)
      ? node.map(text).join("")
      : node && typeof node === "object"
        ? text(node.props?.children)
        : typeof node === "string" || typeof node === "number"
          ? String(node)
          : "";
  const render = () => {
    cursor = 0;
    refCursor = 0;
    effects.length = 0;
    const nodes = flat(compiled.exports.default(props));
    // 화면 반영 뒤 효과를 돌린다. 정리 함수는 빈 의존성 효과(처음 하나뿐)만 모은다.
    effects.forEach((effect) => {
      const cleanup = effect();
      if (typeof cleanup === "function" && cleanups.length === 0) cleanups.push(cleanup);
    });
    const area = nodes.find((node) => node.type === "textarea");
    const status = nodes.find((node) => node.props?.role === "status");
    const count = nodes.find((node) => node.props?.id === "cell-count");
    return { area, status: text(status), count: text(count) };
  };
  const type = (value) => {
    render().area.props.onChange({ target: { value } });
    return render();
  };
  const unmount = () => cleanups.splice(0).forEach((cleanup) => cleanup());
  return { calls, render, type, unmount, leave: () => render().area.props.onBlur() };
}

test("typing saves the trimmed value one second after the last keystroke", (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const view = mount();
  view.type("  새 이름  ");
  t.mock.timers.tick(999);
  assert.deepEqual(view.calls.saves, []);
  view.type("  새 이름 둘  ");
  t.mock.timers.tick(999); // 다시 쳤으니 처음부터 센다
  assert.deepEqual(view.calls.saves, []);
  t.mock.timers.tick(1);
  assert.deepEqual(view.calls.saves, ["새 이름 둘"]);
  assert.deepEqual(view.calls.drafts, ["  새 이름  ", "  새 이름 둘  "]);
});

test("leaving the field saves at once and cancels the waiting timer", (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const view = mount();
  view.type("바꾼 이름");
  view.leave();
  assert.deepEqual(view.calls.saves, ["바꾼 이름"]);
  t.mock.timers.tick(5000);
  assert.deepEqual(view.calls.saves, ["바꾼 이름"]);
  assert.equal(view.calls.reverts, 0);
});

test("a blank value is not saved, says so, and leaving restores the last saved value", (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const view = mount("저장된 값");
  assert.equal(view.type("   ").status, "비워 둘 수 없어요");
  t.mock.timers.tick(5000);
  assert.deepEqual(view.calls.saves, []);
  view.leave();
  assert.deepEqual(view.calls.saves, []);
  assert.equal(view.calls.reverts, 1);
  const after = view.render();
  assert.equal(after.area.props.value, "저장된 값");
  assert.equal(after.status, "");
});

test("over 600 characters is allowed to type, warned, never saved, and restored on leaving", (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const view = mount("저장된 값");
  const typed = view.type("가".repeat(612));
  assert.equal(typed.area.props.value.length, 612);
  assert.equal(typed.count, "612/600자 · 600자를 넘으면 저장되지 않아요");
  assert.equal(typed.status, "600자를 넘으면 저장되지 않아요");
  assert.equal(typed.area.props["aria-describedby"], "cell-count");
  t.mock.timers.tick(5000);
  assert.deepEqual(view.calls.saves, []);
  view.leave();
  assert.equal(view.calls.reverts, 1);
  assert.equal(view.render().area.props.value, "저장된 값");
  // 정확히 600자는 저장된다.
  view.type("가".repeat(600));
  view.leave();
  assert.deepEqual(view.calls.saves, ["가".repeat(600)]);
});

test("the character count ignores leading and trailing spaces", () => {
  const view = mount();
  assert.equal(view.render().count, "5/600자");
  assert.equal(view.type("  abc  ").count, "3/600자");
  assert.equal(view.type(" ".repeat(10) + "가".repeat(600) + " ".repeat(10)).count, "600/600자");
});

test("the editor is a labelled textarea", () => {
  const { area } = mount().render();
  assert.equal(area.props.id, "cell");
  assert.equal(area.props.readOnly, undefined);
});

test("characters are counted as code points like the server: 300 emoji are 300 and savable", (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const view = mount();
  assert.equal(view.type("😀".repeat(300)).count, "300/600자");
  assert.equal(view.type("😀".repeat(601)).count, "601/600자 · 600자를 넘으면 저장되지 않아요");
  view.type("😀".repeat(600));
  t.mock.timers.tick(1000);
  assert.equal(view.calls.saves.length, 1);
});

test("an editor that disappears without a blur saves a valid draft or reverts the preview", () => {
  const saved = mount();
  saved.type(" 사라지기 전 글 ");
  saved.unmount();
  assert.deepEqual(saved.calls.saves, ["사라지기 전 글"]);
  const blank = mount();
  blank.type("   ");
  blank.unmount();
  assert.deepEqual(blank.calls.saves, []);
  assert.equal(blank.calls.reverts, 1);
  const settled = mount();
  settled.type("글");
  settled.leave();
  settled.unmount();
  assert.deepEqual(settled.calls.saves, ["글"]); // 떠날 때 이미 보냈다 — 또 보내지 않는다
});

test("allowBlank saves a blank value after one second and on leaving, without the blank warning", (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const view = mount("저장된 값", { allowBlank: true });
  assert.equal(view.type("   ").status, "");
  t.mock.timers.tick(1000);
  assert.deepEqual(view.calls.saves, [""]);
  view.type("");
  view.leave();
  assert.deepEqual(view.calls.saves, ["", ""]);
  assert.equal(view.calls.reverts, 0);
  // 600자 넘으면 빈 값을 허용해도 저장하지 않는다.
  view.type("가".repeat(601));
  t.mock.timers.tick(5000);
  assert.equal(view.calls.saves.length, 2);
});

test("maxLength Infinity (월간 v1) saves over 600 characters and shows no limit", (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const view = mount("저장된 값", { allowBlank: true, maxLength: Infinity });
  assert.equal(view.type("가".repeat(601)).count, "601자");
  view.leave();
  assert.deepEqual(view.calls.saves, ["가".repeat(601)]);
  assert.equal(view.calls.reverts, 0);
});
