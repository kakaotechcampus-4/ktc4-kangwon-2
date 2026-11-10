/**
 * 관찰 기록 · 관찰일지 화면. 실제 TSX 를 React 흉내 위에서 돌려 이벤트와 state 를 본다
 * (documents-server.test.mjs 의 편집기 시험과 같은 방식). 브라우저 E2E 는 아니다.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire, registerHooks } from "node:module";
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

registerHooks({
  resolve(spec, ctx, next) {
    if (spec.startsWith("@/")) {
      const u = new URL("../" + spec.slice(2) + ".ts", import.meta.url);
      if (existsSync(fileURLToPath(u))) return { url: u.href, shortCircuit: true };
    }
    if (spec.startsWith(".") && ctx.parentURL) {
      const u = new URL(spec + ".ts", ctx.parentURL);
      if (existsSync(fileURLToPath(u))) return { url: u.href, shortCircuit: true };
    }
    return next(spec, ctx);
  },
});

const documents = await import("../lib/api/documents.ts");
const axis = await import("../lib/workspace/observation-axis.ts");
const recordContext = await import("../lib/workspace/record-context.ts");
const { ApiError, invalidFields } = await import("../lib/api/client.ts");

const require = createRequire(import.meta.url);
const jsx = (type, props, key) => ({ type, props, key });
const runtime = { jsx, jsxs: jsx, Fragment: "fragment" };
function compile(path, modules) {
  const code = require("next/dist/compiled/babel/core").transformSync(
    readFileSync(new URL(path, import.meta.url), "utf8"),
    {
      filename: path,
      babelrc: false,
      configFile: false,
      presets: [
        [require("next/dist/compiled/babel/preset-env"), { targets: { node: "current" } }],
        [require("next/dist/compiled/babel/preset-react"), { runtime: "automatic" }],
        require("next/dist/compiled/babel/preset-typescript"),
      ],
    },
  ).code;
  const out = { exports: {} };
  new Function("require", "module", "exports", code)(
    (name) => {
      assert.ok(name in modules, `unhandled import: ${name}`);
      return modules[name];
    },
    out,
    out.exports,
  );
  return out.exports;
}

const all = (node) => {
  if (Array.isArray(node)) return node.flatMap(all);
  if (node === null || node === undefined || typeof node === "boolean") return [];
  return typeof node === "object" ? [node, ...all(node.props?.children)] : [node];
};
const textOf = (node) =>
  all(node)
    .filter((part) => typeof part === "string" || typeof part === "number")
    .join("");

/** React 흉내 — hook 자리를 컴포넌트 경로 + key 로 나누고, 함수 컴포넌트를 펼친다. */
function host() {
  const boxes = new Map();
  const effects = new Map();
  const queue = [];
  let scope = "";
  const box = () => {
    if (!boxes.has(scope)) boxes.set(scope, { slots: [], cursor: 0 });
    return boxes.get(scope);
  };
  const useState = (initial) => {
    const b = box();
    const i = b.cursor++;
    if (!(i in b.slots)) b.slots[i] = typeof initial === "function" ? initial() : initial;
    return [
      b.slots[i],
      (next) => (b.slots[i] = typeof next === "function" ? next(b.slots[i]) : next),
    ];
  };
  const useEffect = (fn, deps) => {
    const key = `${scope}#${box().cursor++}`;
    const prev = effects.get(key);
    if (prev && deps && deps.every((d, i) => Object.is(d, prev.deps[i]))) return;
    const next = { deps };
    effects.set(key, next);
    queue.push(() => {
      prev?.cleanup?.();
      next.cleanup = fn();
    });
  };
  const react = {
    useState,
    useEffect,
    useMemo: (fn) => fn(),
    useRef: (current) => useState(() => ({ current }))[0],
  };
  const resolve = (node, path) => {
    if (Array.isArray(node)) return node.map((n) => resolve(n, path));
    if (!node || typeof node !== "object") return node;
    if (typeof node.type === "function") {
      const outer = scope;
      scope = `${path}/${node.type.name}#${node.key ?? ""}`;
      box().cursor = 0;
      const out = node.type(node.props);
      const id = scope;
      scope = outer;
      return resolve(out, id);
    }
    return { ...node, props: { ...node.props, children: resolve(node.props?.children, path) } };
  };
  return {
    react,
    mount(Page, props = {}) {
      let tree;
      const render = () => {
        scope = "";
        box().cursor = 0;
        tree = resolve(Page(props), "");
      };
      const nodes = () => all(tree).filter((n) => typeof n === "object");
      const button = (label) =>
        nodes().find((n) => n.type === "button" && textOf(n.props.children) === label);
      render();
      return {
        render,
        nodes,
        button,
        text: () => textOf(tree),
        async flush() {
          for (let i = 0; i < 4; i++) {
            render();
            queue.splice(0).forEach((fn) => fn());
            await new Promise((r) => setImmediate(r));
          }
          render();
        },
        async press(label) {
          const found = button(label);
          assert.ok(found, `button: ${label}`);
          await found.props.onClick({ preventDefault() {} });
          render();
        },
        type(node, value) {
          node.props.onChange({ target: { value } });
          render();
        },
      };
    },
  };
}

const TODAY = "2026-11-09";
const DOMAINS = ["신체운동·건강", "의사소통", "사회관계", "예술경험", "자연탐구"];
const ROOMS = [
  {
    id: "class-a",
    name: "햇살반",
    children: [
      { id: "kid-1", name: "김하늘" },
      { id: "kid-2", name: "박서아" },
    ],
  },
  { id: "class-b", name: "별빛반", children: [{ id: "kid-9", name: "이달" }] },
];
const RECORD = {
  id: "observation:1",
  classId: "class-a",
  childId: "kid-2",
  childName: "박서아",
  date: "2026-11-02",
  domain: "자연탐구",
  context: "바깥놀이",
  fact: "개미를 오래 보았다.",
};
const common = (react) => ({
  "react/jsx-runtime": runtime,
  react,
  "next/link": { __esModule: true, default: "link" },
  "@/lib/workspace/model": { today: () => TODAY, validDate: (v) => /^\d{4}-\d{2}-\d{2}$/.test(v) },
  "@/lib/hooks/use-client-state": { useClientState: (read) => react.useState(read) },
  "@/lib/hooks/use-observation-domains": { useObservationDomains: () => DOMAINS },
  "@/lib/onboarding/settings": {
    chosenClassFor: () => ({ id: "class-a" }),
    loadClassSettings: () => ({}),
  },
  "@/components/app/Posty": { Posty: "posty" },
  "@/components/app/ChildPicker": { ChildNote: "child-note" },
  "@/components/app/icons": { Icon: "icon" },
  "@/lib/workspace/domain-look": { DOMAIN_LOOK: {} },
  "./ObservationJournal.module.css": { __esModule: true, default: {} },
});
function browser(t, search = "") {
  globalThis.window = {
    location: { search },
    scrollTo() {},
    history: { pushState() {}, back() {} },
    addEventListener() {},
    removeEventListener() {},
  };
  globalThis.document = { addEventListener() {}, removeEventListener() {} };
  t.after(() => {
    delete globalThis.window;
    delete globalThis.document;
  });
}

