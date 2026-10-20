import { defineConfig, devices } from "@playwright/test";

/** 실제 Postgres · FastAPI · Next 스택을 먼저 기동한다. docs/structure.md 참조. */
export default defineConfig({
  testDir: "e2e",
  workers: 1,
  forbidOnly: !!process.env.CI,
  timeout: 90_000,
  expect: { timeout: 15_000 },
  // CI 러너가 느려 한 번 미끄러질 수 있다. 두 번 연속 실패해야 빨간불이다.
  retries: process.env.CI ? 1 : 0,
  // CI 에서는 HTML 보고서와 json 을 남긴다 — 실패를 나중에 열어봐야 한다.
  reporter: process.env.CI
    ? [["list"], ["html", { open: "never" }], ["json", { outputFile: "test-results/results.json" }]]
    : "list",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://127.0.0.1:3000",
    locale: "ko-KR",
    timezoneId: "Asia/Seoul",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    actionTimeout: 15_000,
    navigationTimeout: 20_000,
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
