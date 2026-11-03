// 월간 만들기(Ⓜ1): 처음 고를 달 · 연간에서 이어받는 것 · 달 버튼과 만들기 버튼, 놀이형 판별.
import assert from "node:assert/strict";
import { test } from "node:test";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";

const require = createRequire(import.meta.url);
function load(path, modules) {
  const code = require("next/dist/compiled/babel/core").transformSync(
    readFileSync(new URL(path, import.meta.url), "utf8"),
    {
      filename: path,
      babelrc: false,
      configFile: false,
      presets: [
        [require("next/dist/compiled/babel/preset-env"), { targets: { node: "current" } }],
        [require("next/dist/compiled/babel/preset-react"), { runtime: "automatic" }],
        require("next/dist/compiled/babel/preset-typescript"),
      ],
    },
  ).code;
  const m = { exports: {} };
  new Function("require", "module", "exports", code)((n) => modules[n] ?? require(n), m, m.exports);
  return m.exports;
}
const { renderToStaticMarkup } = require("react-dom/server");
const React = require("react");
const { isPlayAnnual } = load("../lib/monthly/play-entry.ts", {});
const MONTH_ORDER = [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2];
const stub = () => null;
const monthlyLabels = load("../lib/monthly/section-labels.ts", {});
const {
  MonthlyNewView,
  firstOpenMonth,
  inheritOf,
  pickTemplate,
  firstExtras,
  sameColumns,
  profileInput,
} = load("../components/workspace/MonthlyNew.tsx", {
  react: React,
  "next/link": {
    __esModule: true,
    default: ({ href, children }) => React.createElement("a", { href }, children),
  },
  "next/navigation": { useRouter: () => ({}) },
  "@/lib/api/client": { ApiError: class {} },
  "@/lib/api/monthly": {},
  "@/lib/api/playMonthly": {},
  "@/lib/api/plans": {},
  "@/lib/api/onboarding": {},
  "@/lib/api/templateProfiles": {},
  "@/lib/monthly/section-labels": monthlyLabels,
  "@/lib/onboarding/settings": {},
  "@/lib/onboarding/types": { MONTH_ORDER, ageSelectionLabel: stub, selectedAgesFor: stub },
  "@/lib/hooks/use-client-state": { useClientState: stub },
  "@/components/plan-generator/playProjectPagination": { playSeason: (p) => ({ name: p.label }) },
  "@/components/plan-ui/GenerationRing": { __esModule: true, default: stub },
  "@/components/plan-generator/PlanMemo": { PlanMemoField: stub, memoError: stub },
  "@/components/app/compact-shell": { useCompactShell: stub },
  "./WorkspaceUI": { useClasses: stub },
});

test("놀이형 판별: 놀이형만 참, 목록 실패(null) · 월별 주제형 · 빈 목록은 기존 화면", () => {
  assert.equal(isPlayAnnual({ items: [{ format: "PLAY_PROJECT" }] }), true);
  assert.equal(isPlayAnnual({ items: [{ format: "MONTHLY_THEME" }] }), false);
  assert.equal(isPlayAnnual({ items: [] }), false);
  assert.equal(isPlayAnnual(null), false);
});

test("처음 고를 달: 이번 달부터 학년도 순서로 빈 달, 해를 넘겨 2월 뒤 3월로", () => {
  const d = (id) => ({ id, status: "DRAFT" });
  assert.equal(firstOpenMonth(11, {}), 11);
  assert.equal(firstOpenMonth(11, { 11: d(1), 12: d(2) }), 1);
  assert.equal(firstOpenMonth(2, { 2: d(1) }), 3);
  const all = Object.fromEntries(MONTH_ORDER.map((m) => [m, d(m)]));
  assert.equal(firstOpenMonth(11, all), 11);
});

test("이어받기: 주제형은 생활주제 · 소주제, 놀이형은 그 계절에 고른 놀이를 고른 순서로", () => {
  const theme = {
    format: "MONTHLY_THEME",
    months: [{ month: 4, theme: "봄", sub_themes: ["a", "b"] }],
  };
  assert.deepEqual(inheritOf(theme, 4), { kind: "theme", theme: "봄", subs: ["a", "b"] });
  assert.equal(inheritOf(theme, 5), null);
  assert.equal(inheritOf(null, 4), null);
  const c = (k, n) => ({ row_key: k, play_name: { value: n } });
  const play = {
    format: "PLAY_PROJECT",
    periods: [
      {
        label: "가을",
        months: [9, 10, 11],
        selected: ["c2", "c1", "gone"],
        candidates: [c("c1", "낙엽"), c("c2", "도토리")],
      },
    ],
  };
  assert.deepEqual(inheritOf(play, 10), {
    kind: "play",
    season: "가을",
    plays: [
      { row_key: "c2", name: "도토리" },
      { row_key: "c1", name: "낙엽" },
    ],
  });
});

