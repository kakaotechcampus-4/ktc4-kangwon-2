// 되돌리기 · 다시 하기 순수 로직(ADR-044 §2): 30번 한도 · 새 변경이 다시 하기를 비움 · 같아진 것은 안 보냄.
import { test } from "node:test";
import assert from "node:assert/strict";
const { EMPTY_HISTORY, HISTORY_LIMIT, pushStep, popUndo, popRedo, stepSave } =
  await import("../lib/plan-generator/playEditHistory.ts");

const picks = (...list) => ({ a: list, b: [] });
const cell = (itemId, before, after) => ({ kind: "cell", itemId, before, after });
const pick = (before, after) => ({ kind: "picks", before, after });

test("only the last 30 steps stay", () => {
  let history = EMPTY_HISTORY;
  for (let n = 0; n < HISTORY_LIMIT + 5; n++)
    history = pushStep(history, cell("i", "v" + n, "v" + (n + 1)));
  assert.equal(history.undo.length, 30);
  assert.equal(history.undo[0].before, "v5");
  assert.equal(history.undo.at(-1).after, "v35");
});

test("undo moves a step to redo and redo moves it back", () => {
  const history = pushStep(pushStep(EMPTY_HISTORY, cell("i", "a", "b")), cell("i", "b", "c"));
  const undone = popUndo(history);
  assert.deepEqual(undone.step, cell("i", "b", "c"));
  assert.equal(undone.history.undo.length, 1);
  assert.equal(undone.history.redo.length, 1);
  const redone = popRedo(undone.history);
  assert.deepEqual(redone.step, cell("i", "b", "c"));
  assert.deepEqual(redone.history, history);
  assert.equal(popUndo(EMPTY_HISTORY), null);
  assert.equal(popRedo(EMPTY_HISTORY), null);
});

test("a new change empties redo", () => {
  const undone = popUndo(pushStep(EMPTY_HISTORY, cell("i", "a", "b")));
  assert.equal(undone.history.redo.length, 1);
  assert.deepEqual(pushStep(undone.history, cell("i", "a", "z")).redo, []);
});

test("undoing a mix of picks and cell edits builds the matching saves, last change first", () => {
  const s1 = pick(picks(), picks("c1"));
  const s2 = cell("item_1", "원래 이름", "고친 이름");
  const s3 = pick(picks("c1"), picks("c1", "c2"));
  let history = [s1, s2, s3].reduce(pushStep, EMPTY_HISTORY);
  // 화면 상태를 흉내 낸다 — 저장 요청은 이 상태를 바꾸고, 같은 상태는 보내지 않는다.
  const now = { selections: picks("c1", "c2"), values: { item_1: "고친 이름" } };
  const sent = [];
  const apply = (direction, pop) => {
    const popped = pop(history);
    history = popped.history;
    const save = stepSave(popped.step, direction, {
      selections: now.selections,
      cellValue: (id) => now.values[id],
    });
    if (!save) return;
    sent.push(save);
    if (save.kind === "picks") now.selections = save.selections;
    else now.values[save.itemId] = save.value;
  };
  apply("undo", popUndo);
  apply("undo", popUndo);
  apply("undo", popUndo);
  assert.deepEqual(sent, [
    { kind: "picks", selections: picks("c1") },
    { kind: "cell", itemId: "item_1", value: "원래 이름" },
    { kind: "picks", selections: picks() },
  ]);
  apply("redo", popRedo);
  assert.deepEqual(sent.at(-1), { kind: "picks", selections: picks("c1") });
  apply("redo", popRedo);
  assert.deepEqual(sent.at(-1), { kind: "cell", itemId: "item_1", value: "고친 이름" });
});

test("a step whose target already equals the current state sends nothing", () => {
  const current = { selections: picks("c1"), cellValue: () => "같은 값" };
  assert.equal(stepSave(cell("i", "같은 값", "다른 값"), "undo", current), null);
  assert.equal(stepSave(pick(picks(), picks("c1")), "redo", current), null);
  assert.deepEqual(stepSave(pick(picks(), picks("c1")), "undo", current), {
    kind: "picks",
    selections: picks(),
  });
});
