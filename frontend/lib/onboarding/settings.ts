/**
 * 온보딩 설정 mock 저장소.
 * 지금은 localStorage에 저장하고, API가 준비되면 load/save 내부만 fetch로 교체한다.
 */
import {
  selectedAgesFor,
  DEFAULT_CHARACTER_MESSAGES,
  EMPTY_CLASS_SETTINGS,
  MONTH_ORDER,
  createEmptyClassroom,
  type ClassSettings,
  type ClassroomEntry,
} from "./types";

import { accountStorageKey } from "../auth/demo-session";
const KEY = "saessak.classSettings";
export const CLASS_SETTINGS_CHANGED = "saessak:class-settings-changed";

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function stringValue(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function uniqueId(value: unknown, fallback: string, used: Set<string>): string {
  let id = stringValue(value).trim() || fallback;
  while (used.has(id)) id += "-duplicate";
  used.add(id);
  return id;
}

function normalizeClassroom(value: unknown, index: number, usedIds: Set<string>): ClassroomEntry {
  const raw = isRecord(value) ? value : {};
  const base = createEmptyClassroom(uniqueId(raw.id, `class-${index + 1}`, usedIds));
  const childIds = new Set<string>();
  return {
    ...base,
    className: stringValue(raw.className),
    teacherName: stringValue(raw.teacherName),
    selectedAges: selectedAgesFor(raw),
    ageGroup:
      raw.ageGroup === "3" ||
      raw.ageGroup === "4" ||
      raw.ageGroup === "5" ||
      raw.ageGroup === "mixed"
        ? raw.ageGroup
        : "",
    currentChildCount:
      typeof raw.currentChildCount === "number" &&
      Number.isSafeInteger(raw.currentChildCount) &&
      raw.currentChildCount >= 0
        ? raw.currentChildCount
        : "",
    guardianConsent: raw.guardianConsent === true,
    childrenSkipped: raw.childrenSkipped === true,
    children: Array.isArray(raw.children)
      ? raw.children
          .filter(isRecord)
          .filter((child) => stringValue(child.name).trim() !== "")
          .map((child, i) => ({
            id: uniqueId(child.id, `child-${i + 1}`, childIds),
            name: stringValue(child.name).trim(),
            ...(typeof child.code === "string" ? { code: child.code } : {}),
          }))
      : [],
  };
}

/**
 * 기존 단일 반 저장 구조(className / ageGroup / children)도 새 classes[] 구조로 마이그레이션한다.
 */
function normalizeSettings(parsed: Record<string, unknown>): ClassSettings {
  const rawClasses = Array.isArray(parsed.classes)
    ? (parsed.classes as Partial<ClassroomEntry>[])
    : null;

  const legacyClass =
    !rawClasses &&
    (typeof parsed.className === "string" ||
      typeof parsed.ageGroup === "string" ||
      Array.isArray(parsed.children))
      ? [
          {
            id: "class-1",
            className: typeof parsed.className === "string" ? parsed.className : "",
            ageGroup: typeof parsed.ageGroup === "string" ? parsed.ageGroup : "",
            currentChildCount: "",
            teacherName: "",
            guardianConsent: false,
            childrenSkipped: false,
            children: Array.isArray(parsed.children) ? parsed.children : [],
          } as Partial<ClassroomEntry>,
        ]
      : null;

  const classesSource = rawClasses ?? legacyClass ?? EMPTY_CLASS_SETTINGS.classes;
  const classIds = new Set<string>();
  const classes =
    classesSource.length > 0
      ? classesSource.map((c, i) => normalizeClassroom(c, i, classIds))
      : [createEmptyClassroom()];

  const characterMessages = { ...DEFAULT_CHARACTER_MESSAGES };
  if (isRecord(parsed.characterMessages)) {
    for (const month of MONTH_ORDER) {
      const message = parsed.characterMessages[month];
      if (typeof message === "string") characterMessages[month] = message;
    }
  }

  return {
    ...EMPTY_CLASS_SETTINGS,
    orgName: typeof parsed.orgName === "string" ? parsed.orgName : "",
    directorName: typeof parsed.directorName === "string" ? parsed.directorName : "",
    regionProvince: typeof parsed.regionProvince === "string" ? parsed.regionProvince : "",
    regionDistrict: typeof parsed.regionDistrict === "string" ? parsed.regionDistrict : "",
    classes,
    primaryClassId: classes.some((c) => c.id === parsed.primaryClassId)
      ? String(parsed.primaryClassId)
      : classes[0]?.id,
    characterEducationEnabled:
      typeof parsed.characterEducationEnabled === "boolean"
        ? parsed.characterEducationEnabled
        : true,
    characterMessages,
    completedAt: typeof parsed.completedAt === "string" ? parsed.completedAt : undefined,
  };
}

export function loadClassSettings(): ClassSettings | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(accountStorageKey(KEY));
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    return isRecord(parsed) ? normalizeSettings(parsed) : null;
  } catch {
    return null;
  }
}

export function saveClassSettings(settings: ClassSettings): boolean {
  if (typeof window === "undefined") return false;
  try {
    window.localStorage.setItem(accountStorageKey(KEY), JSON.stringify(settings));
    window.dispatchEvent(new Event(CLASS_SETTINGS_CHANGED));
    return true;
  } catch {
    return false;
  }
}

export function clearClassSettings() {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(accountStorageKey(KEY));
    window.dispatchEvent(new Event(CLASS_SETTINGS_CHANGED));
  } catch {
    /* noop */
  }
}

/** 등록 명단을 우선 합산하고, 빈 명단만 초기 참고 인원을 사용한다. */
export function totalChildrenFor(settings: ClassSettings | null): number {
  return (
    settings?.classes.reduce(
      (total, classroom) =>
        total +
        (classroom.children.length > 0
          ? classroom.children.length
          : classroom.currentChildCount === ""
            ? 0
            : classroom.currentChildCount),
      0,
    ) ?? 0
  );
}

/** 계획안 생성 화면의 기본 반으로 첫 번째 반을 사용한다. */
export function primaryClassFor(settings: ClassSettings | null): ClassroomEntry | null {
  if (!settings || settings.classes.length === 0) return null;
  return (
    settings.classes.find((c) => c.id === settings.primaryClassId) ?? settings.classes[0] ?? null
  );
}

/** 로그인 계정명을 우선하고, 이름이 없는 이전 계정만 해당 계정의 반 설정을 사용한다. */
export function planHeaderFor(settings: ClassSettings | null, teacherName: string | null): string {
  const classroom = primaryClassFor(settings);
  const name = teacherName?.trim();
  return [
    settings?.orgName.trim() || "기관 미설정",
    name ? `${name} 선생님` : "선생님",
    classroom?.className.trim(),
  ]
    .filter(Boolean)
    .join(" · ");
}

/** 성품인사에서 특정 월의 문구만 꺼낼 때 (계획안 생성 시 활용) */
export function characterMessageFor(settings: ClassSettings | null, month: number): string | null {
  if (!settings || !settings.characterEducationEnabled) return null;
  const m = month as keyof ClassSettings["characterMessages"];
  return settings.characterMessages[m] ?? null;
}
