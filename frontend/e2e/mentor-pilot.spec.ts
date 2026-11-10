import { expect, test, type Page } from "@playwright/test";
import { verifyHwpx } from "./hwpx";
import { completeOnboarding } from "./onboarding";

/**
 * 보관함은 **반 → 관찰일지 → 아이 → 날짜** 로만 탐색한다.
 * 예전의 전체 문서 목록은 없앴으므로 제목만으로 바로 누르지 않는다.
 */
async function openObservation(
  page: Page,
  doc: { title: string; child_name: string; start: string },
) {
  await page.getByRole("complementary", { name: "반 선택" }).getByText("햇살반").click();
  await page.getByRole("button", { name: "관찰일지", exact: true }).click();
  await page.getByRole("button", { name: doc.child_name, exact: true }).click();
  await page.getByLabel("날짜 선택").fill(doc.start);
  await page
    .getByRole("button", { name: new RegExp(doc.title.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")) })
    .click();
  await page
    .getByRole("complementary", { name: "문서 미리보기" })
    .getByRole("button", { name: /^(편집하기|문서 열기)$/ })
    .click();
}

/** The mentor follows these controls; API reads below verify persisted results. */
async function enterPilot(page: Page) {
  const email = `pilot-${Date.now()}-${Math.random().toString(36).slice(2, 7)}@example.com`;
  await page.goto("/signup");
  await page.getByLabel("선생님 이름").fill("파일럿교사");
  await page.getByLabel("이메일").fill(email);
  await page.locator("#auth-password").fill("pilot-password-1234");
  await page.getByLabel("비밀번호 확인").fill("pilot-password-1234");
  await page.getByRole("button", { name: "회원가입", exact: true }).click();
  await expect(page.getByRole("heading", { name: "가입을 완료했어요" })).toBeVisible();
  await expect(page).toHaveURL(/\/signup$/);
  await page.getByRole("link", { name: "메인화면으로 가기", exact: true }).click();
  await expect(page).toHaveURL(/\/$/);
  await page.goto("/onboarding");
  await completeOnboarding(page, {
    center: "파일럿어린이집",
    director: "가상원장",
    teacher: "파일럿교사",
    children: ["가나다"],
  });
  // 홈의 h1 은 날짜라 매일 달라진다. 홈에만 있는 적는 칸 제목으로 「도착했나」를 본다.
  await expect(page.getByRole("heading", { name: "지금, 한 줄", exact: true })).toBeVisible();
  return api(page, "/api/auth/me");
}

async function api(page: Page, path: string) {
  const token = await page.evaluate(() => sessionStorage.getItem("saessak.authToken"));
  const response = await page.request.get(path, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(response.ok(), await response.text()).toBeTruthy();
  return response.json();
}

test("멘토: 연간 생성·편집·확정·한글 다운로드와 월간 연속 입력·저장, 주간 생성·수정·확정·한글 다운로드", async ({
  page,
}, info) => {
  await enterPilot(page);
  await page.getByRole("link", { name: "계획안", exact: true }).click();
  // 첫 화면의 첫 칸이 월별 주제형이다.
  await page.getByRole("link", { name: "연간부터 시작하기", exact: true }).first().click();
  await page.getByRole("button", { name: "연간계획안 만들기", exact: true }).click();
  await expect(page).toHaveURL(/\/plans\/annual\/\d+$/);
  const annualId = page.url().split("/").at(-1);
  const generated = await api(page, `/api/plans/annual/${annualId}`);
  expect(generated.months).toHaveLength(12);
  expect(
    generated.months.every((month: { sub_themes: string[] }) => month.sub_themes.length >= 2),
  ).toBeTruthy();
  // 처음엔 3월 생활주제 칸이 골라져 있다. 칸을 떠나면(blur) 그 달을 저장한다.
  await page.getByLabel("3월 생활주제", { exact: true }).fill("우리 반과 새로운 친구");
  await page.getByLabel("3월 1번째 소주제", { exact: true }).fill("우리 반 이름 알아보기");
  await page.getByLabel("3월 2번째 소주제", { exact: true }).fill("친구와 인사 나누기");
  // 연간 안전교육 칸은 꺼 뒀다(2026-10-22) — 화면에 입력이 없고, 저장해도 서버 값을 건드리지 않는다.
  await expect(page.getByLabel("3월 안전교육 입력", { exact: true })).toHaveCount(0);
  await page.screenshot({ path: info.outputPath("annual-edit.png"), fullPage: true });
  const lastSave = page.waitForResponse(
    (r) =>
      r.request().method() === "PUT" &&
      r.url().endsWith(`/api/plans/annual/${annualId}/months/3`) &&
      (r.request().postData() ?? "").includes("친구와 인사 나누기"),
  );
  await page.getByLabel("3월 2번째 소주제", { exact: true }).blur();
  expect((await lastSave).ok()).toBeTruthy();
  await page.reload();
  const sheet = page.getByRole("region", { name: "문서 미리보기", exact: true });
  await expect(sheet.getByText("우리 반과 새로운 친구", { exact: true })).toBeVisible();
  await expect(sheet.getByText(/안전교육/)).toHaveCount(0);
  const savedAnnual = await api(page, `/api/plans/annual/${annualId}`);
  expect(savedAnnual.months[0].safety_education_state).toBe("SOURCE_REQUIRED");
  await page.getByRole("button", { name: "확정하기", exact: true }).click();
  await page
    .getByRole("group", { name: /이대로 확정할까요\?/ })
    .getByRole("button", { name: "확정하기", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: `${generated.school_year} 연간계획안을 확정했어요` }),
  ).toBeVisible();
  // 확정 취소는 없다(ADR-064) — 고치려면 문서 보관함에서 「수정하기」를 누른다.
  await expect(page.getByRole("button", { name: "확정 취소", exact: true })).toHaveCount(0);
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "한글 파일(hwpx)로 내려받기", exact: true }).click();
  await verifyHwpx(await download, info.outputPath("pilot-annual.hwpx"), [
    "우리 반과 새로운 친구",
    "우리 반 이름 알아보기",
    "친구와 인사 나누기",
  ]);
  await page.screenshot({ path: info.outputPath("annual-confirmed.png"), fullPage: true });

  // 확정 화면 → 월간 만들기. 넣을 칸은 만들기 화면에서 고른다(따로 양식 화면이 없다, 2026-11-03).
  await page.getByRole("link", { name: "월간계획안 만들기", exact: true }).click();
  await expect(page.getByRole("group", { name: "어떤 칸을 넣을까요?" })).toBeVisible();
  await expect(page.getByRole("checkbox", { name: /실내 대체활동/ })).not.toBeChecked();
  await page.getByRole("button", { name: /월간계획안 만들기/ }).click();
  // 놀이 월간과 같은 화면: 문서에서 칸을 누르면 옆 패널에서 고치고, 입력을 멈추거나 떠나면 저장한다.
  const doc = page.getByRole("region", { name: "월간계획안 미리보기", exact: true });
  const outdoor = doc
    .getByRole("row")
    .filter({ has: page.getByRole("rowheader", { name: "바깥놀이", exact: true }) });
  // 문서는 나타난 뒤 「맞춤」 배율로 한 번 더 그려진다 — 자리가 잡힐 때까지 다시 잰다.
  await expect
    .poll(async () => {
      const firstWeek = await doc.getByRole("columnheader").nth(1).boundingBox();
      const firstCell = await outdoor.locator("td").first().boundingBox();
      return Math.abs(firstWeek!.x - firstCell!.x);
    })
    .toBeLessThan(2);
  const cell = (n: number) => outdoor.locator("td").nth(n).locator("[data-cell]");
  // 칸 편집은 이름 · 설명 두 칸이다(ADR-066) — 문서 칸에 보이는 글은 이름이다.
  const field = page.getByRole("textbox", { name: "바깥놀이 이름", exact: true });
  await cell(0).click();
  await expect(cell(0)).toHaveAttribute("aria-pressed", "true");
  await expect(field).toBeVisible();
  // 월간 v1 칸 편집에는 다시 만들기가 없다(81aa2fc4, 2026-11-04). 확정은 페이지 안에서 한 번 더 묻는다.
  await field.fill("");
  await field.pressSequentially("친구와 함께 만드는 우리 반 놀이", { delay: 15 });
  // A nested component used to remount this input after every character.
  await expect(field).toBeFocused();
  await expect(field).toHaveValue("친구와 함께 만드는 우리 반 놀이");
  await expect(cell(0)).toHaveText("친구와 함께 만드는 우리 반 놀이");
  await cell(1).click(); // 떠나면 앞 칸을 저장하고, 고른 칸과 패널이 함께 바뀐다.
  await expect(cell(1)).toHaveAttribute("aria-pressed", "true");
  await field.fill("교사가 준비한 자연물을 함께 살펴본다.");
  await field.blur();
  await expect(page.getByRole("status").filter({ hasText: /^저장됨$/ })).toBeVisible();
  await page.reload();
  await expect(cell(0)).toHaveText("친구와 함께 만드는 우리 반 놀이");
  await expect(cell(1)).toHaveText("교사가 준비한 자연물을 함께 살펴본다.");
  await cell(0).click();
  await field.fill("친구와 함께 만드는 새로운 우리 반 놀이");
  await page.getByRole("button", { name: "확정하기", exact: true }).click();
  // 안전교육을 아직 놓지 않은 주는 빈칸으로 센다(c4cb083c) — 확정 창이 「빈칸이 남아 있어요」로 시작한다.
  await page
    .getByRole("group", { name: /이대로 확정할까요\?/ })
    .getByRole("button", { name: "확정하기", exact: true })
    .click();
  await expect(
    page.getByText("확정했어요. 고치려면 문서 보관함의 「수정하기」를 눌러 주세요."),
  ).toBeVisible();
  // 확정 후 화면: 확정본 · 한글 내보내기 · 주간 만들기 · 홈.
  await expect(page.getByRole("heading", { name: /월 월간계획안을 확정했어요$/ })).toBeVisible();
  await expect(page.getByRole("link", { name: "주간계획안 만들기", exact: true })).toHaveAttribute(
    "href",
    "/plans/weekly",
  );
  await page.reload();
  await expect(cell(0)).toHaveText("친구와 함께 만드는 새로운 우리 반 놀이");
  await expect(cell(0)).not.toHaveAttribute("role", "button");
  await expect(page.getByRole("textbox")).toHaveCount(0);
  const monthlyDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "한글 파일(hwpx)로 내려받기", exact: true }).click();
  await verifyHwpx(await monthlyDownload, info.outputPath("pilot-monthly.hwpx"), [
    "친구와 함께 만드는 새로운 우리 반 놀이",
    "교사가 준비한 자연물을 함께 살펴본다.",
  ]);
  await page.screenshot({ path: info.outputPath("monthly-confirmed.png"), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect
    .poll(() =>
      page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      ),
    )
    .toBeLessThanOrEqual(0);
  await page.screenshot({ path: info.outputPath("monthly-mobile.png"), fullPage: true });
  await page.setViewportSize({ width: 1440, height: 1000 });

  // 확정 화면 → 주간 만들기 → 칸 고치기 → 확정 → 한글 다운로드. 주간도 API 로 건너뛰지 않는다.
  // 주 이름 표기는 자주 바뀌어서 끝말 「주간계획안 만들기」로만 찾는다. 확정 창은 연간 · 월간 · 주간이 같은
  // 제목 「이대로 확정할까요?」(PlayMonthlyConfirm CONFIRM_TITLE, 11-07)으로 찾는다.
  await page.getByRole("link", { name: "주간계획안 만들기", exact: true }).click();
  await page.getByRole("button", { name: /주간계획안 만들기$/ }).click();
  await expect(page).toHaveURL(/\/plans\/weekly\?plan_id=\d+/);
  const weeklyText = "낙엽을 모아 우리 반 길을 꾸민다.";
  const weekOutdoor = page
    .getByRole("region", { name: "주간계획안 미리보기", exact: true })
    .getByRole("row")
    .filter({ has: page.getByRole("rowheader", { name: "바깥놀이", exact: true }) })
    .locator("[data-cell]");
  const weekField = page.getByRole("textbox", { name: "바깥놀이", exact: true });
  await weekOutdoor.click();
  await weekField.fill(weeklyText);
  await weekField.blur();
  await expect(page.getByRole("status").filter({ hasText: /^저장됨$/ })).toBeVisible();
  // 화면에만 남은 글자가 아니라 서버에 저장된 글자인지 다시 읽어 본다.
  await page.reload();
  await expect(weekOutdoor).toHaveText(weeklyText);
  await page.getByRole("button", { name: "확정하기", exact: true }).click();
  await page
    .getByRole("group", { name: /이대로 확정할까요\?/ })
    .getByRole("button", { name: "확정하기", exact: true })
    .click();
  await expect(page.getByRole("heading", { name: /주간계획안을 확정했어요$/ })).toBeVisible();
  const weeklyDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "한글 파일(hwpx)로 내려받기", exact: true }).click();
  await verifyHwpx(await weeklyDownload, info.outputPath("pilot-weekly.hwpx"), [weeklyText]);
  await page.screenshot({ path: info.outputPath("weekly-confirmed.png"), fullPage: true });
  const weekPlan = await api(
    page,
    `/api/plans/weekly/${new URL(page.url()).searchParams.get("plan_id")}`,
  );
  expect(weekPlan.status).toBe("CONFIRMED");

  const monthlyList = await api(page, `/api/plans/monthly?class_id=${generated.class_id}`);
  const monthPlan = await api(page, `/api/plans/monthly/${monthlyList.items[0].id}`);
  for (const kind of ["annual", "monthly", "weekly"] as const) {
    await page.goto("/documents");
    await page.getByRole("complementary", { name: "반 선택" }).getByText("햇살반").click();
    await page
      .getByRole("button", {
        name:
          kind === "annual" ? "연간 계획안" : kind === "monthly" ? "월간 계획안" : "주간 계획안",
        exact: true,
      })
      .click();
    if (kind !== "annual") await page.getByLabel("월 선택").fill(monthPlan.target_month);
    const title =
      kind === "annual"
        ? `${generated.school_year}학년도 연간계획안`
        : kind === "monthly"
          ? `${monthPlan.month}월 월간계획안`
          : `${weekPlan.week_id.slice(0, 4)}년 ${Number(weekPlan.week_id.slice(5, 7))}월 ${weekPlan.week_id.split("W")[1]}주차 주간계획안`;
    await page.getByRole("button", { name: new RegExp(title) }).click();
    const preview = page.getByRole("complementary", { name: "문서 미리보기" });
    await expect(
      preview.getByRole("heading", { name: title, exact: true, level: 2 }),
    ).toBeVisible();
    if (kind === "annual") await expect(preview).toContainText("우리 반과 새로운 친구");
    if (kind === "monthly")
      await expect(preview).toContainText("친구와 함께 만드는 새로운 우리 반 놀이");
    if (kind === "weekly") await expect(preview).toContainText(weeklyText);
    await expect(preview.locator("input,textarea,select")).toHaveCount(0);
    const link = preview.getByRole("link", { name: "문서 열기", exact: true });
    await expect(link).toHaveAttribute(
      "href",
      new RegExp(
        kind === "annual"
          ? `/plans/annual/${annualId}`
          : `plan_id=${kind === "monthly" ? monthPlan.id : weekPlan.id}`,
      ),
    );
    await link.click();
    if (kind === "monthly") {
      await expect(cell(0)).toHaveText("친구와 함께 만드는 새로운 우리 반 놀이");
      await expect(cell(0)).not.toHaveAttribute("role", "button");
      await expect(page.getByRole("textbox")).toHaveCount(0);
    }
    if (kind === "weekly") {
      // 보관함 링크로 그 주의 확정본이 열린다. 고칠 수 없다.
      await expect(
        page.getByRole("heading", { name: /주간계획안을 확정했어요$/, level: 1 }),
      ).toBeVisible();
      await expect(weekOutdoor).toHaveText(weeklyText);
      await expect(page.getByRole("textbox")).toHaveCount(0);
    }
  }
});

