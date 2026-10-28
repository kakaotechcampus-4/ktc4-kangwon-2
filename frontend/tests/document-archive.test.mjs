/** 문서 보관함(S-J5) 탐색 — 상태 판정과 기간 계산. */
import { test } from "node:test";
import assert from "node:assert/strict";

const {
  ARCHIVE_STATUS_LABEL,
  archiveStatus,
  planStatus,
  weekDays,
  shiftDays,
  shiftMonth,
  weekIdLabel,
  weekRangeLabel,
  schoolYearOf,
  monthLabel,
  shortDate,
} = await import("../lib/workspace/document-archive.ts");

test("목록 상태는 확정 · 검토 중 · 미작성 셋뿐이다", () => {
  assert.equal(archiveStatus({ status: "confirmed" }), "confirmed");
  assert.equal(archiveStatus({ status: "draft" }), "draft");
  assert.equal(archiveStatus(null), "none");
  assert.equal(archiveStatus(undefined), "none");
  assert.deepEqual(Object.keys(ARCHIVE_STATUS_LABEL), ["confirmed", "draft", "none"]);
});

test("stale 인 확정본을 검토 중으로 끌어내리지 않는다", () => {
  // 근거가 바뀌어도 목록에서는 확정이다. 재확인은 문서 상세 안에서 한다.
  assert.equal(archiveStatus({ status: "confirmed", stale: true }), "confirmed");
  assert.equal(archiveStatus({ status: "draft", stale: true }), "draft");
});

test("계획안 상태는 대문자 두 가지뿐이다", () => {
  assert.equal(planStatus("CONFIRMED"), "confirmed");
  assert.equal(planStatus("DRAFT"), "draft");
});

test("주는 월요일에 시작하고 일요일에 끝난다", () => {
  // 2026-10-20 은 화요일.
  assert.deepEqual(weekDays("2026-10-20"), [
    "2026-10-19",
    "2026-10-20",
    "2026-10-21",
    "2026-10-22",
    "2026-10-23",
    "2026-10-24",
    "2026-10-25",
  ]);
  // 일요일은 그 주의 끝이다 — 다음 주로 넘기지 않는다.
  assert.equal(weekDays("2026-10-25")[0], "2026-10-19");
});

test("달을 넘는 주도 7일 그대로다", () => {
  const days = weekDays("2026-11-01");
  assert.equal(days.length, 7);
  assert.equal(days[0], "2026-10-26");
  assert.equal(days[6], "2026-11-01");
});

test("날짜 · 달 이동이 경계를 넘는다", () => {
  assert.equal(shiftDays("2026-10-31", 1), "2026-11-01");
  assert.equal(shiftDays("2026-01-01", -1), "2025-12-31");
  assert.equal(shiftMonth("2026-12", 1), "2027-01");
  assert.equal(shiftMonth("2026-01", -1), "2025-12");
  assert.equal(shiftMonth("2026-10", 0), "2026-10");
});

test("주차 머리글은 서버가 준 week_id 를 읽기만 한다", () => {
  assert.equal(weekIdLabel("2026-10-W4"), "2026년 10월 4주차");
  assert.equal(weekIdLabel("2026-01-W1"), "2026년 1월 1주차");
  // 모양이 다르면 지어내지 않고 그대로 보여 준다.
  assert.equal(weekIdLabel("뭔가-다른-값"), "뭔가-다른-값");
});

test("일지 주 머리글은 주차 번호 대신 날짜 범위다", () => {
  assert.equal(weekRangeLabel(weekDays("2026-10-20")), "2026년 10월 19일 ~ 25일");
  assert.equal(weekRangeLabel(weekDays("2026-11-01")), "2026년 10월 26일 ~ 11월 1일");
});

