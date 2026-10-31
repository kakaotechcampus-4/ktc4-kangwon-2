/**
 * 「내 담당 반」 — 화면이 보여준 반과 저장되는 반이 같은가.
 *
 * 담당 반 Select의 기본값은 그 form의 다음 제출에서만 확정한다. 다른 단계의 입력·완료는
 * 저장된 primary를 보존하고, Routines의 strict 선택 규칙도 바꾸지 않는다.
 */
import assert from "node:assert/strict";
import { test } from "node:test";
import { createRequire, registerHooks } from "node:module";
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

registerHooks({
  resolve(spec, ctx, next) {
    const url = spec.startsWith("@/")
      ? new URL(`../${spec.slice(2)}.ts`, import.meta.url)
      : spec.startsWith(".") && ctx.parentURL
        ? new URL(spec + ".ts", ctx.parentURL)
        : null;
    if (url && existsSync(fileURLToPath(url))) return { url: url.href, shortCircuit: true };
    return next(spec, ctx);
  },
});

const settings = await import("../lib/onboarding/settings.ts");
const types = await import("../lib/onboarding/types.ts");
const { API_STORAGE_CONTEXT } = await import("../lib/api/storage-context.ts");

const require = createRequire(import.meta.url);
const jsx = (type, props, key) => ({ type, props, key });
const runtime = { jsx, jsxs: jsx, Fragment: "fragment" };
const settle = () => new Promise((resolve) => setImmediate(resolve));
const EMAIL = "fixture@example.com";
const accountKey = `saessak.demoAccount:${encodeURIComponent(EMAIL)}`;
const linksKey = `saessak.apiLinks.v1:${API_STORAGE_CONTEXT}:${encodeURIComponent(EMAIL)}`;

const CLASS_A = {
  ...types.EMPTY_CLASS_SETTINGS.classes[0],
  id: "class-a",
  className: "국화반",
  teacherName: "선생님",
  selectedAges: [4],
};
const CLASS_B = { ...CLASS_A, id: "class-b", className: "난초반" };

/** 로그인한 브라우저. 저장은 **진짜 `saveClassSettings`** 로 한다. */
function browser({ rooms, primaryClassId = "" } = {}) {
  const values = new Map([
    [accountKey, JSON.stringify({ name: "선생님", email: EMAIL })],
    [linksKey, JSON.stringify({ classes: {}, children: {} })],
  ]);
  const local = {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
  };
  const session = new Map([
    ["saessak.demoSession", "active"],
    ["saessak.accountEmail", EMAIL],
  ]);
  const sessionStorage = {
    getItem: (key) => session.get(key) ?? null,
    setItem: (key, value) => session.set(key, value),
    removeItem: (key) => session.delete(key),
  };
  globalThis.localStorage = local;
  globalThis.sessionStorage = sessionStorage;
  globalThis.window = { localStorage: local, sessionStorage, dispatchEvent: () => true };
  if (rooms)
    settings.saveClassSettings({
      ...types.EMPTY_CLASS_SETTINGS,
      orgName: "기관",
      directorName: "원장",
      regionProvince: "강원특별자치도",
      regionDistrict: "춘천시",
      classes: rooms,
      primaryClassId,
    });
}

// ── 저장 규칙 (진짜 helper) ────────────────────────────────────────────────

test("고른 적이 없으면 저장값은 비어 있고, 화면은 첫 반을 보여준다", (t) => {
  browser({ rooms: [CLASS_A, CLASS_B] });
  t.after(() => delete globalThis.window);
  const stored = settings.loadClassSettings();

  assert.equal(stored.primaryClassId, "", "정규화가 첫 반을 몰래 채우면 안 된다");
  assert.equal(settings.chosenClassFor(stored), null);
  assert.equal(settings.shownPrimaryId(stored), CLASS_A.id, "칸은 첫 반을 고른 것처럼 보여준다");
});

