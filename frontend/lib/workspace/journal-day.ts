/**
 * 보육일지 하루 화면의 규칙 — 계획안 후보 · 관찰 이름 빼기 · 날씨 칩 · 깐 줄 안내.
 *
 * 모두 **교사가 눌러야 들어가는 것**을 고르는 규칙이다. 화면이 스스로 사실 칸을 채우지 않는다
 * (ADR-086 · 3차 점검 1-3). 화면 코드와 떼어 둔 것은 규칙만 따로 시험하려고다.
 */
import type { WeeklyPlan } from "@/lib/api/types";
import type { DayPreset, DayWeather } from "@/lib/api/routines";

const WEEK = ["일", "월", "화", "수", "목", "금", "토"];
const DAY_CODE = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"];

/** `date` 는 시간대가 없는 `YYYY-MM-DD` 다. UTC 로 읽어야 요일이 밀리지 않는다. */
const weekday = (date: string) => new Date(`${date}T00:00:00Z`).getUTCDay();

/** 「11월 3일 (화)」 — 화면 날짜 표기(시안 기준). */
export function dayLabel(date: string) {
  const at = new Date(`${date}T00:00:00Z`);
  return `${at.getUTCMonth() + 1}월 ${at.getUTCDate()}일 (${WEEK[at.getUTCDay()]})`;
}

/** 그날이 든 주간계획안. 표시 마지막 날(토요일 운영이면 토요일)까지 본다. */
export function planOfDay(plans: WeeklyPlan[], date: string): WeeklyPlan | null {
  return plans.find((p) => p.week_period.start_date <= date && date <= p.display_end_date) ?? null;
}

/** 한 칸 글을 후보로 쪼갠다. 칸 하나에 활동이 줄마다 적혀 있을 수 있다. */
const lines = (value: string) =>
  value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);

export interface DayPlan {
  /** 요일 칸이 있는 대·소집단 활동 · 특별활동의 그날 값. */
  group: string[];
  special: string[];
  /** 「계획 보기」에 펼 것 — 그날 칸과 주 전체 칸, 묶음 이름별로. */
  all: { label: string; values: string[] }[];
}

export function dayPlan(plan: WeeklyPlan, date: string): DayPlan {
  const code = DAY_CODE[weekday(date)];
  const sections = [...plan.sections]
    .filter((s) => s.visible)
    .sort((a, b) => a.order - b.order)
    .map((s) => ({
      key: s.section_key,
      label: s.label ?? s.section_key,
      // 요일 칸이면 그날 칸만, 아니면 주 전체 칸.
      values: s.cells
        .filter((c) => s.repeat_by !== "DAY" || c.day === code)
        .flatMap((c) => lines(c.value)),
    }));
  const of = (key: string) => sections.find((s) => s.key === key)?.values ?? [];
  return {
    group: of("group_activity"),
    special: of("special_program"),
    all: sections.filter((s) => s.values.length).map(({ label, values }) => ({ label, values })),
  };
}

/**
 * 회색 후보를 띄울 줄인가 — 「특별활동」 줄은 특별활동 칸, 「활동」 줄은 대·소집단 활동 칸.
 *
 * 일과 이름은 교사가 자유롭게 적는다(ADR-025). 「오전 실내놀이」처럼 놀이 줄은 계획안에
 * 요일 칸이 없어(실내 자유놀이는 주 전체 목록) 후보를 정할 수 없다 — 「계획 보기」로 고른다.
 */
export function planCandidates(rowName: string, plan: DayPlan | null): string[] {
  if (!plan) return [];
  const name = rowName.replace(/\s/g, "");
  if (name.includes("특별활동")) return plan.special;
  if (name.includes("활동") && !name.includes("놀이")) return plan.group;
  return [];
}

