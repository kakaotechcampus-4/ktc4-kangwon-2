// 목업 모드에서 로그아웃하면 목업 DB(saessak.mswSS.v1:<계정>)를 지운다 — 교사가 친 아이 이름이
// 남지 않게(ADR-013). 그런데 그 계정의 반 설정과 목업 id 연결(apiLinks)은 남아서, 다시 로그인하면
// 없는 반(GET /api/classes/2/children 404)을 불러 홈이 「기록을 불러오지 못했어요」가 됐다(점검 X-E3).
// 목업 DB를 지울 때 그 계정의 반 설정과 목업 연결도 같이 지운다. 다른 계정 · 실제 서버 연결은 그대로.
import { test } from "node:test";
import assert from "node:assert/strict";

function storage(entries) {
  const map = new Map(Object.entries(entries));
  return {
    get length() {
      return map.size;
    },
    key: (i) => [...map.keys()][i] ?? null,
    getItem: (k) => (map.has(k) ? map.get(k) : null),
    setItem: (k, v) => map.set(k, String(v)),
    removeItem: (k) => map.delete(k),
    keys: () => [...map.keys()].sort(),
  };
}

const acct = "fix%40example.com";
const other = "other%40example.com";
const local = storage({
  [`saessak.mswSS.v1:${acct}`]: "{}",
  [`saessak.classSettings:${acct}`]: JSON.stringify({ orgName: "햇살어린이집", classes: [] }),
  [`saessak.apiLinks.v1:development-mock:${acct}`]: JSON.stringify({ classes: {} }),
  [`saessak.apiLinks.v1:backend:${acct}`]: JSON.stringify({ classes: {} }),
  [`saessak.classSettings:${other}`]: JSON.stringify({ orgName: "다른원", classes: [] }),
  [`saessak.apiLinks.v1:development-mock:${other}`]: JSON.stringify({ classes: {} }),
});
globalThis.window = { localStorage: local, sessionStorage: storage({}) };

const { sanitizeBrowserChildMetadata } = await import("../lib/privacy/browser-storage.ts");

test("목업 DB를 지우면 그 계정의 반 설정과 목업 연결도 지운다", () => {
  sanitizeBrowserChildMetadata();
  assert.deepEqual(local.keys(), [
    `saessak.apiLinks.v1:backend:${acct}`,
    `saessak.apiLinks.v1:development-mock:${other}`,
    `saessak.classSettings:${other}`,
  ]);
});
