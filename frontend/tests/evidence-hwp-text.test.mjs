/** 증빙 등록 — 한글 파일은 §8 parse 가 준 표를 글로 펴서 미리보기에 넣는다. */
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

const { tableText } = await import("../lib/api/forms.ts");
const cell = (text) => ({ text, rowspan: 1, colspan: 1 });

test("행은 한 줄, 칸은 · 로 잇고, 표 사이는 한 줄 띄운다", () => {
  const tables = [
    [
      [cell("날짜"), cell("2026-10-15")],
      [cell("놀이"), cell("블록 쌓기")],
    ],
    [[cell("평가"), cell("또래와 차례를 지킨다")]],
  ];
  assert.equal(
    tableText(tables),
    "날짜 · 2026-10-15\n놀이 · 블록 쌓기\n\n평가 · 또래와 차례를 지킨다",
  );
});

test("빈 칸 · 빈 행 · 빈 표는 버린다", () => {
  const tables = [
    [
      [cell(" "), cell("관찰")],
      [cell(""), cell("")],
    ],
    [[cell("")]],
  ];
  assert.equal(tableText(tables), "관찰");
  assert.equal(tableText([]), "");
});