test("멘토: 일과 입력부터 보육일지 한글 다운로드·평가 현황 반영까지", async ({ page }, info) => {
  const user = await enterPilot(page);
  await page.getByRole("link", { name: "일과 작성하기", exact: true }).click();
  const dateInput = page.getByLabel("날짜", { exact: true });
  const yesterday = new Date((await dateInput.inputValue()) + "T12:00:00Z");
  yesterday.setUTCDate(yesterday.getUTCDate() - 1);
  await dateInput.fill(yesterday.toISOString().slice(0, 10));
  const row = page.locator('[aria-label="일과 목록"] article').first();
  await row.getByLabel("일과 이름").fill("오전 실내놀이");
  // 시작 · 종료 칸은 시계판과 함께 접혀 있다. 열고 고친 뒤 닫는다.
  await row.getByRole("button", { name: /시계로 시간 고르기/ }).click();
  // 깔아 둔 하루의 다른 줄과 겹치면 겹친 시간 알림이 저장을 막는다. 이 줄 자리(07:30~09:00) 안에서 고친다.
  await row.getByLabel("시작 시간", { exact: true }).fill("07:40");
  await row.getByLabel("종료 시간", { exact: true }).fill("08:50");
  await row.getByRole("button", { name: "닫기", exact: true }).click();
  // 「계획한 것」은 접혀 있다.
  await row.locator("details").locator("summary").click();
  await row.getByLabel("계획한 것").fill("자연물과 블록을 제공한다.");
  await row
    .getByLabel("실제로 한 것")
    .fill("유아들이 블록으로 길을 만들고 자연물을 길 옆에 놓았다.");
  // 저장 단추는 없다(ADR-084). 「오늘 일지 만들기」가 근거로 올리고 이 화면에서 바로 초안을 만든다(보관함으로 가지 않는다).
  const response = page.waitForResponse(
    (r) => r.url().endsWith("/api/documents") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: /^(오늘|이날) 일지 만들기 →$/ }).click();
  const generated = await response;
  expect(generated.status()).toBe(201);
  const created = await generated.json();
  await expect(
    page.getByRole("link", { name: "일과 기록에서 고쳐 주세요 →", exact: true }),
  ).toHaveAttribute("href", /\/routines\?date=.*&class_id=\d+/);
  expect(created.child_id).toBeNull();
  // 일지는 칠판 밑에 바로 펼쳐진다. 그 자리에서 확정 · 내려받기까지 간다.
  await expect(page.getByRole("region", { name: /보육일지$/ })).toBeVisible();
  await page.getByRole("checkbox", { name: /원본 기록과 사실이 일치하고/ }).check();
  await page.getByRole("button", { name: "검토 완료 · 문서 확정", exact: true }).click();
  await expect(page.getByText("검토한 문서를 확정했어요.")).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "한글 파일로 내려받기", exact: true }).click();
  const file = await download;
  await verifyHwpx(file, info.outputPath("pilot-daily-log.hwpx"), [
    "유아들이 블록으로 길을 만들고 자연물을 길 옆에 놓았다.",
  ]);
  await page.getByRole("link", { name: "평가 점검", exact: true }).click();
  // 화면 본문은 서류 도장판이고, 평가항목별 보기는 단추를 누르면 오른쪽 서랍에 나온다.
  await page.getByRole("button", { name: /^평가항목 4-1 · 4-2/ }).click();
  await expect(
    page.getByRole("region", { name: "4-1 관찰 및 실행 계획", exact: true }),
  ).toContainText("확정 보육일지 1건");
  const checklist = await api(page, `/api/centers/${user.center_id}/evaluation-checklist`);
  expect(checklist.items[0].count).toBe(1);
  expect(checklist.items[0].verdict).toBe("INSUFFICIENT");
  await page.screenshot({ path: info.outputPath("daily-log-counted.png"), fullPage: true });
});

