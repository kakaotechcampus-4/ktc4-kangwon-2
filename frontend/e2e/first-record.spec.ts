import { expect, test } from "@playwright/test";

/**
 * 교사가 처음 하는 일 — 가입 → 원 → 반 → 아동 → 관찰 기록 → 아이들 전부 보기.
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

  // 가입 → 온보딩
  await page.goto("/signup");
  await page.getByLabel("선생님 이름").fill("테스트교사");
  await page.getByLabel("이메일").fill(email);
  await page.locator("#auth-password").fill(password);
  await page.getByLabel("비밀번호 확인").fill(password);
  await page.getByRole("button", { name: "회원가입" }).click();

  // 가입하면 완료 카드가 뜨고, 메인은 원·반 없이도 열린다.
  await expect(page.getByRole("heading", { name: "가입을 완료했어요" })).toBeVisible();
  await expect(page).toHaveURL(/\/signup$/);
  await page.getByRole("link", { name: "메인화면으로 가기", exact: true }).click();
  await expect(page).toHaveURL(/\/$/);
  // 원·반이 비면 메인 날짜 아래에 등록 안내가 뜬다.
  const roomSetup = page.getByRole("heading", { name: "선생님, 우리 반부터 알려 주세요!" });
  await expect(roomSetup).toBeVisible();

  // 문서 보관함도 원·반 없이 열린다 — 안내 카드 대신 보관함이 그려진다.
  const roomGate = page.getByRole("heading", { name: "원·반을 먼저 등록해 주세요" });
  await page
    .getByRole("complementary", { name: "주 메뉴" })
    .getByRole("link", { name: "문서 보관함", exact: true })
    .click();
  await expect(page).toHaveURL(/\/documents$/);
  await expect(
    page.getByRole("heading", { name: "반을 선택해 주세요", exact: true }),
  ).toBeVisible();
  await expect(roomGate).toHaveCount(0);

  // 그 밖의 메뉴는 원·반이 있어야 열린다 — 안내 카드에서 온보딩으로 간다.
  await page
    .getByRole("complementary", { name: "주 메뉴" })
    .getByRole("link", { name: "계획안", exact: true })
    .click();
  await expect(roomGate).toBeVisible();
  await page.getByRole("link", { name: "등록하러 가기", exact: true }).click();

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
  // 마치면 메인으로 돌아오고, 원·반이 찼으니 안내는 없다. 홈의 h1 은 날짜라 매일 달라진다 —
  // 적는 칸 제목으로 「도착했나」를 먼저 본다. 안 그러면 그리기 전이라 0개로 통과한다.
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("heading", { name: "지금, 한 줄", exact: true })).toBeVisible();
  await expect(roomSetup).toHaveCount(0);

  // 관찰 기록 한 건
  await page.goto("/records");
  // 적는 칸은 접혀 있다 — 목록이 먼저다.
  await page.getByRole("button", { name: "＋ 새 관찰 기록 쓰기" }).click();
  await page.getByRole("combobox", { name: "담당 반" }).selectOption({ label: "햇살반" });
  await page.getByRole("combobox", { name: "아동", exact: true }).selectOption({ label: child });
  await page.getByLabel("실제로 관찰한 사실").fill(fact);
  await page.getByRole("button", { name: "관찰 기록 저장" }).click();
  await expect(page.getByText("관찰 기록을 저장했어요.")).toBeVisible();

  // 사이드바가 **기록**과 **문서**로 갈리면서 「아이들 전부 보기」는 메뉴에서 빠졌다.
  // 관찰 기록 화면 안의 길로 들어가고, 그 아래 화면이므로 메뉴는 관찰 기록이 켜진 채다.
  const menu = page.getByRole("complementary", { name: "주 메뉴" });
  const recordsMenu = menu.getByRole("link", { name: "관찰 기록", exact: true });
  await recordsMenu.click();
  await expect(page).toHaveURL(/\/records$/);
  await page.getByRole("link", { name: "아이들 전부 보기", exact: true }).click();
  await expect(page).toHaveURL(/\/records\/children$/);
  await expect(recordsMenu).toHaveAttribute("aria-current", "page");
  await expect(page.getByRole("button", { name: `${child} · 1건` })).toBeVisible();
  await expect(page.getByText("관찰 기록 1건")).toBeVisible();
});
