import assert from "node:assert/strict";
import { test } from "node:test";
import { registerHooks } from "node:module";
registerHooks({
  resolve(specifier, context, nextResolve) {
    if (specifier === "./demo-session") return nextResolve("./demo-session.ts", context);
    if (specifier === "./account-store") return nextResolve("./account-store.ts", context);
    if (
      specifier === "../onboarding/types" ||
      specifier === "../onboarding/settings" ||
      specifier === "./types" ||
      specifier === "../auth/demo-session"
    )
      return nextResolve(specifier + ".ts", context);
    return nextResolve(specifier, context);
  },
});
const { registerAccount, verifyAccount, accountName, loginDestination, completeAccountOnboarding } =
  await import("../lib/auth/local-account.ts");
const { accountStorageKey, startDemoSession } = await import("../lib/auth/demo-session.ts");

test("registration, credential checks, duplicate registration and safe password storage", async () => {
  const values = new Map();
  globalThis.localStorage = {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
  };
  const session = new Map();
  globalThis.window = {
    localStorage,
    sessionStorage: {
      getItem: (key) => session.get(key) ?? null,
      setItem: (key, value) => session.set(key, value),
      removeItem: (key) => session.delete(key),
    },
  };
  // 가입 전 남아 있던 반 설정은 새 계정의 온보드 완료로 간주하지 않는다.
  values.set("saessak.classSettings", JSON.stringify({ completedAt: "2026-09-01" }));
  assert.equal(loginDestination(), "/onboarding/center");
  await assert.rejects(registerAccount("", "bad", "short"));
  await registerAccount(" 민지 ", "Teacher@example.com", "demo-password-123");
  assert.equal(loginDestination(), "/onboarding/center");
  await verifyAccount("teacher@example.com", "demo-password-123");
  assert.equal(startDemoSession(), true);
  assert.equal(accountName(), "민지");
  assert.equal(loginDestination(), "/onboarding/center");
  // 설정을 마치기 전에 재로그인해도 초기 설정으로 안내한다.
  await verifyAccount("teacher@example.com", "demo-password-123");
  assert.equal(startDemoSession(), true);
  assert.equal(loginDestination(), "/onboarding/center");
  values.set(
    accountStorageKey("saessak.classSettings"),
    JSON.stringify({
      orgName: "기관",
      directorName: "원장",
      regionProvince: "서울특별시",
      regionDistrict: "강남구",
      classes: [{ id: "c", className: "반", teacherName: "담임", ageGroup: "3" }],
    }),
  );
  assert.equal(completeAccountOnboarding(), true);
  await verifyAccount("teacher@example.com", "demo-password-123");
  assert.equal(startDemoSession(), true);
  assert.equal(loginDestination(), "/");
  await assert.rejects(verifyAccount("teacher@example.com", "wrong-password"));
  await assert.rejects(verifyAccount("other@example.com", "demo-password-123"));
  await assert.rejects(registerAccount("중복", "TEACHER@example.com", "demo-password-456"));
  const firstKey = accountStorageKey("saessak.classSettings");
  values.set(
    firstKey,
    JSON.stringify({
      orgName: "기관",
      directorName: "원장",
      regionProvince: "세종특별자치시",
      regionDistrict: "세종특별자치시",
      classes: [{ id: "c", className: "반", teacherName: "담임", ageGroup: "3" }],
    }),
  );
  await registerAccount("다른 선생님", "other@example.com", "demo-password-456");
  await verifyAccount("other@example.com", "demo-password-456");
  assert.equal(startDemoSession(), true);
  assert.equal(accountName(), "다른 선생님");
  assert.equal(loginDestination(), "/onboarding/center");
  assert.notEqual(accountStorageKey("saessak.classSettings"), firstKey);
  assert.equal(values.get(accountStorageKey("saessak.classSettings")), undefined);
  await verifyAccount("teacher@example.com", "demo-password-123");
  assert.equal(startDemoSession(), true);
  assert.equal(loginDestination(), "/");
  assert.equal(JSON.parse(values.get(accountStorageKey("saessak.classSettings"))).orgName, "기관");
  assert.equal(
    [...values.values()].some((value) => value.includes("demo-password-123")),
    false,
  );
  // 이전 단일 계정 형식의 설정과 문서도 로그인 시 유실 없이 이전한다.
  const credentialKey = "saessak.demoAccount:teacher%40example.com";
  values.set("saessak.demoAccount", values.get(credentialKey));
  values.delete(credentialKey);
  values.delete(firstKey);
  values.set("saessak.workspace.v1", "legacy documents");
  await verifyAccount("teacher@example.com", "demo-password-123");
  assert.equal(startDemoSession(), true);
  assert.equal(values.get(firstKey), values.get("saessak.classSettings"));
  assert.equal(values.get(accountStorageKey("saessak.workspace.v1")), "legacy documents");
  assert.equal(loginDestination(), "/onboarding/center");
  delete globalThis.localStorage;
  delete globalThis.window;
});
