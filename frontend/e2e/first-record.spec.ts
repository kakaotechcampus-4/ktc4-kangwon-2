import { expect, test } from "@playwright/test";

/**
 * 교사가 처음 하는 일 — 가입 → 원 → 반 → 아동 → 관찰 기록 → 아이별 모아보기.
 *
 * MSW 를 끈 실제 스택(Postgres · FastAPI · Next)에서 돈다. 화면이 실제 API 를 타는지가
 * 목적이라 목 데이터로 통과하면 의미가 없다. ADR-028.
 * 아동 이름은 가명이다(CLAUDE.md 개인정보). 이메일은 실행마다 새로 만든다.
 */
test("가입부터 관찰 기록까지", async ({ page }) => {
  const email = `e2e-${Date.now()}@example.com`;
  const password = "e2e-password-1234";
  const child = "가나다";
  const fact = "블록 세 개를 쌓은 뒤 더 높이 만들래라고 말했다.";

  // 가입 → 로그인
  await page.goto("/signup");
  await page.getByLabel("선생님 이름").fill("테스트교사");
  await page.getByLabel("이메일").fill(email);
  await page.locator("#auth-password").fill(password);
  await page.getByLabel("비밀번호 확인").fill(password);
  await page.getByRole("button", { name: "회원가입" }).click();
  await page.getByRole("link", { name: "로그인하러 가기" }).click();
  await page.getByLabel("이메일").fill(email);
  await page.locator("#auth-password").fill(password);
  await page.getByRole("button", { name: "로그인" }).click();

  // S1 원 정보
  await expect(page).toHaveURL(/\/onboarding\/center$/);
  await page.getByLabel("원명").fill("테스트어린이집");
  await page.getByLabel("원장 이름").fill("테스트원장");
  await page.getByLabel("시·도").selectOption("강원특별자치도");
  await page.getByLabel("시·군·구").selectOption("춘천시");
  await page.getByRole("button", { name: "다음" }).click();

  // S2 반 정보 — 동의 체크가 있어야 아동 이름을 받는다(CLAUDE.md 개인정보).
  await expect(page).toHaveURL(/\/onboarding\/classes$/);
  await page.getByLabel("반 이름").fill("햇살반");
  await page.getByLabel("만 4세").check();
  await page.getByLabel("담임 이름").fill("테스트교사");
  await page.getByLabel("이 반 모든 아동의 법정대리인 동의를 받았습니다.").check();
  await page.getByRole("button", { name: "다음" }).click();

  // S3 아동 명단
  await expect(page).toHaveURL(/\/onboarding\/children$/);
  await page.getByLabel("아동 추가").fill(child);
  await page.getByRole("button", { name: "+ 추가" }).click();
  await expect(page.getByRole("button", { name: `${child} 삭제` })).toBeVisible();
  await page.getByRole("button", { name: "설정 완료" }).click();
  await expect(page).not.toHaveURL(/\/onboarding/);

  // 관찰 기록 한 건
  await page.goto("/records");
  await page.getByRole("combobox", { name: "담당 반" }).selectOption({ label: "햇살반" });
  await page.getByRole("combobox", { name: "아동", exact: true }).selectOption({ label: child });
  await page.getByLabel("실제로 관찰한 사실").fill(fact);
  await page.getByRole("button", { name: "관찰 기록 저장" }).click();
  await expect(page.getByText("관찰 기록을 저장했어요.")).toBeVisible();

  // 아이별 모아보기 — 서버에서 다시 읽은 건수
  await page.goto("/records/children");
  await expect(page.getByRole("button", { name: `${child} · 1건` })).toBeVisible();
  await expect(page.getByText("관찰 기록 1건")).toBeVisible();
});