test("멘토: 관찰 기록에서 관찰일지를 만들고 수정·확정·한글 다운로드한다", async ({
  page,
}, info) => {
  await enterPilot(page);
  const fact = "블록 세 개를 쌓은 뒤 친구에게 같이 만들자고 말했다.";
  await page.getByRole("link", { name: "관찰일지", exact: true }).click();
  // 적는 칸은 늘 펴져 있고, 반은 사이드바가 고른다.
  await page
    .getByRole("group", { name: "아이", exact: true })
    .getByRole("button", { name: "가나다", exact: true })
    .click();
  await page.getByLabel("본 대로 적기").fill(fact);
  // 영역은 기본값이 없다 — 교사가 골라야 저장된다(ADR-082).
  await page
    .getByRole("group", { name: "영역", exact: true })
    .getByRole("button", { name: "사회관계", exact: true })
    .click();
  await page.getByRole("button", { name: "기록하기", exact: true }).click();
  await expect(page.getByText("관찰 기록을 저장했어요.")).toBeVisible();
  // 할 일은 그 줄을 눌러야 나온다 — 줄마다 단추를 세 개씩 두지 않는다.
  await page.locator("article button").first().click();
  await page.getByRole("link", { name: "이 기록으로 일지 만들기", exact: true }).click();
  // 관찰일지는 문서 보관함이 아니라 관찰 기록 아래에서 만든다.
  await expect(page).toHaveURL(/\/records\/journal\?record=/);
  await page.screenshot({ path: info.outputPath("observation-selection.png"), fullPage: true });
  const response = page.waitForResponse(
    (r) => r.url().endsWith("/api/documents") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "초안 만들기", exact: true }).click();
  const generated = await response;
  expect(generated.status()).toBe(201);
  const created = await generated.json();
  // 새 관찰일지 화면은 원문을 「사실」 칸 대신 칠판의 쪽지(근거 기록)로 보인다 — 고칠 수 없다.
  const notes = page.getByRole("list", { name: "근거 기록", exact: true });
  await expect(notes).toBeVisible();
  await expect(page.getByRole("textbox", { name: "사실 내용", exact: true })).toHaveCount(0);
  // 쪽지 한 장에 날짜 · 영역과 원문이 같이 있다 — 쪽지 안에서 원문을 찾는다.
  await expect(notes.getByText(fact)).toBeVisible();
  // 만든 일지는 보관함에도 쌓인다. 거기서 다시 열어 마저 쓴다.
  await page.getByRole("link", { name: "문서 보관함", exact: true }).click();
  await openObservation(page, created);
  await page
    .getByRole("textbox", { name: "해석 내용", exact: true })
    .fill("블록을 쌓고 친구에게 함께 놀이할 것을 제안했다.");
  await page
    .getByRole("textbox", { name: "지원 내용", exact: true })
    .fill("다음 놀이에는 함께 쌓을 수 있는 블록과 넓은 공간을 제공한다.");
  await page.getByRole("checkbox", { name: /원본 기록과 사실이 일치하고/ }).check();
  await page.getByRole("button", { name: "검토 완료 · 문서 확정", exact: true }).click();
  await expect(page.getByText("검토한 문서를 확정했어요.")).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "한글 파일로 내려받기", exact: true }).click();
  await verifyHwpx(await download, info.outputPath("pilot-observation.hwpx"), [
    fact,
    "블록을 쌓고 친구에게 함께 놀이할 것을 제안했다.",
    "다음 놀이에는 함께 쌓을 수 있는 블록과 넓은 공간을 제공한다.",
  ]);
  await page.reload();
  const documents = await api(page, "/api/documents");
  const saved = documents.items.find(
    (document: { kind: string }) => document.kind === "observation",
  );
  // 보관함엔 사이드바로 들어와 눌러서 열었다 — 새로고침하면 보관함 첫 화면이라 다시 연다.
  await openObservation(page, saved);
  await expect(page.getByText("교사 확정", { exact: true }).first()).toBeVisible();
  await page.screenshot({ path: info.outputPath("observation-confirmed.png"), fullPage: true });

  // Read-only facts must lead back to a usable correction/review path.
  await page.getByRole("link", { name: "관찰 기록에서 고쳐 주세요 →", exact: true }).click();
  await page.locator("article button").first().click();
  await page.getByRole("button", { name: "수정", exact: true }).click();
  const updatedFact = fact + " 놀이를 마친 뒤 블록을 바구니에 담았다.";
  await page.getByLabel("본 대로 적기").fill(updatedFact);
  await page.getByRole("button", { name: "고친 대로 저장", exact: true }).click();
  await expect(page.getByText("수정했어요.", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: "문서 보관함", exact: true }).click();
  await openObservation(page, saved);
  await expect(
    page.getByText("이 문서의 근거로 사용된 관찰 기록이 변경되었습니다.", { exact: false }),
  ).toBeVisible();
  await page.getByRole("button", { name: "확정 취소", exact: true }).click();
  await page.getByRole("button", { name: "변경된 근거 반영하기", exact: true }).click();
  await expect(page.getByText(updatedFact, { exact: true }).first()).toBeVisible();
  await page.getByRole("checkbox", { name: /원본 기록과 사실이 일치하고/ }).check();
  await page.getByRole("button", { name: "검토 완료 · 문서 확정", exact: true }).click();
  await expect(page.getByText("검토한 문서를 확정했어요.")).toBeVisible();
});