// ── 관찰 기록 (RecordsPage) ────────────────────────────────────────────────

const NO_IMPACT = { affected: [], newlyStale: [] };

function recordsPage(t, api = {}, { now = "08:00" } = {}) {
  browser(t);
  const app = host();
  const warned = [];
  const Page = compile("../components/workspace/RecordsPage.tsx", {
    ...common(app.react),
    "@/lib/hooks/use-unsaved-warning": { useUnsavedWarning: (on) => warned.push(on) },
    "@/lib/api/client": { isUnauthenticated: () => false, invalidFields },
    "@/lib/api/records": {
      listRecords: async () => [RECORD],
      addRecord: async () => ({}),
      editRecord: async () => ({ record: {}, impact: NO_IMPACT }),
      removeRecord: async () => NO_IMPACT,
      suggestRecordDomain: async () => null,
      missingInRecord: async () => [],
      dayRoutines: async () => [],
      ...api,
    },
    "@/lib/workspace/record-context": { ...recordContext, nowTime: () => now },
    "@/lib/api/documents": { documentLocalId: (id) => `document:${id}` },
    "@/lib/workspace/child-mark": { markFor: () => 0 },
    "./WorkspaceUI": {
      WorkspacePage: "page",
      Empty: "empty",
      Message: "message",
      useClasses: () => ROOMS,
      ws: {},
    },
    "./WorkspaceViewState": {
      WorkspaceViewState: "view-state",
      FieldError: "field-error",
      fieldErrorProps: () => ({}),
    },
  }).default;
  const view = app.mount(Page);
  const fact = () => view.nodes().find((n) => n.props["aria-label"] === "본 대로 적기");
  const date = () => view.nodes().find((n) => n.props["aria-label"] === "날짜");
  const pickedDomain = () =>
    view.nodes().find((n) => n.props["aria-pressed"] === true && DOMAINS.includes(textOf(n)));
  /** 쌓인 기록 카드를 펼친다. */
  const open = () => {
    view
      .nodes()
      .find((n) => n.props["aria-expanded"] !== undefined && textOf(n).includes(RECORD.fact))
      .props.onClick();
    view.render();
  };
  const links = () => view.nodes().filter((n) => n.type === "link");
  return { ...view, warned, fact, date, pickedDomain, open, links };
}

test("F1 「그만두기」는 고치기 전 날짜 · 영역 · 아이로 되돌린다", async (t) => {
  const view = recordsPage(t);
  await view.flush();
  view.type(view.date(), "2026-11-05");
  await view.press("의사소통");
  await view.press("김하늘");
  view.open();
  await view.press("고치기");
  assert.equal(view.date().props.value, RECORD.date);
  assert.equal(textOf(view.pickedDomain()), RECORD.domain);

  await view.press("그만두기");
  assert.equal(view.date().props.value, "2026-11-05");
  assert.equal(textOf(view.pickedDomain()), "의사소통");
  assert.match(view.text(), /하늘이가/);
  assert.equal(view.fact().props.value, "");
});

test("F2 적던 글이 있으면 고치기 전에 화면 안에서 묻고, 버리기로 해야 덮는다", async (t) => {
  const view = recordsPage(t);
  await view.flush();
  view.type(view.fact(), "적던 새 글");
  view.open();
  // window.confirm 은 없다 — 부르면 여기서 터진다.
  await view.press("고치기");
  assert.equal(view.fact().props.value, "적던 새 글");
  assert.ok(view.button("버리고 고치기"));

  await view.press("계속 쓰기");
  assert.equal(view.button("버리고 고치기"), undefined);
  assert.equal(view.fact().props.value, "적던 새 글");

  await view.press("고치기");
  await view.press("버리고 고치기");
  assert.equal(view.fact().props.value, RECORD.fact);
});

/**
 * 화면을 떠나는 누르기를 흉내 낸다. 화면이 document 에 건 캡처 단계 click 을 붙잡아 둔다.
 * `go(href)` 는 그 링크를 누른 것이고, 화면이 다시 누르면 `clicked` 에 남는다.
 */
function leaving() {
  const listeners = [];
  globalThis.document.addEventListener = (type, fn) => type === "click" && listeners.push(fn);
  globalThis.document.removeEventListener = (type, fn) => {
    const i = listeners.indexOf(fn);
    if (i >= 0) listeners.splice(i, 1);
  };
  const clicked = [];
  return {
    clicked,
    /** 링크를 누른다. 화면이 막았으면 true. */
    go(href) {
      const anchor = {
        getAttribute: () => href,
        closest: () => null,
        click() {
          clicked.push(href);
          // 화면이 다시 누른 것도 같은 손잡이를 지난다 — 이번엔 막으면 안 된다.
          for (const fn of [...listeners]) fn(event(anchor));
        },
      };
      let stopped = false;
      const event = (target) => ({
        button: 0,
        defaultPrevented: false,
        target: { closest: () => target },
        preventDefault: () => (stopped = true),
        stopPropagation() {},
      });
      for (const fn of [...listeners]) fn(event(anchor));
      return stopped;
    },
  };
}

test("A1 적은 게 없으면 그냥 떠나고, 적던 글이 있으면 브라우저 경고를 건다", async (t) => {
  const view = recordsPage(t);
  const leave = leaving();
  await view.flush();
  assert.equal(view.warned.at(-1), false);
  assert.equal(leave.go("/routines"), false);

  view.type(view.fact(), "적던 새 글");
  await view.flush();
  assert.equal(view.warned.at(-1), true);
});

test("A1 아이 · 영역을 골랐으면 떠날 때 저장하고 이동하며 머리줄에 「저장됨」", async (t) => {
  const saved = [];
  const view = recordsPage(t, {
    addRecord: async (body) => (saved.push(body), { ...RECORD, id: "observation:9" }),
  });
  const leave = leaving();
  await view.flush();
  await view.press("김하늘");
  await view.press("사회관계");
  view.type(view.fact(), "블록 세 개를 쌓았다.");
  await view.flush();

  assert.equal(leave.go("/routines"), true, "저장 전에 먼저 떠나지 않는다");
  await view.flush();
  assert.equal(saved.length, 1);
  assert.equal(saved[0].domain, "사회관계");
  assert.deepEqual(leave.clicked, ["/routines"]);
  assert.match(view.text(), /저장됨/);
});