test("학년도는 3월에 시작한다", () => {
  assert.equal(schoolYearOf("2026-03-01"), 2026);
  assert.equal(schoolYearOf("2026-12-31"), 2026);
  assert.equal(schoolYearOf("2026-02-28"), 2025);
  assert.equal(schoolYearOf("2026-01-01"), 2025);
});

test("짧은 머리글", () => {
  assert.equal(monthLabel("2026-10"), "2026년 10월");
  assert.equal(shortDate("2026-10-05"), "10.5");
});

// ── 화면이 보여 주는 것과 열 수 있는 것이 같아야 한다 (보육일지 화면의 관찰일지 편집기) ──
const { journalsInView, openableIn } = await import("../lib/workspace/document-archive.ts");

const d = (id, kind, start, classId = "c1", childId = "") => ({
  id,
  kind,
  classId,
  childId,
  start,
});
const pool = [
  d("doc:1", "dailyLog", "2026-10-28"),
  d("doc:2", "dailyLog", "2026-10-27"),
  d("doc:3", "observation", "2026-10-28", "c1", "kid-1"),
  d("doc:4", "observation", "2026-10-28", "c1", "kid-2"),
  d("doc:5", "weeklyLog", "2026-10-26"),
  d("doc:6", "dailyLog", "2026-10-28", "c2"),
];

test("보육일지 화면은 같은 반·같은 날짜의 일일 보육일지만 보여 준다", () => {
  const view = { kind: "dailyLog", classId: "c1", day: "2026-10-28" };
  assert.deepEqual(
    journalsInView(pool, view).map((x) => x.id),
    ["doc:1"],
  );
});

test("다른 반 문서는 섞이지 않는다", () => {
  assert.equal(
    journalsInView(pool, { kind: "dailyLog", classId: "c2", day: "2026-10-28" })[0].id,
    "doc:6",
  );
  assert.deepEqual(
    journalsInView(pool, { kind: "dailyLog", classId: "c3", day: "2026-10-28" }),
    [],
  );
});

test("관찰일지는 아동까지 맞아야 한다", () => {
  const view = { kind: "observation", classId: "c1", childId: "kid-1", day: "2026-10-28" };
  assert.deepEqual(
    journalsInView(pool, view).map((x) => x.id),
    ["doc:3"],
  );
});

test("주간 보육일지는 날짜가 아니라 그 달로 거른다", () => {
  assert.deepEqual(
    journalsInView(pool, { kind: "weeklyLog", classId: "c1", month: "2026-10" }).map((x) => x.id),
    ["doc:5"],
  );
  assert.deepEqual(
    journalsInView(pool, { kind: "weeklyLog", classId: "c1", month: "2026-11" }),
    [],
  );
});

test("보육일지 화면에서 관찰일지 상세를 열지 않는다", () => {
  const care = { kind: "dailyLog", classId: "c1", day: "2026-10-28" };
  // 관찰일지를 보다가 보육일지로 옮겨도 그 선택이 남아 편집기를 띄우면 안 된다.
  assert.equal(openableIn(pool, care, "doc:3"), null);
  assert.equal(openableIn(pool, care, "doc:1").id, "doc:1");
});

test("문서 종류를 안 골랐거나 선택이 없으면 상세를 열지 않는다", () => {
  assert.equal(openableIn(pool, null, "doc:1"), null);
  assert.equal(openableIn(pool, { kind: "dailyLog", classId: "c1", day: "2026-10-28" }, ""), null);
});

test("미작성 날짜에서는 어떤 상세도 열리지 않는다", () => {
  const empty = { kind: "dailyLog", classId: "c1", day: "2026-10-30" };
  assert.deepEqual(journalsInView(pool, empty), []);
  assert.equal(openableIn(pool, empty, "doc:1"), null);
});

test("반을 바꾸면 이전 반의 문서는 열리지 않는다", () => {
  assert.equal(
    openableIn(pool, { kind: "dailyLog", classId: "c2", day: "2026-10-28" }, "doc:1"),
    null,
  );
});
