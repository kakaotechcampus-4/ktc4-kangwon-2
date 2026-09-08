/**
 * 온보딩 설정 mock 저장소.
 * 지금은 localStorage에 저장하고, API가 준비되면 load/save 내부만 fetch로 교체한다.
 */
import {
  DEFAULT_CHARACTER_MESSAGES,
  EMPTY_CLASS_SETTINGS,
  createEmptyClassroom,
  type ClassSettings,
  type ClassroomEntry,
} from "./types";

const KEY = "saessak.classSettings";

function normalizeClassroom(raw: Partial<ClassroomEntry> | undefined, index: number): ClassroomEntry {
  const base = createEmptyClassroom(raw?.id || `class-${index + 1}`);
  return {
    ...base,
    ...raw,
    ageGroup: raw?.ageGroup === "mixed" ? "" : (raw?.ageGroup ?? ""),
    children: Array.isArray(raw?.children) ? raw.children : [],
  };
}

/**
 * 기존 단일 반 저장 구조(className / ageGroup / children)도 새 classes[] 구조로 마이그레이션한다.
 */
function normalizeSettings(parsed: Record<string, unknown>): ClassSettings {
  const rawClasses = Array.isArray(parsed.classes)
    ? (parsed.classes as Partial<ClassroomEntry>[])
    : null;

  const legacyClass = !rawClasses && (
    typeof parsed.className === "string" ||
    typeof parsed.ageGroup === "string" ||
    Array.isArray(parsed.children)
  )
    ? [{
        id: "class-1",
        className: typeof parsed.className === "string" ? parsed.className : "",
        ageGroup: typeof parsed.ageGroup === "string" ? parsed.ageGroup : "",
        currentChildCount: "",
        teacherName: "",
        guardianConsent: false,
        childrenSkipped: false,
        children: Array.isArray(parsed.children) ? parsed.children : [],
      } as Partial<ClassroomEntry>]
    : null;

  const classesSource = rawClasses ?? legacyClass ?? EMPTY_CLASS_SETTINGS.classes;
  const classes = classesSource.length > 0
    ? classesSource.map((c, i) => normalizeClassroom(c, i))
    : [createEmptyClassroom()];

  return {
    ...EMPTY_CLASS_SETTINGS,
    ...parsed,
    orgName: typeof parsed.orgName === "string" ? parsed.orgName : "",
    directorName: typeof parsed.directorName === "string" ? parsed.directorName : "",
    regionProvince: typeof parsed.regionProvince === "string" ? parsed.regionProvince : "",
    regionDistrict: typeof parsed.regionDistrict === "string" ? parsed.regionDistrict : "",
    classes,
    characterEducationEnabled: typeof parsed.characterEducationEnabled === "boolean"
      ? parsed.characterEducationEnabled
      : true,
    characterMessages: {
      ...DEFAULT_CHARACTER_MESSAGES,
      ...(parsed.characterMessages && typeof parsed.characterMessages === "object"
        ? parsed.characterMessages as Partial<ClassSettings["characterMessages"]>
        : {}),
    },
    completedAt: typeof parsed.completedAt === "string" ? parsed.completedAt : undefined,
  };
}

export function loadClassSettings(): ClassSettings | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    return normalizeSettings(parsed);
  } catch {
    return null;
  }
}

export function saveClassSettings(settings: ClassSettings) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(KEY, JSON.stringify(settings));
  } catch {
    /* 저장 불가 환경에서는 조용히 무시 */
  }
}

export function clearClassSettings() {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(KEY);
  } catch {
    /* noop */
  }
}

/** 계획안 생성 화면의 기본 반으로 첫 번째 반을 사용한다. */
export function primaryClassFor(settings: ClassSettings | null): ClassroomEntry | null {
  if (!settings || settings.classes.length === 0) return null;
  return settings.classes[0] ?? null;
}

/** 성품인사에서 특정 월의 문구만 꺼낼 때 (계획안 생성 시 활용) */
export function characterMessageFor(settings: ClassSettings | null, month: number): string | null {
  if (!settings || !settings.characterEducationEnabled) return null;
  const m = month as keyof ClassSettings["characterMessages"];
  return settings.characterMessages[m] ?? null;
}
