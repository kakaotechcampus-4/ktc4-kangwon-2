// 목업 모드에서 아이별 기록이 안 열렸다 — GET /api/classes/{id}/children/tracking 목업이 없어
// HTML 404 가 왔다(점검 X-E1). 목업은 이 화면에서 적은 관찰 기록을 아이마다 센다(api-spec §2-1).
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
const { observationHandlers } = await import("../msw/observationHandlers.ts");
const { resetTestData } = await import("../msw/data/store.ts");
const { createCenter } = await import("../lib/api/centers.ts");
const { createClass } = await import("../lib/api/classes.ts");
const { createChild, getChildTracking } = await import("../lib/api/children.ts");
const { createObservation } = await import("../lib/api/observations.ts");
const server = setupServer(...observationHandlers, ...handlers);

test("목업 — 아이별 기록 수를 반 명단 순서로, 기록 없는 아이도 0 으로 센다", async () => {
  resetTestData();
  server.listen({ onUnhandledRequest: "error" });
  const patched = globalThis.fetch;
  globalThis.fetch = (url, options) => patched(new URL(url, "http://localhost").href, options);
  try {
    const center = await createCenter({
      name: "검증 원",
      director_name: "원장",
      region_sido: "강원특별자치도",
      region_sigungu: "춘천시",
    });
    const klass = await createClass(center.id, {
      name: "햇님반",
      teacher_name: "교사",
      age_min: 3,
      age_max: 3,
      child_count: null,
      consent_confirmed: true,
    });
    const a = await createChild(klass.id, { name: "가상도윤" });
    const b = await createChild(klass.id, { name: "가상하람" });
    for (const domain of ["자연탐구", "자연탐구", "의사소통"])
      await createObservation({
        class_id: klass.id,
        child_id: a.id,
        date: "2026-11-09",
        domain,
        context: "",
        fact: "도토리를 세었다.",
      });
    const { items } = await getChildTracking(klass.id);
    assert.deepEqual(
      items.map((i) => [i.name, i.total, i.last_date]),
      [
        ["가상도윤", 3, "2026-11-09"],
        ["가상하람", 0, null],
      ],
    );
    assert.equal(items[0].by_domain["자연탐구"], 2);
    assert.equal(items[0].by_domain["신체운동·건강"], 0, "원이 쓰는 영역은 0 이어도 다 담는다");
    assert.equal(items[1].child_id, b.id);
  } finally {
    globalThis.fetch = patched;
    server.close();
  }
});
