/**
 * 트렌드 화면 [계획안에 활용하기] → 트렌드를 쓰는 생성 화면의 요청 사항 칸 (api-spec §3-1 · ADR-072).
 *
 * 예전에는 연간 만들기(`/plans/annual/new`)로 갔다. 연간은 트렌드를 쓰지 않고(ADR-072 결정 1),
 * 그 화면은 `topic` 을 읽지 않아 메모가 비어 있었다.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { registerHooks } from "node:module";
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const ROOT = new URL("../", import.meta.url);

registerHooks({
  resolve(spec, ctx, next) {
    if (spec.startsWith("@/")) {
      const base = new URL(spec.slice(2), ROOT);
      for (const candidate of [base.href, base.href + ".ts", base.href + ".tsx"]) {
        if (existsSync(fileURLToPath(candidate))) return { url: candidate, shortCircuit: true };
      }
    }
    if (spec.startsWith(".") && ctx.parentURL) {
      const u = new URL(spec + ".ts", ctx.parentURL);
      if (existsSync(fileURLToPath(u))) return { url: u.href, shortCircuit: true };
    }
    return next(spec, ctx);
  },
});

const { trendPlanHref, topicMemo, TOPIC_MEMO_MAX } = await import("../lib/api/trends.ts");
const source = (path) => readFileSync(new URL(path, ROOT), "utf8");

const item = {
  source: "youtube",
  title: "가을 낙엽 놀이",
  summary: "낙엽을 모아 모양을 만들어요.",
  url: "https://www.youtube.com/watch?v=abc",
  published_at: "2026-10-02",
  origin: "꼬미쌤TV",
};

test("주간 만들기로 가고, 제목 · 요약만 넘긴다(링크는 넘기지 않는다)", () => {
  const href = trendPlanHref(item);
  const url = new URL(href, "http://x");
  assert.equal(url.pathname, "/plans/weekly");
  assert.equal(url.searchParams.get("topic"), "가을 낙엽 놀이\n낙엽을 모아 모양을 만들어요.");
  assert.ok(!href.includes("youtube"), "ADR-072: 링크는 LLM 에 넘기지 않는다");
});

test("요청 사항 상한(300자)을 넘기지 않는다", () => {
  const long = { ...item, summary: "가".repeat(400) };
  const topic = new URL(trendPlanHref(long), "http://x").searchParams.get("topic");
  assert.equal(topic.length, TOPIC_MEMO_MAX);
  assert.equal(TOPIC_MEMO_MAX, 300);
  // 요청 사항 칸의 상한과 같은 값이다.
  assert.match(source("components/plan-generator/PlanMemo.tsx"), /MEMO_MAX = 300\b/);
});

test("받는 쪽은 ?topic 을 그대로 요청 사항 첫 값으로 읽는다", () => {
  assert.equal(topicMemo("?topic=" + encodeURIComponent("가을 놀이\n낙엽")), "가을 놀이\n낙엽");
  assert.equal(topicMemo("?month=10"), "");
  assert.equal(topicMemo(""), "");
  assert.equal(topicMemo("?topic=" + "나".repeat(400)).length, TOPIC_MEMO_MAX);
});

test("트렌드 화면은 연간으로 보내지 않고, 주간 · 월간 만들기가 topic 을 읽는다 (문자열)", () => {
  assert.doesNotMatch(source("components/workspace/TrendsPage.tsx"), /plans\/annual/);
  for (const path of ["components/workspace/WeeklyNew.tsx", "components/workspace/MonthlyNew.tsx"])
    assert.match(source(path), /useClientState\(\s*\(\) => topicMemo\(/, path);
  // 놀이 중심형은 주간이 없어 월간으로 넘긴다 — 그때 요청 사항을 들고 간다.
  assert.match(source("components/workspace/WeeklyNew.tsx"), /\/plans\/monthly\?topic=/);
});
