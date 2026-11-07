import { expect, test, type Page } from "@playwright/test";

test.use({ channel: process.env.E2E_BROWSER_CHANNEL });

const kinds = ["연간", "월간", "주간"];

async function enterArchive(page: Page) {
  const center = {
    id: 901,
    name: "크기 검증 어린이집",
    director_name: "검증원장",
    region_sido: "강원특별자치도",
    region_sigungu: "춘천시",
    created_at: "2026-11-04T00:00:00Z",
  };
  const classroom = {
    id: 902,
    center_id: center.id,
    name: "크기 검증반",
    school_year: 2026,
    age_min: 4,
    age_max: 4,
    child_count: 0,
    teacher_name: "검증교사",
    my_access: "OWNER",
    consent_confirmed_at: null,
    created_at: center.created_at,
  };
  await page.addInitScript(
    ({ center, classroom }) => {
      const email = "archive-card-size@example.com";
      const suffix = encodeURIComponent(email);
      const classId = "server-class:" + classroom.id;
      sessionStorage.setItem("saessak.accountEmail", email);
      sessionStorage.setItem("saessak.demoSession", "active");
      localStorage.setItem(
        `saessak.demoAccount:${suffix}`,
        JSON.stringify({ name: "검증교사", email, onboardingCompletedAt: center.created_at }),
      );
      localStorage.setItem(
        `saessak.classSettings:${suffix}`,
        JSON.stringify({
          orgName: center.name,
          directorName: center.director_name,
          regionProvince: center.region_sido,
          regionDistrict: center.region_sigungu,
          primaryClassId: classId,
          classes: [
            {
              id: classId,
              className: classroom.name,
              teacherName: classroom.teacher_name,
              selectedAges: [4],
              children: [],
            },
          ],
        }),
      );
      // 화면의 반 id → 서버 반 번호 연결표. 없으면 classServerId 가 null 이라
      // 보관함이 연간 목록을 비워 저장된 카드가 그려지지 않는다. CI 는 MSW 가 꺼져 키가 `backend` 다.
      localStorage.setItem(
        `saessak.apiLinks.v1:backend:${suffix}`,
        JSON.stringify({
          center: { id: center.id, signature: "qa" },
          classes: { [classId]: { id: classroom.id, signature: "qa" } },
          children: {},
        }),
      );
    },
    { center, classroom },
  );
  // 실제 /documents UI를 사용하되 테스트 브라우저의 읽기 응답만 대체한다.
  // 쓰기 요청은 서버로 전달하지 않아 기존 계정·DB에는 영향이 없다.
  await page.route("**/api/**", async (route) => {
    if (route.request().method() !== "GET") return route.abort();
    const path = new URL(route.request().url()).pathname;
    let body: unknown = { items: [] };
    if (path === "/api/auth/me")
      body = { id: 1, name: "검증교사", email: "archive-card-size@example.com", center_id: 901 };
    else if (path === `/api/centers/${center.id}`) body = center;
    else if (path === `/api/centers/${center.id}/classes`) body = { items: [classroom] };
    else if (path === `/api/centers/${center.id}/settings`)
      body = { trends_enabled: false, observation_axis: "NURI_5" };
    else if (path === "/api/assistant") body = { available: false };
    await route.fulfill({ json: body });
  });
  await page.goto("/documents");
  await expect(page.getByRole("button", { name: "연간 계획안", exact: true })).toBeVisible();
}

async function measureCard(page: Page, kind: string) {
  await page.getByRole("button", { name: `${kind} 계획안`, exact: true }).click();
  const card = page.locator("a, button").filter({ hasText: `새 ${kind} 계획안 작성` });
  await expect(card).toBeVisible();
  return card.evaluate((element) => {
    const rect = element.getBoundingClientRect();
    const parent = element.parentElement!.getBoundingClientRect();
    const style = getComputedStyle(element);
    return {
      width: rect.width,
      height: rect.height,
      left: rect.left,
      top: rect.top,
      parentLeft: parent.left,
      parentTop: parent.top,
      parentRight: parent.right,
      font: style.fontFamily,
      alignItems: style.alignItems,
      justifyContent: style.justifyContent,
      minHeight: style.minHeight,
      maxWidth: style.maxWidth,
      gridColumns: getComputedStyle(element.parentElement!).gridTemplateColumns,
    };
  });
}