test("A1 떠나며 저장하는 중 다른 링크를 눌러도 떠나지 않고, 저장이 실패하면 글이 남는다 (#487 하민 점검)", async (t) => {
  let fail;
  const saved = [];
  const view = recordsPage(t, {
    addRecord: (body) => (
      saved.push(body),
      new Promise((_, reject) => {
        fail = reject;
      })
    ),
  });
  const leave = leaving();
  await view.flush();
  await view.press("김하늘");
  await view.press("사회관계");
  view.type(view.fact(), "블록 세 개를 쌓았다.");
  await view.flush();

  assert.equal(leave.go("/routines"), true);
  await view.flush();
  assert.equal(saved.length, 1);
  // 저장 응답 전에 두 번째 앱 링크를 누른다.
  assert.equal(leave.go("/documents"), true, "저장 중에도 이동을 붙잡는다");
  await view.flush();
  assert.equal(saved.length, 1, "두 번째 누르기가 저장을 또 보내지 않는다");

  fail(new Error("서버가 잠깐 못 받았어요."));
  await view.flush();
  assert.deepEqual(leave.clicked, []);
  assert.equal(view.fact().props.value, "블록 세 개를 쌓았다.");
});

test("A1 아이를 안 골랐으면 쪽지를 띄우고, 「버리고 이동」을 눌러야 떠난다", async (t) => {
  const saved = [];
  const view = recordsPage(t, { addRecord: async (body) => (saved.push(body), {}) });
  const leave = leaving();
  await view.flush();
  view.type(view.fact(), "적던 새 글");
  await view.flush();

  assert.equal(leave.go("/records/journal"), true);
  view.render();
  assert.match(view.text(), /잠깐만요!/);
  assert.match(view.text(), /누구 기록인지 골라야 저장돼요/);
  assert.deepEqual(leave.clicked, []);

  await view.press("아이 고르기");
  assert.doesNotMatch(view.text(), /누구 기록인지/);
  assert.ok(view.button("김하늘"), "아이 칩이 펼쳐져 있다");
  assert.deepEqual(leave.clicked, []);

  leave.go("/records/journal");
  view.render();
  await view.press("버리고 이동");
  assert.deepEqual(leave.clicked, ["/records/journal"]);
  assert.equal(saved.length, 0);
});

test("A1 아이만 고르고 영역이 비었으면 「영역 고르기」 쪽지다", async (t) => {
  const view = recordsPage(t);
  const leave = leaving();
  await view.flush();
  await view.press("김하늘");
  view.type(view.fact(), "적던 새 글");
  await view.flush();

  leave.go("/routines");
  view.render();
  assert.match(view.text(), /영역을 골라야 저장돼요/);
  assert.ok(view.button("영역 고르기"));
});

test("F11 관찰일지로 가는 길이 반을 들고 간다", async (t) => {
  const view = recordsPage(t);
  await view.flush();
  await view.press("김하늘");
  const head = view.links().find((n) => textOf(n).includes("관찰일지 만들기"));
  assert.equal(head.props.href, "/records/journal?child=kid-1&class=class-a");
  view.open();
  const card = view.links().find((n) => textOf(n) === "이 기록으로 일지 만들기");
  assert.equal(card.props.href, "/records/journal?record=observation%3A1&class=class-a");
});

test("A5 고친 기록을 쓴 확정 일지가 있으면 「N건 다시 검토」와 그 일지 링크를 띄운다", async (t) => {
  const impact = { affected: [7], newlyStale: [7] };
  const view = recordsPage(t, { editRecord: async () => ({ record: {}, impact }) });
  await view.flush();
  view.open();
  await view.press("고치기");
  view.type(view.fact(), "개미를 5분 동안 보았다.");
  await view
    .nodes()
    .find((n) => n.type === "form")
    .props.onSubmit({ preventDefault() {} });
  await view.flush();

  assert.match(view.text(), /이 기록을 쓴 일지 1건이 다시 검토 대상이 되었어요/);
  const link = view.links().find((n) => textOf(n).includes("일지 보기"));
  assert.equal(link.props.href, "/documents?id=document%3A7");
});

test("A5 지워서 여러 일지가 다시 검토 대상이 되면 보관함으로 잇는다", async (t) => {
  const impact = { affected: [7, 8], newlyStale: [7] };
  const view = recordsPage(t, { removeRecord: async () => impact });
  globalThis.window.confirm = () => true;
  await view.flush();
  view.open();
  await view.press("지우기");
  await view.flush();

  assert.match(view.text(), /이 기록을 쓴 일지 1건이 다시 검토 대상이 되었어요/);
  assert.match(view.text(), /이미 재검토 대상인 일지 1건도/);
  const link = view.links().find((n) => textOf(n).includes("문서 보관함"));
  assert.equal(link.props.href, "/documents");
});

/** 적고 멈추기를 기다리지 않는다 — 타이머를 바로 돌린다. */
function instantTimers(t) {
  const { setTimeout: later, clearTimeout: cancel } = globalThis;
  globalThis.setTimeout = (fn) => (fn(), 0);
  globalThis.clearTimeout = () => {};
  t.after(() => {
    globalThis.setTimeout = later;
    globalThis.clearTimeout = cancel;
  });
}
const submitForm = async (view) => {
  await view
    .nodes()
    .find((n) => n.type === "form")
    .props.onSubmit({ preventDefault() {} });
  await view.flush();
};

test("A2 영역은 아무것도 안 눌린 채 시작하고, 안 고르면 저장하지 않는다", async (t) => {
  const saved = [];
  const view = recordsPage(t, { addRecord: async (body) => (saved.push(body), { id: "o:1" }) });
  await view.flush();
  assert.equal(view.pickedDomain(), undefined);

  await view.press("김하늘");
  view.type(view.fact(), "블록 세 개를 쌓았다.");
  await submitForm(view);
  assert.equal(saved.length, 0);
  assert.match(view.text(), /영역을 골라/);

  await view.press("사회관계");
  await submitForm(view);
  assert.equal(saved[0].domain, "사회관계");
});

