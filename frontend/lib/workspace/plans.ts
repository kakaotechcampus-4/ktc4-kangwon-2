import { AGE_LABEL, type AgeGroup, type PeriodState, type PlanType } from "../plan-generator/types";
import type { Template } from "./model";
export type PlanRow = { label: string; title: string; detail: string };
export type PlanContent = {
  annualPlanId?: number;
  rows: PlanRow[];
  origin: "ai" | "template";
  notes: string[];
};
export function planPeriod(type: PlanType, period: PeriodState) {
  const year = period.annual.year;
  const month = type === "weekly" ? period.weekly.month : period.monthly.month;
  const date = (y: number, m: number, d: number) =>
    `${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
  if (type === "annual")
    return { start: date(year, 3, 1), end: date(year + 1, 2, new Date(year + 1, 2, 0).getDate()) };
  if (type === "daily") return { start: period.daily.date, end: period.daily.date };
  const last = new Date(year, month, 0).getDate();
  if (
    type === "weekly" &&
    (!Number.isInteger(period.weekly.week) ||
      period.weekly.week < 1 ||
      period.weekly.week > Math.ceil(last / 7))
  )
    throw new Error("선택한 달에 없는 주차예요.");
  // 주차는 월의 1~7일, 8~14일 등 7일 단위로 정의한다.
  const startDay = type === "weekly" ? Math.min(last, (period.weekly.week - 1) * 7 + 1) : 1;
  return {
    start: date(year, month, startDay),
    end: date(year, month, type === "weekly" ? Math.min(last, startDay + 6) : last),
  };
}
export function templatePlan(
  type: PlanType,
  age: AgeGroup,
  period: PeriodState,
  memo: string,
  template?: Template,
  /** [3,5] 같은 실제 선택 연령 표기. 없으면 기존 AgeGroup 라벨을 쓴다. */
  ageLabel?: string,
): PlanContent {
  const ageText = ageLabel || AGE_LABEL[age];
  const months = [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2];
  const annualThemes = [
    "새로운 우리 반",
    "봄을 찾아요",
    "나와 우리 가족",
    "우리 동네",
    "여름과 물놀이",
    "건강한 여름",
    "함께하는 우리",
    "가을 자연 탐구",
    "생활 속 발견",
    "겨울과 나눔",
    "함께 자라는 우리",
    "즐거웠던 우리 반",
  ];
  const labels =
    type === "annual"
      ? months.map((m) => `${m}월`)
      : type === "monthly"
        ? ["1주", "2주", "3주", "4주", "5주 · 해당 시"]
        : type === "weekly"
          ? ["월요일", "화요일", "수요일", "목요일", "금요일"]
          : ["09:00", "10:00", "11:00", "12:00", "13:00"];
  const titles =
    type === "annual"
      ? annualThemes
      : type === "daily"
        ? ["등원 및 자유놀이", "관심 주제 탐색", "바깥 놀이", "점심 및 휴식", "오후 놀이 및 하원"]
        : [
            "관심 있는 것을 발견해요",
            "다양한 재료로 표현해요",
            "친구와 함께 놀아요",
            "놀이를 넓혀가요",
            "즐거웠던 놀이를 돌아봐요",
          ];
  return {
    origin: "template",
    notes: [
      "기본 양식으로 구성한 초안입니다. 입력한 요청사항은 메모로 보존되며, 구체적인 활동 반영은 직접 수정하거나 AI 연결 후 생성해주세요.",
    ],
    rows: labels.map((label, i) => ({
      label,
      title: titles[i],
      detail: template
        ? template.headings
            .map(
              (h) =>
                `${h}: ${h.includes("대상") ? ageText : h.includes("주제") ? titles[i] : "우리 반에 맞는 내용을 작성해주세요."}`,
            )
            .join("\n")
        : `놀이 목표: ${ageText}의 흥미와 경험을 바탕으로 ${titles[i]} 주제를 탐색해요.\n놀이 제안: 아이들이 고른 자료로 놀이하고, 다양한 표현을 시도할 수 있도록 공간을 준비해요.\n교사 지원: 안전한 자료와 충분한 시간을 제공하고, 아이들의 제안에 따라 활동을 조정해요.\n준비물: 활동에 맞는 안전한 놀이 자료\n${memo ? `교사 요청 메모: ${memo}` : "실행 후 아이들의 반응과 다음 지원을 기록해주세요."}`,
    })),
  };
}
