import { expect, test, type Locator, type Page, type TestInfo } from "@playwright/test";
import { completeOnboarding } from "./onboarding";
import { verifyHwpx } from "./hwpx";
import { execFileSync } from "node:child_process";

/** TASK 2: 실제 Next → FastAPI → PostgreSQL. 응답을 fulfill하거나 MSW로 대체하지 않는다. */
type Routine = {
  id: number;
  name: string;
  start: string;
  end: string;
  execution: string;
  position: number;
};
type Evidence = {
  network: { method: string; url: string; status: number }[];
  errors: string[];
  notes: unknown[];
};
const diagnostics = new WeakMap<Page, Evidence>();
const rows = (page: Page) => page.locator('[aria-label="일과 목록"] article');
const token = (page: Page) => page.evaluate(() => sessionStorage.getItem("saessak.authToken"));

/**
 * 시간은 「오전 09:20 ~ 10:40」 한 칸이고, 시작 · 종료 칸은 시계판과 함께 접혀 있다.
 * 열고 고친 뒤 다시 닫는다 — 열어 둔 채로 두면 아래 줄을 덮는다.
 */
async function withClock<T>(row: Locator, run: () => Promise<T>) {
  await row.getByRole("button", { name: /시계로 시간 고르기/ }).click();
  const out = await run();
  await row.getByRole("button", { name: "닫기", exact: true }).click();
  return out;
}

const pickTime = (row: Locator, label: string, value: string) =>
  withClock(row, () => row.getByLabel(`${label} 시간`, { exact: true }).fill(value));

const expectTime = (row: Locator, label: string, value: string) =>
  withClock(row, () => expect(row.getByLabel(`${label} 시간`, { exact: true })).toHaveValue(value));

/** 「계획한 것」은 접혀 있다. 적으려면 먼저 편다. */
async function fillPlan(row: Locator, value: string) {
  const fold = row.locator("details");
  if (!(await fold.evaluate((el) => (el as HTMLDetailsElement).open)))
    await fold.locator("summary").click();
  await row.getByLabel("계획한 것").fill(value);
}

/** 깔아 두는 기본 하루 — 국가 공식 양식의 유아 10행형 (RoutinesPage DEFAULT_ROUTINES). */
const PRESET_ROWS = 10;

async function api(page: Page, path: string, method = "GET", data?: unknown) {
  const response = await page.request.fetch(path, {
    method,
    data,
    headers: { Authorization: `Bearer ${await token(page)}` },
  });
  expect(
    response.ok(),
    `${method} ${path}: ${response.status()} ${await response.text()}`,
  ).toBeTruthy();
  return response.status() === 204 ? undefined : response.json();
}

async function enterHome(page: Page) {
  const email = `task2-${Date.now()}-${Math.random().toString(36).slice(2, 7)}@example.com`;
  await page.goto("/signup");
  await page.getByLabel("선생님 이름").fill("일과테스트교사");
  await page.getByLabel("이메일").fill(email);
  await page.locator("#auth-password").fill("task2-password-1234");
  await page.getByLabel("비밀번호 확인").fill("task2-password-1234");
  await page.getByRole("button", { name: "회원가입", exact: true }).click();
  await expect(page.getByRole("heading", { name: "가입을 완료했어요" })).toBeVisible();
  await expect(page).toHaveURL(/\/signup$/);
  await page.getByRole("link", { name: "메인화면으로 가기", exact: true }).click();
  await expect(page).toHaveURL(/\/$/);
  await page.goto("/onboarding");
  await completeOnboarding(page, {
    center: "일과테스트어린이집",
    director: "테스트원장",
    teacher: "테스트교사",
    children: ["가나다"],
  });
  await expect(page.getByRole("link", { name: "일과 작성하기" })).toBeVisible();
  const me = await api(page, "/api/auth/me");
  const classes = await api(page, `/api/centers/${me.center_id}/classes`);
  const klass = classes.items.find((item: { name: string }) => item.name === "햇살반");
  const children = await api(page, `/api/classes/${klass.id}/children`);
  expect(
    await page.evaluate(async () => (await navigator.serviceWorker.getRegistrations()).length),
  ).toBe(0);
  return {
    classId: klass.id as number,
    centerId: me.center_id as number,
    childId: children.items[0].id as number,
  };
}

async function dayRows(page: Page, classId: number, date: string): Promise<Routine[]> {
  return (await api(page, `/api/routines?class_id=${classId}&from=${date}&to=${date}`)).items;
}

async function saved(page: Page, exact = true) {
  await page.getByRole("button", { name: "저장", exact: true }).click();
  await expect(page.getByText(exact ? "저장했어요." : /저장했어요\./, { exact })).toBeVisible();
}

/**
 * 반을 바꾼다. 고르개는 사이드바 하나뿐이고, 고르면 주소에서 옛 반을 떼고 다시 연다.
 * 반이 둘 이상일 때만 나타나므로, 새로 만든 반이 목록에 붙기를 먼저 기다린다.
 */
async function switchClass(page: Page, label: string) {
  const picker = page.getByRole("combobox", { name: "반 바꾸기", exact: true });
  // 보기 글자는 「햇살반 · 만 4세」라 이름만으로는 안 맞는다. 값으로 고른다.
  const option = picker.locator("option", { hasText: label });
  await expect(option).toHaveCount(1);
  await picker.selectOption((await option.getAttribute("value"))!);
  await expect(page.getByLabel("상단 현재 반", { exact: true })).toHaveText(label);
}

async function expectNames(page: Page, expected: string[]) {
  await expect
    .poll(() =>
      rows(page)
        .getByLabel("일과 이름")
        .evaluateAll((nodes) => nodes.map((node) => (node as HTMLInputElement).value)),
    )
    .toEqual(expected);
}

function note(page: Page, scenario: string, details: unknown) {
  diagnostics.get(page)!.notes.push({ scenario, url: page.url(), details });
}

function dbDocument(id: number) {
  if (!process.env.E2E_DATABASE_URL)
    throw new Error("실제 DB 검증을 위해 E2E_DATABASE_URL이 필요합니다.");
  const script =
    "import os,sys,json,psycopg; c=psycopg.connect(os.environ['E2E_DATABASE_URL']); " +
    "r=c.execute('SELECT id,status,stale FROM documents WHERE id=%s',(int(sys.argv[1]),)).fetchone(); " +
    "print(json.dumps(dict(zip(['id','status','stale'],r))))";
  return JSON.parse(
    execFileSync(process.env.E2E_PYTHON ?? "python", ["-c", script, String(id)], {
      encoding: "utf8",
    }),
  );
}

test.beforeEach(async ({ page }) => {
  const state: Evidence = { network: [], errors: [], notes: [] };
  // 구글 폰트는 화면 기능과 무관하다. 망이 막힌 환경에서 콘솔 오류로 검증이 흔들리지 않게
  // 여기서 빈 응답으로 끝낸다 — 서버·API 응답은 가로채지 않는다.
  await page.route(/fonts\.(googleapis|gstatic)\.com/, (route) =>
    route.fulfill({ status: 200, contentType: "text/css", body: "" }),
  );
  diagnostics.set(page, state);
  page.on("response", (r) => {
    const url = new URL(r.url());
    if (url.pathname.startsWith("/api/"))
      state.network.push({
        method: r.request().method(),
        url: url.pathname + url.search,
        status: r.status(),
      });
  });
  page.on("pageerror", (error) => state.errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") state.errors.push(message.text());
  });
  page.on("requestfailed", (request) => {
    if (request.failure()?.errorText !== "net::ERR_ABORTED")
      state.errors.push(`${request.method()} ${request.url()} ${request.failure()?.errorText}`);
  });
});

test.afterEach(async ({ page }, info: TestInfo) => {
  const state = diagnostics.get(page)!;
  await info.attach("network-console-evidence", {
    body: JSON.stringify(state, null, 2),
    contentType: "application/json",
  });
  const intentional401 = info.title.includes("D E F");
  // 거절을 확인하는 시나리오는 스스로 적어 둔다 — 그 4xx 는 증거이지 사고가 아니다.
  const expected = info.annotations
    .filter((a) => a.type === "expected-4xx" || a.type === "expected-http-error")
    .map((a) => a.description ?? "");
  expect(
    state.network.filter(
      (r) =>
        r.status >= 400 &&
        !(intentional401 && r.status === 401 && r.url.startsWith("/api/routines")) &&
        !expected.some((path) => r.url === path),
    ),
  ).toEqual([]);
  const expectedConsole = info.annotations
    .filter((a) => a.type === "expected-console-error")
    .map((a) => a.description);
  expect(
    state.errors.filter(
      (error) => !(intentional401 && /401/.test(error)) && !expectedConsole.includes(error),
    ),
  ).toEqual([]);
});

