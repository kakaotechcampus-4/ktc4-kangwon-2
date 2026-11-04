import { test } from "node:test";
import assert from "node:assert/strict";
import { registerHooks } from "node:module";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
registerHooks({
  resolve(spec, ctx, next) {
    if (spec.startsWith(".") && ctx.parentURL) {
      const u = new URL(spec + ".ts", ctx.parentURL);
      if (existsSync(fileURLToPath(u))) return { url: u.href, shortCircuit: true };
    }
    return next(spec, ctx);
  },
});
const { setupServer } = await import("msw/node");
const { handlers } = await import("../msw/handlers.ts");
const { resetTestData, commit } = await import("../msw/data/store.ts");
const { createCenter } = await import("../lib/api/centers.ts");
const {
  createClass,
  getClasses,
  getArchiveSummary,
  requestClassAccess,
  getReceivedRequests,
  decideAccessRequest,
} = await import("../lib/api/classes.ts");
const { createAnnualPlan } = await import("../lib/api/plans.ts");
const server = setupServer(...handlers);

// 목업도 서버 계약(docs/api-spec.md §2-2 · backend/app/features/class_access/router.py)대로 답한다.
test("열람 요청 목업 — 요약 · 요청 · 받은 요청 · 결정이 서버와 같은 모양 · 오류로 답한다", async () => {
  resetTestData();
  server.listen({ onUnhandledRequest: "error" });
  const patched = globalThis.fetch;
  globalThis.fetch = (url, options) => patched(new URL(url, "http://localhost").href, options);
  const fails = (status, code, fields) => (e) =>
    e.status === status &&
    e.body.error.code === code &&
    JSON.stringify(e.body.error.fields) === JSON.stringify(fields);
  try {
    const center = await createCenter({
      name: "검증 원",
      director_name: "원장",
      region_sido: "강원특별자치도",
      region_sigungu: "춘천시",
    });
    const mine = await createClass(center.id, {
      name: "햇살반",
      teacher_name: "교사",
      age_min: 4,
      age_max: 5,
      child_count: null,
    });

    // 목업 반은 모두 이 계정이 만든 반이다.
    const { items } = await getClasses(center.id);
    assert.deepEqual(
      items.map((c) => c.my_access),
      ["OWNER"],
    );

    // 요약 — 자료가 없으면 빈 배열. 연간 하나를 만들면 학년도 3월 1일 ~ 이듬해 2월 말.
    assert.deepEqual(await getArchiveSummary(mine.id), { items: [] });
    const annual = await createAnnualPlan({
      class_id: mine.id,
      form_id: null,
      format: "MONTHLY_THEME",
    });
    commit((db) => {
      // 월간 · 놀이 중심 월간도 `monthly` 로 센다. 목업 자료 모양 중 요약이 읽는 칸만 넣는다.
      db.monthlyPlans.push({
        id: 900,
        class_id: mine.id,
        target_month: "2027-02",
        status: "CONFIRMED",
      });
      db.playMonthlyPlans.push({
        id: 901,
        class_id: mine.id,
        target_month: "2026-04",
        status: "DRAFT",
      });
      db.weeklyPlans.push({
        id: 902,
        class_id: mine.id,
        status: "DRAFT",
        week_period: { label: "4월 1주", start_date: "2026-03-30", end_date: "2026-04-03" },
      });
    });
    const summary = await getArchiveSummary(mine.id);
    const year = annual.school_year;
    assert.deepEqual(summary.items, [
      { kind: "monthly", start: "2027-02-01", end: "2027-02-28", status: "CONFIRMED" },
      { kind: "monthly", start: "2026-04-01", end: "2026-04-30", status: "DRAFT" },
      { kind: "weekly", start: "2026-03-30", end: "2026-04-03", status: "DRAFT" },
      {
        kind: "annual",
        start: `${year}-03-01`,
        end: `${year + 1}-02-${new Date(Date.UTC(year + 1, 2, 0)).getUTCDate()}`,
        status: annual.status,
      },
    ]);
    // 제목 · 아이 이름 · id 는 없다.
    for (const item of summary.items)
      assert.deepEqual(Object.keys(item).sort(), ["end", "kind", "start", "status"]);

    // 없는 반 · 다른 원 반은 404 ["class_id"].
    await assert.rejects(getArchiveSummary(999), fails(404, "NOT_FOUND", ["class_id"]));
    await assert.rejects(requestClassAccess(999), fails(404, "NOT_FOUND", ["class_id"]));
    // 내 반에 요청하면 서버처럼 409 ALREADY_EXISTS ["class_id"].
    await assert.rejects(requestClassAccess(mine.id), fails(409, "ALREADY_EXISTS", ["class_id"]));

    // 받은 요청 — 다른 교사가 보낸 것이라 테스트가 넣는다. PENDING 먼저, 그 안에서 updated_at 내림차순.
    assert.deepEqual(await getReceivedRequests(), { items: [] });
    const row = (id, status, updated_at) => ({
      id,
      class_id: mine.id,
      class_name: "햇살반",
      requester_name: "이선생",
      status,
      created_at: "2026-11-01T00:00:00Z",
      updated_at,
    });
    commit((db) => {
      db.accessRequests.push(
        row(1, "APPROVED", "2026-11-04T03:00:00Z"),
        row(2, "PENDING", "2026-11-02T00:00:00Z"),
        row(3, "PENDING", "2026-11-03T00:00:00Z"),
        { ...row(4, "PENDING", "2026-11-04T00:00:00Z"), class_id: 999 }, // 내 반이 아니다
      );
    });
    assert.deepEqual(
      (await getReceivedRequests()).items.map((r) => [r.id, r.status]),
      [
        [3, "PENDING"],
        [2, "PENDING"],
        [1, "APPROVED"],
      ],
    );

    // 결정 — PENDING → APPROVED · REJECTED, APPROVED → REVOKED. 그 밖은 409 STALE_WRITE ["status"].
    const approved = await decideAccessRequest(3, "APPROVED");
    assert.equal(approved.status, "APPROVED");
    assert.equal(approved.class_name, "햇살반");
    assert.equal(approved.requester_name, "이선생");
    assert.match(approved.updated_at, /Z$/);
    await assert.rejects(decideAccessRequest(3, "APPROVED"), fails(409, "STALE_WRITE", ["status"]));
    await assert.rejects(decideAccessRequest(3, "REJECTED"), fails(409, "STALE_WRITE", ["status"]));
    assert.equal((await decideAccessRequest(3, "REVOKED")).status, "REVOKED");
    await assert.rejects(decideAccessRequest(3, "REVOKED"), fails(409, "STALE_WRITE", ["status"]));
    assert.equal((await decideAccessRequest(2, "REJECTED")).status, "REJECTED");
    // 없는 요청 · 내 반 요청이 아니면 404 ["id"].
    await assert.rejects(decideAccessRequest(4, "APPROVED"), fails(404, "NOT_FOUND", ["id"]));
    await assert.rejects(decideAccessRequest(77, "APPROVED"), fails(404, "NOT_FOUND", ["id"]));

    // 본문 검사가 먼저다 — PENDING 으로 되돌리기 · 다른 칸은 422.
    const patch = (b) =>
      fetch("/api/access-requests/1", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(b),
      }).then(async (r) => [r.status, (await r.json()).error]);
    assert.deepEqual(await patch({ status: "PENDING" }), [
      422,
      { code: "VALIDATION_FAILED", message: "입력값을 확인해주세요.", fields: ["status"] },
    ]);
    assert.deepEqual((await patch({ status: "REVOKED", note: "x" }))[1].fields, ["note"]);
    assert.equal((await patch({ status: "REVOKED", note: "x" }))[0], 422);
    // 422 는 아무것도 바꾸지 않는다.
    assert.equal((await getReceivedRequests()).items.find((r) => r.id === 1).status, "APPROVED");
  } finally {
    globalThis.fetch = patched;
    server.close();
  }
});
