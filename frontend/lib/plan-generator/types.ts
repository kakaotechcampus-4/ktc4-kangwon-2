export type AgeGroup = "3" | "4" | "5" | "mixed";

export type PlanType = "monthly" | "weekly" | "daily";

export type GenerationPhase = "idle" | "generating" | "done";

export interface MonthlyPeriod {
  month: number;
}

export interface WeeklyPeriod {
  month: number;
  week: number;
}

export interface DailyPeriod {
  date: string;
}

export interface PeriodState {
  monthly: MonthlyPeriod;
  weekly: WeeklyPeriod;
  daily: DailyPeriod;
}

export interface PlanGeneratorRequest {
  age: AgeGroup;
  planTypes: PlanType[];
  period: Partial<PeriodState>;
  memo: string;
}

export const AGE_LABEL: Record<AgeGroup, string> = {
  "3": "만 3세",
  "4": "만 4세",
  "5": "만 5세",
  mixed: "혼합반",
};

export const PLAN_TYPE_LABEL: Record<PlanType, string> = {
  monthly: "월간",
  weekly: "주간",
  daily: "일간",
};

export const PLAN_TYPE_HELP: Record<PlanType, string> = {
  monthly: "한 달 놀이 흐름",
  weekly: "한 주 세부 활동",
  daily: "하루 시간표",
};

export const GENERATION_STEPS = [
  "입력 조건 확인",
  "활동 주제 분석",
  "계획안 작성 중",
  "최종 확인",
] as const;
