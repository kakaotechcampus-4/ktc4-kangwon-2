import { expect, test, type Page, type TestInfo } from "@playwright/test";

const viewports = [
  { width: 1440, height: 900 },
  { width: 768, height: 1024 },
  { width: 390, height: 844 },
  { width: 375, height: 812 },
];
const day = "2026-10-19";
const types = ["연간 계획안", "월간 계획안", "주간 계획안", "관찰일지", "보육일지"];

async function api(page: Page, path: string, method = "GET", data?: unknown) {
  const token = await page.evaluate(() => sessionStorage.getItem("saessak.authToken"));
  const response = await page.request.fetch(path, {
    method,
    data,
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(
    response.ok(),
    `${method} ${path}: ${response.status()} ${await response.text()}`,
  ).toBeTruthy();
  return response.status() === 204 ? undefined : response.json();
}

async function enter(page: Page) {
  const email = `w12-audit-${Date.now()}-${Math.random().toString(36).slice(2, 7)}@example.com`;
  const password = "w12-audit-password-1234";
  await page.goto("/signup");
  await page.getByLabel("선생님 이름").fill("점검교사");
  await page.getByLabel("이메일").fill(email);
  await page.locator("#auth-password").fill(password);
  await page.getByLabel("비밀번호 확인").fill(password);
  await page.getByRole("button", { name: "회원가입", exact: true }).click();
  await page.getByRole("link", { name: "로그인하러 가기" }).click();
  await page.getByLabel("이메일").fill(email);
  await page.locator("#auth-password").fill(password);
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  await expect(page).toHaveURL(/\/onboarding\/center$/);
  await page.getByLabel("원명").fill("점검전용어린이집");
  await page.getByLabel("원장 이름").fill("가상원장");
  await page.getByLabel("시·도", { exact: true }).selectOption("강원특별자치도");
  await page.getByLabel("시·군·구").selectOption("춘천시");
  await page.getByRole("button", { name: "다음", exact: true }).click();
  await page.getByLabel("반 이름").fill("햇살반");
  await page.getByLabel("만 4세", { exact: true }).check();
  await page.getByLabel("담임 이름").fill("점검교사");
  await page.getByLabel("이 반 모든 아동의 법정대리인 동의를 받았습니다.").check();
  await page.getByRole("button", { name: "다음", exact: true }).click();
  await page.getByLabel("아동 추가").fill("가나다");
  await page.getByRole("button", { name: "+ 추가", exact: true }).click();
  await page.getByRole("button", { name: "설정 완료", exact: true }).click();
  await expect(page).toHaveURL(/\/$/);
  const me = await api(page, "/api/auth/me");
  const classes = await api(page, `/api/centers/${me.center_id}/classes`);
  const cls = classes.items.find((c: { name: string }) => c.name === "햇살반");
  const children = await api(page, `/api/classes/${cls.id}/children`);
  const other = await api(page, `/api/classes/${cls.id}/children`, "POST", { name: "라마바" });
  return {
    classId: cls.id as number,
    centerId: me.center_id as number,
    childId: children.items[0].id as number,
    otherChildId: other.id as number,
    email,
    password,
  };
}

async function daily(page: Page, classId: number, date: string, confirmed = false) {
  const routine = await api(page, "/api/routines", "POST", {
    class_id: classId,
    date,
    name: "블록놀이",
    start: "09:00",
    end: "10:00",
    plan: "블록을 준비한다.",
    execution: "블록을 쌓아 길을 만들었다.",
  });
  const doc = await api(page, "/api/documents", "POST", {
    kind: "dailyLog",
    class_id: classId,
    start: date,
    end: date,
    source_ids: [routine.id],
  });
  if (confirmed)
    await api(page, `/api/documents/${doc.id}/confirm`, "POST", {
      checks: { fact: true, interpretation: true, support: true },
    });
  return { doc, routine };
}

async function openCare(page: Page, date = day) {
  await page.goto("/documents");
  await page
    .getByRole("complementary", { name: "반 선택" })
    .getByRole("button", { name: "햇살반", exact: true })
    .click();
  await page.getByRole("button", { name: "보육일지", exact: true }).click();
  await page.getByLabel("날짜 선택").fill(date);
}

function docButton(page: Page, title: string) {
  return page.getByRole("button", {
    name: new RegExp(title.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")),
  });
}

async function captureLayout(page: Page, info: TestInfo, label: string) {
  const measurements = await page
    .locator('[class*="archive"]')
    .first()
    .evaluate((root) => {
      const width = document.documentElement.clientWidth;
      const clipped = Array.from(root.querySelectorAll("button,a,input,select")).flatMap((node) => {
        const element = node as HTMLElement;
        const box = element.getBoundingClientRect();
        if (!box.width || !box.height) return [];
        let parent = element.parentElement;
        while (parent && parent !== root) {
          const style = getComputedStyle(parent);
          if (
            ["auto", "scroll"].includes(style.overflowX) &&
            parent.scrollWidth > parent.clientWidth
          )
            return [];
          parent = parent.parentElement;
        }
        return box.left < -1 || box.right > width + 1
          ? [
              {
                text:
                  element.getAttribute("aria-label") || element.textContent?.trim().slice(0, 55),
                left: box.left,
                right: box.right,
              },
            ]
          : [];
      });
      const cardGrids = Array.from(root.querySelectorAll('[class*="docGrid"]')).map((grid) => {
        const cards = Array.from(grid.children).filter((node) =>
          node.matches('[class*="docCard"], [class*="addCard"]'),
        );
        const boxes = cards
          .map((card) => card.getBoundingClientRect())
          .filter((box) => box.width > 0 && box.height > 0);
        return {
          cardCount: boxes.length,
          widthDifference: boxes.length
            ? Math.max(...boxes.map((box) => box.width)) -
              Math.min(...boxes.map((box) => box.width))
            : 0,
          heightDifference: boxes.length
            ? Math.max(...boxes.map((box) => box.height)) -
              Math.min(...boxes.map((box) => box.height))
            : 0,
          hasCreateAndSaved:
            cards.some((card) => card.className.includes("addCard")) &&
            cards.some((card) => card.className.includes("docCard")),
        };
      });
      const roster = root.querySelector('aside[class*="roster"]');
      const main = roster?.nextElementSibling;
      let journalPanels: {
        sideBySide: boolean;
        bottomDifference: number;
        journalFillGap: number;
      } | null = null;
      if (roster && main) {
        const left = roster.getBoundingClientRect();
        const right = main.getBoundingClientRect();
        const journal = roster.parentElement!.getBoundingClientRect();
        const browser = roster.closest('[class*="browser"]')!.getBoundingClientRect();
        if (left.width > 0 && right.width > 0) {
          journalPanels = {
            sideBySide: right.left >= left.right - 1 && Math.abs(left.top - right.top) < 2,
            bottomDifference: Math.abs(left.bottom - right.bottom),
            journalFillGap: Math.abs(journal.bottom - browser.bottom),
          };
        }
      }
      return {
        width,
        scrollWidth: document.documentElement.scrollWidth,
        clipped,
        cardGrids,
        journalPanels,
        calendarDateFits: Array.from(root.querySelectorAll('[class*="dayStrip"] button')).every(
          (button) => {
            const date = button.firstElementChild!;
            return date.getBoundingClientRect().width <= button.getBoundingClientRect().width - 7;
          },
        ),
        cardDateOneLine: Array.from(
          root.querySelectorAll('[class*="docCard"] [class*="cover"] b'),
        ).every((date) => {
          return (
            date.getBoundingClientRect().height <=
            parseFloat(getComputedStyle(date).lineHeight) * 1.1
          );
        }),
        scrollers: Array.from(root.querySelectorAll("div,aside"))
          .filter((el) => el.scrollWidth > el.clientWidth + 2)
          .map((el) => ({
            class: el.className,
            clientWidth: el.clientWidth,
            scrollWidth: el.scrollWidth,
            overflowX: getComputedStyle(el).overflowX,
          })),
      };
    });
  await info.attach(`${label}-layout.json`, {
    body: JSON.stringify(measurements, null, 2),
    contentType: "application/json",
  });
  await page.screenshot({ path: info.outputPath(`${label}.png`), fullPage: true });
  expect
    .soft(measurements.scrollWidth, `${label}: page overflow`)
    .toBeLessThanOrEqual(measurements.width + 1);
  expect.soft(measurements.clipped, `${label}: clipped archive controls`).toEqual([]);
  expect
    .soft(measurements.calendarDateFits, `${label}: calendar dates must fit their columns`)
    .toBe(true);
  expect
    .soft(measurements.cardDateOneLine, `${label}: document cover dates must not wrap`)
    .toBe(true);
  for (const grid of measurements.cardGrids) {
    if (grid.cardCount > 1) {
      expect.soft(grid.widthDifference, `${label}: card widths must match`).toBeLessThanOrEqual(1);
      expect
        .soft(grid.heightDifference, `${label}: card heights must match`)
        .toBeLessThanOrEqual(1);
    }
  }
  if (measurements.journalPanels) {
    expect
      .soft(measurements.journalPanels.journalFillGap, `${label}: journal must fill the main panel`)
      .toBeLessThanOrEqual(2);
    if (measurements.journalPanels.sideBySide)
      expect
        .soft(
          measurements.journalPanels.bottomDifference,
          `${label}: child list and content must align at the bottom`,
        )
        .toBeLessThanOrEqual(2);
  }
}

for (const viewport of viewports) {
  test(`W12 보관함 ${viewport.width}x${viewport.height}: 탐색·상태·문서 재열기·키보드·넘침`, async ({
    page,
  }, info) => {
    await page.setViewportSize(viewport);
    const user = await enter(page);
    const draft = await daily(page, user.classId, day);
    await daily(page, user.classId, "2026-10-20", true);
    const other = await api(page, `/api/centers/${user.centerId}/classes`, "POST", {
      name: "달님반",
      age_min: 4,
      age_max: 4,
      teacher_name: "가상교사",
      consent_confirmed: true,
    });
    await api(page, `/api/classes/${other.id}/children`, "POST", { name: "마바사" });
    await openCare(page);
    await expect(docButton(page, draft.doc.title)).toContainText("검토 중");
    await expect(page.getByText("확정", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("미작성", { exact: true }).first()).toBeVisible();
    await captureLayout(page, info, "care");
    // 반별 보육일지는 아동 선택 없이 탐색한다.
    await expect(page.getByLabel("아동 이름 검색")).toHaveCount(0);
    await expect(docButton(page, draft.doc.title)).toBeVisible();
    await docButton(page, draft.doc.title).click();
    await page
      .getByRole("complementary", { name: "문서 미리보기" })
      .getByRole("button", { name: /^(편집하기|문서 열기)$/ })
      .click();
    await expect(
      page.getByRole("heading", { name: draft.doc.title, exact: true, level: 2 }),
    ).toBeVisible();
    await page
      .getByRole("textbox", { name: "지원 내용", exact: true })
      .fill("다음 놀이에 다양한 블록을 준비해 함께 길을 만들도록 지원한다.");
    await page.getByRole("button", { name: "초안 저장", exact: true }).click();
    await expect(page.getByText("작성 중인 초안을 저장했어요.")).toBeVisible();
    await captureLayout(page, info, "draft-editor");
    await page.getByRole("button", { name: "← 문서 목록으로 돌아가기", exact: true }).click();
    await docButton(page, draft.doc.title).click();
    await page
      .getByRole("complementary", { name: "문서 미리보기" })
      .getByRole("button", { name: /^(편집하기|문서 열기)$/ })
      .click();
    await expect(page.getByRole("textbox", { name: "지원 내용", exact: true })).toHaveValue(
      "다음 놀이에 다양한 블록을 준비해 함께 길을 만들도록 지원한다.",
    );
    await page.getByRole("button", { name: "← 문서 목록으로 돌아가기", exact: true }).click();
    await page.getByLabel("날짜 선택").fill("2026-10-21");
    await expect(docButton(page, draft.doc.title)).toHaveCount(0);
    await expect(page.getByRole("button", { name: /이 날짜 보육일지 작성/ })).toBeVisible();
    for (const name of types) {
      const button = page.getByRole("button", { name, exact: true });
      await button.focus();
      await page.keyboard.press("Enter");
      await expect(button).toHaveAttribute("aria-pressed", "true");
      await captureLayout(page, info, name);
    }
    await page.getByRole("button", { name: "관찰일지", exact: true }).click();
    await page.getByRole("button", { name: "가나다", exact: true }).click();
    await captureLayout(page, info, "observation");
    await page
      .getByRole("complementary", { name: "반 선택" })
      .getByRole("button", { name: "달님반", exact: true })
      .click();
    await expect(page.getByRole("heading", { name: "문서를 선택해 주세요" })).toBeVisible();
    await page.getByRole("button", { name: "관찰일지", exact: true }).click();
    await expect(page.getByRole("button", { name: "가나다", exact: true })).toHaveCount(0);
    await page.getByRole("button", { name: "마바사", exact: true }).focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("button", { name: "마바사", exact: true })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await page.keyboard.press("Tab");
    await expect(page.locator(":focus")).toBeVisible();
    await captureLayout(page, info, "other-class");
  });
}

test("W12 보관함: 목록 로딩·실패·재시도와 상세 조회 실패", async ({ page }, info) => {
  const user = await enter(page);
  const { doc } = await daily(page, user.classId, day);
  let release!: () => void;
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/api/documents", async (route) => {
    await pending;
    await route.continue();
  });
  await page.goto("/documents");
  await page
    .getByRole("complementary", { name: "반 선택" })
    .getByRole("button", { name: "햇살반", exact: true })
    .click();
  await page.getByRole("button", { name: "보육일지", exact: true }).click();
  await page.getByLabel("날짜 선택").fill(day);
  await page.screenshot({ path: info.outputPath("list-loading.png"), fullPage: true });
  await expect.soft(page.getByText("문서 목록을 불러오고 있어요.", { exact: true })).toBeVisible();
  release();
  await expect(docButton(page, doc.title)).toBeVisible();
  await page.unrouteAll({ behavior: "wait" });
  await page.route("**/api/documents", (route) => route.abort("failed"));
  await page.reload();
  await expect(page.getByRole("button", { name: "다시 시도", exact: true })).toBeVisible();
  await page.screenshot({ path: info.outputPath("list-error.png"), fullPage: true });
  await page.unroute("**/api/documents");
  await page.getByRole("button", { name: "다시 시도", exact: true }).click();
  await openCare(page);
  await page.route(`**/api/documents/${doc.id}`, (route) => route.abort("failed"));
  await docButton(page, doc.title).click();
  await expect(page.getByRole("button", { name: "미리보기 다시 시도", exact: true })).toBeVisible();
  await page.screenshot({ path: info.outputPath("detail-error.png"), fullPage: true });
  await page.unroute(`**/api/documents/${doc.id}`);
  await page.getByRole("button", { name: "미리보기 다시 시도", exact: true }).click();
  await expect(page.getByRole("heading", { name: doc.title, exact: true, level: 2 })).toBeVisible();
});

