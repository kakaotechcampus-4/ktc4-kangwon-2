import { defineConfig, devices } from "@playwright/test";

/** 실제 Postgres · FastAPI · Next 스택을 먼저 기동한다. docs/structure.md 참조. */
export default defineConfig({
  testDir: "e2e",
  // CI 는 둘씩 돌린다 — e2e 가 CI 에서 가장 늦게 끝나는 잡이다. 테스트마다 새 계정과
  // 자기 원을 만들어서(e2e/onboarding.ts 「목록에 없어요」) 서로 같은 행을 안 본다.
  workers: process.env.CI ? 2 : 1,
  // 파일 안의 테스트도 나눈다. 안 나누면 가장 긴 routines.spec.ts 가 한 워커에 통째로 몰린다.
  // 테스트끼리 순서나 상태를 공유하지 않는다 — 각자 계정을 만든다.
  fullyParallel: !!process.env.CI,
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
  // 기준 창 1440 x 900 — 맥북 13·14인치 기본 보기. 배율은 100%(deviceScaleFactor 1).
  // 다른 크기를 봐야 하는 시험만 그 안에서 setViewportSize 로 바꾼다.
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1440, height: 900 },
        deviceScaleFactor: 1,
      },
    },
  ],
});
