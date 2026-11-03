import assert from "node:assert/strict";
import { test } from "node:test";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";

const require = createRequire(import.meta.url);
const axis = await import("../lib/workspace/observation-axis.ts");
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
  const Page = compile("../components/workspace/ChildTrackingPage.tsx", {
    "react/jsx-runtime": runtime,
    react: hooks,
    "next/link": { __esModule: true, default: "a" },
    "@/lib/api/auth": auth,
    "@/lib/api/onboarding": { CLASS_PREFIX: "class-", CHILD_PREFIX: "child-" },
    "@/lib/api/classes": {
      getClasses: async () => ({
        items: [
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
    "@/components/app/icons": { Icon: "icon" },
    "./DocumentArchiveArt": new Proxy({}, { get: () => "decoration" }),
    "./ChildTrackingArt": new Proxy({}, { get: () => "tracking-art" }),
    "./WorkspaceUI": { Message: "message" },
    "./ChildTracking.module.css": {
      __esModule: true,
      default: new Proxy({}, { get: (_, name) => name }),
    },
  }).default;
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
    calls,
    render,
    flush,
    byClass,
    mount: async () => {
      for (let i = 0; i < 4; i++) await flush();
    },
    text: () => text(tree),
    button: (label) => nodes(tree).find((node) => node?.type === "button" && text(node) === label),
    cards: () => byClass("domainCard"),
    count(domain) {
      const card = byClass("domainCard").find((node) =>
        nodes(node).some((n) => n?.type === "p" && text(n) === domain),
      );
      return text(nodes(card).find((node) => node?.type === "strong"));
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
    pickClass(id) {
      nodes(tree)
        .find((node) => node?.type === "select")
        .props.onChange({ target: { value: String(id) } });
      render();
    },
    header: () => nodes(tree).find((node) => node?.type === "header"),
  };
}

test("5영역·2영역은 서버의 실제 수만 표시하며 전환해도 전체 타임라인은 유지한다", async (t) => {
  const page = harness(t);
  await page.mount();
  assert.equal(page.cards().length, 5);
  assert.equal(page.count("신체운동·건강"), "3건");
  assert.equal(page.count("의사소통"), "2건");
  const timeline = text(page.byClass("timeline"));
  const calls = [...page.calls];
  page.button("놀이·일상생활").props.onClick();
  await page.flush();
  assert.equal(page.cards().length, 2);
  assert.equal(page.count("놀이활동"), "4건");
  assert.equal(page.count("일상생활"), "1건");
  assert.equal(text(page.byClass("timeline")), timeline);
  assert.deepEqual(page.calls, calls); // 모드 전환은 요청·기관 설정 저장을 만들지 않는다.
  page.button("누리과정 5영역").props.onClick();
  page.render();
  assert.equal(page.cards().length, 5);
});

test("기관이 놀이·일상생활을 쓰면 그 모드로 시작한다", async (t) => {
  const page = harness(t, { configuredAxis: "DAILY_PLAY_2" });
  await page.mount();
  assert.equal(page.button("놀이·일상생활").props["aria-pressed"], true);
  assert.equal(page.cards().length, 2);
});

test("전체 0건이면 다른 기준의 영역 키가 없어도 두 카드를 0건으로 표시한다", async (t) => {
  const child = tracking(101, "가아동", nuriZeros);
  const page = harness(t, { children: [child] });
  await page.mount();
  assert.equal(page.count("신체운동·건강"), "0건");
  page.button("놀이·일상생활").props.onClick();
  page.render();
  assert.equal(page.cards().length, 2);
  assert.equal(page.count("놀이활동"), "0건");
  assert.equal(page.count("일상생활"), "0건");
  for (const card of page.cards()) assert.match(text(card), /아직 기록 없음/);
  assert.equal(page.byClass("domainNotice").length, 0);
  assert.match(page.text(), /아직 남긴 기록이 없어요/);
  page.button("누리과정 5영역").props.onClick();
  page.render();
  assert.equal(page.cards().length, 5);
  assert.equal(page.count("신체운동·건강"), "0건");
});

test("과거 기준의 일부 영역만 있으면 없는 집계를 대시로 표시한다", async (t) => {
  const child = tracking(101, "가아동", { "신체운동·건강": 3, 놀이활동: 0, 일상생활: 0 });
  const page = harness(t, { configuredAxis: "DAILY_PLAY_2", children: [child] });
  await page.mount();
  assert.equal(page.count("놀이활동"), "0건");
  page.button("누리과정 5영역").props.onClick();
  page.render();
  assert.equal(page.cards().length, 5);
  assert.equal(page.count("신체운동·건강"), "3건");
  assert.equal(page.count("의사소통"), "—");
  assert.match(page.text(), /집계 정보 없음/);
});

test("아동 변경은 모드를 유지하고 늦은 이전 아동 응답을 무시하며 반 변경은 기본으로 돌아간다", async (t) => {
  const old = deferred();
  const page = harness(t, { observations: { 101: old.promise } });
  await page.mount();
  page.button("놀이·일상생활").props.onClick();
  page.render();
  page.pickChild(102);
  assert.equal(page.byClass("timeline").length, 0);
  assert.equal(page.count("놀이활동"), "2건");
  await page.flush();
  assert.match(text(page.byClass("timeline")), /나아동/);
  old.resolve(recordsFor(first));
  await page.flush();
  assert.doesNotMatch(text(page.byClass("timeline")), /가아동/);
  assert.equal(page.button("놀이·일상생활").props["aria-pressed"], true);
  page.pickClass(20);
  assert.equal(page.byClass("summaryText").length, 0);
  await page.flush();
  assert.equal(page.button("누리과정 5영역").props["aria-pressed"], true);
  assert.match(text(page.byClass("summaryText")), /다아동/);
});

test("늦게 도착한 기관 설정은 사용자가 선택한 모드를 덮어쓰지 않는다", async (t) => {
  const settings = deferred();
  const page = harness(t, { settings: settings.promise });
  await page.mount();
  assert.equal(page.button("누리과정 5영역").props["aria-pressed"], true);
  page.button("누리과정 5영역").props.onClick();
  page.render();
  settings.resolve({ observation_axis: "DAILY_PLAY_2" });
  await page.flush();
  assert.equal(page.button("누리과정 5영역").props["aria-pressed"], true);
  page.pickClass(20);
  await page.flush();
  assert.equal(page.button("놀이·일상생활").props["aria-pressed"], true);
});

test("상단 작성 링크는 없고 하단 빈 상태의 선택 아동 작성 링크는 유지한다", async (t) => {
  const page = harness(t, { children: [tracking(101, "가아동", nuriZeros)] });
  await page.mount();
  assert.equal(nodes(page.header()).filter((node) => node?.type === "a").length, 0);
  const link = nodes(page.byClass("emptyState")).find((node) => node?.type === "a");
  assert.equal(text(link), "관찰 기록 남기기 →");
  assert.equal(link.props.href, "/records?class=class-10&child=child-101");
  assert.equal(page.byClass("avatar").length, 0);
  assert.equal(page.byClass("summaryAvatar").length, 0);
});

test("기관 기준을 해석할 수 없으면 기록 수로 추정하지 않고 5영역을 기본으로 둔다", async (t) => {
  const page = harness(t, { configuredAxis: "UNKNOWN_AXIS" });
  await page.mount();
  assert.equal(page.button("누리과정 5영역").props["aria-pressed"], true);
  assert.equal(page.cards().length, 5);
});

for (const { label, counts, play, life } of [
  {
    label: "두 영역 모두 명시적 0건",
    counts: { 놀이활동: 0, 일상생활: 0 },
    play: "0건",
    life: "0건",
  },
  { label: "놀이활동만 제공", counts: { 놀이활동: 4 }, play: "4건", life: "—" },
  { label: "일상생활만 제공", counts: { 일상생활: 2 }, play: "—", life: "2건" },
  {
    label: "두 영역 모두 기록 있음",
    counts: { 놀이활동: 4, 일상생활: 1 },
    play: "4건",
    life: "1건",
  },
  {
    label: "다른 기준 기록만 있고 두 영역 키 없음",
    counts: { "신체운동·건강": 3 },
    play: "—",
    life: "—",
  },
]) {
  test(`놀이·일상생활은 항상 두 카드 유지: ${label}`, async (t) => {
    const child = tracking(101, "가아동", counts);
    const page = harness(t, { children: [child] });
    await page.mount();
    const before = text(page.byClass("timeline"));
    page.button("놀이·일상생활").props.onClick();
    page.render();
    assert.equal(page.cards().length, 2);
    assert.equal(page.count("놀이활동"), play);
    assert.equal(page.count("일상생활"), life);
    assert.equal(page.byClass("domainNotice").length, 0);
    assert.equal(text(page.byClass("timeline")), before);
    if (play === "—" || life === "—") assert.match(text(page.cards()), /기록 정보 없음/);
  });
}

const playZeros = Object.fromEntries(axis.DAILY_PLAY_DOMAINS.map((domain) => [domain, 0]));
for (const { label, counts, expected, hint } of [
  {
    label: "놀이·일상생활 기관에서 그 기준 기록만 있음",
    counts: { ...playZeros, 놀이활동: 2, 일상생활: 2 },
    expected: "—",
    hint: /집계 정보 없음/,
  },
  {
    label: "놀이·일상생활 기관에서 전체 0건",
    counts: playZeros,
    expected: "0건",
    hint: /아직 기록 없음/,
  },
]) {
  test(`누리과정 5영역은 항상 다섯 카드 유지: ${label}`, async (t) => {
    const child = tracking(101, "가아동", counts);
    const page = harness(t, { configuredAxis: "DAILY_PLAY_2", children: [child] });
    await page.mount();
    const before = text(page.byClass("timeline"));
    page.button("누리과정 5영역").props.onClick();
    page.render();
    assert.equal(page.cards().length, 5);
    for (const domain of axis.NURI_DOMAINS) assert.equal(page.count(domain), expected, domain);
    assert.match(text(page.cards()), hint);
    assert.equal(page.byClass("domainNotice").length, 0);
    assert.doesNotMatch(page.text(), /이 기준으로 작성된 관찰 기록이 없어요/);
    // 실제 기록 수 · 전체 타임라인은 그대로다.
    assert.equal(text(page.byClass("timeline")), before);
    page.button("놀이·일상생활").props.onClick();
    page.render();
    assert.equal(page.cards().length, 2);
    assert.equal(page.count("놀이활동"), `${counts.놀이활동}건`);
  });
}

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
  assert.equal(page.count("놀이활동"), "0건");
  assert.equal(page.count("일상생활"), "0건");
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