/** 관찰의 상황(「실내놀이, 쌓기」)이 이 일과 줄의 것인가. 관찰에는 시각이 없어 이름으로만 잇는다. */
export function contextMatches(context: string, rowName: string) {
  const head = context.split(",")[0].replace(/\s/g, "");
  const name = rowName.replace(/\s/g, "").replace(/\(.*\)$/, "");
  return Boolean(head && name) && (name.includes(head) || head.includes(name));
}

// 두 글자 성. 한 글자로 끊으면 「남궁민수」가 「궁민수」가 된다 (backend shared/childCode/names.py 와 같다).
const TWO_SYLLABLE_SURNAMES = new Set([
  "남궁",
  "황보",
  "제갈",
  "사공",
  "선우",
  "서문",
  "독고",
  "동방",
  "망절",
]);

/** 등록 이름과 성을 뗀 이름. 성을 떼고 두 글자 이상 남을 때만 뗀다 (서버와 같은 규칙). */
function variants(full: string) {
  const name = full.trim();
  const surname = TWO_SYLLABLE_SURNAMES.has(name.slice(0, 2)) ? 2 : name.length >= 3 ? 1 : 0;
  return surname && name.length - surname >= 2 ? [name, name.slice(surname)] : [name];
}

const escape = (text: string) => text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/**
 * 관찰 글에서 반 아이 이름을 「○○」로 뺀다. 「가람이가」의 부르는 「이」까지 같이 뺀다.
 *
 * **고쳐 쓰지 않는다** — 조사가 어색하게 남아도 그대로 둔다. 넣은 뒤 교사가 고친다(3차 점검 1-9).
 * 외자 이름(「솔」)은 지우면 아무 「솔」이나 지워져 문장이 망가진다. 지우지 않고 「솔이」처럼
 * 부르는 꼴을 `suspects` 로 돌려준다 — 화면이 노랗게 짚는다.
 */
export function withoutNames(text: string, names: string[]) {
  const all = [...new Set(names.filter((n) => n.trim()).flatMap(variants))].sort(
    (a, b) => b.length - a.length,
  );
  const masked = all
    .filter((name) => name.length >= 2)
    .reduce((out, name) => out.replace(new RegExp(`${escape(name)}이?`, "g"), "○○"), text);
  // 두 글자 등록 이름(「박솔」)은 성 + 외자로 본다. 교사는 「솔이」라고 부른다.
  const suspects = names
    .map((name) => name.trim())
    .filter((name) => name.length === 1 || name.length === 2)
    .map((name) => `${name.slice(-1)}이`)
    .filter((call) => masked.includes(call));
  return { text: masked, suspects: [...new Set(suspects)] };
}

/** 특이사항에 넣을 대체놀이 한 줄. 비 · 눈이면 그 말로, 미세먼지 나쁨 이상이면 미세먼지로. */
export function indoorNote(weather: DayWeather | null): string | null {
  if (!weather?.indoor_hint) return null;
  if (weather.indoor_hint === "dust") return "미세먼지로 실내 대체놀이";
  const sky = weather.sky ?? "비";
  return `${sky}${sky.endsWith("눈") ? "으로" : "로"} 실내 대체놀이`;
}

/** 바깥놀이 줄에 「바깥놀이(대체)」 칩을 띄울까. 이미 「(대체)」면 띄우지 않는다. */
export function needsOutdoorSwap(rowName: string, hint: DayWeather["indoor_hint"]) {
  return Boolean(hint) && rowName.includes("바깥놀이") && !rowName.includes("대체");
}

/** 「반 기본 일과표로 깔았어요」 · 「11월 3일 (월) 일과로 깔았어요」. */
export function presetNote(preset: DayPreset | null | undefined) {
  if (!preset) return "";
  if (preset.source === "template" || !preset.from_date) return "반 기본 일과표로 깔았어요";
  return `${dayLabel(preset.from_date)} 일과로 깔았어요`;
}

/** 넣는 글을 줄을 바꿔 덧붙인다. 비었으면 그대로 넣는다. */
export const appendLine = (current: string, text: string) =>
  current.trim() ? `${current.replace(/\s+$/, "")}\n${text}` : text;
