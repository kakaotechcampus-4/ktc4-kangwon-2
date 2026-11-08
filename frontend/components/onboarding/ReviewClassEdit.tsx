"use client";

import { useState } from "react";
import AgeSelection from "./AgeSelection";
import OnboardingLayout from "./OnboardingLayout";
import { ConsentBox } from "./ClassFlow";
import { CtaButton, ErrorLine, LineField, Question } from "./FlowParts";
import {
  NOTICE_CONSENT_BLOCKED,
  consentOffBlocked,
  draftOf,
  submitClassEdit,
  type ClassDraft,
} from "@/lib/onboarding/classEdit";
import type { ClassroomEntry } from "@/lib/onboarding/types";

/**
 * 마지막 확인에서 반 하나를 고친다. 네 칸을 한 화면에 두고, **「저장」 전에는 아무것도 보내지 않는다**
 * (api-spec 반 수정 「FE 규칙」). 보내는 것은 바뀐 칸뿐이다.
 */
export default function ReviewClassEdit({
  entry,
  onSaved,
  onNotice,
  onCancel,
}: {
  entry: ClassroomEntry;
  /** 서버가 돌려준 반을 화면 · 저장소에 반영한다. */
  onSaved: (next: ClassroomEntry) => void;
  onNotice: (message: string) => void;
  onCancel: () => void;
}) {
  const [draft, setDraft] = useState<ClassDraft>(() => draftOf(entry));
  const [nameError, setNameError] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const patch = (p: Partial<ClassDraft>) => setDraft((d) => ({ ...d, ...p }));
  const valid =
    draft.className.trim() !== "" &&
    draft.teacherName.trim() !== "" &&
    draft.selectedAges.length > 0;

  function toggleConsent(checked: boolean) {
    // 아이가 있는 반은 동의를 끌 수 없다. 체크는 그대로 둔다.
    if (consentOffBlocked(entry, checked)) {
      onNotice(NOTICE_CONSENT_BLOCKED);
      return;
    }
    patch({ guardianConsent: checked });
  }

  async function save() {
    if (busy || !valid) return;
    setBusy(true);
    setError("");
    setNameError("");
    const result = await submitClassEdit(entry, draft);
    setBusy(false);
    if (result.ok) {
      onSaved(result.entry);
      if (result.notice) onNotice(result.notice);
      return;
    }
    if (result.nameError) setNameError(result.nameError);
    if (result.notice) {
      onNotice(result.notice);
      patch({ guardianConsent: entry.guardianConsent });
    }
    if (result.error) setError(result.error);
  }

  return (
    <OnboardingLayout
      stage={4}
      say={{ title: "고쳐 볼까요?", body: "고친 내용은 바로 저장돼요." }}
      progress={1}
      onBack={onCancel}
      footer={
        <CtaButton disabled={busy || !valid} onClick={() => void save()}>
          {busy ? "저장 중이에요" : "저장"}
        </CtaButton>
      }
    >
      <Question title={"반 정보를\n고쳐주세요"} hint="칸을 눌러 바로 고치고 저장해 주세요." />
      <LineField
        id="editClassName"
        label="반 이름"
        active={false}
        value={draft.className}
        error={nameError}
        onChange={(e) => {
          patch({ className: e.target.value });
          setNameError("");
        }}
      />
      <AgeSelection
        value={draft.selectedAges}
        onChange={(selectedAges) => patch({ selectedAges })}
      />
      <LineField
        id="editTeacherName"
        label="담임 이름"
        active={false}
        value={draft.teacherName}
        onChange={(e) => patch({ teacherName: e.target.value })}
      />
      <div className="mb-7">
        <ConsentBox checked={draft.guardianConsent} onChange={toggleConsent} />
      </div>
      <ErrorLine>{error}</ErrorLine>
    </OnboardingLayout>
  );
}
