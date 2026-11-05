import { expect, test, type Page } from "@playwright/test";
import { readFile, writeFile } from "node:fs/promises";
import { resetTestData, read } from "../msw/data/store";
import { addCenter } from "../msw/data/centers";
import { addClass } from "../msw/data/classes";
import { addChild } from "../msw/data/children";
import { addPlan } from "../msw/data/annual-plans";

test.skip(process.env.E2E_ARCHIVE_DESIGN_PREVIEW !== "1", "격리된 보관함 디자인 검증입니다.");
test.use({ channel: process.env.E2E_BROWSER_CHANNEL });
const baseline = process.env.ARCHIVE_DESIGN_BASELINE === "1";
const evidenceRoot = process.env.ARCHIVE_EVIDENCE_ROOT!;
const day = "2026-11-03";

async function enter(page: Page, count = 2) {
  resetTestData();
  const center = addCenter({
    name: "검증 어린이집",
    director_name: "가명원장",
    region_sido: "강원특별자치도",
    region_sigungu: "춘천시",
  });
  const classes = Array.from({ length: count }, (_, index) =>
    addClass(center.id, {
      name: index === 0 ? "햇살반" : index === 1 ? "새싹반" : `검증 ${index + 1}반`,
      teacher_name: "가명교사",
      age_min: 3,
      age_max: 5,
    }),
  );
  const child = addChild(classes[0].id, "가명아동");
  for (const classroom of classes.slice(0, 2))
    addPlan({ class_id: classroom.id, form_id: null, format: "MONTHLY_THEME" }, 2026);
  await page.addInitScript(
    ({ db, classes, child, center }) => {
      const email = "archive-design-qa@example.com",
        suffix = encodeURIComponent(email);
      sessionStorage.setItem("saessak.accountEmail", email);
      sessionStorage.setItem("saessak.demoSession", "active");
      sessionStorage.setItem("saessak.authToken", `mock.${suffix}`);
      if (localStorage.getItem(`saessak.demoAccount:${suffix}`)) return;
      localStorage.setItem(
        `saessak.demoAccount:${suffix}`,
        JSON.stringify({ name: "검증교사", email, onboardingCompletedAt: "2026-11-03T00:00:00Z" }),
      );
      localStorage.setItem(`saessak.mswSS.v1:${suffix}`, JSON.stringify(db));
      localStorage.setItem(
        `saessak.classSettings:${suffix}`,
        JSON.stringify({
          orgName: center.name,
          directorName: "가명원장",
          regionProvince: "강원특별자치도",
          regionDistrict: "춘천시",
          primaryClassId: "qa-" + classes[0].id,
          classes: classes.map((item) => ({
            id: "qa-" + item.id,
            className: item.name,
            teacherName: item.teacher_name,
            ageGroup: "4",
            selectedAges: [4],
            guardianConsent: true,
            childIds: item.id === child.class_id ? ["server-child:" + child.id] : [],
            children: [],
          })),
          characterEducationEnabled: false,
          characterMessages: {},
        }),
      );
      localStorage.setItem(
        `saessak.apiLinks.v1:development-mock:${suffix}`,
        JSON.stringify({
          center: { id: center.id, signature: "qa" },
          classes: Object.fromEntries(
            classes.map((item) => ["qa-" + item.id, { id: item.id, signature: "qa" }]),
          ),
          children: { ["server-child:" + child.id]: child.id },
        }),
      );
    },
    { db: read(), classes, child, center },
  );
  // API 구현은 바꾸지 않는다. 독립 브라우저의 읽기 전용 응답 fixture로 디자인을 검증한다.
  const journal = {
    id: 9001,
    kind: "dailyLog",
    title: "햇살반 검증 보육일지",
    class_id: classes[0].id,
    class_name: classes[0].name,
    child_id: null,
    child_name: null,
    start: day,
    end: day,
    status: "DRAFT",
    origin: "TEACHER",
    stale: false,
    generation: { method: null, rule_id: null, rule_version: null },
    sources_count: 1,
    created_at: day + "T01:00:00Z",
    updated_at: day + "T01:00:00Z",
  };
  const db = read();
  await page.addInitScript(
    ({ classes, child, center }) => {
      const suffix = encodeURIComponent("archive-design-qa@example.com");
      const links = {
        center: { id: center.id, signature: "qa" },
        classes: Object.fromEntries(
          classes.map((item) => ["qa-" + item.id, { id: item.id, signature: "qa" }]),
        ),
        children: { ["server-child:" + child.id]: child.id },
      };
      localStorage.setItem(`saessak.apiLinks.v1:backend:${suffix}`, JSON.stringify(links));
    },
    { classes, child, center },
  );
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    if (route.request().method() !== "GET") return route.abort();
    const path = url.pathname;
    if (!path.startsWith("/api/documents")) {
      let body: unknown;
      if (path === "/api/auth/me")
        body = {
          id: 1,
          name: "검증교사",
          email: "archive-design-qa@example.com",
          center_id: center.id,
          role: "TEACHER",
        };
      // 서버는 반마다 열람 상태를 준다(ADR-059). 이 검증의 반은 모두 내 반이다.
      else if (path === `/api/centers/${center.id}/classes`)
        body = { items: classes.map((item) => ({ ...item, my_access: "OWNER" })) };
      else if (path === "/api/access-requests/received") body = { items: [] };
      else if (/^\/api\/classes\/\d+\/children$/.test(path))
        body = {
          items: db.children.filter((item) => item.class_id === Number(path.split("/")[3])),
        };
      else if (path === `/api/centers/${center.id}/settings`)
        body = {
          trends_enabled: false,
          weekly_saturday_enabled: false,
          observation_axis: "NURI_5",
        };
      else if (path === `/api/centers/${center.id}`) body = center;
      else if (path === "/api/observations") body = { items: [] };
      else if (path === "/api/assistant") body = { available: false };
      else if (path === "/api/plans/annual")
        body = {
          items: db.plans.map((plan) => ({
            id: plan.id,
            class_id: plan.class_id,
            school_year: plan.school_year,
            format: plan.format,
            status: plan.status,
            created_at: plan.created_at,
            confirmed_at: plan.confirmed_at,
          })),
        };
      else if (/^\/api\/plans\/annual\/\d+$/.test(path))
        body = db.plans.find((plan) => plan.id === Number(path.split("/")[4]));
      else if (path === "/api/plans/monthly" || path === "/api/plans/weekly") body = { items: [] };
      else throw new Error("Unexpected preview API: " + path);
      return route.fulfill({ json: body });
    }
    const body =
      url.pathname === "/api/documents"
        ? { items: [journal] }
        : {
            ...journal,
            sources: [
              {
                id: 51,
                class_id: classes[0].id,
                child_id: null,
                date: day,
                text: "검증 사실 본문",
              },
            ],
            sections: [
              { heading: "사실", body: "검증 사실 본문", source_ids: [51] },
              { heading: "해석", body: "검증 해석", source_ids: [51] },
              { heading: "지원", body: "검증 지원", source_ids: [51] },
            ],
            review_note: "검증 메모",
          };
    await route.fulfill({ json: body });
  });
  await page.goto("/documents");
  await expect(
    page.getByRole("heading", { name: "문서를 선택해 주세요", exact: true }),
  ).toBeVisible();
  return { classes, plan: read().plans[0] };
}