test("계획안 3종 생성 카드: 데스크톱 400×245, 새로고침 유지, 좁은 화면 비례 축소", async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 1671, height: 941 });
  await enterArchive(page);
  const measurements: Record<string, Awaited<ReturnType<typeof measureCard>>> = {};
  for (const width of [1671, 1280, 390, 375]) {
    await page.setViewportSize({ width, height: 941 });
    for (const kind of kinds) {
      const size = await measureCard(page, kind);
      if (width >= 1280) {
        // 1440 보다 좁은 창은 화면 전체를 창 폭 / 1440 으로 줄인다(globals.css --app-zoom).
        const zoom = Math.min(1, width / 1440);
        expect(size.width).toBeCloseTo(400 * zoom, 0);
        expect(size.height).toBeCloseTo(245 * zoom, 0);
      } else {
        expect(size.width).toBeLessThan(400);
        expect(size.width / size.height).toBeCloseTo(400 / 245, 2);
        expect(size.left + size.width).toBeLessThanOrEqual(size.parentRight + 1);
        expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(width);
      }
      expect(size.left).toBe(size.parentLeft);
      expect(size.top).toBe(size.parentTop);
      expect(size.alignItems).toBe("center");
      expect(size.justifyContent).toBe("center");
      measurements[`${width}-${kind}`] = size;
      if (width === 1671)
        await page.screenshot({ path: testInfo.outputPath(`${kind}-desktop.png`) });
    }
    if (width === 375) await page.screenshot({ path: testInfo.outputPath("mobile.png") });
  }
  await page.setViewportSize({ width: 1671, height: 941 });
  await page.reload();
  for (const kind of kinds) {
    const size = await measureCard(page, kind);
    expect(size.width).toBe(400);
    expect(size.height).toBe(245);
  }
  console.log(
    JSON.stringify(
      Object.entries(measurements).map(([view, size]) => ({
        view,
        width: size.width,
        height: size.height,
      })),
    ),
  );
  await testInfo.attach("rendered-card-sizes", {
    body: JSON.stringify(measurements, null, 2),
    contentType: "application/json",
  });
});

test("저장된 문서 카드: 네 면의 기본 실선과 hover·선택 강조 유지", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1671, height: 941 });
  await enterArchive(page);
  const schoolYear = await page.evaluate(() => {
    const date = new Date();
    return date.getMonth() >= 2 ? date.getFullYear() : date.getFullYear() - 1;
  });
  const plan = {
    id: 903,
    class_id: 902,
    format: "MONTHLY_THEME",
    school_year: schoolYear,
    status: "DRAFT",
    created_at: "2026-11-04T00:00:00Z",
    confirmed_at: null,
    months: [],
  };
  await page.route("**/api/plans/annual**", (route) =>
    route.fulfill({
      json: new URL(route.request().url()).pathname.endsWith("/903") ? plan : { items: [plan] },
    }),
  );
  await page.reload();
  await measureCard(page, "연간");
  const saved = page.locator('button:has(> div[data-type="annual"])');
  await expect(saved).toBeVisible();
  const basic = await saved.evaluate((element) => {
    const style = getComputedStyle(element);
    return {
      width: element.getBoundingClientRect().width,
      colors: [
        style.borderTopColor,
        style.borderRightColor,
        style.borderBottomColor,
        style.borderLeftColor,
      ],
      widths: [
        style.borderTopWidth,
        style.borderRightWidth,
        style.borderBottomWidth,
        style.borderLeftWidth,
      ],
      styles: [
        style.borderTopStyle,
        style.borderRightStyle,
        style.borderBottomStyle,
        style.borderLeftStyle,
      ],
      radius: style.borderRadius,
      background: style.backgroundColor,
      shadow: style.boxShadow,
    };
  });
  expect(basic.width).toBe(440);
  expect(basic.colors).toEqual(Array(4).fill("rgb(203, 213, 207)"));
  expect(basic.widths).toEqual(Array(4).fill("1px"));
  expect(basic.styles).toEqual(Array(4).fill("solid"));
  expect(basic.radius).toBe("13px");
  await page.screenshot({ path: testInfo.outputPath("saved-default.png") });
  await saved.hover();
  await expect(saved).toHaveCSS("border-color", "rgb(159, 207, 181)");
  await expect(saved).toHaveCSS("background-color", basic.background);
  await expect(saved).toHaveCSS("box-shadow", basic.shadow);
  await page.screenshot({ path: testInfo.outputPath("saved-hover.png") });
  await saved.click();
  await expect(saved).toHaveAttribute("aria-pressed", "true");
  await expect(saved).toHaveCSS("outline-width", "2px");
  await expect(saved).toHaveCSS("outline-style", "solid");
  await expect(saved).toHaveCSS("outline-offset", "2px");
  await expect(page.getByRole("link", { name: "문서 열기", exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("saved-selected.png"), fullPage: true });
  console.log(
    "saved-card",
    JSON.stringify(basic),
    "hover: rgb(159, 207, 181), selected: 2px solid",
  );
});
