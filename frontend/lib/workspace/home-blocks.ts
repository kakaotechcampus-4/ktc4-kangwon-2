/**
 * 우리 반 첫 화면의 작은 쪽지들이 쓰는 셈.
 *
 * 화면에서 떼어 둔 것은 **날짜 경계**를 시험으로 잡기 때문이다. 주말 건너뛰기와 지난주
 * 월~일 구간은 눈으로 보고 맞다고 하기 어렵고, 틀리면 교사에게 「비어 있는 날」이
 * 엉뚱하게 뜬다.
 *
 * 날짜는 전부 `YYYY-MM-DD` 다. 셈은 UTC 로 한다 — 한국(UTC+9)에서 현지 시각으로 날짜를
 * 더하면 하루 밀린다 (`child-mark.ts` 의 `ymd` 와 같은 이유).
 */
import { weekStart } from "./child-mark";

/** 날짜를 `days` 만큼 옮긴다. 음수면 과거로 간다. */
export function shiftDays(date: string, days: number): string {
  const at = new Date(`${date}T00:00:00Z`);
  at.setUTCDate(at.getUTCDate() + days);
  const month = String(at.getUTCMonth() + 1).padStart(2, "0");
  const day = String(at.getUTCDate()).padStart(2, "0");
  return `${at.getUTCFullYear()}-${month}-${day}`;
}

/** 「10.23」 — 쪽지에 큰 글씨로 쓰는 날짜. */
export const shortDate = (date: string) => date.slice(5).replace("-", ".");

/** 월~금만 본다. 주간 교육계획이 월~금이고, 주말은 일지를 쓰지 않는다. */
function weekday(date: string): boolean {
  const day = new Date(`${date}T00:00:00Z`).getUTCDay();
  return day >= 1 && day <= 5;
}

/**
 * 일과가 하나도 없어 일지를 만들 수 없는, 제일 가까운 지난 평일. 없으면 `null`.
 *
 * **쓰기 시작한 날보다 앞은 보지 않는다**(`since`). 가입 첫날에 지난 2주가 전부 「비어 있는
 * 날」로 뜨면 그건 교사가 빠뜨린 것이 아니라 아직 쓰기 전이다 — 할 일처럼 보여 주면
 * 첫 화면이 빚 목록이 된다.
 *
 * `since` 는 **일과든 관찰이든 이 반에 처음 적은 날**이다. 일과 날짜만으로 정하면, 관찰은
 * 2주째 적는데 일과를 한 번도 안 적은 교사에게 아무것도 안 보인다 — 정작 그 사람에게
 * 보여야 하는 쪽지다.
 */
export function emptyDay(
  routineDates: readonly string[],
  since: string,
  today: string,
  back = 14,
): string | null {
  if (!since) return null;
  const filled = new Set(routineDates);
  for (let step = 1; step <= back; step += 1) {
    const date = shiftDays(today, -step);
    if (date < since) break;
    if (weekday(date) && !filled.has(date)) return date;
  }
  return null;
}

/** 이 반에 처음 적은 날. 일과와 관찰을 함께 본다. 아무것도 없으면 빈 문자열. */
export function firstWrittenDay(...groups: readonly string[][]): string {
  let earliest = "";
  for (const group of groups)
    for (const date of group) if (date && (!earliest || date < earliest)) earliest = date;
  return earliest;
}

/** 지난주 한 주의 모습. 기록이 한 건도 없으면 만들지 않는다. */
export interface LastWeek {
  /** 지난주 월요일 · 일요일. 쪽지에 구간을 적는다. */
  from: string;
  to: string;
  count: number;
  /** 제일 많이 적은 영역. 같은 수면 이름 순으로 앞선 것 — 새로고침마다 바뀌지 않게 한다. */
  domain: string;
  domainCount: number;
}

/**
 * 지난주(월~일) 돌아보기.
 *
 * **문장을 지어내지 않는다.** 「모으고 견주는 놀이가 늘었습니다」 같은 해석은 사람이나
 * AI 가 기록을 읽어야 나오는 말이고, 그건 주간 보육일지가 하는 일이다. 여기서는 센 것만
 * 돌려주고 화면이 숫자로 적는다.
 */
export function lastWeekLook(
  rows: readonly { date: string; domain: string }[],
  today: string,
): LastWeek | null {
  const from = shiftDays(weekStart(today), -7);
  const to = shiftDays(weekStart(today), -1);
  const tally = new Map<string, number>();
  let count = 0;
  for (const row of rows) {
    if (row.date < from || row.date > to) continue;
    count += 1;
    if (row.domain) tally.set(row.domain, (tally.get(row.domain) ?? 0) + 1);
  }
  if (!count) return null;
  let domain = "";
  let domainCount = 0;
  for (const [name, times] of [...tally].sort((a, b) => a[0].localeCompare(b[0], "ko")))
    if (times > domainCount) {
      domain = name;
      domainCount = times;
    }
  return { from, to, count, domain, domainCount };
}