async function fonts(page: Page) {
  await page.evaluate(() => document.fonts.ready);
  const result: Record<string, string> = {};
  for (const [name, locator] of [
    ["title", page.getByRole("heading", { name: "문서 보관함", exact: true })],
    ["body", page.getByRole("heading", { name: "문서를 선택해 주세요", exact: true })],
    [
      "class",
      page.getByRole("complementary", { name: "반 선택", exact: true }).getByRole("button").first(),
    ],
    ["card", page.getByRole("button", { name: "연간 계획안", exact: true })],
    [
      "mainSidebar",
      page
        .getByRole("complementary", { name: "주 메뉴", exact: true })
        .getByRole("link", { name: "문서 보관함", exact: true }),
    ],
  ] as const)
    result[name] = await locator.evaluate((element) => getComputedStyle(element).fontFamily);
  return result;
}

test("폰트 보존·미선택 화면·반응형 배치", async ({ page }) => {
  await page.setViewportSize({ width: 1585, height: 1000 });
  await enter(page);
  const currentFonts = await fonts(page);
  if (baseline) {
    await writeFile(`${evidenceRoot}/fonts-before.json`, JSON.stringify(currentFonts, null, 2));
    await page.screenshot({ path: `${evidenceRoot}/archive-before.png`, fullPage: true });
    return;
  }
  expect(currentFonts).toEqual(
    JSON.parse(await readFile(`${evidenceRoot}/fonts-before.json`, "utf8")),
  );
  await writeFile(`${evidenceRoot}/fonts-after.json`, JSON.stringify(currentFonts, null, 2));
  await expect(
    page.getByText("계획안과 작성한 문서들이 차곡차곡 모여 있어요.", { exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: /반 추가하기/ })).toHaveCount(0);
  const rail = page.getByRole("complementary", { name: "반 선택", exact: true });
  await expect(rail.locator('svg[data-art="class-garden"]')).toBeVisible();
  await expect(
    page
      .getByRole("complementary", { name: "주 메뉴", exact: true })
      .locator('svg[data-art="class-garden"]'),
  ).toHaveCount(0);
  await page.screenshot({ path: `${evidenceRoot}/archive-desktop.png`, fullPage: true });
  for (const width of [1024, 768, 390, 375]) {
    await page.setViewportSize({ width, height: 1000 });
    // 본문 여백은 사이드바 폭을 따른다 — components/app/ContentShell.tsx (펼침 267px).
    await expect(page.locator('div[class*="lg:ml-["]')).toHaveCSS(
      "margin-left",
      width < 1024 ? "0px" : "267px",
    );
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    const buttons = page.locator("button[data-type]");
    await expect(buttons).toHaveCount(5);
    await page.screenshot({ path: `${evidenceRoot}/archive-${width}.png`, fullPage: true });
  }
});

