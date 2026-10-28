/**
 * 평가 서류 점검 — 교사가 고른 폴더의 파일 이름만 보고 검토문서가 있는지 센다.
 * 파일 내용은 읽지 않고, 서버로 보내지 않는다. 이름은 아동 실명을 담을 수 있어 어디에도 저장하지 않는다(ADR-013).
 * 서류 목록 · 기간은 「2024 개정 어린이집 평가 매뉴얼(2026.2)」 p.169 · p.171 · p.29 다(ADR-022 · ADR-045).
 */

/** 보육일지 · 계획안은 「평가월 1개월 전부터 전일까지」, 나머지는 「1년 이내」를 본다. */
export type Rule = { kind: "weekdays" } | { kind: "months" } | { kind: "count"; min: number };

export interface TeacherDoc {
  id: string;
  title: string;
  /** 공백을 뺀 소문자. 이 중 하나가 파일 이름에 있으면 그 서류로 본다. */
  keywords: string[];
  /** 이 단어가 있으면 키워드가 맞아도 빼낸다. 「연간 보육계획안」은 원장 몫, 「개별화교육계획안」은 다른 서류다. */
  exclude?: string[];
  rule: Rule;
  /** 장애영유아를 맡은 반만 해당한다. 해당 없는 반은 체크로 채운다. */
  optional?: boolean;
  basis: string;
  example: string;
  /** 이름만으로는 알 수 없는 것 */
  caveat?: string;
}

export const TEACHER_DOCS: TeacherDoc[] = [
  {
    id: "journal",
    title: "보육일지",
    keywords: ["보육일지"],
    rule: { kind: "weekdays" },
    basis: "4-1 · 지난달 1일부터 어제까지 평일마다",
    example: "2026-10-15_보육일지.hwp · 주간이면 2026-10-13_주간보육일지.hwp",
    caveat:
      "공휴일 · 방학도 빈 날로 보여요. 주간 일지는 이름에 「주간」과 그 주 월요일 날짜를 넣어 주세요.",
  },
  {
    id: "plan",
    title: "보육계획안 (월간 · 주간 · 일일 중 하나)",
    keywords: ["보육계획안", "월간계획안", "주간계획안", "일일계획안", "계획안"],
    exclude: ["연간", "개별화"],
    rule: { kind: "months" },
    basis: "4-1 · 지난달과 이번 달에 1건 이상",
    example: "2026-10_월간계획안.hwp",
  },
  {
    id: "assessment",
    title: "영유아 평가 기록",
    keywords: ["영유아평가", "유아평가", "발달평가"],
    rule: { kind: "count", min: 1 },
    basis: "4-2 · 1년 이내 · 아이마다 연 2회",
    example: "2026-09_영유아평가_1학기.hwp",
    caveat: "아이마다 2번 했는지는 이름으로 알 수 없어요. 건수만 세요.",
  },
  {
    id: "parent",
    title: "부모 개별면담 기록",
    keywords: ["부모면담", "개별면담", "학부모면담", "부모상담"],
    rule: { kind: "count", min: 1 },
    basis: "5-2 · 1년 이내 · 연 2회",
    example: "2026-04_부모면담.hwp",
    caveat: "아이마다 2번 했는지는 이름으로 알 수 없어요. 건수만 세요.",
  },
  {
    id: "training",
    title: "교육 이수증 · 수료증",
    keywords: ["이수증", "수료증"],
    rule: { kind: "count", min: 1 },
    basis: "5-3 · 1년 이내 · 연 1회 이상",
    example: "2026-05_놀이지원교육_수료증.pdf",
  },
  {
    id: "iep",
    title: "개별화교육계획",
    keywords: ["개별화교육계획", "iep"],
    rule: { kind: "count", min: 1 },
    optional: true,
    basis: "4-1 · 장애영유아를 맡은 반만",
    example: "2026-03_개별화교육계획.hwp",
  },
];

