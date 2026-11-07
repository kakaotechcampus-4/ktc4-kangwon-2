"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

/**
 * 확정하기 옆 「임시저장」 — 계획안 편집 화면이 같이 쓴다.
 * 칸은 입력을 멈추거나 떠나면 저절로 저장된다. 이 단추는 열린 입력창을 닫아 마지막 글까지 저장 줄에 넣고,
 * 줄이 다 끝나면 계획안 첫 화면으로 간다 — 초안 그대로라 「이어서 하기」에 보인다.
 * `save` 는 남은 저장이 모두 성공하면 true. 실패면 그 화면에 남는다(실패 안내 · 「다시 저장」은 각 화면이 보인다).
 */
export default function DraftSave({
  save,
  disabled,
}: {
  save: () => Promise<boolean>;
  disabled?: boolean;
}) {
  const router = useRouter();
  const [saving, setSaving] = useState(false);
  return (
    <button
      type="button"
      className="min-h-[44px] rounded-md border border-line bg-paper px-4 text-sm font-bold text-[#5e4b96] transition-transform hover:bg-[#f6f1fb] active:translate-x-[2px] active:translate-y-[3px] disabled:opacity-40"
      disabled={disabled || saving}
      onClick={async () => {
        (document.activeElement as HTMLElement | null)?.blur();
        setSaving(true);
        const ok = await save().catch(() => false);
        if (ok) router.push("/plans");
        else setSaving(false);
      }}
    >
      {saving ? "저장 중…" : "임시저장"}
    </button>
  );
}
