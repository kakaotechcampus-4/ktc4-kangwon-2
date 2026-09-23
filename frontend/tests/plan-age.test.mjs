import assert from "node:assert/strict";
import { test } from "node:test";
import { registerHooks } from "node:module";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";

// Resolve the extensionless local imports used by the Next.js TypeScript source.
registerHooks({
  resolve(spec, ctx, next) {
    if (spec.startsWith(".") && ctx.parentURL) {
      const url = new URL(spec + ".ts", ctx.parentURL);
      if (existsSync(fileURLToPath(url))) return { url: url.href, shortCircuit: true };
    }
    return next(spec, ctx);
  },
});
const { validAIInput } = await import("../lib/workspace/api-validation.ts");
const { templatePlan } = await import("../lib/workspace/plans.ts");
const { ageSelectionLabel } = await import("../lib/onboarding/types.ts");

const COMBOS = [[3], [4], [5], [3, 4], [4, 5], [3, 5], [3, 4, 5]];
const PERIOD = {
  annual: { year: 2027 },
  monthly: { month: 3 },
  weekly: { month: 3, week: 1 },
  daily: { date: "2027-03-02" },
};
const planPayload = (extra) => ({
  type: "annual",
  age: "mixed",
  memo: "",
  period: PERIOD,
  ...extra,
});

test("plan AI 요청은 선택한 연령 조합을 그대로 싣고, 잘못된 값만 거절한다", () => {
  for (const ages of COMBOS)
    assert.equal(validAIInput("plan", planPayload({ ages })), true, JSON.stringify(ages));
  // 단일 연령 화면처럼 ages 가 없던 기존 요청도 그대로 통과한다.
  assert.equal(validAIInput("plan", planPayload({ age: "4" })), true);
  for (const ages of [[], [2], [6], [3, 3], [3, 4, 5, 5], ["3"], "mixed", null, {}])
    assert.equal(validAIInput("plan", planPayload({ ages })), false, JSON.stringify(ages));
});

test("[3,5] 를 골라도 계획안 본문은 범위로 적는다", () => {
  // 서버에 age_min=3 · age_max=5 로 저장되므로 본문도 같은 범위여야 한다.
  // 떨어진 연령을 가진 반은 실측 369건 중 0건이다 (docs/PRD.md 「연령 표기」).
  const label = ageSelectionLabel([3, 5]);
  assert.equal(label, "만 3~5세반");
  const plan = templatePlan("annual", "mixed", PERIOD, "", undefined, label);
  assert.ok(plan.rows.every((row) => row.detail.includes("만 3~5세반")));
  assert.ok(plan.rows.every((row) => !row.detail.includes("혼합반")));
  const withTemplate = templatePlan(
    "annual",
    "mixed",
    PERIOD,
    "",
    { headings: ["대상 연령", "주제"], style: "" },
    label,
  );
  assert.ok(withTemplate.rows.every((row) => row.detail.includes("대상 연령: 만 3~5세반")));
  // 라벨이 없는 기존 호출은 종전 AgeGroup 표기를 유지한다.
  assert.ok(templatePlan("annual", "mixed", PERIOD, "").rows[0].detail.includes("혼합반"));
  assert.ok(templatePlan("annual", "4", PERIOD, "").rows[0].detail.includes("만 4세"));
});

test("연령 표기는 범위다 — 저장되는 값과 같아야 한다", () => {
  assert.deepEqual(
    COMBOS.map((ages) => ageSelectionLabel(ages)),
    ["만 3세반", "만 4세반", "만 5세반", "만 3~4세반", "만 4~5세반", "만 3~5세반", "만 3~5세반"],
  );
});
