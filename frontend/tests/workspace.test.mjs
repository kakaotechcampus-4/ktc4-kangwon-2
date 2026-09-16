import assert from "node:assert/strict";
import { test } from "node:test";
import { registerHooks } from "node:module";
import { fixtureSession, fixtureKey, fixtureAccount } from "./auth-fixture.mjs";
registerHooks({
  resolve(specifier, context, nextResolve) {
    if (specifier === "../auth/demo-session")
      return nextResolve("../auth/demo-session.ts", context);
    if (
      specifier === "../plan-generator/types" &&
      context.parentURL?.endsWith("/workspace/plans.ts")
    )
      return nextResolve("../plan-generator/types.ts", context);
    if (specifier === "./model" && context.parentURL?.endsWith("/workspace/store.ts"))
      return nextResolve("./model.ts", context);
    if (specifier === "./account-store") return nextResolve("./account-store.ts", context);
    return nextResolve(specifier, context);
  },
});
const { templatePlan, planPeriod } = await import("../lib/workspace/plans.ts");
const { parseWorkspace, updateWorkspace, readWorkspace } =
  await import("../lib/workspace/store.ts");
import {
  validateDocument,
  compareEvidence,
  invalidateDependents,
  analyzeText,
  validPeriod,
  assertDocumentUnchanged,
  isSavedDocument,
} from "../lib/workspace/model.ts";