test("A B C G H J — 홈 진입, 7줄·드래그 저장, S-J2 생성·확정, 정확한 재검토 건수", async ({
  page,
}, info) => {
  const { classId } = await enterHome(page);
  await test.step("A: 홈의 오늘 일과 버튼을 실제 클릭하고 로딩·빈 5줄 확인", async () => {
    let release!: () => void;
    const paused = new Promise<void>((resolve) => {
      release = resolve;
    });
    await page.route("**/api/routines?**", async (route) => {
      await paused;
      await route.continue();
    });
    await page.getByRole("link", { name: "일과 작성하기" }).click();
    await expect(page).toHaveURL(/\/routines\?date=.*class_id=/);
    await expect(page.getByText("이 날짜의 일과를 불러오는 중이에요…")).toBeVisible();
    release();
    await expect(rows(page)).toHaveCount(PRESET_ROWS);
    await page.unroute("**/api/routines?**");
    note(page, "A", { presetRows: PRESET_ROWS, classId });
  });
  const date = await page.getByLabel("날짜", { exact: true }).inputValue();
  await test.step("B: 깔아 둔 하루 중 7줄을 고쳐 저장하고 새로고침 후 내용과 시간 확인", async () => {
    // 손대지 않은 세 줄은 저장되지 않는다 — 깔아 둔 하루를 서버에 쌓지 않는다.
    for (let i = 0; i < 7; i++) {
      const row = rows(page).nth(i);
      await row.getByLabel("일과 이름").fill(`일과${i + 1}`);
      await pickTime(row, "시작", `${String(8 + i).padStart(2, "0")}:00`);
      await pickTime(row, "종료", `${String(9 + i).padStart(2, "0")}:00`);
      await fillPlan(row, "놀이 자료를 준비한다.");
      if (i < 6) await row.getByLabel("실제로 한 것").fill("블록을 쌓고 길을 만들었다.");
    }
    await saved(page);
    await page.reload();
    await expect(rows(page)).toHaveCount(7);
    for (let i = 0; i < 7; i++) {
      await expect(rows(page).nth(i).getByLabel("일과 이름")).toHaveValue(`일과${i + 1}`);
      await expectTime(rows(page).nth(i), "시작", `${String(8 + i).padStart(2, "0")}:00`);
      await expectTime(rows(page).nth(i), "종료", `${String(9 + i).padStart(2, "0")}:00`);
      await expect(rows(page).nth(i).getByLabel("계획한 것")).toHaveValue("놀이 자료를 준비한다.");
      await expect(rows(page).nth(i).getByLabel("실제로 한 것")).toHaveValue(
        i < 6 ? "블록을 쌓고 길을 만들었다." : "",
      );
    }
    note(page, "B", await dayRows(page, classId, date));
  });
  await test.step("C: 저장한 순서가 다시 읽어도 그대로다", async () => {
    // 끌어서 옮기기와 「시간순 정렬」은 없앴다. 순서는 적은 차례 그대로 남는다.
    const expected = ["일과1", "일과2", "일과3", "일과4", "일과5", "일과6", "일과7"];
    await page.reload();
    await expectNames(page, expected);
    expect((await dayRows(page, classId, date)).map((r) => r.name)).toEqual(expected);
    note(page, "C", expected);
  });
  let documentId: number;
  await test.step("G: 저장 전 입력을 먼저 저장하고, 실제로 한 것이 있는 일과로 이 화면에서 초안 생성", async () => {
    await rows(page).nth(0).getByLabel("일과 이름").fill("수정한 일과1");
    const response = page.waitForResponse(
      (r) => r.url().endsWith("/api/documents") && r.request().method() === "POST",
    );
    // 일지는 보관함으로 가지 않고 이 화면에서 만든다 — 고르는 단계 없이, 실제로 한 것을
    // 적은 줄 전부를 화면 순서(시간순) 그대로 근거로 삼는다.
    await page.getByRole("button", { name: "오늘 일지 만들기 →", exact: true }).click();
    const generated = await response;
    expect(generated.status()).toBe(201);
    await expect(page).toHaveURL(`/routines?date=${date}&class_id=${classId}`);
    const sourceRows = await dayRows(page, classId, date);
    expect(sourceRows[0].name).toBe("수정한 일과1");
    const expectedIds = sourceRows.filter((r) => r.execution).map((r) => r.id);
    expect(generated.request().postDataJSON().source_ids).toEqual(expectedIds);
    const doc = await generated.json();
    documentId = doc.id;
    expect(doc.sources.map((source: { id: number }) => source.id)).toEqual(expectedIds);
    await expect(page.getByRole("region", { name: /보육일지$/ })).toBeVisible();
    await expect(
      page.getByRole("heading", { name: doc.title, exact: true, level: 2 }),
    ).toBeVisible();
    note(page, "G", { documentId, selectedIds: doc.sources.map((s: { id: number }) => s.id) });
  });
  await test.step("H: 브라우저에서 문서를 확정하고 두 근거 수정은 1건으로 집계", async () => {
    await page.getByRole("button", { name: /기본 항목 검사|AI 검증하기/ }).click();
    await expect(page.getByRole("checkbox", { name: /원본 기록과 사실이 일치하고/ })).toHaveCount(
      1,
    );
    await page.getByRole("button", { name: "검사 결과 접기", exact: true }).click();
    await expect(page.getByText(/기본 항목은 통과했어요/)).toHaveCount(0);
    await page.getByRole("button", { name: /기본 항목 검사|AI 검증하기/ }).click();
    await expect(page.getByText(/기본 항목은 통과했어요/)).toBeVisible();
    await page.getByRole("checkbox", { name: /원본 기록과 사실이 일치하고/ }).check();
    await page.getByRole("button", { name: "검토 완료 · 문서 확정", exact: true }).click();
    await expect(page.getByRole("button", { name: "확정 취소", exact: true })).toBeVisible();
    expect(dbDocument(documentId!)).toEqual({ id: documentId!, status: "CONFIRMED", stale: false });
    await page.getByRole("link", { name: "홈", exact: true }).click();
    // 이미 적힌 일과가 있으면 홈의 일과 줄 자체가 고치러 가는 길이다.
    // 줄 이름은 「09:00 일과 — …」 처럼 시각이 앞에 온다.
    await page.getByRole("link", { name: /일과 —/ }).click();
    await expect(rows(page)).toHaveCount(7);
    await rows(page).nth(0).getByLabel("실제로 한 것").fill("블록 길을 더 길게 이어 붙였다.");
    await rows(page).nth(2).getByLabel("실제로 한 것").fill("길 위에 자동차를 올려 굴렸다.");
    await saved(page, false);
    await expect(
      page.getByText(/이 일과를 쓴 보육일지 1건이 다시 검토 대상이 되었어요/),
    ).toBeVisible();
    const db = dbDocument(documentId!);
    expect(db.stale).toBe(true);
    note(page, "H", db);
    await fillPlan(rows(page).nth(0), "계획만 고친다.");
    await saved(page);
    await expect(page.getByText(/다시 검토 대상이 되었어요|이미 재검토 대상인/)).toHaveCount(0);
    await page.screenshot({ path: info.outputPath("A-G-H-routines.png"), fullPage: true });
  });
});

test("S-J2 빈 상태 — 실제로 한 것이 없는 저장 줄에서 입력 링크로 돌아간다", async ({ page }) => {
  const { classId } = await enterHome(page);
  await page.getByRole("link", { name: "일과 작성하기" }).click();
  await expect(rows(page)).toHaveCount(PRESET_ROWS);
  const date = await page.getByLabel("날짜", { exact: true }).inputValue();
  await rows(page).nth(0).getByLabel("일과 이름").fill("시간과 이름만 있는 일과");
  await saved(page);
  await expect(
    page.getByRole("button", { name: "오늘 일지 만들기 →", exact: true }),
  ).toBeDisabled();
  await page.getByRole("link", { name: "문서 보관함", exact: true }).click();
  // 보관함 상단의 생성 단추는 없앴다. 생성 화면은 기존 딥링크(S-J1 → S-J2)로 들어간다.
  await page.goto(`/documents?kind=dailyLog&class_id=${classId}&date=${date}`);
  await page.getByRole("combobox", { name: "문서 종류" }).selectOption("dailyLog");
  await page.getByRole("combobox", { name: "담당 반" }).selectOption({ label: "햇살반" });
  await expect(page.getByRole("heading", { name: "선택할 수 있는 일과가 없어요" })).toBeVisible();
  await expect(page.getByText("일과 1줄이 있지만 실제로 한 것이 모두 비어 있어요.")).toBeVisible();
  const write = page.getByRole("link", { name: "일과 기록 입력 →", exact: true });
  await expect(write).toHaveAttribute("href", `/routines?date=${date}&class_id=${classId}`);
  await write.click();
  await expect(page).toHaveURL(`/routines?date=${date}&class_id=${classId}`);
  await expect(rows(page).nth(0).getByLabel("일과 이름")).toHaveValue("시간과 이름만 있는 일과");
  note(page, "S-J2 empty", { classId, date, returnedByLink: true });
});

test("D E F J — 어제 복사·검증 오류·실제 401 저장 실패와 재시도·삭제 지연", async ({
  page,
}, info) => {
  const { classId } = await enterHome(page);
  await page.getByRole("link", { name: "일과 작성하기" }).click();
  await expect(rows(page)).toHaveCount(PRESET_ROWS);
  const date = await page.getByLabel("날짜", { exact: true }).inputValue();
  const yesterday = new Date(`${date}T00:00:00Z`);
  yesterday.setUTCDate(yesterday.getUTCDate() - 1);
  await api(page, "/api/routines", "POST", {
    class_id: classId,
    date: yesterday.toISOString().slice(0, 10),
    name: "어제 일과",
    start: "09:00",
    end: "10:00",
    plan: "어제 계획",
    execution: "어제 실행",
  });
  // 어제 하루가 있으면 다시 열 때 그 이름 · 시간이 깔린다. 교사가 누를 단추는 없다.
  await page.reload();
  await expect(rows(page)).toHaveCount(1);
  await expect(rows(page).nth(0).getByLabel("일과 이름")).toHaveValue("어제 일과");
  await expectTime(rows(page).nth(0), "시작", "09:00");
  await expect(rows(page).nth(0).getByLabel("실제로 한 것")).toHaveValue("");
  expect(await dayRows(page, classId, date)).toEqual([]);
  note(page, "D", { timeAndNameOnly: true, noWrite: true });
  await rows(page).nth(0).getByLabel("일과 이름").fill("");
  await rows(page).nth(0).getByLabel("실제로 한 것").fill("오늘 작성 중인 실행");
  await page.getByRole("button", { name: "오늘 일지 만들기 →", exact: true }).click();
  await expect(rows(page).nth(0).getByText("일과 이름을 적어 주세요.")).toBeVisible();
  await expect(rows(page).nth(0).getByLabel("실제로 한 것")).toHaveValue("오늘 작성 중인 실행");
  expect(await dayRows(page, classId, date)).toEqual([]);
  note(page, "E", { fieldError: true, textPreserved: true });
  await rows(page).nth(0).getByLabel("일과 이름").fill("오늘 일과");
  const originalToken = await token(page);
  await page.evaluate(
    (value) => sessionStorage.setItem("saessak.authToken", value + "invalid"),
    originalToken,
  );
  await page.getByRole("button", { name: "저장", exact: true }).click();
  await expect(page.getByText("로그인이 필요해요. 다시 로그인한 뒤 이용해주세요.")).toBeVisible();
  await expect(rows(page).nth(0).getByLabel("실제로 한 것")).toHaveValue("오늘 작성 중인 실행");
  await page.getByRole("button", { name: "오늘 일지 만들기 →", exact: true }).click();
  await expect(page.getByText("로그인이 필요해요. 다시 로그인한 뒤 이용해주세요.")).toBeVisible();
  await expect(page).toHaveURL(/\/routines\?/);
  await page.evaluate(
    (value) => sessionStorage.setItem("saessak.authToken", value!),
    originalToken,
  );
  await page.getByRole("button", { name: "+ 줄 추가", exact: true }).click();
  await saved(page);
  await page.reload();
  await expect(rows(page)).toHaveCount(1); // 완전히 빈 두 번째 줄만 제외했다.
  note(page, "F", { realServerStatus: 401, noNavigation: true, retrySaved: true });
  await rows(page).nth(0).getByRole("button", { name: "1번째 일과 지우기" }).click();
  expect(await dayRows(page, classId, date)).toHaveLength(1);
  await saved(page);
  expect(await dayRows(page, classId, date)).toEqual([]);
  await page.screenshot({ path: info.outputPath("D-E-F-routines.png"), fullPage: true });
});

