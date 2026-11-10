import { expect, test, type Page } from "@playwright/test";
import { completeOnboarding } from "./onboarding";

/**
 * 상단바 알림함 — 두 계정이 같은 원에서 열람 요청을 주고받는다.
 *
 * 받은 쪽(A)은 **문서 보관함에 있는 채로** 종을 누른다. 주소의 쿼리만 바뀌는 이동은 Next 가 화면을
 * 다시 그리지 않아서, 주소만 바뀌고 받은 요청 칸이 안 열리는 회귀를 여기서 잡는다(location.assign 길).
 * 보낸 쪽(B)은 홈에서 종을 누른다(router.push 길).
 *
 * 같은 원으로 묶으려면 정부 목록에서 고른 원이어야 한다(ADR-068) — 직접 적은 원에는 들어갈 수 없다.
 * 다른 spec 은 목록을 쓰지 않으므로 이 원은 이 spec 만 쓴다. 다시 돌리면 원이 남아 있어 반 이름에
 * 실행마다 다른 꼬리를 붙이고, 반은 이름이 아니라 「내 반」(OWNER)으로 찾는다.
 *
 * MSW 를 끈 실제 스택(Postgres · FastAPI · Next)에서 돈다. ADR-028.
 */
const DAYCARE = "강원특별자치도청어린이집";

/** 콘솔 오류 · 페이지 오류 · /api 400 이상 응답을 모은다. 두 계정 화면에 같이 건다. */
async function watch(page: Page) {
  const evidence = { requests: [] as string[], errors: [] as string[] };
  // 구글 폰트는 기능과 무관하다. 망이 막힌 환경에서 콘솔 오류로 흔들리지 않게 빈 응답으로 끝낸다.
  await page.route(/fonts\.(googleapis|gstatic)\.com/, (route) =>
    route.fulfill({ status: 200, contentType: "text/css", body: "" }),
  );
  page.on("response", (response) => {
    if (!new URL(response.url()).pathname.startsWith("/api/")) return;
    evidence.requests.push(`${response.request().method()} ${response.status()} ${response.url()}`);
    if (response.status() >= 400)
      evidence.errors.push(`HTTP ${response.status()} ${response.url()}`);
  });
  page.on("pageerror", (error) => evidence.errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") evidence.errors.push(message.text());
  });
  page.on("requestfailed", (request) => {
    if (request.failure()?.errorText !== "net::ERR_ABORTED")
      evidence.errors.push(`${request.url()} ${request.failure()?.errorText}`);
  });
  return evidence;
}

