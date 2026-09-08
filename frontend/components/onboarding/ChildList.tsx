"use client";

import { useState } from "react";
import type { ChildEntry } from "@/lib/onboarding/types";
import { TextInput } from "./FormField";
import { GhostButton } from "./PrimaryButton";

/** 이름 중심의 단순한 아동 명단. */
export default function ChildList({
  children,
  onAdd,
  onRemove,
  disabled = false,
  idPrefix = "child",
}: {
  children: ChildEntry[];
  onAdd: (name: string) => void;
  onRemove: (id: string) => void;
  disabled?: boolean;
  idPrefix?: string;
}) {
  const [draft, setDraft] = useState("");
  const [dup, setDup] = useState(false);

  function submit() {
    if (disabled) return;
    const name = draft.trim();
    if (!name) return;
    if (children.some((c) => c.name === name)) {
      setDup(true);
      return;
    }
    onAdd(name);
    setDraft("");
    setDup(false);
  }

  return (
    <div className={`flex flex-col gap-6 ${disabled ? "opacity-60" : ""}`} aria-disabled={disabled || undefined}>
      <div className="flex flex-col gap-2">
        <label htmlFor={`${idPrefix}-name`} className="font-display text-[15px] text-ink">아동 추가</label>
        <div className="flex gap-2">
          <TextInput
            id={`${idPrefix}-name`}
            value={draft}
            disabled={disabled}
            placeholder={disabled ? "법정대리인 동의 확인 후 입력할 수 있어요" : "아동 이름 입력 후 Enter"}
            aria-invalid={dup || undefined}
            onChange={(e) => { setDraft(e.target.value); setDup(false); }}
            onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); submit(); } }}
            className={`flex-1 ${dup ? "border-peach-strong" : ""}`}
          />
          <GhostButton onClick={submit} disabled={disabled} className="shrink-0">+ 추가</GhostButton>
        </div>
        {dup && <p className="text-[12.5px] text-peach-ink">이미 같은 이름이 등록되어 있어요. 구분이 필요하면 성을 붙여 입력해주세요.</p>}
      </div>

      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <span className="font-display text-[15px] text-ink">
            아동 명단
            <span className="ml-1.5 align-middle font-mono text-[11px] px-2 py-0.5 rounded-full bg-mint-tint text-mint-ink">{children.length}명</span>
          </span>
          <span className="hidden lg:inline text-[12.5px] text-ink-soft">이름을 잘못 입력했다면 삭제 후 다시 추가해주세요</span>
        </div>

        {children.length === 0 ? (
          <div className="rounded-[18px] border border-dashed border-line bg-sage-tint px-3.5 py-5 text-center text-[13px] text-ink-soft">
            {disabled ? "동의 확인 후 아동 이름을 등록할 수 있어요." : "아직 등록된 아동이 없어요. 위에서 이름을 입력해 추가해주세요."}
          </div>
        ) : (
          <ul className="rounded-[18px] border-[1.5px] border-line overflow-hidden divide-y divide-line">
            {children.map((c, i) => (
              <li key={c.id} className="flex items-center gap-3 px-3.5 py-2.5 bg-paper">
                <span className="font-mono text-[11px] text-ink-soft w-[22px]">{String(i + 1).padStart(2, "0")}</span>
                <span aria-hidden="true" className="inline-flex items-center justify-center w-[34px] h-[34px] rounded-full bg-mint-tint text-mint-ink text-[13px] font-bold shrink-0">
                  {c.name.slice(-2)}
                </span>
                <span className="flex-1 text-[14.5px] text-ink">{c.name}</span>
                <button
                  type="button"
                  disabled={disabled}
                  onClick={() => onRemove(c.id)}
                  aria-label={`${c.name} 삭제`}
                  className="min-h-[36px] min-w-[44px] px-2.5 rounded-full text-[12.5px] text-ink-soft hover:text-peach-ink hover:bg-peach-tint transition-colors disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sage-ink"
                >
                  삭제
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