test("화면이 보여준 반을 그대로 저장하면 둘이 같아진다", (t) => {
  browser({ rooms: [CLASS_A, CLASS_B] });
  t.after(() => delete globalThis.window);
  const stored = settings.loadClassSettings();
  const shown = settings.shownPrimaryId(stored);

  settings.saveClassSettings({ ...stored, primaryClassId: shown });
  const after = settings.loadClassSettings();
  assert.equal(after.primaryClassId, shown);
  assert.equal(settings.chosenClassFor(after).id, CLASS_A.id);
  assert.equal(settings.shownPrimaryId(after), shown, "다시 열어도 같은 반을 보여준다");
});

test("없어진 반을 가리키던 저장값은 보여주는 반으로 맞춰진다", (t) => {
  browser({ rooms: [CLASS_A, CLASS_B], primaryClassId: "class-gone" });
  t.after(() => delete globalThis.window);
  const stored = settings.loadClassSettings();
  assert.equal(stored.primaryClassId, "", "목록에 없는 반은 저장값에서 떨어진다");
  assert.equal(settings.shownPrimaryId(stored), CLASS_A.id);
});

test("반이 없으면 아무 반도 지어내지 않는다", (t) => {
  browser();
  t.after(() => delete globalThis.window);
  assert.equal(settings.shownPrimaryId({ ...types.EMPTY_CLASS_SETTINGS, classes: [] }), "");
});

// ── 온보딩 화면 (진짜 컴포넌트) ────────────────────────────────────────────

const compile = (path, modules) => {
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
  const compiled = { exports: {} };
  new Function("require", "module", "exports", code)(
    (name) => {
      assert.ok(name in modules, `unhandled import: ${name}`);
      return modules[name];
    },
    compiled,
    compiled.exports,
  );
  return compiled.exports;
};

const all = (node) => {
  if (Array.isArray(node)) return node.flatMap(all);
  if (node === null || node === undefined || typeof node === "boolean") return [];
  return typeof node === "object" ? [node, ...all(node.props?.children)] : [node];
};

/** React 흉내 하나. 이 화면은 훅 자리가 고정이라 한 상자면 된다. */
function host() {
  const slots = [];
  const effects = [];
  const pending = [];
  let cursor = 0;
  const state = (initial) => {
    const index = cursor++;
    if (!(index in slots))
      slots[index] = {
        v: typeof initial === "function" ? initial() : initial,
        set: (next) => {
          slots[index].v = typeof next === "function" ? next(slots[index].v) : next;
        },
      };
    return [slots[index].v, slots[index].set];
  };
  return {
    react: {
      useState: state,
      useRef: (initial) => state(() => ({ current: initial }))[0],
      useEffect: (fn, deps) => {
        const index = cursor++;
        if (
          !effects[index] ||
          !deps ||
          deps.some((d, i) => !Object.is(d, effects[index].deps[i]))
        ) {
          effects[index]?.cleanup?.();
          effects[index] = { deps: deps ?? [] };
          pending.push(() => {
            effects[index].cleanup = fn();
          });
        }
      },
    },
    cleanup: () => effects.forEach((e) => e?.cleanup?.()),
    mount(render) {
      let tree = null;
      const resolve = (node) => {
        if (Array.isArray(node)) return node.map(resolve);
        if (!node || typeof node !== "object") return node;
        if (typeof node.type === "function") return resolve(node.type(node.props));
        return { ...node, props: { ...node.props, children: resolve(node.props?.children) } };
      };
      const draw = () => {
        cursor = 0;
        tree = resolve(render());
      };
      draw();
      return {
        draw,
        tree: () => tree,
        async flush() {
          for (let i = 0; i < 5; i++) {
            draw();
            pending.splice(0).forEach((fn) => fn());
            await settle();
          }
          draw();
        },
      };
    },
  };
}

const passthrough = (tag) => (props) => jsx(tag, props);

