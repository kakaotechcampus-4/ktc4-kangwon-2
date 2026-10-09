/**
 * 목업 스위치가 꺼진 배포에서 서비스워커와 워커 파일이 남지 않는지 본다.
 *
 * - MockProvider: enabled 일 때만 worker 를 띄우고, 꺼졌으면 남은 목업 워커만 골라 지운다.
 * - scripts/msw-worker.mjs: 워커 파일을 환경변수에 맞춰 만들거나 지운다.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const root = new URL("../", import.meta.url);
const read = (name) => readFileSync(new URL(name, root), "utf8").replace(/\r\n/g, "\n");
const settle = () => new Promise((resolve) => setImmediate(resolve));

// 실제 TSX 를 돌린다. React renderer 는 없고 hook 만 흉내 낸다.
const code = require("next/dist/compiled/babel/core").transformSync(read("msw/MockProvider.tsx"), {
  filename: "MockProvider.tsx",
  babelrc: false,
  configFile: false,
  presets: [
    [require("next/dist/compiled/babel/preset-env"), { targets: { node: "current" } }],
    [require("next/dist/compiled/babel/preset-react"), { runtime: "automatic" }],
    require("next/dist/compiled/babel/preset-typescript"),
  ],
}).code;

/** scriptURL 만 들고 있는 최소 등록 객체. unregister 호출 여부를 기록한다. */
function registration(scriptURL, slot = "active") {
  const reg = { active: null, waiting: null, installing: null, unregistered: false };
  reg[slot] = { scriptURL };
  reg.unregister = async () => {
    reg.unregistered = true;
    return true;
  };
  return reg;
}

/** node 22 의 globalThis.navigator 는 getter 라 대입이 막혀 있다. */
const setNavigator = (value) =>
  Object.defineProperty(globalThis, "navigator", { value, configurable: true, writable: true });

/**
 * mocking 값을 정해 MockProvider 를 평가하고, effect 까지 한 번 돌린다.
 * `enabled` 는 모듈 최상단에서 읽히므로 평가 전에 환경변수를 세워야 한다.
 */
async function render(t, { mocking, registrations = [], session = new Map() }) {
  const previous = process.env.NEXT_PUBLIC_API_MOCKING;
  process.env.NEXT_PUBLIC_API_MOCKING = mocking;

  let reloads = 0;
  const started = [];
  setNavigator({
    serviceWorker: { controller: null, getRegistrations: async () => registrations },
  });
  // 새로고침 1회 제한은 sessionStorage 로 묶여 있다 — 탭 하나를 흉내 내려면 같은 Map 을 넘긴다.
  globalThis.sessionStorage = {
    getItem: (k) => session.get(k) ?? null,
    setItem: (k, v) => session.set(k, String(v)),
    removeItem: (k) => session.delete(k),
  };
  globalThis.window = {
    sessionStorage: globalThis.sessionStorage,
    location: {
      reload: () => {
        reloads += 1;
      },
    },
  };
  t.after(() => {
    process.env.NEXT_PUBLIC_API_MOCKING = previous;
    delete globalThis.navigator;
    delete globalThis.window;
    delete globalThis.sessionStorage;
  });

  const effects = [];
  const modules = {
    react: {
      useState: (initial) => [typeof initial === "function" ? initial() : initial, () => {}],
      useEffect: (fn) => {
        effects.push(fn);
      },
    },
    "react/jsx-runtime": {
      jsx: (type, props) => ({ type, props }),
      jsxs: (type, props) => ({ type, props }),
      Fragment: "fragment",
    },
    "./browser": {
      startMockWorker: async () => {
        started.push(1);
      },
    },
  };
  const compiled = { exports: {} };
  new Function("require", "module", "exports", code)(
    (name) => {
      assert.ok(name in modules, `unhandled import: ${name}`);
      return modules[name];
    },
    compiled,
    compiled.exports,
  );
  compiled.exports.default({ children: "CHILD" });
  effects.forEach((fn) => fn());
  for (let i = 0; i < 5; i++) await settle();
  return {
    started,
    session,
    get reloads() {
      return reloads;
    },
    get flag() {
      return session.get(RELOAD_KEY) ?? null;
    },
  };
}