test("멘토: 평가 점검은 서버의 9개 지표·19개 요소를 보여주고 체크를 보존한다", async ({
  page,
}, info) => {
  const user = await enterPilot(page);
  await page.getByRole("link", { name: "평가 점검", exact: true }).click();
  // 현장에서 보는 19가지는 단추를 누르면 오른쪽 서랍에 나온다.
  await page.getByRole("button", { name: /^나머지 평가항목/ }).click();
  const selfCheck = page.getByRole("dialog", { name: /^나머지 평가항목/ });
  // 안 끝난 첫 평가항목만 펼쳐져 있다. 접힌 평가항목을 하나씩 펼쳐 19개를 센다.
  // 펼칠 때마다 「접힌 것」 목록이 줄어 매번 첫 번째를 다시 찾는다. 영역(section) 밖의 옛 사전점검 접기는 열지 않는다.
  const closed = selfCheck.locator("section details:not([open]) > summary");
  while (await closed.count()) await closed.first().click();
  await expect(selfCheck.getByRole("checkbox")).toHaveCount(19);
  const checklist = await api(page, `/api/centers/${user.center_id}/evaluation-checklist`);
  expect(checklist.items).toHaveLength(9);
  const first = checklist.items.find((item: { kind: string }) => item.kind === "SELF_CHECK")
    .elements[0];
  const check = selfCheck.getByRole("checkbox").first();
  await check.check();
  await expect(page.getByText(/저장됨/)).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: /^나머지 평가항목/ }).click();
  await expect(check).toBeChecked();
  const saved = await api(page, `/api/centers/${user.center_id}/evaluation-checklist`);
  expect(
    saved.items
      .flatMap((item: { elements?: unknown[] }) => item.elements ?? [])
      .find((element: { element: string }) => element.element === first.element).checked,
  ).toBe(true);
  await page.screenshot({ path: info.outputPath("evaluation-checklist.png"), fullPage: true });
});

