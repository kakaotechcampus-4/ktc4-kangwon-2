// 관찰 축이 두 갈래다 (docs/references/관찰일지-서술-기준.md).
// 서버 목록(backend observations/models.py AXES)과 화면 목록이 어긋나면
// 교사가 고른 값이 422 로 돌아온다. 그 어긋남을 여기서 잡는다.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
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
const axis = await import("../lib/workspace/observation-axis.ts");

const MODELS = new URL("../../backend/app/features/observations/models.py", import.meta.url);

/** 파이썬 튜플 리터럴에서 따옴표 안의 값만 꺼낸다. */
function pythonTuple(source, name) {
  const body = new RegExp(`^${name} = \\(([^)]*)\\)`, "m").exec(source)[1];
  return [...body.matchAll(/"([^"]+)"/g)].map((m) => m[1]);
}

test("화면 목록이 서버 AXES 와 같다", () => {
  const source = readFileSync(fileURLToPath(MODELS), "utf8");
  assert.deepEqual([...axis.NURI_DOMAINS], pythonTuple(source, "NURI_DOMAINS"));
  assert.deepEqual([...axis.DAILY_PLAY_DOMAINS], pythonTuple(source, "DAILY_PLAY_DOMAINS"));
  // 축 이름도 같아야 한다. 서버가 모르는 이름을 보내면 422 다.
  for (const key of Object.keys(axis.AXES)) assert.ok(source.includes(`"${key}":`), key);
});

test("기본은 누리과정 5영역이다", () => {
  assert.equal(axis.DEFAULT_AXIS, "NURI_5");
  assert.equal(axis.AXES[axis.DEFAULT_AXIS].length, 5);
  assert.equal(axis.AXES.DAILY_PLAY_2.length, 2);
});

test("축마다 사람이 읽을 이름이 있다", () => {
  for (const key of Object.keys(axis.AXES)) assert.ok(axis.AXIS_LABELS[key], key);
});

test("상수 모듈은 아무것도 import 하지 않는다", () => {
  // model.ts 가 쓰는 자리라 React · API 를 끌어오면 그걸 안 쓰는 쪽까지 딸려 온다.
  const source = readFileSync(
    fileURLToPath(new URL("../lib/workspace/observation-axis.ts", import.meta.url)),
    "utf8",
  );
  assert.ok(!/^\s*import /m.test(source));
});
