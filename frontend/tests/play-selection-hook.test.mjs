// 저장 훅의 정리 순서: 입력창이 사라질 때의 저장이 큐에 들어간 뒤에야 큐를 내린다.
import assert from "node:assert/strict";
import { test } from "node:test";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
function load(path, modules) {
  const file = new URL(path, import.meta.url);
  const code = require("next/dist/compiled/babel/core").transformSync(readFileSync(file, "utf8"), {
    filename: fileURLToPath(file),
    babelrc: false,
    configFile: false,
    presets: [
      [require("next/dist/compiled/babel/preset-env"), { targets: { node: "current" } }],
      require("next/dist/compiled/babel/preset-typescript"),
    ],
  }).code;
  const compiled = { exports: {} };
  new Function("require", "module", "exports", code)(
    (name) => modules[name],
    compiled,
    compiled.exports,
  );
  return compiled.exports;
}

function mountHook() {
  const effects = [];
  const refs = [];
  const state = [];
  let cursor = 0;
  let refCursor = 0;
  const sentCells = [];
  const queueModule = load("../lib/plan-generator/playSelectionQueue.ts", {});
  const saveModule = load("../lib/hooks/use-play-selection-save.ts", {
    react: {
      useState: (initial) => {
        const index = cursor++;
        if (!(index in state)) state[index] = typeof initial === "function" ? initial() : initial;
        return [state[index], () => {}];
      },
      useRef: (initial) => (refs[refCursor++] ??= { current: initial }),
      useEffect: (effect) => effects.push(effect),
    },
    "@/lib/api/plans": {
      savePlaySelection: async () => ({ revision: 2 }),
      editPlayCell: async (_id, itemId, value) => (
        sentCells.push([itemId, value]),
        { revision: 2 }
      ),
      isSaveConflict: () => false,
      isRejectedSave: () => false,
    },
    "@/lib/plan-generator/playSelectionQueue": queueModule,
  });
  const render = () => {
    cursor = 0;
    refCursor = 0;
    effects.length = 0;
    const hook = saveModule.usePlaySelectionSave(1, 1, async () => {});
    return { hook, run: effects.map((effect) => effect()) };
  };
  return { render, sentCells };
}

test("a cell saved by an editor that unmounts together with the screen still reaches the queue", async () => {
  const view = mountHook();
  const { hook, run } = view.render();
  const cleanup = run.find((value) => typeof value === "function");
  cleanup(); // 화면이 내려간다 — 정리는 부모 것이 먼저 돌 수 있다
  hook.saveCell("item_a", "마지막 글", "옛 글"); // 이어서 입력창 정리의 저장
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.deepEqual(view.sentCells, [["item_a", "마지막 글"]]);
  hook.saveCell("item_a", "내려간 뒤의 글", "마지막 글"); // 내려간 뒤에는 받지 않는다
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(view.sentCells.length, 1);
});

test("a remount that runs the effect again keeps the queue active", async () => {
  const view = mountHook();
  const first = view.render();
  first.run.find((value) => typeof value === "function")(); // 개발 모드의 정리
  view.render(); // 효과가 다시 돈다
  await new Promise((resolve) => setTimeout(resolve, 0));
  first.hook.saveCell("item_a", "글", "옛 글");
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(view.sentCells.length, 1);
});
