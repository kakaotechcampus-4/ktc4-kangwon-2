import { readFile } from "node:fs/promises";
import JSZip from "jszip";
import { expect, test, type Download, type Page } from "@playwright/test";

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
  await page.getByRole("link", { name: "로그인하러 가기" }).click();
  await page.getByLabel("이메일").fill(email);
  await page.locator("#auth-password").fill("pilot-password-1234");
  await page.getByRole("button", { name: "로그인", exact: true }).click();
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
  await page.getByRole("link", { name: "계획 노트", exact: true }).click();
  await page.getByRole("link", { name: "계획안 만들기", exact: true }).click();
  await page.getByRole("button", { name: "연간 한 해 놀이 흐름", exact: true }).click();
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

  await page.getByRole("link", { name: "계획 노트", exact: true }).click();
  await page.getByRole("link", { name: "월간 양식 설정", exact: true }).click();
  await page.getByRole("button", { name: /칸으로 양식 만들기/ }).click();
  await expect(page.getByText("새 양식을 만들고 원 기본으로 설정했어요.")).toBeVisible();
  await page.getByRole("link", { name: "계획 노트", exact: true }).click();
  await page.getByRole("link", { name: "월간계획안", exact: true }).click();
  await page.getByRole("button", { name: /월 계획안 만들기/ }).click();
  const field = page.getByRole("textbox", { name: "칸 내용", exact: true }).first();
  await expect(field).toBeVisible();
  const outdoor = page
    .getByRole("row")
    .filter({ has: page.getByRole("rowheader", { name: "바깥놀이", exact: true }) });
  const firstWeek = await page.getByRole("columnheader").nth(1).boundingBox();
  const firstCell = await outdoor.locator("td").first().boundingBox();
  expect(Math.abs(firstWeek!.x - firstCell!.x)).toBeLessThan(2);
  page.once("dialog", (dialog) => dialog.accept());
  const regenerated = page.waitForResponse(
    (response) => response.url().endsWith("/regenerate") && response.request().method() === "POST",
  );
  await outdoor.getByRole("button", { name: "↻ 이 칸만 다시 만들기", exact: true }).first().click();
  expect((await regenerated).status()).toBe(200);
  await field.fill("");
  await field.pressSequentially("친구와 함께 만드는 우리 반 놀이", { delay: 15 });
  // A nested component used to remount this input after every character.
  await expect(field).toBeFocused();
  await expect(field).toHaveValue("친구와 함께 만드는 우리 반 놀이");
  const second = page.getByRole("textbox", { name: "칸 내용", exact: true }).nth(1);
  await second.fill("교사가 준비한 자연물을 함께 살펴본다.");
  await page.getByRole("button", { name: "수정 내용 저장", exact: true }).click();
  await expect(page.getByText("수정한 내용을 저장했어요.")).toBeVisible();
  await page.reload();
  await expect(field).toHaveValue("친구와 함께 만드는 우리 반 놀이");
  await expect(second).toHaveValue("교사가 준비한 자연물을 함께 살펴본다.");
  await field.fill("친구와 함께 만드는 새로운 우리 반 놀이");
  await page.getByRole("button", { name: "확정하기", exact: true }).click();
  await expect(page.getByText("확정했어요. 이제 고칠 수 없어요.")).toBeVisible();
  await page.reload();
  await expect(field).toHaveValue("친구와 함께 만드는 새로운 우리 반 놀이");
  await expect(field).toHaveAttribute("readonly", "");
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
  await page.getByRole("button", { name: "초안 만들기", exact: true }).click();
  await expect(
    page.getByRole("link", { name: "일과 기록에서 고쳐 주세요 →", exact: true }),
  ).toHaveAttribute("href", /\/routines\?date=.*&class_id=\d+/);
  await page.getByRole("checkbox", { name: /원본 기록과 사실이 일치하고/ }).check();
  await page.getByRole("button", { name: "검토 완료 · 문서 확정", exact: true }).click();
  await expect(page.getByText("검토한 문서를 확정했어요.")).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "한글 파일로 내려받기", exact: true }).click();
  const file = await download;
  await verifyHwpx(file, info.outputPath("pilot-daily-log.hwpx"), [
    "유아들이 블록으로 길을 만들고 자연물을 길 옆에 놓았다.",
  ]);
  await page.getByRole("link", { name: "평가 준비", exact: true }).click();
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
  await page.getByRole("button", { name: "초안 만들기", exact: true }).click();
  await expect(page.getByRole("heading", { name: "사실", exact: true })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "사실 내용", exact: true })).toHaveCount(0);
  await expect(page.getByText(fact, { exact: true }).first()).toBeVisible();
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
  await page
    .getByRole("button", { name: new RegExp(saved.title.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")) })
    .click();
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
  await page
    .getByRole("button", { name: new RegExp(saved.title.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")) })
    .click();
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

test("멘토: 평가 준비는 서버의 9개 지표·19개 요소를 보여주고 체크를 보존한다", async ({
  page,
}, info) => {
  const user = await enterPilot(page);
  await page.getByRole("link", { name: "평가 준비", exact: true }).click();
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
  await page.getByRole("link", { name: "계획 노트", exact: true }).click();
  await page.getByRole("link", { name: "기관 양식", exact: true }).click();
  await expect(page.getByRole("heading", { level: 1 })).toContainText("양식");
  await page.getByRole("link", { name: "계획 노트", exact: true }).click();
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
