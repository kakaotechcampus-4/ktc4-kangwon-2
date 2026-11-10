/**
 * 아이마다 고정된 표식(쪽지 색)과 기록 요약.
 *
 * 아이 데이터에는 사진이 없다 (`ChildEntry` 는 id·이름뿐이다). 이름 글자만 깔아 놓으면
 * 열여덟 칸이 전부 비슷해 보여서, 교사가 매번 글자를 읽어야 아이를 찾는다. 이름 첫 글자를
 * 손글씨로 적은 작은 쪽지를 달아 두면 글자를 다 읽기 전에 자리가 먼저 눈에 들어온다.
 * 전에는 뜻 없는 도형이라 따로 외워야 했다.
 *
 * **색은 아이 id 로 정한다.** 목록 순서로 정하면 아이 한 명이 들어올 때 가나다 순서가
 * 밀려 이미 있던 아이들의 색이 전부 바뀐다 — 교사가 외운 자리가 그때마다 무너진다.
 */

/** 쪽지 색 가짓수. ChildPicker 의 색 목록(포스티 쪽지 색)과 같아야 한다. */
export const MARK_TONES = 7;

export interface ChildMark {
  /** 0 .. MARK_TONES-1 */
  tone: number;
}

/**
 * id 로 색을 고른다. 같은 id 면 늘 같은 색이다.
 *
 * id 끝이 번호면(`child-12`, 서버 번호) 그 번호로 돌린다 — 차례로 등록한 아이끼리
 * 색이 겹치지 않는다. 번호가 없으면 글자를 섞어 흩뜨린다.
 */
export function markFor(childId: string): ChildMark {
  const number = /(\d+)$/.exec(childId);
  if (number) return { tone: Number(number[1]) % MARK_TONES };
  let sum = 7;
  for (let i = 0; i < childId.length; i += 1) {
    sum = (sum * 31 + childId.charCodeAt(i)) % 100003;
  }
  return { tone: sum % MARK_TONES };
}

/** 한 글자 표식 — 성을 뺀 이름의 첫 글자. 두 글자 이름이면 첫 글자 그대로다. */
function oneLetter(name: string): string {
  const chars = Array.from(name.trim());
  return (chars.length >= 3 ? chars[1] : chars[0]) ?? "";
}

/**
 * 쪽지에 적는 글자. 평소에는 한 글자다.
 *
 * 같은 반(`classNames`)에 한 글자가 같은 아이가 있으면 **이름 끝 두 글자**로 쓴다 —
 * 정하린 · 김하늘이 둘 다 「하」면 표식으로 아이가 안 갈린다(점검 O-E1).
 */
export function markLetter(name: string, classNames: readonly string[] = []): string {
  const one = oneLetter(name);
  const own = name.trim();
  const clash = classNames.some((other) => other.trim() !== own && oneLetter(other) === one);
  if (!clash) return one;
  return Array.from(own).slice(-2).join("");
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

/**
 * 칠판 쪽지의 둘째 줄. 「2주째」 · 「9일째」 · 「아직 한 번도」
 *
 * 고르개의 `tallyLabel` 과 달리 **횟수를 쓰지 않는다** — 이 칸에 오는 아이는 모두
 * 0번이거나 그에 가까워서 「0번」이 모든 쪽지에 똑같이 붙는다. 알려줄 것은 얼마나
 * 오래 비었는가다. 두 주를 넘기면 일수보다 주가 읽기 쉽다.
 */
export function staleLabel(tally: ChildTally): string {
  if (tally.days === null) return "아직 한 번도";
  if (tally.days < 14) return `${tally.days}일째`;
  return `${Math.floor(tally.days / 7)}주째`;
}

/** 타일 둘째 줄. 「오늘 · 3번」 · 「9일 전 · 0번」 · 「아직 없어요」 */
export function tallyLabel(tally: ChildTally): string {
  if (tally.days === null) return "아직 없어요";
  const when = tally.days === 0 ? "오늘" : `${tally.days}일 전`;
  return `${when} · ${tally.week}번`;
}

/** 교실에서 부르는 이름 — 성을 떼고 받침이 있으면 「이」를 붙인다. 「김하늘」 → 「하늘이」, 「나래」 → 「나래」. */
export function calledName(name: string) {
  const chars = Array.from(name.trim());
  const given = chars.length >= 3 ? chars.slice(1).join("") : chars.join("");
  const last = given.charCodeAt(given.length - 1) - 0xac00;
  const closed = last >= 0 && last < 11172 && last % 28 !== 0;
  return `${given}${closed ? "이" : ""}`;
}
