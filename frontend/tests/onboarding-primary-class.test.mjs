/**
 * 「내 담당 반」 — 화면이 보여준 반과 저장되는 반이 같은가.
 *
 * 담당 반 칸의 기본값은 마지막 확인의 「이대로 시작할게요」에서만 확정한다. 다른 단계의 입력·완료는
 * 저장된 primary를 보존하고, Routines의 strict 선택 규칙도 바꾸지 않는다.
 */
import assert from "node:assert/strict";
import { test } from "node:test";
import { registerHooks } from "node:module";
import { existsSync } from "node:fs";
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

// ── 마지막 확인 화면의 저장 규칙 (진짜 helper) ─────────────────────────────

const flow = await import("../lib/onboarding/flow.ts");

test("반이 둘 이상이면 이대로 시작할 때 화면에 보인 반이 주로 보는 반으로 저장된다", (t) => {
  browser({ rooms: [CLASS_A, CLASS_B] });
  t.after(() => delete globalThis.window);
  const stored = settings.loadClassSettings();
  assert.equal(flow.showsPrimarySelect(stored), true);

  const done = flow.finishedSettings(stored);
  assert.equal(done.primaryClassId, CLASS_A.id);
  assert.ok(done.completedAt);
  assert.equal(
    flow.finishedSettings({ ...stored, primaryClassId: CLASS_B.id }).primaryClassId,
    CLASS_B.id,
  );
});

test("반이 하나뿐이면 주로 보는 반 칸이 없고 저장값도 비워 둔다", (t) => {
  browser({ rooms: [CLASS_A] });
  t.after(() => delete globalThis.window);
  const stored = settings.loadClassSettings();
  assert.equal(flow.showsPrimarySelect(stored), false);
  assert.equal(flow.finishedSettings(stored).primaryClassId, "");
  assert.equal(settings.chosenClassFor(stored).id, CLASS_A.id, "고를 것이 없으니 그 반을 본다");
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