function onboarding(
  t,
  { rooms = [CLASS_A, CLASS_B], primaryClassId = "", step = 2, search = "" } = {},
) {
  browser({ rooms, primaryClassId });
  t.after(() => delete globalThis.window);
  const pushed = [];
  // 렌더마다 새 객체를 주면 effect deps 가 매번 바뀌어 서버 목록이 입력을 덮는다.
  const router = { push: (href) => pushed.push(href) };
  const app = host();
  const Page = compile("../components/onboarding/OnboardingPage.tsx", {
    "react/jsx-runtime": runtime,
    react: app.react,
    "next/navigation": {
      __esModule: true,
      useRouter: () => router,
      useSearchParams: () => new URLSearchParams(search),
    },
    "@/lib/hooks/use-client-state": {
      __esModule: true,
      useHydrated: () => true,
    },
    "./AgeSelection": {
      __esModule: true,
      default: passthrough("age-selection"),
    },
    "./OnboardingLayout": {
      __esModule: true,
      default: ({ children }) => jsx("layout", { children }),
      StepFooter: ({ left, right }) => jsx("footer", { children: [left, right] }),
      StepHeading: ({ children }) => jsx("heading", { children }),
    },
    "./FormField": {
      __esModule: true,
      default: ({ label, children }) => jsx("field", { children: [label, children] }),
      TextInput: passthrough("text-input"),
    },
    "./Select": {
      __esModule: true,
      default: ({ id, value, options, onChange }) =>
        jsx("select", {
          id,
          value,
          onChange,
          children: (options ?? []).map((o) =>
            jsx("option", { value: o.value, children: o.label }),
          ),
        }),
    },
    "./ChildList": {
      __esModule: true,
      default: passthrough("child-list"),
    },
    "./CharacterMessageGrid": {
      __esModule: true,
      default: passthrough("character-grid"),
    },
    "./PrimaryButton": {
      __esModule: true,
      default: ({ children, onClick, disabled }) => jsx("button", { children, onClick, disabled }),
      GhostButton: ({ children, onClick, disabled }) =>
        jsx("button", { children, onClick, disabled }),
      TextButton: ({ children, onClick, disabled }) =>
        jsx("button", { children, onClick, disabled }),
    },
    // **진짜 저장·읽기 경로다.** 흉내 내면 이 어긋남이 다시 숨는다.
    "@/lib/onboarding/settings": settings,
    "@/lib/auth/local-account": {
      completeAccountOnboarding: () => true,
      onboardingDestination: () => "/onboarding/children",
    },
    "@/lib/onboarding/types": types,
    "@/lib/onboarding/regions": {
      PROVINCE_OPTIONS: [],
      districtsFor: () => ["춘천시"],
      normalizeProvince: (value) => value,
    },
    "@/lib/api/onboarding": {
      syncCenter: async () => {},
      syncClasses: async () => {},
      rememberConsent: () => {},
      hasConsent: () => false,
      migrateChildren: async () => {},
      loadServerClasses: async (current) => current,
      loadServerChildren: async (classroom) => classroom,
      addServerChild: async (_classroom, name) => ({ id: "child-fixture", name }),
      removeServerChild: async () => {},
    },
  }).default;

  const view = app.mount(() => Page({ step }));
  t.after(app.cleanup);
  const find = (type) => all(view.tree()).filter((node) => node?.type === type);
  return {
    flush: view.flush,
    draw: view.draw,
    pushed,
    tree: view.tree,
    find,
    primarySelect: () => find("select").find((node) => node.props.id === "primaryClassId"),
    field: (id) => find("text-input").find((node) => node.props.id === id),
    button: (label) =>
      find("button").find((node) => String([node.props.children].flat().join("")) === label),
    next: () =>
      find("button").find((node) => String([node.props.children].flat().join("")).includes("다음")),
    type: (node, value) => node.props.onChange({ target: { value } }),
  };
}

