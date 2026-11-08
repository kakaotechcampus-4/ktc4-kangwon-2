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

test("도장 근거는 쌤플 확정 · 폴더 · 교사 체크를 따로 세고, 한 칸에 여럿이면 다 낸다", async () => {
  const { stampSources } = await import("../lib/workspace/evaluation-files.ts");
  const found = { status: "found" };
  // 쌤플 서류 — 확정 + 폴더 둘 다
  assert.deepEqual(stampSources({ done: true }, found, false), ["ssample", "folder"]);
  // 「일부 빠짐」은 도장이 아니다
  assert.deepEqual(stampSources({ done: false }, { status: "partial" }, false), []);
  // 쌤플 서류에 남은 옛 체크(옛 화면이 폴더 결과를 써 넣은 것)는 근거가 아니다
  assert.deepEqual(stampSources({ done: false }, undefined, true), []);
  // 쌤플 서류가 확정 0건이어도 폴더에서 찾았으면 「내컴퓨터」만 — 옛 체크가 있어도 같다
  assert.deepEqual(stampSources({ done: false }, found, false), ["folder"]);
  assert.deepEqual(stampSources({ done: false }, found, true), ["folder"]);
  // 쌤플이 만들지 않는 서류 — 폴더 + 교사 체크
  assert.deepEqual(stampSources(null, found, true), ["folder", "teacher"]);
  assert.deepEqual(stampSources(null, undefined, true), ["teacher"]);
  assert.deepEqual(stampSources(null, undefined, false), []);
});

test("도장 근거 줄은 쌤플 · 폴더 · 직접확인을 따로 적고 상태를 나눈다", async () => {
  const { sourceLines } = await import("../lib/workspace/evaluation-files.ts");
  const brief = (lines) => lines.map((l) => `${l.source}:${l.state}:${l.text}`);
  // 서버에 남는 모양(ADR-074) — 이름 · 날짜 없이 숫자만
  const partial = { status: "partial", files: 2, gaps: 2 };
  // 쌤플 서류 — 확정 0건 · 폴더는 일부 빠짐(빈 평일 수로 적는다)
  assert.deepEqual(
    brief(
      sourceLines(doc("journal"), { done: false, some: false, text: "확정 0건" }, partial, false),
    ),
    ["ssample:none:확정 0건", "folder:short:일부 빠짐 · 빈 평일 2일"],
  );
  // 계획안은 달로 센다 · 확정은 있지만 모자라면 점선
  assert.deepEqual(
    brief(
      sourceLines(
        doc("plan"),
        { done: false, some: true, text: "확정 1건" },
        { ...partial, gaps: 1 },
        false,
      ),
    ),
    ["ssample:short:확정 1건", "folder:short:일부 빠짐 · 빈 달 1개"],
  );
  // 폴더를 안 골랐으면 「폴더를 고르면」 · 쌤플이 만들지 않는 서류는 쌤플 줄이 없고 누른 것만 직접확인
  assert.deepEqual(brief(sourceLines(doc("parent"), null, undefined, true)), [
    "folder:none:폴더를 고르면 이름으로 찾아봐요",
    "teacher:on:도장판에서 눌렀어요",
  ]);
  // 쌤플 서류의 옛 체크는 직접확인 줄을 만들지 않는다
  assert.deepEqual(
    brief(
      sourceLines(
        doc("journal"),
        { done: true, some: true, text: "확정 3건" },
        { status: "found", files: 1, gaps: 0 },
        true,
      ),
    ),
    ["ssample:on:확정 3건", "folder:on:이름으로 찾음 · 1건"],
  );
});

test("폴더 결과 요약은 이름을 버리고 숫자만 남긴다 — 빈 날은 일부 빠짐일 때만", async () => {
  const { summarize, windowOf } = await import("../lib/workspace/evaluation-files.ts");
  const names = ["2026-10-01_보육일지.hwp", "2026-10-02_보육일지.hwp"];
  const partial = checkDoc(doc("journal"), names, TODAY);
  assert.equal(partial.status, "partial");
  assert.deepEqual(summarize(partial), {
    status: "partial",
    files: 2,
    gaps: partial.missing.length,
  });
  assert.ok(partial.missing.length > 0);
  // 못 찾은 서류는 빈 평일이 기간 전부지만 0 으로 보낸다 — 서버가 「일부 빠짐일 때만 빈 날」을 본다
  const missing = checkDoc(doc("journal"), [], TODAY);
  assert.ok(missing.missing.length > 0);
  assert.deepEqual(summarize(missing), { status: "missing", files: 0, gaps: 0 });
  // 기간은 checkDoc 과 같다 — 보육일지는 최근, 면담은 1년
  assert.deepEqual(windowOf(doc("journal"), TODAY), windowsFor(TODAY).recent);
  assert.deepEqual(windowOf(doc("parent"), TODAY), windowsFor(TODAY).year);
});
