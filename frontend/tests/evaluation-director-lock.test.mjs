// 원장 서류 체크는 원 단위라 원을 처음 등록한 선생님만 바꾼다(ADR-087). 다른 선생님은 보기만 한다.
import assert from "node:assert/strict";
import { test } from "node:test";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";

const require = createRequire(import.meta.url);
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");
const code = require("next/dist/compiled/babel/core").transformSync(
  readFileSync(new URL("../components/workspace/EvaluationSheet.tsx", import.meta.url), "utf8"),
  {
    filename: "EvaluationSheet.tsx",
    babelrc: false,
    configFile: false,
    presets: [
      [require("next/dist/compiled/babel/preset-env"), { targets: { node: "current" } }],
      [require("next/dist/compiled/babel/preset-react"), { runtime: "automatic" }],
      require("next/dist/compiled/babel/preset-typescript"),
    ],
  },
).code;
const ITEMS = [
  { id: "operation-plan", title: "어린이집 운영계획", basis: "5-1" },
  { id: "annual-plan", title: "연간 보육계획안", basis: "5-1" },
];
const stub = () => null;
const modules = {
  react: React,
  "next/link": { __esModule: true, default: stub },
  "@/lib/workspace/evaluation-files": { DIRECTOR_ITEMS: ITEMS, TEACHER_DOCS: [] },
  "@/lib/workspace/model": { today: () => "2026-11-10" },
  "@/components/app/Posty": { Posty: stub },
  "@/components/app/icons": { Icon: stub },
  "./WorkspaceUI": { ws: {} },
  "./EvidenceImport": { __esModule: true, default: stub },
  "./Evaluation.module.css": { __esModule: true, default: {} },
};
const m = { exports: {} };
new Function("require", "module", "exports", code)((n) => modules[n] ?? require(n), m, m.exports);
const { DirectorList } = m.exports;
const checks = [{ item: "annual-plan", checked: true, checked_at: "2026-11-01T00:00:00Z" }];
const render = (props) =>
  renderToStaticMarkup(React.createElement(DirectorList, { checks, onToggle() {}, ...props }));

test("원을 만든 선생님이 아니면 체크 칸이 잠기고 까닭을 적는다", () => {
  const html = render({ canEdit: false });
  assert.equal(html.match(/<input[^>]*disabled/g)?.length, ITEMS.length);
  assert.match(html, /원을 처음 등록한 선생님만 바꿀 수 있어요/);
  assert.match(html, /checked/); // 보기는 그대로다
});

test("원을 만든 선생님은 체크할 수 있다", () => {
  const html = render({ canEdit: true });
  assert.doesNotMatch(html, /disabled/);
  assert.doesNotMatch(html, /처음 등록한 선생님만/);
});