test("A2 사실을 적고 멈추면 AI 가 영역 하나를 점선으로 제안만 하고, 눌러야 들어간다", async (t) => {
  instantTimers(t);
  const asked = [];
  const view = recordsPage(t, {
    suggestRecordDomain: async (...args) => (asked.push(args), "사회관계"),
  });
  await view.flush();
  view.type(view.fact(), "친구에게 같이 만들자고 말했다.");
  await view.flush();

  assert.deepEqual(asked.at(-1), ["class-a", "친구에게 같이 만들자고 말했다.", ""]);
  const chip = view.button("사회관계");
  assert.equal(chip.props["data-suggested"], true);
  assert.equal(chip.props["aria-pressed"], false);
  assert.equal(view.pickedDomain(), undefined);

  await view.press("사회관계");
  assert.equal(textOf(view.pickedDomain()), "사회관계");
});

test("A2 글을 바꾸거나 저장한 뒤에는 옛 글의 영역 제안이 남지 않는다 (#487 하민 점검)", async (t) => {
  instantTimers(t);
  const asked = [];
  const view = recordsPage(t, {
    suggestRecordDomain: async (...args) => (asked.push(args), "사회관계"),
    addRecord: async () => ({ ...RECORD, id: "observation:5" }),
  });
  const dotted = () =>
    view
      .nodes()
      .filter((n) => n.props["data-suggested"])
      .map(textOf);
  await view.flush();
  view.type(view.fact(), "친구에게 같이 만들자고 말했다.");
  await view.flush();
  assert.deepEqual(dotted(), ["사회관계"]);

  // 다른 내용의 짧은 글로 바꾼다 — 다시 묻지 않는 길이라도 옛 제안은 사라져야 한다.
  view.type(view.fact(), "울었다");
  await view.flush();
  assert.deepEqual(dotted(), []);
  assert.equal(asked.length, 1);

  // 제안을 받아 저장한 뒤, 다음 기록의 짧은 글에도 옛 제안이 붙지 않는다.
  view.type(view.fact(), "친구에게 같이 만들자고 말했다.");
  await view.flush();
  await view.press("김하늘");
  await view.press("사회관계");
  await submitForm(view);
  view.type(view.fact(), "울었다");
  await view.flush();
  assert.deepEqual(dotted(), []);
});

test("A2 제안이 없으면 점선도 없다", async (t) => {
  instantTimers(t);
  const view = recordsPage(t);
  await view.flush();
  view.type(view.fact(), "비 오는 소리를 듣고 톡톡 하고 따라 말했다.");
  await view.flush();
  assert.equal(
    view.nodes().some((n) => n.props["data-suggested"]),
    false,
  );
});

test("A4 저장한 뒤 빠진 것이 있으면 쪽지 한 줄만 띄우고 막지 않는다", async (t) => {
  const asked = [];
  const view = recordsPage(t, {
    addRecord: async () => ({ ...RECORD, id: "observation:5" }),
    missingInRecord: async (id) => (asked.push(id), ["반응", "상황"]),
  });
  await view.flush();
  await view.press("김하늘");
  await view.press("사회관계");
  view.type(view.fact(), "블록 세 개를 쌓았다.");
  await submitForm(view);

  assert.deepEqual(asked, ["observation:5"]);
  assert.match(view.text(), /관찰 기록을 저장했어요/);
  assert.match(view.text(), /아이 반응이 안 보여요/);
  assert.doesNotMatch(view.text(), /어디서/);
});

const DAY = [
  { name: "등원", start: "09:00", end: "" },
  { name: "실내놀이", start: "10:00", end: "11:30" },
  { name: "점심", start: "11:30", end: "" },
  { name: "바깥놀이", start: "14:00", end: "" },
];
const slot = (view, name) =>
  view.nodes().find((n) => n.type === "button" && textOf(n).endsWith(name) && n.props["data-slot"]);
const context = (view) => view.nodes().find((n) => n.props.name === "context");

test("A3 오늘이고 지금이 그 일과 시간이면 상황 칸을 미리 눌러 두고, 놀이면 「어디서」를 묻는다", async (t) => {
  const asked = [];
  const view = recordsPage(
    t,
    { dayRoutines: async (...args) => (asked.push(args), DAY) },
    { now: "10:20" },
  );
  await view.flush();

  assert.deepEqual(asked.at(-1), ["class-a", TODAY]);
  assert.equal(context(view).props.value, "실내놀이");
  assert.equal(slot(view, "실내놀이").props["aria-pressed"], true);
  assert.equal(view.warned.at(-1), false, "미리 눌러 둔 상황만으로는 적던 글이 아니다");

  await view.press("쌓기");
  assert.equal(context(view).props.value, "실내놀이, 쌓기");
  assert.equal(view.button("쌓기").props["aria-pressed"], true);

  await slot(view, "바깥놀이").props.onClick();
  view.render();
  assert.equal(context(view).props.value, "바깥놀이");
  assert.equal(view.button("쌓기"), undefined, "바깥놀이는 흥미 영역을 묻지 않는다");
});

test("A3 몰아서 적을 때(지난 날짜 · 일과 밖 시각)는 칩만 보이고 미리 누르지 않는다", async (t) => {
  const view = recordsPage(t, { dayRoutines: async () => DAY }, { now: "16:00" });
  await view.flush();
  assert.equal(context(view).props.value, "");
  assert.ok(slot(view, "점심"));

  view.type(view.date(), "2026-11-05");
  await view.flush();
  assert.equal(context(view).props.value, "");
});

test("A3 그날 일과가 없으면 시간표 없이 지금처럼 적는다", async (t) => {
  const view = recordsPage(t, {}, { now: "10:20" });
  await view.flush();
  assert.equal(
    view.nodes().some((n) => n.props["data-slot"]),
    false,
  );
  assert.equal(context(view).props.value, "");
});

// ── 관찰일지 만들기 (ObservationJournalPage) ──────────────────────────────

const SUMMARY = {
  id: "document:1",
  childId: "kid-1",
  title: "김하늘 관찰일지",
  start: "2026-11-02",
  end: "2026-11-06",
  status: "draft",
  origin: "ai",
  stale: false,
};

function journalPage(t, { search = "", docs = [], records = [], opened } = {}) {
  browser(t, search);
  const app = host();
  const asked = [];
  const drafts = [];
  const editors = [];
  const Page = compile("../components/workspace/ObservationJournalPage.tsx", {
    ...common(app.react),
    "@/lib/api/records": {
      listRecords: async (classId) => {
        asked.push(classId);
        return records;
      },
    },
    // 만드는 중에 멈춰 둔다 — 그동안 화면이 무엇을 잠그는지 본다.
    "@/lib/api/documents": {
      createDocument: () => new Promise(() => {}),
      listDocuments: async () => docs,
    },
    "@/lib/api/onboarding": { classServerId: () => 3 },
    "@/lib/workspace/child-mark": { markFor: () => 0, weekStart: () => "2026-11-09" },
    "./WorkspaceUI": {
      WorkspacePage: "page",
      Empty: "empty",
      Message: "message",
      useClasses: () => ROOMS,
      ws: {},
    },
    "./ObservationJournalEditor": {
      __esModule: true,
      default: function JournalEditorStub(props) {
        editors.push(props);
        return null;
      },
    },
    "./ObservationClassDrafts": {
      __esModule: true,
      default: function ClassDraftsStub(props) {
        drafts.push(props);
        return null;
      },
    },
    "./use-server-document": {
      useServerDocument: () =>
        opened ? { status: "ready", doc: opened, server: {} } : { status: "loading" },
    },
    "./RecordsPage": { openPicker: () => {} },
  }).default;
  return { ...app.mount(Page), asked, drafts, editors };
}

