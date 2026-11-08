"use client";
import { useState } from "react";
import type { PlayMonthlyActivity } from "@/lib/api/types";
import PlayMonthlyConfirm from "./PlayMonthlyConfirm";

/** 놀이 행 하나 빼기(09d 「이 활동 빼기」). 행 삭제는 되돌리기가 없어 확인 상자를 거친다. */
export default function PlayMonthlyRowRemove({
  activity,
  section,
  onRemove,
  disabled,
  isLastInSection,
}: {
  activity: PlayMonthlyActivity;
  /** 구역 이름 — 예: 「함께 하는 활동」 */
  section: string;
  onRemove: (itemId: string) => void;
  disabled: boolean;
  isLastInSection: boolean;
}) {
  const [asking, setAsking] = useState(false);
  // 상자를 연 뒤 disabled 가 되면 상자도 닫는다.
  if (disabled && asking) setAsking(false);
  return (
    <div className="flex flex-col gap-2">
      <button
        type="button"
        data-act="remove"
        aria-label={`${section} 행 빼기: ${activity.name.value}`}
        className="inline-flex min-h-[44px] items-center justify-center gap-1.5 rounded-md border-2 border-[#ecc8c2] bg-[#fdf3f1] text-[15px] font-bold text-[#b3261e] hover:bg-[#fbe4df] disabled:opacity-40"
        disabled={disabled}
        onClick={() => setAsking(true)}
      >
        <span aria-hidden="true" className="text-[18px] leading-none">
          −
        </span>
        이 활동 빼기
      </button>
      {isLastInSection && (
        <small className="text-[12px] text-[#5c5243]">
          마지막 행이에요. 빼면 {section}에 행이 없어 확정할 수 없어요.
        </small>
      )}
      {asking && (
        <PlayMonthlyConfirm
          message="이 행을 빼면 되돌릴 수 없어요. 뺄까요?"
          yes="빼기"
          disabled={disabled}
          onYes={() => {
            if (disabled) return;
            setAsking(false);
            onRemove(activity.activity_id);
          }}
          onNo={() => setAsking(false)}
        />
      )}
    </div>
  );
}
