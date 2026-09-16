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