test("F7 초안을 만드는 동안 아이 · 기간 · 근거를 고를 수 없다", async (t) => {
  const view = journalPage(t, {
    search: "?child=kid-1",
    records: [{ ...RECORD, childId: "kid-1", date: TODAY }],
  });
  await view.flush();
  const controls = () =>
    view
      .nodes()
      .filter(
        (n) => (n.type === "button" && n.props["aria-pressed"] !== undefined) || n.type === "input",
      );
  assert.ok(controls().length >= 5, "아이 둘 · 날짜 둘 · 근거 하나");
  assert.ok(controls().every((n) => !n.props.disabled));
  // 만들기 요청은 끝나지 않는다 — 기다리지 않고 그 사이 화면을 본다.
  view.button("초안 만들기").props.onClick();
  view.render();
  assert.ok(controls().every((n) => n.props.disabled));
});

test("F10 올린 서류(IMPORT)는 관찰일지 목록에 두지 않는다", async (t) => {
  const view = journalPage(t, {
    search: "?child=kid-1",
    docs: [SUMMARY, { ...SUMMARY, id: "document:2", title: "올린 관찰기록", origin: "import" }],
  });
  await view.flush();
  assert.match(view.text(), /김하늘 관찰일지/);
  assert.doesNotMatch(view.text(), /올린 관찰기록/);
});

test("F11 주소의 class 로 그 반을 연다", async (t) => {
  const view = journalPage(t, { search: "?class=class-b&child=kid-9" });
  await view.flush();
  assert.deepEqual(view.asked, ["class-b"]);
  // 기록이 없는 아이라 이름 뒤에 「기록 없음」이 붙는다.
  assert.ok(view.button("이달기록 없음"), "그 반 아이가 나온다");
});

test("F15 확정본이 stale 이면 목록에 둘 다 보인다", async (t) => {
  const view = journalPage(t, {
    search: "?child=kid-1",
    docs: [{ ...SUMMARY, status: "confirmed", stale: true }],
  });
  await view.flush();
  assert.match(view.text(), /확정 · 다시 확인 필요/);
});

// ── 관찰일지 편집기 (ObservationJournalEditor) ─────────────────────────────

const DOC = {
  id: "document:1",
  kind: "observation",
  title: "김하늘 관찰일지",
  className: "햇살반",
  childName: "김하늘",
  start: "2026-11-02",
  end: "2026-11-02",
  status: "draft",
  origin: "ai",
  sections: [
    { heading: "사실", body: "개미를 오래 보았다.", sourceIds: ["observation:1"] },
    { heading: "해석", body: "작은 생물에 관심이 많다.", sourceIds: ["observation:1"] },
    { heading: "지원", body: "돋보기를 놀이터에 둔다.", sourceIds: ["observation:1"] },
  ],
  sources: [
    { id: "observation:1", date: "2026-11-02", text: "개미를 오래 보았다.", domain: "자연탐구" },
  ],
};

function editor(t, { initial = DOC, save, refresh, api = {}, onNext, extra = {} } = {}) {
  browser(t);
  const app = host();
  const calls = [];
  const modules = { ...common(app.react), "./WorkspaceUI": { Message: "message", ws: {} } };
  const Editor = compile("../components/workspace/ObservationJournalEditor.tsx", {
    ...modules,
    "@/lib/api/documents": { ...documents, ...api },
    "@/lib/api/client": { invalidFields },
    "@/components/plan-generator/AnnualFrame": { EXPORTS: {}, FileLogo: "file-logo" },
    "@/lib/hooks/use-hwpx-download": {
      useHwpxDownload: () => ({ exporting: false, download: async () => {} }),
    },
    "@/lib/hooks/use-unsaved-warning": { useUnsavedWarning: () => {} },
    "./document-selection": { serverIssues: () => [] },
    "@/lib/workspace/observation-axis": axis,
    "./WorkspaceViewState": compile("../components/workspace/WorkspaceViewState.tsx", modules),
  }).default;
  const server = {
    stale: true,
    pending: false,
    save: async (sections) => {
      calls.push("save");
      return save ? save(sections) : { ...initial, sections };
    },
    refresh: async () => {
      calls.push("refresh");
      return refresh ?? initial;
    },
    saveAndConfirm: async (sections) => {
      calls.push("confirm");
      return { ...initial, sections, status: "confirmed" };
    },
    ...extra,
  };
  const view = app.mount(Editor, { initial, server, domains: DOMAINS, onNext });
  const pad = (heading) => view.nodes().find((n) => n.props["aria-label"] === `${heading} 내용`);
  return { ...view, calls, pad };
}

test("F9 저장 안 한 해석이 있으면 반영 전에 묻는다 — 저장하고 반영", async (t) => {
  const view = editor(t);
  view.type(view.pad("해석"), "고치던 해석");
  await view.press("바뀐 근거 반영하기");
  assert.deepEqual(view.calls, [], "묻기 전에는 아무것도 보내지 않는다");
  await view.press("저장하고 반영");
  assert.deepEqual(view.calls, ["save", "refresh"]);
});

test("F9 편집 버리고 반영 · 고친 게 없으면 바로 반영", async (t) => {
  const view = editor(t);
  view.type(view.pad("해석"), "고치던 해석");
  await view.press("바뀐 근거 반영하기");
  await view.press("편집 버리고 반영");
  assert.deepEqual(view.calls, ["refresh"]);
  assert.equal(view.pad("해석").props.value, "작은 생물에 관심이 많다.");

  await view.press("바뀐 근거 반영하기");
  assert.deepEqual(view.calls, ["refresh", "refresh"]);
});

test("F12 근거 쪽지와 출력 미리보기가 서버가 준 영역을 쓴다", async (t) => {
  const draft = editor(t);
  assert.match(draft.text(), /11\/2\(월\) · 자연탐구/);
  const done = editor(t, { initial: { ...DOC, status: "confirmed" } });
  const row = done.nodes().find((n) => n.type === "tr" && textOf(n).startsWith("자연탐구"));
  assert.match(textOf(row), /\(11\/2\) 개미를 오래 보았다\./);
});

