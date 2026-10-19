import { defineConfig, devices } from "@playwright/test";

// 띄워 둔 서버에 붙기만 한다(webServer 를 쓰지 않는다). DB·백엔드까지 세워야 해서
// Next 하나만 띄우는 webServer 로는 모자라다. CI 와 로컬이 같은 방식으로 돈다.
// 띄우는 법: docs/structure.md 「E2E」. ADR-028.
export default defineConfig({
  testDir: "e2e",
  // 가입부터 기록까지 한 줄로 이어지는 흐름이다. 병렬로 돌릴 것이 없다.
  workers: 1,
  forbidOnly: !!process.env.CI,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://127.0.0.1:3000",
    locale: "ko-KR",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
