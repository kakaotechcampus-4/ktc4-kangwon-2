/**
 * 아이마다 고정된 표식(도형·색)과 기록 요약.
 *
 * 아이 데이터에는 사진이 없다 (`ChildEntry` 는 id·이름뿐이다). 이름 글자만 깔아 놓으면
 * 열여덟 칸이 전부 비슷해 보여서, 교사가 매번 글자를 읽어야 아이를 찾는다. 도형과 색을
 * 하나씩 달아 두면 글자를 읽기 전에 자리가 먼저 눈에 들어온다.
 *
 * **표식은 아이 id 로 정한다.** 목록 순서로 정하면 아이 한 명이 들어올 때 가나다 순서가
 * 밀려 이미 있던 아이들의 도형이 전부 바뀐다 — 교사가 외운 자리가 그때마다 무너진다.
 */

/** 도형 가짓수. ChildPicker 의 도형 목록과 같아야 한다. */
export const MARK_SHAPES = 6;
/** 색 가짓수. 셋만 쓴다 — 더 늘리면 크림·흰 바탕에서 명암비가 모자란 색이 끼게 된다. */
export const MARK_TONES = 3;

export interface ChildMark {
  /** 0 .. MARK_SHAPES-1 */
  shape: number;
  /** 0 .. MARK_TONES-1 */
  tone: number;
}

/** id 글자를 섞어 흩뜨린다. 같은 id 면 늘 같은 표식이 나온다. */
export function markFor(childId: string): ChildMark {
  let sum = 7;
  for (let i = 0; i < childId.length; i += 1) {
    sum = (sum * 31 + childId.charCodeAt(i)) % 100003;
  }
  return {
    shape: sum % MARK_SHAPES,
    tone: Math.floor(sum / MARK_SHAPES) % MARK_TONES,
  };
}

/** 한 아이의 기록 상태. */
export interface ChildTally {
  /** 마지막 기록이 며칠 전인지. 한 번도 없으면 null. */
  days: number | null;
  /** 이번 주(월요일부터 오늘까지)에 적은 횟수. */
  week: number;
}

/** 한 주를 월요일에 시작한다 — 주간 교육계획이 월~금이다. */
export function weekStart(date: string): string {
  const day = new Date(`${date}T00:00:00Z`);
  // getUTCDay: 일요일 0. 월요일을 0 으로 옮긴다.
  day.setUTCDate(day.getUTCDate() - ((day.getUTCDay() + 6) % 7));
  return ymd(day);
}

/**
 * 날짜를 `YYYY-MM-DD` 로 적는다.
 *
 * `toISOString()` 을 쓰면 안 된다. 한국은 UTC+9 라서 그 자리의 자정이 UTC 로는 전날
 * 오후 세 시다 — 날짜가 하루 밀린다. UTC 로 계산하고 UTC 로 적는다.
 */
function ymd(date: Date): string {
  const month = String(date.getUTCMonth() + 1).padStart(2, "0");
  const day = String(date.getUTCDate()).padStart(2, "0");
  return `${date.getUTCFullYear()}-${month}-${day}`;
}

/** 두 날짜 사이의 날 수. 같은 날이면 0. */
export function daysBetween(from: string, to: string): number {
  const a = Date.parse(`${from}T00:00:00Z`);
  const b = Date.parse(`${to}T00:00:00Z`);
  return Math.round((b - a) / 86400000);
}

/** 아이 하나의 기록을 센다. 넘기는 목록은 이미 그 반으로 좁혀진 것이어야 한다. */
export function tallyFor(
  rows: readonly { childId: string; date: string }[],
  childId: string,
  today: string,
): ChildTally {
  const start = weekStart(today);
  let week = 0;
  let last = "";
  for (const row of rows) {
    if (row.childId !== childId) continue;
    if (row.date >= start && row.date <= today) week += 1;
    if (row.date > last) last = row.date;
  }
  return { days: last ? daysBetween(last, today) : null, week };
}

/** 한 주 넘게 비어 있으면 눈에 띄게 한다. 한 번도 없는 아이가 제일 급하다. */
export const STALE_DAYS = 7;

export function isStale(tally: ChildTally): boolean {
  return tally.days === null || tally.days >= STALE_DAYS;
}

/** 타일 둘째 줄. 「오늘 · 3번」 · 「9일 전 · 0번」 · 「아직 없어요」 */
export function tallyLabel(tally: ChildTally): string {
  if (tally.days === null) return "아직 없어요";
  const when = tally.days === 0 ? "오늘" : `${tally.days}일 전`;
  return `${when} · ${tally.week}번`;
}
