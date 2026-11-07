import { errorCode, isAlreadyExists } from "../api/client";
import { hasAnnualPlan, saveClassEdit } from "../api/onboarding";
import { selectedAgesFor, type ClassroomEntry, type SelectedAge } from "./types";

export interface ClassDraft {
  className: string;
  selectedAges: SelectedAge[];
  teacherName: string;
  guardianConsent: boolean;
}

export const NOTICE_CONSENT_BLOCKED = "아이 명단이 있어 동의를 끌 수 없어요";
export const NOTICE_AGES_CHANGED = "연령을 바꿨어요. 이미 만든 계획안의 연령은 바뀌지 않아요";
export const NAME_TAKEN = "같은 이름의 반이 이미 있어요";

export const draftOf = (c: ClassroomEntry): ClassDraft => ({
  className: c.className,
  selectedAges: selectedAgesFor(c),
  teacherName: c.teacherName,
  guardianConsent: c.guardianConsent,
});

/** 바뀐 칸만 담는다. 서버에는 이것만 보낸다(api-spec 「FE 규칙」). */
export function changedFields(entry: ClassroomEntry, draft: ClassDraft) {
  const patch: Partial<ClassDraft> = {};
  const name = draft.className.trim();
  const teacher = draft.teacherName.trim();
  const before = selectedAgesFor(entry);
  if (name !== entry.className) patch.className = name;
  if (teacher !== entry.teacherName) patch.teacherName = teacher;
  if (draft.guardianConsent !== entry.guardianConsent)
    patch.guardianConsent = draft.guardianConsent;
  if (draft.selectedAges.join() !== before.join()) patch.selectedAges = draft.selectedAges;
  return patch;
}

/** 아이가 있는 반의 동의는 끌 수 없다 — 서버에 보내기 전에 화면이 먼저 막는다. */
export const consentOffBlocked = (entry: ClassroomEntry, checked: boolean) =>
  !checked && entry.children.length > 0;

export type ClassEditResult =
  | { ok: true; entry: ClassroomEntry; notice?: string }
  | { ok: false; nameError?: string; notice?: string; error?: string };

const API = { saveClassEdit, hasAnnualPlan };

/** 「저장」을 눌렀을 때만 부른다. 오류는 코드로 갈라 화면이 쓸 말로 돌려준다. */
export async function submitClassEdit(
  entry: ClassroomEntry,
  draft: ClassDraft,
  api: typeof API = API,
): Promise<ClassEditResult> {
  if (consentOffBlocked(entry, draft.guardianConsent) && entry.guardianConsent)
    return { ok: false, notice: NOTICE_CONSENT_BLOCKED };
  const patch = changedFields(entry, draft);
  if (Object.keys(patch).length === 0) return { ok: true, entry };
  try {
    const next = await api.saveClassEdit(entry, patch);
    const agesChanged = patch.selectedAges !== undefined;
    // 저장은 이미 끝났다. 계획안을 못 읽었다고 실패로 돌려주지 않고 안내만 건너뛴다.
    const hasPlan = agesChanged && (await api.hasAnnualPlan(next).catch(() => false));
    const notice = hasPlan ? NOTICE_AGES_CHANGED : undefined;
    return { ok: true, entry: next, notice };
  } catch (e) {
    if (isAlreadyExists(e)) return { ok: false, nameError: NAME_TAKEN };
    if (errorCode(e) === "GATE_BLOCKED") return { ok: false, notice: NOTICE_CONSENT_BLOCKED };
    return { ok: false, error: e instanceof Error ? e.message : "저장하지 못했어요." };
  }
}