test("아무것도 고치지 않고 다음으로 넘어가도 화면에 보인 반이 저장된다", async (t) => {
  const view = onboarding(t);
  await view.flush();
  const shown = view.primarySelect().props.value;
  assert.equal(shown, CLASS_A.id, "칸은 첫 반을 고른 것처럼 보여준다");

  view.next().props.onClick();
  await view.flush();

  assert.equal(
    settings.loadClassSettings().primaryClassId,
    shown,
    "화면은 국화반인데 저장은 「없음」이다",
  );
  assert.equal(settings.chosenClassFor(settings.loadClassSettings()).id, CLASS_A.id);
});

test("담당 반을 바꾸면 보인 반과 저장된 반이 같이 바뀐다", async (t) => {
  const view = onboarding(t);
  await view.flush();
  view.type(view.primarySelect(), CLASS_B.id);
  await view.flush();
  assert.equal(view.primarySelect().props.value, CLASS_B.id);

  view.next().props.onClick();
  await view.flush();
  assert.equal(settings.loadClassSettings().primaryClassId, CLASS_B.id);
});

test("다시 열어도 저장한 반이 그대로 보인다", async (t) => {
  const view = onboarding(t, { primaryClassId: CLASS_B.id });
  await view.flush();
  assert.equal(view.primarySelect().props.value, CLASS_B.id);
});

test("없어진 담당 반은 담당 반 form의 다음에서 표시한 A로 확정된다", async (t) => {
  const view = onboarding(t, { primaryClassId: "class-gone" });
  await view.flush();
  assert.equal(settings.loadClassSettings().primaryClassId, "");
  assert.equal(view.primarySelect().props.value, CLASS_A.id);
  assert.equal(view.next().props.disabled, false);

  await view.next().props.onClick();
  await view.flush();
  assert.equal(settings.loadClassSettings().primaryClassId, CLASS_A.id);
  assert.deepEqual(view.pushed, ["/onboarding/children"]);
});

for (const primaryClassId of ["", CLASS_B.id]) {
  const label = primaryClassId ? "B" : "없음";

  test(`원 정보 다음은 담당 반 ${label}을 그대로 보존한다`, async (t) => {
    const view = onboarding(t, { step: 1, primaryClassId });
    await view.flush();
    assert.equal(view.primarySelect(), undefined, "담당 반 Select가 없는 단계다");
    assert.equal(view.next().props.disabled, false, "유효한 원 정보 form을 제출한다");

    await view.next().props.onClick();
    await view.flush();
    assert.equal(settings.loadClassSettings().primaryClassId, primaryClassId);
    assert.deepEqual(view.pushed, ["/onboarding/classes"]);
  });

  test(`원 정보 입력 수정 후 다음도 담당 반 ${label}을 확정하지 않는다`, async (t) => {
    const view = onboarding(t, { step: 1, primaryClassId });
    await view.flush();
    view.type(view.field("orgName"), "수정 기관");
    await view.flush();
    assert.equal(view.field("orgName").props.value, "수정 기관");

    await view.next().props.onClick();
    await view.flush();
    const saved = settings.loadClassSettings();
    assert.equal(saved.orgName, "수정 기관", "실제 patch와 저장 경로를 실행한다");
    assert.equal(saved.primaryClassId, primaryClassId);
  });

  for (const step of [3, 4]) {
    test(`${step}단계 설정 완료는 담당 반 ${label}을 그대로 보존한다`, async (t) => {
      const view = onboarding(t, { step, primaryClassId });
      await view.flush();
      assert.equal(view.primarySelect(), undefined);

      await view.button("설정 완료").props.onClick();
      await view.flush();
      const saved = settings.loadClassSettings();
      assert.equal(saved.primaryClassId, primaryClassId);
      assert.ok(saved.completedAt, "실제 finish 저장을 실행한다");
      assert.deepEqual(view.pushed, ["/"]);
    });
  }
}

