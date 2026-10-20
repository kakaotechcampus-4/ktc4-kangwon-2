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
