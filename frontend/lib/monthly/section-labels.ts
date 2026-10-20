/**
 * 월간계획안 칸 이름을 교사의 말로 바꾼다.
 *
 * **서버는 `theme` · `week_axis` 처럼 기계 이름을 준다.** 기반 Template 의 `label` 이
 * 지금은 그 이름과 같아서(docs/api-spec.md §9-4), 그대로 띄우면 교사가 영어 식별자를
 * 읽게 된다.
 *
 * 화면 이름은 Profile 을 만들 때 `display_labels` 로 우리가 정해 보낸다. 이 표가 그
 * 출처이고, 화면에 띄울 때도 같은 표를 쓴다 — 보내는 값과 띄우는 값이 어긋나지 않게
 * 한 곳에 둔다.
 */
export const SECTION_LABELS: Record<string, string> = {
  theme: "놀이 주제",
  week_axis: "주차",
  outdoor_play: "바깥놀이",
  safety_education: "안전교육",
  focus: "소주제",
  goals: "목표",
  habits: "기본생활습관",
  emergency_response: "비상대응",
  drill: "소방대피 훈련",
  indoor_alternative: "실내 대체활동",
  special_program: "특성화 활동",
  event_schedule: "행사 일정",
  daily_routine: "일과",
  community_link: "지역 연계",
  family_link: "가정 연계",
};

/**
 * 띄울 이름. 표에 없으면 서버가 준 이름을 그대로 쓴다 — 지어내지 않는다.
 *
 * 서버 `label` 보다 이 표를 먼저 본다. 이 표를 넣기 전에 만든 Profile 은 `label` 이
 * 기계 이름이라, 서버 값을 먼저 보면 옛 Profile 만 영어로 남는다.
 */
export const sectionName = (key: string, label?: string | null): string =>
  SECTION_LABELS[key] ?? label ?? key;
