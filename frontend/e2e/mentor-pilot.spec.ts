import { readFile } from "node:fs/promises";
import JSZip from "jszip";
import { expect, test, type Download, type Page } from "@playwright/test";

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

/** 생성한 문서의 날짜·아동·종류를 유지한 채 목록으로 돌아가 다시 연다. */
async function reopenCreated(
  page: Page,
  doc: { title: string; kind: string; start: string; child_name: string | null },
) {
  await expect(page.getByRole("heading", { name: doc.title, exact: true, level: 2 })).toBeVisible();
  await page.getByRole("button", { name: "← 문서 목록으로 돌아가기", exact: true }).click();
  for (const name of ["연간 계획안", "월간 계획안", "주간 계획안", "보육일지", "관찰일지"])
    await expect(page.getByRole("button", { name, exact: true })).toBeVisible();
  await expect(page.getByLabel("날짜 선택")).toHaveValue(doc.start);
  await expect(
    page.getByRole("button", {
      name: doc.kind === "observation" ? "관찰일지" : "보육일지",
      exact: true,
    }),
  ).toHaveAttribute("aria-pressed", "true");
  if (doc.kind === "observation")
    await expect(page.getByRole("button", { name: doc.child_name!, exact: true })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  else await expect(page.getByLabel("아동 이름 검색")).toHaveCount(0);
  await page
    .getByRole("button", { name: new RegExp(doc.title.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")) })
    .click();
  await page
    .getByRole("complementary", { name: "문서 미리보기" })
    .getByRole("button", { name: /^(편집하기|문서 열기)$/ })
    .click();
  await expect(page.getByRole("heading", { name: doc.title, exact: true, level: 2 })).toBeVisible();
}

async function verifyHwpx(file: Download, path: string, expected: string[]) {
  expect(file.suggestedFilename()).toMatch(/\.hwpx$/);
  await file.saveAs(path);
  const archive = await JSZip.loadAsync(await readFile(path));
  const section = await archive.file("Contents/section0.xml")!.async("string");
  const preview = await archive.file("Preview/PrvText.txt")!.async("string");
  for (const text of expected) {
    expect(section).toContain(text);
    expect(preview).toContain(text);
  }
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
  await expect(page).toHaveURL(/\/onboarding\/center$/);
  await page.getByLabel("원명").fill("파일럿어린이집");
  await page.getByLabel("원장 이름").fill("가상원장");
  await page.getByLabel("시·도").selectOption("강원특별자치도");
  await page.getByLabel("시·군·구").selectOption("춘천시");
  await page.getByRole("button", { name: "다음", exact: true }).click();
  await page.getByLabel("반 이름").fill("햇살반");
  await page.getByLabel("만 4세", { exact: true }).check();
  await page.getByLabel("담임 이름").fill("파일럿교사");
  await page.getByLabel("이 반 모든 아동의 법정대리인 동의를 받았습니다.").check();
  await page.getByRole("button", { name: "다음", exact: true }).click();
  await page.getByLabel("아동 추가").fill("가나다");
  await page.getByRole("button", { name: "+ 추가", exact: true }).click();
  await page.getByRole("button", { name: "설정 완료", exact: true }).click();
  await expect(page.getByRole("heading", { name: "우리 반", exact: true, level: 1 })).toBeVisible();
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

test("멘토: 연간 생성·편집·확정·한글 다운로드와 월간 연속 입력·저장", async ({ page }, info) => {
  await enterPilot(page);
  await page.getByRole("link", { name: "계획안", exact: true }).click();
  await page.getByRole("link", { name: "계획안 만들기", exact: true }).click();
  await page.getByRole("button", { name: "연간 한 해 놀이 흐름", exact: true }).click();
  await page.getByRole("button", { name: /^월별 주제형/ }).click();
  await page.getByRole("button", { name: "계획안 생성하기", exact: true }).click();
  await expect(page).toHaveURL(/\/plans\/annual\/\d+$/);
  const annualId = page.url().split("/").at(-1);
  const generated = await api(page, `/api/plans/annual/${annualId}`);
  expect(generated.months).toHaveLength(12);
  expect(
    generated.months.every((month: { sub_themes: string[] }) => month.sub_themes.length >= 2),
  ).toBeTruthy();
  await page.getByRole("button", { name: "내용 수정", exact: true }).click();
  await page.getByLabel("3월 활동명", { exact: true }).fill("우리 반과 새로운 친구");
  await page
    .getByLabel("3월 활동 내용", { exact: true })
    .fill("우리 반 이름 알아보기\n친구와 인사 나누기");
  // 연간 안전교육 칸은 꺼 뒀다(2026-10-22) — 화면에 입력이 없고, 저장해도 서버 값을 건드리지 않는다.
  await expect(page.getByLabel("3월 안전교육 입력", { exact: true })).toHaveCount(0);
  await page.screenshot({ path: info.outputPath("annual-edit.png"), fullPage: true });
  await page.getByRole("button", { name: "수정 완료" }).click();
  // 클릭이 끝나도 월별 PUT 저장은 진행 중일 수 있어 완료 안내를 기다린 뒤 새로고침한다.
  await expect(page.getByText("수정한 내용을 저장했어요.", { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByText("우리 반과 새로운 친구", { exact: true })).toBeVisible();
  await expect(page.locator("#plan-document").getByText(/안전교육/)).toHaveCount(0);
  const savedAnnual = await api(page, `/api/plans/annual/${annualId}`);
  expect(savedAnnual.months[0].safety_education_state).toBe("SOURCE_REQUIRED");
  await page.getByRole("button", { name: "연간계획안 확정", exact: true }).click();
  await expect(page.getByRole("button", { name: "확정됨", exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: /다시 생성하기/ })).toBeDisabled();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: /한글 파일로 내려받기/ }).click();
  await verifyHwpx(await download, info.outputPath("pilot-annual.hwpx"), [
    "우리 반과 새로운 친구",
    "우리 반 이름 알아보기",
    "친구와 인사 나누기",
  ]);
  await page.screenshot({ path: info.outputPath("annual-confirmed.png"), fullPage: true });

  await page.getByRole("link", { name: "계획안", exact: true }).click();
  await page.getByRole("link", { name: "월간 양식 설정", exact: true }).click();
  // Latest approved version is preselected. Switching versions drops picks the other one lacks.
  const base = page.getByLabel("기반 양식");
  await expect(base).toHaveValue("monthly-template-a-v0.2.2");
  await page.getByRole("checkbox", { name: /실내 대체활동/ }).check();
  await base.selectOption("monthly-template-a-v0.2.1");
  await base.selectOption("monthly-template-a-v0.2.2");
  await expect(page.getByRole("checkbox", { name: /실내 대체활동/ })).not.toBeChecked();
  await page.getByRole("button", { name: /칸으로 양식 만들기/ }).click();
  await expect(page.getByText("새 양식을 만들고 원 기본으로 설정했어요.")).toBeVisible();
  await page.getByRole("link", { name: "계획안", exact: true }).click();
  await page.getByRole("link", { name: "월간계획안", exact: true }).click();
  await page.getByRole("button", { name: /월 계획안 만들기/ }).click();
  // 놀이 월간과 같은 화면: 문서에서 칸을 누르면 옆 패널에서 고치고, 입력을 멈추거나 떠나면 저장한다.
  const doc = page.getByRole("region", { name: "월간계획안 미리보기", exact: true });
  const outdoor = doc
    .getByRole("row")
    .filter({ has: page.getByRole("rowheader", { name: "바깥놀이", exact: true }) });
  const firstWeek = await doc.getByRole("columnheader").nth(1).boundingBox();
  const firstCell = await outdoor.locator("td").first().boundingBox();
  expect(Math.abs(firstWeek!.x - firstCell!.x)).toBeLessThan(2);
  const cell = (n: number) => outdoor.locator("td").nth(n).locator("[data-cell]");
  const field = page.getByRole("textbox", { name: /^바깥놀이 · / });
  await cell(0).click();
  await expect(cell(0)).toHaveAttribute("aria-pressed", "true");
  await expect(field).toBeVisible();
  page.once("dialog", (dialog) => dialog.accept());
  const regenerated = page.waitForResponse(
    (response) => response.url().endsWith("/regenerate") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "↻ 이 칸만 다시 만들기", exact: true }).click();
  expect((await regenerated).status()).toBe(200);
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
  await expect(page.getByText("저장됨", { exact: true })).toBeVisible();
  await page.reload();
  await expect(cell(0)).toHaveText("친구와 함께 만드는 우리 반 놀이");
  await expect(cell(1)).toHaveText("교사가 준비한 자연물을 함께 살펴본다.");
  await cell(0).click();
  await field.fill("친구와 함께 만드는 새로운 우리 반 놀이");
  await page.getByRole("button", { name: "확정하기", exact: true }).click();
  await expect(page.getByText("확정했어요. 이제 고칠 수 없어요.")).toBeVisible();
  await page.reload();
  await expect(cell(0)).toHaveText("친구와 함께 만드는 새로운 우리 반 놀이");
  await expect(cell(0)).not.toHaveAttribute("role", "button");
  await expect(page.getByRole("textbox")).toHaveCount(0);
  const monthlyDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "한글 파일로 내려받기", exact: true }).click();
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
  await page.setViewportSize({ width: 1600, height: 1000 });
  const monthlyList = await api(page, `/api/plans/monthly?class_id=${generated.class_id}`);
  const monthPlan = await api(page, `/api/plans/monthly/${monthlyList.items[0].id}`);
  const week = monthPlan.weeks.find((w: { active: boolean }) => w.active);
  const auth = await page.evaluate(() => sessionStorage.getItem("saessak.authToken"));
  const weeklyResponse = await page.request.post("/api/plans/weekly", {
    headers: { Authorization: `Bearer ${auth}` },
    data: { class_id: generated.class_id, week_id: week.week_id },
  });
  expect(weeklyResponse.status()).toBe(201);
  const weekPlan = await weeklyResponse.json();
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
      // 보관함 링크가 고른 주가 「보는 중」이고, 그 주 계획안이 열린다.
      await expect(
        page
          .getByRole("navigation", { name: `${monthPlan.month}월의 주` })
          .locator('[aria-current="true"]'),
      ).toContainText(week.label);
      await expect(
        page.getByRole("heading", { name: week.label, exact: true, level: 2 }),
      ).toBeVisible();
    }
  }
});