const observation = {
  id: "r1",
  classId: "c1",
  childId: "child1",
  date: "2026-09-11",
  fact: "블록 세 개를 쌓고 더 높이 만들겠다고 말했다.",
};
const source = {
  id: "r1",
  classId: "c1",
  childId: "child1",
  date: observation.date,
  text: observation.fact,
};
function document(overrides = {}) {
  return {
    id: "d1",
    kind: "observation",
    classId: "c1",
    childId: "child1",
    start: "2026-09-11",
    end: "2026-09-11",
    status: "confirmed",
    sources: [source],
    sections: [
      { heading: "사실", body: source.text, sourceIds: [source.id] },
      {
        heading: "해석",
        body: "더 높이 쌓겠다는 발언에서 블록 높이에 관심을 보인 것으로 해석할 수 있다.",
        sourceIds: [source.id],
      },
      {
        heading: "지원",
        body: "다음 자유놀이에 크기가 다른 블록을 제공하고 어떤 받침을 선택하는지 관찰할 예정이다.",
        sourceIds: [source.id],
      },
    ],
    ...overrides,
  };
}
test("fabricated facts and missing sources cannot pass", () => {
  const doc = document();
  assert.deepEqual(validateDocument(doc), []);
  const changed = structuredClone(doc);
  changed.sections[0].body += " 친구를 도와주었다.";
  assert.ok(validateDocument(changed).some((s) => s.includes("정확히 일치")));
  assert.ok(validateDocument({ ...doc, sources: [] }).some((s) => s.includes("원본 기록")));
});
test("empty or generic support and fabricated reference ids are rejected", () => {
  const doc = document();
  doc.sections[2].body = "잘 지원하겠다.";
  assert.ok(validateDocument(doc).some((s) => s.includes("구체적으로")));
  doc.sections[1].sourceIds = ["made-up"];
  assert.ok(validateDocument(doc).some((s) => s.includes("근거 기록")));
});
test("invalid and out-of-period observations are rejected", () => {
  assert.equal(validPeriod("2026-02-30", "2026-03-01"), false);
  assert.equal(validPeriod("2026-09-12", "2026-09-11"), false);
  assert.ok(
    validateDocument(document({ start: "2026-09-12", end: "2026-09-13" })).some((s) =>
      s.includes("기간 밖"),
    ),
  );
});
test("evidence isolates class, child, confirmed status and dates", () => {
  const doc = document();
  const others = [
    document({ id: "ok", kind: "dailyLog" }),
    document({ id: "other-class", classId: "c2", kind: "dailyLog" }),
    document({ id: "other-child", childId: "child2", kind: "dailyLog" }),
    document({ id: "draft", status: "draft", kind: "dailyLog" }),
    document({ id: "old", start: "2026-08-01", end: "2026-08-31", kind: "dailyLog" }),
  ];
  const result = compareEvidence(doc, others, [observation]);
  assert.deepEqual(
    result.matches.map((d) => d.id),
    ["ok"],
  );
  assert.equal(result.linked[0].state, "일치");
});
test("changes in original facts and source-document status trigger re-review", () => {
  assert.equal(
    compareEvidence(document(), [], [{ ...observation, fact: "수정된 관찰" }]).linked[0].state,
    "원본 변경 · 재검토",
  );
  const daily = document({ id: "daily", kind: "dailyLog", status: "draft" });
  const weekly = document({ kind: "weeklyLog", sources: [{ ...source, id: "daily" }] });
  assert.equal(compareEvidence(weekly, [daily], []).linked[0].state, "문서 변경 · 재검토");
});
test("source edits invalidate transitively, including weekly and assessment documents", () => {
  const daily = document({ id: "daily" });
  const weekly = document({ id: "weekly", sources: [{ ...source, id: "daily" }] });
  const assessment = document({ id: "assessment", sources: [{ ...source, id: "weekly" }] });
  const independent = document({ id: "unrelated", sources: [] });
  const result = invalidateDependents([daily, weekly, assessment, independent], "r1");
  assert.deepEqual(
    result.map((d) => d.status),
    ["draft", "draft", "draft", "confirmed"],
  );
});
test("template analysis uses source headings and handles text without headings", () => {
  assert.deepEqual(
    analyzeText("놀이 목표:\n아이의 관심을 살핀다.\n교사 지원:\n자료를 제공한다.").headings,
    ["놀이 목표", "교사 지원"],
  );
  assert.deepEqual(analyzeText("abcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwxyz").headings, [
    "내용",
  ]);
});
test("annual plans contain twelve months and use the academic year across leap February", () => {
  const period = {
    annual: { year: 2027 },
    monthly: { month: 2 },
    weekly: { month: 9, week: 2 },
    daily: { date: "2027-09-11" },
  };
  const plan = templatePlan("annual", "4", period, "");
  assert.equal(plan.rows.length, 12);
  assert.equal(plan.rows[0].label, "3월");
  assert.equal(plan.rows[11].label, "2월");
  assert.deepEqual(planPeriod("annual", period), { start: "2027-03-01", end: "2028-02-29" });
  assert.deepEqual(planPeriod("weekly", period), { start: "2027-09-08", end: "2027-09-14" });
});
test("corrupted storage is rejected without silently overwriting it", () => {
  assert.throws(() => parseWorkspace('{"version":1,"observations":[]}'));
  assert.throws(() =>
    parseWorkspace('{"version":1,"observations":[],"documents":[{}],"templates":[],"criteria":[]}'),
  );
  let value = '{"bad":true}';
  let wrote = false;
  globalThis.window = {
    sessionStorage: fixtureSession(),
    localStorage: {
      getItem: (key) => (key === fixtureKey ? fixtureAccount : value),
      setItem: () => {
        wrote = true;
      },
    },
    dispatchEvent: () => {},
  };
  assert.throws(() => updateWorkspace((d) => d));
  assert.equal(wrote, false);
  value = null;
  window.localStorage.setItem = (_key, next) => {
    value = next;
  };
  updateWorkspace((data) => ({
    ...data,
    criteria: [{ id: "c", label: "관찰", terms: "관찰", source: "기관 기준" }],
  }));
  assert.equal(readWorkspace().criteria.length, 1);
  window.localStorage.setItem = () => {
    throw new Error("quota");
  };
  assert.throws(() => updateWorkspace((d) => d), /quota/);
  delete globalThis.window;
});
test("a stale editor cannot overwrite changed, invalidated or missing documents", () => {
  const original = document();
  assert.doesNotThrow(() => assertDocumentUnchanged(structuredClone(original), original));
  assert.throws(
    () => assertDocumentUnchanged({ ...original, status: "draft" }, original),
    /다른 작업/,
  );
  assert.throws(
    () => assertDocumentUnchanged({ ...original, sections: [] }, original),
    /다른 작업/,
  );
  assert.throws(() => assertDocumentUnchanged(undefined, original), /다른 작업/);
});
test("imported evidence can be re-confirmed without fabricated observation fields", () => {
  const imported = document({
    origin: "import",
    sources: [],
    sections: [{ heading: "첨부 원문", body: "교사가 직접 작성한 기존 관찰 원문", sourceIds: [] }],
  });
  assert.deepEqual(validateDocument(imported), []);
  assert.ok(validateDocument({ ...imported, childId: "" }).some((s) => s.includes("대상 아동")));
  assert.ok(
    validateDocument({ ...imported, kind: "dailyLog", end: "2026-09-12" }).some((s) =>
      s.includes("같아야"),
    ),
  );
});
test("source ownership, duplicate sections and forged fact references are rejected", () => {
  const doc = document();
  assert.ok(validateDocument({ ...doc, childId: "another" }).some((s) => s.includes("반·아동")));
  assert.ok(
    validateDocument({ ...doc, sections: [...doc.sections, doc.sections[2]] }).some((s) =>
      s.includes("중복"),
    ),
  );
  const altered = structuredClone(doc);
  altered.sections[0].sourceIds = ["unknown"];
  assert.ok(validateDocument(altered).some((s) => s.includes("근거 기록 연결")));
});
test("document schema rejects invalid kinds and statuses", () => {
  const doc = {
    ...document(),
    title: "test",
    className: "test",
    childName: "test",
    origin: "teacher",
    createdAt: "2026-09-11",
    updatedAt: "2026-09-11",
    reviewNote: "",
  };
  assert.equal(isSavedDocument(doc), true);
  assert.equal(isSavedDocument({ ...doc, kind: "garbage" }), false);
  assert.equal(isSavedDocument({ ...doc, status: "passed" }), false);
  const data = {
    version: 1,
    observations: [],
    documents: [doc, { ...doc }],
    templates: [],
    criteria: [],
  };
  assert.throws(() => parseWorkspace(JSON.stringify(data)), /중복/);
});
test("February without a fifth week never duplicates the fourth week", () => {
  const period = {
    annual: { year: 2026 },
    monthly: { month: 2 },
    weekly: { month: 2, week: 5 },
    daily: { date: "2026-02-28" },
  };
  assert.throws(() => planPeriod("weekly", period), /없는 주차/);
  period.weekly.week = 4;
  assert.deepEqual(planPeriod("weekly", period), { start: "2026-02-22", end: "2026-02-28" });
});