test("화면: 확정한 달은 잠김, 작성 중 표시, 있는 달은 열기, 막힌 까닭이면 버튼 잠김", () => {
  const view = (p) =>
    renderToStaticMarkup(
      MonthlyNewView({
        play: true,
        meta: "",
        back: { href: "/plans", label: "계획안" },
        month: 12,
        plans: { 10: { id: 1, status: "CONFIRMED" }, 11: { id: 2, status: "DRAFT" } },
        inherit: { kind: "play", season: "가을", plays: [{ row_key: "c1", name: "낙엽" }] },
        focus: ["c1"],
        blocked: null,
        problem: "",
        onMonth() {},
        onFocus() {},
        onCreate() {},
        ...p,
      }),
    );
  const out = view({});
  assert.match(out, /disabled=""[^>]*>10월<span[^>]*>✓ 확정/);
  assert.match(out, /11월<span[^>]*>작성 중/);
  assert.match(out, /type="checkbox"[^>]*checked=""/);
  assert.match(out, /<button type="button" class="min-h-\[54px\][^"]*">12월 월간계획안 만들기/);
  assert.match(view({ month: 11 }), /11월 월간계획안 열기/);
  const blocked = view({ blocked: "연간을 먼저 확정해 주세요.", problem: "실패" });
  assert.match(
    blocked,
    /disabled=""[^>]*>12월 월간계획안 만들기<\/button><p[^>]*>연간을 먼저 확정해 주세요/,
  );
  assert.match(blocked, /role="alert"[^>]*>실패/);
});

test("월별 주제형 칸 고르기: 기반 양식 · 처음 켤 칸 · 같은 양식 재사용 · 시작 요청", () => {
  const sec = (section_key, selection, repeat_by = "WEEK") => ({
    section_key,
    label: null,
    role: "CONTENT",
    repeat_by,
    selection,
  });
  const tpl = (v, approved = true) => ({
    template_ref: { template_id: "a", template_version: v },
    approved,
    sections: [
      sec("theme", "REQUIRED", "NONE"),
      sec("focus", "OPTIONAL"),
      sec("goals", "OPTIONAL", "NONE"),
      sec("drill", "INSTITUTION_INPUT"),
    ],
    focus_variants: ["EXPECTED_PLAY", "SUBTHEME"],
  });
  const items = [tpl("v0.2.1"), tpl("v0.10.0", false), tpl("v0.1.1")];
  const current = {
    profile_ref: { profile_id: "p", profile_version: 1 },
    base_template_ref: { template_id: "a", template_version: "v0.1.1" },
    selected_optional_keys: ["focus", "drill"],
  };
  assert.equal(pickTemplate(items).template_ref.template_version, "v0.2.1");
  assert.equal(pickTemplate([tpl("v1", false)]), null);
  const t = pickTemplate(items);
  assert.deepEqual(firstExtras(t, current), ["focus"]);
  // 지금 양식이 옛 판이면 같은 칸이라도 최신 판으로 새로 만든다.
  assert.equal(sameColumns({ ...current, selected_optional_keys: ["focus"] }, t, ["focus"]), false);
  const latest = {
    ...current,
    base_template_ref: t.template_ref,
    selected_optional_keys: ["focus"],
  };
  assert.equal(sameColumns(latest, t, ["focus"]), true);
  assert.equal(sameColumns(latest, t, ["goals"]), false);
  assert.equal(sameColumns(null, t, []), false);
  const input = profileInput(t, ["focus"]);
  assert.deepEqual(Object.keys(input.display_labels), ["theme", "focus"]);
  assert.equal(input.focus_variant, "SUBTHEME");
  assert.equal(profileInput(t, ["goals"]).focus_variant, null);
  const out = renderToStaticMarkup(
    MonthlyNewView({
      play: false,
      meta: "",
      back: { href: "/plans", label: "계획안" },
      month: 12,
      plans: {},
      inherit: null,
      focus: [],
      template: t,
      extras: ["goals"],
      blocked: null,
      problem: "",
      onMonth() {},
      onFocus() {},
      onCreate() {},
    }),
  );
  assert.match(out, /어떤 칸을 넣을까요\?/);
  assert.equal((out.match(/type="checkbox"[^>]*checked=""/g) ?? []).length, 1);
  assert.doesNotMatch(out, />drill</);
});
