import { expect, test, type Page, type TestInfo } from "@playwright/test";
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
  await page.getByRole("link", { name: "로그인하러 가기" }).click();
  await page.getByLabel("이메일").fill(email);
  await page.locator("#auth-password").fill("task2-password-1234");
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  await expect(page).toHaveURL(/\/onboarding\/center$/);
  await page.getByLabel("원명").fill("일과테스트어린이집");
  await page.getByLabel("원장 이름").fill("테스트원장");
  await page.getByLabel("시·도", { exact: true }).selectOption("강원특별자치도");
  await page.getByLabel("시·군·구").selectOption("춘천시");
  await page.getByRole("button", { name: "다음", exact: true }).click();
  await page.getByLabel("반 이름").fill("햇살반");
  await page.getByLabel("만 4세", { exact: true }).check();
  await page.getByLabel("담임 이름").fill("테스트교사");
  await page.getByLabel("이 반 모든 아동의 법정대리인 동의를 받았습니다.").check();
  await page.getByRole("button", { name: "다음", exact: true }).click();
  await page.getByLabel("아동 추가").fill("가나다");
  await page.getByRole("button", { name: "+ 추가", exact: true }).click();
  await page.getByRole("button", { name: "설정 완료", exact: true }).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("link", { name: "오늘 일과 적기" })).toBeVisible();
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
  expect(
    state.network.filter(
      (r) =>
        r.status >= 400 &&
        !(intentional401 && r.status === 401 && r.url.startsWith("/api/routines")),
    ),
  ).toEqual([]);
  expect(state.errors.filter((error) => !(intentional401 && /401/.test(error)))).toEqual([]);
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
    await page.getByRole("link", { name: "오늘 일과 적기" }).click();
    await expect(page).toHaveURL(/\/routines\?date=.*class_id=/);
    await expect(page.getByText("이 날짜의 일과를 불러오는 중이에요…")).toBeVisible();
    release();
    await expect(rows(page)).toHaveCount(5);
    await page.unroute("**/api/routines?**");
    note(page, "A", { blankRows: 5, classId });
  });
  const date = await page.getByLabel("날짜", { exact: true }).inputValue();
  await test.step("B: 7줄을 입력하고 저장·새로고침 후 내용과 시간 확인", async () => {
    await page.getByRole("button", { name: "+ 줄 추가", exact: true }).click();
    await page.getByRole("button", { name: "+ 줄 추가", exact: true }).click();
    for (let i = 0; i < 7; i++) {
      const row = rows(page).nth(i);
      await row.getByLabel("일과 이름").fill(`일과${i + 1}`);
      await row.getByLabel("시작", { exact: true }).fill(`${String(8 + i).padStart(2, "0")}:00`);
      await row.getByLabel("종료", { exact: true }).fill(`${String(9 + i).padStart(2, "0")}:00`);
      await row.getByLabel("활동계획").fill("놀이 자료를 준비한다.");
      if (i < 6) await row.getByLabel("활동실행").fill("블록을 쌓고 길을 만들었다.");
    }
    await saved(page);
    await page.reload();
    await expect(rows(page)).toHaveCount(7);
    for (let i = 0; i < 7; i++) {
      await expect(rows(page).nth(i).getByLabel("일과 이름")).toHaveValue(`일과${i + 1}`);
      await expect(rows(page).nth(i).getByLabel("시작", { exact: true })).toHaveValue(
        `${String(8 + i).padStart(2, "0")}:00`,
      );
      await expect(rows(page).nth(i).getByLabel("종료", { exact: true })).toHaveValue(
        `${String(9 + i).padStart(2, "0")}:00`,
      );
      await expect(rows(page).nth(i).getByLabel("활동계획")).toHaveValue("놀이 자료를 준비한다.");
      await expect(rows(page).nth(i).getByLabel("활동실행")).toHaveValue(
        i < 6 ? "블록을 쌓고 길을 만들었다." : "",
      );
    }
    note(page, "B", await dayRows(page, classId, date));
  });
  await test.step("C: 첫 줄을 네 번째로 드래그하고 저장·재조회 순서 비교", async () => {
    // 두 줄이 동시에 보이게 한 뒤 실제 마우스로 끈다. 자동 스크롤이 드래그 시작을 가리지 않는다.
    await page.setViewportSize({ width: 1440, height: 1800 });
    const source = page.getByRole("button", { name: "1번째 줄 끌어서 옮기기", exact: true });
    const target = page.getByRole("button", { name: "4번째 줄 끌어서 옮기기", exact: true });
    await source.scrollIntoViewIfNeeded();
    await source.dragTo(target);
    const expected = ["일과2", "일과3", "일과4", "일과1", "일과5", "일과6", "일과7"];
    await expectNames(page, expected);
    await saved(page);
    await page.reload();
    await expectNames(page, expected);
    expect((await dayRows(page, classId, date)).map((r) => r.name)).toEqual(expected);
    note(page, "C", expected);
  });
  let documentId: number;
  await test.step("G: 저장 전 입력을 자동 저장하고 S-J2에서 고른 순서대로 실제 초안 생성", async () => {
    await rows(page).nth(0).getByLabel("일과 이름").fill("수정한 일과2");
    await page.getByRole("button", { name: "오늘 일지 만들기 →", exact: true }).click();
    await expect(page).toHaveURL(`/documents?kind=dailyLog&class_id=${classId}&date=${date}`);
    await expect(page.getByRole("combobox", { name: "문서 종류" })).toHaveValue("dailyLog");
    await expect(page.getByLabel("날짜", { exact: true })).toHaveValue(date);
    const sourceRows = await dayRows(page, classId, date);
    expect(sourceRows[0].name).toBe("수정한 일과2");
    await page.getByRole("link", { name: "새 일과 기록 입력 →" }).click();
    await expect(page).toHaveURL(`/routines?date=${date}&class_id=${classId}`);
    await expect(page.getByRole("combobox", { name: "반", exact: true })).toHaveValue(
      String(classId),
    );
    await page.goBack();
    await expect(page).toHaveURL(/\/documents\?/);
    const candidates = page
      .getByRole("group", { name: "문서에 사용할 일과" })
      .getByRole("checkbox");
    await expect(candidates).toHaveCount(7);
    await expect(candidates.nth(6)).toBeDisabled();
    await candidates.nth(2).check();
    await candidates.nth(0).check();
    const response = page.waitForResponse(
      (r) => r.url().endsWith("/api/documents") && r.request().method() === "POST",
    );
    let release!: () => void;
    const paused = new Promise<void>((resolve) => {
      release = resolve;
    });
    await page.route("**/api/documents", async (route) => {
      if (route.request().method() === "POST") await paused;
      await route.continue();
    });
    await page.getByRole("button", { name: "초안 만들기", exact: true }).click();
    await expect(page.getByText("보육일지 초안을 작성하고 있어요. 30초쯤 걸려요.")).toBeVisible();
    await expect(page.getByRole("button", { name: "초안 작성 중…", exact: true })).toBeDisabled();
    release();
    const generated = await response;
    await page.unroute("**/api/documents");
    expect(generated.status()).toBe(201);
    expect(generated.request().postDataJSON().source_ids).toEqual([
      sourceRows[2].id,
      sourceRows[0].id,
    ]);
    const doc = await generated.json();
    documentId = doc.id;
    expect(doc.sources.map((source: { id: number }) => source.id)).toEqual([
      sourceRows[2].id,
      sourceRows[0].id,
    ]);
    await expect(
      page.getByRole("heading", { name: doc.title, exact: true, level: 2 }),
    ).toBeVisible();
    await expect(
      page.getByText(doc.sections.find((s: { heading: string }) => s.heading === "사실").body, {
        exact: true,
      }),
    ).toBeVisible();
    note(page, "G", { documentId, selectedIds: doc.sources.map((s: { id: number }) => s.id) });
  });
  await test.step("H: 브라우저에서 문서를 확정하고 두 근거 수정은 1건으로 집계", async () => {
    await page.getByRole("button", { name: /기본 항목 검사|AI 검증하기/ }).click();
    await page.getByRole("checkbox", { name: /사실이 원본 기록과 일치/ }).check();
    await page.getByRole("checkbox", { name: /해석이 기록의 근거를/ }).check();
    await page.getByRole("checkbox", { name: /지원에 구체적인 교사/ }).check();
    await page.getByRole("button", { name: "검토 완료 · 문서 확정", exact: true }).click();
    await expect(page.getByRole("button", { name: "확정 취소", exact: true })).toBeVisible();
    expect(dbDocument(documentId!)).toEqual({ id: documentId!, status: "CONFIRMED", stale: false });
    await page.getByRole("link", { name: "우리 반", exact: true }).click();
    await page.getByRole("link", { name: "오늘 일과 적기" }).click();
    await expect(rows(page)).toHaveCount(7);
    await rows(page).nth(0).getByLabel("활동실행").fill("블록 길을 더 길게 이어 붙였다.");
    await rows(page).nth(2).getByLabel("활동실행").fill("길 위에 자동차를 올려 굴렸다.");
    await saved(page, false);
    await expect(
      page.getByText(/이 일과를 쓴 보육일지 1건이 다시 검토 대상이 되었어요/),
    ).toBeVisible();
    const db = dbDocument(documentId!);
    expect(db.stale).toBe(true);
    note(page, "H", db);
    await rows(page).nth(0).getByLabel("활동계획").fill("계획만 고친다.");
    await saved(page);
    await expect(page.getByText(/다시 검토 대상이 되었어요|이미 재검토 대상인/)).toHaveCount(0);
    await page.screenshot({ path: info.outputPath("A-G-H-routines.png"), fullPage: true });
  });
});

