import assert from "node:assert/strict";
import { test } from "node:test";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";

const require = createRequire(import.meta.url);
const axis = await import("../lib/workspace/observation-axis.ts");
const journalDay = await import("../lib/workspace/journal-day.ts");
const childMark = await import("../lib/workspace/child-mark.ts");
const domainLook = await import("../lib/workspace/domain-look.ts");
const TODAY = "2026-11-05";
const jsx = (type, props, key) => ({ type, props, key });
const runtime = { jsx, jsxs: jsx, Fragment: "fragment" };
const nodes = (node) => {
  if (Array.isArray(node)) return node.flatMap(nodes);
  if (node === null || node === undefined || typeof node === "boolean") return [];
  return typeof node === "object" ? [node, ...nodes(node.props.children)] : [node];
};
const text = (node) =>
  nodes(node)
    .filter((n) => typeof n === "string" || typeof n === "number")
    .join("");
const settle = () => new Promise((resolve) => setImmediate(resolve));
function deferred() {
  let resolve;
  const promise = new Promise((done) => {
    resolve = done;
  });
  return { promise, resolve };
}
function compile(path, imports) {
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
  // `module` 이라는 이름은 Next 의 lint 가 막는다 (@next/next/no-assign-module-variable).
  // 아래 new Function 의 매개변수 이름 "module"/"exports" 는 babel 이 뱉은 CJS 코드가
  // 그대로 쓰므로 바꾸지 않는다 — 바깥 변수 이름만 바꾼다.
  const cjs = { exports: {} };
  new Function("require", "module", "exports", code)(
    (name) => {
      assert.ok(name in imports, `Unexpected import: ${name}`);
      return imports[name];
    },
    cjs,
    cjs.exports,
  );
  return cjs.exports;
}

const nuriZeros = Object.fromEntries(axis.NURI_DOMAINS.map((domain) => [domain, 0]));
const tracking = (id, name, counts) => ({
  child_id: id,
  name,
  code: `fixture-${id}`,
  total: Object.values(counts).reduce((a, b) => a + b, 0),
  last_date: "2026-10-31",
  by_domain: counts,
});
const first = tracking(101, "가아동", {
  ...nuriZeros,
  "신체운동·건강": 3,
  의사소통: 2,
  놀이활동: 4,
  일상생활: 1,
});
const second = tracking(102, "나아동", { ...nuriZeros, 놀이활동: 2, 일상생활: 1 });
const otherClass = tracking(201, "다아동", nuriZeros);
function recordsFor(child, classId = 10) {
  return Object.entries(child.by_domain).flatMap(([domain, count]) =>
    Array.from({ length: count }, (_, index) => ({
      id: `${child.child_id}-${domain}-${index}`,
      child_id: child.child_id,
      class_id: classId,
      date: "2026-10-31",
      domain,
      context: "",
      fact: `${child.name} ${domain} 기록 ${index + 1}`,
    })),
  );
}

