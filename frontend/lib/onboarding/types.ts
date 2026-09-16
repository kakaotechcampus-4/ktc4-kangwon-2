import type { AgeGroup } from "@/lib/plan-generator/types";

export type { AgeGroup };

/** 온보딩 4단계 + 완료 */
export type OnboardingStep = 1 | 2 | 3 | 4 | "done";

export interface ChildEntry {
  code?: string;
  id: string;
  name: string;
}

export type SelectedAge = 3 | 4 | 5;
export interface ClassroomEntry {
  selectedAges?: SelectedAge[];
  id: string;
  className: string;
  ageGroup: AgeGroup | "";
  currentChildCount: number | "";
  teacherName: string;
  guardianConsent: boolean;
  childrenSkipped: boolean;
  children: ChildEntry[];
}

/** 3월 → 다음 해 2월 순서 (어린이집 학사 연도) */
export const MONTH_ORDER = [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2] as const;
export type Month = (typeof MONTH_ORDER)[number];

export type CharacterMessages = Record<Month, string>;

/** 기본 제공 월별 성품인사 — 사용자가 그대로 쓰거나 문구를 수정할 수 있다. */
export const DEFAULT_CHARACTER_MESSAGES: CharacterMessages = {
  3: "경청하는 어린이가 되겠습니다.",
  4: "긍정적인 어린이가 되겠습니다.",
  5: "기쁨을 나누는 어린이가 되겠습니다.",
  6: "친구를 배려하는 어린이가 되겠습니다.",
  7: "감사하는 어린이가 되겠습니다.",
  8: "스스로 참고 기다리는 어린이가 되겠습니다.",
  9: "약속을 잘 지키는 어린이가 되겠습니다.",
  10: "새롭게 생각하는 어린이가 되겠습니다.",
  11: "솔직하게 말하는 어린이가 되겠습니다.",
  12: "끝까지 해내는 어린이가 되겠습니다.",
  1: "어른 말씀을 잘 듣는 어린이가 되겠습니다.",
  2: "바르게 판단하는 어린이가 되겠습니다.",
};

/**
 * 온보딩에서 저장되어 이후 계획안 생성에 재사용되는 설정.
 * 팀 화면 명세의 원 정보 / 반 정보 / 성품인사 요구사항을 반영한다.
 */
export interface ClassSettings {
  primaryClassId?: string;
  orgName: string;
  directorName: string;
  regionProvince: string;
  regionDistrict: string;
  classes: ClassroomEntry[];
  characterEducationEnabled: boolean;
  characterMessages: CharacterMessages;
  completedAt?: string;
}

export function createEmptyClassroom(id = "class-1"): ClassroomEntry {
  return {
    id,
    className: "",
    ageGroup: "",
    currentChildCount: "",
    teacherName: "",
    guardianConsent: false,
    childrenSkipped: false,
    children: [],
  };
}

export const EMPTY_CLASS_SETTINGS: ClassSettings = {
  orgName: "",
  directorName: "",
  regionProvince: "",
  regionDistrict: "",
  classes: [createEmptyClassroom()],
  characterEducationEnabled: true,
  characterMessages: { ...DEFAULT_CHARACTER_MESSAGES },
};

/** 반 정보와 계획안 생성에서 사용하는 연령 선택지. */
export const AGE_OPTIONS: { value: AgeGroup; label: string }[] = [
  { value: "3", label: "3세" },
  { value: "4", label: "4세" },
  { value: "5", label: "5세" },
  { value: "mixed", label: "혼합" },
];

export const STEP_LABELS: Record<Exclude<OnboardingStep, "done">, string> = {
  1: "원 정보",
  2: "반 정보",
  3: "아동 명단",
  4: "성품인사",
};

/** Explicit empty selection stays empty; only legacy values use migration. */
export function selectedAgesFor(value: {
  selectedAges?: unknown;
  ageGroup?: unknown;
}): SelectedAge[] {
  if (Array.isArray(value.selectedAges))
    return [3, 4, 5].filter(
      (age) => value.selectedAges instanceof Array && value.selectedAges.includes(age),
    ) as SelectedAge[];
  return value.ageGroup === "mixed"
    ? [3, 4, 5]
    : ["3", "4", "5"].includes(String(value.ageGroup))
      ? [Number(value.ageGroup) as SelectedAge]
      : [];
}
export function ageSelectionLabel(ages: readonly SelectedAge[]): string {
  return ages.length ? "만 " + ages.join("·") + "세반" : "연령 미선택";
}