test("S-J2 빈 상태 — 활동실행 없는 저장 줄에서 실제 입력 링크로 돌아간다", async ({ page }) => {
  const { classId } = await enterHome(page);
  await page.getByRole("link", { name: "오늘 일과 적기" }).click();
  await expect(rows(page)).toHaveCount(5);
  const date = await page.getByLabel("날짜", { exact: true }).inputValue();
  await rows(page).nth(0).getByLabel("일과 이름").fill("시간과 이름만 있는 일과");
  await saved(page);
  await expect(
    page.getByRole("button", { name: "오늘 일지 만들기 →", exact: true }),
  ).toBeDisabled();
  await page.getByRole("link", { name: "문서 보관함", exact: true }).click();
  await page.getByRole("button", { name: "＋ 기록으로 문서 만들기", exact: true }).click();
  await page.getByRole("combobox", { name: "문서 종류" }).selectOption("dailyLog");
  await page.getByRole("combobox", { name: "담당 반" }).selectOption({ label: "햇살반" });
  await expect(page.getByRole("heading", { name: "선택할 수 있는 일과가 없어요" })).toBeVisible();
  await expect(page.getByText("일과 1줄이 있지만 활동실행이 모두 비어 있어요.")).toBeVisible();
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
  await page.getByRole("link", { name: "오늘 일과 적기" }).click();
  await expect(rows(page)).toHaveCount(5);
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
  await page.getByRole("button", { name: "어제 일과 불러오기", exact: true }).click();
  await expect(rows(page)).toHaveCount(1);
  await expect(rows(page).nth(0).getByLabel("일과 이름")).toHaveValue("어제 일과");
  await expect(rows(page).nth(0).getByLabel("시작", { exact: true })).toHaveValue("09:00");
  await expect(rows(page).nth(0).getByLabel("활동계획")).toHaveValue("");
  await expect(rows(page).nth(0).getByLabel("활동실행")).toHaveValue("");
  expect(await dayRows(page, classId, date)).toEqual([]);
  note(page, "D", { timeAndNameOnly: true, noWrite: true });
  await rows(page).nth(0).getByLabel("일과 이름").fill("");
  await rows(page).nth(0).getByLabel("활동실행").fill("오늘 작성 중인 실행");
  await page.getByRole("button", { name: "오늘 일지 만들기 →", exact: true }).click();
  await expect(rows(page).nth(0).getByText("일과 이름을 적어 주세요.")).toBeVisible();
  await expect(rows(page).nth(0).getByLabel("활동실행")).toHaveValue("오늘 작성 중인 실행");
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
  await expect(rows(page).nth(0).getByLabel("활동실행")).toHaveValue("오늘 작성 중인 실행");
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
  await rows(page).nth(0).getByRole("button", { name: "줄 지우기", exact: true }).click();
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
  await page.getByRole("link", { name: "오늘 일과 적기" }).click();
  await expect(rows(page)).toHaveCount(5);
  const date = await page.getByLabel("날짜", { exact: true }).inputValue();
  await rows(page).nth(0).getByLabel("일과 이름").fill("햇살반 일과");
  await rows(page).nth(0).getByLabel("활동실행").fill("햇살반에서 블록을 쌓았다.");
  await saved(page);
  await page.getByRole("combobox", { name: "반", exact: true }).selectOption(String(other.id));
  await expect(rows(page)).toHaveCount(5);
  await expectNames(page, ["", "", "", "", ""]);
  await rows(page).nth(0).getByLabel("일과 이름").fill("달님반 일과");
  await rows(page).nth(0).getByLabel("활동실행").fill("달님반에서 공을 굴렸다.");
  await saved(page);
  await page.getByRole("button", { name: "오늘 일지 만들기 →", exact: true }).click();
  await expect(page).toHaveURL(`/documents?kind=dailyLog&class_id=${other.id}&date=${date}`);
  await expect(page.getByRole("combobox", { name: "담당 반" })).toHaveValue(
    (await page
      .getByRole("combobox", { name: "담당 반" })
      .locator("option", { hasText: "달님반" })
      .getAttribute("value")) ?? "",
  );
  await expect(page.getByRole("group", { name: "문서에 사용할 일과" })).toContainText(
    "달님반 일과",
  );
  await page.getByRole("link", { name: "새 일과 기록 입력 →" }).click();
  await page.getByRole("combobox", { name: "반", exact: true }).selectOption(String(classId));
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
  await page.getByRole("link", { name: "관찰 기록", exact: true }).click();
  // 단일 반 온보딩은 담당 반을 묻지 않는다. 주 반이 없는 상태에서는 전체 조회 없이 선택을 기다린다.
  await page.getByRole("combobox", { name: "담당 반" }).selectOption({ label: "햇살반" });
  await expect(page.getByText("햇살반 관찰 사실", { exact: true })).toBeVisible();
  await expect(page.getByText("달님반 관찰 사실", { exact: true })).toHaveCount(0);
  await page.getByRole("combobox", { name: "담당 반" }).selectOption({ label: "달님반" });
  await expect(page.getByText("달님반 관찰 사실", { exact: true })).toBeVisible();
  await expect(page.getByText("햇살반 관찰 사실", { exact: true })).toHaveCount(0);
  const write = page.getByRole("link", { name: /일과 기록/ }).first();
  await expect(write).toHaveAttribute("href", `/routines?date=${date}&class_id=${other.id}`);
  await write.click();
  await expect(page.getByRole("combobox", { name: "반", exact: true })).toHaveValue(
    String(other.id),
  );
  await page.getByLabel("날짜", { exact: true }).fill("2026-10-16");
  await expect(rows(page)).toHaveCount(5);
  await rows(page).nth(0).getByLabel("일과 이름").fill("지난 날짜 일과");
  await rows(page).nth(0).getByLabel("활동실행").fill("지난 날짜에 길을 만들었다.");
  await page.getByRole("button", { name: "오늘 일지 만들기 →", exact: true }).click();
  await expect(page).toHaveURL(`/documents?kind=dailyLog&class_id=${other.id}&date=2026-10-16`);
  await expect(page.getByLabel("날짜", { exact: true })).toHaveValue("2026-10-16");
  await page.getByRole("link", { name: "새 일과 기록 입력 →" }).click();
  await expect(page).toHaveURL(`/routines?date=2026-10-16&class_id=${other.id}`);
  await expect(rows(page).nth(0).getByLabel("일과 이름")).toHaveValue("지난 날짜 일과");
  note(page, "I S-J1/S-J2 scope", {
    classA: classId,
    classB: other.id,
    preservedDate: "2026-10-16",
  });
  await page.getByRole("link", { name: "기록 모아보기", exact: true }).click();
  await expect(page).toHaveURL(/\/quick-records$/);
  await expect(
    page.getByRole("heading", { name: "기록 모아보기", exact: true, level: 1 }),
  ).toBeVisible();
  await page.getByRole("combobox", { name: "반", exact: true }).selectOption({ label: "달님반" });
  await expect(page.getByText("달님반 관찰 사실", { exact: true })).toBeVisible();
  await expect(page.getByText("햇살반 관찰 사실", { exact: true })).toHaveCount(0);
  await page.screenshot({ path: info.outputPath("I-quick-records-isolation.png"), fullPage: true });
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
  note(page, "I quick-records entry", {
    classA: classId,
    classB: other.id,
    preservedDate: previousDate,
  });
  await page.screenshot({ path: info.outputPath("I-class-isolation.png"), fullPage: true });
});
