/**
 * 주간계획안 칸 이름을 교사의 말로 바꾼다.
 *
 * 월간과 같은 이유다 (`lib/monthly/section-labels.ts`) — 서버는 `basic_habit` 같은
 * 기계 이름을 주고, 기반 Template 의 `label` 도 지금은 그 이름과 같다.
 *
 * **월간 표를 그대로 쓰지 않는다.** 겹치는 이름이 많지만 기본생활습관의 키가 다르고
 * (월간 `habits` · 주간 `basic_habit`, 계약 §5-2), 주간에만 있는 칸이 셋이다.
 * 한쪽을 고칠 때 다른 쪽이 조용히 따라 바뀌면 안 된다.
 */
export const SECTION_LABELS: Record<string, string> = {
  theme: "놀이 주제",
  focus: "소주제",
  goals: "목표",
  basic_habit: "기본생활습관",
  safety_education: "안전교육",
  indoor_play: "실내자유놀이",
  group_activity: "대·소집단활동",
  outdoor_play: "바깥놀이",
  indoor_alternative: "대체놀이",
  family_link: "가정 연계",
  event_schedule: "행사",
  special_program: "특별활동",
};

/** 띄울 이름. 표에 없으면 서버가 준 이름을 그대로 쓴다 — 지어내지 않는다. */
export const sectionName = (key: string, label?: string | null): string =>
  SECTION_LABELS[key] ?? label ?? key;

/** 요일 한 글자. `operating_days` 순서를 그대로 따른다. */
export const DAY_NAMES: Record<string, string> = {
  MON: "월",
  TUE: "화",
  WED: "수",
  THU: "목",
  FRI: "금",
  SAT: "토",
};