test("종류 선택·반 필터·기존 문서 목록과 미리보기·편집 진입", async ({ page }) => {
  test.skip(baseline);
  await page.setViewportSize({ width: 1585, height: 1000 });
  const { plan } = await enter(page);
  await page.getByRole("button", { name: "연간 계획안", exact: true }).click();
  await page.locator('button:has(> div[data-type="annual"])').click();
  const preview = page.getByRole("complementary", { name: "문서 미리보기", exact: true });
  await expect(preview.getByRole("link", { name: "문서 열기", exact: true })).toHaveAttribute(
    "href",
    `/plans/annual/${plan.id}`,
  );
  await expect(preview.getByText("햇살반", { exact: true })).toBeVisible();
  await page
    .getByRole("complementary", { name: "반 선택", exact: true })
    .getByRole("button", { name: "새싹반", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "문서를 선택해 주세요", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "연간 계획안", exact: true }).click();
  await page.locator('button:has(> div[data-type="annual"])').click();
  await expect(preview.getByText("새싹반", { exact: true })).toBeVisible();
  for (const name of ["월간 계획안", "주간 계획안", "관찰일지"]) {
    await page.getByRole("button", { name, exact: true }).click();
    await expect(page.getByRole("button", { name, exact: true })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  }
  await page
    .getByRole("complementary", { name: "반 선택", exact: true })
    .getByRole("button", { name: "햇살반", exact: true })
    .click();
  await page.getByRole("button", { name: "보육일지", exact: true }).click();
  // 보육일지는 오늘 날짜로 열린다. 검증 문서의 날짜로 옮겨야 실행 날짜와 상관없이 같다.
  await page.getByLabel("날짜 선택").fill(day);
  await page.getByRole("button", { name: /햇살반 검증 보육일지/ }).click();
  await expect(preview.getByText("검증 사실 본문", { exact: true })).toBeVisible();
  await preview.getByRole("button", { name: "편집하기", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "← 문서 목록으로 돌아가기", exact: true }),
  ).toBeVisible();
});

test("반 목록이 많아도 하단 캐릭터와 겹치지 않고 목록만 스크롤한다", async ({ page }) => {
  test.skip(baseline);
  await page.setViewportSize({ width: 1585, height: 1000 });
  await enter(page, 24);
  const rail = page.getByRole("complementary", { name: "반 선택", exact: true });
  const metrics = await rail.evaluate((element) => {
    const list = element.querySelector('div[class*="classList"]')!;
    const art = element.querySelector('svg[data-art="class-garden"]')!;
    return {
      scrolls: list.scrollHeight > list.clientHeight,
      listBottom: list.getBoundingClientRect().bottom,
      artTop: art.getBoundingClientRect().top,
    };
  });
  expect(metrics.scrolls).toBe(true);
  expect(metrics.listBottom).toBeLessThanOrEqual(metrics.artTop + 1);
  await rail.getByRole("button", { name: "검증 24반", exact: true }).click();
  await expect(rail.getByRole("button", { name: "검증 24반", exact: true })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
});