test("F13 서버가 짚은 공책(sections.해석)을 표시한다", async (t) => {
  const view = editor(t, {
    save: () => {
      throw new ApiError(422, {
        error: {
          code: "VALIDATION_FAILED",
          message: "해석에 기록에 없는 숫자가 있어요.",
          fields: ["sections.해석"],
        },
      });
    },
  });
  view.type(view.pad("해석"), "개미를 열 번 보았다.");
  await view.press("초안 저장");
  assert.equal(view.pad("해석").props["aria-invalid"], true);
  assert.equal(view.pad("지원").props["aria-invalid"], undefined);
  assert.match(view.text(), /해석에 기록에 없는 숫자가 있어요/);
  // 고치면 표시가 풀린다.
  view.type(view.pad("해석"), "개미를 오래 보았다.");
  assert.equal(view.pad("해석").props["aria-invalid"], undefined);
});

test("3차-12 확정본 미리보기는 문서 사본의 축 · 상황으로 그린다 — 원 설정이 바뀌어도", async (t) => {
  // 원은 지금 5영역(DOMAINS)이지만, 이 문서는 2축으로 만들었다.
  const view = editor(t, {
    initial: {
      ...DOC,
      status: "confirmed",
      observationAxis: "DAILY_PLAY_2",
      sources: [{ ...DOC.sources[0], domain: "놀이활동", context: "바깥놀이" }],
    },
  });
  const heads = view
    .nodes()
    .filter((n) => n.type === "th" && n.props.scope === "row")
    .map((n) => textOf(n));
  assert.deepEqual(heads, ["일상생활", "놀이활동", "총평"]);
  const row = view.nodes().find((n) => n.type === "tr" && textOf(n).startsWith("놀이활동"));
  assert.match(textOf(row), /\(11\/2\) \(바깥놀이\) 개미를 오래 보았다\./);

  // 사본이 없는 옛 문서만 지금 원 설정을 쓴다.
  const old = editor(t, { initial: { ...DOC, status: "confirmed" } });
  assert.ok(old.nodes().some((n) => n.type === "th" && textOf(n) === "종합해석"));
});

// ── 관찰일지 딸깍 (ADR-083) ────────────────────────────────────────────────

test("B5 기간 칩 한 번으로 기간을 정하고, 기록 없는 아이만 점선과 「기록 없음」", async (t) => {
  const view = journalPage(t, { records: [{ ...RECORD, childId: "kid-1", date: TODAY }] });
  await view.flush();
  assert.equal(view.button("이번 주").props["aria-pressed"], true);
  await view.press("이번 달");
  const dates = view.nodes().filter((n) => n.type === "input" && n.props.type === "date");
  assert.deepEqual(
    dates.map((n) => n.props.value),
    ["2026-11-01", TODAY],
  );
  await view.press("지난달");
  assert.deepEqual(
    view
      .nodes()
      .filter((n) => n.props.type === "date")
      .map((n) => n.props.value),
    ["2026-10-01", "2026-10-31"],
  );
  await view.press("이번 주");
  // 숫자를 붙이지 않는다. 기록 있는 아이는 이름만.
  assert.ok(view.button("김하늘"));
  assert.ok(view.button("박서아기록 없음"));
});

test("B1 아이를 고르지 않으면 반 전체를 보여 준다", async (t) => {
  const view = journalPage(t, { records: [RECORD] });
  await view.flush();
  const last = view.drafts.at(-1);
  assert.deepEqual(
    last.kids.map((k) => k.name),
    ["김하늘", "박서아"],
  );
  assert.equal(last.classId, "class-a");
  // 아이를 고르면 그 아이 목록으로 바뀌고, 다시 누르면 반 전체로 돌아간다.
  const before = view.drafts.length;
  await view.press("김하늘기록 없음");
  assert.equal(view.drafts.length, before);
  await view.press("김하늘기록 없음");
  assert.ok(view.drafts.length > before);
});

test("B6 반 전체 초안의 다음 아이 초안이 있으면 「확정하고 다음 아이」를 단다", async (t) => {
  const draft = { ...SUMMARY, start: "2026-11-01", end: TODAY };
  const docs = [draft, { ...draft, id: "document:2", childId: "kid-2", title: "박서아 관찰일지" }];
  const view = journalPage(t, { docs, opened: { ...DOC, id: "document:1" } });
  await view.flush();
  view.drafts.at(-1).onOpen("document:1");
  view.render();
  const props = view.editors.at(-1);
  assert.equal(typeof props.onNext, "function");
  // 마지막 아이에게는 다음이 없다.
  props.onNext();
  view.render();
  assert.equal(view.editors.at(-1).onNext, undefined);
});

// ── 반 전체 초안 (ObservationClassDrafts) ─────────────────────────────────

const KIDS = [
  { id: "kid-1", name: "가람" },
  { id: "kid-2", name: "나래" },
  { id: "kid-3", name: "다온" },
  { id: "kid-4", name: "하람" },
];
const rec = (id, childId, date = "2026-11-03", createdAt = "2026-11-03T01:00:00Z") => ({
  ...RECORD,
  id: `observation:${id}`,
  childId,
  date,
  createdAt,
});
const draftOf = (childId, extra = {}) => ({
  ...SUMMARY,
  id: `document:${childId}`,
  childId,
  start: "2026-11-01",
  end: "2026-11-10",
  createdAt: "2026-11-04T00:00:00Z",
  aiReviewState: "done",
  ...extra,
});

function classDrafts(t, { records = [], docs = [], create, bundle } = {}) {
  browser(t);
  const app = host();
  const calls = { create: [], bundle: [], opened: [], changed: 0 };
  const Drafts = compile("../components/workspace/ObservationClassDrafts.tsx", {
    ...common(app.react),
    "@/lib/api/documents": {
      createDocument: async (input) => {
        calls.create.push(input);
        return create ? create(input) : {};
      },
      downloadDocumentBundle: async (ids) => {
        calls.bundle.push(ids);
        if (bundle) await bundle(ids);
      },
    },
    "@/lib/api/client": { errorCode: documentsErrorCode },
    "@/lib/hooks/use-unsaved-warning": { useUnsavedWarning: () => {} },
    "./WorkspaceUI": { Message: "message", ws: {} },
  });
  const view = app.mount(Drafts.default, {
    kids: KIDS,
    records,
    docs,
    start: "2026-11-01",
    end: "2026-11-10",
    classId: "class-a",
    onOpen: (id) => calls.opened.push(id),
    onChanged: () => calls.changed++,
  });
  const row = (name) => view.nodes().find((n) => n.type === "li" && textOf(n).startsWith(name));
  const box = (name) => view.nodes().find((n) => n.props["aria-label"] === `${name} 초안 만들기`);
  return { ...view, calls, row, box, helpers: Drafts };
}
const { errorCode: documentsErrorCode } = await import("../lib/api/client.ts");

