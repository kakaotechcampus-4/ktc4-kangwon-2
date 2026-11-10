/**
 * 어린이집 찾기 칸 (components/onboarding/CenterFlow.tsx FindField · #416, 하민 교차검토 F5).
 *
 * 목록 API 가 실패한 것과 정상 응답이 빈 것을 나눈다. 실패를 「없어요 · 직접 적기」로 그리면
 * 교사는 목록에 정말 없는 줄 알고 직접 적어 원을 따로 만든다.
 * 실제 소스를 babel 로 옮겨 FindField 를 부른다. 다른 모듈은 이름표 스텁이다.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";

const require = createRequire(import.meta.url);
const code = require("next/dist/compiled/babel/core").transformSync(
  readFileSync(new URL("../components/onboarding/CenterFlow.tsx", import.meta.url), "utf8"),
  {
    filename: "CenterFlow.tsx",
    babelrc: false,
    configFile: false,
    presets: [
      [require("next/dist/compiled/babel/preset-env"), { targets: { node: "current" } }],
      [require("next/dist/compiled/babel/preset-react"), { runtime: "automatic" }],
      require("next/dist/compiled/babel/preset-typescript"),
    ],
  },
).code;

const jsx = (type, props) => ({ type, props });
const tag = new Proxy({}, { get: (_, name) => (name === "__esModule" ? true : String(name)) });
const imports = {
  "react/jsx-runtime": { jsx, jsxs: jsx, Fragment: "fragment" },
  react: { useEffect() {}, useRef: () => ({}), useState: (v) => [v, () => {}] },
  "next/navigation": { useRouter: () => ({}) },
  "./OnboardingLayout": tag,
  "./RegionSheet": tag,
  "./FlowParts": tag,
  "./useOnboardingData": tag,
  "@/lib/onboarding/settings": {},
  "@/lib/onboarding/regions": {},
  "@/lib/api/onboarding": {},
  "@/lib/api/centers": {},
};
const mod = { exports: {} };
new Function("require", "module", "exports", code)(
  (name) => {
    assert.ok(name in imports, `unhandled import: ${name}`);
    return imports[name];
  },
  mod,
  mod.exports,
);
const { FindField } = mod.exports;

const resolve = (node) => {
  if (Array.isArray(node)) return node.map(resolve);
  if (!node || typeof node !== "object") return node;
  if (typeof node.type === "function") return resolve(node.type(node.props));
  return { ...node, props: { ...node.props, children: resolve(node.props.children) } };
};
const text = (node) =>
  Array.isArray(node)
    ? node.map(text).join("")
    : node && typeof node === "object"
      ? text(node.props.children)
      : typeof node === "string" || typeof node === "number"
        ? String(node)
        : "";
const buttons = (node, out = []) => {
  if (Array.isArray(node)) node.forEach((n) => buttons(n, out));
  else if (node && typeof node === "object") {
    if (node.type === "button" || node.type === "CtaButton") out.push(node);
    buttons(node.props.children, out);
  }
  return out;
};

const base = {
  query: "햇살",
  onQuery() {},
  settings: { regionProvince: "강원특별자치도", regionDistrict: "춘천시" },
  hint: "",
  onPick() {},
  onManual() {},
};

test("목록을 못 받았으면 「없어요 · 직접 적기」가 아니라 실패와 「다시 찾기」를 보인다", () => {
  let retried = 0;
  const tree = resolve(
    FindField({ ...base, results: [], failed: true, onRetry: () => (retried += 1) }),
  );
  const shown = text(tree);
  assert.match(shown, /목록을 불러오지 못했어요/);
  assert.doesNotMatch(shown, /없어요 ·|어린이집이 없어요/);
  assert.doesNotMatch(shown, /직접 적기/);
  const retry = buttons(tree).find((b) => text(b).includes("다시 찾기"));
  assert.ok(retry, "다시 찾기 단추가 있다");
  retry.props.onClick();
  assert.equal(retried, 1);
});

test("정상 응답이 비었을 때만 「없어요」와 「직접 적기」를 보인다", () => {
  const shown = text(resolve(FindField({ ...base, results: [], failed: false, onRetry() {} })));
  assert.match(shown, /어린이집이 없어요/);
  assert.match(shown, /직접 적기/);
  assert.doesNotMatch(shown, /불러오지 못했어요/);
});