/** 원장님이 챙기는 서류와 평가 당일 내는 서류. 교사 폴더에는 보통 없어 검사하지 않는다. */
export const DIRECTOR_ITEMS = [
  { id: "operation-plan", title: "어린이집 운영계획", basis: "5-1 · 당해 연도" },
  { id: "annual-plan", title: "연간 보육계획안", basis: "5-1 · 당해 연도" },
  {
    id: "interaction-record",
    title: "담임교사 상호작용 관찰 · 지원 기록",
    basis: "5-3 · 1년 이내 연 1회",
  },
  {
    id: "duty-training",
    title: "보육교직원 직무교육 이수증",
    basis: "5-3 · 원장 · 담임 · 연장보육 전담교사",
  },
  {
    id: "day-papers",
    title: "평가 당일 서류 — 원아명단 · 실내외 배치도 · 하루일과표 · 경력 서류",
    basis: "현장평가 당일 제출",
  },
];

/** `~$보육일지.hwp` 같은 한글 · 오피스 임시 파일과 숨김 파일은 서류가 아니다. */
export function isIgnored(name: string) {
  const lower = name.toLowerCase();
  return (
    lower.startsWith("~$") ||
    lower.startsWith(".") ||
    lower.endsWith(".tmp") ||
    lower === "thumbs.db"
  );
}

function normalize(name: string) {
  return name
    .replace(/\.[^.]+$/, "")
    .toLowerCase()
    .replace(/\s+/g, "");
}

const pad = (n: number) => String(n).padStart(2, "0");
const iso = (y: number, m: number, d: number) => `${y}-${pad(m)}-${pad(d)}`;

function validDay(y: number, m: number, d: number) {
  const date = new Date(y, m - 1, d);
  return date.getFullYear() === y && date.getMonth() === m - 1 && date.getDate() === d;
}

export type FileDate = { kind: "day"; value: string } | { kind: "month"; value: string };

/** 이름에서 `2026-10-15` · `20261015` · `2026.10.15` · `2026_10` 같은 날짜를 찾는다. 처음 나온 것만 쓴다. */
export function parseDate(name: string): FileDate | null {
  const day = name.match(/(20\d{2})[-._ ]?(\d{2})[-._ ]?(\d{2})(?!\d)/);
  if (day) {
    const [y, m, d] = [Number(day[1]), Number(day[2]), Number(day[3])];
    if (validDay(y, m, d)) return { kind: "day", value: iso(y, m, d) };
  }
  const month = name.match(/(20\d{2})[-._ ]?(\d{1,2})(?!\d)/);
  if (month) {
    const [y, m] = [Number(month[1]), Number(month[2])];
    if (m >= 1 && m <= 12) return { kind: "month", value: `${y}-${pad(m)}` };
  }
  return null;
}

/** `date`(YYYY-MM-DD)를 현지 날짜로 읽는다. toISOString 은 UTC 라 쓰지 않는다. */
function toDate(value: string) {
  const [y, m, d] = value.split("-").map(Number);
  return new Date(y, m - 1, d);
}
const fromDate = (date: Date) => iso(date.getFullYear(), date.getMonth() + 1, date.getDate());

function addDays(value: string, days: number) {
  const date = toDate(value);
  date.setDate(date.getDate() + days);
  return fromDate(date);
}

export interface Windows {
  /** 지난달 1일 ~ 어제 (p.29 「현장평가월 이전 1개월부터 전일까지」, 오늘 평가한다고 본다) */
  recent: { from: string; to: string };
  /** 1년 전 다음 날 ~ 오늘 */
  year: { from: string; to: string };
}

export function windowsFor(today: string): Windows {
  const t = toDate(today);
  const from = new Date(t.getFullYear(), t.getMonth() - 1, 1);
  const yearAgo = new Date(t.getFullYear() - 1, t.getMonth(), t.getDate() + 1);
  return {
    recent: { from: fromDate(from), to: addDays(today, -1) },
    year: { from: fromDate(yearAgo), to: today },
  };
}

/** 월 단위 날짜는 그 달이 기간과 겹치면 기간 안으로 본다. */
function inWindow(date: FileDate, window: { from: string; to: string }) {
  if (date.kind === "day") return date.value >= window.from && date.value <= window.to;
  return date.value >= window.from.slice(0, 7) && date.value <= window.to.slice(0, 7);
}

function weekdaysBetween(from: string, to: string) {
  const days: string[] = [];
  for (let d = from; d <= to; d = addDays(d, 1)) {
    const weekday = toDate(d).getDay();
    if (weekday !== 0 && weekday !== 6) days.push(d);
  }
  return days;
}

function monthsBetween(from: string, to: string) {
  const months: string[] = [];
  for (let m = from.slice(0, 7); m <= to.slice(0, 7);) {
    months.push(m);
    const [y, mm] = m.split("-").map(Number);
    m = mm === 12 ? `${y + 1}-01` : `${y}-${pad(mm + 1)}`;
  }
  return months;
}