test("B1 아이별 상태 — 확정 · 초안 · 검토 못 함 · 물어볼 것 · 기록 없음, 기록 1개는 체크 끈 채로", async (t) => {
  const view = classDrafts(t, {
    records: [
      rec(1, "kid-1"),
      rec(2, "kid-2"),
      rec(3, "kid-2", "2026-11-05", "2026-11-05T01:00:00Z"),
      rec(4, "kid-3"),
      rec(5, "kid-3", "2026-11-04"),
    ],
    docs: [draftOf("kid-2"), draftOf("kid-3", { status: "confirmed" })],
  });
  assert.match(textOf(view.row("가람")), /관찰 1개/);
  assert.equal(view.box("가람").props.checked, false, "기록 1개는 끈 채로");
  assert.equal(view.box("가람").props.disabled, false);
  // 초안을 만든 뒤 기록이 하나 더 생겼다 — 물어본다.
  assert.match(textOf(view.row("나래")), /물어볼 것새 기록 1개그대로 열기넣어서 다시/);
  assert.match(textOf(view.row("다온")), /확정/);
  assert.match(textOf(view.row("하람")), /기록 없음/);
  assert.equal(view.box("하람").props.disabled, true);

  const unreviewed = classDrafts(t, {
    records: [rec(1, "kid-1"), rec(2, "kid-1")],
    docs: [draftOf("kid-1", { aiReviewState: "mock" })],
  });
  // mock 검토를 「초안」(통과)으로 보이게 하지 않는다.
  assert.match(textOf(unreviewed.row("가람")), /검토 못 함/);
});

test("B1 반 전체 초안은 체크한 아이만 차례로 만들고, 한도 초과면 남은 아이를 부르지 않는다", async (t) => {
  const { ApiError } = await import("../lib/api/client.ts");
  const fail = (code, message) =>
    new ApiError(code === "VALUE_INVALID" ? 422 : 503, {
      error: { code, message, fields: ["source_ids"] },
    });
  const view = classDrafts(t, {
    records: [
      rec(1, "kid-1"),
      rec(2, "kid-1"),
      rec(3, "kid-2"),
      rec(4, "kid-2"),
      rec(5, "kid-3"),
      rec(6, "kid-3"),
      rec(7, "kid-4"),
    ],
    create: (input) => {
      if (input.childId === "kid-1") throw fail("VALUE_INVALID", "「민」이 아이 이름인가요?");
      if (input.childId === "kid-2")
        throw fail("LLM_BUDGET_EXCEEDED", "AI 사용 한도를 넘었습니다.");
      return {};
    },
  });
  await view.press("반 전체 초안 만들기");
  await view.flush();
  // 기록 1개인 하람은 체크가 꺼져 있어 부르지 않는다. 한도에 걸린 뒤 다온도 부르지 않는다.
  assert.deepEqual(
    view.calls.create.map((c) => c.childId),
    ["kid-1", "kid-2"],
  );
  assert.deepEqual(view.calls.create[0].sourceIds, ["observation:1", "observation:2"]);
  assert.match(textOf(view.row("가람")), /물어볼 것.*「민」이 아이 이름인가요\?/);
  assert.match(textOf(view.row("나래")), /못 만듦.*AI 사용 한도/);
  assert.match(textOf(view.row("다온")), /못 만듦.*AI 사용 한도/);
});

test("B1 넣어서 다시는 이 기간 기록 전부로 옛 초안을 바꾼다", async (t) => {
  const view = classDrafts(t, {
    records: [rec(1, "kid-1"), rec(2, "kid-1", "2026-11-06", "2026-11-06T00:00:00Z")],
    docs: [draftOf("kid-1")],
  });
  await view.press("넣어서 다시");
  assert.equal(view.calls.create.length, 1);
  assert.equal(view.calls.create[0].replaceDraft, true);
  assert.deepEqual(view.calls.create[0].sourceIds, ["observation:1", "observation:2"]);
  await view.press("그대로 열기");
  assert.deepEqual(view.calls.opened, ["document:kid-1"]);
});

test("B2 확정본 묶음은 근거가 그대로인 확정본만 받고, 빠진 수를 알린다", async (t) => {
  const view = classDrafts(t, {
    records: [rec(1, "kid-1"), rec(2, "kid-2"), rec(3, "kid-3")],
    docs: [
      draftOf("kid-1", { status: "confirmed" }),
      draftOf("kid-2", { status: "confirmed", stale: true }),
      draftOf("kid-3"),
    ],
  });
  assert.match(view.text(), /1명은 원본 기록이 바뀌어 파일에서 빠져요/);
  await view.press("확정 1명 한 파일로");
  assert.deepEqual(view.calls.bundle, [["document:kid-1"]]);
});

// ── 편집기: 붙여 온 검토 · 고친 문장 · 다음 아이 ─────────────────────────────

const FLAGGED = "작은 생물에 매일 관심이 많다.";
const REVIEWED = {
  ...DOC,
  sections: DOC.sections.map((s) =>
    s.heading === "해석" ? { ...s, body: `${FLAGGED} 개미를 오래 본다.` } : s,
  ),
  aiReview: {
    state: "done",
    message: "",
    issues: [
      {
        heading: "해석",
        sentence: FLAGGED,
        code: "UNSUPPORTED_FACT",
        sourceText: null,
        reason: "기록에 없는 일이 사실처럼 적혀 있어요.",
        fix: "",
      },
    ],
  },
};

test("B3 붙여 온 검토는 문장에 형광펜, 이유는 칸 아래 한 줄. 문장을 고치면 사라진다", async (t) => {
  const view = editor(t, { initial: REVIEWED });
  const marks = view.nodes().filter((n) => n.type === "mark");
  assert.deepEqual(marks.map(textOf), [FLAGGED]);
  assert.match(view.text(), /기록에 없는 일이 사실처럼 적혀 있어요\./);
  assert.ok(view.nodes().find((n) => n.props["aria-label"] === "다시 검토"));
  view.type(view.pad("해석"), "개미를 오래 본다.");
  assert.equal(view.nodes().filter((n) => n.type === "mark").length, 0);
});

