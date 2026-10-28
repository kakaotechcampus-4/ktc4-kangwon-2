/** 받아쓰기가 같은 말을 여러 번 적지 않는다 (lib/hooks/use-dictation.ts). */
import { test } from "node:test";
import assert from "node:assert/strict";
import { registerHooks } from "node:module";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";

// 훅 파일끼리는 확장자 없이 서로를 부른다. node 에게 `.ts` 를 붙여 준다.
registerHooks({
  resolve(spec, ctx, next) {
    if (spec.startsWith(".") && !spec.endsWith(".ts")) {
      const guess = new URL(spec + ".ts", ctx.parentURL);
      if (existsSync(fileURLToPath(guess))) return { url: guess.href, shortCircuit: true };
    }
    return next(spec, ctx);
  },
});

const { transcriptFrom } = await import("../lib/hooks/use-dictation.ts");

/** `event.results` 를 흉내 낸다 — 브라우저는 지금까지 받은 것을 **전부** 다시 넘긴다. */
const results = (...말) => 말.map((transcript) => [{ transcript }]);

test("한 번 말하면 한 번만 적는다", () => {
  assert.equal(transcriptFrom(results("안녕하세요"), 0), "안녕하세요");
});

test("누적으로 다시 와도 못 읽은 것만 적는다", () => {
  // 크롬은 한 마디에도 onresult 를 여러 번 부르고, 그때마다 앞의 것이 같이 들어 있다.
  const 첫번째 = results("안녕하세요");
  assert.equal(transcriptFrom(첫번째, 0), "안녕하세요");

  const 두번째 = results("안녕하세요", "도토리를 주웠어요");
  assert.equal(transcriptFrom(두번째, 첫번째.length), "도토리를 주웠어요");

  const 세번째 = results("안녕하세요", "도토리를 주웠어요");
  assert.equal(transcriptFrom(세번째, 두번째.length), "");
});

test("여러 마디가 한꺼번에 오면 이어 붙인다", () => {
  const 받은것 = results("안녕하세요", "도토리를", "주웠어요");
  assert.equal(transcriptFrom(받은것, 1), "도토리를 주웠어요");
});
