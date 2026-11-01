// 월별 주제형 다듬기(ThemeAnnualResult)의 저장 · 확정 순서(PUI-02 · PUI-03).
// 실제 컴포넌트를 Babel 로 바꿔 React hook · API 대역으로 돌린다.
import assert from "node:assert/strict";
import fs from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";
import test from "node:test";

const frontend = path.resolve(import.meta.dirname, "..");
const require = createRequire(path.join(frontend, "package.json"));
const babel = require("next/dist/compiled/babel/core");
const jsx = (type, props) => ({ type, props });
const runtime = { jsx, jsxs: jsx, Fragment: "fragment" };
const es = (value) => ({ __esModule: true, default: value });

function compile(relative, modules) {
  const filename = path.join(frontend, relative);
  const { code } = babel.transformSync(fs.readFileSync(filename, "utf8"), {
    filename,
    babelrc: false,
    configFile: false,
    presets: [
      [require("next/dist/compiled/babel/preset-env"), { targets: { node: "current" } }],
      [require("next/dist/compiled/babel/preset-react"), { runtime: "automatic" }],
      require("next/dist/compiled/babel/preset-typescript"),
    ],
  });
  const mod = { exports: {} };
  new Function("require", "module", "exports", "document", code)(
    (name) => (name === "react/jsx-runtime" ? runtime : modules[name]),
    mod,
    mod.exports,
    { activeElement: null, getElementById: () => null },
  );
  return mod.exports;
}

const nodes = (value) =>
  Array.isArray(value)
    ? value.flatMap(nodes)
    : !value || typeof value !== "object"
      ? []
      : typeof value.type === "function"
        ? nodes(value.type(value.props))
        : [value, ...nodes(value.props?.children)];
const settle = async () => {
  for (let i = 0; i < 5; i++) await new Promise(setImmediate);
};
const slotsModule = compile("lib/plan-generator/subThemeSlots.ts", {});

function harness(send) {
  const slots = [];
  let index = 0;
  const events = [];
  const react = {
    useState(init) {
      const k = index++;
      if (!(k in slots)) slots[k] = typeof init === "function" ? init() : init;
      return [slots[k], (v) => (slots[k] = typeof v === "function" ? v(slots[k]) : v)];
    },
    useRef(init) {
      return (slots[index++] ??= { current: init });
    },
    useEffect() {},
  };
  const months = [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2];
  const plan = {
    id: 1,
    school_year: 2026,
    status: "DRAFT",
    months: months.map((month) => ({
      month,
      theme: `${month}월 원래`,
      week_count: 4,
      sub_themes: ["a", "b", "c", "d"],
    })),
  };
  const apis = {
    putAnnualMonth: async (_id, month, body) => {
      await send(month, body);
      events.push("write:" + body.theme);
    },
    confirmAnnualPlan: async () => events.push("confirm"),
    getAnnualPlan: async () => plan,
    isSaveConflict: () => false,
    isRejectedSave: () => false,
    errorFields: () => [],
  };
  const Frame = (p) => jsx("frame", { children: [p.actions, p.notice, p.aside, p.children] });
  const { default: Result } = compile("components/plan-generator/ThemeAnnualResult.tsx", {
    react,
    "@/lib/api/plans": apis,
    "@/lib/plan-generator/subThemeSlots": slotsModule,
    "./AnnualFrame": {
      ...es(Frame),
      AsideStrip: (p) => jsx("strip", p),
      BUTTON: {},
      tabClass: () => "",
    },
    "./AnnualThemeSheet": es((p) => jsx("sheet", p)),
    "./PlayMonthlyConfirm": es((p) => jsx("dialog", p)),
  });
  const render = () => {
    index = 0;
    return nodes(
      jsx(Result, { plan, className: "", onConflict: async () => {}, onConfirmed() {} }),
    );
  };
  const input = () => render().find((n) => n.type === "input");
  const edit = async (value) => {
    input().props.onChange({ target: { value } });
    input().props.onBlur();
    await settle();
  };
  const confirm = () => {
    render()
      .find((n) => n.type === "button" && n.props.children === "확정하기")
      .props.onClick();
    return render()
      .find((n) => n.type === "dialog")
      .props.onYes();
  };
  const alert = () => render().find((n) => n.props?.role === "alert")?.props.children ?? "";
  return { render, input, edit, confirm, alert, events };
}

test("a later month's save does not clear an earlier failure, and confirm stops on it", async () => {
  const view = harness(async (month) => {
    if (month === 3) throw new Error("network");
  });
  await view.edit("3월 고침");
  view
    .render()
    .find((n) => n.type === "sheet")
    .props.onSelect({ month: 4, slot: "theme" });
  await view.edit("4월 고침");
  assert.ok(view.render().some((n) => n.type === "button" && n.props.children === "다시 저장"));
  await view.confirm();
  assert.ok(!view.events.includes("confirm"));
  assert.match(view.alert(), /3월은 아직 저장되지 않았어요/);
});

test("a blank theme blocks confirm instead of confirming the old server theme", async () => {
  const view = harness(async () => {});
  await view.edit("");
  await view.confirm();
  assert.deepEqual(view.events, []);
  assert.match(view.alert(), /3월은 아직 저장되지 않았어요/);
});

test("confirm waits for queued saves and locks edits made while it waits", async () => {
  let release;
  const held = new Promise((resolve) => (release = resolve));
  const view = harness((_month, body) => (body.theme === "B" ? held : undefined));
  await view.edit("B");
  const confirming = view.confirm();
  assert.equal(view.input().props.readOnly, true);
  await view.edit("C");
  release();
  await confirming;
  await settle();
  assert.deepEqual(view.events, ["write:B", "confirm"]);
});

test("two failed saves in a row do not count as saved; retyping the first value sends it again", async () => {
  let fail;
  const firstHeld = new Promise((_, reject) => (fail = reject));
  let online = false;
  const view = harness((_month, body) => {
    if (body.theme === "B" && !online) return firstHeld;
    if (!online) throw new Error("network");
  });
  await view.edit("B");
  await view.edit("C");
  fail(new Error("network"));
  await settle();
  online = true;
  await view.edit("B");
  await view.confirm();
  assert.deepEqual(view.events, ["write:B", "confirm"]);
});

test("an earlier failed save does not hide a later one; going back to the old value saves again", async () => {
  let fail;
  const held = new Promise((_, reject) => (fail = reject));
  const view = harness((_month, body) => (body.theme === "B" ? held : undefined));
  await view.edit("B");
  await view.edit("C");
  fail(new Error("network"));
  await settle();
  await view.edit("3월 원래");
  await view.confirm();
  assert.deepEqual(view.events, ["write:C", "write:3월 원래", "confirm"]);
});
