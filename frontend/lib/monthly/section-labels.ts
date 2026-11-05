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
  // 서버가 Template 의 `habits` 를 Profile 쪽 이름인 `basic_habit` 으로 바꿔 내려준다
  // (`template_profiles/repository.py` `_TEMPLATE_KEY`). 둘 다 적어 둬야 어느 쪽이 와도
  // 한글로 뜬다 — 없으면 교사 화면에 기계 이름이 그대로 나온다.
  basic_habit: "기본생활습관",
  emergency_response: "비상대응",
  drill: "소방대피/재난대비",
  indoor_alternative: "실내 대체활동",
  // 바깥놀이 · 실내 대체활동의 주별 설명(ADR-066). 문서에는 안 나오고 「칸 편집」 · 변경 이력에만 뜬다.
  outdoor_play_detail: "바깥놀이 설명",
  indoor_alternative_detail: "실내 대체활동 설명",
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

/** 안전교육 칸 「[주제] - 내용」을 「[주제]」 아래 줄에 내용으로 — 놀이 월간과 같은 모양. */
export const safetyLines = (text: string) => text.replace(/^(\[[^\]\n]+\]) - /, "$1\n");

/** 넣은 훈련 칸의 글 — 서버처럼 「[주제] 문장」 한 줄(2026-11-06). */
export const drillText = (d: { label: string; cell: { value: string } }) =>
  `[${d.label}] ${d.cell.value}`;