async function api(page: Page, path: string, method = "GET") {
  const token = await page.evaluate(() => sessionStorage.getItem("saessak.authToken"));
  const response = await page.request.fetch(path, {
    method,
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(response.ok(), `${method} ${path}: ${await response.text()}`).toBeTruthy();
  return response.json();
}

/** 가입 → 목록에서 고른 원으로 온보딩. 끝나면 홈(`/`)이다. */
async function enter(page: Page, teacher: string, className: string) {
  const email = `e2e-notify-${Date.now()}-${Math.random().toString(36).slice(2, 7)}@example.com`;
  const password = "e2e-password-1234";
  await page.goto("/signup");
  await page.getByLabel("선생님 이름").fill(teacher);
  await page.getByLabel("이메일").fill(email);
  await page.locator("#auth-password").fill(password);
  await page.getByLabel("비밀번호 확인").fill(password);
  await page.getByRole("button", { name: "회원가입", exact: true }).click();
  await expect(page.getByRole("heading", { name: "가입을 완료했어요" })).toBeVisible();
  await page.getByRole("link", { name: "메인화면으로 가기", exact: true }).click();
  await expect(page).toHaveURL(/\/$/);
  await page.goto("/onboarding");
  await completeOnboarding(page, {
    center: DAYCARE,
    daycare: DAYCARE,
    director: "가상원장",
    className,
    teacher,
  });
}

const bell = (page: Page, unread: number) =>
  page.getByRole("button", { name: `알림 ${unread}건 안 읽음`, exact: true });

/**
 * 서버에 남은 알림 — [종류, 읽었나]. 「안 읽은 것 없음」은 종으로 보지 않는다 — 목록을 받기 전에도
 * 종이 같은 이름이라, 읽음이 저장되지 않았어도 통과한다.
 */
async function inbox(page: Page) {
  const { items } = await api(page, "/api/me/notifications");
  return items.map((i: { kind: string; read_at: string | null }) => [i.kind, i.read_at !== null]);
}

test("열람 요청은 주인 종에, 승인은 요청자 종에 뜨고 누르면 그 칸이 열린다", async ({
  page,
  browser,
  baseURL,
}) => {
  // 계정 둘의 가입 · 온보딩이 있어 기본 90초를 넘길 수 있다.
  test.slow();
  const tag = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 5)}`;
  const ownerClass = `해님${tag}반`;
  const requesterClass = `달님${tag}반`;

  // A — 반 주인
  const ownerLog = await watch(page);
  await enter(page, "주인교사", ownerClass);
  const me = await api(page, "/api/auth/me");
  const classes = await api(page, `/api/centers/${me.center_id}/classes`);
  const owned = classes.items.find(
    (c: { name: string; my_access: string }) => c.name === ownerClass && c.my_access === "OWNER",
  );
  expect(owned, JSON.stringify(classes.items)).toBeTruthy();
  const ownerClassId = owned.id as number;

  // B — 같은 원에 들어와 자기 반을 만들고 A 반을 청한다. 요청 화면은 이 spec 의 주제가 아니라 API 로.
  const context = await browser.newContext({
    baseURL,
    locale: "ko-KR",
    timezoneId: "Asia/Seoul",
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 1,
  });
  try {
    const other = await context.newPage();
    const requesterLog = await watch(other);
    await enter(other, "요청교사", requesterClass);
    const sameCenter = await api(other, "/api/auth/me");
    expect(sameCenter.center_id).toBe(me.center_id);
    await api(other, `/api/classes/${ownerClassId}/access-requests`, "POST");

    // A 는 보관함에 있는 채로 종을 누른다. 폴링이 없어 들어온 뒤에 받은 것을 본다.
    await page.goto("/documents");
    await expect(page.getByRole("complementary", { name: "반 선택" })).toBeVisible();
    await bell(page, 1).click();
    const ownerPanel = page.getByRole("region", { name: "알림 목록" });
    await expect(ownerPanel).toBeVisible();
    await ownerPanel.getByText(`요청교사 선생님이 ${ownerClass} 열람을 요청했어요`).click();
    await expect(page).toHaveURL(/\/documents\?foreign=received$/);
    // 주소만 바뀌고 화면이 그대로면 여기서 걸린다.
    const received = page.getByRole("region", { name: "받은 열람 요청" });
    const row = received.getByRole("listitem").filter({ hasText: "요청교사 선생님" });
    await expect(row).toContainText(ownerClass);
    // 누른 알림은 읽음으로 보낸 뒤 옮겼다.
    expect(await inbox(page)).toEqual([["ACCESS_REQUESTED", true]]);
    await row.getByRole("button", { name: "승인", exact: true }).click();
    await expect(row.getByRole("button", { name: "승인 취소", exact: true })).toBeVisible();
    // 승인은 서로다(ADR-068) — 거울로 열린 B 반 쪽 줄은 A 에게 알림을 만들지 않는다.
    expect(await inbox(page)).toEqual([["ACCESS_REQUESTED", true]]);

    // B 는 홈에서 종을 누른다.
    await other.goto("/");
    await bell(other, 1).click();
    const requesterPanel = other.getByRole("region", { name: "알림 목록" });
    await expect(requesterPanel).toBeVisible();
    await requesterPanel.getByText(`${ownerClass} 열람 요청이 승인됐어요`).click();
    await expect(other).toHaveURL(new RegExp(`/documents\\?foreign=${ownerClassId}$`));
    await expect(other.getByRole("region", { name: `${ownerClass} 문서` })).toContainText(
      "승인받았어요 · 서로 함께 봐요",
    );
    expect(await inbox(other)).toEqual([["ACCESS_APPROVED", true]]);

    expect(ownerLog.errors, ownerLog.requests.join("\n")).toEqual([]);
    expect(requesterLog.errors, requesterLog.requests.join("\n")).toEqual([]);
  } finally {
    await context.close();
  }
});
