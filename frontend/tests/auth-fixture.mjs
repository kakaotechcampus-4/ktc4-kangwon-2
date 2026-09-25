export const fixtureEmail = "fixture@example.com";
export const fixtureAccount = JSON.stringify({
  name: "선생님",
  email: fixtureEmail,
  salt: Array(16).fill(1),
  hash: "a".repeat(64),
});
export const fixtureKey = "saessak.demoAccount:fixture%40example.com";
export function fixtureSession() {
  const values = new Map([
    ["saessak.demoSession", "active"],
    ["saessak.accountEmail", fixtureEmail],
  ]);
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
  };
}

/**
 * `/api/auth/*` 만 가로채는 fetch 스텁.
 *
 * 로그인·회원가입 판정이 서버로 넘어가서(docs/api-spec.md §0) 이 함수들이 망을 탄다.
 * 브라우저 저장소 동작만 보는 테스트는 서버를 띄울 이유가 없으므로 여기서 흉내낸다.
 *
 * **가입한 이메일·비밀번호를 기억한다.** 무엇을 넣어도 통과시키면 「틀린 비밀번호를
 * 거부하나」를 보는 테스트가 통과해 버린다.
 *
 * 되돌리는 함수를 돌려준다 — 안 되돌리면 다음 테스트가 이 스텁을 쓴다.
 */
export function stubAuthFetch({ name = "선생님" } = {}) {
  const original = globalThis.fetch;
  const accounts = new Map();
  const json = (body, status) =>
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  const ok = (email, displayName) =>
    json({ token: "test-token", user: { id: 1, email, name: displayName, center_id: null } }, 200);

  globalThis.fetch = async (url, options = {}) => {
    const path = String(url);
    if (!path.includes("/api/auth/")) return original?.(url, options);
    const body = JSON.parse(options.body ?? "{}");
    const email = String(body.email ?? "").toLowerCase();

    if (path.endsWith("/signup")) {
      if (accounts.has(email))
        return json({ error: { code: "ALREADY_EXISTS", message: "", fields: ["email"] } }, 409);
      accounts.set(email, { password: body.password, name: body.name ?? name });
      return json(
        { token: "test-token", user: { id: 1, email, name: body.name ?? name, center_id: null } },
        201,
      );
    }

    const account = accounts.get(email);
    if (!account || account.password !== body.password)
      return json({ error: { code: "UNAUTHENTICATED", message: "", fields: [] } }, 401);
    return ok(email, account.name);
  };

  const restore = () => {
    globalThis.fetch = original;
  };
  // 이미 가입돼 있다고 치는 계정. 브라우저 저장소에 계정을 직접 넣고 로그인하는
  // 테스트가 쓴다 — 서버는 그 저장소를 볼 수 없다.
  // 테스트마다 계정을 비운다. 안 비우면 앞 테스트가 가입한 이메일이 남아 409 가 난다.
  restore.reset = () => {
    accounts.clear();
    return restore;
  };
  restore.seed = (email, password, displayName = name) => {
    accounts.set(String(email).toLowerCase(), { password, name: displayName });
    return restore;
  };
  return restore;
}
