"use client";

import { useEffect, useRef } from "react";
import { DEFAULT_CHARACTER_MESSAGES, MONTH_ORDER, type CharacterMessages, type Month } from "@/lib/onboarding/types";
import { TextButton } from "./PrimaryButton";

export default function CharacterMessageGrid({
  messages,
  onChange,
  onResetAll,
  currentMonth = new Date().getMonth() + 1,
  disabled = false,
}: {
  messages: CharacterMessages;
  onChange: (month: Month, text: string) => void;
  onResetAll: () => void;
  currentMonth?: number;
  disabled?: boolean;
}) {
  const editedCount = MONTH_ORDER.filter((m) => messages[m] !== DEFAULT_CHARACTER_MESSAGES[m]).length;

  return (
    <div className={`flex flex-col gap-3 ${disabled ? "opacity-55" : ""}`} aria-disabled={disabled || undefined}>
      <div className="flex flex-col items-start gap-0.5 lg:flex-row lg:items-center lg:justify-between">
        <span className="text-[12.5px] text-ink-soft">
          {disabled
            ? "성품교육을 사용하지 않는 상태예요"
            : editedCount === 0
              ? "기본 문구를 그대로 사용 중이에요"
              : `${editedCount}개 월의 문구를 직접 수정했어요`}
        </span>
        <TextButton onClick={onResetAll} disabled={disabled || editedCount === 0} className="disabled:opacity-50 disabled:hover:bg-transparent">
          기본 문구로 모두 되돌리기
        </TextButton>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2.5 lg:gap-3">
        {MONTH_ORDER.map((m) => (
          <MessageCard
            key={m}
            month={m}
            value={messages[m]}
            isCurrent={m === currentMonth}
            edited={messages[m] !== DEFAULT_CHARACTER_MESSAGES[m]}
            disabled={disabled}
            onChange={(v) => onChange(m, v)}
          />
        ))}
      </div>
    </div>
  );
}

function MessageCard({
  month, value, isCurrent, edited, disabled, onChange,
}: {
  month: Month;
  value: string;
  isCurrent: boolean;
  edited: boolean;
  disabled: boolean;
  onChange: (v: string) => void;
}) {
  const ref = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight}px`;
  }, [value]);

  return (
    <div className={`rounded-[18px] border-[1.5px] border-line bg-paper p-3 flex flex-col gap-2 transition-colors ${disabled ? "bg-sage-tint" : "focus-within:border-sage-ink"}`}>
      <div className="flex items-center justify-between">
        <span className={`font-mono text-[11px] tracking-wide px-2.5 py-[3px] rounded-full font-medium ${isCurrent ? "bg-sage text-ink" : "bg-sage-tint text-sage-ink"}`}>
          {month}월{isCurrent ? " · 이번 달" : ""}
        </span>
        {!disabled && edited && <span className="font-mono text-[10px] px-1.5 rounded-full bg-peach-tint text-peach-ink">수정됨</span>}
      </div>
      <textarea
        ref={ref}
        rows={1}
        value={value}
        disabled={disabled}
        aria-label={`${month}월 성품인사`}
        onChange={(e) => onChange(e.target.value)}
        className="w-full resize-none overflow-hidden bg-transparent border-0 p-0.5 text-[15px] lg:text-[13.5px] leading-[1.55] text-ink focus:outline-none disabled:cursor-not-allowed"
      />
    </div>
  );
}