// 저장소의 다른 화면 테스트와 같은 방식으로 실제 컴포넌트의 effect와 이벤트를 실행한다.
// 아동별 React key를 프레임에 포함해 언마운트 정리와 늦은 응답 무시도 확인한다.
function harness(
  t,
  {
    configuredAxis = "NURI_5",
    settings,
    children = [first, second],
    observations = {},
    trackingRequest,
  } = {},
) {
  const frames = new Map();
  const pending = [];
  const calls = [];
  let frame, tree;
  const hooks = {
    useState(initial) {
      const current = frame;
      const index = current.cursor++;
      if (!(index in current.slots))
        current.slots[index] = typeof initial === "function" ? initial() : initial;
      return [
        current.slots[index],
        (next) => {
          current.slots[index] = typeof next === "function" ? next(current.slots[index]) : next;
        },
      ];
    },
    useEffect(fn, deps) {
      const current = frame;
      const index = current.cursor++;
      const before = current.effects[index];
      if (!before || deps.some((dep, i) => !Object.is(dep, before.deps[i]))) {
        before?.cleanup?.();
        const effect = { deps };
        current.effects[index] = effect;
        pending.push(() => {
          if (frames.get(current.key) === current && current.effects[index] === effect)
            effect.cleanup = fn();
        });
      }
    },
  };
  const auth = {
    getMe: async () => ({ center_id: 42 }),
    getCurrentUser: async () => ({ center_id: 42 }),
  };
  const { useObservationDomains } = compile("../lib/hooks/use-observation-domains.ts", {
    react: hooks,
    "@/lib/api/auth": auth,
    "@/lib/api/centers": {
      getCenterSettings: async (id) => {
        calls.push(["settings", id]);
        return settings ?? { observation_axis: configuredAxis };
      },
    },
    "@/lib/workspace/observation-axis": axis,
  });
  const mod = compile("../components/workspace/ChildTrackingPage.tsx", {
    "react/jsx-runtime": runtime,
    react: hooks,
    "next/link": { __esModule: true, default: "a" },
    "@/lib/api/auth": auth,
    "@/lib/api/onboarding": {
      CLASS_PREFIX: "class-",
      CHILD_PREFIX: "child-",
      // 반은 사이드바가 고른다. 시험은 연결을 안 두므로 서버가 준 첫 반으로 떨어진다.
      classServerId: () => null,
    },
    "@/lib/hooks/use-client-state": { useClientState: (_read, fallback) => [fallback, () => {}] },
    "@/lib/onboarding/settings": {
      loadClassSettings: () => null,
      chosenClassFor: () => null,
    },
    "@/lib/api/classes": {
      isMyClass: (c) => c.my_access !== "NONE",
      getClasses: async () => ({
        items: [
          // 남의 반이 맨 앞에 있어도 첫 반 대체로 고르지 않는다 (ADR-059).
          { id: 5, name: "남의반", my_access: "NONE" },
          { id: 10, name: "가반" },
          { id: 20, name: "나반" },
        ],
      }),
    },
    "@/lib/api/children": {
      getChildTracking: async (id) => {
        calls.push(["tracking", id]);
        if (trackingRequest) return trackingRequest(id);
        return { items: id === 10 ? children : [otherClass] };
      },
    },
    "@/lib/api/observations": {
      getObservations: async ({ child_id }) => {
        calls.push(["observations", child_id]);
        if (observations[child_id]) return { items: await observations[child_id] };
        const child = [...children, otherClass].find((c) => c.child_id === child_id);
        return { items: recordsFor(child, child_id === 201 ? 20 : 10) };
      },
    },
    "@/lib/hooks/use-observation-domains": { useObservationDomains },
    "@/lib/workspace/observation-axis": axis,
    "@/lib/workspace/child-mark": childMark,
    "@/lib/workspace/domain-look": domainLook,
    "@/lib/workspace/model": { today: () => TODAY },
    "@/components/app/ChildPicker": { ChildNote: "child-note" },
    "@/components/app/icons": { Icon: "icon" },
    "@/lib/workspace/journal-day": journalDay,
    "@/components/app/Posty": { Posty: "posty" },
    "./DocumentArchiveArt": new Proxy({}, { get: () => "decoration" }),
    "./WorkspaceUI": { Message: "message" },
    "./ChildTracking.module.css": {
      __esModule: true,
      default: new Proxy({}, { get: (_, name) => name }),
    },
  });
  const Page = mod.default;
  function enter(key, draw) {
    if (!frames.has(key)) frames.set(key, { key, slots: [], effects: [], cursor: 0 });
    const outer = frame;
    frame = frames.get(key);
    frame.cursor = 0;
    frame.seen = true;
    try {
      return draw();
    } finally {
      frame = outer;
    }
  }
  function resolve(node, path) {
    if (Array.isArray(node)) return node.map((child, index) => resolve(child, `${path}/${index}`));
    if (!node || typeof node !== "object") return node;
    if (typeof node.type === "function") {
      const key = `${path}/${node.type.name}:${node.key ?? ""}`;
      return resolve(
        enter(key, () => node.type(node.props)),
        key,
      );
    }
    return {
      ...node,
      props: { ...node.props, children: resolve(node.props.children, `${path}/children`) },
    };
  }
  function render() {
    frames.forEach((item) => {
      item.seen = false;
    });
    tree = resolve(
      enter("page", () => Page()),
      "page",
    );
    for (const [key, item] of frames) {
      if (!item.seen) {
        item.effects.forEach((effect) => effect?.cleanup?.());
        frames.delete(key);
      }
    }
  }
  async function flush() {
    render();
    pending.splice(0).forEach((run) => run());
    await settle();
    render();
  }
  t.after(() => frames.forEach((item) => item.effects.forEach((effect) => effect?.cleanup?.())));
  render();
  const byClass = (name) => nodes(tree).filter((node) => node?.props?.className === name);
  return {
    module: mod,
    calls,
    render,
    flush,
    byClass,
    mount: async () => {
      for (let i = 0; i < 4; i++) await flush();
    },
    text: () => text(tree),
    button: (label) => nodes(tree).find((node) => node?.type === "button" && text(node) === label),
    // 영역별 기록 수는 타일 다섯 장이 아니라 한 줄짜리 띠다 — li 하나가 한 영역.
    cards: () => nodes(byClass("domainRow")).filter((node) => node?.type === "li"),
    count(domain) {
      const item = nodes(byClass("domainRow"))
        .filter((node) => node?.type === "li")
        .find((node) => nodes(node).some((n) => n?.type === "span" && text(n) === domain));
      return text(nodes(item).find((node) => node?.type === "b"));
    },
    /** 그 영역에 기록이 하나도 없으면 띠를 흐리게 둔다. */
    empty(domain) {
      const item = nodes(byClass("domainRow"))
        .filter((node) => node?.type === "li")
        .find((node) => nodes(node).some((n) => n?.type === "span" && text(n) === domain));
      return item?.props["data-empty"] === true;
    },
    pickChild(id) {
      nodes(tree)
        .find(
          (node) =>
            node?.type === "button" &&
            node.props["aria-label"]?.startsWith(
              `${children.find((c) => c.child_id === id).name} ·`,
            ),
        )
        .props.onClick();
      render();
    },
    header: () => nodes(tree).find((node) => node?.type === "header"),
  };
}