// 기관 양식 · 트렌드봇은 계획안 첫 화면에서 링크를 뺐다(2026-11-02 결정) — 주소로 들어간다.
test("멘토: 설정·기관 양식·트렌드봇 화면에 진입한다", async ({ page }, info) => {
  const user = await enterPilot(page);
  await page.getByRole("link", { name: "설정", exact: true }).first().click();
  await expect(page.getByRole("heading", { name: "설정", exact: true, level: 1 })).toBeVisible();
  // 트렌드봇은 「기록 · 계획안」 묶음에 있다. 새로 열면 「우리 원」이 먼저 보인다.
  const recordsTab = page.getByRole("tab", { name: "기록 · 계획안", exact: true });
  await recordsTab.click();
  const trends = page.getByRole("checkbox", { name: "트렌드봇 사용", exact: true });
  await expect(trends).not.toBeChecked();
  await trends.click();
  await expect(trends).toBeChecked();
  await page.reload();
  await recordsTab.click();
  await expect(trends).toBeChecked();
  expect((await api(page, `/api/centers/${user.center_id}/settings`)).trends_enabled).toBe(true);
  await page.goto("/templates");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("양식");
  await page.goto("/trends");
  await expect(
    page.getByRole("heading", { name: "트렌드봇", exact: true, level: 1 }),
  ).toBeVisible();
  await expect(page.getByText(/아직 모인 자료가 없어요|에 모았어요/)).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("link", { name: "홈", exact: true })).toBeVisible();
  await page.screenshot({ path: info.outputPath("mobile-trends.png"), fullPage: true });
});

