/** 연간 가져오기 확인 표 (계약 I-A · I-B). 저장 본문은 3월 → 2월, 생활주제가 빈 달은 막는다. */
import assert from "node:assert/strict";
import { test } from "node:test";
import { registerHooks } from "node:module";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";

registerHooks({
  resolve(spec, ctx, next) {
    const url = spec.startsWith(".") && ctx.parentURL ? new URL(spec + ".ts", ctx.parentURL) : null;
    if (url && existsSync(fileURLToPath(url))) return { url: url.href, shortCircuit: true };
    return next(spec, ctx);
  },
});

const { rowsFromExtract, blankThemeMonths, importMonths, emptyImportRows } =
  await import("../lib/api/annualImport.ts");

test("추출 결과는 순서와 상관없이 3월 → 2월로 서고, 빠지거나 못 찾은 달은 표시된다", () => {
  const rows = rowsFromExtract([
    { month: 2, theme: null, sub_themes: [], missing: true },
    { month: 3, theme: "새 친구", sub_themes: ["인사해요", "놀이해요"], missing: false },
  ]);
  assert.deepEqual(
    rows.map((row) => row.month),
    [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2],
  );
  assert.deepEqual(rows[0], {
    month: 3,
    theme: "새 친구",
    subThemes: "인사해요\n놀이해요",
    missing: false,
  });
  assert.equal(rows[1].missing, true); // 4월은 응답에 없다
  assert.equal(rows[11].missing, true);
  assert.deepEqual(blankThemeMonths(rows), [4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2]);
});

test("저장 본문은 생활주제 · 소주제 앞뒤 공백을 털고 빈 줄을 뺀다", () => {
  const rows = emptyImportRows().map((row) => ({ ...row, theme: ` ${row.month}월 주제 ` }));
  rows[0].subThemes = "  봄 \n\n 꽃  \n";
  assert.deepEqual(blankThemeMonths(rows), []);
  const months = importMonths(rows);
  assert.equal(months.length, 12);
  assert.deepEqual(months[0], { month: 3, theme: "3월 주제", sub_themes: ["봄", "꽃"] });
  assert.deepEqual(months[11], { month: 2, theme: "2월 주제", sub_themes: [] });
});