test("원이 누리과정 5영역이면 다섯 칸에 서버의 실제 수만 표시한다", async (t) => {
  const page = harness(t);
  await page.mount();
  assert.equal(page.cards().length, 5);
  assert.equal(page.count("신체운동·건강"), "3");
  assert.equal(page.count("의사소통"), "2");
  assert.equal(page.count("사회관계"), "0");
  assert.ok(page.empty("사회관계"));
  // 영역 축은 원 설정을 따른다 — 화면에서 바꾸는 단추가 없다.
  assert.equal(page.button("놀이·일상생활"), undefined);
  assert.match(text(page.byClass("timeline")), /가아동/);
});

test("원이 놀이·일상생활이면 두 칸으로 시작한다", async (t) => {
  const page = harness(t, { configuredAxis: "DAILY_PLAY_2" });
  await page.mount();
  assert.equal(page.cards().length, 2);
  assert.equal(page.count("놀이활동"), "4");
  assert.equal(page.count("일상생활"), "1");
});

test("기관 기준을 해석할 수 없으면 기록 수로 추정하지 않고 5영역을 기본으로 둔다", async (t) => {
  const page = harness(t, { configuredAxis: "UNKNOWN_AXIS" });
  await page.mount();
  assert.equal(page.cards().length, 5);
});

test("전체 0건이면 칸을 0으로, 기록이 있는데 그 칸 키가 없으면 대시로 둔다", async (t) => {
  const none = harness(t, { children: [tracking(101, "가아동", {})] });
  await none.mount();
  for (const domain of axis.NURI_DOMAINS) assert.equal(none.count(domain), "0", domain);
  assert.match(none.text(), /아직 적은 기록이 없어요/);

  const old = harness(t, {
    children: [tracking(101, "가아동", { "신체운동·건강": 3, 놀이활동: 0 })],
  });
  await old.mount();
  assert.equal(old.count("신체운동·건강"), "3");
  assert.equal(old.count("의사소통"), "—");
  assert.ok(old.empty("의사소통"));
});

for (const { label, counts, play, life } of [
  { label: "두 영역 모두 명시적 0건", counts: { 놀이활동: 0, 일상생활: 0 }, play: "0", life: "0" },
  { label: "놀이활동만 제공", counts: { 놀이활동: 4 }, play: "4", life: "—" },
  {
    label: "다른 기준 기록만 있고 두 영역 키 없음",
    counts: { "신체운동·건강": 3 },
    play: "—",
    life: "—",
  },
]) {
  test(`놀이·일상생활 원은 항상 두 칸: ${label}`, async (t) => {
    const page = harness(t, {
      configuredAxis: "DAILY_PLAY_2",
      children: [tracking(101, "가아동", counts)],
    });
    await page.mount();
    assert.equal(page.cards().length, 2);
    assert.equal(page.count("놀이활동"), play);
    assert.equal(page.count("일상생활"), life);
  });
}

test("아이를 바꾸면 늦게 온 이전 아이 응답은 무시한다", async (t) => {
  const old = deferred();
  const page = harness(t, { observations: { 101: old.promise } });
  await page.mount();
  page.pickChild(102);
  assert.equal(page.byClass("timeline").length, 0);
  await page.flush();
  assert.match(text(page.byClass("timeline")), /나아동/);
  old.resolve(recordsFor(first));
  await page.flush();
  assert.doesNotMatch(text(page.byClass("timeline")), /가아동/);
});