test("B3 mock · 실패한 검토는 형광펜 없이 판정하지 않았다고 말한다", async (t) => {
  const view = editor(t, {
    initial: { ...REVIEWED, aiReview: { state: "mock", message: "", issues: [] } },
  });
  assert.match(view.text(), /AI 검토가 꺼져 있어 판정하지 않았어요/);
  const failed = editor(t, {
    initial: { ...REVIEWED, aiReview: { state: "failed", message: "지금은 못 써요.", issues: [] } },
  });
  assert.match(failed.text(), /AI 검토를 못 했어요\. 지금은 못 써요\./);
});

test("B4 고친 문장은 보라 점선 제안으로 오고, 확인할 곳을 같이 보이며, 눌러야 바뀐다", async (t) => {
  const asked = [];
  const view = editor(t, {
    initial: REVIEWED,
    api: {
      rewriteSentence: async (id, kind, input) => {
        asked.push({ id, ...input });
        return {
          sentence: "작은 생물에 관심이 많다.",
          judged: true,
          issues: [
            {
              heading: "해석",
              sentence: "작은 생물에 관심이 많다.",
              code: "DIAGNOSIS",
              sourceText: null,
              reason: "성향을 단정하는 표현이 있어요.",
              fix: "",
            },
          ],
        };
      },
    },
  });
  await view.press("고친 문장");
  await view.flush();
  assert.equal(asked[0].sentence, FLAGGED);
  assert.equal(asked[0].style, "fix");
  // jev 가 짚어도 거르지 않는다 — 문장과 확인할 곳을 같이 보여 준다.
  assert.match(view.text(), /작은 생물에 관심이 많다\.확인할 곳: 성향을 단정하는 표현이 있어요\./);
  assert.equal(view.pad("해석").props.value, REVIEWED.sections[1].body, "누르기 전엔 그대로");
  await view.press("이 문장으로 바꾸기");
  assert.equal(view.pad("해석").props.value, "작은 생물에 관심이 많다. 개미를 오래 본다.");
});

test("B4 규칙 검사에 걸린 고친 문장은 보여 주지 않는다", async (t) => {
  const view = editor(t, {
    initial: REVIEWED,
    api: { rewriteSentence: async () => ({ sentence: null, judged: false, issues: [] }) },
  });
  await view.press("더 짧게");
  await view.flush();
  assert.match(view.text(), /규칙 검사를 지난 문장을 못 만들었어요/);
  assert.equal(view.button("이 문장으로 바꾸기"), undefined);
});

test("B6 「확정하고 다음 아이」는 확정이 된 뒤에만 다음으로 간다", async (t) => {
  let moved = 0;
  const none = editor(t, { extra: { stale: false } });
  assert.equal(none.button("확정하고 다음 아이"), undefined, "다음 아이가 없으면 단추도 없다");

  const view = editor(t, { onNext: () => moved++, extra: { stale: false } });
  view
    .nodes()
    .find((n) => n.type === "input" && n.props.type === "checkbox")
    .props.onChange({
      target: { checked: true },
    });
  view.render();
  await view.press("확정하고 다음 아이");
  await view.flush();
  assert.deepEqual(view.calls, ["confirm"]);
  assert.equal(moved, 1);
});

test("FR 종이 미리보기의 빈 영역 줄은 화면에만 「이 영역 관찰이 없어요」", async (t) => {
  const done = editor(t, { initial: { ...DOC, status: "confirmed" } });
  const row = (domain) => done.nodes().find((n) => n.type === "tr" && textOf(n).startsWith(domain));
  assert.match(textOf(row("의사소통")), /이 영역 관찰이 없어요/);
  assert.doesNotMatch(textOf(row("자연탐구")), /이 영역 관찰이 없어요/);
  const draft = editor(t);
  assert.match(draft.text(), /이 영역 관찰이 없어요: 신체운동·건강, 의사소통, 사회관계, 예술경험/);
});

// ── F4 (하민 교차 검토) — 만드는 동안 다른 일지를 열 수 없다 ─────────────────

test("F4 한 아이 초안을 만드는 동안 목록의 다른 일지를 열 수 없다", async (t) => {
  const view = journalPage(t, {
    search: "?child=kid-1",
    docs: [SUMMARY],
    records: [{ ...RECORD, childId: "kid-1", date: TODAY }],
  });
  await view.flush();
  const opener = () =>
    view.nodes().find((n) => n.type === "button" && textOf(n).startsWith("김하늘 관찰일지"));
  assert.equal(opener().props.disabled, false);
  view.button("초안 만들기").props.onClick();
  view.render();
  // 열 수 있으면 늦게 온 생성 응답이 교사가 연 일지를 덮는다.
  assert.equal(opener().props.disabled, true);
});

test("F4 반 전체 초안이 도는 동안 아이 · 기간 고르기를 잠근다", async (t) => {
  const view = journalPage(t, { records: [RECORD] });
  await view.flush();
  const pickers = () =>
    view
      .nodes()
      .filter(
        (n) => (n.type === "button" && n.props["aria-pressed"] !== undefined) || n.type === "input",
      );
  assert.ok(pickers().every((n) => !n.props.disabled));
  view.drafts.at(-1).onBusy(true);
  view.render();
  assert.ok(pickers().every((n) => n.props.disabled));
  view.drafts.at(-1).onBusy(false);
  view.render();
  assert.ok(pickers().every((n) => !n.props.disabled));
});

test("F4 반 전체 초안이 도는 동안 아이 일지 열기를 잠그고 화면에 알린다", async (t) => {
  const busy = [];
  browser(t);
  const app = host();
  const Drafts = compile("../components/workspace/ObservationClassDrafts.tsx", {
    ...common(app.react),
    "@/lib/api/documents": {
      createDocument: () => new Promise(() => {}),
      downloadDocumentBundle: async () => {},
    },
    "@/lib/api/client": { errorCode: documentsErrorCode },
    "@/lib/hooks/use-unsaved-warning": { useUnsavedWarning: () => {} },
    "./WorkspaceUI": { Message: "message", ws: {} },
  });
  const view = app.mount(Drafts.default, {
    kids: KIDS,
    records: [rec(1, "kid-1"), rec(2, "kid-1"), rec(3, "kid-2"), rec(4, "kid-2")],
    docs: [draftOf("kid-2"), draftOf("kid-3", { status: "confirmed" })],
    start: "2026-11-01",
    end: "2026-11-10",
    classId: "class-a",
    onOpen: () => {},
    onChanged: () => {},
    onBusy: (on) => busy.push(on),
  });
  assert.equal(view.button("나래").props.disabled, false);
  view.button("반 전체 초안 만들기").props.onClick();
  view.render();
  assert.deepEqual(busy, [true]);
  assert.equal(view.button("나래").props.disabled, true);
  assert.equal(view.button("다온").props.disabled, true);
});
