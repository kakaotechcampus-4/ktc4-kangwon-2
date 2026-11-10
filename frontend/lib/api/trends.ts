import { apiRequest } from "./client";

/**
 * docs/api-spec.md §3-2. 주 1회 모아 **사람이 검사해 머지한** 자료다 (ADR-016).
 *
 * 화면에서 다시 거르지 않는다. 저장소에 남아 있는 것이 이미 통과한 것이다.
 */
export type TrendItem = {
  source: string;
  title: string;
  summary: string;
  url: string;
  published_at: string;
  origin: string;
};

/** `week` 는 어느 주에 모은 것인지다(2026-W42). 교사에게 그걸 보여줘야 한다. */
export type Trends = { week: string; items: TrendItem[] };

export const getTrends = () => apiRequest<Trends>("/api/trends");

/** 요청 사항 칸의 상한(ADR-060). `PlanMemo.tsx` 의 `MEMO_MAX` 와 같다 — 테스트가 맞춰 본다. */
export const TOPIC_MEMO_MAX = 300;

/**
 * [계획안에 활용하기] 가 가는 곳. 트렌드를 실제로 쓰는 생성은 주간 · 놀이 중심 월간뿐이다(ADR-072 결정 1).
 * 주간 만들기로 보내고, 놀이 중심형이면 그 화면이 월간 만들기로 넘긴다(주간이 없다).
 * 제목 · 요약만 넘긴다 — 링크는 LLM 에 넘기지 않는다(ADR-072 결정 2).
 */
export function trendPlanHref(item: Pick<TrendItem, "title" | "summary">): string {
  const topic = `${item.title}\n${item.summary}`.slice(0, TOPIC_MEMO_MAX);
  return `/plans/weekly?topic=${encodeURIComponent(topic)}`;
}

/** 생성 화면이 요청 사항 첫 값으로 읽는 `?topic`. 없으면 빈 문자열. */
export function topicMemo(search: string): string {
  return (new URLSearchParams(search).get("topic") ?? "").slice(0, TOPIC_MEMO_MAX);
}
