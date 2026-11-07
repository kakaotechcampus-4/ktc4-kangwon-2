import { expect, type Page } from "@playwright/test";

/**
 * 새 온보딩(한 화면에 질문 하나)을 처음부터 끝까지 지나간다.
 *
 * spec 다섯 개가 각자 같은 순서를 적어 두고 있었다. 화면이 바뀔 때마다 다섯 곳이 함께 깨지므로
 * 여기 한 곳에만 둔다. 부르기 전에 `/onboarding/center` 에 와 있어야 한다 — 거기까지 가는 길
 * (주소로 가기 · 「등록하러 가기」)은 spec 마다 다르다.
 *
 * 아동 이름은 가명이다(CLAUDE.md 개인정보).
 */
export async function completeOnboarding(
  page: Page,
  input: {
    center: string;
    director: string;
    className?: string;
    /** 비우면 가입 때 쓴 이름이 미리 채워진 그대로 둔다. */
    teacher?: string;
    ages?: Array<3 | 4 | 5>;
    consent?: boolean;
    children?: string[];
  },
) {
  const { className = "햇살반", ages = [4], consent = true, children = [] } = input;
  const next = page.getByRole("button", { name: "다음", exact: true });

  // S1 원 정보 — 지역 → 어린이집 찾기 → 원장(ADR-068). 지역은 시트에서 시·도 → 시·군·구 순서로
  // 고른다. 정부 목록에서 고르면 테스트끼리 같은 원으로 묶이므로 「목록에 없어요」로 직접 적는다.
  await expect(page).toHaveURL(/\/onboarding\/center$/);
  await page.locator("button#region").click();
  const sheet = page.getByRole("dialog");
  await sheet.getByRole("button", { name: "강원특별자치도", exact: true }).click();
  await sheet.getByRole("button", { name: "춘천시", exact: true }).click();
  await expect(sheet).toBeHidden();
  await next.click();
  await page.getByRole("button", { name: "목록에 없어요 · 직접 적기", exact: true }).click();
  await page.getByLabel("어린이집 이름").fill(input.center);
  await next.click();
  await page.getByLabel("원장 이름").fill(input.director);
  await next.click();

  // S2 반 정보 — 마지막 「다음」이 반을 등록한다. 확인 시트는 없다(마지막 확인에서 고친다).
  await expect(page).toHaveURL(/\/onboarding\/classes$/);
  await page.getByLabel("반 이름").fill(className);
  await next.click();
  for (const age of ages) await page.getByLabel(`만 ${age}세`, { exact: true }).check();
  await next.click();
  if (input.teacher) await page.getByLabel("담임 이름").fill(input.teacher);
  await next.click();
  // 동의 체크가 있어야 아동 이름을 받는다 — 서버도 동의 전 반에는 아이를 안 받는다(ADR-062).
  if (consent) await page.getByLabel("이 반 모든 아동의 법정대리인 동의를 받았습니다.").check();
  await next.click();

  // S3 아동 명단
  await expect(page).toHaveURL(/\/onboarding\/children$/);
  for (const child of children) {
    await page.getByLabel("아이 이름").fill(child);
    await page.getByRole("button", { name: "추가", exact: true }).click();
    await expect(page.getByRole("button", { name: `${child} 명단에서 빼기` })).toBeVisible();
  }
  if (!consent) await next.click();
  else if (children.length) await page.getByRole("button", { name: /다 넣었어요$/ }).click();
  else await page.getByRole("button", { name: "나중에 넣을게요", exact: true }).click();

  // 마지막 확인 → 완료 화면 → 메인
  await expect(page).toHaveURL(/\/onboarding\/review$/);
  await page.getByRole("button", { name: "이대로 시작할게요", exact: true }).click();
  await expect(page.getByRole("heading", { name: "준비 끝났어요!" })).toBeVisible();
  await page.getByRole("link", { name: "메인으로 가기", exact: true }).click();
  await expect(page).toHaveURL(/\/$/);
}