/** 새로고침을 세션당 한 번으로 묶는 표시. MockProvider 와 같은 키를 쓴다. */
const RELOAD_KEY = "saessak.msw.cleanupReload";

const MOCK_URL = "http://localhost:3000/mockServiceWorker.js";

test("mocking=enabled 면 worker 를 시작하고 남은 등록을 지우지 않는다", async (t) => {
  const mock = registration(MOCK_URL);
  const page = await render(t, { mocking: "enabled", registrations: [mock] });
  assert.equal(page.started.length, 1, "startMockWorker 가 실행된다");
  assert.equal(mock.unregistered, false, "켜진 환경에서는 워커를 지우지 않는다");
  assert.equal(page.reloads, 0);
  assert.equal(page.flag, null, "켜진 환경에서는 새로고침 표시도 건드리지 않는다");
});

test("mocking=disabled 면 worker 를 시작하지 않고 남은 목업 워커를 지운다", async (t) => {
  const mock = registration(MOCK_URL);
  const page = await render(t, { mocking: "disabled", registrations: [mock] });
  assert.equal(page.started.length, 0, "startMockWorker 가 실행되지 않는다");
  assert.equal(mock.unregistered, true);
  assert.equal(page.reloads, 1, "지운 뒤 한 번 새로고침해 제어권을 떼어낸다");
  assert.equal(page.flag, "1", "이번 세션에서 새로고침했다는 표시를 남긴다");
});

test("새로고침 뒤 목업 워커가 사라졌으면 표시를 지운다", async (t) => {
  const session = new Map();
  const before = await render(t, {
    mocking: "disabled",
    registrations: [registration(MOCK_URL)],
    session,
  });
  assert.equal(before.reloads, 1);
  assert.equal(before.flag, "1");

  // 새로고침 뒤 다시 뜬 화면 — 이제 남은 목업 워커가 없다.
  const after = await render(t, { mocking: "disabled", registrations: [], session });
  assert.equal(after.reloads, 0, "지울 것이 없으면 새로고침하지 않는다");
  assert.equal(after.flag, null, "다음에 또 남으면 다시 한 번 새로고침할 수 있게 표시를 치운다");
});

test("지워도 목업 워커가 남으면 두 번째 새로고침은 하지 않는다", async (t) => {
  const session = new Map();
  // unregister 가 먹지 않아 등록이 그대로 남는 드문 상황을 흉내 낸다.
  const first = await render(t, {
    mocking: "disabled",
    registrations: [registration(MOCK_URL)],
    session,
  });
  assert.equal(first.reloads, 1);

  const second = await render(t, {
    mocking: "disabled",
    registrations: [registration(MOCK_URL)],
    session,
  });
  assert.equal(second.reloads, 0, "무한 새로고침을 만들지 않는다");
  assert.equal(second.flag, "1", "표시는 그대로 둔다");

  const third = await render(t, {
    mocking: "disabled",
    registrations: [registration(MOCK_URL)],
    session,
  });
  assert.equal(third.reloads, 0, "같은 세션에서는 몇 번을 다시 열어도 새로고침하지 않는다");
});

test("enabled 가 아닌 값은 모두 목업 꺼짐으로 본다", async (t) => {
  for (const mocking of ["false", "true", "", "(unset)"]) {
    const mock = registration(MOCK_URL);
    const page = await render(t, { mocking, registrations: [mock] });
    assert.equal(page.started.length, 0, `mocking=${mocking}`);
    assert.equal(mock.unregistered, true, `mocking=${mocking}`);
  }
});

test("목업이 아닌 서비스워커는 건드리지 않는다", async (t) => {
  const other = registration("http://localhost:3000/firebase-messaging-sw.js");
  const page = await render(t, { mocking: "disabled", registrations: [other] });
  assert.equal(other.unregistered, false);
  assert.equal(page.reloads, 0, "지운 것이 없으면 새로고침하지 않는다");
  assert.equal(page.flag, null, "목업이 아닌 워커는 새로고침 표시도 남기지 않는다");
});