test("아동 입력의 즉시 캐시 저장과 완료는 빈 담당 반을 보존한다", async (t) => {
  const view = onboarding(t, { step: 3 });
  await view.flush();
  assert.equal(view.primarySelect(), undefined);
  await view.find("child-list")[0].props.onAdd("검증 아동");
  await view.flush();
  assert.equal(view.find("child-list")[0].props.items.length, 1);
  assert.equal(settings.loadClassSettings().primaryClassId, "", "patch 즉시 저장도 보존한다");

  await view.button("설정 완료").props.onClick();
  await view.flush();
  assert.equal(settings.loadClassSettings().primaryClassId, "");
});

test("성품 인사 입력 수정 후 완료도 빈 담당 반을 보존한다", async (t) => {
  const view = onboarding(t, { step: 4 });
  await view.flush();
  view.find("character-grid")[0].props.onChange("3", "수정 인사");
  await view.flush();

  await view.button("설정 완료").props.onClick();
  await view.flush();
  const saved = settings.loadClassSettings();
  assert.equal(saved.characterMessages["3"], "수정 인사");
  assert.equal(saved.primaryClassId, "");
});

test("담당 반 form의 다른 입력이나 이전 버튼은 표시 기본값을 확정하지 않는다", async (t) => {
  const view = onboarding(t);
  await view.flush();
  assert.equal(view.primarySelect().props.value, CLASS_A.id);
  view.type(view.field(`className-${CLASS_A.id}`), "수정 국화반");
  await view.flush();

  await view.button("이전").props.onClick();
  await view.flush();
  const saved = settings.loadClassSettings();
  assert.equal(saved.classes[0].className, "수정 국화반");
  assert.equal(saved.primaryClassId, "", "이전은 담당 반 form 제출이 아니다");
  assert.deepEqual(view.pushed, ["/onboarding/center"]);
});

test("반 하나라 담당 반 Select가 없으면 다음에서 빈 primary를 채우지 않는다", async (t) => {
  const view = onboarding(t, { rooms: [CLASS_A] });
  await view.flush();
  assert.equal(view.primarySelect(), undefined);
  assert.equal(view.next().props.disabled, false);

  await view.next().props.onClick();
  await view.flush();
  assert.equal(settings.loadClassSettings().primaryClassId, "");
  assert.equal(settings.chosenClassFor(settings.loadClassSettings()), null);
});

test("온보딩 form을 제출하지 않은 직접 Routines scope는 strict no-primary를 유지한다", (t) => {
  browser({ rooms: [CLASS_A, CLASS_B] });
  t.after(() => delete globalThis.window);
  const saved = settings.loadClassSettings();
  assert.equal(settings.shownPrimaryId(saved), CLASS_A.id, "form 표시 정책은 유지한다");
  assert.equal(settings.primaryClassFor(saved).id, CLASS_A.id, "legacy fallback도 유지한다");
  assert.equal(
    settings.chosenClassFor(saved),
    null,
    "strict scope에 form 기본값을 주입하지 않는다",
  );
  assert.equal(settings.loadClassSettings().primaryClassId, "");
});

test("설정에서 들어오면 그 단계만 저장하고 설정으로 돌아간다", async (t) => {
  const view = onboarding(t, { step: 2, search: "from=settings" });
  await view.flush();

  const exit = view.button("저장하고 설정으로");
  assert.ok(exit, "설정에서 들어온 교사에게는 돌아가는 버튼이 보인다");
  exit.props.onClick();
  await view.flush();

  assert.deepEqual(view.pushed, ["/settings"], "아동 명단까지 걸어가지 않는다");
  assert.equal(settings.loadClassSettings().classes.length, 2, "반은 저장된다");
});

test("설정을 거치지 않으면 돌아가는 버튼이 없다", async (t) => {
  const view = onboarding(t, { step: 2 });
  await view.flush();
  assert.equal(view.button("저장하고 설정으로"), undefined);
});