test("멘토: 일과 입력부터 보육일지 한글 다운로드·평가 현황 반영까지", async ({ page }, info) => {
  const user = await enterPilot(page);
  await page.getByRole("link", { name: "오늘 일과 적기", exact: true }).click();
  const dateInput = page.getByLabel("날짜", { exact: true });
  const yesterday = new Date((await dateInput.inputValue()) + "T12:00:00Z");
  yesterday.setUTCDate(yesterday.getUTCDate() - 1);
  await dateInput.fill(yesterday.toISOString().slice(0, 10));
  const row = page.locator('[aria-label="일과 목록"] article').first();
  await row.getByLabel("일과 이름").fill("오전 실내놀이");
  for (const [label, hour] of [
    ["시작", "09"],
    ["종료", "10"],
  ]) {
    await row.getByLabel(`${label} 시`, { exact: true }).selectOption(hour);
    await row.getByLabel(`${label} 분`, { exact: true }).selectOption("00");
  }
  await row.getByLabel("활동계획").fill("자연물과 블록을 제공한다.");
  await row.getByLabel("활동실행").fill("유아들이 블록으로 길을 만들고 자연물을 길 옆에 놓았다.");
  await page.getByRole("button", { name: "오늘 일지 만들기 →", exact: true }).click();
  await page
    .getByRole("group", { name: "문서에 사용할 일과" })
    .getByRole("checkbox")
    .first()
    .check();
  const response = page.waitForResponse(
    (r) => r.url().endsWith("/api/documents") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "초안 만들기", exact: true }).click();
  const generated = await response;
  expect(generated.status()).toBe(201);
  const created = await generated.json();
  await expect(
    page.getByRole("link", { name: "일과 기록에서 고쳐 주세요 →", exact: true }),
  ).toHaveAttribute("href", /\/routines\?date=.*&class_id=\d+/);
  expect(created.child_id).toBeNull();
  await reopenCreated(page, created);
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
  await expect(
    page.getByRole("region", { name: "4-1 관찰 및 실행 계획", exact: true }),
  ).toContainText("집계에 들어간 문서 1건");
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
  await page.getByRole("link", { name: "관찰 기록", exact: true }).click();
  // 적는 칸은 접혀 있다 — 목록이 먼저다.
  await page.getByRole("button", { name: "＋ 새 관찰 기록 쓰기" }).click();
  await page
    .getByRole("combobox", { name: "담당 반", exact: true })
    .selectOption({ label: "햇살반" });
  await page.getByRole("combobox", { name: "아동", exact: true }).selectOption({ label: "가나다" });
  await page.getByLabel("실제로 관찰한 사실").fill(fact);
  await page.getByRole("button", { name: "관찰 기록 저장", exact: true }).click();
  await expect(page.getByText("관찰 기록을 저장했어요.")).toBeVisible();
  await page.getByRole("link", { name: "관찰일지 만들기", exact: true }).click();
  await expect(page).toHaveURL(/\/documents/);
  await page.screenshot({ path: info.outputPath("observation-selection.png"), fullPage: true });
  const response = page.waitForResponse(
    (r) => r.url().endsWith("/api/documents") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "초안 만들기", exact: true }).click();
  const generated = await response;
  expect(generated.status()).toBe(201);
  const created = await generated.json();
  await expect(page.getByRole("heading", { name: "사실", exact: true })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "사실 내용", exact: true })).toHaveCount(0);
  await expect(page.getByText(fact, { exact: true }).first()).toBeVisible();
  await reopenCreated(page, created);
  await page
    .getByRole("textbox", { name: "해석 내용", exact: true })
    .fill("블록을 쌓고 친구에게 함께 놀이할 것을 제안했다.");
  await page
    .getByRole("textbox", { name: "지원 내용", exact: true })
    .fill("다음 놀이에는 함께 쌓을 수 있는 블록과 넓은 공간을 제공한다.");
  await page.getByRole("checkbox").check();
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
  await page.getByRole("button", { name: "보관함 보기", exact: true }).click();
  await openObservation(page, saved);
  await expect(page.getByText("교사 확정", { exact: true }).first()).toBeVisible();
  await page.screenshot({ path: info.outputPath("observation-confirmed.png"), fullPage: true });

  // Read-only facts must lead back to a usable correction/review path.
  await page.getByRole("link", { name: "관찰 기록에서 고쳐 주세요 →", exact: true }).click();
  await page
    .getByRole("combobox", { name: "담당 반", exact: true })
    .selectOption({ label: "햇살반" });
  await page.getByRole("button", { name: "기록 수정", exact: true }).click();
  const updatedFact = fact + " 놀이를 마친 뒤 블록을 바구니에 담았다.";
  await page.getByLabel("실제로 관찰한 사실").fill(updatedFact);
  await page.getByRole("button", { name: "수정 저장", exact: true }).click();
  await expect(page.getByText("수정했어요.", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: "문서 보관함", exact: true }).click();
  await openObservation(page, saved);
  await expect(
    page.getByText("이 문서의 근거로 사용된 관찰 기록이 변경되었습니다.", { exact: false }),
  ).toBeVisible();
  await page.getByRole("button", { name: "확정 취소", exact: true }).click();
  await page.getByRole("button", { name: "변경된 근거 반영하기", exact: true }).click();
  await expect(page.getByText(updatedFact, { exact: true }).first()).toBeVisible();
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "검토 완료 · 문서 확정", exact: true }).click();
  await expect(page.getByText("검토한 문서를 확정했어요.")).toBeVisible();
});

