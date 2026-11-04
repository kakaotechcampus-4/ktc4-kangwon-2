"use client";

import { StepFooter, StepHeading } from "./OnboardingLayout";
import CharacterMessageGrid from "./CharacterMessageGrid";
import PrimaryButton, { GhostButton } from "./PrimaryButton";
import { DEFAULT_CHARACTER_MESSAGES, type ClassSettings, type Month } from "@/lib/onboarding/types";

// 월별 성품인사 — 설정 화면이 쓴다.
export function StepCharacterMessages({
  settings,
  onChange,
  onPrev,
  onFinish,
}: {
  settings: ClassSettings;
  onChange: (p: Partial<ClassSettings>) => void;
  onPrev: () => void;
  onFinish: () => void;
}) {
  return (
    <>
      <StepHeading
        title="월별 성품인사를 설정해주세요"
        description="월별 성품인사를 확인하고 필요하면 수정해주세요. 설정한 문구는 해당 월의 계획안 작성에 활용돼요."
      />

      <div className="rounded-md border border-line bg-cream px-4 py-3.5">
        <label className="flex items-start gap-3 cursor-pointer">
          <input
            type="checkbox"
            checked={!settings.characterEducationEnabled}
            onChange={(e) => onChange({ characterEducationEnabled: !e.target.checked })}
            className="mt-0.5 w-4 h-4 accent-[var(--pg-primary)]"
          />
          <span>
            <span className="block text-[13.5px] font-medium text-ink">
              성품교육을 사용하지 않습니다.
            </span>
            <span className="block mt-1 text-[12px] text-ink-soft">
              체크하면 아래 12개월 성품인사를 계획안에서 사용하지 않아요.
            </span>
          </span>
        </label>
      </div>

      <CharacterMessageGrid
        messages={settings.characterMessages}
        disabled={!settings.characterEducationEnabled}
        onChange={(month: Month, text) =>
          onChange({ characterMessages: { ...settings.characterMessages, [month]: text } })
        }
        onResetAll={() => onChange({ characterMessages: { ...DEFAULT_CHARACTER_MESSAGES } })}
      />

      <StepFooter
        left={<GhostButton onClick={onPrev}>이전</GhostButton>}
        right={
          <PrimaryButton onClick={onFinish} className="flex-1 lg:flex-none lg:min-w-[140px]">
            설정 완료
          </PrimaryButton>
        }
      />
    </>
  );
}
