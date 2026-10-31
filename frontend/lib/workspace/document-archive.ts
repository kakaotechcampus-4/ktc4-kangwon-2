/**
 * 문서 보관함(S-J5) 탐색 — 상태 판정과 기간 계산만 한다. 그리기는 하지 않는다.
 *
 * 여기 있는 함수는 전부 서버가 준 값에서만 답을 만든다. 화면이 상태를 지어내거나
 * 주차를 세기 시작하면 서버와 어긋나고, 어긋난 쪽이 교사 눈에 먼저 보인다.
 */

export type ArchiveStatus = "confirmed" | "draft" | "none";

export const ARCHIVE_STATUS_LABEL: Record<ArchiveStatus, string> = {
  confirmed: "확정",
  draft: "검토 중",
  none: "미작성",
};

/**
 * 목록에 보여 줄 상태. 셋뿐이다 — 확정 · 검토 중 · 미작성.
 *
 * **`stale` 을 보지 않는다.** 근거가 바뀐 확정본도 목록에서는 확정이다. 확정은 교사가 누른
 * 것이고 `stale` 은 별개 사실이라, 여기서 초안으로 끌어내리면 안 된다 (ADR-030).
 * 재확인 안내와 재확정은 **문서 상세 안에서** 그대로 돈다 — 그 길을 막지 않는다.
 */
export function archiveStatus(doc?: { status: "draft" | "confirmed" } | null): ArchiveStatus {
  if (!doc) return "none";
  return doc.status === "confirmed" ? "confirmed" : "draft";
}

/** 계획안 목록은 대문자 상태만 준다 — `stale` 이라는 개념이 없다. */
export const planStatus = (status: "DRAFT" | "CONFIRMED"): ArchiveStatus =>
  status === "CONFIRMED" ? "confirmed" : "draft";

const parse = (date: string) => {
  const [y, m, d] = date.split("-").map(Number);
  // 현지 시간으로 만든다. `new Date("2026-10-20")` 은 UTC 라 한국에서 하루 밀린다.
  return new Date(y, m - 1, d);
};
const iso = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

/** 그 날짜가 든 주(월~일) 7일. */
export function weekDays(date: string): string[] {
  const start = parse(date);
  start.setDate(start.getDate() - ((start.getDay() + 6) % 7));
  return Array.from({ length: 7 }, (_, i) => {
    const t = new Date(start);
    t.setDate(t.getDate() + i);
    return iso(t);
  });
}

export function shiftDays(date: string, days: number): string {
  const d = parse(date);
  d.setDate(d.getDate() + days);
  return iso(d);
}

/** `YYYY-MM` 을 앞뒤로 민다. 연도 넘김은 Date 가 처리한다. */
export function shiftMonth(month: string, delta: number): string {
  const [y, m] = month.split("-").map(Number);
  const d = new Date(y, m - 1 + delta, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export const monthOf = (date: string) => date.slice(0, 7);

export function monthLabel(month: string): string {
  const [y, m] = month.split("-").map(Number);
  return `${y}년 ${m}월`;
}

/**
 * 주간계획안의 머리글. **서버가 준 `week_id`(`YYYY-MM-Wn`) 를 읽기만 한다** —
 * 화면이 4주인지 5주인지 세지 않는다 (weekly-plan-contract §3-1).
 * 모양이 다르면 받은 값을 그대로 보여 준다.
 */
export function weekIdLabel(weekId: string): string {
  const m = /^(\d{4})-(\d{2})-W(\d+)$/.exec(weekId);
  return m ? `${m[1]}년 ${Number(m[2])}월 ${Number(m[3])}주차` : weekId;
}

/** 일지 쪽 주 탐색 머리글. **주차 번호를 짓지 않고** 날짜 범위로 적는다. */
export function weekRangeLabel(days: string[]): string {
  const first = parse(days[0]);
  const last = parse(days[days.length - 1]);
  const head = `${first.getFullYear()}년 ${first.getMonth() + 1}월 ${first.getDate()}일`;
  return first.getMonth() === last.getMonth()
    ? `${head} ~ ${last.getDate()}일`
    : `${head} ~ ${last.getMonth() + 1}월 ${last.getDate()}일`;
}

/** 어린이집 학년도는 3월에 시작한다 — 1 · 2월은 전년도다. */
export function schoolYearOf(date: string): number {
  const [y, m] = date.split("-").map(Number);
  return m >= 3 ? y : y - 1;
}

export const WEEKDAY = ["월", "화", "수", "목", "금", "토", "일"] as const;

/** `2026-10-20` → `10.20`. 날짜 칸은 좁다. */
export function shortDate(date: string): string {
  const [, m, d] = date.split("-").map(Number);
  return `${m}.${d}`;
}

/** 보관함이 한 화면에서 거르는 조건. 서버 상태를 바꾸지 않는 순수 계산이다. */
export type JournalView =
  | { kind: "dailyLog"; classId: string; day: string }
  | { kind: "weeklyLog"; classId: string; month: string }
  | { kind: "observation"; classId: string; childId: string; day: string };

type JournalDoc = {
  id: string;
  kind: string;
  classId: string;
  childId: string;
  start: string;
};

/**
 * 그 화면이 **실제로 보여 주는** 일지만 고른다.
 *
 * 반 · 종류 · 날짜(관찰일지는 아동까지)가 모두 맞아야 한다. 하나라도 빠지면 보육일지
 * 화면에 관찰일지가, 또는 다른 반의 문서가 섞인다 (실제로 났던 일).
 */
export function journalsInView<T extends JournalDoc>(docs: T[], view: JournalView): T[] {
  return docs.filter((d) => {
    if (d.classId !== view.classId || d.kind !== view.kind) return false;
    if (view.kind === "weeklyLog") return monthOf(d.start) === view.month;
    if (view.kind === "observation" && d.childId !== view.childId) return false;
    return d.start === view.day;
  });
}

/**
 * 지금 열어도 되는 문서. **화면이 보여 주는 목록 안에 없으면 열지 않는다** —
 * 종류를 바꿔도 남아 있던 선택이 엉뚱한 편집기를 띄우는 것을 막는다.
 */
export function openableIn<T extends JournalDoc>(
  docs: T[],
  view: JournalView | null,
  activeId: string,
): T | null {
  if (!view || !activeId) return null;
  return journalsInView(docs, view).find((d) => d.id === activeId) ?? null;
}

/** 보관함에서 기존 월간·주간 화면으로 넘기는 실제 문서 주소. 잘못된 쿼리는 무시한다. */
export function archivePlanEntry(search: string) {
  const query = new URLSearchParams(search);
  const id = Number(query.get("plan_id"));
  const classId = Number(query.get("class_id"));
  const weekId = query.get("week_id") ?? "";
  if (![id, classId].every((n) => Number.isSafeInteger(n) && n > 0)) return null;
  if (weekId && !/^\d{4}-(0[1-9]|1[0-2])-W[1-9]\d*$/.test(weekId)) return null;
  const month = weekId ? Number(weekId.slice(5, 7)) : Number(query.get("month"));
  if (!Number.isInteger(month) || month < 1 || month > 12) return null;
  return { id, classId, month, weekId };
}