test("멘토: 평가 점검은 서버의 9개 지표·19개 요소를 보여주고 체크를 보존한다", async ({
  page,
}, info) => {
  const user = await enterPilot(page);
  await page.getByRole("link", { name: "평가 점검", exact: true }).click();
  await page.getByRole("tab", { name: /^자체평가/ }).click();
  // 안 끝난 첫 평가항목만 펼쳐져 있다. 접힌 평가항목을 하나씩 펼쳐 19개를 센다.
  // 펼칠 때마다 「접힌 것」 목록이 줄어 매번 첫 번째를 다시 찾는다. 영역(section) 밖의 옛 사전점검 접기는 열지 않는다.
  const closed = page
    .getByRole("tabpanel", { name: /^자체평가/ })
    .locator("section details:not([open]) > summary");
  while (await closed.count()) await closed.first().click();
  await expect(page.getByRole("checkbox")).toHaveCount(19);
  const checklist = await api(page, `/api/centers/${user.center_id}/evaluation-checklist`);
  expect(checklist.items).toHaveLength(9);
  const first = checklist.items.find((item: { kind: string }) => item.kind === "SELF_CHECK")
    .elements[0];
  const check = page.getByRole("checkbox").first();
  await check.check();
  await expect(page.getByText(/저장됨/)).toBeVisible();
  await page.reload();
  await expect(check).toBeChecked();
  const saved = await api(page, `/api/centers/${user.center_id}/evaluation-checklist`);
  expect(
    saved.items
      .flatMap((item: { elements?: unknown[] }) => item.elements ?? [])
      .find((element: { element: string }) => element.element === first.element).checked,
  ).toBe(true);
  await page.screenshot({ path: info.outputPath("evaluation-checklist.png"), fullPage: true });
});