test("지울 워커가 없거나 조회가 실패해도 화면을 막지 않는다", async (t) => {
  const empty = await render(t, { mocking: "disabled", registrations: [] });
  assert.equal(empty.reloads, 0);

  const previous = process.env.NEXT_PUBLIC_API_MOCKING;
  process.env.NEXT_PUBLIC_API_MOCKING = "disabled";
  setNavigator({
    serviceWorker: {
      getRegistrations: async () => {
        throw new Error("denied");
      },
    },
  });
  globalThis.window = {
    location: {
      reload: () => {
        throw new Error("새로고침하면 안 된다");
      },
    },
  };
  t.after(() => {
    process.env.NEXT_PUBLIC_API_MOCKING = previous;
    delete globalThis.navigator;
    delete globalThis.window;
  });
  const effects = [];
  const compiled = { exports: {} };
  new Function("require", "module", "exports", code)(
    (name) =>
      ({
        react: {
          useState: (i) => [typeof i === "function" ? i() : i, () => {}],
          useEffect: (fn) => effects.push(fn),
        },
        "react/jsx-runtime": { jsx: () => ({}), jsxs: () => ({}), Fragment: "f" },
        "./browser": { startMockWorker: async () => {} },
      })[name],
    compiled,
    compiled.exports,
  );
  compiled.exports.default({ children: "CHILD" });
  effects.forEach((fn) => fn());
  for (let i = 0; i < 5; i++) await settle();
});

const SCRIPT = fileURLToPath(new URL("scripts/msw-worker.mjs", root));

/**
 * 임시 프로젝트를 만들고 그 안에서 워커 동기화 스크립트를 돌린다.
 * .env 파일은 next 가 찾는 자리(프로젝트 루트)에 그대로 놓는다.
 */
function project(t, { envFiles = {}, worker = false } = {}) {
  const dir = mkdtempSync(join(tmpdir(), "msw-project-"));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  for (const [name, body] of Object.entries(envFiles)) writeFileSync(join(dir, name), body);

  const target = join(dir, "public", "mockServiceWorker.js");
  if (worker) {
    mkdirSync(join(dir, "public"), { recursive: true });
    writeFileSync(target, "stale");
  }

  return {
    target,
    /** mocking 을 주면 쉘에서 넘긴 값, 안 주면 쉘에는 없는 상태. dev 는 predev 쪽. */
    run({ mocking, dev = false } = {}) {
      const env = { ...process.env };
      delete env.NEXT_PUBLIC_API_MOCKING;
      if (mocking !== undefined) env.NEXT_PUBLIC_API_MOCKING = mocking;
      const args = dev ? ["--dev", dir] : [dir];
      return execFileSync(process.execPath, [SCRIPT, ...args], { env, encoding: "utf8" });
    },
  };
}

test("워커 파일 동기화 스크립트는 mocking 값에 따라 만들고 지운다", (t) => {
  const app = project(t);
  app.run({ mocking: "enabled" });
  assert.ok(existsSync(app.target), "enabled 면 워커 파일을 만든다");
  assert.match(readFileSync(app.target, "utf8"), /Mock Service Worker/i);

  for (const mocking of ["disabled", "false", ""]) {
    writeFileSync(app.target, "stale");
    app.run({ mocking });
    assert.equal(
      existsSync(app.target),
      false,
      `mocking=${mocking || "(빈 값)"} 이면 남기지 않는다`,
    );
  }

  writeFileSync(app.target, "stale");
  app.run();
  assert.equal(existsSync(app.target), false, "값이 없는 배포에서도 지운다");
});

// ── .env 파일 ──────────────────────────────────────────────────────────────
// predev 는 next 보다 먼저 돈다. 스크립트가 .env 를 직접 읽지 않으면 값이 비어 보여서,
// .env.local 에 enabled 를 적어둔 보통의 로컬 개발에서 워커 파일을 지워버린다.

