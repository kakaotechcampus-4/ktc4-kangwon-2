import { shownPrimaryId } from "./settings";
import { selectedAgesFor, type ClassSettings, type ClassroomEntry } from "./types";

export type OnboardingRoute = "center" | "classes" | "children" | "review";

export const REVIEW_PATH = "/onboarding/review";

/**
 * 이 주소에서 다른 곳으로 돌려보낼지. 없으면 `null`.
 *
 * 앞 단계가 비어 있으면 그 단계로 간다. 설정은 온보딩과 따로 돌아 여기로 오지 않는다.
 */
export function startupRedirect(route: OnboardingRoute, destination: string): string | null {
  if (route !== "center" && destination === "/onboarding/center") return destination;
  if ((route === "children" || route === "review") && destination === "/onboarding/classes")
    return destination;
  return null;
}

/** 반을 하나 등록하면 이어서 가는 곳. 한 반만 이어 받아 아이를 넣고 마지막 확인으로 돌아온다. */
export const childrenPathAfterAdd = (classId: string) =>
  `/onboarding/children?class=${encodeURIComponent(classId)}&back=review`;

/** 이름 · 연령 · 담임이 다 찬 반만 등록된 반으로 본다. 옛 흐름에서 남은 빈 반은 버린다. */
export const isCompleteClass = (c: ClassroomEntry) =>
  c.className.trim() !== "" && c.teacherName.trim() !== "" && selectedAgesFor(c).length > 0;

/** 「이대로 시작할게요」를 누를 때 저장할 값. 주로 보는 반은 고를 수 있을 때(2개 이상)만 확정한다. */
export function finishedSettings(settings: ClassSettings, now = new Date()): ClassSettings {
  const primary = settings.classes.length > 1 ? { primaryClassId: shownPrimaryId(settings) } : {};
  return { ...settings, ...primary, completedAt: now.toISOString() };
}

export const showsPrimarySelect = (settings: ClassSettings) => settings.classes.length >= 2;