test("멘토: 설정·기관 양식·트렌드봇 화면에 클릭으로 진입한다", async ({ page }, info) => {
  const user = await enterPilot(page);
  await page.getByRole("link", { name: "설정", exact: true }).first().click();
  await expect(page.getByRole("heading", { name: "설정", exact: true, level: 1 })).toBeVisible();
  const trends = page.getByRole("checkbox", { name: "트렌드봇 사용", exact: true });
  await expect(trends).not.toBeChecked();
  await trends.click();
  await expect(trends).toBeChecked();
  await page.reload();
  await expect(trends).toBeChecked();
  expect((await api(page, `/api/centers/${user.center_id}/settings`)).trends_enabled).toBe(true);
  await page.getByRole("button", { name: "초대 코드 만들기", exact: true }).click();
  await expect(page.getByText(/초대 코드 [A-Z2-9]{10}/)).toBeVisible();
  await page.getByRole("link", { name: "계획안", exact: true }).click();
  await page.getByRole("link", { name: "기관 양식", exact: true }).click();
  await expect(page.getByRole("heading", { level: 1 })).toContainText("양식");
  await page.getByRole("link", { name: "계획안", exact: true }).click();
  await page.getByRole("link", { name: "트렌드봇", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "트렌드봇", exact: true, level: 1 }),
  ).toBeVisible();
  await expect(page.getByText(/아직 모인 자료가 없어요|에 모았어요/)).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("link", { name: "우리 반", exact: true })).toBeVisible();
  await page.screenshot({ path: info.outputPath("mobile-trends.png"), fullPage: true });
});

test("멘토: 등록한 반 수정을 시도해도 새 반과 새 아동으로 바꾸지 않는다", async ({ page }) => {
  const user = await enterPilot(page);
  const before = await api(page, `/api/centers/${user.center_id}/classes`);
  await page.getByRole("link", { name: "설정", exact: true }).first().click();
  await page.getByRole("link", { name: "반·담당 반 관리", exact: true }).click();
  await expect(page.getByLabel("반 이름")).toHaveValue("햇살반");
  await page.getByLabel("반 이름").fill("바꿀 수 없는 반 이름");
  await page.getByRole("button", { name: "다음", exact: true }).click();
  await expect(
    page.getByRole("alert").filter({ hasText: "기존 아동과 기록을 보호" }),
  ).toBeVisible();
  expect(await api(page, `/api/centers/${user.center_id}/classes`)).toEqual(before);
});