test(".env.local 의 enabled 를 읽어 워커 파일을 만든다", (t) => {
  const app = project(t, { envFiles: { ".env.local": "NEXT_PUBLIC_API_MOCKING=enabled\n" } });
  app.run({ dev: true });
  assert.ok(existsSync(app.target), "쉘에 값이 없어도 .env.local 을 보고 만든다");
  assert.match(readFileSync(app.target, "utf8"), /Mock Service Worker/i);
});

test(".env.local 의 disabled 를 읽어 남아 있던 워커 파일을 지운다", (t) => {
  const app = project(t, {
    envFiles: { ".env.local": "NEXT_PUBLIC_API_MOCKING=disabled\n" },
    worker: true,
  });
  app.run({ dev: true });
  assert.equal(existsSync(app.target), false);
});

test("쉘에서 넘긴 값이 .env.local 보다 세다 — next 와 같은 우선순위", (t) => {
  const off = project(t, {
    envFiles: { ".env.local": "NEXT_PUBLIC_API_MOCKING=enabled\n" },
    worker: true,
  });
  off.run({ dev: true, mocking: "disabled" });
  assert.equal(existsSync(off.target), false, "쉘의 disabled 가 파일의 enabled 를 이긴다");

  const on = project(t, { envFiles: { ".env.local": "NEXT_PUBLIC_API_MOCKING=disabled\n" } });
  on.run({ dev: true, mocking: "enabled" });
  assert.ok(existsSync(on.target), "쉘의 enabled 가 파일의 disabled 를 이긴다");
});

test(".env.local 이 .env 보다 세다 — next 와 같은 우선순위", (t) => {
  const off = project(t, {
    envFiles: {
      ".env": "NEXT_PUBLIC_API_MOCKING=enabled\n",
      ".env.local": "NEXT_PUBLIC_API_MOCKING=disabled\n",
    },
    worker: true,
  });
  off.run({ dev: true });
  assert.equal(
    existsSync(off.target),
    false,
    ".env.local 의 disabled 가 .env 의 enabled 를 이긴다",
  );

  const on = project(t, {
    envFiles: {
      ".env": "NEXT_PUBLIC_API_MOCKING=disabled\n",
      ".env.local": "NEXT_PUBLIC_API_MOCKING=enabled\n",
    },
  });
  on.run({ dev: true });
  assert.ok(existsSync(on.target), ".env.local 의 enabled 가 .env 의 disabled 를 이긴다");
});

test("predev 와 prebuild 가 보는 env 파일이 next 와 같다", (t) => {
  const app = project(t, {
    envFiles: {
      ".env.development": "NEXT_PUBLIC_API_MOCKING=enabled\n",
      ".env.production": "NEXT_PUBLIC_API_MOCKING=disabled\n",
    },
  });
  app.run({ dev: true });
  assert.ok(existsSync(app.target), "predev 는 .env.development 를 본다");

  app.run();
  assert.equal(
    existsSync(app.target),
    false,
    "prebuild 는 .env.production 을 본다 — 배포본에 안 남는다",
  );
});

test("env 파일이 하나도 없으면 지운다", (t) => {
  const app = project(t, { worker: true });
  app.run({ dev: true });
  assert.equal(existsSync(app.target), false);
});

test("워커 파일은 git 산출물이 아니고 build 전에 정리된다", () => {
  const pkg = JSON.parse(read("package.json"));
  assert.equal(pkg.scripts.predev, "node scripts/msw-worker.mjs --dev");
  assert.equal(pkg.scripts.prebuild, "node scripts/msw-worker.mjs");
  assert.equal(pkg.scripts.dev, "next dev", "기존 dev 명령은 그대로 둔다");
  assert.equal(pkg.scripts.build, "next build", "기존 build 명령은 그대로 둔다");
  assert.match(read(".gitignore"), /^\/public\/mockServiceWorker\.js$/m);
});
