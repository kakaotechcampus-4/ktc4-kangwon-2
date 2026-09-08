import type { AgeGroup } from "@/lib/plan-generator/types";

export type { AgeGroup };

/** 온보딩 3단계 + 완료 */
export type OnboardingStep = 1 | 2 | 3 | "done";

export interface ChildEntry {
  id: string;
  name: string;
}

export interface ClassroomEntry {
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

/** 온보딩 명세 기준으로 3·4·5세만 노출한다. 계획안 생성 페이지는 혼합반 타입을 계속 지원할 수 있다. */
export const AGE_OPTIONS: { value: Exclude<AgeGroup, "mixed">; label: string }[] = [
  { value: "3", label: "3세" },
  { value: "4", label: "4세" },
  { value: "5", label: "5세" },
];

export const STEP_LABELS: Record<Exclude<OnboardingStep, "done">, string> = {
  1: "원 정보",
  2: "반 정보",
  3: "성품인사",
};
