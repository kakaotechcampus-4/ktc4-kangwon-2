import { expect, test, type Page } from "@playwright/test";

/**
 * 홈 빠른 관찰 기록 — 저장한 것이 **그 자리에 보이는가** (독립 감사 P0 회귀).
 *
 * 예전에는 POST 가 201 인데 홈이 0건으로 보였다. 홈이 반을 짚지 않고 조회해서,
 * 주 반을 고른 적 없는 한 반짜리 계정이 빈 목록을 받았기 때문이다.
 * 201 만 보고 통과시키면 이 회귀를 다시 놓친다 — **화면의 건수와 목록까지** 본다.
 *
 * MSW 를 끈 실제 스택(Postgres · FastAPI · Next)에서 돈다. ADR-028.
 * 아동 이름은 가명이다(CLAUDE.md 개인정보). 이메일은 실행마다 새로 만든다.
 */
const diagnostics = new WeakMap<Page, { requests: string[]; errors: string[] }>();
test.beforeEach(async ({ page }) => {
  const evidence = { requests: [] as string[], errors: [] as string[] };
  // 구글 폰트는 화면 기능과 무관하다. 망이 막힌 환경에서 콘솔 오류로 검증이 흔들리지 않게
  // 여기서 빈 응답으로 끝낸다 — 서버·API 응답은 가로채지 않는다.
  await page.route(/fonts\.(googleapis|gstatic)\.com/, (route) =>
    route.fulfill({ status: 200, contentType: "text/css", body: "" }),
  );
  diagnostics.set(page, evidence);
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
});
test.afterEach(async ({ page }, info) => {
  const evidence = diagnostics.get(page)!;
  await info.attach("home-network-console", {
    body: JSON.stringify(evidence, null, 2),
    contentType: "application/json",
  });
  expect(evidence.errors).toEqual([]);
  const reads = evidence.requests.filter(
    (line) => line.startsWith("GET 200 ") && line.includes("/api/observations"),
  );
  expect(
    reads.every((line) => new URL(line.slice("GET 200 ".length)).searchParams.has("class_id")),
  ).toBe(true);
});