test("멘토: 등록한 반 수정을 시도해도 새 반과 새 아동으로 바꾸지 않는다", async ({ page }) => {
  const user = await enterPilot(page);
  const before = await api(page, `/api/centers/${user.center_id}/classes`);
  await page.getByRole("link", { name: "설정", exact: true }).first().click();
  // 반 쪽지를 떼어 연다. 등록한 반은 고칠 칸 없이 글로만 보인다. 저장 길은 첫 설정 화면과 같다.
  await page.getByRole("button", { name: "반 수 · 담당 반 수정", exact: true }).click();
  const note = page.getByRole("dialog", { name: "반 수 · 담당 반" });
  await expect(note.getByText("햇살반", { exact: true })).toBeVisible();
  await expect(note.getByRole("textbox", { name: "반 이름" })).toHaveCount(0);
  await note.getByRole("button", { name: "저장", exact: true }).click();
  await expect(note).toBeHidden();
  expect(await api(page, `/api/centers/${user.center_id}/classes`)).toEqual(before);
});

test("멘토: 등록한 반을 마지막 확인에서 고치면 같은 반이 바뀌고, 아이가 있으면 동의는 못 끈다", async ({
  page,
}) => {
  const user = await enterPilot(page);
  const before = await api(page, `/api/centers/${user.center_id}/classes`);
  // 설정과 온보딩은 따로 돈다 — 마지막 확인은 주소로 바로 연다.
  await page.goto("/onboarding/review");
  await page.getByRole("button", { name: "햇살반 수정", exact: true }).click();
  await page.getByLabel("반 이름").fill("새싹반");
  await page.getByRole("button", { name: "저장", exact: true }).click();
  await expect(page.getByRole("region", { name: "새싹반 정보" })).toBeVisible();
  // 새 반을 만들지 않고 같은 반의 이름만 바뀐다 — 아이와 기록이 그대로 붙어 있다.
  const after = await api(page, `/api/centers/${user.center_id}/classes`);
  expect(after.items.map((c: { id: number; name: string }) => [c.id, c.name])).toEqual(
    before.items.map((c: { id: number }) => [c.id, "새싹반"]),
  );

  // 아이가 있는 반은 동의를 끌 수 없다 — 알림이 뜨고 체크는 그대로다.
  await page.getByRole("button", { name: "새싹반 수정", exact: true }).click();
  const consent = page.getByLabel("이 반 모든 아동의 법정대리인 동의를 받았습니다.");
  await consent.click();
  await expect(
    page.getByRole("status").filter({ hasText: "아이 명단이 있어 동의를 끌 수 없어요" }),
  ).toBeVisible();
  await expect(consent).toBeChecked();
  await page.getByRole("button", { name: "이전", exact: true }).click();
  await expect(page.getByRole("button", { name: "이대로 시작할게요", exact: true })).toBeVisible();
});
