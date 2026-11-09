/**
 * 승인받은 남의 반 문서 목록 (lib/workspace/approved-rows.ts · ClassAccessPanels ApprovedList).
 *
 * 놀이 중심 월간(v2)은 기존 월간 목록에 없다. 따로 부르지 않으면 그것만 있는 반이
 * 「아직 만든 문서가 없어요」로 보인다(#373). 남의 반이라 편집으로 가는 길은 없어야 한다.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { registerHooks } from "node:module";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";

const ROOT = new URL("../", import.meta.url);
registerHooks({
  resolve(spec, ctx, next) {
    if (spec.startsWith("@/")) {
      const base = new URL(spec.slice(2), ROOT);
      for (const candidate of [base.href, base.href + ".ts", base.href + ".tsx"]) {
        if (existsSync(fileURLToPath(candidate))) return { url: candidate, shortCircuit: true };
      }
    }
    if (spec.startsWith(".") && ctx.parentURL) {
      const u = new URL(spec + ".ts", ctx.parentURL);
      if (existsSync(fileURLToPath(u))) return { url: u.href, shortCircuit: true };
    }
    return next(spec, ctx);
  },
});

const { setupServer } = await import("msw/node");
const { http, HttpResponse } = await import("msw");
const { fixtureAccount, fixtureKey, fixtureSession } = await import("./auth-fixture.mjs");
const { loadApprovedRows } = await import("../lib/workspace/approved-rows.ts");

const server = setupServer();
server.listen({ onUnhandledRequest: "error" });
const realFetch = globalThis.fetch;
globalThis.fetch = (url, options) => realFetch(new URL(url, "http://localhost").href, options);

const values = new Map([[fixtureKey, fixtureAccount]]);
globalThis.localStorage = {
  getItem: (k) => values.get(k) ?? null,
  setItem: (k, v) => values.set(k, v),
  removeItem: (k) => values.delete(k),
};
const session = fixtureSession();
globalThis.sessionStorage = {
  getItem: (k) => session.getItem(k),
  setItem: () => {},
  removeItem: () => {},
};
globalThis.window = Object.assign(new EventTarget(), {
  localStorage: globalThis.localStorage,
  sessionStorage: globalThis.sessionStorage,
  location: { search: "" },
});

test("승인받은 반에 놀이 중심 월간만 있으면 그 문서가 목록에 나오고 편집 길은 없다", async () => {
  const asked = [];
  const empty =
    (name) =>
    ({ request }) => {
      asked.push(`${name} ${new URL(request.url).searchParams.get("class_id")}`);
      return HttpResponse.json({ items: [] });
    };
  server.use(
    http.get("*/api/documents", empty("documents")),
    http.get("*/api/plans/annual", empty("annual")),
    http.get("*/api/plans/monthly", empty("monthly")),
    http.get("*/api/plans/weekly", empty("weekly")),
    http.get("*/api/plans/monthly/play", ({ request }) => {
      asked.push(`play ${new URL(request.url).searchParams.get("class_id")}`);
      return HttpResponse.json({
        items: [
          {
            id: 31,
            class_id: 7,
            school_year: 2026,
            month: 10,
            target_month: "2026-10",
            status: "CONFIRMED",
            revision: 3,
            created_at: "2026-10-01T00:00:00Z",
            confirmed_at: "2026-10-02T00:00:00Z",
          },
        ],
      });
    }),
  );

  const { rows, failed } = await loadApprovedRows({ id: 7, name: "하늘반" });

  assert.deepEqual(failed, []);
  assert.ok(asked.includes("play 7"), "놀이 중심 월간도 그 반을 짚어 부른다");
  assert.equal(rows.length, 1);
  const [row] = rows;
  assert.equal(row.confirmed, true);
  assert.equal(row.name, "월간 계획안");
  assert.ok("plan" in row.view);
  // 미리보기는 놀이형 읽기 경로(getPlayMonthly)로 간다.
  assert.equal(row.view.plan.play, true);
  assert.equal(row.view.plan.id, 31);
  // 편집 화면 주소가 비어 있어야 미리보기가 「문서 열기」 · 「수정하기」를 그리지 않는다.
  assert.equal(row.view.plan.href, "");
  assert.equal(typeof row.hwp, "function", "확정본은 내려받기가 있다");
});

test("놀이 월간 내려받기는 놀이형 경로를 부른다", async () => {
  let hit = "";
  server.use(
    http.get("*/api/documents", () => HttpResponse.json({ items: [] })),
    http.get("*/api/plans/annual", () => HttpResponse.json({ items: [] })),
    http.get("*/api/plans/monthly", () => HttpResponse.json({ items: [] })),
    http.get("*/api/plans/weekly", () => HttpResponse.json({ items: [] })),
    http.get("*/api/plans/monthly/play", () =>
      HttpResponse.json({
        items: [
          {
            id: 31,
            class_id: 7,
            school_year: 2026,
            month: 10,
            target_month: "2026-10",
            status: "CONFIRMED",
            revision: 3,
            created_at: "2026-10-01T00:00:00Z",
            confirmed_at: null,
          },
        ],
      }),
    ),
    http.get("*/api/plans/monthly/play/:id/export/hwp", ({ request }) => {
      hit = new URL(request.url).pathname;
      return new HttpResponse("x", { status: 500 });
    }),
  );
  const { rows } = await loadApprovedRows({ id: 7, name: "하늘반" });
  await rows[0].hwp().catch(() => {});
  assert.equal(hit, "/api/plans/monthly/play/31/export/hwp");
});
