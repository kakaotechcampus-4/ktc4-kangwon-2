import { expect, test, type Page } from "@playwright/test";
import { verifyHwpx } from "./hwpx";
import { completeOnboarding } from "./onboarding";

/**
 * 놀이 중심형 연간 → 월간을 교사가 누르는 순서대로 지나간다. 생성은 API 로 건너뛰지 않는다.
 * 놀이 월간 아래에는 주간이 없다(ADR-046 §4) — 이 두 층이 전부다.
 *
 * mock 후보 이름은 실행마다 바뀐다. 이름이 아니라 순서로 고르고, 모델 글은 기대값으로 두지 않는다(ADR-023).
 */
async function enter(page: Page) {
  const email = `play-${Date.now()}-${Math.random().toString(36).slice(2, 7)}@example.com`;
  await page.goto("/signup");
  await page.getByLabel("선생님 이름").fill("놀이교사");
  await page.getByLabel("이메일").fill(email);
  await page.locator("#auth-password").fill("play-password-1234");
  await page.getByLabel("비밀번호 확인").fill("play-password-1234");
  await page.getByRole("button", { name: "회원가입", exact: true }).click();
  await expect(page.getByRole("heading", { name: "가입을 완료했어요" })).toBeVisible();
  await page.getByRole("link", { name: "메인화면으로 가기", exact: true }).click();
  await expect(page).toHaveURL(/\/$/);
  await page.goto("/onboarding");
  await completeOnboarding(page, { center: "놀이어린이집", director: "가상원장" });
  await expect(page.getByRole("heading", { name: "지금, 한 줄", exact: true })).toBeVisible();
}