test("머리의 링크는 관찰 기록으로 가는 하나뿐이고, 작성 링크들은 그 아이로 간다", async (t) => {
  const page = harness(t, { children: [tracking(101, "가아동", nuriZeros)] });
  await page.mount();
  const headLinks = nodes(page.header()).filter((node) => node?.type === "a");
  assert.deepEqual(
    headLinks.map((a) => a.props.href),
    ["/records"],
  );
  const link = nodes(page.byClass("emptyState")).find((node) => node?.type === "a");
  assert.equal(text(link), "기록 적으러 가기 →");
  assert.equal(link.props.href, "/records?class=class-10&child=child-101");
  const journal = page.byClass("journalGo")[0];
  assert.equal(text(journal), "관찰일지 작성 →");
  assert.equal(journal.props.href, "/records/journal?child=child-101");
});

test("오래 비어 있는 순 — 한 번도 없는 아이, 오래된 아이 순, 한 주 넘으면 D+", async (t) => {
  const kids = [
    { ...tracking(1, "다아이", { 의사소통: 1 }), last_date: "2026-11-04" },
    { ...tracking(2, "나아이", { 의사소통: 1 }), last_date: "2026-10-22" },
    { ...tracking(3, "가아이", {}), last_date: null },
  ];
  const page = harness(t, { children: kids });
  await page.mount();
  const names = () => page.byClass("note").map((n) => n.props["aria-label"].split(" ·")[0]);
  assert.deepEqual(names(), ["가아이", "나아이", "다아이"]);
  assert.deepEqual(page.byClass("flag").map(text), ["기록 없음", "D+14"]);
});

test("칠판 띠 말은 가장 오래 비어 있는 아이에 맞춘다", async (t) => {
  const { boardLine } = harness(t).module;
  const kid = (id, name, last) => ({ ...tracking(id, name, {}), last_date: last });
  const say = (kids) => {
    const line = boardLine(kids, TODAY);
    return line && `${line.lead}${line.names}${line.tail}|${line.sub}`;
  };
  assert.equal(say([]), null);
  assert.equal(
    say([kid(1, "가", "2026-11-04"), kid(2, "나", null)]),
    "아직 한 번도 못 적은 아이 — 나|",
  );
  assert.equal(
    say([kid(1, "가", "2026-10-22"), kid(2, "나", "2026-11-05")]),
    "한 주 넘게 못 본 아이 — 가|마지막 기록 14일 전",
  );
  assert.equal(
    say([kid(1, "가", "2026-10-22"), kid(2, "나", "2026-10-20")]),
    "한 주 넘게 못 본 아이 — 나 · 가|가장 오래된 기록 16일 전",
  );
  // 모두 사흘 안 — 「한 주 넘게」라고 하지 않는다.
  assert.equal(
    say([kid(1, "가", "2026-11-02"), kid(2, "나", "2026-11-04")]),
    "다음엔 가 차례예요|마지막 기록 3일 전",
  );
  assert.equal(say([kid(1, "가", TODAY)]), "오늘 모두 한 번씩 적었어요|");
  assert.equal(boardLine([kid(1, "가", TODAY)], TODAY).target, null);
});

test("집계 조회 중에는 0건 카드를 만들지 않고 성공한 0건 응답 뒤 두 카드를 표시한다", async (t) => {
  const request = deferred();
  const page = harness(t, {
    configuredAxis: "DAILY_PLAY_2",
    children: [tracking(101, "가아동", {})],
    trackingRequest: () => request.promise,
  });
  await page.mount();
  assert.equal(page.cards().length, 0);
  assert.match(page.text(), /불러오고 있어요/);
  request.resolve({ items: [tracking(101, "가아동", {})] });
  await page.flush();
  assert.equal(page.cards().length, 2);
  assert.equal(page.count("놀이활동"), "0");
  assert.equal(page.count("일상생활"), "0");
});

test("집계 조회 실패를 0건으로 표시하지 않고 기존 오류 상태를 유지한다", async (t) => {
  const page = harness(t, {
    configuredAxis: "DAILY_PLAY_2",
    trackingRequest: async () => {
      throw new Error("fixture tracking failure");
    },
  });
  await page.mount();
  assert.equal(page.cards().length, 0);
  assert.match(page.text(), /기록을 잠시 불러올 수 없어요/);
  assert.doesNotMatch(page.text(), /아직 남긴 기록이 없어요/);
});