/** 주간 일지는 날짜가 든 그 주 월~금을 덮는다. */
function coveredDays(name: string, date: FileDate) {
  if (date.kind !== "day") return [];
  if (!normalize(name).includes("주간")) return [date.value];
  const weekday = toDate(date.value).getDay();
  const monday = addDays(date.value, weekday === 0 ? -6 : 1 - weekday);
  return [0, 1, 2, 3, 4].map((n) => addDays(monday, n));
}

export type Status = "found" | "partial" | "missing";

export interface DocResult {
  id: string;
  status: Status;
  /** 기간 안에서 센 파일 이름. 화면에만 보이고 저장하지 않는다. */
  matched: string[];
  /** 키워드는 맞는데 날짜가 없는 파일 */
  undated: string[];
  /** 기간 밖이라 세지 않은 파일 수 */
  outside: number;
  /** weekdays · months 규칙에서 빈 날 · 빈 달 */
  missing: string[];
}

export function matchesDoc(doc: TeacherDoc, name: string) {
  const n = normalize(name);
  return doc.keywords.some((k) => n.includes(k)) && !(doc.exclude ?? []).some((k) => n.includes(k));
}

export function checkDoc(doc: TeacherDoc, names: string[], today: string): DocResult {
  const windows = windowsFor(today);
  const window = doc.rule.kind === "count" ? windows.year : windows.recent;
  const result: DocResult = {
    id: doc.id,
    status: "missing",
    matched: [],
    undated: [],
    outside: 0,
    missing: [],
  };
  const days = new Set<string>();
  const months = new Set<string>();
  for (const name of names) {
    if (isIgnored(name) || !matchesDoc(doc, name)) continue;
    const date = parseDate(name);
    if (!date) {
      result.undated.push(name);
      continue;
    }
    if (!inWindow(date, window)) {
      result.outside += 1;
      continue;
    }
    result.matched.push(name);
    for (const d of coveredDays(name, date)) days.add(d);
    months.add(date.value.slice(0, 7));
  }
  if (doc.rule.kind === "weekdays") {
    const need = weekdaysBetween(window.from, window.to);
    result.missing = need.filter((d) => !days.has(d));
    result.status = !result.matched.length
      ? "missing"
      : result.missing.length
        ? "partial"
        : "found";
  } else if (doc.rule.kind === "months") {
    result.missing = monthsBetween(window.from, window.to).filter((m) => !months.has(m));
    result.status = !result.matched.length
      ? "missing"
      : result.missing.length
        ? "partial"
        : "found";
  } else {
    result.status = result.matched.length >= doc.rule.min ? "found" : "missing";
  }
  return result;
}

export interface Scan {
  total: number;
  results: DocResult[];
}

export function scanNames(names: string[], today: string): Scan {
  const files = names.filter((n) => !isIgnored(n));
  return { total: files.length, results: TEACHER_DOCS.map((doc) => checkDoc(doc, files, today)) };
}

/** 체크는 항목 id 만 이 브라우저에 남긴다(`doc:journal` · `director:annual-plan`). 파일 이름은 아동 실명을 담을 수 있어 남기지 않는다(ADR-013). */
function checksKey(centerId: number, schoolYear: number) {
  return `ssample:evaluation-files:${centerId}:${schoolYear}`;
}

export function readChecks(centerId: number, schoolYear: number): string[] {
  try {
    const value = JSON.parse(window.localStorage.getItem(checksKey(centerId, schoolYear)) ?? "[]");
    return Array.isArray(value) ? value.filter((v) => typeof v === "string") : [];
  } catch {
    return [];
  }
}

export function writeChecks(centerId: number, schoolYear: number, checks: string[]) {
  try {
    window.localStorage.setItem(checksKey(centerId, schoolYear), JSON.stringify(checks));
  } catch {
    // 저장이 막힌 브라우저에서도 화면의 체크는 유지한다.
  }
}

/** 이름으로 찾은 서류를 체크에 더한다. 교사가 이미 한 체크는 지우지 않는다. */
export function withFound(checks: string[], scan: Scan) {
  const found = scan.results.filter((r) => r.status === "found").map((r) => `doc:${r.id}`);
  return [...new Set([...checks, ...found])];
}
