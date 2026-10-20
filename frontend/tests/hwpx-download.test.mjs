// hwpx 내려받기(lib/api/export.ts)가 파일 이름을 어디서 가져오는지.
// 실제 서버를 부르지 않는다. fetch 와 브라우저의 내려받기 링크만 흉내 낸다.
import { test, beforeEach, afterEach } from "node:test";
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
const { downloadHwpx } = await import("../lib/api/export.ts");

const original = {
  fetch: globalThis.fetch,
  window: globalThis.window,
  document: globalThis.document,
  createObjectURL: URL.createObjectURL,
  revokeObjectURL: URL.revokeObjectURL,
};
let saved;
/** 누를 때 문서에 붙어 있었는가. 떼어 둔 <a> 는 파이어폭스 · 사파리에서 안 받아진다. */
let attachedWhenClicked;
/** 누른 뒤 치웠는가. 안 치우면 받을 때마다 빈 <a> 가 쌓인다. */
let removedAfter;
beforeEach(() => {
  saved = [];
  attachedWhenClicked = [];
  removedAfter = [];
  globalThis.window = { sessionStorage: { getItem: () => null } };
  const children = new Set();
  globalThis.document = {
    body: {
      appendChild(node) {
        children.add(node);
        node.remove = () => {
          children.delete(node);
          removedAfter.push(node.download);
        };
        return node;
      },
    },
    createElement: () => ({
      style: {},
      remove() {},
      click() {
        saved.push(this.download);
        attachedWhenClicked.push(children.has(this));
      },
    }),
  };
  URL.createObjectURL = () => "blob:test";
  URL.revokeObjectURL = () => {};
});
afterEach(() => {
  Object.assign(globalThis, {
    fetch: original.fetch,
    window: original.window,
    document: original.document,
  });
  URL.createObjectURL = original.createObjectURL;
  URL.revokeObjectURL = original.revokeObjectURL;
});

const respond = (headers) => {
  globalThis.fetch = async () => new Response(new Blob(["hwpx"]), { status: 200, headers });
};

test("filename* 의 한글 이름을 먼저 쓴다", async () => {
  respond({
    "Content-Disposition": `attachment; filename="plan-3.hwpx"; filename*=UTF-8''${encodeURIComponent("햇살반 연간 보육계획안.hwpx")}`,
  });
  await downloadHwpx("/api/plans/3/export/hwp", "연간계획안.hwpx");
  assert.deepEqual(saved, ["햇살반 연간 보육계획안.hwpx"]);
});

test("filename* 이 없으면 영문 filename 을 쓴다", async () => {
  respond({ "Content-Disposition": 'attachment; filename="plan-3.hwpx"' });
  await downloadHwpx("/api/plans/3/export/hwp", "연간계획안.hwpx");
  assert.deepEqual(saved, ["plan-3.hwpx"]);
});

test("헤더에 이름이 없으면 기본 이름을 쓴다 — 빈 이름이면 확장자가 빠진다", async () => {
  respond({});
  await downloadHwpx("/api/plans/3/export/hwp", "연간계획안.hwpx");
  assert.deepEqual(saved, ["연간계획안.hwpx"]);
});

test("누를 때 문서에 붙어 있고, 누른 뒤 치운다", async () => {
  respond({ "Content-Disposition": 'attachment; filename="plan-3.hwpx"' });

  await downloadHwpx("/api/plans/3/export/hwp", "연간계획안.hwpx");

  // 떼어 둔 <a> 의 click() 은 크롬에서만 먹는다. 교사가 버튼을 눌렀는데 아무 일도
  // 안 일어나는 길이라, 붙어 있었는지를 직접 본다.
  assert.deepEqual(attachedWhenClicked, [true]);
  assert.deepEqual(removedAfter, ["plan-3.hwpx"]);
});