test("I J — 두 반의 일과·관찰 격리, 기록 화면 클릭 진입과 날짜 유지", async ({ page }, info) => {
  const { classId, centerId, childId } = await enterHome(page);
  const other = await api(page, `/api/centers/${centerId}/classes`, "POST", {
    name: "달님반",
    teacher_name: "다른교사",
    age_min: 4,
    age_max: 4,
    consent_confirmed: true,
  });
  const child = await api(page, `/api/classes/${other.id}/children`, "POST", { name: "나다라" });
  await page.getByRole("link", { name: "일과 작성하기" }).click();
  await expect(rows(page)).toHaveCount(PRESET_ROWS);
  const date = await page.getByLabel("날짜", { exact: true }).inputValue();
  await rows(page).nth(0).getByLabel("일과 이름").fill("햇살반 일과");
  await rows(page).nth(0).getByLabel("실제로 한 것").fill("햇살반에서 블록을 쌓았다.");
  await saved(page);
  await switchClass(page, "달님반");
  await expect(page).toHaveURL(/\/routines(\?|$)/);
  await expect(rows(page)).toHaveCount(PRESET_ROWS);
  // 다른 반은 그날이 비어 있다 — 깔아 둔 하루가 보이고 햇살반 줄은 섞이지 않는다.
  await expect(rows(page).nth(0).getByLabel("일과 이름")).toHaveValue("등원 및 통합보육");
  await rows(page).nth(0).getByLabel("일과 이름").fill("달님반 일과");
  await rows(page).nth(0).getByLabel("실제로 한 것").fill("달님반에서 공을 굴렸다.");
  await saved(page);
  // 일지는 보관함으로 가지 않고 이 화면에서 만들어 칠판 밑에 펼친다.
  await page.getByRole("button", { name: "오늘 일지 만들기 →", exact: true }).click();
  await expect(page.getByRole("region", { name: /보육일지$/ })).toBeVisible();
  await expect(page).toHaveURL(`/routines?date=${date}&class_id=${other.id}`);
  // 만든 일지는 고른 반(달님반) 것이고, 햇살반에는 그날 일지가 생기지 않는다.
  const otherLogs = await api(page, `/api/documents?kind=dailyLog&class_id=${other.id}`);
  expect(otherLogs.items.map((d: { start: string }) => d.start)).toContain(date);
  const mineLogs = await api(page, `/api/documents?kind=dailyLog&class_id=${classId}`);
  expect(mineLogs.items.map((d: { start: string }) => d.start)).not.toContain(date);
  await switchClass(page, "햇살반");
  await expect(rows(page).nth(0).getByLabel("일과 이름")).toHaveValue("햇살반 일과");
  for (const [cls, id, fact] of [
    [classId, childId, "햇살반 관찰 사실"],
    [other.id, child.id, "달님반 관찰 사실"],
  ]) {
    await api(page, "/api/observations", "POST", {
      class_id: cls,
      child_id: id,
      date,
      domain: "자연탐구",
      context: "놀이",
      fact,
    });
  }
  await page.getByRole("link", { name: "관찰일지", exact: true }).click();
  await expect(page.getByText("햇살반 관찰 사실", { exact: true })).toBeVisible();
  await expect(page.getByText("달님반 관찰 사실", { exact: true })).toHaveCount(0);
  await switchClass(page, "달님반");
  await expect(page.getByText("달님반 관찰 사실", { exact: true })).toBeVisible();
  await expect(page.getByText("햇살반 관찰 사실", { exact: true })).toHaveCount(0);
  // 관찰 기록 본문의 일과 링크는 걷었다. 사이드바 「보육일지」 메뉴로 가도 고른 반이 따라간다.
  await page.getByRole("link", { name: "보육일지", exact: true }).click();
  await expect(page.getByLabel("상단 현재 반", { exact: true })).toHaveText("달님반");
  // 오늘 일과가 다 뜬 뒤 날짜를 바꾼다 — 먼저 바꾸면 늦게 끝난 첫 불러오기가 오늘로 되돌린다.
  await expect(rows(page).nth(0).getByLabel("실제로 한 것")).toHaveValue("달님반에서 공을 굴렸다.");
  await page.getByLabel("날짜", { exact: true }).fill("2026-10-16");
  await expect(rows(page)).toHaveCount(PRESET_ROWS);
  await rows(page).nth(0).getByLabel("일과 이름").fill("지난 날짜 일과");
  await rows(page).nth(0).getByLabel("실제로 한 것").fill("지난 날짜에 길을 만들었다.");
  // 지난 날짜도 그 날짜 · 그 반 그대로 이 화면에서 일지를 만든다.
  await page.getByRole("button", { name: "오늘 일지 만들기 →", exact: true }).click();
  await expect(page.getByRole("region", { name: /보육일지$/ })).toBeVisible();
  await expect(page).toHaveURL(`/routines?date=2026-10-16&class_id=${other.id}`);
  await expect(rows(page).nth(0).getByLabel("일과 이름")).toHaveValue("지난 날짜 일과");
  note(page, "I S-J1/S-J2 scope", {
    classA: classId,
    classB: other.id,
    preservedDate: "2026-10-16",
  });
  // 주간 기록 메뉴는 보육일지 메뉴의 주간 탭으로 합쳤다(13주차 멘토 리뷰).
  await page.getByRole("link", { name: "주간 보육일지", exact: true }).click();
  await expect(page).toHaveURL(/\/weekly-records$/);
  await expect(
    page.getByRole("heading", { name: "보육일지", exact: true, level: 1 }),
  ).toBeVisible();
  await expect(page.getByLabel("상단 현재 반", { exact: true })).toHaveText("달님반");
  await expect(page.getByText("달님반 관찰 사실", { exact: true })).toBeVisible();
  await expect(page.getByText("햇살반 관찰 사실", { exact: true })).toHaveCount(0);
  await page.screenshot({
    path: info.outputPath("I-weekly-records-isolation.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "지난 주", exact: true }).click();
  const previous = new Date(`${date}T00:00:00Z`);
  previous.setUTCDate(previous.getUTCDate() - 7);
  const previousDate = previous.toISOString().slice(0, 10);
  const quickWrite = page.getByRole("link", { name: "일과 적기", exact: true });
  await expect(quickWrite).toHaveAttribute(
    "href",
    `/routines?date=${previousDate}&class_id=${other.id}`,
  );
  await quickWrite.click();
  await expect(page).toHaveURL(`/routines?date=${previousDate}&class_id=${other.id}`);
  note(page, "I weekly-records entry", {
    classA: classId,
    classB: other.id,
    preservedDate: previousDate,
  });
  await page.screenshot({ path: info.outputPath("I-class-isolation.png"), fullPage: true });
});
test("후속 #1~5 — 한 칸 시간 입력 · 기존 초 보존 · 이름 없는 줄에서 멈춤", async ({
  page,
}, info) => {
  const { classId } = await enterHome(page);
  const date = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Seoul" }).format(new Date());
  const seeds = [
    { name: "오후 놀이", start: "13:00:00", end: "14:00:00" },
    { name: "기존 분초", start: "09:16:25", end: "10:21:35" },
    { name: "동률 놀이", start: "09:16:25", end: "10:21:35" },
    { name: "시간 미입력", start: null, end: null },
  ];
  for (const [position, seed] of seeds.entries())
    await api(page, "/api/routines", "POST", {
      class_id: classId,
      date,
      position,
      ...seed,
      plan: `${seed.name} 계획`,
      execution: `${seed.name} 활동을 진행했다.`,
    });
  await page.goto(`/routines?date=${date}&class_id=${classId}`);
  // 화면은 시간순으로 줄을 세운다. 같은 시각은 원래 순서, 시간 없는 줄은 맨 끝이다.
  await expectNames(page, ["기존 분초", "동률 놀이", "오후 놀이", "시간 미입력"]);
  // 초가 있는 시간도 분까지만 보여 준다. 교사가 건드리지 않으면 초는 서버에 그대로 남는다.
  await expectTime(rows(page).nth(0), "시작", "09:16");
  await fillPlan(rows(page).nth(0), "계획만 수정함");
  await page.getByRole("button", { name: "+ 줄 추가", exact: true }).click();
  // 새 줄은 맨 끝에 생기고, 시계를 닫으면 시간순으로 선다 — 06:00 이라 맨 위로 간다.
  // 다른 줄과 겹치면 겹친 시간 알림이 저장을 막으므로 09:16 앞으로 둔다.
  await pickTime(rows(page).last(), "시작", "06:00");
  const added = rows(page).first();
  // 줄이 맨 위로 옮겨 선 뒤에 연다. 먼저 누르면 옛 첫 줄의 시계가 열린다.
  await expect(added.getByRole("button", { name: /^일과 시간 오전 06:00 ~/ })).toBeVisible();
  await pickTime(added, "종료", "07:00");
  await added.getByLabel("실제로 한 것").fill("새벽 활동을 기록했다.");

  const mutations = () =>
    diagnostics
      .get(page)!
      .network.filter((r) => /\/api\/routines(?:\/|$)/.test(r.url) && r.method !== "GET").length;
  const initial = mutations();
  await page.getByRole("button", { name: "저장", exact: true }).click();
  // 고칠 곳은 포스티 안내판이 줄마다 짚어 준다.
  await expect(page.getByRole("alert").filter({ hasText: "고칠 곳이" })).toBeVisible();
  await expect(added.getByLabel("일과 이름")).toBeFocused();
  expect(mutations()).toBe(initial);

  await added.getByLabel("일과 이름").fill("새벽 놀이");
  await saved(page);
  // 저장하면 보이는 순서가 그대로 서버 순서가 된다.
  const order = ["새벽 놀이", "기존 분초", "동률 놀이", "오후 놀이", "시간 미입력"];
  const stored = await dayRows(page, classId, date);
  expect(stored.map((r) => r.name)).toEqual(order);
  // 계획만 고친 줄도 교사가 안 건드린 초는 그대로다.
  expect(stored[1].start).toBe("09:16:25");
  expect(stored[1].end).toBe("10:21:35");
  expect(stored[0].start).toBe("06:00:00");
  expect(stored[0].end).toBe("07:00:00");
  await page.reload();
  await expectNames(page, order);
  await page.screenshot({ path: info.outputPath("routine-time-input.png"), fullPage: true });
  note(page, "followup #1-5", { order, ids: stored.map((r) => r.id), secondsPreserved: true });
});

test("후속 #6~11 — 실제 근거 비교·편집·단일 확인·원자적 재확정·안전한 재시도", async ({
  page,
}, info) => {
  const { classId } = await enterHome(page);
  const date = "2026-10-19";
  const routines = [];
  for (let position = 0; position < 2; position++)
    routines.push(
      await api(page, "/api/routines", "POST", {
        class_id: classId,
        date,
        position,
        start: "09:00",
        end: "10:00",
        name: `낙엽놀이${position}`,
        plan: "놀이 자료 준비",
        execution: "비가 와서 취소되었고 블록놀이로 대체함",
      }),
    );
  const doc = await api(page, "/api/documents", "POST", {
    kind: "dailyLog",
    class_id: classId,
    start: date,
    end: date,
    source_ids: routines.map((r) => r.id),
  });
  expect(doc.generation.rule_version).toBe("v4-mock");
  expect(doc.sections.every((s: { body: string }) => !s.body.startsWith("[mock]"))).toBe(true);
  const noteText = "교사가 이전에 작성한 검토 메모";
  await api(page, `/api/documents/${doc.id}`, "PUT", {
    sections: [...doc.sections].reverse(),
    review_note: noteText,
    updated_at: doc.updated_at,
  });
  await api(page, `/api/documents/${doc.id}/confirm`, "POST", {
    checks: { fact: true, interpretation: true, support: true },
  });
  for (const r of routines)
    await api(page, `/api/routines/${r.id}`, "PUT", {
      date,
      position: r.position,
      start: "09:05",
      end: "10:05",
      name: `변경된 ${r.name}`,
      plan: r.plan,
      execution: "아이들이 낙엽놀이를 즐겁게 진행함",
    });
  expect(dbDocument(doc.id)).toEqual({ id: doc.id, status: "CONFIRMED", stale: true });
  const review = await openDocument(page, doc.title, date);
  await expect(review.getByText("변경된 일과 기록 2건")).toBeVisible();
  await expect(review.getByRole("heading", { name: "수정 전", exact: true })).toHaveCount(2);
  await expect(review.getByText(/아이들이 낙엽놀이를 즐겁게 진행함/)).toHaveCount(2);
  await expect(page.getByText(/테스트 모드\(mock\)로 만든 초안/)).toBeVisible();
  await expect(page.getByRole("button", { name: "문서 삭제", exact: true })).toHaveCount(0);
  const warning = page.getByText(/이 문서의 근거로 사용된 일과 기록이 변경되었습니다/);
  await expect(warning).toBeVisible();
  const reviewBox = await review.boundingBox();
  const titleBox = await page
    .getByRole("heading", { name: doc.title, exact: true, level: 2 })
    .boundingBox();
  expect(reviewBox!.y).toBeLessThan(titleBox!.y);
  const submit = review.getByRole("button", { name: "변경사항 반영하고 재확정", exact: true });
  await expect(submit).toBeDisabled();
  await review
    .getByLabel("재검토 해석")
    .fill("교사가 변경된 사실을 대조하여 직접 수정한 해석입니다.");
  await review
    .getByLabel("재검토 지원")
    .fill("놀이 자료를 더 준비하고 활동 이후 교사가 다시 관찰할 계획입니다.");
  await review.getByRole("checkbox").check();
  await page.screenshot({ path: info.outputPath("source-comparison-review.png"), fullPage: true });
  let release!: () => void;
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route(`**/api/documents/${doc.id}/reconfirm`, async (route) => {
    await held;
    await route.continue();
  });
  const response = page.waitForResponse(
    (r) =>
      r.url().endsWith(`/api/documents/${doc.id}/reconfirm`) && r.request().method() === "POST",
  );
  const initial = diagnostics.get(page)!.network.length;
  await submit.click();
  await expect(review.getByRole("button", { name: "재확정 중…", exact: true })).toBeDisabled();
  release();
  const completed = await response;
  await page.unroute(`**/api/documents/${doc.id}/reconfirm`);
  expect(completed.status()).toBe(200);
  const request = completed.request().postDataJSON();
  const after = await completed.json();
  expect(after.status).toBe("CONFIRMED");
  expect(after.stale).toBe(false);
  expect(after.review_note).toBe(noteText);
  expect(after.sections.map((s: { heading: string }) => s.heading)).toEqual([
    "사실",
    "해석",
    "지원",
  ]);
  expect(after.sections[0].body).toContain("아이들이 낙엽놀이를 즐겁게 진행함");
  expect(after.sections[1].body).toBe("교사가 변경된 사실을 대조하여 직접 수정한 해석입니다.");
  expect(after.sections[2].body).toBe(
    "놀이 자료를 더 준비하고 활동 이후 교사가 다시 관찰할 계획입니다.",
  );
  await expect(review).toHaveCount(0);
  const actions = diagnostics
    .get(page)!
    .network.slice(initial)
    .filter((r) => r.method === "POST" && r.url.startsWith(`/api/documents/${doc.id}/`));
  expect(actions.map((r) => r.url)).toEqual([`/api/documents/${doc.id}/reconfirm`]);
  const retries = await Promise.all([
    api(page, `/api/documents/${doc.id}/reconfirm`, "POST", request),
    api(page, `/api/documents/${doc.id}/reconfirm`, "POST", request),
  ]);
  expect(retries).toEqual([after, after]);
  await page.reload();
  await openDocument(page, doc.title, date);
  await expect(
    page.getByText("교사가 변경된 사실을 대조하여 직접 수정한 해석입니다.", { exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("region", { name: "변경된 근거 검토" })).toHaveCount(0);
  expect(dbDocument(doc.id)).toEqual({ id: doc.id, status: "CONFIRMED", stale: false });
  await page.screenshot({ path: info.outputPath("reconfirmed-document.png"), fullPage: true });
  note(page, "followup #6-11", {
    documentId: doc.id,
    originalNotePreserved: true,
    apiActions: actions,
    retries: 2,
  });
});

/** 삭제된 근거를 처리하는 화면·API 를 실제 스택에서 확인한다. 서버 응답을 가로채지 않는다. */
async function confirmedDailyLog(page: Page, classId: number, date: string, names: string[]) {
  const routines = [];
  for (const [position, name] of names.entries())
    routines.push(
      await api(page, "/api/routines", "POST", {
        class_id: classId,
        date,
        position,
        start: "09:00",
        end: "10:00",
        name,
        plan: "놀이 자료 준비",
        execution: `${name} 시간에 있었던 일을 그대로 적었다.`,
      }),
    );
  return routines;
}

/**
 * 보육일지는 **반 → 보육일지 → 날짜** 로 탐색한다. 예전의 전체 문서 목록은 없앴으므로
 * 제목만으로 바로 누르지 않는다.
 */
async function openDocument(page: Page, title: string, date: string, className = "햇살반") {
  await page.goto("/documents");
  await page.getByRole("complementary", { name: "반 선택" }).getByText(className).click();
  await page.getByRole("button", { name: "보육일지", exact: true }).click();
  await expect(page.getByLabel("아동 이름 검색")).toHaveCount(0);
  await expect(page.getByText("왼쪽에서 아이를 선택해 주세요", { exact: true })).toHaveCount(0);
  await page.getByLabel("날짜 선택").fill(date);
  await page
    .getByRole("button", { name: new RegExp(title.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")) })
    .click();
  await page
    .getByRole("complementary", { name: "문서 미리보기" })
    .getByRole("button", { name: /^(편집하기|문서 열기)$/ })
    .click();
  return page.getByRole("region", { name: "변경된 근거 검토" });
}

/** 일부러 거절을 받아 본다. 그 주소의 4xx 는 afterEach 의 사고 검사에서 빼 둔다. */
async function raw(page: Page, path: string, method: string, data?: unknown) {
  test.info().annotations.push({ type: "expected-4xx", description: path });
  return page.request.fetch(path, {
    method,
    data,
    headers: { Authorization: `Bearer ${await token(page)}` },
  });
}

test("후속 #12 — 삭제된 근거를 다른 일과로 대체해 같은 문서를 재확정한다", async ({
  page,
}, info) => {
  const { classId } = await enterHome(page);
  const date = "2026-10-20";
  const [gone, kept, spare] = await confirmedDailyLog(page, classId, date, [
    "지워질 일과",
    "남는 일과",
    "대체용 일과",
  ]);
  const doc = await api(page, "/api/documents", "POST", {
    kind: "dailyLog",
    class_id: classId,
    start: date,
    end: date,
    source_ids: [gone.id, kept.id],
  });
  await api(page, `/api/documents/${doc.id}/confirm`, "POST", {
    checks: { fact: true, interpretation: true, support: true },
  });
  await api(page, `/api/routines/${gone.id}`, "DELETE");
  expect(dbDocument(doc.id)).toEqual({ id: doc.id, status: "CONFIRMED", stale: true });

  // 확정본에 초안 전용 refresh 를 부르면 서버가 막는다 — 화면도 이 버튼을 내보내지 않는다.
  const blocked = await raw(page, `/api/documents/${doc.id}/refresh`, "POST");
  expect(blocked.status()).toBe(409);
  expect((await blocked.json()).error.code).toBe("ALREADY_CONFIRMED");

  // 교사가 실제로 보낸 본문을 그대로 들고 있다가 아래에서 재시도로 다시 보낸다.
  let sent: string | null = null;
  await page.route(`**/api/documents/${doc.id}/reconfirm`, async (route) => {
    sent = route.request().postData();
    await route.continue();
  });
  const review = await openDocument(page, doc.title, date);
  await expect(page.getByRole("button", { name: "변경된 근거 반영하기" })).toHaveCount(0);
  await expect(review.getByText("보육일지에 사용된 일과 기록 1건이 삭제되었습니다.")).toBeVisible();
  await expect(review.getByRole("heading", { name: "지워질 일과 09:00~10:00" })).toBeVisible();
  const submit = review.getByRole("button", { name: "변경사항 반영하고 재확정", exact: true });
  await expect(submit).toBeDisabled();
  await review.getByRole("radio", { name: /다른 일과 기록으로 대체하기/ }).check();
  const picker = review.getByLabel(/대체할 일과 기록/);
  // 후보는 같은 반·같은 날짜에서 아직 쓰지 않은 일과뿐이다. 남는 일과는 들어가지 않는다.
  await expect(picker.locator("option")).toHaveText([
    "—",
    `[대체용 일과 09:00~10:00] 대체용 일과 시간에 있었던 일을 그대로 적었다.`,
  ]);
  await picker.selectOption(String(spare.id));
  await review.getByLabel("재검토 해석").fill("교사가 대체한 근거를 다시 읽고 고친 해석입니다.");
  await review.getByLabel("재검토 지원").fill("다음에는 같은 놀이를 더 길게 열어 줄 계획입니다.");
  await review.getByRole("checkbox").check();
  await page.screenshot({ path: info.outputPath("deleted-source-replace.png"), fullPage: true });
  await submit.click();
  await expect(review).toHaveCount(0);

  const after = await api(page, `/api/documents/${doc.id}`);
  expect([after.status, after.stale]).toEqual(["CONFIRMED", false]);
  expect(after.sources.map((s: { id: number }) => s.id).sort()).toEqual([spare.id, kept.id].sort());
  expect(after.sections[0].body).toContain("대체용 일과 시간에 있었던 일");
  expect(after.sections[0].body).not.toContain("지워질 일과 시간에 있었던 일");
  expect(after.sections[1].body).toBe("교사가 대체한 근거를 다시 읽고 고친 해석입니다.");
  expect(dbDocument(doc.id)).toEqual({ id: doc.id, status: "CONFIRMED", stale: false });
  // 응답을 잃은 교사가 같은 요청을 다시 보내도 같은 문서 하나로 끝난다 (F5).
  expect(sent).not.toBeNull();
  const retried = await api(page, `/api/documents/${doc.id}/reconfirm`, "POST", JSON.parse(sent!));
  expect(retried).toEqual(after);
  expect(dbDocument(doc.id)).toEqual({ id: doc.id, status: "CONFIRMED", stale: false });
  await page.reload();
  await expect(page.getByRole("region", { name: "변경된 근거 검토" })).toHaveCount(0);
  note(page, "followup #12", { document: doc.id, replaced: [gone.id, spare.id] });
});

test("후속 #13 — 삭제된 근거를 제외하고, 전부 빼려 하면 서버가 막는다", async ({ page }, info) => {
  const { classId } = await enterHome(page);
  const date = "2026-10-21";
  const [gone, kept] = await confirmedDailyLog(page, classId, date, ["사라질 일과", "버틸 일과"]);
  const doc = await api(page, "/api/documents", "POST", {
    kind: "dailyLog",
    class_id: classId,
    start: date,
    end: date,
    source_ids: [gone.id, kept.id],
  });
  await api(page, `/api/documents/${doc.id}/confirm`, "POST", {
    checks: { fact: true, interpretation: true, support: true },
  });
  await api(page, `/api/routines/${gone.id}`, "DELETE");

  const review = await openDocument(page, doc.title, date);
  const submit = review.getByRole("button", { name: "변경사항 반영하고 재확정", exact: true });
  // 대체 후보가 없으면 대체하기를 고를 수 없다.
  await expect(review.getByRole("radio", { name: /다른 일과 기록으로 대체하기/ })).toBeDisabled();
  await review.getByRole("radio", { name: /보육일지에서도 제외하기/ }).check();
  await review.getByLabel("재검토 해석").fill("남은 근거만으로 다시 읽고 고친 해석입니다.");
  await review.getByLabel("재검토 지원").fill("남은 놀이를 이어 갈 수 있게 지원할 계획입니다.");
  await review.getByRole("checkbox").check();
  await page.screenshot({ path: info.outputPath("deleted-source-exclude.png"), fullPage: true });
  await submit.click();
  await expect(review).toHaveCount(0);

  const after = await api(page, `/api/documents/${doc.id}`);
  expect([after.status, after.stale]).toEqual(["CONFIRMED", false]);
  expect(after.sources.map((s: { id: number }) => s.id)).toEqual([kept.id]);
  expect(after.sections.every((s: { source_ids: number[] }) => s.source_ids.length === 1)).toBe(
    true,
  );
  expect(after.sections[0].body).not.toContain("사라질 일과 시간에 있었던 일");

  // 남은 근거까지 지우면 뺄 것이 없다. 서버가 막고 확정본은 그대로다.
  await api(page, `/api/routines/${kept.id}`, "DELETE");
  const comparison = await api(page, `/api/documents/${doc.id}/source-comparison`);
  expect(comparison.can_reconfirm).toBe(false);
  const refused = await raw(page, `/api/documents/${doc.id}/reconfirm`, "POST", {
    review_token: comparison.review_token,
    updated_at: comparison.updated_at,
    checks: { fact: true, interpretation: true, support: true },
    sections: after.sections.map((s: { heading: string; body: string }) => ({
      heading: s.heading,
      body: s.heading === "사실" ? "" : s.body,
      source_ids: [],
    })),
    resolutions: [{ source_id: kept.id, action: "drop" }],
  });
  expect(refused.status()).toBe(409);
  expect((await refused.json()).error.code).toBe("GATE_BLOCKED");
  expect(dbDocument(doc.id)).toEqual({ id: doc.id, status: "CONFIRMED", stale: true });
  note(page, "followup #13", { document: doc.id, dropped: gone.id });
});

test("후속 #14 — 일과 줄: 이름 · 시간 · 지우기가 한 줄에 서고 실제로 한 것이 그 아래 넓게 선다", async ({
  page,
}, info) => {
  const { classId } = await enterHome(page);
  const date = "2026-10-22";
  await api(page, "/api/routines", "POST", {
    class_id: classId,
    date,
    position: 0,
    start: "09:16",
    end: "10:40",
    name: "오전 실내놀이",
    plan: "블록으로 탑 쌓기",
    execution: "블록으로 탑을 쌓다가 무너지자 아래쪽을 넓게 깔았다.",
  });
  await page.goto(`/routines?date=${date}&class_id=${classId}`);
  const card = rows(page).first();
  await expect(card.getByLabel("일과 이름")).toHaveValue("오전 실내놀이");
  const nameBox = (await card.getByLabel("일과 이름").boundingBox())!;
  // 시간은 「오전 09:16 ~ 10:40」 한 칸이다. 시작 · 종료 칸은 시계판과 함께 접혀 있다.
  const timeBox = (await card.getByRole("button", { name: /^일과 시간 / }).boundingBox())!;
  const removeBox = (await card.getByLabel("1번째 일과 지우기").boundingBox())!;
  // 이름 · 시간 · 지우기는 같은 줄에 왼쪽부터 차례로 선다.
  for (const box of [timeBox, removeBox])
    expect(Math.abs(box.y + box.height / 2 - (nameBox.y + nameBox.height / 2))).toBeLessThan(
      nameBox.height,
    );
  expect(nameBox.x).toBeLessThan(timeBox.x);
  expect(timeBox.x).toBeLessThan(removeBox.x);
  // 매일 적는 「실제로 한 것」이 그 아래 넓게 서고, 「계획한 것」은 접혀 있다.
  const doneBox = (await card.getByLabel("실제로 한 것").boundingBox())!;
  expect(doneBox.y).toBeGreaterThan(nameBox.y);
  expect(doneBox.width).toBeGreaterThan(nameBox.width);
  await page.screenshot({ path: info.outputPath("routine-card-layout.png"), fullPage: true });
  // 모바일에서도 가로 스크롤이 생기지 않는다.
  await page.setViewportSize({ width: 390, height: 844 });
  await expect
    .poll(() =>
      page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      ),
    )
    .toBeLessThanOrEqual(0);
  await page.screenshot({ path: info.outputPath("routine-card-mobile.png"), fullPage: true });
  note(page, "followup #14", { name: nameBox, done: doneBox });
});

test("후속 #15 — 확정 취소된 초안에서 삭제된 근거를 처리하고 다시 확정한다", async ({
  page,
}, info) => {
  const { classId } = await enterHome(page);
  const date = "2026-10-23";
  // 1) 일과 3개로 보육일지를 만든다.
  const [gone, kept, spare] = await confirmedDailyLog(page, classId, date, [
    "없어질 일과",
    "남을 일과",
    "바꿔 넣을 일과",
  ]);
  const doc = await api(page, "/api/documents", "POST", {
    kind: "dailyLog",
    class_id: classId,
    start: date,
    end: date,
    source_ids: [gone.id, kept.id],
  });
  // 2) 확정한다.
  await api(page, `/api/documents/${doc.id}/confirm`, "POST", {
    checks: { fact: true, interpretation: true, support: true },
  });
  // 3) 쓴 일과 하나를 지운다. 4) 확정을 취소한다 — 여기서 예전에는 막다른 길이었다.
  await api(page, `/api/routines/${gone.id}`, "DELETE");
  await api(page, `/api/documents/${doc.id}/unconfirm`, "POST");
  expect(dbDocument(doc.id)).toEqual({ id: doc.id, status: "DRAFT", stale: true });

  // 본문 없는 예전 호출은 그대로 막힌다 — 서버 규칙을 무르지 않았다.
  const blocked = await raw(page, `/api/documents/${doc.id}/refresh`, "POST");
  expect(blocked.status()).toBe(409);
  expect((await blocked.json()).error.code).toBe("GATE_BLOCKED");

  const review = await openDocument(page, doc.title, date);
  // 5) 초안에서도 같은 복구 화면이 뜨고, 막다른 안내 대신 선택지를 준다.
  await expect(review.getByText("보육일지에 사용된 일과 기록 1건이 삭제되었습니다.")).toBeVisible();
  await expect(review.getByRole("heading", { name: "없어질 일과 09:00~10:00" })).toBeVisible();
  await expect(page.getByText(/이 문서를 지우고 새로 만들어주세요/)).toHaveCount(0);
  // 복구 화면이 떠 있는 동안 실패할 버튼은 내보내지 않는다.
  await expect(page.getByRole("button", { name: "변경된 근거 반영하기" })).toHaveCount(0);
  const apply = review.getByRole("button", { name: "변경사항 반영하기", exact: true });
  await expect(apply).toBeDisabled();
  // 초안에서는 교사 확인을 여기서 받지 않는다 — 확정은 아래 본문에서 한다.
  await expect(review.getByRole("checkbox")).toHaveCount(0);
  await review.getByRole("radio", { name: /다른 일과 기록으로 대체하기/ }).check();
  await review.getByLabel(/대체할 일과 기록/).selectOption(String(spare.id));
  await page.screenshot({ path: info.outputPath("draft-recovery-replace.png"), fullPage: true });
  // 6) 기존 문서에 반영한다.
  await apply.click();
  await expect(review).toHaveCount(0);
  await expect(page.getByText(/변경사항을 반영했어요/)).toBeVisible();

  const applied = await api(page, `/api/documents/${doc.id}`);
  expect([applied.id, applied.status, applied.stale]).toEqual([doc.id, "DRAFT", false]);
  expect(applied.sources.map((s: { id: number }) => s.id).sort()).toEqual(
    [spare.id, kept.id].sort(),
  );
  expect(applied.sections[0].body).toContain("바꿔 넣을 일과 시간에 있었던 일");
  expect(applied.sections[0].body).not.toContain("없어질 일과 시간에 있었던 일");

  // 7) 교사가 읽고 확정한다.
  await page.getByRole("checkbox", { name: /원본 기록과 사실이 일치하고/ }).check();
  await page.getByRole("button", { name: "검토 완료 · 문서 확정", exact: true }).click();
  await expect(page.getByText("검토한 문서를 확정했어요.")).toBeVisible();
  // 8) 새로고침해도 9) 문서 id · 근거 · 확정 상태가 그대로다.
  await page.reload();
  expect(dbDocument(doc.id)).toEqual({ id: doc.id, status: "CONFIRMED", stale: false });
  const final = await api(page, `/api/documents/${doc.id}`);
  expect(final.sources.map((s: { id: number }) => s.id).sort()).toEqual([spare.id, kept.id].sort());
  await page.screenshot({ path: info.outputPath("draft-recovery-confirmed.png"), fullPage: true });
  note(page, "followup #15", { document: doc.id, replaced: [gone.id, spare.id] });
});

test("후속 #16 — 초안에서 삭제된 근거를 제외하고, 전부 빼려 하면 막힌다", async ({ page }) => {
  const { classId } = await enterHome(page);
  const date = "2026-10-24";
  const [gone, kept] = await confirmedDailyLog(page, classId, date, ["빠질 일과", "남을 일과"]);
  const doc = await api(page, "/api/documents", "POST", {
    kind: "dailyLog",
    class_id: classId,
    start: date,
    end: date,
    source_ids: [gone.id, kept.id],
  });
  await api(page, `/api/documents/${doc.id}/confirm`, "POST", {
    checks: { fact: true, interpretation: true, support: true },
  });
  await api(page, `/api/routines/${gone.id}`, "DELETE");
  await api(page, `/api/documents/${doc.id}/unconfirm`, "POST");
  const before = await api(page, `/api/documents/${doc.id}`);

  // 살아 있는 근거는 아예 고를 수 없다 — 교사가 멀쩡한 근거를 실수로 빼지 못한다.
  const alive = await raw(page, `/api/documents/${doc.id}/refresh`, "POST", {
    resolutions: [{ source_id: kept.id, action: "drop" }],
  });
  expect(alive.status()).toBe(422);
  expect((await alive.json()).error.code).toBe("VALIDATION_FAILED");
  expect(await api(page, `/api/documents/${doc.id}`)).toEqual(before);

  const review = await openDocument(page, doc.title, date);
  await expect(review.getByRole("radio", { name: /다른 일과 기록으로 대체하기/ })).toBeDisabled();
  await review.getByRole("radio", { name: /보육일지에서도 제외하기/ }).check();
  await review.getByRole("button", { name: "변경사항 반영하기", exact: true }).click();
  await expect(review).toHaveCount(0);
  const after = await api(page, `/api/documents/${doc.id}`);
  expect([after.id, after.status, after.stale]).toEqual([doc.id, "DRAFT", false]);
  expect(after.sources.map((s: { id: number }) => s.id)).toEqual([kept.id]);
  expect(after.sections.every((s: { source_ids: number[] }) => s.source_ids.length === 1)).toBe(
    true,
  );
  // 해석·지원은 그대로다 — 서버가 다시 쓰지 않는다.
  expect(after.sections.slice(1).map((s: { body: string }) => s.body)).toEqual(
    before.sections.slice(1).map((s: { body: string }) => s.body),
  );

  // 마지막 근거까지 지워지면 뺄 것이 없다. 서버가 막고 초안은 그대로다.
  await api(page, `/api/routines/${kept.id}`, "DELETE");
  const emptied = await api(page, `/api/documents/${doc.id}`);
  const refused = await raw(page, `/api/documents/${doc.id}/refresh`, "POST", {
    resolutions: [{ source_id: kept.id, action: "drop" }],
  });
  expect(refused.status()).toBe(409);
  expect((await refused.json()).error.code).toBe("GATE_BLOCKED");
  expect(await api(page, `/api/documents/${doc.id}`)).toEqual(emptied);
});

for (const sourceKind of ["dailyLog", "routine"] as const) {
  test(`주간 보육일지 — ${sourceKind} 근거로 생성한 문서를 편집·확정·한글 다운로드하고 같은 달 목록에서 다시 연다`, async ({
    page,
  }, info) => {
    const { classId } = await enterHome(page);
    const start = "2026-09-28";
    const end = "2026-10-02";
    const sourceIds: number[] = [];
    for (const date of [start, end]) {
      const [routine] = await confirmedDailyLog(page, classId, date, ["블록놀이"]);
      if (sourceKind === "routine") {
        sourceIds.push(routine.id);
        continue;
      }
      const daily = await api(page, "/api/documents", "POST", {
        kind: "dailyLog",
        class_id: classId,
        start: date,
        end: date,
        source_ids: [routine.id],
      });
      await api(page, `/api/documents/${daily.id}/confirm`, "POST", {
        checks: { fact: true, interpretation: true, support: true },
      });
      sourceIds.push(daily.id);
    }
    await page.goto(`/documents?kind=dailyLog&class_id=${classId}&date=${start}`);
    await page.getByRole("combobox", { name: "문서 종류" }).selectOption("weeklyLog");
    await page.getByLabel("근거로 쓸 기록").selectOption(sourceKind);
    await page.getByLabel("종료일", { exact: true }).fill(end);
    const candidates = page.getByRole("group").getByRole("checkbox");
    await expect(candidates).toHaveCount(2);
    // 주간 근거는 목록 순서를 따른다. 기간 양끝 날짜의 근거를 모두 선택한다.
    await page.getByRole("checkbox", { name: new RegExp(`^${start}`) }).check();
    await page.getByRole("checkbox", { name: new RegExp(`^${end}`) }).check();
    const response = page.waitForResponse(
      (r) => r.url().endsWith("/api/documents") && r.request().method() === "POST",
    );
    await page.getByRole("button", { name: "초안 만들기", exact: true }).click();
    const generated = await response;
    expect(generated.status()).toBe(201);
    expect(generated.request().postDataJSON()).toMatchObject({
      kind: "weeklyLog",
      class_id: classId,
      child_id: null,
      start,
      end,
      source_kind: sourceKind,
      source_ids: expect.arrayContaining(sourceIds),
    });
    expect(generated.request().postDataJSON().source_ids).toHaveLength(sourceIds.length);
    const doc = await generated.json();
    await expect(
      page.getByRole("heading", { name: doc.title, exact: true, level: 2 }),
    ).toBeVisible();
    const support = "다음 놀이에는 블록을 준비해 함께 길을 만들도록 지원한다.";
    await page.getByRole("textbox", { name: "지원 내용", exact: true }).fill(support);
    await page.getByRole("checkbox", { name: /원본 기록과 사실이 일치하고/ }).check();
    await page.getByRole("button", { name: "검토 완료 · 문서 확정", exact: true }).click();
    await expect(page.getByText("검토한 문서를 확정했어요.")).toBeVisible();
    const saved = await api(page, `/api/documents/${doc.id}`);
    expect(saved).toMatchObject({ id: doc.id, status: "CONFIRMED", child_id: null });
    expect(saved.sections.find((s: { heading: string }) => s.heading === "지원").body).toBe(
      support,
    );
    // 확정본은 한글 파일로 받는다. 교사가 고친 지원 글이 파일에 들어갔는지 연다.
    const download = page.waitForEvent("download");
    await page.getByRole("button", { name: "한글 파일로 내려받기", exact: true }).click();
    await verifyHwpx(await download, info.outputPath(`weekly-log-${sourceKind}.hwpx`), [support]);
    await page.getByRole("button", { name: "← 문서 목록으로 돌아가기", exact: true }).click();
    await expect(page.getByRole("button", { name: "주간", exact: true })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expect(page.getByText("2026년 9월", { exact: true })).toBeVisible();
    await page
      .getByRole("button", { name: new RegExp(doc.title.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")) })
      .click();
    await page
      .getByRole("complementary", { name: "문서 미리보기" })
      .getByRole("button", { name: /^(편집하기|문서 열기)$/ })
      .click();
    await expect(
      page.getByRole("heading", { name: doc.title, exact: true, level: 2 }),
    ).toBeVisible();
    await expect(page.getByRole("button", { name: "확정 취소", exact: true })).toBeVisible();
  });
}

test("보육일지 탐색 — 아동 없는 반에서도 일일·주간 조회, 수정·재열기와 반 격리", async ({
  page,
}, info) => {
  const { classId, centerId, childId } = await enterHome(page);
  const date = "2026-10-19";
  const [routine] = await confirmedDailyLog(page, classId, date, ["블록놀이"]);
  const daily = await api(page, "/api/documents", "POST", {
    kind: "dailyLog",
    class_id: classId,
    start: date,
    end: date,
    source_ids: [routine.id],
  });
  const weekly = await api(page, "/api/documents", "POST", {
    kind: "weeklyLog",
    class_id: classId,
    start: date,
    end: "2026-10-23",
    source_kind: "routine",
    source_ids: [routine.id],
  });
  await api(page, `/api/children/${childId}`, "DELETE");
  expect((await api(page, `/api/classes/${classId}/children`)).items).toHaveLength(0);
  const other = await api(page, `/api/centers/${centerId}/classes`, "POST", {
    name: "달님반",
    teacher_name: "다른교사",
    age_min: 4,
    age_max: 4,
    consent_confirmed: true,
  });
  await openDocument(page, daily.title, date);
  await expect(
    page.getByRole("heading", { name: daily.title, exact: true, level: 2 }),
  ).toBeVisible();
  const support = "다음 놀이에는 블록을 준비해 함께 길을 만들도록 지원한다.";
  await page.getByRole("textbox", { name: "지원 내용", exact: true }).fill(support);
  await page.getByRole("button", { name: "초안 저장", exact: true }).click();
  await expect(page.getByText("작성 중인 초안을 저장했어요.", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "← 문서 목록으로 돌아가기", exact: true }).click();
  await expect(page.getByRole("heading", { name: "햇살반 보육일지", exact: true })).toBeVisible();
  await expect(page.getByText("만 4세반 · 반별 문서", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "가나다", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "＋ 보육일지 작성", exact: true })).toHaveCount(0);
  const calendar = page.getByRole("group", { name: "보육일지 주간 달력" });
  await expect(calendar.getByRole("button")).toHaveCount(7);
  await expect(calendar.getByRole("button", { pressed: true })).toHaveCount(1);
  await expect(calendar.getByRole("button", { pressed: true })).toContainText("검토 중");
  // 이미 문서가 있는 날짜에는 하단 중복 생성 카드도 표시하지 않는다.
  await expect(page.getByRole("button", { name: /^이 날짜 보육일지 작성/ })).toHaveCount(0);
  await page.getByRole("button", { name: "다음 기간", exact: true }).click();
  await expect(page.getByLabel("날짜 선택")).toHaveValue("2026-10-26");
  await page.getByRole("button", { name: "이전 기간", exact: true }).click();
  await expect(page.getByLabel("날짜 선택")).toHaveValue(date);
  await page
    .getByRole("button", { name: new RegExp(daily.title.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")) })
    .click();
  await page
    .getByRole("complementary", { name: "문서 미리보기" })
    .getByRole("button", { name: /^(편집하기|문서 열기)$/ })
    .click();
  await expect(page.getByRole("textbox", { name: "지원 내용", exact: true })).toHaveValue(support);
  expect(await api(page, `/api/documents/${daily.id}`)).toMatchObject({
    id: daily.id,
    child_id: null,
  });
  await page.getByRole("button", { name: "← 문서 목록으로 돌아가기", exact: true }).click();
  await page.getByRole("button", { name: "주간", exact: true }).click();
  await expect(page.getByLabel("아동 이름 검색")).toHaveCount(0);
  await expect(page.getByRole("button", { name: /^새 주간 보육일지 작성/ })).toBeEnabled();
  await expect(
    page.getByRole("button", {
      name: new RegExp(weekly.title.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")),
    }),
  ).toBeVisible();
  await page.getByRole("button", { name: "이전 기간", exact: true }).click();
  await expect(
    page.getByRole("button", {
      name: new RegExp(weekly.title.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")),
    }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "다음 기간", exact: true }).click();
  await page
    .getByRole("button", { name: new RegExp(weekly.title.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")) })
    .click();
  await page
    .getByRole("complementary", { name: "문서 미리보기" })
    .getByRole("button", { name: /^(편집하기|문서 열기)$/ })
    .click();
  await expect(
    page.getByRole("heading", { name: weekly.title, exact: true, level: 2 }),
  ).toBeVisible();
  await page.getByRole("button", { name: "← 문서 목록으로 돌아가기", exact: true }).click();
  await page.getByRole("button", { name: "일일", exact: true }).click();
  await page.getByRole("complementary", { name: "반 선택" }).getByText("달님반").click();
  await page.getByRole("button", { name: "보육일지", exact: true }).click();
  await expect(page.getByRole("heading", { name: "달님반 보육일지", exact: true })).toBeVisible();
  await expect(
    page.getByRole("button", {
      name: new RegExp(daily.title.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")),
    }),
  ).toHaveCount(0);
  await expect(page.getByLabel("아동 이름 검색")).toHaveCount(0);
  for (const width of [390, 768, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    await expect(page.getByLabel("날짜 선택")).toBeVisible();
    await expect(page.getByLabel("아동 이름 검색")).toHaveCount(0);
    await expect
      .poll(() =>
        page.evaluate(
          () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
        ),
      )
      .toBeLessThanOrEqual(0);
    await page.screenshot({
      path: info.outputPath(`care-navigation-${width}.png`),
      fullPage: true,
    });
  }
  await page.getByRole("button", { name: /^이 날짜 보육일지 작성/ }).click();
  const creationClass = page.getByRole("combobox", { name: "담당 반", exact: true });
  await expect(creationClass.locator("option:checked")).toHaveText(/달님반/);
  await expect(page.getByLabel("날짜", { exact: true })).toHaveValue(date);
  expect(other.id).not.toBe(classId);
  await page.screenshot({
    path: info.outputPath("care-class-without-children.png"),
    fullPage: true,
  });
});

test("관찰일지 탐색 — 아동 선택·검색·변경 시 해당 아동 기록만 열고 날짜를 이동한다", async ({
  page,
}, info) => {
  const { classId, childId } = await enterHome(page);
  const other = await api(page, `/api/classes/${classId}/children`, "POST", { name: "라마바" });
  const date = "2026-10-19";
  const docs = [];
  for (const [id, fact] of [
    [childId, "블록을 쌓았다."],
    [other.id, "공을 굴렸다."],
  ] as const) {
    const source = await api(page, "/api/observations", "POST", {
      class_id: classId,
      child_id: id,
      date,
      domain: "자연탐구",
      context: "놀이",
      fact,
    });
    docs.push(
      await api(page, "/api/documents", "POST", {
        kind: "observation",
        class_id: classId,
        child_id: id,
        start: date,
        end: date,
        source_ids: [source.id],
      }),
    );
  }
  await page.goto("/documents");
  await page.getByRole("complementary", { name: "반 선택" }).getByText("햇살반").click();
  await page.getByRole("button", { name: "관찰일지", exact: true }).click();
  await expect(page.getByLabel("아동 이름 검색")).toBeVisible();
  await expect(page.getByText("왼쪽에서 아이를 선택해 주세요", { exact: true })).toBeVisible();
  await expect(page.getByLabel("날짜 선택")).toHaveCount(0);
  await page.getByRole("button", { name: "가나다", exact: true }).click();
  await expect(page.getByRole("button", { name: "가나다", exact: true })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await page.getByLabel("날짜 선택").fill(date);
  const calendar = page.getByRole("group", { name: "관찰일지 주간 달력" });
  await expect(calendar.getByRole("button")).toHaveCount(7);
  await expect(calendar.getByRole("button", { pressed: true })).toHaveCount(1);
  await expect(calendar.getByRole("button", { pressed: true })).toContainText("검토 중");
  await page
    .getByRole("button", { name: new RegExp(docs[0].title.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")) })
    .click();
  await page
    .getByRole("complementary", { name: "문서 미리보기" })
    .getByRole("button", { name: /^(편집하기|문서 열기)$/ })
    .click();
  await expect(page.getByText("블록을 쌓았다.", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("공을 굴렸다.", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "← 문서 목록으로 돌아가기", exact: true }).click();
  await page.getByLabel("아동 이름 검색").fill("라마");
  await expect(page.getByRole("button", { name: "가나다", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "라마바", exact: true }).click();
  await expect(page.getByRole("button", { name: "라마바", exact: true })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect(
    page.getByRole("heading", { name: docs[0].title, exact: true, level: 2 }),
  ).toHaveCount(0);
  await page
    .getByRole("button", { name: new RegExp(docs[1].title.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")) })
    .click();
  await page
    .getByRole("complementary", { name: "문서 미리보기" })
    .getByRole("button", { name: /^(편집하기|문서 열기)$/ })
    .click();
  await expect(page.getByText("공을 굴렸다.", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("블록을 쌓았다.", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "← 문서 목록으로 돌아가기", exact: true }).click();
  await page.getByRole("button", { name: "다음 기간", exact: true }).click();
  await expect(page.getByLabel("날짜 선택")).toHaveValue("2026-10-26");
  await expect(calendar.getByRole("button", { pressed: true })).toContainText("미작성");
  await expect(page.getByRole("button", { name: /^이 날짜 관찰일지 작성/ })).toBeEnabled();
  await expect(
    page.getByRole("button", {
      name: new RegExp(docs[1].title.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")),
    }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "이전 기간", exact: true }).click();
  await expect(page.getByLabel("날짜 선택")).toHaveValue(date);
  await expect(calendar.getByRole("button", { pressed: true })).toContainText("검토 중");
  await expect(page.getByRole("button", { name: /^이 날짜 관찰일지 작성/ })).toHaveCount(0);
  await expect(
    page.getByRole("button", {
      name: new RegExp(docs[1].title.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")),
    }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "＋ 관찰일지 작성", exact: true })).toHaveCount(0);
  await page.screenshot({
    path: info.outputPath("observation-child-navigation.png"),
    fullPage: true,
  });
});

for (const width of [1440, 390]) {
  test(`미리보기 ${width}px — 읽기 전용·조회 재시도·선택 변경·편집 복귀·반 격리`, async ({
    page,
  }, info) => {
    await page.setViewportSize({ width, height: 1000 });
    const { classId, centerId } = await enterHome(page);
    const documents = [];
    for (const [date, activity] of [
      ["2026-10-19", "블록놀이"],
      ["2026-10-20", "공놀이"],
    ]) {
      const [routine] = await confirmedDailyLog(page, classId, date, [activity]);
      documents.push(
        await api(page, "/api/documents", "POST", {
          kind: "dailyLog",
          class_id: classId,
          start: date,
          end: date,
          source_ids: [routine.id],
        }),
      );
    }
    const [a, b] = documents;
    await api(page, `/api/centers/${centerId}/classes`, "POST", {
      name: "달님반",
      teacher_name: "다른교사",
      age_min: 4,
      age_max: 4,
      consent_confirmed: true,
    });
    const writes: string[] = [];
    let watching = true;
    page.on("request", (r) => {
      if (
        watching &&
        new URL(r.url()).pathname.startsWith("/api/") &&
        !["GET", "HEAD", "OPTIONS"].includes(r.method())
      )
        writes.push(`${r.method()} ${new URL(r.url()).pathname}`);
    });
    await page.goto("/documents");
    await page.getByRole("complementary", { name: "반 선택" }).getByText("햇살반").click();
    await page.getByRole("button", { name: "보육일지", exact: true }).click();
    const preview = page.getByRole("complementary", { name: "문서 미리보기" });
    await expect(preview).toHaveCount(0);
    const card = (title: string) =>
      page.getByRole("button", { name: new RegExp(title.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")) });
    await page.getByLabel("날짜 선택").fill(a.start);
    let refuse = true;
    info.annotations.push({ type: "expected-http-error", description: `/api/documents/${a.id}` });
    info.annotations.push({
      type: "expected-console-error",
      description: `[API] GET /api/documents/${a.id} → 500 {error: Object}`,
    });
    info.annotations.push({
      type: "expected-console-error",
      description:
        "Failed to load resource: the server responded with a status of 500 (Internal Server Error)",
    });
    await page.route(`**/api/documents/${a.id}`, async (route) => {
      if (refuse && route.request().method() === "GET") {
        refuse = false;
        await route.fulfill({
          status: 500,
          contentType: "application/json",
          body: JSON.stringify({ error: { message: "의도한 미리보기 조회 실패" } }),
        });
      } else await route.continue();
    });
    await card(a.title).click();
    await expect(preview.getByRole("alert")).toContainText("의도한 미리보기 조회 실패");
    await expect(preview.getByRole("button", { name: "편집하기", exact: true })).toHaveCount(0);
    await preview.getByRole("button", { name: "미리보기 다시 시도", exact: true }).click();
    await expect(
      preview.getByRole("heading", { name: a.title, exact: true, level: 2 }),
    ).toBeVisible();
    await expect(preview).toContainText(
      a.sections.find((s: { heading: string }) => s.heading === "사실").body,
    );
    await expect(preview.locator("input,textarea,select")).toHaveCount(0);
    await expect(page.getByRole("textbox", { name: "지원 내용", exact: true })).toHaveCount(0);
    if (width > 760) {
      const left = await page.getByLabel("날짜 선택").boundingBox();
      const right = await preview.boundingBox();
      expect(left!.x + left!.width).toBeLessThanOrEqual(right!.x);
      let release!: () => void;
      const held = new Promise<void>((resolve) => {
        release = resolve;
      });
      let requested!: () => void;
      const arrived = new Promise<void>((resolve) => {
        requested = resolve;
      });
      await page.route(`**/api/documents/${b.id}`, async (route) => {
        const response = await route.fetch();
        requested();
        await held;
        await route.fulfill({ response });
      });
      await page.getByLabel("날짜 선택").fill(b.start);
      await card(b.title).click();
      await arrived;
      await expect(preview.getByRole("status")).toContainText("불러오고");
      await page.getByLabel("날짜 선택").fill(a.start);
      await card(a.title).click();
      await expect(
        preview.getByRole("heading", { name: a.title, exact: true, level: 2 }),
      ).toBeVisible();
      const late = page.waitForResponse((r) => r.url().endsWith(`/api/documents/${b.id}`));
      release();
      await late;
      await expect(
        preview.getByRole("heading", { name: b.title, exact: true, level: 2 }),
      ).toHaveCount(0);
      await page.unroute(`**/api/documents/${b.id}`);
    } else {
      await expect(page.getByLabel("날짜 선택")).toBeHidden();
      await preview.getByRole("button", { name: "목록으로", exact: true }).click();
      await expect(page.getByLabel("날짜 선택")).toHaveValue(a.start);
      await card(a.title).click();
    }
    await expect(
      preview.getByRole("heading", { name: a.title, exact: true, level: 2 }),
    ).toBeVisible();
    expect(writes).toEqual([]);
    await page.screenshot({ path: info.outputPath(`preview-${width}.png`), fullPage: true });
    watching = false;
    await preview.getByRole("button", { name: "편집하기", exact: true }).click();
    const support = "다음 놀이에는 블록을 준비해 함께 길을 만들도록 지원한다.";
    await page.getByRole("textbox", { name: "지원 내용", exact: true }).fill(support);
    await page.getByRole("button", { name: "초안 저장", exact: true }).click();
    await expect(page.getByText("작성 중인 초안을 저장했어요.", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "← 문서 목록으로 돌아가기", exact: true }).click();
    await expect(page.getByLabel("날짜 선택")).toHaveValue(a.start);
    await card(a.title).click();
    await expect(preview).toContainText(support);
    if (width <= 760) await preview.getByRole("button", { name: "목록으로", exact: true }).click();
    await page.getByLabel("날짜 선택").fill(b.start);
    await card(b.title).click();
    await expect(
      preview.getByRole("heading", { name: b.title, exact: true, level: 2 }),
    ).toBeVisible();
    await expect(preview).not.toContainText(support);
    await page.getByRole("complementary", { name: "반 선택" }).getByText("달님반").click();
    await expect(page.getByRole("heading", { name: b.title, exact: true, level: 2 })).toHaveCount(
      0,
    );
    await expect(preview).toHaveCount(0);
    await expect(
      page.getByRole("heading", { name: "문서를 선택해 주세요", exact: true }),
    ).toBeVisible();
    expect(
      (await api(page, `/api/documents/${a.id}`)).sections.find(
        (s: { heading: string }) => s.heading === "지원",
      ).body,
    ).toBe(support);
  });
}

test("관찰 미리보기 — 아동을 바꾸면 이전 아동 본문을 닫고 해당 아동만 표시한다", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  const { classId, childId } = await enterHome(page);
  const other = await api(page, `/api/classes/${classId}/children`, "POST", { name: "라마바" });
  const date = "2026-10-19";
  const docs = [];
  for (const [id, fact] of [
    [childId, "블록을 쌓았다."],
    [other.id, "공을 굴렸다."],
  ] as const) {
    const source = await api(page, "/api/observations", "POST", {
      class_id: classId,
      child_id: id,
      date,
      domain: "자연탐구",
      context: "놀이",
      fact,
    });
    docs.push(
      await api(page, "/api/documents", "POST", {
        kind: "observation",
        class_id: classId,
        child_id: id,
        start: date,
        end: date,
        source_ids: [source.id],
      }),
    );
  }
  await page.goto("/documents");
  await page.getByRole("complementary", { name: "반 선택" }).getByText("햇살반").click();
  await page.getByRole("button", { name: "관찰일지", exact: true }).click();
  const preview = page.getByRole("complementary", { name: "문서 미리보기" });
  for (const [index, name, fact, excluded] of [
    [0, "가나다", "블록을 쌓았다.", "공을 굴렸다."],
    [1, "라마바", "공을 굴렸다.", "블록을 쌓았다."],
  ] as const) {
    await page.getByRole("button", { name, exact: true }).click();
    await expect(preview).toHaveCount(0);
    await page.getByLabel("날짜 선택").fill(date);
    await page
      .getByRole("button", {
        name: new RegExp(docs[index].title.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")),
      })
      .click();
    await expect(
      preview.getByRole("heading", { name: docs[index].title, exact: true, level: 2 }),
    ).toBeVisible();
    await expect(preview).toContainText(name);
    await expect(preview.getByText(fact, { exact: true })).toBeVisible();
    await expect(preview.getByText(excluded, { exact: true })).toHaveCount(0);
    await expect(page.getByRole("textbox", { name: "해석 내용", exact: true })).toHaveCount(0);
  }
});
