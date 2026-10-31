/** 평가 서류 점검 — 파일 이름만 보고 검토문서를 센다 (ADR-045). */
import { test } from "node:test";
import assert from "node:assert/strict";

const { parseDate, windowsFor, scanNames, checkDoc, TEACHER_DOCS, isIgnored } =
  await import("../lib/workspace/evaluation-files.ts");

const doc = (id) => TEACHER_DOCS.find((d) => d.id === id);
const TODAY = "2026-10-28"; // 수요일

test("날짜는 여러 표기를 읽고, 없는 날은 날짜로 보지 않는다", () => {
  assert.deepEqual(parseDate("2026-10-15_보육일지.hwp"), { kind: "day", value: "2026-10-15" });
  assert.deepEqual(parseDate("보육일지 20261015.hwp"), { kind: "day", value: "2026-10-15" });
  assert.deepEqual(parseDate("2026.10.15 보육일지"), { kind: "day", value: "2026-10-15" });
  assert.deepEqual(parseDate("2026-10_월간계획안.hwp"), { kind: "month", value: "2026-10" });
  assert.equal(parseDate("보육일지.hwp"), null);
  assert.deepEqual(parseDate("2026-02-30_보육일지"), { kind: "month", value: "2026-02" });
});

test("최근 기간은 지난달 1일부터 어제까지, 1년은 오늘까지다", () => {
  assert.deepEqual(windowsFor(TODAY), {
    recent: { from: "2026-09-01", to: "2026-10-27" },
    year: { from: "2025-10-29", to: "2026-10-28" },
  });
  assert.equal(windowsFor("2026-01-05").recent.from, "2025-12-01");
});

test("임시 파일 · 숨김 파일은 세지 않는다", () => {
  assert.ok(isIgnored("~$보육일지.hwp"));
  assert.ok(isIgnored(".DS_Store"));
  assert.ok(!isIgnored("2026-10-15_보육일지.hwp"));
  assert.equal(scanNames(["~$2026-10-15_보육일지.hwp"], TODAY).total, 0);
});

test("보육일지는 평일마다 있어야 하고, 빈 평일을 돌려준다", () => {
  const names = [];
  for (let d = 1; d <= 30; d++) names.push(`2026-09-${String(d).padStart(2, "0")}_보육일지.hwp`);
  for (let d = 1; d <= 27; d++) names.push(`2026-10-${String(d).padStart(2, "0")}_보육일지.hwp`);
  assert.equal(checkDoc(doc("journal"), names, TODAY).status, "found");

  const some = checkDoc(
    doc("journal"),
    names.filter((n) => n !== "2026-10-15_보육일지.hwp"),
    TODAY,
  );
  assert.equal(some.status, "partial");
  assert.deepEqual(some.missing, ["2026-10-15"]);
});

test("주간 보육일지는 그 주 월~금을 덮는다", () => {
  const r = checkDoc(doc("journal"), ["2026-10-14_주간보육일지.hwp"], TODAY);
  assert.equal(r.status, "partial");
  for (const d of ["2026-10-12", "2026-10-13", "2026-10-14", "2026-10-15", "2026-10-16"])
    assert.ok(!r.missing.includes(d), d);
  assert.ok(r.missing.includes("2026-10-19"));
});

test("오늘 쓴 일지 · 날짜 없는 일지 · 기간 밖 일지는 세지 않는다", () => {
  const r = checkDoc(
    doc("journal"),
    ["2026-10-28_보육일지.hwp", "보육일지.hwp", "2026-08-31_보육일지.hwp"],
    TODAY,
  );
  assert.equal(r.status, "missing");
  assert.deepEqual(r.undated, ["보육일지.hwp"]);
  assert.equal(r.outside, 2);
});

test("계획안은 지난달 · 이번 달에 하나씩 있어야 하고, 연간 · 개별화교육계획안은 빼낸다", () => {
  assert.equal(
    checkDoc(doc("plan"), ["2026-09_월간계획안.hwp", "2026-10-06_주간계획안.hwp"], TODAY).status,
    "found",
  );
  const r = checkDoc(doc("plan"), ["2026-10_월간계획안.hwp", "2026_연간보육계획안.hwp"], TODAY);
  assert.equal(r.status, "partial");
  assert.deepEqual(r.missing, ["2026-09"]);
  assert.equal(checkDoc(doc("plan"), ["2026-10_개별화교육계획안.hwp"], TODAY).status, "missing");
});

test("영유아 평가 · 면담 · 이수증은 1년 이내 1건이면 찾음이다", () => {
  const scan = scanNames(
    ["2026-03_영유아 평가.hwp", "2025-09_부모면담.hwp", "2026-05_수료증.pdf"],
    TODAY,
  );
  const status = Object.fromEntries(scan.results.map((r) => [r.id, r.status]));
  assert.equal(status.assessment, "found");
  assert.equal(status.parent, "missing"); // 2025-09 는 1년(2025-10-29~) 밖이다
  assert.equal(status.training, "found");
  // 월 단위 날짜는 그 달이 기간과 겹치면 센다
  assert.equal(checkDoc(doc("parent"), ["2025-10_부모면담.hwp"], TODAY).status, "found");
});

test("이름으로 찾은 서류만 체크에 더하고, 교사가 한 체크는 남긴다", async () => {
  const { withFound } = await import("../lib/workspace/evaluation-files.ts");
  const scan = scanNames(["2026-05_수료증.pdf", "2026-10_월간계획안.hwp"], TODAY);
  assert.deepEqual(withFound(["director:annual-plan"], scan).sort(), [
    "director:annual-plan",
    "doc:training",
  ]);
});