async function api(page: Page, path: string) {
  const token = await page.evaluate(() => sessionStorage.getItem("saessak.authToken"));
  const response = await page.request.get(path, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(response.ok(), await response.text()).toBeTruthy();
  return response.json();
}

/**
 * 고르기 판(연간 놀이 · 월간 활동이 같은 판)에서 목록마다 앞에서 5개를 고른다 — 확정하려면 정확히 5개다.
 * 고른 줄은 위로 올라가서, 아직 안 고른 첫 줄은 늘 n 번째다. 줄을 누르면 「놀이 자세히」에 뜨고
 * 거기 「… 고르기」가 고른다. 마지막 목록이 아니면 「다음 목록 고르러 가기」로 넘어간다.
 * 후보 목록은 한 번에 하나만 보인다. 이름이 판마다 달라서(「봄 놀이 후보」 · 「함께 하는 활동 후보」) 끝말로 찾는다.
 */
async function pickFive(page: Page, lists: string[]) {
  const detail = page.getByRole("region", { name: "놀이 자세히", exact: true });
  const rows = page.getByRole("region", { name: / 후보$/ }).getByRole("listitem");
  for (const [i, list] of lists.entries()) {
    for (let n = 0; n < 5; n++) {
      await rows.nth(n).getByRole("button").click();
      await detail.getByRole("button", { name: / 고르기$/ }).click();
    }
    await expect(page.getByRole("tab", { name: `${list} 5/5`, exact: true })).toBeVisible();
    const next = lists[i + 1];
    await page
      .getByRole("button", { name: next ? `${next} 고르러 가기` : "문서 만들기", exact: true })
      .click();
  }
}

test("놀이 중심형: 연간 놀이 고르기·칸 수정·확정·한글 다운로드와 월간 활동 고르기·칸 수정·확정·한글 다운로드", async ({
  page,
}, info) => {
  await enter(page);
  await page.getByRole("link", { name: "계획안", exact: true }).click();
  // 첫 화면에 방식 칸이 둘이고 칸마다 「연간부터 시작하기」가 있다 — 놀이 중심형 쪽을 주소로 가린다.
  await page
    .getByRole("link", { name: "연간부터 시작하기", exact: true })
    .and(page.locator('[href$="format=PLAY_PROJECT"]'))
    .click();
  await page.getByRole("button", { name: "연간계획안 만들기", exact: true }).click();
  await expect(page).toHaveURL(/\/plans\/annual\/\d+$/);
  const annualId = page.url().split("/").at(-1);

  // ④ 놀이 고르기 → ⑤ 다듬기. 주소는 그대로다.
  await expect(page.getByRole("heading", { name: "놀이 고르기", level: 1 })).toBeVisible();
  await pickFive(page, ["봄", "여름", "가을", "겨울"]);
  const sheet = page.getByRole("region", { name: "문서 미리보기", exact: true });
  await sheet.getByRole("tab", { name: /^봄/ }).click();
  // 문서 칸은 단추다. 이름이 「놀이명 값 + 열 이름」이라 끝말로 봄 첫 놀이의 놀이명 칸을 찾는다.
  await sheet
    .getByRole("button", { name: / 놀이명$/ })
    .first()
    .click();
  // 칸 단추의 이름에도 「놀이명」이 들어가서 getByLabel 이 아니라 textbox 로 찾는다.
  const playName = page.getByRole("textbox", { name: "놀이명", exact: true });
  const annualText = "솔방울로 길 만들기 놀이";
  // 「저장됨」은 고를 때부터 떠 있다 — 그 글 대신 이 칸의 저장 응답을 기다린다.
  const annualSave = page.waitForResponse(
    (r) =>
      r.request().method() === "PUT" &&
      r.url().includes(`/api/plans/annual/${annualId}/cells/`) &&
      (r.request().postData() ?? "").includes(annualText),
  );
  await playName.fill(annualText);
  await playName.blur();
  expect((await annualSave).ok()).toBeTruthy();
  // 새로고침하면 봄부터 다시 연다. 화면에만 남은 글이 아니라 서버에 저장된 글인지 본다.
  await page.reload();
  await expect(
    sheet.getByRole("button", { name: `${annualText} 놀이명`, exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "확정하기", exact: true }).click();
  await page
    .getByRole("group", { name: /이대로 확정할까요\?/ })
    .getByRole("button", { name: "확정하기", exact: true })
    .click();
  await expect(page.getByRole("heading", { name: /연간계획안을 확정했어요$/ })).toBeVisible();
  const annualDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "한글 파일(hwpx)로 내려받기", exact: true }).click();
  await verifyHwpx(await annualDownload, info.outputPath("play-annual.hwpx"), [annualText]);

  // 확정 화면 → 월간 만들기. 기본 달은 오늘이라 3월로 못박는다 — 봄이라 위에서 고친 놀이를 이어받는다.
  await page.getByRole("link", { name: "월간계획안 만들기", exact: true }).click();
  await page
    .getByRole("radiogroup", { name: "달", exact: true })
    .getByRole("radio", { name: "3월", exact: true })
    .click();
  await expect(page.getByRole("checkbox", { name: annualText, exact: true })).toBeVisible();
  await page.getByRole("button", { name: /월간계획안 만들기$/ }).click();
  await expect(page).toHaveURL(/\/plans\/monthly\/play\/\d+$/);
  const monthlyId = page.url().split("/").at(-1);

  // 활동 고르기 판(ADR-065)이 먼저 열린다 → 다 고르면 다듬기.
  await expect(page.getByRole("heading", { name: "활동 고르기", level: 1 })).toBeVisible();
  await pickFive(page, ["함께 하는 활동", "유아 예상 자유놀이"]);
  const monthly = page.getByRole("region", { name: "놀이 중심 월간계획안 미리보기", exact: true });
  // 활동 줄은 함께 하는 활동이 먼저 그려진다. mock 글(「함께 놀이 1」) 대신 자리로 첫 줄을 찾는다.
  const together = monthly.locator("[data-play-row]").first().locator("[data-cell]");
  await together.click();
  const rowName = page.getByRole("textbox", { name: "놀이 행 이름", exact: true });
  const monthlyText = "솔방울 길 따라 걷기";
  const monthlySave = page.waitForResponse(
    (r) =>
      r.request().method() === "PUT" &&
      r.url().includes(`/api/plans/monthly/play/${monthlyId}/cells/`) &&
      (r.request().postData() ?? "").includes(monthlyText),
  );
  await rowName.fill(monthlyText);
  await rowName.blur();
  expect((await monthlySave).ok()).toBeTruthy();
  await page.reload();
  await expect(together).toHaveText(monthlyText);
  await page.getByRole("button", { name: "확정하기", exact: true }).click();
  await expect(page.getByRole("heading", { name: /월간계획안을 확정했어요$/ })).toBeVisible();
  // 놀이 월간 아래에는 주간이 없다(ADR-046 §4). 다음 단계는 다음 달 월간이다.
  await expect(page.getByRole("link", { name: /주간계획안 만들기/ })).toHaveCount(0);
  const monthlyDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "한글 파일(hwpx)로 내려받기", exact: true }).click();
  await verifyHwpx(await monthlyDownload, info.outputPath("play-monthly.hwpx"), [monthlyText]);

  expect((await api(page, `/api/plans/annual/${annualId}`)).status).toBe("CONFIRMED");
  // 봄 안의 달(3 · 4 · 5월)은 이어받는 놀이가 같다 — 고른 달이 3월로 만들어졌는지는 서버 값으로 본다.
  expect(await api(page, `/api/plans/monthly/play/${monthlyId}`)).toMatchObject({
    status: "CONFIRMED",
    month: 3,
  });
});