async function api(page: Page, path: string, method = "GET", data?: unknown) {
  const token = await page.evaluate(() => sessionStorage.getItem("saessak.authToken"));
  const response = await page.request.fetch(path, {
    method,
    data,
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(response.ok(), await response.text()).toBeTruthy();
  return response.json();
}

async function enterHome(page: Page) {
  const email = `e2e-home-${Date.now()}-${Math.random().toString(36).slice(2, 7)}@example.com`;
  const password = "e2e-password-1234";
  const child = "가나다";

  await page.goto("/signup");
  await page.getByLabel("선생님 이름").fill("테스트교사");
  await page.getByLabel("이메일").fill(email);
  await page.locator("#auth-password").fill(password);
  await page.getByLabel("비밀번호 확인").fill(password);
  await page.getByRole("button", { name: "회원가입" }).click();

  // 반 하나짜리 온보딩 — 주 반을 따로 고르는 단계가 없는 경로다.
  await expect(page).toHaveURL(/\/onboarding\/center$/);
  await page.getByLabel("원명").fill("테스트어린이집");
  await page.getByLabel("원장 이름").fill("테스트원장");
  await page.getByLabel("시·도").selectOption("강원특별자치도");
  await page.getByLabel("시·군·구").selectOption("춘천시");
  await page.getByRole("button", { name: "다음" }).click();

  await expect(page).toHaveURL(/\/onboarding\/classes$/);
  await page.getByLabel("반 이름").fill("햇살반");
  await page.getByLabel("만 4세").check();
  await page.getByLabel("담임 이름").fill("테스트교사");
  await page.getByLabel("이 반 모든 아동의 법정대리인 동의를 받았습니다.").check();
  await page.getByRole("button", { name: "다음" }).click();

  await expect(page).toHaveURL(/\/onboarding\/children$/);
  await page.getByLabel("아동 추가").fill(child);
  await page.getByRole("button", { name: "+ 추가" }).click();
  await page.getByRole("button", { name: "설정 완료" }).click();
  await expect(page).not.toHaveURL(/\/onboarding/);
  await expect(page.getByRole("heading", { name: "우리 반", exact: true, level: 1 })).toBeVisible();
  const me = await api(page, "/api/auth/me");
  const classes = await api(page, `/api/centers/${me.center_id}/classes`);
  const klass = classes.items.find((row: { name: string }) => row.name === "햇살반");
  expect(
    await page.evaluate(async () => (await navigator.serviceWorker.getRegistrations()).length),
  ).toBe(0);
  return { centerId: me.center_id as number, classId: klass.id as number };
}

async function saveHome(page: Page, fact: string, expectedClassId: number) {
  await page.getByLabel("빠른 기록 내용").fill(fact);
  await page.getByRole("button", { name: "기록 남기기", exact: true }).click();
  return confirmHome(page, expectedClassId);
}
/** 「이렇게 남길까요?」의 아이 칸에서 첫 아이를 고른다. 비워 둔 채로는 저장이 막힌다. */
async function pickChild(page: Page) {
  const picker = page.getByRole("combobox", { name: "아이", exact: true });
  // `option[value!='']` 은 CSS 가 아니다 — 셀렉터 자체가 SyntaxError 로 터진다.
  const first = await picker.locator("option:not([value=''])").first().getAttribute("value");
  await picker.selectOption(first!);
}

async function confirmHome(page: Page, expectedClassId: number) {
  const posted = page.waitForResponse(
    (r) => r.url().endsWith("/api/observations") && r.request().method() === "POST",
  );
  // 아이 칸은 비어 있는 채로 열린다 — 고르기 전에는 「이대로 남기기」가 눌리지 않는다.
  await pickChild(page);
  await page.getByRole("button", { name: "이대로 남기기", exact: true }).click();
  const response = await posted;
  expect(response.status()).toBe(201);
  expect(response.request().postDataJSON().class_id).toBe(expectedClassId);
  return response.json();
}

test("K 한 반 계정: 홈에서 저장한 관찰이 홈에 그대로 보인다", async ({ page }, info) => {
  const { classId } = await enterHome(page);
  const fact = "블록 세 개를 쌓은 뒤 더 높이 만들래라고 말했다.";

  // 홈에서 한 줄 남긴다.
  await expect(page.getByText("오늘 기록 0건")).toBeVisible();
  const saved = await saveHome(page, fact, classId);

  // ★ 여기가 회귀 지점이다. 201 이 아니라 **화면**을 본다.
  await expect(page.getByText("오늘 기록 1건")).toBeVisible({ timeout: 5000 });
  await expect(page.getByText(fact, { exact: true }).first()).toBeVisible();

  // 새로고침해도 남아 있다 — 저장은 됐는데 화면만 비는 상태가 아니다.
  await page.reload();
  await expect(page.getByText("오늘 기록 1건")).toBeVisible({ timeout: 5000 });
  await expect(page.getByText(fact, { exact: true }).first()).toBeVisible();
  await expect(page.getByLabel("현재 반", { exact: true })).toContainText("햇살반");
  await info.attach("K-saved-record", {
    body: JSON.stringify(saved),
    contentType: "application/json",
  });
  await page.screenshot({ path: info.outputPath("K-home-record.png"), fullPage: true });
});

test("L 두 반: 상단·저장·조회·일과 링크·뒤로가기와 지연 연결이 같은 반을 유지한다", async ({
  page,
}, info) => {
  const { centerId, classId } = await enterHome(page);
  const factA = "햇살반에서 블록 길을 만들었다.";
  const factB = "달님반에서 공을 친구에게 굴렸다.";
  await saveHome(page, factA, classId);
  await expect(page.getByText("오늘 기록 1건")).toBeVisible();
  const other = await api(page, `/api/centers/${centerId}/classes`, "POST", {
    name: "달님반",
    teacher_name: "다른교사",
    age_min: 4,
    age_max: 4,
    consent_confirmed: true,
  });
  await api(page, `/api/classes/${other.id}/children`, "POST", { name: "나다라" });

  // 실제 아동 연결 요청만 늦춘다. 응답은 FastAPI의 원본 그대로 이어 보낸다.
  let release!: () => void;
  let arrived!: () => void;
  const blocked = new Promise<void>((resolve) => {
    release = resolve;
  });
  const hit = new Promise<void>((resolve) => {
    arrived = resolve;
  });
  const childrenUrl = `**/api/classes/${other.id}/children`;
  await page.route(childrenUrl, async (route) => {
    arrived();
    await blocked;
    await route.continue();
  });
  await page.reload();
  await hit;
  await expect(page.getByLabel("현재 반", { exact: true })).toContainText("햇살반");
  await expect(page.getByText(factA, { exact: true }).first()).toBeVisible();
  release();
  await page.getByLabel("빠른 기록 내용").fill(factB);
  await page.getByRole("button", { name: "기록 남기기", exact: true }).click();
  const select = page.getByRole("combobox", { name: "반", exact: true });
  await select.selectOption({ label: "달님반" });
  await page.unroute(childrenUrl);
  await expect(page.getByLabel("현재 반", { exact: true })).toContainText("달님반");
  await expect(page.getByLabel("상단 현재 반", { exact: true })).toHaveText("달님반");
  await expect(page.getByText(factA, { exact: true })).toHaveCount(0);
  await expect(page.getByText("오늘 기록 0건")).toBeVisible();
  const made = await confirmHome(page, other.id);
  await expect(page.getByText("오늘 기록 1건")).toBeVisible();
  await expect(page.getByText(factB, { exact: true }).first()).toBeVisible();
  const date = made.date as string;
  const routine = page.getByRole("link", { name: "오늘 일과 적기", exact: true });
  await expect(routine).toHaveAttribute("href", `/routines?date=${date}&class_id=${other.id}`);
  await routine.click();
  await expect(page).toHaveURL(`/routines?date=${date}&class_id=${other.id}`);
  await expect(page.getByRole("combobox", { name: "반", exact: true })).toHaveValue(
    String(other.id),
  );
  await expect(page.getByLabel("날짜", { exact: true })).toHaveValue(date);
  await page.goBack();
  await expect(page).toHaveURL(`/?class_id=${other.id}`);
  await expect(page.getByLabel("현재 반", { exact: true })).toContainText("달님반");
  await expect(page.getByLabel("상단 현재 반", { exact: true })).toHaveText("달님반");
  await expect(page.getByText("오늘 기록 1건")).toBeVisible();
  await expect(page.getByText(factB, { exact: true }).first()).toBeVisible();
  await expect(page.getByText(factA, { exact: true })).toHaveCount(0);
  await page.reload();
  await expect(page.getByLabel("현재 반", { exact: true })).toContainText("달님반");
  await expect(page.getByText("오늘 기록 1건")).toBeVisible();
  await expect(page.getByRole("link", { name: "오늘 일과 적기", exact: true })).toHaveAttribute(
    "href",
    `/routines?date=${date}&class_id=${other.id}`,
  );
  // A 저장을 기다리는 사이 B로 이동해도 늦은 완료가 B의 목록을 비우지 않는다.
  await page.getByLabel("빠른 기록 내용").fill("햇살반의 늦게 저장된 추가 사실");
  await page.getByRole("button", { name: "기록 남기기", exact: true }).click();
  await page.getByRole("combobox", { name: "반", exact: true }).selectOption({ label: "햇살반" });
  let finishSave!: () => void;
  let savingStarted!: () => void;
  const holdSave = new Promise<void>((resolve) => {
    finishSave = resolve;
  });
  const saveStarted = new Promise<void>((resolve) => {
    savingStarted = resolve;
  });
  await page.route("**/api/observations", async (route) => {
    if (route.request().method() === "POST") {
      savingStarted();
      await holdSave;
    }
    await route.continue();
  });
  const latePost = page.waitForResponse(
    (r) => r.url().endsWith("/api/observations") && r.request().method() === "POST",
  );
  await pickChild(page);
  await page.getByRole("button", { name: "이대로 남기기", exact: true }).click();
  await saveStarted;
  await page.getByRole("combobox", { name: "반", exact: true }).selectOption({ label: "달님반" });
  await expect(page.getByText(factB, { exact: true }).first()).toBeVisible();
  const refreshedB = page.waitForResponse((r) => {
    const url = new URL(r.url());
    return (
      r.request().method() === "GET" &&
      url.pathname === "/api/observations" &&
      url.searchParams.get("class_id") === String(other.id)
    );
  });
  finishSave();
  const completed = await latePost;
  expect(completed.status()).toBe(201);
  expect(completed.request().postDataJSON().class_id).toBe(classId);
  await refreshedB;
  await page.unroute("**/api/observations");
  await expect(page.getByLabel("현재 반", { exact: true })).toContainText("달님반");
  await expect(page.getByLabel("상단 현재 반", { exact: true })).toHaveText("달님반");
  await expect(page.getByText("오늘 기록 1건")).toBeVisible();
  await expect(page.getByText(factB, { exact: true }).first()).toBeVisible();
  await expect(page.getByText("햇살반의 늦게 저장된 추가 사실", { exact: true })).toHaveCount(0);
  await page.screenshot({ path: info.outputPath("L-home-class-B.png"), fullPage: true });
  await info.attach("L-class-scope", {
    body: JSON.stringify({
      classA: classId,
      classB: other.id,
      date,
      delayedRealResponse: true,
      backRestoredB: true,
      lateSaveKeptB: true,
    }),
    contentType: "application/json",
  });
  await page.goto(`/records/routines?date=${date}&class_id=${other.id}`);
  await expect(page).toHaveURL(`/routines?date=${date}&class_id=${other.id}`);
  await expect(page.getByRole("combobox", { name: "반", exact: true })).toHaveValue(
    String(other.id),
  );
});
