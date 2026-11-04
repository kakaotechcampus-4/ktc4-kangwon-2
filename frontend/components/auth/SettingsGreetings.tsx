"use client";
import CharacterMessageGrid from "@/components/onboarding/CharacterMessageGrid";
import PrimaryButton from "@/components/onboarding/PrimaryButton";
import { DEFAULT_CHARACTER_MESSAGES, type ClassSettings, type Month } from "@/lib/onboarding/types";
import styles from "./Settings.module.css";

/**
 * 설정 화면의 성품인사. 온보딩 단계(StepCharacterMessages)와 칸은 같지만
 * 단계 제목 · 「이전」이 없다 — 설정에서는 돌아갈 단계가 없다.
 */
export default function SettingsGreetings({
  settings,
  onChange,
  onFinish,
}: {
  settings: ClassSettings;
  onChange: (p: Partial<ClassSettings>) => void;
  onFinish: () => void;
}) {
  return (
    <div className="flex flex-col gap-4">
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

      <div className={styles.saveRow}>
        <PrimaryButton onClick={onFinish} className="flex-1 lg:flex-none lg:min-w-[140px]">
          성품인사 저장
        </PrimaryButton>
      </div>
    </div>
  );
}
